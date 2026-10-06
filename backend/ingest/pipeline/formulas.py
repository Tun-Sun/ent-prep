# -*- coding: utf-8 -*-
r"""Канон формулы и поиск по формулам корпуса.

Формула — содержимое $...$ или $$...$$ на странице. Одну и ту же запись модель
выдаёт то \nu, то ν, то 10^{23}, то 10^23, то 6{,}02, то 6,02, то 6.02. Канон —
ключ, который такие различия стирает. Разные формулы при этом должны остаться
разными: m_м и m_{моля} — разные ключи, x_1 и x^1 — тоже (маркер индекса
сохраняется). Регистр ключ сохраняет: N_A (число Авогадро) и n_моль (количество
вещества) — разные величины. Поиск по запросу регистр не учитывает.

  python pipeline/formulas.py                    отчёт: группы вариантов записи
  python pipeline/formulas.py --find "E=mc^2"    где формула (канон как подстрока)
  python pipeline/formulas.py --find ... --exact точное совпадение канона
  python pipeline/formulas.py --out out_b        один прогон
"""
import argparse, collections, glob, io, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DISP = re.compile(r"\$\$(.+?)\$\$", re.S)
INL = re.compile(r"(?<!\$)\$((?:[^$\\]|\\.)+?)\$(?!\$)", re.S)

# пробелы и «украшения», не несущие смысла
SP = re.compile(r"\\(?:,|;|:|!|quad|qquad|thinspace|negthinspace|displaystyle|nonumber)\s*")
DELIM = re.compile(r"\\(?:left|right|middle|big[gl]?[LR]?|Big[gl]?[LR]?)\b")
TEXTY = re.compile(r"\\(?:text|textrm|mathrm|mbox|hbox|operatorname|mathit|mathbf)\s*\{([^{}]*)\}")
NUMCOM = re.compile(r"(\d)\s*\{,\}\s*(\d)")

GREEK = dict(zip(
    "alpha beta gamma delta epsilon varepsilon zeta eta theta iota kappa lambda mu nu xi pi "
    "rho sigma tau upsilon phi varphi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma "
    "Upsilon Phi Psi Omega".split(),
    "α β γ δ ε ε ζ η θ ι κ λ μ ν ξ π ρ σ τ υ φ φ χ ψ ω Γ Δ Θ Λ Ξ Π Σ Υ Φ Ψ Ω".split()))

SYM = dict(zip(
    "cdot times div pm mp approx neq equiv leq le geq ge ll gg infty partial nabla to "
    "rightarrow leftarrow Rightarrow Leftarrow degree circ ldots dots perp parallel propto "
    "angle triangle square percent".split(),
    "· × ÷ ± ∓ ≈ ≠ ≡ ≤ ≤ ≥ ≥ << >> ∞ ∂ ∇ → → ← ⇒ ⇐ ° ° … … ⊥ ∥ ∝ ∠ △ □ %".split()))

# команда + аргумент без скобок (\bar x, \sqrt 2, \sin x) -> с скобками
ATTR = ("bar", "hat", "vec", "dot", "ddot", "overline", "underline", "tilde", "widetilde",
        "sqrt", "frac", "dfrac", "tfrac", "sin", "cos", "tg", "ctg", "arctg", "arcsin",
        "arccos", "log", "ln", "lg", "exp", "lim", "max", "min")
ATTR_RE = re.compile(r"\\(" + "|".join(ATTR) + r")\s+(?:\{([^{}]*)\}|([A-Za-z0-9α-ωА-Яа-я]))")
# Индексы: скобки приписываем всем, а не срезаем — иначе a^{2}b и a^{2b} дали бы один ключ.
# Цифры после ^ или _ без скобок читаем одним числом (10^23 = 10^{23}): в физике
# «10, умноженная на 2, в степени 3» так не пишут, а 10^{2}3 остаётся отдельным ключом.
GRP = r"(?:\{(?:[^{}]|\{[^{}]*\})*\}|\([^()]*\))"
SCRIPT = re.compile(r"([_^])(" + GRP + r"|[0-9]+|[^\s])")
BOX = ("boxed", "fbox", "framebox", "ensuremath")


