"""Начисление по уроку: сверка одного ответа и процент блока — в одном месте.

Правило, из которого растёт весь этот файл: у машины два права — подтвердить и
отвергнуть. Третье состояние («не проверено») она обязана вернуть как
`pending_review` без балла, а не превратить в ноль: ложный ноль ученик не
отличит от неверного ответа, а тренер потом не найдёт, где проверка не делалась.
Процент поэтому считается по проверенным задачам, а сколько осталось висеть —
отдельное число, которое матрица обязана показать.
"""
from django.conf import settings
from django.utils import timezone

from .openanswer import score_open_answer
from .openanswer.normalize import normalize_answer


def _normalized_repr(raw):
    """Что нормализатор вычленил из строки ученика — для карточки у тренера."""
    out = []
    for part in normalize_answer(raw or ''):
        if part['kind'] == 'number':
            out.append(('%g' % part['num']) + (' ' + part['unit_raw'] if part['unit_raw'] else ''))
        elif part['kind'] == 'expr':
            out.append(part.get('expr') or part['src'])
        else:
            out.append(part['src'])
    return '; '.join(out)


def grade_assignment_answer(answer):
    """Сверить `raw_answer` с эталоном книги и записать вердикт.

    Эталон — только `Question.latex_answer` (то, что напечатано и принято приёмкой).
    Задача без напечатанного ответа сверки не имеет: она уходит преподавателю
    с пустым `judged_by`, и ни одного балла машина ей не начисляет.
    """
    etalon = (answer.question.latex_answer or '').strip()
    answer.normalized_answer = _normalized_repr(answer.raw_answer)
    if not etalon:
        answer.verdict = 'pending_review'
        answer.judged_by = ''
        answer.verdict_note = 'в книге ответа нет — проверяет преподаватель'
        answer.save(update_fields=['normalized_answer', 'verdict', 'judged_by',
                                   'verdict_note', 'updated_at'])
        return answer
    res = score_open_answer(etalon, answer.raw_answer,
                            strict_units=settings.OPEN_ANSWER_STRICT_UNITS)
    answer.verdict = res['verdict']
    answer.judged_by = res['judged_by'] or ''
    answer.verdict_note = res['why']
    answer.save(update_fields=['normalized_answer', 'verdict', 'judged_by',
                               'verdict_note', 'updated_at'])
    return answer


def score_submission(submission):
    """Итог сдачи: сколько решено, сколько проверено, сколько висит и какой процент.

    `pending_review` не входит ни в числитель, ни в знаменатель — до ручной проверки
    процент показывается по тому, что машина действительно решила, а `total` и
    `pending` рядом говорят тренеру, насколько этот процент пока узкий.
    """
    answers = list(submission.answers.select_related('question'))
    total = len(submission.block.question_ids or []) if submission.block else len(answers)
    checked = [a for a in answers if a.verdict != 'pending_review']
    pending = len(answers) - len(checked)
    earned = sum(a.points_earned or 0.0 for a in checked)
    possible = sum(a.question.points for a in checked)
    return {
        'total': total,
        'answered': len(answers),
        'checked': len(checked),
        'pending': pending,
        'earned': round(earned, 4),
        'possible': round(possible, 4),
        'percent': round(earned / possible * 100, 1) if possible else None,
    }


def close_submission(submission, reviewer=None):
    """Сдача становится `reviewed`, только когда непроверенных ответов не осталось.

    Молча ставить `reviewed` после последней правки тренера нельзя: если в блоке
    осталась задача без эталона, очередь должна продолжать её показывать.
    """
    left = submission.answers.filter(verdict='pending_review').count()
    if left or submission.state == 'in_progress':
        submission.save(update_fields=['state'])
        return left
    submission.state = 'reviewed'
    submission.reviewed_at = timezone.now()
    submission.reviewed_by = reviewer
    submission.save(update_fields=['state', 'reviewed_at', 'reviewed_by'])
    return left
