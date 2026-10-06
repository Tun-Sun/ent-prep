#!/usr/bin/env python3
"""Превью страниц + out/index.json для стенда.  python index.py --pdf C:/Ocifrovka/скан.pdf"""
import argparse, io, json, os
import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ap = argparse.ArgumentParser()
ap.add_argument("--pdf", default="C:/Ocifrovka/скан.pdf")
ap.add_argument("--out", required=True)
ap.add_argument("--preview-dpi", type=int, default=150)
a = ap.parse_args()

doc = pymupdf.open(a.pdf)
os.makedirs(os.path.join(a.out, "scan"), exist_ok=True)
index = []
for fn in sorted(os.listdir(os.path.join(a.out, "pages"))):
    if not fn.endswith(".json"):
        continue
    p = json.load(io.open(os.path.join(a.out, "pages", fn), encoding="utf-8"))
    n = p["page"]
    if 1 <= n <= doc.page_count:
        rel = f"scan/p{n:02d}.png"
        p["scan"] = rel
        doc[n - 1].get_pixmap(dpi=a.preview_dpi).save(os.path.join(a.out, rel))
    json.dump(p, io.open(os.path.join(a.out, "pages", fn), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    index.append({"page": n, "uncertain": p.get("uncertain") or [], "figures": len(p.get("figures") or []),
                  "chars": len(p.get("markdown") or "")})

index.sort(key=lambda x: x["page"])
json.dump(index, io.open(os.path.join(a.out, "index.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"{len(index)} страниц, превью {a.preview_dpi} dpi -> {a.out}\\index.json")
for i in index:
    print(f"  p{i['page']:02d} {i['chars']:5d} ch | figs {i['figures']} | ? {len(i['uncertain'])}")
