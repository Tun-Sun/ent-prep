#!/usr/bin/env python3
"""Границы задач: markdown страниц -> out_<прогон>/tasks.json со схемой сущностей.

Детерминированный разбор, к API не ходим. Смысл: после разбора ошибки распознавания
видно по каждой задаче, а не по странице. Страница из шести задач с одним спорным
знаком иначе не говорит, в какой именно задаче ошибка.

Диалекты границ, найденные в корпусе:
    **1.** / **9.13.** / **1.203.**   жирный номер в начале абзаца
    ### 1.223                        номер — целый заголовок
    Тапсырма 12. / **Задача 1**      слово с номером
    **Пример 1.**                    то же слово с номером, но счёт свой: в учебнике
                                     с изложением пример и задача — две единицы текста
    3. По какой линии                простой нумерованный список

Чисто теоретический лист (конспект без единого номера) — не пустой прогон: границей
считается сама страница, и единица «Теория <номер страницы>» несёт весь её текст.
Шапка бланка («INTELLECT» на двух языках, логотип, линейка) сюда не доходит: она
срезана с записи страницы в letterhead.py, и разбор видит только содержимое листа.

Страницы ответов — отдельный режим: там номер подписан к значению, а не к условию.
Три признака ответа:
    а) блок под заголовком «Ответы / Жауаптар»;
    б) на строке два и больше жирных номеров («**9.1.** 0,02 с; **9.2.** 12.»);
    в) тот же номер уже встречался раньше по порядку страниц — сборник печатает
       задачи вперёд, ответы сзади, поэтому первое вхождение считается задачей.
Номер, который встретился один раз и попал на страницу, где остальные свёрнуты в
ответы, остаётся задачей с пометкой «похоже на ответ»: решает человек, не эвристика.

 python tasks.py --out out_v2
"""
import argparse, collections, glob, io, json, os, re

NUM = r"\d{1,2}(?:\.\d{1,3})?"
# после номера в источнике бывает звёздочка-«сложно», градус или апостроф: 1.227*, **1.237°.**
# Звёздочку модель экранирует (1.234\*.), поэтому бэкслэш тоже здесь.
JUNK = r"[*°'′”\u00b0\\]*"
TRAIL = JUNK + r"[.)]?[:.]?\s*"

HEAD_ONLY = re.compile(r"^#{1,4}\s+\*{0,2}(" + NUM + r")" + JUNK + r"[.)]?" + JUNK + r"\s*$")
BOLD = re.compile(r"^\*\*\s*(" + NUM + r")" + TRAIL + r"\*\*\s*(.*)$")
BOLD_ALL = re.compile(r"\*\*\s*(" + NUM + r")[.)]\s*\*\*")
# Ответы печатают не только отдельной страницей, но и блоком в конце той же:
# «**Ответы к главе 1: 1.1) 5,4 мкН. 1.2) 100 см.**» Без этой ветки такая строка
# доставалась последней задаче страницы — в банк уезжал чужой список в конце условия,
# а поле ответа пустело, хотя ответ напечатан рядом с задачей.
ANS_BLOCK = re.compile(r"^\s*(?:#{1,4}\s+)?\*{0,2}\s*(?:Ответы|Жауаптар|Answers)\b"
                       r"[^:\n]*?:\s*", re.I)
# Число с точкой или скобкой и пробелом — начало записи ответа. Перед числом не должно
# быть цифры, точки и запятой: иначе «$4 \cdot 10^{-13}$ Кл.» дало бы запись «13», а
# «0,225 Н» — запись «225».
ANS_REC = re.compile(r"(?<![\d.,])(" + NUM + r")[.)]\s+")
WORD = re.compile(r"^\*{0,2}\s*(Тапсырма|Задача|Есеп|Вариант|Пример)\s*(" + NUM + r")\s*\*{0,2}"
                  + JUNK + r"[.)]?" + JUNK + r"\s*", re.I)
PLAIN = re.compile(r"^(" + NUM + r")[.)]\s+\S")
SECT = re.compile(r"^\s*(#{1,4})\s+(\S.*)$")
ANS_HEAD = re.compile(r"ответ|жауап|answer", re.I)
# в оцифровке строка ответа приходит в трёх видах: «Ответ: …», «$$Ответ: …$$» и «*Ответ*: …».
# Первые две раньше терялись: без учёта обёртки $$ в банке у задачи пустой ответ, хотя
# он напечатан прямо в её теле. Группу \1 сохраняем подстановкой — снимать $$ нельзя,
# иначе от формулы останется висячий delimiter и KaTeX покажет его как текст.
# Третий вид после \b — «Ответ\text{: }»: модель бережёт русское слово и прячет двоеточие
# внутрь \text{}, голое «:» после слова не стоит, а ответ в книге напечатан.
ANS_IN = re.compile(r"^\s*((?:\$\$|\$)\s*)?[*_]{0,2}\s*(Ответ|Жауабы|Жауап|Answer)\b"
                    r"(?:\s*[*_]{0,2}\s*[:.]|\s*\\text\s*\{[^{}]*[:.][^{}]*\})", re.I)