def unbox(s):
    r"""Снимаем \boxed{...} — рамка вокруг ответа, не содержание. По паре скобок,
    вложенность любая (регэксп на два уровня проскакивает \frac{3p}{\bar{v}^{2}})."""
    for _ in range(8):
        at = None
        for c in BOX:
            p = s.find("\\" + c + "{")
            if p >= 0 and (at is None or p < at):
                at = p
        if at is None:
            return s
        open_at = s.index("{", at)
        d, k = 0, open_at
        while k < len(s):
            d += (s[k] == "{") - (s[k] == "}")
            if d == 0:
                break
            k += 1
        if d:
            return s
        s = s[:at] + s[open_at + 1:k] + s[k + 1:]
    return s


def _script(m):
    g = m.group(2)
    if g[0] == "{":
        return m.group(1) + g
    return m.group(1) + "{" + g.strip("()") + "}"


CMDS = sorted(list(GREEK) + list(SYM), key=len, reverse=True)
# запрет только на строчную букву: \alpha A -> αA, но \top не рвётся на \to + p
CMD_RE = re.compile(r"\\(" + "|".join(CMDS) + r")(?![a-z])")


def canon(s):
    """Ключ формулы: разные способы записать одно и то же дают один ключ."""
    s = s.strip().strip("$").strip()
    # \tag{2} — номер формулы в книге, не её содержание
    s = re.sub(r"\\tag\s*\{[^{}]*\}|\\notag", "", s)
    s = s.replace("\\{", "\x01").replace("\\}", "\x02")
    s = s.replace("\\%", "%").replace("\\&", "&").replace("\\#", "#").replace("\\\\", " ")
    s = re.sub(r"\\(?=\s)", " ", s)                   # «\ » — тоже пробел, не часть команды
    s = SP.sub(" ", s)
    s = DELIM.sub("", s)
    s = unbox(s)                                        # \boxed{...} — рамка, не содержание
    s = re.sub(r"\\[dt]frac", r"\\frac", s)
    s = re.sub(r"\\(?:rm|bf|it)\{([^{}]*)\}", r"\1", s)
    for _ in range(4):
        t = TEXTY.sub(r"\1", s)
        if t == s:
            break
        s = t
    s = CMD_RE.sub(lambda m: GREEK.get(m.group(1)) or SYM[m.group(1)], s)
    for _ in range(3):
        t = ATTR_RE.sub(lambda m: "\\" + m.group(1) + "{" + (m.group(2) or m.group(3)) + "}", s)
        if t == s:
            break
        s = t
    s = NUMCOM.sub(r"\1,\2", s)                       # 6{,}02 -> 6,02
    s = re.sub(r"(?<=\d)\.(?=\d)", r",", s)           # 6.02  -> 6,02
    s = re.sub(r"\s+", "", s)
    for _ in range(4):                                # 10^23 -> 10^{23}
        t = SCRIPT.sub(_script, s)
        if t == s:
            break
        s = t
    s = s.replace("{}", "")                           # {}^{12}_{6}C = ^{12}_{6}C
    s = s.replace("\x01", "{").replace("\x02", "}")
    # точка/запятая на конце — это конец предложения: «M=m/ν.» и «M=m/ν» — одна формула.
    # Срезаем в самом конце: \text{.} становится точкой только что
    return re.sub(r"[.,;:\s]+$", "", s)


def maths(md):
    """Формулы страницы с позициями: (запись, номер строки). Блок $$...$$ раньше,
    чтобы его не разрезали внутренние $."""
    out = []
    for m in DISP.finditer(md):
        out.append((m.group(1), md[:m.start()].count("\n") + 1))
    rest = DISP.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), md)
    for m in INL.finditer(rest):
        out.append((m.group(1), md[:m.start()].count("\n") + 1))
    # «Н $\cdot$ м$^2$/Кл$^2$» — модель разрывает единицы измерений текстом, и от записи
    # остаётся огрызок надстрочного символа без основания. Это не формула: в индекс ему не идти.
    return [(s.strip(), ln) for s, ln in out
            if len(s.strip()) > 1
            and not (re.match(r"^[\^_]", s.strip()) and not re.search(r"[A-Za-zА-Яа-я]", s))]


