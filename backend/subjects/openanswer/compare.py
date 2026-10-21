"""Сверка ответа ученика с эталоном: Level 1 (числа), Level 2 (SymPy), честный pending_review.

Никакого угадывания: если часть эталона не переводится ни в число, ни в выражение,
которое решает SymPy, вся задача уходит к человеку с вердиктом pending_review.
При этом каждая часть получает свой статус (`parts`): задача без балла — не задача
без информации, и тренер обязан видеть, что уже сошлось.
"""
import re

from . import cas
from .cas import CYR_VAR
from .normalize import (ratio_members, split_items, strip_wrappers, to_value,
                        tail_after_eq, greek_to_latin)

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


def _ratio_src(part):
    return part.get('expr') or greek_to_latin(tail_after_eq(strip_wrappers(part['src']))[0])


def _ratio_equal(ev, sv):
    """Сверка цепочки отношений попарными частными: `6 : 4 : 2` — это `3 : 2 : 1`.

    Отношение — не выражение, и SymPy его не решает, поэтому цепочку разбираем на
    члены и сравниваем соседние частные. Цепочки разной длины не совпадают по
    определению: `3 : 2` против `3 : 2 : 1` — неполный ответ. Если хоть один член
    не читается CAS, вердикта нет — строка уходит человеку.

    -> True / False / None (None — ни одной цепочки в паре нет)
    """
    a, b = ratio_members(_ratio_src(ev)), ratio_members(_ratio_src(sv))
    if not a or not b:
        return None
    if len(a) != len(b):
        return False
    pairs = [None] * (len(a) - 1)
    for road in (cas.parse_by_src, cas.parse_by_latex_engine):
        ea, eb = [road(m) for m in a], [road(m) for m in b]
        if any(x is None for x in ea + eb):
            continue
        for i in range(len(ea) - 1):
            if pairs[i] is True:
                continue
            try:
                r = cas.expressions_equal(ea[i] / ea[i + 1], eb[i] / eb[i + 1])
            except TypeError:
                continue
            if r is True:
                pairs[i] = True
            elif r is False and pairs[i] is None:
                pairs[i] = False
    if False in pairs:
        return False
    return True if all(p is True for p in pairs) else None


# Имя величины слева от `=`: `v_A = 2` и `v_B = 2` — разные ответы, хотя число справа
# одно и то же. Берём первое имя: в `s = 2\pi R = 2575 км` всё после `s` — это разбор.
LHS_NAME = re.compile(r'[A-Za-zа-яё]+(?:[_{]\s*[A-Za-zа-яё0-9]+)?')


def _lhs_name(part):
    lhs = (part.get('lhs') or '').strip()
    if not lhs:
        return ''
    m = LHS_NAME.search(strip_wrappers(lhs))
    if not m:
        return ''
    name = m.group(0).replace('{', '').replace('}', '').lower()
    return ''.join(CYR_VAR.get(ch, ch) for ch in name)


def _lhs_conflict(ev, sv):
    r"""Ученик назвал другую величину — сверять нечего, и это не «совпало».

    Сокращение прощаем (`F_{н}` против `F`), совпадение с пустым именем ученика
    тоже: `2575 км` без `s =` остаётся ответом на `s = 2\pi R = 2575 км`.
    """
    a, b = _lhs_name(ev), _lhs_name(sv)
    if not a or not b or a == b:
        return False
    return not (a.startswith(b) or b.startswith(a))


# Литера варианта. В тесте сверяется буква, а не формула: тестовый ответ
# — это буква, и SymPy тут только портит вердикт. Кириллица принимается как
# гомоглиф латиницы — ученик печатает с русской раскладкой, глядя на напечатанные
# в книге латинские `A) … H)`.
OPTION_LETTERS = {}
for _opt, _chars in (('A', 'AaАа'), ('B', 'BbВвБб'), ('C', 'CcСс'), ('D', 'Dd'),
                     ('E', 'EeЕе'), ('F', 'Ff'), ('G', 'Gg'), ('H', 'HhНн')):
    for _ch in _chars:
        OPTION_LETTERS[_ch] = _opt

