"""Итог домашнего блока уходит в GetCourse Tech API (Шаг 6.2).

Три правила, из которых растёт этот файл:

1. **Наружу идут только числа.** Ни ответа ученика, ни эталона книги, ни заметки
   преподавателя здесь нет и быть не может: в GetCourse живёт методист, а не разбор
   решения. Процент считается тем же `score_submission`, что и матрица тренера, —
   иначе витрина и выгрузка разойдутся на том самом `pending_review`.
2. **Ключей нет — отправки нет, но журнал есть.** Пока `GC_ACCOUNT_NAME` и
   `GC_SECRET_KEY` не заданы, строка в `LessonReport` заводится со статусом
   «не отправлено»: урок сдаётся, методист потом видит, что именно платформа
   собиралась сообщить, а тренер не гадал бы, дошла ли она до выгрузки.
3. **Одна строка на (урок, ученик, блок).** Повторный клик «Сдать» и повторная
   правка последнего вердикта не плодят отправок: те же числа — та же строка без
   нового вызова, новые числа — одна допись поверх прежнего значения.

Падение сети уроком быть не может: ошибка ловится, считается попытку и ложится в
`last_error`, а следующий триггер её повторит.
"""
import json
import logging

from django.conf import settings
from django.utils import timezone

from .lesson_grading import score_submission
from .models import LessonReport

logger = logging.getLogger(__name__)

# Событие одно и то же на все отправки: менять строку — значит рассорить уже
# написанные в GetCourse правила приёма.
EVENT_TYPE = 'lesson.homework.completed'


def is_configured():
    """Есть ли чем слать. Нет аккаунта или секретного ключа — модуль no-op."""
    return bool(settings.GC_ACCOUNT_NAME and settings.GC_SECRET_KEY)


def external_key(submission):
    """Идемпотентность: урок + ученик + блок. Сданный дважды блок — одна строка."""
    return '%s:%s:%s' % (submission.assignment_id, submission.student_id, submission.block_id)


def numbers_for(submission):
    """Те самые числа: те же, что матрица показывает тренеру."""
    score = score_submission(submission)
    answers = list(submission.answers.select_related('question'))
    return {
        'total': score['total'],
        'correct': sum(1 for a in answers if a.verdict == 'correct'),
        'pending_review': score['pending'],
        'percent': score['percent'],
        'earned': score['earned'],
        'possible': score['possible'],
    }


def is_ready(submission):
    """Пора ли слать: домашка сдана, и финальный вердикт есть по каждой задаче.

    `pending_review` блокирует отправку намеренно: половину проверка ещё не видела,
    а половинчатый процент методист прочитает как итог.
    """
    block = submission.block
    if block is None or block.kind != 'homework':
        return False
    if submission.state == 'in_progress':
        return False
    if not (block.question_ids or []):
        return False
    if submission.answers.filter(verdict='pending_review').exists():
        return False
    return submission.answers.exists()


def build_event(submission, numbers):
    return {
        'type': EVENT_TYPE,
        'gc_uid': submission.student.gc_uid,
        'assignment_id': submission.assignment_id,
        'block_id': submission.block_id,
        'external_key': external_key(submission),
        'percent': numbers['percent'],
        'total': numbers['total'],
        'correct': numbers['correct'],
        'pending_review': numbers['pending_review'],
        'occurred_at': (submission.last_submitted_at or submission.reviewed_at
                        or timezone.now()).isoformat(),
    }


def _post(event):
    """Один вызов к Tech API. Возвращает (успех, что не так).

    GetCourse отвечает `200` и на отказ, поэтому код — ещё не вердикт: смотрим
    `success` в теле, если он там есть.
    """
    url = settings.GC_TECH_URL
    if not url:
        return False, 'GC_TECH_URL не собран'
    body = {
        'secret_key': settings.GC_SECRET_KEY,
        'method': settings.GC_TECH_METHOD,
        'data': json.dumps(event, ensure_ascii=False),
    }
    if settings.GC_CUSTOM_FIELD_ID:
        body['customFieldId'] = settings.GC_CUSTOM_FIELD_ID
    try:
        import requests
        resp = requests.post(url, data=body, timeout=15)
    except Exception as exc:
        return False, '%s: %s' % (type(exc).__name__, exc)
    if not (200 <= resp.status_code < 300):
        return False, 'HTTP %s: %s' % (resp.status_code, resp.text[:300])
    try:
        answer = resp.json()
    except ValueError:
        return True, ''
    if isinstance(answer, dict) and answer.get('success') is False:
        return False, str(answer.get('errors') or answer)[:500]
    return True, ''


def report_submission(submission):
    """Триггер из сдачи блока и из последней ручной проверки.

    Возвращает строку журнала или `None`, если слать было рано. Исключений наружу
    не отдаёт ни при каком раскладе: отказ GetCourse не отменяет ученику его сдачу.
    """
    submission.refresh_from_db()
    if not is_ready(submission):
        return None
    numbers = numbers_for(submission)
    event = build_event(submission, numbers)
    key = external_key(submission)
    sent_numbers = {k: event[k] for k in ('percent', 'total', 'correct', 'pending_review')}

    row, created = LessonReport.objects.get_or_create(
        external_key=key,
        defaults={'assignment': submission.assignment, 'block': submission.block,
                  'student': submission.student, 'gc_uid': submission.student.gc_uid,
                  'event_type': EVENT_TYPE, 'payload': sent_numbers,
                  'percent': numbers['percent'], 'total': numbers['total'],
                  'correct': numbers['correct'], 'pending_review': numbers['pending_review']})

    same_numbers = (row.percent == sent_numbers['percent'] and row.total == sent_numbers['total']
                    and row.correct == sent_numbers['correct']
                    and row.pending_review == sent_numbers['pending_review'])
    if row.status == 'sent' and same_numbers:
        return row

    if not is_configured():
        row.status = 'skipped'
        row.last_error = '' if submission.student.gc_uid else 'у ученика нет gc_uid'
        row.save()
        return row
    if not submission.student.gc_uid:
        row.status = 'skipped'
        row.last_error = 'у ученика нет gc_uid: в GetCourse его не на что опознать'
        row.save()
        return row

    try:
        ok, error = _post(event)
    except Exception as exc:
        # сам вызов не обязан быть предсказуемым: падение сети или чужой код не
        # имеют права отменить ученику сдачу или тренеру его вердикт
        ok, error = False, '%s: %s' % (type(exc).__name__, exc)
    row.attempts += 1
    row.gc_uid = submission.student.gc_uid
    row.payload = sent_numbers
    row.percent = numbers['percent']
    row.total = numbers['total']
    row.correct = numbers['correct']
    row.pending_review = numbers['pending_review']
    row.last_error = error
    if ok:
        row.status = 'sent'
        row.sent_at = timezone.now()
    else:
        row.status = 'failed'
        logger.warning('GetCourseTech API: %s — %s', key, error)
    row.save()
    return row