ANS_WORD = re.compile(r"^\s*((?:\$\$|\$)\s*)?[*_]{0,2}\s*(?:Ответ|Жауабы|Жауап|Answer)\b"
                      r"(?:\s*[*_]{0,2}\s*[:.]|\s*\\text\s*\{[^{}]*[:.][^{}]*\})\s*", re.I)
# Ответ внутри строки: ячейка таблицы «Дано | Решение» набрана моделью одной строкой через
# <br>, и «*Ответ:* …» стоит не в её начале. Строчный якорь ANS_IN такой ответ не видит,
# и задача уезжает в банк с пустым ответом, хотя ответ в тексте есть.
# Слово не должно быть частью другого слова («Ответы» — это заголовок блока, не ответ).
# Двоеточие обязательно и только оно: «Ответ.» посреди рассуждения — это проза, а не метка.
# Закрывающие звёздочки после двоеточия (формула «*Ответ:* …») снимаем — значение
# всё равно чистится от *, а без этого варианта метка не распознаётся вообще.
ANS_MID = re.compile(r"(?<![0-9A-Za-z\u0400-\u04FF])(?:[*_]{1,2}\s*)?(?:Ответ|Жауабы|Жауап|Answer)"
                     r"\s*[*_]{0,2}\s*:\s*(?:[*_]{1,2}\s*)?(\S.*)$", re.I)
TABLE = re.compile(r"^\s*\|\s*(?:№|#)\s*\|")
SEP_ROW = re.compile(r"^\s*\|[\s:|-]+$")
ROW = re.compile(r"^\s*\|")
DANO = re.compile(r"Дано|Берілгені|Ықшам|Бысықша", re.I)
# Вариантов бывает восемь (A–H), а не пять: с узким A–E тест терял хвост вариантов.
# На низком DPI модель отдаёт кириллические гомоглифы этих же букв («С)» вместо «C)»,
# «Н)» вместо «H)»), и без их нормализации вариант выглядел бы потерянным.
OPTION_HOMOG = {"А": "A", "В": "B", "С": "C", "Е": "E", "Н": "H", "К": "K"}
OPTION = re.compile(r"^\s*([A-HАВЕКНС])\)\s*")
OPTION_CYR = re.compile(r"^\s*([АВЕК])\)\s")
# Подпись выкройки и номер рисунка в прозе: «![Рис. 1.30](assets/p13_fig1.png)» и
# «(рис. 1.32)». Дефис и тире в номере значат одно: у Касаткиной рисунки «1-3».
FIG_CAP = re.compile(r"!\[([^\]]*)\]\((assets/[^)]+)\)")
FIG_NUM = re.compile(r"\d+(?:[.\u2011-]\d+)*")
RIS = re.compile(r"(?:рис[а-яёa-z]*\.?|сурет)\s*(\d+(?:[.\u2011-]\d+)?)", re.I)


def fig_key(s):
    m = FIG_NUM.search(s or "")
    return re.sub(r"[.\u2011-]", ".", m.group(0)) if m else ""


def figure_order(body):
    """Первой в список ставится выкройка, которую задача называет текстом.

    Импорт берёт figures[0], а в книге строка «![Рис. 1.30] … ![Рис. 1.32]» идёт
    одна под несколько задач: без порядка под задачей про рис. 1.32 лежала бы
    картинка рис. 1.30. Остальные выкройки остаются в списке — по ним банк
    показывает подписи, и provenance следующего импорта их не теряет.
    """
    caps = [(fig_key(m.group(1)), m.group(2)) for m in FIG_CAP.finditer(body)]
    figs = [p for _, p in caps]
    named = [fig_key(n) for n in RIS.findall(FIG_CAP.sub(" ", body))]
    for want in named:
        for key, path in caps:
            if key and key == want:
                return [path] + [f for f in figs if f != path]
    return figs


def share_figures(tasks, pages):
    """Задача без своей строки картинок берёт тот вырез, который называет текстом.

    В книге строка «![Рис. 1.37] … ![Рис. 1.40]» одна на несколько задач и физически
    стоит под последней: ей и доставались все четыре выкройки, а предыдущие оставались
    без рисунка. Одну выкройку могут показать две задачи — условие и его решение, —
    поэтому соседа не обиранем: у соседа первым стоит названный им самим рисунок.
    """
    for t in tasks:
        if t.get("figures"):
            continue
        prose = FIG_CAP.sub(" ", t.get("markdown") or "")
        want = {fig_key(n) for n in RIS.findall(prose)} - {""}
        if not want:
            continue
        for pg in t.get("pages") or []:
            hit = next((m.group(2) for m in FIG_CAP.finditer((pages.get(pg) or {}).get("markdown") or "")
                        if fig_key(m.group(1)) in want), None)
            if hit:
                t["figures"] = [hit]
                break


