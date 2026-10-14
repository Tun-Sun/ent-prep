"""Level 1: очистка строки ответа, разбор на части и числовое значение.

Слой numeric-only: то, что удаётся перевести в число с единицей, сюда и попадает.
Формулу с буквами слой не пытается выдать за число (kind='expr' — мяч Level 2),
а словесный хвост остаётся kind='text' — это работа для ручного вердикта.
"""
import math
import re

from .units import parse_unit

B = chr(92)
MINUS = '\u2212\u2013-'
GREEK = {
    'alpha': 'a', 'beta': 'b', 'gamma': 'g', 'delta': 'D', 'varepsilon': 'e',
    'epsilon': 'e', 'zeta': 'z', 'eta': 'n', 'theta': 'th', 'iota': 'i',
    'kappa': 'k', 'lambda': 'l', 'mu': 'M', 'nu': 'N', 'xi': 'x', 'pi': 'pi',
    'rho': 'r', 'sigma': 's', 'tau': 't', 'phi': 'f', 'varphi': 'f', 'chi': 'c',
    'psi': 'ps', 'omega': 'w', 'Delta': 'D', 'Omega': 'W', 'Phi': 'F', 'Gamma': 'G',
    'Theta': 'Th', 'Lambda': 'L', 'Pi': 'P', 'mu_0': 'mu0',
}


def strip_wrappers(s):
    s = s.replace('<br>', ';').replace('<br/>', ';').replace('<br />', ';')
    s = re.sub(r'\{,\}', ',', s)
    s = re.sub(r'\\left|\\right|\\bigl|\\bigr|\\Bigl|\\Bigr', ' ', s)
    s = re.sub(r'\\[,;! ]|\\quad|\\qquad|\\thinspace|\\displaystyle', ' ', s)
    s = re.sub(r'\\operatorname\{([^{}]*)\}', r'\1', s)
    s = re.sub(r'\\mathrm\{([^{}]*)\}', r'\1', s)
    s = re.sub(r'\\text\{([^{}]*)\}', r' \1 ', s)
    s = re.sub(r'\\mbox\{([^{}]*)\}', r' \1 ', s)
    s = s.replace('$', ' ').replace('\\\\', ' ')
    s = s.replace(B + '{}', '')
    s = s.replace(B + '%', '%').replace(B + 'circ', '°')
    s = s.replace(B + 'cdot', '*').replace(B + 'times', '*').replace(B + 'div', '/')
    s = s.replace(B + 'approx', '~').replace(B + 'simeq', '~').replace(B + 'neq', '!=')
    s = s.replace(B + 'leq', '<=').replace(B + 'geq', '>=').replace(B + 'le', '<=')
    s = s.replace(B + 'lt', '<').replace(B + 'gt', '>')
    s = s.replace(B + 'in', ' in ').replace(B + 'pi', ' pi ')
    s = s.replace(B + 'degree', '°')
    s = re.sub(r'\^\{([^{}]+)\}', r'^\1', s)
    s = re.sub(r'_\{([^{}]+)\}', r'_\1', s)
    s = re.sub(r'\{(\w)\}', r'\1', s)
    s = s.replace('^°', '°')
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def greek_to_latin(s):
    """Только известные греческие имена; \\frac и \\sqrt трогать нельзя — их ест CAS."""
    def rep(m):
        name = m.group(1)
        return GREEK.get(name, m.group(0))
    return re.sub(r'\\([A-Za-z]+)', rep, s)


# Метка части ответа: `а) `, `1. ` — но не `0.` из десятичной дроби, поэтому после точки нужен пробел.
PART_LABEL = re.compile(r'^\s*\(?(?:[а-яёА-ЯЁ]{1,2}|\d{1,2})[)\.](?=\s)')


def split_items(s):
    """Строка ответа -> список независимых частей (а), б), 1), значения через ; и ,)."""
    s = strip_wrappers(s)
    s = re.sub(r'(?<=\.)\s+(?=\d{1,2}[)]\s)', '; ', s)
    chunks = [c for c in re.split(r';|\n', s) if c.strip()]
    items = []
    for c in chunks:
        for piece in _split_by_comma_assignments(c.strip()):
            label = ''
            m = PART_LABEL.match(piece)
            if m and '=' not in m.group(0):
                label = m.group(0).strip()
                piece = piece[m.end():]
            piece = piece.strip(' ,.')
            if piece:
                items.append({'label': label, 'text': piece})
    return items


