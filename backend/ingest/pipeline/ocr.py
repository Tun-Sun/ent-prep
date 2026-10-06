#!/usr/bin/env python3
"""Страницы пособия -> Gemini Flash -> Markdown с KaTeX + выкройки рисунков.

  python ocr.py --pdf C:/Ocifrovka/скан.pdf --pages 2-5 --out out_x
  python ocr.py --pages-dir pages --only 6 --out out_x
  python ocr.py ... --price-in 10 --price-out 60    ставка за млн токенов, для денег

Учёт расходов — в out_*/usage.json, он накапливается между прогонами папки:
кэш повторных вызовов денег не стоит, а ретраи и упавшие страницы стоят.
"""
import argparse, base64, concurrent.futures as cf, hashlib, io, json, os, re, sys, threading, time, urllib.error, urllib.request

import letterhead

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
API = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}


def read_key(path):
    for p in (path, os.path.join(HERE, "key.txt"), "C:/Ocifrovka/key.txt"):
        if p and os.path.isfile(p):
            return open(p, encoding="utf-8").read().strip()
    sys.exit("API key not found: pass --key-file")


class CallFailed(RuntimeError):
    """Вызов не удался. attempts нужен учёту: таймаут после готового ответа
    (500/504, обрыв соединения) токены уже потратил, а страницы мы не получили."""

    def __init__(self, msg, attempts):
        super().__init__(msg)
        self.attempts = attempts


def call(model, key, img_bytes, prompt, max_tokens, retries=4):
    body = {
        "contents": [{"role": "user", "parts": [
            {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(img_bytes).decode()}},
            {"text": prompt},
        ]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": max_tokens,
                             "responseMimeType": "application/json", "responseSchema": SCHEMA},
    }
    url = API.format(m=model)
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"x-goog-api-key": key, "content-type": "application/json"})
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read()), attempt + 1
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code} {e.read()[:300].decode('utf-8', 'replace')}"
            if e.code not in (429, 500, 502, 503, 504):
                break
        except Exception as e:
            last = f"{type(e).__name__} {e}"
        time.sleep(2 ** attempt * 3)
    raise CallFailed(f"call failed: {last}", attempt + 1)


BAD_ESC = re.compile(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})')

# LaTeX в JSON-строке ломает ручной разбор: \frac -> form feed, \text -> tab.
# Пусть сервер сам экранирует ответ по схеме.
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "markdown": {"type": "STRING", "description": "Текст страницы, формулы в $...$ и $$...$$"},
        "figures": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "id": {"type": "STRING"},
            "bbox": {"type": "ARRAY", "items": {"type": "NUMBER"}},
            "kind": {"type": "STRING"},
            "caption": {"type": "STRING"},
            "near": {"type": "STRING"}},
            "propertyOrdering": ["id", "bbox", "kind", "caption", "near"]}},
        "uncertain": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "where": {"type": "STRING"}, "fragment": {"type": "STRING"}, "alt": {"type": "STRING"},
            "why": {"type": "STRING"}},
            "propertyOrdering": ["where", "fragment", "alt", "why"]}},
    },
    "required": ["markdown", "figures", "uncertain"],
    "propertyOrdering": ["markdown", "figures", "uncertain"],
}


