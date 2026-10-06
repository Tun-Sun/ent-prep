#!/usr/bin/env python3
"""Сколько страниц свёрстано array/cline вместо markdown-таблицы."""
import io, json, os, re, sys

RX = re.compile(r"\\begin\{array\}")
BAD = re.compile(r"\\cline|\\hfill|\\begin\{tabular|\\begin\{align|\\begin\{equation")
ROW = re.compile(r"^\|.*\|\s*$", re.M)

for out in sys.argv[1:] or ["out_v2", "out_b"]:
    hits = []
    for fn in sorted(os.listdir(os.path.join(out, "pages"))):
        if not fn.endswith(".json"):
            continue
        d = json.load(io.open(os.path.join(out, "pages", fn), encoding="utf-8"))
        md = d["markdown"]
        a, b, t = len(RX.findall(md)), len(BAD.findall(md)), len(ROW.findall(md))
        if a or b:
            hits.append((d["page"], a, b, t))
    print(out, "страниц с array/cline:", hits, "всего запрещённого:", sum(h[1] + h[2] for h in hits))