def _split_by_comma_assignments(c):
    """`v_A = 0, v_B = 2wR, v_C = 2wR` -> 3 части; `2,5 рад` и `если ... , то` -> 1."""
    if '=' not in c:
        return [c]
    pieces = [p.strip() for p in re.split(r',(?=\s|$)(?![^(]*\))', c) if p.strip()]
    merged = []
    for p in pieces:
        if merged and '=' not in p:
            merged[-1] = merged[-1] + ', ' + p
        else:
            merged.append(p)
    return merged


def tail_after_eq(text):
    """Цепочка `s = 2*pi*R = 2575 км` -> значение после последнего `=`."""
    if '=' not in text:
        return text, ''
    segs = [s.strip() for s in text.split('=')]
    return segs[-1], '='.join(segs[:-1])


# Тысячи через запятую признаём только при двух группах по три цифры: `1,234,567`.
# Одиночная `1,234` в этом корпусе — десятичная запятая, а не тысячи.
_NUM = r'([-−–]?\s*(?:\d{1,3}(?:,\d{3}){2,}(?:\.\d+)?|\d+\.\d+|\d+,\d+|\d+))'


def parse_number(text):
    """-> (value, rest, approx) либо None. Тянет обычное число, смешанное, периодическое, научное."""
    t = text.strip()
    t = re.sub(r'(\d)\{,\}(\d)', r'\1,\2', t)
    t = re.sub(r'(\d)[ \u00a0](\d{3})(?![\d])', r'\1\2', t)
    approx = False
    m = re.match(r'^~\s*', t)
    if m:
        approx = True
        t = t[m.end():]
    t = re.sub(r'^\s*=\s*', '', t)

    mm = re.match(r'^([-−–]?)\s*(\d+)\s*\(?\s*(\d+)\s*\)?\s*/\s*(\d+)\s*\)?(?![\d/])', t)
    if mm:
        sign = -1.0 if mm.group(1) else 1.0
        whole, num, den = int(mm.group(2)), int(mm.group(3)), int(mm.group(4))
        val = sign * (whole + num / den)
        return _finish(val, t[mm.end():], approx)

    mm = re.match(r'^([-−–]?)\s*(\d+)\s*\\frac\s*\{?\s*(\d+)\s*\}?\s*\{?\s*(\d+)\s*\}?(?![\d])', t)
    if mm:
        sign = -1.0 if mm.group(1) else 1.0
        whole, num, den = int(mm.group(2)), int(mm.group(3)), int(mm.group(4))
        return _finish(sign * (whole + num / den), t[mm.end():], approx)

    mm = re.match(_NUM + r'(?:\((\d{1,6})\))?', t)
    if not mm:
        return None
    core = mm.group(1)
    period = mm.group(2)
    sign = -1.0 if core and core[0] in MINUS else 1.0
    digits = re.sub(r'[-−–\s]', '', core)
    digits = digits.replace(',', '.')
    try:
        val = sign * float(digits)
    except ValueError:
        return None
    if period:
        nonrep, _, frac = digits.partition('.')
        shift = 10 ** len(frac) if frac else 1
        val = sign * (abs(val) + int(period) / (shift * (10 ** len(period) - 1)))
    rest = t[mm.end():]
    # Научная запись двумя дорогами: `2,5·10^-3` как печатает книга и `2.5e-3` как
    # печатает ученик. `e` без цифры сразу за знаком — это не экспонента, а буква
    # (например напряжённость `E`), и она остаётся на стороне единиц.
    sci = re.match(r'^\s*(?:[eE]\s*([-−–+]?\s*\d{1,3})'
                   r'|[*x·]\s*10\s*(?:\^\s*)?\{?\(?\s*([-−–]?\d+)\s*\)?\}?)', rest)
    if sci:
        exp = re.sub(r'\s|[−–]', '-', sci.group(1) or sci.group(2))
        val = val * 10 ** int(exp.lstrip('+'))
        rest = rest[sci.end():]
    # `24\pi см³` — множитель пи, а не единица: иначе Level 1 теряет π, а SymPy съедает степень см.
    m_pi = re.match(r'^\s*(?:pi|π)(?![A-Za-z])', rest)
    if m_pi:
        val = val * math.pi
        rest = rest[m_pi.end():]
    return _finish(val, rest, approx)


def _finish(val, rest, approx):
    rest = re.sub(r'^\s*[*/]\s*', ' ', rest)
    return (val, rest.strip(), approx)


_EXP = r'\s*\^?\s*[-−–]?\s*[\d²³]?'
UNIT_STOP = re.compile(r'^(?:' + '|'.join([
    r'(?:м/с|см/с|км/с|км/ч|об/мин|об/с)' + _EXP,
    r'мм рт\. ст\.', r'моль/\(л·с\)', r'дж/\(моль·к\)', r'н·м2/кл',
    r'%|процент[а-яё]*',
    r'[a-zа-яёА-ЯЁ°]+' + _EXP + r'(?:/[a-zа-яёА-ЯЁ°]+' + _EXP + r')?(?:·[a-zа-яёА-ЯЁ°]+)?',
]) + r')')