def clean(s):
    return re.sub(r"[*_`]+", "", s).strip()


# Заголовок блока переразбивки: «**БЛОК 1. Вычислите:**», «**<u>БЛОК 2.</u> …**»,
# «### **БЛОК 4. Освободитесь…**». Жирным — только строка, закрытая звёздочками, или
# решётка: проза, начинающаяся со слова «блок», заголовок не напоминает.
BLOCK_HEAD = re.compile(r"^\s*(?:#{1,4}\s+)?\*{0,2}\s*(?:<u>)?\s*(?:БЛОК|Блок|блок)\b")
# Заголовок-буква варианта («### A», «#### **B**», «### В»): нумерацию не перебивает,
# ответы под ним печатают одним списком на все варианты.
VARIANT = re.compile(r"^[A-HА-Я]$", re.I)


def block_head(line):
    """Имя блока, если строка — его заголовок, иначе None."""
    if not BLOCK_HEAD.match(line):
        return None
    s = line.strip()
    if not s.startswith("#") and not (s.startswith("**") and s.endswith("**")):
        return None
    return clean(re.sub(r"^#{1,4}\s+|</?u>", "", s))


# Буква уровня, набранная только жирным, без решётки: «**A**», «**А**».
BOLD_LETTER = re.compile(r"^\*{1,2}\s*(\S.*?)\s*\*{1,2}$")


def level_head(line):
    """Буква напечатанного уровня жирным. Решёточную («### В») делает заголовком
    ветка SECT, а эта строка без решётки ушла бы в тело предыдущей единицы.
    Уровень нумерацию не перебивает: в сборнике счёт сквозной на весь блок."""
    m = BOLD_LETTER.match(line.strip())
    if not m:
        return None
    name = clean(m.group(1))
    return name.upper() if VARIANT.fullmatch(name) else None


def unit_scope(stack):
    """Область единицы — последний заголовок, который не буква варианта. Тема строки в
    банке строится по области, и «Рустюмова 2013 · A» вместо «· БЛОК 1. Вычислите:» —
    это три темы на одну, различить которые потом нельзя."""
    for _, name in reversed(stack):
        if not VARIANT.fullmatch(name):
            return name
    return ""


def run_of(stack):
    """Счёт номеров: путь заголовков без буквы варианта и без шапки «ОТВЕТЫ».
    В сборнике с переразбивкой задачи блока стоят под буквой варианта, а его ответы —
    под заголовком «ОТВЕТЫ», и связывает их именно этот путь."""
    return " / ".join(n for _, n in stack
                      if not ANS_HEAD.search(n) and not VARIANT.fullmatch(n))


# Буква напечатанного уровня: в сборниках ЕНТ под «А» дают базовый, под «В» — повышенный.
# Кириллические гомоглифы сводим к латинице тем же набором, что и варианты ответа
# (OPTION_CYR): на 300 dpi модель пишет «B» и «В» для одного и того же заголовка, и без
# этого одна страница дала бы два разных уровня.
LEVEL_CYR = str.maketrans({"А": "A", "В": "B", "Е": "E", "К": "K"})


def level_of(stack):
    """Верхняя буква-заголовок над единицей, пустая строка — уровня в книге нет."""
    for _, name in reversed(stack):
        if VARIANT.fullmatch(name):
            return name.upper().translate(LEVEL_CYR)
    return ""


def norm(n):
    return n.strip().strip(".*°'′”\\").replace(" ", "")


def block_of(stack):
    """Блок = раздел (заголовок уровня 1–2) плюс текущая область.
    Имени области для идентификации единицы мало: в главе Касаткиной «Решение отдельных
    задач» напечатана трижды, по разу на параграф, и счёт номеров в каждом свой. Без
    раздела Задача 9 из §2 сворачивалась в «ответ» Задачи 9 из §1 — чужое решение в 4700
    знаков в поле ответа, и так 30 раз.
    Answers-таблицы так не ищут: там ответ §1 лежит под заголовком «ОТВЕТЫ / Средний
    уровень», а задача — под «КРИВОЛИНЕЙНОЕ ДВИЖЕНИЕ / Средний уровень», и связывает их
    именно имя области, без раздела (см. attach)."""
    top = stack[-1][1] if stack else ""
    anc = next((name for lvl, name in reversed(stack) if lvl <= 2), "")
    return top if not anc or anc == top else f"{anc} / {top}"