def parse_json(text):
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```\w*\s*|\s*```$", "", t, flags=re.S)
    try:
        return json.loads(t)
    except Exception:
        pass
    s, e = t.find("{"), t.rfind("}")
    if 0 <= s < e:
        t = t[s:e + 1]
    # LaTeX внутри JSON приходит с одинарными бэкслешами — удваиваем не-JSON экранирования
    try:
        return json.loads(BAD_ESC.sub(r"\\\\", t))
    except Exception:
        return json.loads(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", t))


def parse_pages(spec):
    """'2' | '2-5' | '2,4,7-9' -> {2,4,5,7,8,9}; пусто -> None = все страницы"""
    out = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            out.update(range(int(lo), int(hi) + 1))
        else:
            out.add(int(part))
    return out or None


# Модель иногда отдаёт "\text" как настоящую табуляцию: JSON при этом валиден, но
# экранирование СЪЕДАЕТ первую букву команды — портится не \text, а <TAB>ext.
# В markdown этих управляющих символов быть не должно вовсе (проверено: 0 на 18 стр.).
CTRL_LETTER = {0x08: "b", 0x09: "t", 0x0C: "f", 0x0D: "r"}


def unmangle(s):
    return re.sub(r"([\x08\x09\x0c\r])([a-zA-Z]+)",
                  lambda m: "\\" + CTRL_LETTER[ord(m.group(1))] + m.group(2), s)


def close_math(s):
    """Докрыть $, которое модель потеряла в конце строки (ловится чекером как «незакрытых $»).
    Дальше KaTeX съедает весь текст до следующего $ — пол-страницы превращается в формулу.
    Строки с $$ не трогаем: там подсчёт не говорит, где именно разрыв."""
    return "\n".join(ln + "$" if ln.count("$") % 2 and "$$" not in ln else ln
                     for ln in s.split("\n"))


SEP = re.compile(r"^\s*\|[\s:|-]+$")


def fix_tables(md):
    """Модель иногда даёт разделитель таблицы без заголовка: первая строка «|», а в разделителе
    3 колонки. marked такую таблицу не парсит и рвёт её наружу голыми pipe'ами.
    Чиним только явный случай — заголовок пустой, колонок меньше, чем в разделителе."""
    ln = md.split("\n")
    for i in range(1, len(ln)):
        if not SEP.match(ln[i]) or "|" not in ln[i - 1] or ln[i - 1].strip().strip("|").strip():
            continue
        need = ln[i].count("|") - ln[i - 1].count("|")
        if need > 0:
            ln[i - 1] = ln[i - 1].rstrip() + " |" * need
    return "\n".join(ln)


def collect(src, pages, dpi):
    """pages=None -> все страницы источника."""
    import pymupdf
    out = []
    if src.lower().endswith(".pdf"):
        d = pymupdf.open(src)
        for i in pages or range(1, d.page_count + 1):
            if i > d.page_count:
                continue
            p = d[i - 1]
            out.append((i, p.get_pixmap(dpi=dpi).tobytes("png"), p.rect))
    else:
        found = []
        for fn in sorted(os.listdir(src)):
            m = re.search(r"(\d+)", fn)
            if not m or not fn.lower().endswith((".png", ".jpg", ".jpeg")):
                continue
            found.append((int(m.group(1)), os.path.join(src, fn)))
        for i, path in found:
            if pages and i not in pages:
                continue
            out.append((i, open(path, "rb").read(), None))
    return sorted(out, key=lambda t: t[0])


def crop_assets(img_bytes, figures, page, assets_dir):
    from PIL import Image
    import bbox_fix
    im = Image.open(io.BytesIO(img_bytes))
    W, H = im.size
    made = []
    gray = bbox_fix.gray_of(img_bytes) if figures else None
    order, why = "xy", ""
    if figures:
        stored = {f.get("bbox_order") for f in figures} - {None}
        if len(stored) == 1:
            # порядок уже записан в json страницы — при перегоне по содержимому его не угадываем:
            # рамку мог поправить человек, и детектор по бледному чертежу переспорит его
            order, why = stored.pop(), "из json"
        else:
            order, why = bbox_fix.orientation(gray, figures)
        if order != "xy":
            print(f"  p{page:02d} bbox {why}", flush=True)
    for f in figures:
        b = f.get("bbox")
        if not b or len(b) != 4:
            continue
        x0, y0, x1, y1 = [float(v) for v in b]
        if order == "yx":                       # модель вернула [ymin,xmin,ymax,xmax]
            x0, y0, x1, y1 = y0, x0, y1, x1
        if max(x0, y0, x1, y1) > 1.5:          # шкала 0-1000
            x0, x1 = x0 / 1000 * W, x1 / 1000 * W
            y0, y1 = y0 / 1000 * H, y1 / 1000 * H
        pad = round(0.012 * max(W, H))
        box = (max(0, int(x0) - pad), max(0, int(y0) - pad), min(W, int(x1) + pad), min(H, int(y1) + pad))
        before = box
        box = bbox_fix.trim_box(gray, box)
        if box != before:
            print(f"  p{page:02d} {f.get('id','fig')}: срезана полоса у края "
                  f"{[b - a for a, b in zip(before, box)]}", flush=True)
        if box[2] - box[0] < 16 or box[3] - box[1] < 16:
            continue
        name = f"p{page:02d}_{f.get('id','fig')}.png"
        im.crop(box).save(os.path.join(assets_dir, name))
        made.append({**f, "file": f"assets/{name}", "px": box, "bbox_order": order})
    return made


def recrop(a):
    """Пересобрать выкройки из уже сохранённых ответов модели. API не трогает, токены не тратит."""
    src = a.pages_dir or a.pdf
    have = {i: png for i, png, _ in collect(src, parse_pages(a.pages), a.dpi)}
    n = flipped = 0
    for fn in sorted(os.listdir(os.path.join(a.out, "pages"))):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(a.out, "pages", fn)
        d = json.load(io.open(path, encoding="utf-8"))
        png = have.get(d["page"])
        if not png:
            continue
        if d.get("size_px"):
            w, h = ImageSize(png)
            if [w, h] != d["size_px"]:
                print(f"  p{d['page']:02d} ПРОПУСК: размер {w}x{h} != {d['size_px']} (другой dpi?)")
                continue
        figs = d.get("figures") or []
        made = crop_assets(png, figs, d["page"], os.path.join(a.out, "assets"))
        flipped += sum(1 for m in made if m.get("bbox_order") != "xy")
        d["figures"] = made
        json.dump(d, io.open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        n += 1
    print(f"перекроено страниц {n}, рамок с перевёрнутым порядком {flipped}")


class Spend:
    """Что реально ушло на API. Тредов несколько, поэтому всё под локом.
    Токены ответа, взятого из кэша, в расход не идут: их заплатили в прошлый раз,
    но показываем их отдельно — это мера экономии кэша. Страница, упавшая после
    успешного ответа (не распарсился JSON), токены уже потратила — они в расходе."""

    def __init__(self, price_in=0.0, price_out=0.0):
        self.lock = threading.Lock()
        self.p_in, self.p_out = price_in or 0.0, price_out or 0.0
        self.d = dict(attempts=0, live=0, cache=0, paid_in=0, paid_out=0, paid_th=0,
                      cache_read=0, saved_in=0, saved_out=0, api_secs=0.0)

    def page(self, raw, api_secs, live=True, attempts=0):
        u = raw.get("usageMetadata") or {}
        i = u.get("promptTokenCount", 0) or 0
        o = u.get("candidatesTokenCount", 0) or 0
        th = u.get("thoughtsTokenCount", 0) or 0
        cr = u.get("cachedContentTokenCount", 0) or 0
        with self.lock:
            self.d["attempts"] += attempts
            self.d["api_secs"] += api_secs
            if live:
                self.d["live"] += 1
                self.d["paid_in"] += i
                self.d["paid_out"] += o
                self.d["paid_th"] += th
                self.d["cache_read"] += cr
            else:
                self.d["cache"] += 1
                self.d["saved_in"] += i
                self.d["saved_out"] += o + th
        return i, o, th

    def fail(self, attempts):
        with self.lock:
            self.d["attempts"] += attempts

    def money(self):
        d = self.d
        return ((d["paid_in"] - d["cache_read"]) * self.p_in
                + (d["paid_out"] + d["paid_th"]) * self.p_out) / 1e6


def save_usage(path, spend, failed):
    """usage.json — запись о потраченном. Из кэша она не пересобирается, поэтому
    копит между прогонами одной папки и попадает в историю вместе с review.json."""
    old = {}
    if os.path.isfile(path):
        try:
            old = json.load(io.open(path, encoding="utf-8"))
        except Exception:
            print(f"  {path} не читается — начинаю запись заново", flush=True)
    tot = old.get("total") or {}
    merged = {k: round(tot.get(k, 0) + v, 2) for k, v in spend.d.items()}
    money = round(old.get("money_total", 0.0) + spend.money(), 4)
    json.dump({"updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "sessions": old.get("sessions", 0) + 1,
               "price_per_mtok": {"in": spend.p_in, "out": spend.p_out},
               "money": round(spend.money(), 4), "money_total": money,
               "failed_pages_total": round(old.get("failed_pages_total", 0) + failed),
               "session": dict(spend.d), "total": merged},
              io.open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return merged, money


def write_used(path, a, system, cfg):
    """Секция `used` в run.json — хэши, которые знает только момент вызова: промпт потом
    правят, а его старой версии никто не хранил. Остальное дописывает manifest.py."""
    old = {}
    if os.path.isfile(path):
        try:
            old = json.load(io.open(path, encoding="utf-8"))
        except Exception:
            old = {}
    old["used"] = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "model": a.model, "dpi": a.dpi, "max_tokens": a.max_tokens,
                   "workers": a.workers, "no_cache": bool(a.no_cache), "pages_arg": a.pages,
                   "src": a.pages_dir or a.pdf,
                   "prompt": os.path.relpath(a.prompt, ROOT).replace("\\", "/"),
                   "prompt_sha256": hashlib.sha256(system.encode()).hexdigest()[:16],
                   "prompt_extra": a.prompt_extra,
                   "schema_sha256": hashlib.sha256(cfg).hexdigest()[:16]}
    json.dump(old, io.open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default="C:/Ocifrovka/скан.pdf")
    ap.add_argument("--pages-dir")
    ap.add_argument("--pages", default="", help="например 2-5 или 2,4,7-9; пусто = все страницы")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--model", default="gemini-3.7-flash")
    ap.add_argument("--prompt", default=os.path.join(HERE, "prompt_system.md"))
    ap.add_argument("--prompt-extra", help="дополнение к системному промпту, дописывается в конец")
    # папку прогона называет человек: имя попадает в .gitignore-маску out*/, и безымянный
    # прогон в out/ означает, что результат не доедет до истории
    ap.add_argument("--out", required=True, help="папка прогона, например out_kz_5_2")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-tokens", type=int, default=16000)
    ap.add_argument("--key-file")
    # ставку не выдумываем: без неё считаем токены и попытки, но не деньги
    ap.add_argument("--price-in", type=float, default=0.0, help="за млн входных токенов")
    ap.add_argument("--price-out", type=float, default=0.0, help="за млн выходных токенов")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--recrop", action="store_true",
                    help="только заново выкроить рисунки из сохранённых ответов, без API")
    a = ap.parse_args()

    if a.recrop:
        recrop(a)
        return

    key = read_key(a.key_file)
    system = open(a.prompt, encoding="utf-8").read()
    if a.prompt_extra:
        system += "\n\n" + open(a.prompt_extra, encoding="utf-8").read()
    cfg = json.dumps(SCHEMA, sort_keys=True).encode()
    pages = parse_pages(a.pages)
    src = a.pages_dir or a.pdf
    items = collect(src, pages, a.dpi)
    if not items:
        sys.exit(f"nothing to process from {src} pages {a.pages}")

    for sub in ("pages", "md", "assets", "cache"):
        os.makedirs(os.path.join(a.out, sub), exist_ok=True)
    print(f"{len(items)} pages | {a.model} | {a.dpi} dpi | workers={a.workers}", flush=True)

    spend = Spend(a.price_in, a.price_out)
    lock_err = []

    def work(it):
        page, png, rect = it
        h = hashlib.sha256(png + system.encode() + a.model.encode() + cfg).hexdigest()[:16]
        cpath = os.path.join(a.out, "cache", f"p{page:02d}_{h}.json")
        cached = os.path.isfile(cpath) and not a.no_cache
        t0 = time.time()
        if cached:
            raw = json.load(open(cpath, encoding="utf-8"))
            i, o, th = spend.page(raw, 0.0, live=False)
        else:
            try:
                raw, tries = call(a.model, key, png, system, a.max_tokens)
            except CallFailed as e:
                # попытки стоят денег даже там, где страница не получена
                spend.fail(e.attempts)
                raise
            api_secs = time.time() - t0
            i, o, th = spend.page(raw, api_secs, live=True, attempts=tries)
        try:
            text = raw["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            raise RuntimeError(f"p{page}: no text part: {json.dumps(raw)[:300]}"
                               + ("" if cached else " (отказ фильтра в кэш не лёг — страница перевызовётся)"))
        if not cached:
            # в кэш кладётся только ответ с текстом: отказ RECITATION — не ответ страницы,
            # и закешированный он превращается в вечный — следующая попытка читает его же
            json.dump(raw, open(cpath, "w", encoding="utf-8"), ensure_ascii=False)
        data = parse_json(text)
        figures = crop_assets(png, data.get("figures") or [], page, os.path.join(a.out, "assets"))
        md = fix_tables(close_math(unmangle(data.get("markdown", ""))))
        for f in figures:
            md = re.sub(r"\{!%s\}" % re.escape(f["id"]), f"![{f.get('caption') or f['id']}]({f['file']})", md)
        # шапка бланка «INTELLECT» срезается здесь, на записи страницы: полоса в кэше
        # ушла бы и в банк, и на стенд, и в отчёт — каждый экран вычищал бы её сам.
        # Выкроенный логотип с той же полосы — не рисунок задачи.
        md, head, figures = letterhead.cut(md, figures)
        json.dump({"page": page, "dpi": a.dpi, "size_px": [ImageSize(png)[0], ImageSize(png)[1]],
                   "model": a.model, "cached": cached, "figures": figures, "head": head,
                   "uncertain": data.get("uncertain") or [], "markdown": md},
                  io.open(os.path.join(a.out, "pages", f"p{page:02d}.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        io.open(os.path.join(a.out, "md", f"p{page:02d}.md"), "w", encoding="utf-8").write(md)
        return page, (i, o, th), time.time() - t0, cached, len(md), len(figures), len(data.get("uncertain") or [])

    with cf.ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(work, it): it[0] for it in items}
        ok = 0
        for fu in cf.as_completed(futs):
            p = futs[fu]
            try:
                page, tok, secs, was_cached, nchars, nfig, nunc = fu.result()
            except Exception as e:
                lock_err.append((p, str(e)[:200]))
                print(f"  p{p:02d} FAIL {type(e).__name__} {str(e)[:180]}", flush=True)
                continue
            ok += 1
            i, o, th = tok
            print(f"  p{page:02d} {'cache' if was_cached else 'live '} {nchars:5d} ch | figs {nfig} | ? {nunc} | "
                  f"in {i} out {o}" + (f" think {th}" if th else "")
                  + (" tok (оплачены в прошлый раз)" if was_cached else " tok") + f" | {secs:.1f}s", flush=True)

    io.open(os.path.join(a.out, "all.md"), "w", encoding="utf-8").write(
        "\n\n".join(io.open(os.path.join(a.out, "md", f), encoding="utf-8").read()
                    for f in sorted(os.listdir(os.path.join(a.out, "md")))))
    d = spend.d
    retried = d["attempts"] - d["live"]
    print(f"\nстраниц {ok}/{len(items)} | упало {len(lock_err)} | живых вызовов {d['live']} "
          f"(попыток {d['attempts']}, ретраев {retried}) | из кэша {d['cache']} | api {d['api_secs']:.0f}s")
    print(f"токены оплаченные: in {d['paid_in']} (кэш-API {d['cache_read']}) out {d['paid_out']} "
          f"think {d['paid_th']} | на кэше ответов не потрачено: in {d['saved_in']} out {d['saved_out']}")
    money = spend.money()
    tot, total_money = save_usage(os.path.join(a.out, "usage.json"), spend, len(lock_err))
    write_used(os.path.join(a.out, "run.json"), a, system, cfg)
    if spend.p_in or spend.p_out:
        print(f"деньги: {money:.4f} за этот запуск, {total_money:.4f} накоплено в прогоне "
              f"(ставка {spend.p_in}/{spend.p_out} за млн токенов in/out)")
    else:
        print("деньги: ставка не задана — посчитаю по --price-in/--price-out (за млн токенов); "
              f"в usage.json записаны токены и попытки")
    for p, e in sorted(lock_err):
        print(f"  FAILED p{p:02d}: {e}")


def ImageSize(b):
    from PIL import Image
    im = Image.open(io.BytesIO(b))
    return im.size


if __name__ == "__main__":
    main()