def split_unit_and_prose(rest):
    """`км` / `м/с правее заряда q2` / `, вправо` -> (единица, пояснение)."""
    rest = rest.strip().strip(',')
    if not rest:
        return '', ''
    m = UNIT_STOP.match(rest)
    if m:
        unit = m.group(0).strip()
        prose = rest[m.end():].strip(' ,.')
        return unit, prose
    return '', rest.strip(' ,.')


def _mathy_leftover(unit_raw, prose):
    """Хвост после числа — не единица и не слова, а математика: `\\sqrt{3}`, `*1,73`, `/(2)`, `: 2`."""
    if not prose:
        return False
    if re.search(r'[а-яё]{3,}', prose):
        return False
    return bool(re.match(r'^\s*[*·/^(:\\]', prose) or '\\' in prose or '^' in prose)


# Неизвестная «единица» из одних латинских букв (`a^3`, `k`, `dp`) — это переменная, а не размерность.
ALGEBRA_TOKEN = re.compile(r'^[A-Za-z][A-Za-z_0-9]*$')


def to_value(item_text):
    """Часть ответа -> {'kind', 'num', 'unit', 'si', 'approx', 'prose', 'expr_src'}.

    `A ~ B` (формула и её приближение) разбираем двумя кусками: основной становится
    значение до `~`, а alt — числом после него. Ученик вправе написать либо формулу,
    либо округление.
    """
    tail, lhs = tail_after_eq(item_text)
    head, sep, rest = tail.partition('~')
    if sep and head.strip() and rest.strip():
        v = _value_from(head, lhs)
        v['approx'] = True
        v['alt'] = _value_from(rest, '')
        return v
    return _value_from(tail, lhs)


TRAIL_UNIT = re.compile(r'\s+((?:[a-zа-яёА-ЯЁ°]+' + _EXP +
                        r'(?:/[a-zа-яёА-ЯЁ°]+' + _EXP + r')?))\s*$')


def _value_from(tail, lhs):
    tail_src = tail
    tail = re.sub(r'\s+', ' ', tail).strip(' ,.')
    approx = '~' in tail
    tail = tail.replace('~', ' ').strip()
    parsed = parse_number(tail)
    if parsed:
        val, rest, a2 = parsed
        unit_raw, prose = split_unit_and_prose(rest)
        kind, dim, factor = parse_unit(unit_raw)
        if not _mathy_leftover(unit_raw, prose) and \
                not (kind == 'unknown' and ALGEBRA_TOKEN.match(unit_raw or '')):
            si = val * factor if kind == 'known' else None
            return {'kind': 'number', 'num': val, 'unit_raw': unit_raw, 'unit_kind': kind,
                    'dim': dim, 'si': si, 'approx': approx or a2, 'prose': prose,
                    'src': tail_src, 'lhs': lhs}
    if (parsed or re.search(r'[a-zA-Zа-яёА-ЯЁ]', tail)) and \
            not re.search(r'[а-яё]{3,}', tail.replace('pi', '')):
        unit_raw, dim, unit_kind = '', '', 'none'
        m_unit = re.search(r'\s+([a-zа-яёА-ЯЁ°]+\s*\^?[-−–]?[\d²³]?'
                           r'(?:/[a-zа-яёА-ЯЁ°]+\s*\^?[-−–]?[\d²³]?)?)\s*$', tail)
        if m_unit:
            k, d, _factor = parse_unit(m_unit.group(1))
            if k == 'known':
                # `\frac{9\sqrt2}8 см^3`: единица приклеена к формуле, SymPy её не переваривает.
                unit_raw, dim, unit_kind = m_unit.group(1).strip(), d, k
                tail = tail[:m_unit.start()].strip()
        return {'kind': 'expr', 'num': None, 'unit_raw': unit_raw, 'unit_kind': unit_kind,
                'dim': dim, 'si': None, 'approx': approx, 'prose': '',
                'src': tail_src, 'expr': tail, 'lhs': lhs}
    return {'kind': 'text', 'num': None, 'unit_raw': '', 'unit_kind': 'none', 'dim': '',
            'si': None, 'approx': approx, 'prose': tail_src, 'src': tail_src, 'lhs': lhs}


def normalize_answer(raw):
    """Строка (эталон или ответ ученика) -> список разобранных частей."""
    return [to_value(it['text']) for it in split_items(raw)]