def answer_lines(body):
    """Ответы, напечатанные внутри самой единицы: «Ответ: …», «$$Ответ: …$$», «*Ответ*: …».

    Раньше искался только якорь по началу строки, поэтому ответ из ячейки таблицы
    «Дано | Решение» (вся ячейка — одна строка через <br>) терялся, и задача уезжала
    в банк с пустым ответом, хотя в её теле он напечатан. Обёртку $ / $$ не снимаем:
    вместе с ней формула остаётся формулой, без неё KaTeX покажет висячий delimiter.
    """
    out = []
    lines = body.split("\n")
    for i, ln in enumerate(lines):
        if ANS_IN.match(ln):
            v = ANS_WORD.sub(r"\1", ln, count=1).strip().strip("*").strip()
            if v in ("", "$", "$$"):
                # метка набрана отдельной строкой («**Жауап:**»), а значение — следующей
                # строкой, обычно отдельной формулой. Без этого подбора задача уезжает
                # в банк с пустым ответом, хотя на странице он напечатан.
                v = lines[i + 1].strip() if i + 1 < len(lines) else ""
            out.append(v)
            continue
        m = ANS_MID.search(ln)
        if m:
            v = re.sub(r"\s*\|+\s*$", "", m.group(1)).strip().strip("*").strip()
            out.append(v)
    return [v for v in out if v]


def add_answer(answers, num, scope, page, text, block=None, run=""):
    """Запись ответа ключуется именем области — так таблица из раздела «ОТВЕТЫ» находится
    свою задачу из раздела темы. Блок в ключ не кладём: он разные у таблицы и задачи.
    Блок свёрнутой задачи пишем в значение — её принимать по имени области нельзя."""
    text = text.strip().strip("*").strip()
    if text:
        answers.setdefault((num, scope), []).append(
            {"page": page, "text": text, "block": block or "", "run": run})


# ============================ один проход по прогону ============================
BARE = re.compile(r"\d{1,3}")


def page_footers(pages):
    """{страница: индекс последней строки}, если там напечатанный номер страницы.
    Верим только согласованности: голые числа в конце страниц дают одно и то же
    смещение «номер книги минус страница файла» на нескольких страницах. Ответ
    («12») так не выстраивается, а номер страницы — всегда."""
    cand = {}
    for p in pages:
        lines = (p.get("markdown") or "").split("\n")
        last = max((i for i, l in enumerate(lines) if l.strip()), default=None)
        if last is not None and BARE.fullmatch(lines[last].strip()):
            cand[p["page"]] = (last, int(lines[last].strip()) - p["page"])
    agree = collections.Counter(off for _, off in cand.values())
    return {pg: i for pg, (i, off) in cand.items() if agree[off] >= 2}