OPTION_HEAD = re.compile(r'^\s*[(\[{]?([A-Za-zА-Яа-яЁё])')
# Литера, напечатанная в начале строки варианта: `A) 30 сағат`, `B. 15`, `(C) 7`.
# Только начало строки: буква внутри предложения (`С. Петров`) вариантом не считается.
OPTION_LABEL = re.compile(r'(?:^|\n)[ \t]*[([]?([A-Za-zА-Яа-яЁё])[ \t]*[).\]:]')
# `вариант C`, `ответ C`, `жауабы C` — литера после служебного слова
OPTION_PREFIX = re.compile(r'^\s*(?:вариант|ответ|жауап\w*)\b[:.]?\s*', re.I)
# между литерами одного ответа: `B, G`, `G B`, `B; G)`, `B) G)`
OPTION_SPACER = re.compile(r'[\s,;./|()]+')
# литера, оторванная от текста варианта скобкой, точкой или тире: `B) 12·10^16`
OPTION_IN_TEXT = re.compile(r'(?:(?<=^)|(?<=[^\w]))([A-Za-zА-Яа-яЁё])\s*[.\-—–)\]:]')


def _letters_only(s):
    """`'B, g'` -> {'B','G'}, `'B2'` -> None: строка целиком из литер варианта."""
    out = set()
    for chunk in OPTION_SPACER.split(s):
        if not chunk:
            continue
        for ch in chunk:
            letter = OPTION_LETTERS.get(ch)
            if letter is None:
                return None
            out.add(letter)
    return out or None


def option_letters(raw, allow_text=False):
    """-> frozenset канонических литер `A`..`H` либо None.

    Одна литера — это множество из одного элемента, поэтому одиночный ответ и
    блок с несколькими правильными вариантами читаются одним разбором.
    `allow_text=True` разрешает строку, где к литере приложен сам текст варианта
    (`B) 12·10^16; G) 2 жыл`): для ответа ученика это норма, для эталона — нет.
    """
    s = OPTION_PREFIX.sub('', strip_wrappers(raw or '')).strip()
    if not s:
        return None
    got = _letters_only(s)
    if got is not None:
        return frozenset(got)
    if not allow_text:
        return None
    heads = [OPTION_LETTERS[m.group(1)] for m in OPTION_IN_TEXT.finditer(s)
             if m.group(1) in OPTION_LETTERS]
    return frozenset(heads) if heads else None


def option_labels(text):
    """-> ['A', 'B', ...]: литеры вариантов, напечатанные в условии списками.

    Нужен экрану ученика: с телефона буква варианта — это нажатие пальцем, а не
    поиск `A` в клавиатуре. Ряд берётся только непрерывный от `A`, потому что тесты
    печатают ровно так (`A..E`, `A..H`). Дырка в ряду или отсутствие `A` означают,
    что найденные буквы — не список вариантов, и чипов не будет: экран не имеет
    права предлагать выбирать то, чего в задаче нет.
    """
    found = []
    for match in OPTION_LABEL.finditer(text or ''):
        letter = OPTION_LETTERS.get(match.group(1))
        if letter and letter not in found:
            found.append(letter)
    run = []
    for letter in found:
        if letter != chr(ord('A') + len(run)):
            # дырка в ряду: одна литера съедена сканом или это вовсе не список.
            # Половину чипов показать — значит намекнуть ученику, что вариантов меньше,
            # чем напечатано в задаче.
            return []
        run.append(letter)
    return run if len(run) >= 2 else []


