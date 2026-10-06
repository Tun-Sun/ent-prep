#!/usr/bin/env python3
"""run.json — чем был прогон: файл, хэш, dpi, модель, промпт, код.

  python pipeline/manifest.py --out out_kasatkina_em

Считает с диска всё, что пересобирается: источник (хэш, есть ли текстовый слой, какой
растр реально лежит под страницей), рендер (dpi и пиксели страницы из pages/*.json),
превью (scan/*.png — они всегда дешевле страниц, и это надо видеть, а не помнить),
ключи кэша и коммит кода. Секцию `used` не трогает: её в момент вызова пишет ocr.py,
и её из диска не восстановить — промпт после прогона правят.
"""
import argparse, glob, hashlib, io, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def sha16(b):
    return hashlib.sha256(b).hexdigest()[:16]


def src_facts(src):
    """Эффективный dpi считаем по тому, сколько пикселей реально лежит под прямоугольником
    страницы: 668 px на 4.46 дюйма = 150 dpi, и рендер на 300 dpi информации не добавит."""
    if not os.path.isfile(src):
        return {"src": src, "note": "источник не найден с текущего момента"}
    b = open(src, "rb").read()
    f = {"src": src, "bytes": len(b), "sha256": sha16(b)}
    if not src.lower().endswith(".pdf"):
        f["kind"] = "не PDF"
        return f
    import pymupdf
    d = pymupdf.open(src)
    f["pages_in_file"] = d.page_count
    chars = 0
    dpi = []
    raster_pages = 0
    drawings = 0
    for p in d:
        chars += len(p.get_text().strip())
        drawings += len(p.get_drawings())
        area = max(p.rect.width * p.rect.height, 1)
        cov, best_frac, best_px, best_w = 0.0, 0.0, 0, 0.0
        for x in p.get_images(full=True):
            try:
                im = d.extract_image(x[0])
                rs = p.get_image_rects(x[0])
            except Exception:
                continue
            if not rs:
                continue
            r = max(rs, key=lambda q: q.width * q.height)
            frac = r.width * r.height / area
            cov += frac
            if frac > best_frac:
                best_frac, best_px, best_w = frac, im["width"], r.width
        # страница скана бывает набрана несколькими картинками-полосами (5.2: четыре
        # куска по 7–20 %), поэтому считаем суммарное покрытие, а dpi — по крупнейшему.
        # Две цифры намеренно: плотность самих пикселей (деля на прямоугольник вставки)
        # и разрешение относительно листа (деля на ширину страницы). На скан.pdf они
        # расходятся вдвое — 76 и 56, — и спор «какое dpi у скана» был именно из-за этого.
        if cov >= 0.1:
            raster_pages += 1
            dpi.append((p.number + 1, round(best_px / max(best_w / 72.0, 1e-6)),
                        round(best_px / (p.rect.width / 72.0))))
    n = max(d.page_count, 1)
    f["text_layer_chars"] = chars
    f["text_chars_per_page"] = round(chars / n)
    f["vector_paths"] = drawings
    f["pages_with_raster"] = raster_pages
    f["raster_dpi"] = [min(v for _, v, _ in dpi), max(v for _, v, _ in dpi)] if dpi else []
    f["raster_dpi_vs_page"] = [min(w for _, _, w in dpi), max(w for _, _, w in dpi)] if dpi else []
    f["raster_dpi_by_page"] = {str(pg): [v, w] for pg, v, w in dpi}
    # цифровой вёрстке растр размером со страницу не нужен — у неё шрифты и вектор.
    # Если растр есть, текст под ним это OCR, а не оригинал: проверено на Касаткиной —
    # «F о» вместо F₀ и «q„» вместо q₀ в слое, при этом скан 150 dpi.
    text = chars > 200 * n
    half = raster_pages >= n / 2
    f["kind"] = ("скан + текстовый слой (OCR)" if text and half else
                 "цифровая вёрстка: текст + вектор" if text and drawings else
                 "цифровой текст, векторных рисунков нет" if text else
                 "скан: страницы — растр" if half else "смешанный")
    return f