def walk(pages):
    stack, tasks, answers, other, cur = [], [], {}, [], None
    cont = {}                       # (блок, слово, префикс) -> последний номер: отбраковка обманок
    worded = set()                  # блоки, где единицы размечены словом: там голый номер — пункт решения
    acc = collections.Counter()     # куда ушёл каждый знак markdown, чтобы баланс сходился
    foot = page_footers(pages)

    def take(rest, line, bucket):
        """Знаки строки делятся между телом и маркером: полного учёта без этого нет."""
        acc[bucket] += len(rest) + 1
        acc["маркеры"] += len(line) - len(rest)

    def push_head(line):
        m = SECT.match(line)
        lvl = len(m.group(1))
        while stack and stack[-1][0] >= lvl:
            stack.pop()
        stack.append((lvl, clean(m.group(2))))

    def in_answers():
        return any(ANS_HEAD.search(s) for _, s in stack)

    def scope():
        return unit_scope(stack)

    for p in pages:
        page = p["page"]
        lines = (p.get("markdown") or "").split("\n")
        # cur не обнуляем: решение задачи продолжается на следующей странице без маркера,
        # и без этого оно уезжало бы в «вне задач» (в out_b так терялось 25 тыс. знаков)
        blank, i = True, 0
        while i < len(lines):
            raw = lines[i]
            line = raw.rstrip()
            from_head = False               # маркер уже проверен в ветке заголовка, второй раз нельзя
            run = run_of(stack)             # счёт, к которому относится эта строка
            acc["пробелы"] += len(raw) - len(line)      # баланс: без этого строка «abc   » теряется

            if not line.strip():
                acc["пустые"] += len(line) + 1
                cur, blank, i = cur, True, i + 1
                continue

            if foot.get(page) == i and BARE.fullmatch(line.strip()):
                other.append({"page": page, "markdown": line.strip(), "note": "номер страницы"})
                acc["вне задач"] += len(line) + 1
                blank, i = True, i + 1
                continue

            if HEAD_ONLY.match(line):
                acc["маркеры"] += len(line) + 1
                if not in_answers():
                    cur = new_task(page, norm(HEAD_ONLY.match(line).group(1)), "head", stack)
                    tasks.append(cur)
                else:
                    cur = None
                blank, i = True, i + 1
                continue

            bname = block_head(line) if blank else None
            if bname:
                # Уровень 2: блок перебивает § (в нём счёт свой), но сносится только
                # заголовком уровня 1–2, а не буквой варианта «### A».
                while stack and stack[-1][0] >= 2:
                    stack.pop()
                stack.append((2, bname))
                acc["заголовки"] += len(line) + 1
                cur, blank, i = None, True, i + 1
                continue

            lname = level_head(line) if blank else None
            if lname:
                # Уровень — сосед буквы «### A», просто набранной жирным без решётки:
                # тот же третий уровень, счёт задач не перебивает, в тему не лезет.
                while stack and stack[-1][0] >= 3:
                    stack.pop()
                stack.append((3, lname))
                acc["заголовки"] += len(line) + 1
                cur, blank, i = None, True, i + 1
                continue

            if SECT.match(line):
                inner = SECT.match(line).group(2).strip()
                mh = WORD.match(inner) if blank else None
                if mh and plausible("word", norm(mh.group(2)), cont, stack, mh.group(1)):
                    # «### Задача 3» — граница задачи, а не раздел: модель сама решает,
                    # оформить ли заголовок жирным или решёткой, и парсер не вправе этого не знать
                    acc["маркеры"] += len(line) - len(inner)
                    line, from_head = inner, True
                else:
                    push_head(line)
                    acc["заголовки"] += len(line) + 1
                    cur, blank, i = None, True, i + 1
                    continue

            if TABLE.match(line):
                n = table_answers(lines, i, scope(), answers, page, acc, run_of(stack))
                i += n
                cur, blank = None, True
                continue

            if in_answers() and ROW.match(line) and cells_of_answers(line, answers, scope(),
                                                                    run_of(stack), page):
                # Ответ блока печатают таблицей без шапки «№» — «| 1) 1 | 2) 8 |». Веткой
                # TABLE такая не берётся (нет шапки), жирных номеров на строке нет, и
                # весь список ответов уходил в «вне задач»: в Рустюмовой так терялись
                # 20 ответов блока 2, а задачи оставались с пометкой «ответа нет».
                acc["ответы"] += len(line) + 1
                cur, blank, i = None, False, i + 1
                continue

            ma = ANS_BLOCK.match(line) if blank else None
            if ma:
                recs = list(ANS_REC.finditer(line, ma.end()))
                if recs:
                    # ответ здесь ищется по той же области, что и в таблице: задача и её
                    # ответ стоят под одним заголовком главы, раздел им не нужен
                    sc = scope()
                    for k, h in enumerate(recs):
                        end = recs[k + 1].start() if k + 1 < len(recs) else len(line)
                        add_answer(answers, norm(h.group(1)), sc, page, line[h.end():end],
                                   run=run)
                    acc["ответы"] += len(line) + 1
                    cur, blank, i = None, False, i + 1
                    continue

            hits = list(BOLD_ALL.finditer(line))
            if len(hits) >= 2:
                sc = scope()
                for k, h in enumerate(hits):
                    end = hits[k + 1].start() if k + 1 < len(hits) else len(line)
                    add_answer(answers, norm(h.group(1)), sc, page, line[h.end():end], run=run)
                acc["ответы"] += len(line) + 1
                cur, blank, i = None, False, i + 1
                continue

            mb = BOLD.match(line) if blank else None
            mw = WORD.match(line) if blank else None
            mp = PLAIN.match(line) if blank else None
            kind = num = word = None
            rest = ""
            if mb:
                kind, num, rest = "bold", norm(mb.group(1)), mb.group(2)
            elif mw:
                kind, num, word, rest = "word", norm(mw.group(2)), mw.group(1), line[mw.end():].strip()
            elif mp:
                kind, num, rest = "plain", norm(mp.group(1)), line[mp.end() - 1:]

            # plausible() двигает счётчик cont — второй вызов на той же строке сдвинул бы номер
            if kind and not from_head and not plausible(kind, num, cont, stack, word or "", worded):
                kind = num = None

            if kind:
                if in_answers():
                    add_answer(answers, num, scope(), page, rest, run=run_of(stack))
                    acc["ответы"] += len(line) + 1
                    cur, blank, i = None, False, i + 1
                    continue
                if word:
                    worded.add(block_of(stack))
                cur = new_task(page, num, kind, stack, word)
                tasks.append(cur)
                if rest:
                    cur["lines"].append(rest)
                    cur["loc"].append([page, i])
                take(rest, line, "задачи")
                blank, i = False, i + 1
                continue

            if cur is None:
                other.append({"page": page, "markdown": line})
                acc["вне задач"] += len(line) + 1
            else:
                if cur["pages"][-1] != page:
                    cur["pages"].append(page)
                cur["lines"].append(line)
                cur["loc"].append([page, i])
                acc["задачи"] += len(line) + 1
            blank, i = False, i + 1
    return tasks, answers, other, acc


