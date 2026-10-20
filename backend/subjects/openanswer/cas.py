"""Level 2: SymPy. Две независимые дороги в выражение и сверка эквивалентности.

1) parse_latex по исходному LaTeX (родительский парсер SymPy);
2) sympify по нашему упрощённому виду (тот же текст, но после Level 1).
Если обе дороги не сошлись — это pending_review, а не угадывание.
"""
import re

from sympy import (N, Rational, Symbol, acos, acot, asin, atan, cos, cot, exp, log, pi,
                   prime, simplify, sin, sinh, sqrt, sympify, tan, tanh, cosh)
from sympy.parsing.latex import parse_latex

from .normalize import GREEK

B = chr(92)
CYR_VAR = {'а': 'a', 'в': 'v', 'з': 'z', 'к': 'k', 'м': 'm', 'н': 'n', 'р': 'r',
           'с': 's', 'т': 't', 'у': 'u', 'х': 'x', 'п': 'p', 'л': 'l', 'ф': 'f',
           'д': 'd', 'б': 'b', 'г': 'g', 'е': 'e', 'о': 'o', 'ж': 'j', 'э': 'e',
           'я': 'ya', 'ю': 'yu', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ц': 'ts',
           'ы': 'y', 'и': 'i'}


def _braced(s, i):
    depth = 0
    for j in range(i, len(s)):
        depth += s[j] == '{'
        depth -= s[j] == '}'
        if depth == 0:
            return s[i + 1:j], j + 1
    return s[i + 1:], len(s)


def _arg(s, i):
    """Аргумент команды: {…}, \\команда или один символ (Level 1 уже снял часть фигурных скобок)."""
    while i < len(s) and s[i] == ' ':
        i += 1
    if i >= len(s):
        return '', i
    if s[i] == '{':
        return _braced(s, i)
    m = re.match(r'\\[A-Za-z]+', s[i:])
    if m:
        return m.group(0), i + m.end()
    return s[i], i + 1


def expand_frac(s):
    out = []
    i = 0
    while i < len(s):
        if s.startswith(B + 'frac', i):
            j = i + len(B + 'frac')
            num, j2 = _arg(s, j)
            den, j3 = _arg(s, j2)
            if den:
                out.append('((' + expand_frac(num) + ')/(' + expand_frac(den) + '))')
                i = j3
                continue
            out.append(B)
            i += len(B + 'frac')
            continue
        out.append(s[i])
        i += 1
    return ''.join(out)


def expand_sqrt(s):
    s = re.sub(r'\\sqrt\[([^\]]*)\]\{([^{}]*)\}', r'(\2)**(1/(\1))', s)
    s = re.sub(r'\\sqrt\[([^\]]*)\]\s*(\{[^{}]*\}|[\w.]+)', r'(\2)**(1/(\1))', s)
    s = re.sub(r'\\sqrt\{([^{}]*)\}', r'sqrt(\1)', s)
    s = re.sub(r'\\sqrt\s*(\w)', r'sqrt(\1)', s)
    return s


def _cyr_ok(s):
    """Однобуквенные кириллические переменные переводим, слова — нет: вернём None."""
    return not re.search(r'[а-яёА-ЯЁ]{2,}', s)


# Имена функций/констант: правило «буква буква -> умножение» не должно их рвать.
FUNCS = ['arcsin', 'arccos', 'arctan', 'arctg', 'sinh', 'cosh', 'tanh', 'asin', 'acos',
         'atan', 'sqrt', 'log', 'ln', 'lg', 'exp', 'sin', 'cos', 'tan', 'cot', 'abs', 'pi']
LOCALS = {'sqrt': sqrt, 'pi': pi, 'ln': log, 'lg': lambda x: log(x, 10), 'log': log,
          'exp': exp, 'sin': sin, 'cos': cos, 'tan': tan, 'cot': cot,
          'asin': asin, 'acos': acos, 'atan': atan, 'acot': acot, 'abs': abs,
          'sinh': sinh, 'cosh': cosh, 'tanh': tanh,
          'arcsin': asin, 'arccos': acos, 'arctan': atan, 'arctg': atan}