def render_facts(out):
    """Что говорили страницы про себя: dpi, модель, размер — из pages/*.json, не из памяти."""
    dpi, model, px, pages, cached = set(), set(), set(), [], 0
    for fn in sorted(glob.glob(os.path.join(out, "pages", "p*.json"))):
        p = json.load(io.open(fn, encoding="utf-8"))
        pages.append(p.get("page"))
        if p.get("dpi"):
            dpi.add(p["dpi"])
        if p.get("model"):
            model.add(p["model"])
        if p.get("size_px"):
            px.add(tuple(p["size_px"]))
        cached += bool(p.get("cached"))
    return {"pages": len(pages), "page_numbers": [min(pages), max(pages)] if pages else [],
            "dpi": sorted(dpi), "model": sorted(model), "page_px": [list(t) for t in px],
            "from_cache": cached}


def preview_facts(out, rend):
    png = os.path.join(out, "scan", "p01.png")
    if not os.path.isfile(png):
        return {"note": "scan/ нет — превью не собирались"}
    from PIL import Image
    w, h = Image.open(png).size
    one = (rend.get("page_px") or [[None, None]])[0]
    out_ = {"preview_px": [w, h]}
    if one[0] and rend.get("dpi"):
        d = rend["dpi"][0]
        out_["preview_dpi"] = round(w * d / one[0])
        out_["ratio_to_pages"] = round(one[0] / w, 2)
    return out_


def cache_keys(out):
    keys = {}
    for fn in sorted(glob.glob(os.path.join(out, "cache", "p*.json"))):
        base = os.path.basename(fn)
        page, _, h = base[:-5].rpartition("_")
        keys[page] = h
    return keys


def code_facts():
    def git(*args):
        try:
            r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
            return r.stdout.strip() if r.returncode == 0 else ""
        except Exception:
            return ""
    import platform
    try:
        import pymupdf
        pm = getattr(pymupdf, "VersionBind", "")
    except Exception:
        pm = ""
    return {"commit": git("rev-parse", "--short", "HEAD"),
            "dirty": bool(git("status", "--porcelain")), "python": platform.python_version(),
            "pymupdf": pm}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--pdf", default="", help="источник; по умолчанию берём из run.json или pages/")
    a = ap.parse_args()
    out = a.out if os.path.isabs(a.out) else os.path.join(ROOT, a.out)
    path = os.path.join(out, "run.json")
    old = {}
    if os.path.isfile(path):
        try:
            old = json.load(io.open(path, encoding="utf-8"))
        except Exception:
            print(f"  {path} не читается — пишу заново", flush=True)
            old = {}
    rend = render_facts(out)
    # источник прогона важнее источника, названного в командной строке сегодня:
    # вчерашний прогон делался по другому файлу, а манифест описывает прогон, не вызов
    src = (old.get("used") or {}).get("src") or a.pdf
    m = {"written": time.strftime("%Y-%m-%dT%H:%M:%S"),
         "out": os.path.basename(out), "source": src_facts(src) if src else {"note": "источник неизвестен"},
         "render": rend, "views": preview_facts(out, rend), "cache": cache_keys(out),
         "code": code_facts(), "used": old.get("used")}
    if not m["used"]:
        m["used"] = {"note": "прогон был до манифеста: хэш промпта в момент вызова не записан, "
                             "привязать его к этому прогону нельзя"}
    json.dump(m, io.open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    s = m["source"]
    print(f"run.json -> {path}")
    print(f"  {s.get('kind','?')} | хэш {s.get('sha256','—')} | страниц в файле {s.get('pages_in_file','?')} | "
          f"текст {s.get('text_chars_per_page','?')} зн./стр. | векторных путей {s.get('vector_paths','?')} | "
          f"растр {s.get('raster_dpi','—')} dpi (против листа {s.get('raster_dpi_vs_page','—')}) "
          f"на {s.get('pages_with_raster','?')} стр.")
    print(f"  рендер {rend['dpi']} dpi, страниц {rend['pages']}, моделей {rend['model']}, из кэша {rend['from_cache']} | "
          f"превью {m['views'].get('preview_px', '—')} ({m['views'].get('preview_dpi','?')} dpi, ×{m['views'].get('ratio_to_pages','?')})")
    print(f"  код {m['code']['commit']}{' (грязный)' if m['code']['dirty'] else ''} | "
          f"промпт {'записан в момент вызова: ' + m['used'].get('prompt_sha256','') if m['used'].get('prompt_sha256') else 'не привязан'}")


if __name__ == "__main__":
    main()