def new_task(page, num, kind, stack, word=""):
    # loc — координаты тела в строках страницы: по ним стенд и правит конкретную задачу
    return {"num": num, "word": word or "", "kind": kind,
            "scope": unit_scope(stack), "block": block_of(stack), "run": run_of(stack),
            "level": level_of(stack),
            "pages": [page], "lines": [], "loc": []}


def theory_pages(pages):
    """Лист, на котором не нашлось ни одного напечатанного номера задачи — это
    конспект теории, а не пустой прогон. Границу здесь задаёт не номер, и вырывать
    из такого листа абзацы значило бы выдумывать структуру, которой в книге нет:
    честная единица — вся страница целиком."""
    out = []
    for p in pages:
        lines = (p.get("markdown") or "").split("\n")
        body = [(i, l.rstrip()) for i, l in enumerate(lines) if l.strip()]
        if not body:
            continue
        head = next((SECT.match(l) for _, l in body), None)
        scope = clean(head.group(2)) if head else "теория"
        out.append({"num": str(p["page"]), "word": "Теория", "kind": "theory",
                    "scope": scope, "block": scope, "run": scope, "level": "",
                    "pages": [p["page"]],
                    "lines": [l for _, l in body], "loc": [[p["page"], i] for i, _ in body]})
    return out


def cells_of_answers(line, answers, sc, run, page):
    """Строка таблицы ответов без шапки: каждая ячейка — «номер) значение».
    Возвращает число записей: 0 значит, что строка ответом не была (разделитель или
    ячейки с текстом), и ветке её брать нельзя."""
    n = 0
    for cell in line.strip().strip("|").split("|"):
        mc = re.match(r"^\s*\*{0,2}(" + NUM + r")[.)]\*{0,2}\s+(.*)$", cell.strip())
        if mc and mc.group(2).strip():
            add_answer(answers, norm(mc.group(1)), sc, page, mc.group(2), run=run)
            n += 1
    return n


def table_answers(lines, i, sc, answers, page, acc, run=""):
    """| № | 1 | 2 | над | | 0,83 м/с² | 1,57 м/с | — номер из шапки, значение из ячеек.
    Строк-значений может быть несколько (таблица разбита по 3 колонки на листе)."""
    head = [c.strip() for c in lines[i].strip().strip("|").split("|")]
    acc["ответы"] += len(lines[i]) + 1
    j = i + 1
    while j < len(lines) and SEP_ROW.match(lines[j]):
        acc["ответы"] += len(lines[j]) + 1
        j += 1
    cols = head[1:]
    while j < len(lines) and ROW.match(lines[j]):
        cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
        for k, v in enumerate(cells[1:]):
            if k < len(cols) and cols[k]:
                add_answer(answers, norm(cols[k]), sc, page, v, run=run)
        acc["ответы"] += len(lines[j]) + 1
        j += 1
    return j - i


def plausible(kind, num, cont, stack, word="", worded=()):
    """Обманка — вариант ответа «1) 2) 3)» внутри условия. Настоящий маркер продолжает
    счёт в своей области либо начинает его с единицы; составные номера (9.13) уникальны."""
    if kind == "head" or "." in num:
        return True
    try:
        n = int(num)
    except ValueError:
        return False
    if not word and block_of(stack) in worded:
        # «2) Заряды разноимённые.» — второй пункт разобранного решения, а не задача:
        # в блоке, где единицы размечены словом («Задача 11»), голый номер — часть решения.
        # В листе без слов («1 … 2 …» как задачи) этот же приём убил бы весь блок.
        return False
    # ключ — блок (раздел + область), слово и префикс составного номера: счёт внутри
    # блока идёт по порядку, и один и тот же номер в двух блоках — не продолжение счёта.
    # Слово в ключе обязательно: «Пример 1…8» и «Задача 1…3» в одном разделе — два разных
    # счёта, и без слова «Задача 3» после «Пример 5» выглядела бы обманкой.
    key = (block_of(stack), word.lower(), num.split(".")[0] if "." in num else "")
    prev = cont.get(key)
    cont[key] = n
    return prev is None or n == 1 or n == prev + 1


# ================================ сущности ================================
# Перенос в конце строки — не пробел: «верши-\nнах» читается «вершинах», а в банке это
# выглядит как опечатка. Склейка только между строчными буквами (кириллица, латиница и
# казахские буквы), чтобы не склеить тире или знак минус в формуле.
LINE_HYPHEN = re.compile(r"(?<=[a-zа-яёәғқңөұүһі])-\n(?=[a-zа-яёәғқңөұүһі])", re.I)