def _mask_funcs(s):
    """Имя функции/константы прячем служебными символами: правила умножения калечат буквы внутри."""
    tokens = {}
    for name in FUNCS:
        pat = re.compile(r'(?<![A-Za-z])' + name + r'(?![A-Za-z])')
        if not pat.search(s):
            continue
        tok = '\x01' + chr(ord('A') + len(tokens)) + '\x02'
        tokens[tok] = name
        s = pat.sub(tok, s)
    return s, tokens


def _unmask_funcs(s, tokens):
    for tok, name in tokens.items():
        s = s.replace(tok, name)
    return s


def decimal_comma_to_point(s):
    """`6,9` -> `6.9`: для SymPy запятая — разделитель аргументов, а не десятичный знак."""
    return re.sub(r'(?<=\d)\s*,\s*(?=\d)', '.', s)


_MIXED = re.compile(r'(?:([-−–])\s*)?(\d+)\s*\\frac\s*\{?\s*(\d+)\s*\}?\s*\{?\s*(\d+)\s*\}?')


def expand_mixed(s):
    """`-42\frac{2}{3}` — смешанное число, а не произведение: сводим к неправильной дроби."""
    def rep(m):
        sign = '-' if m.group(1) else ''
        whole, num, den = (int(m.group(i)) for i in (2, 3, 4))
        return '(%s(%d*%d+%d)/%d)' % (sign, whole, den, num, den)
    return _MIXED.sub(rep, s)


def to_python_src(s):
    s = decimal_comma_to_point(s)
    # Отношение из двух членов (`9 : 16`) — это частное; цепочку `3 : 2 : 1` частным не делаем.
    if s.count(':') == 1:
        s = re.sub(r'\s*:\s*', '/', s)
    s = expand_mixed(s)
    s = expand_frac(s)
    s = expand_sqrt(s)
    s = s.replace(B + 'circ', '*(pi/180)').replace('°', '*(pi/180)')
    s = re.sub(r'\^\\(\w+)', r'**(\1)', s)
    s = re.sub(r'\^\(([^()]*)\)', r'**(\1)', s)
    s = re.sub(r'\^(\w)', r'**\1', s)
    # Две команды слитно (`\pi\sqrt{3}`) после подстановки имён склеиваются в `pisqrt`,
    # и ни `pi`, ни `sqrt` парсер уже не узнаёт: между ними нужен разделитель.
    s = re.sub(r'(\\[A-Za-z]+)(?=\\)', r'\1 ', s)
    s = re.sub(r'\\([A-Za-z]+)', lambda m: GREEK.get(m.group(1), m.group(1)), s)
    s = s.replace(B, '')
    s, tokens = _mask_funcs(s)
    s = re.sub(r'\s+', '', s)
    s = re.sub(r'([A-Za-zа-яё\)\]0-9])\(', r'\1*(', s)
    s = re.sub(r'\)([A-Za-zа-яё\(0-9])', r')*\1', s)
    s = re.sub(r'(?<=[A-Za-zа-яё\)\]0-9])(?=\x01)', '*', s)
    s = re.sub(r'(?<=\x02)(?=[A-Za-zа-яё0-9])', '*', s)
    # два имени функций подряд (`\pi\sqrt{3}` -> два токена) — тоже произведение
    s = re.sub(r'(?<=\x02)(?=\x01)', '*', s)
    s = re.sub(r'(?<=\d)(?=[A-Za-zа-яё])', '*', s)
    s = re.sub(r'(?<=[A-Za-zа-яё\)\]])(?=[A-Za-zа-яё])', '*', s)
    s = s.replace('{', '(').replace('}', ')')
    s = re.sub(r'([A-Za-zа-яё])_\(([^()]*)\)', r'\1_\2', s)
    s = _unmask_funcs(s, tokens)
    return ''.join(CYR_VAR.get(ch, ch) for ch in s)


