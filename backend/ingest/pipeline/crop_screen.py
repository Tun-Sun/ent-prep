#!/usr/bin/env python3
"""Экран качества выкроек: насколько вырезанный рисунок похож на текст.
Высокая «текстовость» = в рамку попала строка условия, а не чертёж.  python crop_screen.py out_v2 out_b"""
import io, json, os, sys
import numpy as np
import bbox_fix

for out in sys.argv[1:] or ["out_v2", "out_b"]:
    rows = []
    for fn in sorted(os.listdir(os.path.join(out, "pages"))):
        if not fn.endswith(".json"):
            continue
        d = json.load(io.open(os.path.join(out, "pages", fn), encoding="utf-8"))
        for f in (d.get("figures") or []):
            path = os.path.join(out, f["file"])
            if not os.path.exists(path):
                rows.append((d["page"], f["id"], None, None, f["kind"], "нет файла"))
                continue
            g = bbox_fix.gray_of(io.open(path, "rb").read())
            t = bbox_fix.textiness(g)
            ink = float((g < 128).mean())
            rows.append((d["page"], f["id"], t, ink, f.get("kind", ""), f["file"]))
    bad = [r for r in rows if r[2] is None or r[2] > bbox_fix.FIG_MAX]
    print(f"== {out}: выкроек {len(rows)}, из них подозрительных {len(bad)}")
    for p, i, t, ink, kind, f in sorted(rows, key=lambda r: -(r[2] if r[2] is not None else 9)):
        mark = "  <<<" if (t is None or t > bbox_fix.FIG_MAX) else ""
        ts = "нет" if t is None else f"{t:.2f}"
        ins = "—" if ink is None else f"{ink:.3f}"
        print(f"   p{p:02d} {i:<6} текстовость {ts} · чернил {ins} · {kind:<12}{mark}")
