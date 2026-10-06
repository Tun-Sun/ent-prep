#!/usr/bin/env python3
"""Шапка бланка «INTELLECT» вверху каждого листа: название на двух языках, логотип, линейка.

Она не нужна нигде — ни в банке, ни на стенде, ни в отчёте, ни в печатной вёрстке.
Поэтому срезается здесь, на записи страницы, а не по пути к каждому экрану: полоса,
которая осталась в pages/pNN.json, рано или поздно уйдёт в ту поверхность, где её
никто не вычищал.

Модель рисует шапку то в одну строку, то в шесть, то таблицей с пустыми ячейками,
иногда ставит в неё выкроенный логотип. Полосе верим только если в ней действительно
стоит слово бланка: страница, начинающаяся с рисунка задачи, иначе осталась бы без
рисунка. Сырой ответ API лежит в out_*/cache и не трогается — чем модель ответила
на листе видно там, а рабочая запись страницы остаётся чистой.

    python pipeline/letterhead.py                 все прогоны: что режем, не пишем
    python pipeline/letterhead.py --apply         то же + правим pages/*.json, md/, all.md
    python pipeline/letterhead.py --out out_x …   только эти прогоны
"""
import argparse, glob, io, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Лексикон бланка. Строка считается шапкой только когда СЕГОДНЯ все её слова отсюда:
# «центр» сам по себе — слово и из задачи про центр масс.
HEAD_WORDS = {"intellect", "физика-математикалық", "орталығы", "физико-математический",
              "центр", "логотип"}
HEAD_TOKEN = re.compile(r"[A-Za-z\u0400-\u04FF]+(?:-[A-Za-z\u0400-\u04FF]+)*")
RULE = re.compile(r"[-—_]{3,}")
LONE_FIG = re.compile(r"!\[[^\]]*\]\([^)]+\)")
EMPTY_TABLE = re.compile(r"[\s|:\-]+")
FIG = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def head_words(s):
    # дефис держим внутри слова: «физика-математикалық» из двух половин не в лексиконе;
    # <br> моделью разбиты ячейки той же шапки, и тег — не слово бланка
    return [w.lower() for w in HEAD_TOKEN.findall(re.sub(r"<[^>]+>", " ", FIG.sub(" ", s)))]


def band(lines):
    """Сколько строк в начале листа — полоса бланка, 0 если бланка здесь нет.

    Линейка, логотип и пустая табличная заготовка идут и до слова бланка, и после:
    модель рисует шапку то шестью строками, то таблицей, где название сидит в третьей
    ячейке. Поэтому пустые служебные строки расходуем смело, а полосу объявляем только
    если до первой строки содержимого в ней встретилось слово бланка."""
    k, seen = 0, False
    while k < len(lines):
        s = lines[k].strip()
        if (not s or RULE.fullmatch(s) or LONE_FIG.fullmatch(s)
                or ("|" in s and EMPTY_TABLE.fullmatch(FIG.sub(" ", s)))):
            k += 1
            continue
        w = head_words(s)
        if w and all(x in HEAD_WORDS for x in w):
            seen, k = True, k + 1
            continue
        break
    return k if seen else 0


def cut(md, figures=()):
    """(markdown без полосы, сколько строк ушло, выкройки страницы без выкроек бланка).

    Полоса не может съесть лист: если за ней не осталось ни одной значащей строки,
    шапку не нашли — это страница, которая вся из шапки и состоит, и резать её некуда.
    Выкроенный логотип — часть бланка, не рисунок задачи: он уходит из записи вместе
    со своей строкой, иначе «выкроено рисунков» считает центр, а отчёт рамкой укажет
    на шапку."""
    lines = md.split("\n")
    n = band(lines)
    if not n or not any(l.strip() for l in lines[n:]):
        return md, 0, list(figures)
    gone = [os.path.basename(m.group(1)) for l in lines[:n] for m in [FIG.search(l)] if m]
    keep = [f for f in figures if os.path.basename(f.get("file") or "") not in gone]
    return "\n".join(lines[n:]), n, keep


def sweep(out, apply_=False):
    """Один прогон: полоса из pages/*.json (и md/, all.md, index.json следом)."""
    cut_lines = []
    for f in sorted(glob.glob(os.path.join(out, "pages", "*.json"))):
        p = json.load(io.open(f, encoding="utf-8"))
        before = p.get("figures") or []
        md, n, keep = cut(p.get("markdown") or "", before)
        if not n:
            continue
        lines = p["markdown"].split("\n")
        cut_lines.append((out, p["page"], n, sum(len(l) + 1 for l in lines[:n]), lines[:n]))
        if not apply_:
            continue
        p["markdown"] = md
        p["head"] = n                     # в записи страницы видно, что и сколько срезано
        if len(keep) != len(before):
            gone = [x["file"] for x in before if x not in keep]
            p["figures"] = keep
            print(f"    выкройка бланка: {', '.join(gone)} — файл оставили на диске")
        json.dump(p, io.open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        mdp = os.path.join(out, "md", f"p{p['page']:02d}.md")
        if os.path.isfile(mdp):
            io.open(mdp, "w", encoding="utf-8").write(md)

    if not apply_ or not cut_lines:
        return cut_lines

    mds = sorted(glob.glob(os.path.join(out, "md", "*.md")))
    if mds:
        io.open(os.path.join(out, "all.md"), "w", encoding="utf-8").write(
            "\n\n".join(io.open(f, encoding="utf-8").read() for f in mds))

    ip = os.path.join(out, "index.json")
    if os.path.isfile(ip):
        pages = {}
        for f in glob.glob(os.path.join(out, "pages", "*.json")):
            p = json.load(io.open(f, encoding="utf-8"))
            pages[p["page"]] = (len(p["markdown"]), len(p.get("figures") or []))
        idx = json.load(io.open(ip, encoding="utf-8"))
        for row in idx:
            if row["page"] in pages:
                row["chars"], row["figures"] = pages[row["page"]]
        json.dump(idx, io.open(ip, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return cut_lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", action="append", default=[], help="папка прогона, повторимо")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    outs = a.out or sorted(d for d in glob.glob(os.path.join(ROOT, "out*")) if os.path.isdir(d))

    total = []
    for out in outs:
        for run, page, n, chars, lines in sweep(out, a.apply):
            total.append((run, page, n))
            print(f"{os.path.basename(run)} p{page:02d}: срезаем {n} строк, {chars} знаков")
            for l in lines:
                print(f"    |{l[:100]}")
    if not total:
        print("шапки бланка нигде нет")
        return
    print(f"\n{'правлено' if a.apply else 'найдено'}: {len(total)} страниц, "
          f"{sum(n for _, _, n in total)} строк полосы")
    if not a.apply:
        print("ничего не записано — с --apply")


if __name__ == "__main__":
    sys.exit(main())