def entities(t, pages):
    raw = "\n".join(t["lines"])
    body = LINE_HYPHEN.sub("", raw)
    t["markdown"] = body
    # ключ единицы: блок, а не имя области — «Задача 1» в главе встречается трижды
    # (по разу на параграф), и стенд по короткому ключу отмечал бы приёмкой все три
    t["key"] = f"{t['block']}#{t['word']}{t['num']}".strip()
    # полосы тела по страницам: правка на стенде заменяет ровно эти строки, не всю страницу
    span = collections.defaultdict(lambda: [10**9, -1])
    for pg, ln in t.pop("loc"):
        s = span[pg]
        s[0], s[1] = min(s[0], ln), max(s[1], ln + 1)
    t["spans"] = [{"page": pg, "l0": v[0], "l1": v[1]} for pg, v in sorted(span.items())]
    # знаки считаем по исходной склейке: перенос, склеенный LINE_HYPHEN, — не потерянный
    # знак, иначе баланс «N из tot» разойдётся на число склеек по всему прогону
    t["chars"] = len(raw)
    t["display"] = body.count("$$") // 2
    t["inline"] = len(re.findall(r"(?<!\$)\$(?!\$)", body)) // 2
    t["figures"] = figure_order(body)
    t["dano"] = bool(DANO.search(body))
    t["answer_in"] = answer_lines(body)
    t["options"] = len([1 for ln in body.split("\n") if OPTION.match(ln) or OPTION_CYR.match(ln)])
    t["options_cyr"] = sorted({m.group(1) for ln in body.split("\n")
                               for m in [OPTION_CYR.match(ln)] if m})
    t["options_list"] = option_list(body)
    fl = []
    nums = where_nums(t["num"])
    for pg in t["pages"]:
        for u in (pages[pg].get("uncertain") or []):
            # «где» от модели — текст вольный: «Тапсырма 14 / Ответ», «8», «строка 12».
            # Сопоставляем целыми числами: подстрока «1» попала бы в половину задач страницы.
            if nums & where_nums(str(u.get("where") or "")):
                fl.append(dict(u, page=pg))
    t["uncertain"] = fl
    return t


def where_nums(s):
    """Целые токены номера: «9.13» и «14» — по одному, «см. 1.203 и 1.204» — по два.
    Подстроки не берём: «1» иначе совпадает с половиной номеров страницы."""
    return set(re.findall(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3})?)(?![\d.])", str(s)))


def option_list(body):
    """Варианты теста по порядку: буква нормализована, текст — как отсканирован.

    Тело единицы от этого не меняется — варианты печатаются в условии книги и остаются
    там. Список нужен банку: без отдельных строк ответа приложение не может отрендерить
    тест тестом, и тот же текст живёт ещё и в них.
    """
    out = []
    for ln in body.split("\n"):
        m = OPTION.match(ln)
        if not m:
            continue
        out.append({"letter": OPTION_HOMOG.get(m.group(1), m.group(1)),
                    "text": ln[m.end():].strip()})
    return out


# ============================ ответ <-> задача ============================
def attach(tasks, answers, acc):
    """Правило (в): одно и то же число позже по книгам — это ответ, а не вторая задача.
    «Позже» считаем внутри одного блока: повтор номера в другом блоке того же имени —
    это вторая задача, а не ответ первой."""
    first, folded = {}, collections.Counter()
    for t in tasks:
        first.setdefault((t["num"], t["block"]), t)
    for t in list(tasks):
        owner = first[(t["num"], t["block"])]
        if owner is t or t["pages"][0] <= owner["pages"][0]:
            continue
        add_answer(answers, t["num"], owner["scope"], t["pages"][0], " ".join(t["lines"]),
                   owner["block"], run=owner.get("run", ""))
        folded[t["pages"][0]] += 1
        acc["ответы"] += t["chars"] + 1
        acc["задачи"] -= t["chars"] + 1
        tasks.remove(t)

    by_num = collections.defaultdict(list)
    for (n, sc), v in answers.items():
        by_num[n].append((sc, v))
    # Ответ блока ищется по счёту, внутри которого напечатан: задачи стоят под буквой
    # варианта, а его ответы — под заголовком «ОТВЕТЫ», и именем области они не сходятся.
    # Для книг, где блок не перебивает счёт (физика), ключ совпадает с областью, и этот
    # индекс ничего не находит там, где не должен.
    by_run = collections.defaultdict(list)
    for (n, sc), v in answers.items():
        for g in v:
            if g.get("run"):
                by_run[(n, g["run"])].append(g)
    # «взять по номеру» можно, только если номер в книге один: в главе Касаткиной задачи
    # для самостоятельного решения (1…37) и разобранные решения (1…30) идут двумя независимыми
    # счётами, и по номеру к разобранной задаче 20 приклеилось условие задачи 20 из списка —
    # целиком, с чужим решением в 4700 знаков
    blocks_of = collections.defaultdict(set)
    for t in tasks:
        blocks_of[t["num"]].add(t["block"])
    for t in tasks:
        got = answers.get((t["num"], t["scope"])) or []
        if not got and t.get("run"):
            got = by_run.get((t["num"], t["run"])) or []
        only = by_num.get(t["num"], [])
        if not got and len(only) == 1 and len(blocks_of[t["num"]]) == 1:
            got = only[0][1]
        elif not got and len(only) > 1:
            t["answer_note"] = "номер под несколькими заголовками"
        # свёрнутый из другой задачи ответ привязан к её блоку: чужой блок его не берёт
        got = [g for g in got if not g.get("block") or g["block"] == t["block"]]
        if got:
            t["answer"] = "; ".join(g["text"] for g in got[:3])
            t["answer_pages"] = sorted({g["page"] for g in got if g.get("page")})
        elif folded[t["pages"][0]] >= 3:
            t["answer_note"] = "похоже на ответ"
        # Пустой ответ надо уметь отличить от не найденного: без этой строки «без ответа»
        # в банке читается как «мы не доглядели», хотя книга просто ничего не напечатала
        # (теория, вопрос без численного ответа, тест без ключа, ответы в конце книги).
        if not t.get("answer") and not t["answer_in"] and not t.get("answer_note"):
            t["answer_note"] = "ответа в отсканированной части нет"
    return tasks


