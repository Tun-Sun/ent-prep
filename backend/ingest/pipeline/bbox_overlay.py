#!/usr/bin/env python3
"""Рисует на странице оба варианта расшифровки bbox: красный = x-первая, зелёный = y-первая.
Страница -> out_v2/probe/pXX.png, чтобы решить глазами, какая конвенция у модели."""
import io, json, os, sys
import pymupdf
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = "C:/Ocifrovka/скан.pdf"
OUT = os.path.join(ROOT, "out_v2/probe")
os.makedirs(OUT, exist_ok=True)
DPI = int(sys.argv[2]) if len(sys.argv) > 2 else 150

doc = pymupdf.open(PDF)
for spec in sys.argv[1].split(","):
    n = int(spec)
    d = json.load(io.open(os.path.join(ROOT, "out_v2/pages", f"p{n:02d}.json"), encoding="utf-8"))
    pm = doc[n - 1].get_pixmap(dpi=DPI)
    im = Image.frombytes("RGB", (pm.width, pm.height), pm.samples).convert("RGB")
    dr = ImageDraw.Draw(im)
    W, H = im.size
    for f in d.get("figures") or []:
        b = f.get("bbox")
        if not b or len(b) != 4:
            continue
        a0, a1, a2, a3 = [float(v) / 1000 for v in b]
        dr.rectangle((a0 * W, a1 * H, a2 * W, a3 * H), outline=(220, 0, 0), width=3)
        dr.rectangle((a1 * W, a0 * H, a3 * W, a2 * H), outline=(0, 170, 0), width=3)
        dr.text((a0 * W + 4, a1 * H + 4), f"{f['id']} XY", fill=(220, 0, 0))
        dr.text((a1 * W + 4, a0 * H + 4), f"{f['id']} YX", fill=(0, 150, 0))
    p = os.path.join(OUT, f"p{n:02d}.png")
    im.save(p)
    print(p)