def _top_level_comma(s):
    """Есть ли запятая вне фигурных и круглых скобок.

    `parse_latex('B, G')` не падает на хвосте: он молча возвращает левый токен `B`.
    Значит строка со списком через запятую не имеет права уходить в этот парсер —
    сравнение `B` с `B` дало бы ложное `correct` для ответов `B, G` и `B, G, H`.
    """
    depth = 0
    for ch in s:
        if ch in '{([':
            depth += 1
        elif ch in ')}]':
            depth = max(0, depth - 1)
        elif ch == ',' and depth == 0:
            return True
    return False


def parse_by_latex_engine(raw):
    """Родительский LaTeX-парсер SymPy; текст и единицы он не переваривает."""
    s = raw.strip()
    s = re.sub(r'\{,\}', ',', s)
    s = decimal_comma_to_point(s)
    s = re.sub(r'\\text\{[^{}]*\}', '', s)
    s = re.sub(r'\\mathrm\{([^{}]*)\}', r'\1', s)
    s = s.replace(B + 'left', '').replace(B + 'right', '')
    s = s.replace(B + '!', '').replace(B + ' ', '')
    s = re.sub(r'[а-яёА-ЯЁ]{2,}', '', s)
    s = s.replace(B + 'circ', '').strip(' .,;')
    if not s or _top_level_comma(s):
        return None
    try:
        return parse_latex(s)
    except Exception:
        return None


def parse_by_src(s):
    if not _cyr_ok(s):
        return None
    src = to_python_src(s)
    if not src or not re.search(r'[A-Za-z0-9]', src):
        return None
    env = dict(LOCALS)
    for name in set(re.findall(r'(?<![A-Za-z_0-9])(?!_)([A-Za-z][A-Za-z_0-9]*)(?![A-Za-z_0-9])', src)):
        if name not in LOCALS and not name.endswith(('if', 'th')):
            env[name] = Symbol(name)
    try:
        return sympify(src, locals=env)
    except Exception:
        return None


def as_number(e):
    try:
        if e is None or e.free_symbols:
            return None
        return float(N(e, 12))
    except Exception:
        return None


def symbol_names(e):
    """Имена свободных символов по порядку: сравнение наборов — это про них."""
    return sorted(str(s) for s in e.free_symbols)


def substitution_values(names):
    """Каждому имени — своя дробь из пары соседних простых.

    Один и тот же `7/10` всем символам делал равными `A` и `B`, `a/b` и `b/a`:
    подстановка проверяет структуру, а для этого разные имена должны получать
    разные числа.
    """
    return {name: Rational(prime(2 * i + 1), prime(2 * i + 2))
            for i, name in enumerate(names)}


def expressions_equal(a, b, rel=0.005, abs_tol=0.0):
    """True / False / None (None — SymPy не решил, идём к человеку).

    Абсолютного порога по умолчанию нет: атомные ответы (`1,1 * 10^-10 м`) с порогом
    вида 1e-9 сравнивались бы как равные даже с другим знаком.
    """
    if a is None or b is None:
        return None
    na, nb = as_number(a), as_number(b)
    if na is not None and nb is not None:
        return na == nb or abs(na - nb) <= max(rel * max(abs(na), abs(nb)), abs_tol)
    try:
        d = simplify(a - b)
    except Exception:
        return None
    if d == 0:
        return True
    try:
        if d.is_number:
            return abs(float(N(d, 12))) <= abs_tol
    except Exception:
        pass
    names_a, names_b = symbol_names(a), symbol_names(b)
    if names_a != names_b:
        # Разные наборы имён — это разные ответы: `2a` против `2b` не сверяется
        # подстановкой, чем бы ни закончился `simplify` выше.
        return False
    both = a.free_symbols | b.free_symbols
    values = substitution_values(names_a)
    subs = {s: values[str(s)] for s in both}
    if not subs:
        return None
    try:
        va = float(N(a.xreplace(subs), 12))
        vb = float(N(b.xreplace(subs), 12))
    except Exception:
        return None
    return abs(va - vb) <= max(rel * max(abs(va), abs(vb)), abs_tol)