# ================================ отчёт ================================
def report(out, pages, tasks, answers, other, acc):
    tot = sum(len(p.get("markdown") or "") + 1 for p in pages)
    ext = [t for t in tasks if t.get("answer")]
    inn = [t for t in tasks if t["answer_in"] and not t.get("answer")]
    na = [t for t in tasks if not t.get("answer") and not t["answer_in"]]
    hang = [t for t in tasks if t.get("answer_note") == "похоже на ответ"]
    unit = collections.Counter((t["word"] or "номер без слова").lower() for t in tasks)
    print(f"\n=== {out}")
    print(f"  страниц {len(pages)} | единиц {len(tasks)} ("
          + ", ".join(f"{k} {v}" for k, v in sorted(unit.items(), key=lambda kv: -kv[1]))
          + f") | записей ответа {len(answers)}")
    print("  знаки: " + " + ".join(f"{v} {k}" for k, v in acc.most_common())
          + f" = {sum(acc.values())} из {tot}")
    print(f"  ответ со стр. ответов {len(ext)} | ответ внутри решения {len(inn)} | "
          f"без ответа {len(na)} | похоже на ответ {len(hang)}")
    flags = sum(len(p.get("uncertain") or []) for p in pages)
    got = sum(len(t["uncertain"]) for t in tasks)
    print(f"  с рисунком {sum(1 for t in tasks if t['figures'])} | "
          f"с таблицей Дано {sum(1 for t in tasks if t['dano'])} | "
          f"спорных меток {got} из {flags} привязано к задачам")
    cyr = [t for t in tasks if t["options_cyr"]]
    if cyr:
        print(f"  варианты набраны кириллицей (гомоглифы A-E): {len(cyr)} — "
              + ", ".join(f"{t['word']}{t['num']}" for t in cyr[:10]))
    for label, arr in (("без ответа", na), ("похоже на ответ, решить человеку", hang)):
        if arr:
            print(f"  {label}: {len(arr)}")
            for t in arr[:12]:
                print(f"    {t['word']} {t['num']:>7s} стр {t['pages'][0]:>3d} "
                      f"{t['scope'][:22]:22s} {re.sub(chr(92) + 's+', ' ', t['markdown'])[:44]}")
            if len(arr) > 12:
                print(f"    … ещё {len(arr) - 12}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(a.out, "pages", "*.json")))
    pages = sorted((json.load(io.open(f, encoding="utf-8")) for f in paths), key=lambda p: p["page"])
    by_page = {p["page"]: p for p in pages}

    tasks, answers, other, acc = walk(pages)
    theory = not tasks
    if theory:
        tasks = theory_pages(pages)
        other = [o for o in other if o.get("note")]
    for t in tasks:
        entities(t, by_page)      # chars нужны attach(): свёрнутые знаки уходим в «ответы»
    share_figures(tasks, by_page)
    if theory:
        # знаки этих строк walk() уже отнёс к «вне задач» — переносим и метку, иначе
        # отчёт скажет, что в банк ушли единицы, которых разбор не нашёл
        moved = sum(t["chars"] + 1 for t in tasks)
        acc["вне задач"] -= moved
        acc["задачи"] += moved
    attach(tasks, answers, acc)

    json.dump({"run": os.path.basename(a.out.rstrip("/\\")), "pages": len(pages),
               "tasks": tasks, "other": other,
               "answers": [{"num": k[0], "scope": k[1], "values": v}
                           for k, v in sorted(answers.items())]},
              io.open(os.path.join(a.out, "tasks.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    if not a.quiet:
        report(a.out, pages, tasks, answers, other, acc)
    print(f"  -> {os.path.join(a.out, 'tasks.json')}")


if __name__ == "__main__":
    main()