def option_letter(raw, strict=False):
    """-> 'A'..'H' либо None: одна литера варианта, вычитанная из строки целиком.

    Строка обязана начинаться с буквы варианта, оторванной от остального текстом или
    пунктуацией: `Сутек` — это слово, а не вариант `C`. `strict=True` требует, чтобы
    после литеры не осталось ничего, кроме знаков препинания: эталон открытого ответа
    `$E \\approx 400$ В` — это формула, и сверять её буквой нельзя.
    """
    s = OPTION_PREFIX.sub('', strip_wrappers(raw or ''))
    m = OPTION_HEAD.match(s)
    if not m:
        return None
    letter = OPTION_LETTERS.get(m.group(1))
    if letter is None:
        return None
    rest = s[m.end():]
    if strict:
        return None if rest.strip(' \t.,:;)(][—–-') else letter
    rest = rest.lstrip(' \t')
    if rest and rest[0].isalpha():
        return None
    return letter


def _compare_option(etalon_letters, student_raw):
    """Вердикт по набору литер: совпал целиком — `correct`, другой набор — `incorrect`.

    Третьего здесь нарочно нет: `pending_review` на прочитанные литеры означал бы,
    что учитель сам разбирает строку, в которой буквы уже стоят. Не прочитана —
    вот тогда да, человеку. Частичного совпадения тоже нет: в блоке с несколькими
    верными вариантами лишняя или пропущенная литера — это неверный ответ.
    """
    got = option_letters(student_raw, allow_text=True)
    if got is None:
        return {'verdict': 'pending_review', 'judged_by': None, 'matched': 0, 'total': 1,
                'parts': [{'part': 'Вариант', 'status': 'undecided'}],
                'why': 'литера варианта не прочитана из ответа'}
    ok = got == etalon_letters
    # ни своих, ни эталонных литер в `why` нет: эта строка уходит ученику в `feedback`,
    # а ключ теста он обязан увидеть только после вердикта человека
    return {'verdict': 'correct' if ok else 'incorrect', 'judged_by': 'level1',
            'matched': 1 if ok else 0, 'total': 1,
            'parts': [{'part': 'Вариант', 'status': 'matched' if ok else 'mismatched'}],
            'why': 'литеры варианта совпали' if ok else 'литеры варианта не те'}


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


def compare(etalon_raw, student_raw, strict_units=False, question_type=''):
    """-> {'verdict', 'judged_by', 'matched', 'total', 'parts', 'why'}.

    `question_type='single_choice'` ведёт проверку по литере варианта: тестовый ответ
    — это буква, и числа из вариантов в формулу превращать нельзя.
    """
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

    etalon_letters = option_letters(etalon_raw, allow_text=True) if len(etalon) == 1 else None
    if etalon_letters is not None:
        # Для теста литера (или набор литер) — единственный возможный ответ. В открытом
        # ответе литера эталона сама по себе ничего не гарантирует: сверяем буквой только
        # если эталон и есть одна буква, а ученик тоже написал букву; иначе остаётся
        # обычная дорога чисел и формул.
        if question_type == 'single_choice':
            return _compare_option(etalon_letters, student_raw)
        if len(etalon_letters) == 1 and option_letter(etalon_raw, strict=True) \
                and option_letter(student_raw):
            return _compare_option(etalon_letters, student_raw)

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
            if _lhs_conflict(ev, sv):
                # ученик ответил про другую величину — эта пара не сверяется,
                # но и «проверьте глазами» она быть не может: имена прочитаны
                examined = True
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
                ratio = _ratio_equal(ev, sv)
                if ratio is True:
                    hit = i
                    cas_used = True
                    break
                if ratio is not None:
                    # обе стороны прочитаны как цепочки отношений и не сошлись —
                    # это честный ноль, а не «пусть посмотрит человек»
                    continue
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


def score_open_answer(etalon_raw, student_raw, strict_units=False, question_type=''):
    """Единственная точка входа автопроверки для бэкенда.

    `verdict=None` означает «не проверено машиной» — строка уходит преподавателю, и
    ни один балл за неё не начисляется и не снимается. `model_suggestion` из `compare`
    здесь гасится: он помечает, что подсказку стоило бы спросить, но сама модель
    этому уроку не вызывалась, и писать в базу её имя было бы ложью.
    """
    res = compare(etalon_raw, student_raw, strict_units=strict_units,
                  question_type=question_type)
    if res['judged_by'] not in DECIDED:
        res['judged_by'] = None
    return res
