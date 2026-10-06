#!/usr/bin/env python3
"""Стенд приёмки: раздаёт /web и принимает правки обратно в файлы прогона.

    python pipeline/serve.py [--port 8765]      затем открыть http://127.0.0.1:8765/web/

Два эндпоинта, оба пишут только внутрь указанного прогона:
    POST /save/task    {out, page, l0, l1, markdown} — заменяет полосы строк в pages/pNN.json
    POST /save/review  {out, key, ok, note}          — заводит/обновляет review.json

После правки текста перезапускает tasks.py: границы задач пересчитываются по новому
тексту, иначе стенд начал бы показывать разметку, которая от правки уже оторвалась.
Слушает только 127.0.0.1 — это инструмент одного человека на его машине.
"""
import argparse, datetime, io, json, os, re, subprocess, sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = re.compile(r"^out[A-Za-z0-9_\-]*$")


def run_dir(out):
    """Папка прогона. Проверка, что путь не уехал за пределы репозитория и что это прогон."""
    if not OUT.match(out):
        raise ValueError("имя папки прогона должно выглядеть как out_<что-то>")
    d = os.path.abspath(os.path.join(ROOT, out))
    if not d.startswith(os.path.abspath(ROOT) + os.sep) or not os.path.isdir(os.path.join(d, "pages")):
        raise ValueError(f"нет папки pages в {out}")
    return d


def page_path(out, page):
    d = run_dir(out)
    f = os.path.join(d, "pages", f"p{page:02d}.json")
    if not os.path.isfile(f):
        raise ValueError(f"нет страницы {out}/pages/p{page:02d}.json")
    return d, f


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")   # после сохранения стенд читает файл заново
        super().end_headers()

    def log_message(self, fmt, *args):
        if "/save/" in (args[0] if args else ""):
            print(f"  {self.address_string()} {fmt % args}")

    def _json(self, code, obj):
        raw = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if self.path == "/save/task":
                self.save_task(body)
            elif self.path == "/save/review":
                self.save_review(body)
            else:
                self._json(404, {"error": "неизвестный эндпоинт"})
        except Exception as e:
            self._json(400, {"error": str(e)})

    def save_task(self, b):
        out, page = b["out"], int(b["page"])
        l0, l1 = int(b["l0"]), int(b["l1"])
        d, f = page_path(out, page)
        p = json.load(io.open(f, encoding="utf-8"))
        lines = (p.get("markdown") or "").split("\n")
        if not (0 <= l0 <= l1 <= len(lines)):
            raise ValueError(f"полоса {l0}:{l1} не влезает в {len(lines)} строк страницы")
        new = (b.get("markdown") or "").replace("\r\n", "\n").rstrip("\n").split("\n")
        lines[l0:l1] = new
        p["markdown"] = "\n".join(lines)
        p["edited"] = datetime.datetime.now().isoformat(timespec="seconds")
        json.dump(p, io.open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        subprocess.run([sys.executable, os.path.join(HERE, "tasks.py"), "--out", out, "--quiet"],
                       cwd=ROOT, capture_output=True, timeout=120)
        t = json.load(io.open(os.path.join(d, "tasks.json"), encoding="utf-8"))
        self._json(200, {"ok": True, "chars": len(p["markdown"]), "tasks": t["tasks"]})

    def save_review(self, b):
        out, key = b["out"], str(b["key"])
        d = run_dir(out)
        f = os.path.join(d, "review.json")
        r = json.load(io.open(f, encoding="utf-8")) if os.path.isfile(f) else {}
        r[key] = {"ok": bool(b.get("ok")),
                  "by": str(b.get("by") or "человек"),
                  "at": datetime.datetime.now().isoformat(timespec="seconds")}
        note = str(b.get("note") or "").strip()
        if note:
            r[key]["note"] = note
        if not r[key]["ok"] and not note:
            r.pop(key)                      # сняли приёмку без замечания — записи не остаётся
        json.dump(r, io.open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
        self._json(200, {"ok": True, "review": r})


ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=8765)
a = ap.parse_args()
srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
print(f"стенд приёмки: http://127.0.0.1:{a.port}/web/   (остановить Ctrl+C)")
print(f"  папки прогонов: " + ", ".join(sorted(x for x in os.listdir(ROOT) if OUT.match(x))))
try:
    srv.serve_forever()
except KeyboardInterrupt:
    print("\nостановлен")
