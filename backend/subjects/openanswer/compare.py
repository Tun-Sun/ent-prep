"""Сверка ответа ученика с эталоном: Level 1 (числа), Level 2 (SymPy), честный pending_review.

Никакого угадывания: если часть эталона не переводится ни в число, ни в выражение,
которое решает SymPy, вся задача уходит к человеку с вердиктом pending_review.
При этом каждая часть получает свой статус (`parts`): задача без балла — не задача
без информации, и тренер обязан видеть, что уже сошлось.
"""
import re

from . import cas
from .normalize import split_items, strip_wrappers, to_value, tail_after_eq, greek_to_latin

# Политика округления, утверждённая тренером 14.10: 0,5 % от значения.
# Абсолютный пол отсутствует нарочно — иначе он проглотил бы атомные ответы
# вида 1,1·10⁻¹⁰.
TOL_REL = 0.005


def _close(a, b):
    """Толерантность относительная: абсолютный пол проглатывает атомные ответы."""
    tol = TOL_REL * max(abs(a), abs(b))
    if tol == 0:
        return a == b
    return abs(a - b) <= tol


def _values_comparable(ev, sv, strict_units=False):
    """-> True / False / None (не решил).

    strict_units=True требует, чтобы единица была названа с обеих сторон:
    «2575» против «2575 км» тогда не зачитывается, а уходит человеку.
    Без единиц сверяем и с сырым числом, и с СИ-значением другой стороны:
    «58%» и «0,58» — один ответ, записанный по-разному.
    """
    if ev['unit_kind'] == 'known' and sv['unit_kind'] == 'known':
        if ev['dim'] != sv['dim']:
            return False
        return _close(ev['si'], sv['si'])
    if ev['unit_kind'] == 'none' and sv['unit_kind'] == 'none':
        return _close(ev['num'], sv['num'])
    if ev['unit_kind'] == 'unknown' or sv['unit_kind'] == 'unknown':
        if ev['unit_raw'].strip().lower() == sv['unit_raw'].strip().lower():
            return _close(ev['num'], sv['num'])
        return None
    if strict_units:
        return None
    bare = ev if ev['unit_kind'] == 'none' else sv
    unitised = sv if bare is ev else ev
    return _close(bare['num'], unitised['num']) or (
        unitised['si'] is not None and _close(bare['num'], unitised['si']))


def _expr_equal(ev, sv):
    a_src = ev.get('expr') or greek_to_latin(tail_after_eq(strip_wrappers(ev['src']))[0])
    b_src = sv.get('expr') or greek_to_latin(tail_after_eq(strip_wrappers(sv['src']))[0])
    pairs = [(cas.parse_by_src(a_src), cas.parse_by_src(b_src)),
             (cas.parse_by_latex_engine(a_src), cas.parse_by_latex_engine(b_src))]
    decided = False
    for a, b in pairs:
        r = cas.expressions_equal(a, b)
        if r is True:
            return True, 'cas'
        if r is False:
            decided = True
    return (False, 'cas') if decided else (None, None)


def _alt_pair(ev, sv, strict_units=False):
    """Запасной путь для `формула ~ число`: сверяем то, что под `~`, если сама формула не решилась."""
    a, b = ev.get('alt'), sv.get('alt')
    if a is None and b is None:
        return None
    a, b = a or ev, b or sv
    if a['kind'] == 'text' or b['kind'] == 'text':
        return None
    if a['kind'] == 'number' and b['kind'] == 'number':
        return _values_comparable(a, b, strict_units)
    eq, _ = _expr_equal(a, b)
    return eq


