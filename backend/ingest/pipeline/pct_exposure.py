#!/usr/bin/env python3
"""Сколько формул содержат backslash-экраники, которые marked съедает (\\%, \\_, \\{, \\&, ...)."""
import io, json, os, re, sys

RX = re.compile(r"\$\$([\s\S]+?)\$\$|\$([^$\n]+?)\$", re.M)
BAD = re.compile(r"\\([%_{}&~|<>+*.!#-])")   # то, что marked считает markdown-экраником

for d in sys.argv[1:]:
    hits, tot = [], 0
    for f in sorted(os.listdir(os.path.join(d, "pages"))):
        if not f.endswith(".json"):
            continue
        md = json.load(io.open(os.path.join(d, "pages", f), encoding="utf-8"))["markdown"]
        for m in RX.finditer(md):
            tot += 1
            t = m.group(1) or m.group(2)
            if BAD.search(t):
                hits.append((f, t[:70]))
    print(f"{d}: формул {tot}, под ударом marked {len(hits)}")
    for f, t in hits[:8]:
        print("   ", f, "|", t)
