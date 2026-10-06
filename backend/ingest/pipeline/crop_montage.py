#!/usr/bin/env python3
"""Монтаж всех выкроек прогона в один лист — чтобы смотреть глазами, а не метриками.
python crop_montage.py ../out_v2 ../out_b"""
import json, io, os, sys
from PIL import Image, ImageDraw

for out in sys.argv[1:] or ["../out_v2"]:
    items = []
    for fn in sorted(os.listdir(os.path.join(out, "pages"))):
        if not fn.endswith(".json"):
            continue
        d = json.load(io.open(os.path.join(out, "pages", fn), encoding="utf-8"))
        for f in (d.get("figures") or []):
            p = os.path.join(out, f["file"])
            if os.path.exists(p):
                items.append((f"p{d['page']:02d} {f['id']}", Image.open(p).convert("RGB")))
    if not items:
        print(f"{out}: выкроек нет"); continue
    COLS, CELL = 4, 460
    rows = (len(items) + COLS - 1) // COLS
    sheet = Image.new("RGB", (COLS * CELL, rows * (CELL + 22)), "white")
    dr = ImageDraw.Draw(sheet)
    for i, (label, im) in enumerate(items):
        k = min(CELL / im.width, CELL / im.height)
        im = im.resize((int(im.width * k), int(im.height * k)))
        x, y = (i % COLS) * CELL, (i // COLS) * (CELL + 22)
        sheet.paste(im, (x + (CELL - im.width) // 2, y + 22 + (CELL - im.height) // 2))
        dr.rectangle([x, y + 18, x + CELL - 4, y + CELL + 18], outline=(220, 220, 220))
        dr.text((x + 6, y + 4), label, fill=(200, 30, 30))
    rel = os.path.join(out, "montage.png")
    sheet.save(rel)
    print(f"{rel}: {len(items)} выкроек, {rows} рядов")