def compare(etalon_raw, student_raw, strict_units=False):
    """-> {'verdict', 'judged_by', 'matched', 'total', 'parts', 'why'}."""
    student = [to_value(it['text']) for it in split_items(student_raw or '')]
    etalon_items = split_items(etalon_raw or '')
    # часть держит и метку из ответа (`а)`, `1)`), и свой номер: подсказка тренеру
    # обязана называть именно ту часть, которую он читает в строке ученика
    etalon = [dict(to_value(it['text']), label=it['label'], n=i + 1)
              for i, it in enumerate(etalon_items)]
    if not student:
        return {'verdict': 'incorrect', 'judged_by': 'level1', 'matched': 0,
                'total': len(etalon), 'parts': [], 'why': 'пустой ответ'}
    if not etalon:
        return {'verdict': 'pending_review', 'judged_by': None, 'matched': 0,
                'matched_total': 0, 'total': 0, 'parts': [],
                'why': 'эталон не разобран'}

    text_items = [e for e in etalon if e['kind'] == 'text'] + \
                 [s for s in student if s['kind'] == 'text']
    used = [False] * len(student)
    matched = 0
    cas_used = False
    undecided = 0
    parts = []
    for ev in etalon:
        name = ev['label'] or ('Часть %d' % ev['n'])
        if ev['kind'] == 'text':
            undecided += 1
            parts.append({'part': name, 'status': 'text'})
            continue
        hit = None
        unresolved = False
        examined = False
        for i, sv in enumerate(student):
            if used[i] or sv['kind'] == 'text':
                continue
            if ev['kind'] == 'number' and sv['kind'] == 'number':
                r = _values_comparable(ev, sv, strict_units)
                if r is not None:
                    examined = True
                if r is True:
                    hit = i
                    break
                if r is None:
                    unresolved = True
            elif ev['kind'] == 'expr' or sv['kind'] == 'expr':
                examined = True
                eq, how = _expr_equal(ev, sv)
                if eq is not True:
                    alt = _alt_pair(ev, sv, strict_units)
                    if alt is True:
                        hit = i
                        break
                    if alt is None and eq is None:
                        unresolved = True
                    continue
                hit = i
                cas_used = how == 'cas'
                break
        if hit is not None:
            used[hit] = True
            matched += 1
            parts.append({'part': name, 'status': 'matched'})
        elif unresolved:
            undecided += 1
            parts.append({'part': name, 'status': 'undecided'})
        elif not examined and any(s['kind'] == 'text' for s in student):
            # ученик ответил словами там, где эталон — число или формула: сравнивать
            # машине было не с чем, и «не совпало» стало бы ложным нулём. Если же
            # неподходящее число в строке есть, оно уже отработано выше как `mismatched`.
            undecided += 1
            parts.append({'part': name, 'status': 'student_text'})
        else:
            parts.append({'part': name, 'status': 'mismatched'})

    total = len(etalon)
    if undecided:
        return {'verdict': 'pending_review',
                'judged_by': 'model_suggestion' if text_items else None,
                'matched': matched, 'total': total, 'parts': parts,
                'why': 'не решается автоматически: %d из %d частей' % (undecided, total)}
    judged = 'cas' if cas_used else 'level1'
    if matched == total:
        return {'verdict': 'correct', 'judged_by': judged, 'matched': matched,
                'total': total, 'parts': parts, 'why': 'все части совпали'}
    if matched == 0:
        return {'verdict': 'incorrect', 'judged_by': judged, 'matched': 0,
                'total': total, 'parts': parts, 'why': 'ни одна часть не совпала'}
    return {'verdict': 'partial', 'judged_by': judged, 'matched': matched,
            'total': total, 'parts': parts, 'why': 'совпало %d из %d' % (matched, total)}


# Чем выставлен вердикт: пустое значение — «машина не решила», и это не чья-то подсказка.
DECIDED = ('level1', 'cas')

# Что тренер читает про каждую часть многочастного ответа, когда машина встала.
PART_STATUS_RU = {
    'matched': 'совпало',
    'mismatched': 'не совпало',
    'undecided': 'машина не решила',
    'text': 'текст — проверьте глазами',
    'student_text': 'словом вместо числа — проверьте глазами',
}


def parts_hint(parts):
    """`а) совпало, б) текст — проверьте глазами` — одна строка по всем частям.

    Нужна ровно в `pending_review`: балла машина не начислила, но тренер не обязан
    заново сверять то, что уже сошлось, — он смотрит только спорные части.
    """
    return ', '.join('%s: %s' % (p['part'], PART_STATUS_RU.get(p['status'], p['status']))
                     for p in parts)


def score_open_answer(etalon_raw, student_raw, strict_units=False):
    """Единственная точка входа автопроверки для бэкенда.

    `verdict=None` означает «не проверено машиной» — строка уходит преподавателю, и
    ни один балл за неё не начисляется и не снимается. `model_suggestion` из `compare`
    здесь гасится: он помечает, что подсказку стоило бы спросить, но сама модель
    этому уроку не вызывалась, и писать в базу её имя было бы ложью.
    """
    res = compare(etalon_raw, student_raw, strict_units=strict_units)
    if res['judged_by'] not in DECIDED:
        res['judged_by'] = None
    return res
