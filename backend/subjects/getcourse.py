"""Итог домашнего блока уходит в GetCourse Lesson API (Шаг 6.2, транспорт переключён 19.10).

Контракт — `POST {GETCOURSE_API_URL}/user/update-custom-fields` с
`Authorization: Bearer {GETCOURSE_API_TOKEN}` и телом
`{"userId": <gc_uid>, "customFields": {"<GC_CUSTOM_FIELD_ID>": "<строка итога>"}}`:
процент ложится на карточку ученика, которую методист и так видит. Связка через
`lessonAnswerId` (статус ответа урока + комментарий) отвергнута владельцем: ученик
решает в тренажёре и не обязан ради отчётности писать ответ в форму урока.

Три правила, из которых растёт этот файл:

1. **Наружу идут только числа.** Ни ответа ученика, ни эталона книги, ни заметки
   преподавателя здесь нет и быть не может: в GetCourse живёт методист, а не разбор
   решения. Процент считается тем же `score_submission`, что и матрица тренера, —
   иначе витрина и выгрузка разойдутся на том самом `pending_review`.
2. **Ключей нет — отправки нет, но журнал есть.** Пока `GETCOURSE_API_TOKEN` или
   `GC_CUSTOM_FIELD_ID` не заданы, строка в `LessonReport` заводится со статусом
   «не отправлено»: урок сдаётся, методист потом видит, что именно платформа
   собиралась сообщить, а тренер не гадал бы, дошла ли она до выгрузки.
3. **Одна строка на (урок, ученик, блок).** Повторный клик «Сдать» и повторная
   правка последнего вердикта не плодят отправок: те же числа — та же строка без
   нового вызова, новые числа — одна допись поверх прежнего значения.

Падение сети уроком быть не может: ошибка ловится, считается попытку и ложится в
`last_error`, а следующий триггер её повторит.
"""
import logging
import re

from django.conf import settings
from django.utils import timezone

from .lesson_grading import score_submission
from .models import LessonReport

logger = logging.getLogger(__name__)

# Событие одно и то же на все отправки: менять строку — значит рассорить уже
# написанные в GetCourse правила приёма.
EVENT_TYPE = 'lesson.homework.completed'
ENDPOINT = 'user/update-custom-fields'

# GetCourse отдаёт id ученика и строкой, и в случайных кавычках ("'48123'").
_DIGITS = re.compile(r'\d+')


def is_configured():
    """Есть ли чем слать. Нет токена или номера поля — модуль no-op."""
    return bool(settings.GETCOURSE_API_TOKEN and settings.GC_CUSTOM_FIELD_ID)


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


def field_value(numbers, assignment_id):
    """Строка, которую методист читает в доп. поле карточки ученика.

    `%g` снимает хвост `.0`: процент приходит из `score_submission` округлённый до
    десятой, а «100.0%» методист прочитал бы как технический артефакт. Если баллов
    в блоке не было вообще, знака процента после тире быть не должно: «—%» — это не
    «ноль процентов», а «процента нет».
    """
    percent = numbers['percent']
    shown = '—' if percent is None else '%g%%' % percent
    return 'Процент: %s, Решено: %s из %s (Урок #%s)' % (
        shown, numbers['correct'], numbers['total'], assignment_id)


def user_id_of(gc_uid):
    """Числовой id пользователя: `update-custom-fields` принимает только его."""
    match = _DIGITS.search(str(gc_uid or ''))
    if not match:
        raise ValueError('gc_uid %r не содержит цифр: в GetCourse его не на что опознать'
                         % gc_uid)
    return int(match.group())


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


def _post(user_id, value):
    """Один вызов к Lesson API. Возвращает (успех, что не так).

    GetCourse отвечает `200` и на отказ, поэтому код — ещё не вердикт: движок Lesson
    API кладёт отказ в конверт `{"status": false, "errors": [...]}`, и `status:false`
    при `200` — это невыполненная запись, а не успех.
    """
    base = (settings.GETCOURSE_API_URL or '').strip()
    if not base:
        return False, 'GETCOURSE_API_URL пуст: нужен https://<домен-курса>/pl/api/v1'
    url = base.rstrip('/') + '/' + ENDPOINT
    body = {'userId': user_id, 'customFields': {settings.GC_CUSTOM_FIELD_ID: value}}
    try:
        import requests
        resp = requests.post(url, json=body, timeout=15, headers={
            'Authorization': 'Bearer %s' % settings.GETCOURSE_API_TOKEN})
    except Exception as exc:
        return False, '%s: %s' % (type(exc).__name__, exc)
    if not (200 <= resp.status_code < 300):
        return False, 'HTTP %s: %s' % (resp.status_code, resp.text[:300])
    try:
        answer = resp.json()
    except ValueError:
        # HTML вместо JSON — это обычно не тот домен или не тот ключ, а не успех.
        return False, 'не-JSON ответ при HTTP %s: %s' % (resp.status_code, resp.text[:300])
    if isinstance(answer, dict) and answer.get('status') is False:
        return False, str(answer.get('errors') or answer.get('message') or answer)[:500]
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
    value = field_value(numbers, submission.assignment_id)
    key = external_key(submission)
    sent_numbers = {k: numbers[k] for k in ('percent', 'total', 'correct', 'pending_review')}
    sent_numbers['text'] = value

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
        user_id = user_id_of(submission.student.gc_uid)
    except ValueError as exc:
        ok, error = False, str(exc)
    else:
        try:
            ok, error = _post(user_id, value)
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
        logger.warning('GetCourse Lesson API: %s — %s', key, error)
    row.save()
    return row
