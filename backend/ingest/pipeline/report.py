#!/usr/bin/env python3
"""Отчёт «было / распознано / отрендерено» по результатам ocr.py.  python report.py [--pages 2-5]"""
import argparse, io, json, os
from html import escape
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--pages", default="")
ap.add_argument("--no-src", action="store_true", help="две колонки: скан и рендер, без исходника")
ap.add_argument("--tag", default="", help="приписать к имени файла отчёта")
ap.add_argument("--print", dest="print_mode", action="store_true",
                help="одноколоночная вёрстка A4 для печати в PDF: только отрендеренный KaTeX")
a = ap.parse_args()

idx = json.load(io.open(os.path.join(a.out, "index.json"), encoding="utf-8"))
want = None
if a.pages:
    import ocr
    want = ocr.parse_pages(a.pages)

# рамка выкроенного рисунка прямо на превью страницы — иначе не проверить, туда ли резали
marked = 0
for row in idx if not a.print_mode else []:
    if want and row["page"] not in want:
        continue
    p = json.load(io.open(os.path.join(a.out, "pages", f"p{row['page']:02d}.json"), encoding="utf-8"))
    # ocr.py при перезаписи страницы теряет scan — восстанавливаем по имени файла
    scan = p.get("scan") or f"scan/p{row['page']:02d}.png"
    if not p.get("figures") or not os.path.exists(os.path.join(a.out, scan)):
        continue
    src = os.path.join(a.out, scan)
    im = Image.open(src).convert("RGB")
    W, H = im.size
    d = ImageDraw.Draw(im)
    sw = max(2, round(W / 500))
    for f in p["figures"]:
        x0, y0, x1, y1 = f["px"]
        sx, sy = W / p["size_px"][0], H / p["size_px"][1]
        box = [x0 * sx, y0 * sy, x1 * sx, y1 * sy]
        d.rectangle(box, outline=(200, 30, 30), width=sw)
        d.text((box[0] + 4, max(0, box[1] - 16)), f["id"], fill=(200, 30, 30))
    rel = f"marked/p{p['page']:02d}.png"
    os.makedirs(os.path.join(a.out, "marked"), exist_ok=True)
    im.save(os.path.join(a.out, rel))
    p["marked"] = rel
    marked += 1
    json.dump(p, io.open(os.path.join(a.out, "pages", f"p{p['page']:02d}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

pages = []
for row in idx:
    if want and row["page"] not in want:
        continue
    pages.append(json.load(io.open(os.path.join(a.out, "pages", f"p{row['page']:02d}.json"), encoding="utf-8")))

tot = dict(chars=sum(len(p["markdown"]) for p in pages), figs=sum(len(p.get("figures") or []) for p in pages),
           unc=sum(len(p.get("uncertain") or []) for p in pages))

# истинный размер выкройки в мм: пиксели кадра делим на dpi страницы, которой кадр нарезан.
# 544 px при 300 dpi = 46 мм — ровно столько чертёж занимает на листе скана.
fig_mm = {}
for p in pages:
    for f in p.get("figures") or []:
        px, dpi = f.get("px"), p.get("dpi") or 300
        if px:
            fig_mm[os.path.basename(f["file"])] = round((px[2] - px[0]) * 25.4 / dpi, 1)
FW = f'<script id="fw" type="application/json">{json.dumps(fig_mm)}</script>'
SIZE_IMG = """const FW=JSON.parse(document.getElementById('fw').textContent);
document.querySelectorAll('.r img').forEach(i=>{const w=FW[i.getAttribute('src').split('/').pop()];
  if(w){i.style.width=w+'mm';i.style.maxWidth='100%';}});"""

if a.print_mode:
    io.open(os.path.join(a.out, "print.html"), "w", encoding="utf-8").write("""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>Оцифровано</title><link rel="stylesheet" href="../web/vendor/katex/katex.min.css"><style>
@page{size:A4;margin:12mm 12mm}
body{margin:0;font:10.5pt/1.4 "Times New Roman",serif;color:#000}
.pg{page-break-after:always}
.pg:last-child{page-break-after:auto}
h2{font:600 8pt system-ui;color:#8a94a6;text-align:right;margin:0 0 6pt}
h1,h3{font-family:system-ui}
p{margin:0 0 3.5pt;text-align:justify}
img{display:inline-block;margin:4pt 1% 4pt 0;vertical-align:top}
table{border-collapse:collapse;margin:5pt auto;font-size:9.5pt}
th,td{border:1px solid #666;padding:2pt 6pt;text-align:center}
th{background:#f0f2f5}
/* авто-раскладка сжимает «Дано» до min-content, и значения рвёт на две строки.
   >*>tr, а не >tr: парсер вставляет tbody/thead, table>tr не матчится.
   table-layout:fixed не нужен — замер в headless Chrome: широкая формула 363px в колонке 380px. */
table:has(tr>*:nth-child(2):last-child)>*>tr>*{vertical-align:top}
table:has(tr>*:nth-child(2):last-child)>*>tr>*:first-child{width:30%;padding-right:3mm}
.katex{font-size:1em}
.katex-display{margin:5pt 0}
.katex-error{color:#b42318!important;background:#fee4e2}
</style></head><body>"""
        + "".join(f'<section class="pg"><h2>стр. {p["page"]}</h2><div class="r">{escape(p["markdown"])}</div></section>'
                  for p in pages)
        + FW + """<script src="../web/vendor/katex/katex.min.js"></script>
<script src="../web/vendor/katex/auto-render.min.js"></script>
<script src="../web/vendor/marked.min.js"></script>
<script src="../web/md-math.js"></script>
<script>
document.querySelectorAll('.r').forEach(el=>{
  el.innerHTML = mdToHtml(el.textContent);
  renderMathInElement(el,{delimiters:[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false}],
    throwOnError:false, strict:false, trust:false, maxSize:60});
});
""" + SIZE_IMG + """
// одна страница скана = один лист. Если контент не влезает — ужимаем секцию, а не режем на два листа.
// Только после load: без размеров картинок высота секции меньше листа, и подгонка промахивается.
const AVAIL = Math.round((297 - 24) * 96 / 25.4);
const fit = () => document.querySelectorAll('.pg').forEach(el => {
  el.style.zoom = 1;
  for (let i = 0; i < 6; i++) {
    const h = el.getBoundingClientRect().height;
    if (h <= AVAIL + 1) break;
    el.style.zoom = Math.max(0.7, (parseFloat(el.style.zoom) || 1) * (AVAIL - 2) / h);
  }
});
(document.readyState === 'complete' ? Promise.resolve() : new Promise(r => addEventListener('load', r)))
  .then(() => document.fonts.ready).then(fit);
</script></body></html>""")
    print(f"{a.out}\\print.html: {len(pages)} стр., {tot['chars']} знаков — для печати в PDF")
    raise SystemExit(0)

html = ["""<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Отчёт оцифровки</title>
<link rel="stylesheet" href="../web/vendor/katex/katex.min.css"><style>
body{margin:0;font:15px/1.6 "Times New Roman",serif;color:#1a202c;background:#f6f8fa}
header{position:sticky;top:0;background:#fff;border-bottom:1px solid #d8dee6;padding:10px 20px;font:13px system-ui}
.pg{background:#fff;border:1px solid #d8dee6;border-radius:8px;margin:18px;padding:16px 20px}
.pg h2{font:600 15px system-ui;margin:0 0 10px;border-bottom:1px solid #eee;padding-bottom:6px}
.three{display:grid;grid-template-columns:minmax(240px,1fr) minmax(240px,1fr) minmax(320px,1.3fr);gap:14px}
.three.two{grid-template-columns:minmax(340px,1fr) minmax(420px,1.05fr)}
.c{border:1px solid #e5e9f0;border-radius:6px;padding:10px;overflow:auto;max-height:760px}
.c h4{margin:0 0 8px;font:600 10px system-ui;letter-spacing:.07em;text-transform:uppercase;color:#667085}
.c img{max-width:100%}
pre{margin:0;white-space:pre-wrap;word-break:break-word;font:11.5px/1.55 ui-monospace,Consolas,monospace}
table{border-collapse:collapse;font-size:13.5px}th,td{border:1px solid #9aa5b1;padding:4px 8px;text-align:center}
th{background:#eef2f7}.katex-error{color:#b42318!important;background:#fee4e2}
.sum{display:flex;gap:18px;font:13px system-ui;margin-left:12px}
.unc{margin-top:12px;border:1px solid #f0c27b;background:#fffbf2;border-radius:6px;padding:8px 12px;font:13px system-ui}
.unc summary{cursor:pointer;font-weight:600;color:#8a5a00}
.unc table{margin:10px 0 4px;width:100%;font-size:13px}
.unc th,.unc td{border:1px solid #ecd9b3;padding:4px 8px;text-align:left;vertical-align:top}
.unc th{background:#fdf3e0;font-weight:600}
.unc code{font:12px ui-monospace,Consolas,monospace;background:#fff;padding:1px 4px;border-radius:3px}
</style></head><body>"""]
html.append(f"<header><b>Отчёт оцифровки</b> · {len(pages)} стр. · знаков {tot['chars']} · "
            f"рисунков выкроено {tot['figs']} · спорных мест {tot['unc']}"
            f"<span class='sum'>модель {pages[0]['model']} · {pages[0]['dpi']} dpi</span></header>")

for p in pages:
    html.append(f'<section class="pg"><h2>Страница {p["page"]}</h2>'
                f'<div class="three{" two" if a.no_src else ""}">')
    img = p.get("marked") or p.get("scan") or f"scan/p{p['page']:02d}.png"
    html.append(f'<div class="c"><h4>Было (скан + рамки вырезок)</h4>'
                + (f'<img src="{img}">' if os.path.exists(os.path.join(a.out, img)) else "нет превью") + "</div>")
    if not a.no_src:
        html.append(f'<div class="c"><h4>Распознано (исходник)</h4><pre>{escape(p["markdown"])}</pre></div>')
    html.append(f'<div class="c"><h4>Отрендерено (KaTeX)</h4><div class="r">{escape(p["markdown"])}</div></div>')
    html.append("</div>")
    u = p.get("uncertain") or []
    if u:
        html.append(f'<details class="unc" open><summary>Спорных мест: {len(u)} — сверить со сканом</summary><table>'
                    "<tr><th>где</th><th>записано</th><th>может быть</th><th>почему сомнительно</th></tr>"
                    + "".join(f"<tr><td>{escape(x.get('where',''))}</td><td><code>{escape(x.get('fragment',''))}</code></td>"
                              f"<td><code>{escape(x.get('alt',''))}</code></td><td>{escape(x.get('why',''))}</td></tr>"
                              for x in u)
                    + "</table></details>")
    html.append("</section>")

html.append(FW + """<script src="../web/vendor/katex/katex.min.js"></script>
<script src="../web/vendor/katex/auto-render.min.js"></script>
<script src="../web/vendor/marked.min.js"></script>
<script src="../web/md-math.js"></script>
<script>
document.querySelectorAll('.r').forEach(el=>{
  el.innerHTML = mdToHtml(el.textContent);
  renderMathInElement(el,{delimiters:[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false}],
    throwOnError:false, strict:false, trust:false, maxSize:60});
});
""" + SIZE_IMG + "</script></body></html>")

fn = "report" + (f"_{a.tag}" if a.tag else "") + ".html"
io.open(os.path.join(a.out, fn), "w", encoding="utf-8").write("\n".join(html))
print(f"{a.out}\\{fn}: {len(pages)} стр., {tot['chars']} знаков, {tot['figs']} рисунков, "
      f"рамок наложено {marked}, спорных мест {tot['unc']}")
