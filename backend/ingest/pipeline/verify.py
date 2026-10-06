#!/usr/bin/env python3
"""Вторая модель читает те же страницы и сравнивает с основным прогоном.

Зачем: uncertain-список — это самоотчёт модели, он не показывает то, в чём модель
уверена ложно. Расхождение двух разных моделей показывает.

  python verify.py --pages 1-18 --main out_v2 --other gemini-2.5-flash --check out_x
"""
import argparse, io, json, os, re, subprocess, sys
import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from texnorm import norm  # та же нормализация, что и при сверке с эталоном

ap = argparse.ArgumentParser()
ap.add_argument("--pdf", default="C:/Ocifrovka/скан.pdf")
ap.add_argument("--pages", default="1-18")
ap.add_argument("--main", default=os.path.join(ROOT, "out_v2"))
ap.add_argument("--other", default="gemini-2.5-flash")
ap.add_argument("--check", default=os.path.join(ROOT, "out_x"))
ap.add_argument("--prompt-extra", default=os.path.join(HERE, "prompt_uncertain.md"))
ap.add_argument("--workers", type=int, default=5)
a = ap.parse_args()

# 1. прогон второй модели (ocr.py сам пропустит уже закэшированные страницы)
cmd = [sys.executable, os.path.join(HERE, "ocr.py"), "--pages", a.pages, "--model", a.other,
       "--out", a.check, "--workers", str(a.workers), "--pdf", a.pdf]
if a.prompt_extra:
    cmd += ["--prompt-extra", a.prompt_extra]
print("$ " + " ".join(os.path.basename(x) if x.startswith(HERE) else x for x in cmd), flush=True)
subprocess.run(cmd, check=False)

# 2. сравнение по страницам
def load(d, n):
    p = os.path.join(d, "pages", f"p{n:02d}.json")
    return json.load(io.open(p, encoding="utf-8")) if os.path.isfile(p) else None

def units(md):
    """Страница -> список смысловых кусков. Картинки убираем ДО нарезки:
    в путях и подписях есть точки, они рвут предложения на куски."""
    out = []
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", md)
    for line in md.split("\n"):
        line = line.strip()
        if not line or set(line) <= set("-|: "):
            continue
        for u in re.split(r"(?<=[.!?])\s+(?=[А-Яа-яA-Za-z0-9$])", line):
            u = u.strip()
            if len(norm(u)) >= 18:
                out.append(u)
    return out

pages, rows = [], []
for n in sorted({int(x) for x in re.findall(r"p(\d+)\.json", " ".join(os.listdir(os.path.join(a.main, "pages"))))}):
    m, c = load(a.main, n), load(a.check, n)
    if not m or not c:
        continue
    M, C = norm(m["markdown"]), norm(c["markdown"])
    # fragment в uncertain — короткий LaTeX, а не всё предложение: ищем его ВНУТРИ куска
    frags = [norm(u.get("fragment", "")) for u in (m.get("uncertain") or []) if u.get("fragment")]
    frags = [f for f in frags if len(f) >= 2]

    def marked(u):
        n = norm(u)
        return any(f in n for f in frags)

    diffs = []
    for u in units(m["markdown"]):
        if norm(u) not in C:
            alt = next((x for x in units(c["markdown"]) if norm(x)[:40] and norm(x)[:40] in M), "")
            diffs.append((u, alt, "помечено" if marked(u) else "МОЛЧИТ"))
    for u in units(c["markdown"]):
        if norm(u) not in M:
            diffs.append(("", u, "помечено" if marked(u) else "МОЛЧИТ"))
    pages.append((n, len(units(m["markdown"])), len(diffs)))
    rows += [(n, x, y, s) for x, y, s in diffs]

tot_u = sum(p[1] for p in pages)
silent = sum(1 for r in rows if r[3] == "МОЛЧИТ")
if not tot_u:
    sys.exit("расхождений не посчитано: обе стороны пусты — проверь, что прогоны состоялись")
print(f"\n=== расхождения двух моделей: {a.other} против основной ===")
print(f"кусков текста сравнено: {tot_u} · расхождений: {len(rows)} "
      f"({len(rows)/tot_u*100:.1f}%) · из них НЕ помечено моделью: {silent}")
for n, u, c, s in rows:
    print(f"\n[стр {n}] {s}")
    print("  основной:", (u or "—")[:170])
    print("  второй  :", (c or "—")[:170])

json.dump({"rows": rows, "pages": pages, "other": a.other},
          io.open(os.path.join(a.main, "diff.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\n-> {a.main}\\diff.json")
