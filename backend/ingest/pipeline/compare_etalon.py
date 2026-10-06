#!/usr/bin/env python3
"""Сверка распознанного текста с Эталон.pdf.  python compare_etalon.py [--dir out_v2]"""
import argparse, io, json, os, re
import pymupdf
from texnorm import norm

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ap = argparse.ArgumentParser()
ap.add_argument("--dir", default=os.path.join(ROOT, "out"))
ap.add_argument("--etalon", default="C:/Ocifrovka/Эталон.pdf")
a = ap.parse_args()

etalon_raw = "\n".join(p.get_text() for p in pymupdf.open(a.etalon))
e_lines = [norm(l) for l in etalon_raw.split("\n") if len(norm(l)) > 25]

d = os.path.join(a.dir, "pages")
got = [json.load(io.open(os.path.join(d, f), encoding="utf-8"))["markdown"]
       for f in sorted(os.listdir(d)) if f.endswith(".json")]
g_norm = norm("\n".join(got))

misses = [l for l in e_lines if l not in g_norm]
hit = len(e_lines) - len(misses)
print(f"{os.path.basename(a.dir.rstrip(os.sep))}: строк эталона {len(e_lines)}, "
      f"найдено {hit} ({hit/len(e_lines)*100:.1f}%), не найдено {len(misses)}")
for m in misses:
    print(" •", m[:150])