def runs(out=None):
    if out:
        if not os.path.isdir(os.path.join(ROOT, out, "pages")):
            sys.exit(f"нет папки pages в {out}")
        return [out]
    return sorted(os.path.basename(x) for x in glob.glob(os.path.join(ROOT, "out*"))
                  if os.path.isdir(os.path.join(x, "pages")))


def index(runs_):
    """канон -> {raws: Counter(варианты записи), where: [(прогон, страница, строка)]}"""
    idx = collections.defaultdict(lambda: {"raws": collections.Counter(), "where": []})
    total = 0
    for r in runs_:
        for f in sorted(glob.glob(os.path.join(ROOT, r, "pages", "*.json"))):
            page = os.path.basename(f)[:-5]
            md = json.load(io.open(f, encoding="utf-8")).get("markdown") or ""
            for s, ln in maths(md):
                total += 1
                g = idx[canon(s)]
                g["raws"][s] += 1
                g["where"].append((r, page, ln))
    return idx, total


def report(idx, total):
    variants = [(k, g) for k, g in idx.items() if len(g["raws"]) > 1]
    across = [(k, g) for k, g in idx.items() if len({w[0] for w in g["where"]}) > 1]
    print(f"формул {total}, различных по канону {len(idx)}")
    print(f"групп с несколькими вариантами записи: {len(variants)}, "
          f"пересекающих прогоны: {len(across)}")
    print("\n-- чаще всего повторена (одна формула, одно написание) --")
    for k, g in sorted(idx.items(), key=lambda kv: -sum(kv[1]["raws"].values()))[:10]:
        print(f"  {sum(g['raws'].values()):>3}x  {k}  ::  {list(g['raws'])[0][:60]}")
    print("\n-- варианты записи одного канона --")
    for k, g in sorted(variants, key=lambda kv: -len(kv[1]["raws"]))[:20]:
        print(f"  [{k[:58]}]")
        for s, n in g["raws"].most_common():
            print(f"      {n:>2}x  {s[:78]}")
    print("\n-- одна формула в разных прогонах --")
    for k, g in sorted(across, key=lambda kv: -len(kv[1]["where"]))[:10]:
        rs = collections.Counter(w[0] for w in g["where"])
        print(f"  {k[:58]}  ::  " + ", ".join(f"{r}x{n}" for r, n in rs.most_common()))


FRAC = re.compile(r"\\frac\{([^{}]*)\}\{([^{}]*)\}")


def loose(k):
    r"""Плоский ключ для поиска: \frac{a}{b} -> a/b, скобки и \sqrt выбрасываем.
    Поисковый запрос человек пишет через слэш («3RT/M»), а в книге это \frac{3RT}{M}.
    Группировка по canon остаётся строгой, loose — только подстрока в --find."""
    for _ in range(4):
        t = FRAC.sub(r"\1/\2", k)
        if t == k:
            break
        k = t
    return re.sub(r"[\\{}()]", "", k).lower()


def find(idx, q, exact):
    k = canon(q)
    kl, ql = k.lower(), loose(k)
    hits = [(key, g) for key, g in idx.items()
            if (key.lower() == kl if exact
                else bool(kl) and (kl in key.lower() or bool(ql) and ql in loose(key)))]
    if not hits:
        print(f"не найдено. канон запроса: [{k}]")
        print("ближайшие по общему набору знаков:")
        near = sorted(idx.items(), key=lambda kv: -len(set(kl) & set(kv[0].lower())))[:5]
        for key, g in near:
            print(f"  {len(set(kl) & set(key.lower())):>3}  {key[:70]}")
        return 1
    print(f"запрос [{q}] -> канон [{k}], групп: {len(hits)}")
    for key, g in sorted(hits, key=lambda kv: -sum(kv[1]["raws"].values())):
        print(f"\n  канон {key}")
        for s, n in g["raws"].most_common():
            print(f"    {n:>2}x запись: {s[:90]}")
        for w in sorted(g["where"]):
            print(f"    {w[0]}/pages/{w[1]}.json:{w[2]}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--find", metavar="ФОРМУЛА")
    ap.add_argument("--exact", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    idx, total = index(runs(a.out))
    if a.find:
        return find(idx, a.find, a.exact)
    report(idx, total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
