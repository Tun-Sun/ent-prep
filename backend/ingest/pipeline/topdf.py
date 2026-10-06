#!/usr/bin/env python3
"""Собрать PDF из отрендеренного KaTeX: print.html -> headless Chrome.

  python pipeline/topdf.py --out out_b --name "оцифровано_6.1_МКТ"
"""
import argparse, os, subprocess, sys, tempfile

BROWSERS = [
    r"C:/Program Files/Google/Chrome/Application/chrome.exe",
    r"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    r"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
]

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--name", default="оцифровано")
ap.add_argument("--browser", default="")
a = ap.parse_args()

# как в report.py/ocr.py: путь относительно текущего каталога, а не от корня репозитория
out = os.path.abspath(a.out)
html = os.path.join(out, "print.html")
if not os.path.isfile(html):
    sys.exit(f"нет {html} — сначала: python pipeline/report.py --out {a.out} --print")

chrome = next((b for b in ([a.browser] if a.browser else BROWSERS) if b and os.path.isfile(b)), None)
if not chrome:
    sys.exit("не найден Chrome/Edge")

pdf = os.path.join(out, a.name + ".pdf")
profile = os.path.join(tempfile.gettempdir(), "qoder-pdf-profile")
cmd = [chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
       "--virtual-time-budget=40000", f"--user-data-dir={profile}",
       f"--print-to-pdf={pdf}", "file:///" + html.replace("\\", "/")]
r = subprocess.run(cmd, capture_output=True, text=True)
if not os.path.isfile(pdf):
    sys.exit(f"Chrome не создал PDF: {r.stderr[-400:]}")

import pymupdf
d = pymupdf.open(pdf)
txt = "".join(p.get_text() for p in d)
katex = sum(1 for p in d if any("KaTeX" in f[3] for f in p.get_fonts()))
print(f"{a.out}\\{a.name}.pdf: {d.page_count} листов, {round(os.path.getsize(pdf)/1024)} КБ, "
      f"{len(txt)} знаков текстового слоя, листов с KaTeX {katex}, "
      f"незакрытых $ {txt.count('$')}, ошибок рендера {txt.count('ParseError')}")
