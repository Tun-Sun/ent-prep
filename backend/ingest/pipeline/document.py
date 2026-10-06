# -*- coding: utf-8 -*-
"""Один документ — одна команда.

  python pipeline/document.py --pdf C:/Ocifrovka/скан.pdf --out out_kz_7_1
  python pipeline/document.py --out out_kz_7_1 --skip-api      # после ручной правки
  python pipeline/document.py --out out_x --no-pdf

По-прежнему пять скриптов, но порядок и общие флаги здесь: ocr (API, кэш) ->
index (превью скана + index.json) -> report (рамки рисунков поверх скана) ->
tasks (разбор на задачи) -> report --print (вёрстка A4) -> topdf (PDF для печати) ->
manifest (run.json: чем был прогон). Без --skip-api команды, которые тратят деньги,
идут первыми: если API упал, вид всё равно соберётся из того, что уже есть на диске.
"""
import argparse, collections, io, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def step(name, argv, keep_going=False):
    print(f"\n=== {name}: {' '.join(argv[1:])}", flush=True)
    r = subprocess.run(argv, cwd=ROOT)
    if r.returncode and not keep_going:
        sys.exit(f"{name}: код {r.returncode} — стоп")
    return r.returncode


def tail(out, pages):
    """Что получилось: страницы, задачи, деньги. Цифры — из файлов прогона, не из памяти."""
    d = os.path.join(ROOT, out)
    upath = os.path.join(d, "usage.json")
    u = json.load(io.open(upath, encoding="utf-8")) if os.path.isfile(upath) else {}
    t = {}
    f = os.path.join(d, "tasks.json")
    if os.path.isfile(f):
        t = json.load(io.open(f, encoding="utf-8"))
    rev = {}
    if os.path.isfile(os.path.join(d, "review.json")):
        rev = json.load(io.open(os.path.join(d, "review.json"), encoding="utf-8"))
    ts = t.get("tasks") or []
    # те же корзины, что печатает tasks.py: ответ из таблицы ответов, ответ внутри
    # решения, и то и другое — не одно и то же, и «без ответа» считается от них.
    tbl = sum(1 for x in ts if x.get("answer"))
    sol = sum(1 for x in ts if not x.get("answer") and x.get("answer_in"))
    unit = collections.Counter((x["word"] or "номер без слова").lower() for x in ts)
    print(f"\n--- {out} ---")
    print(f"страниц: {t.get('pages', pages)} | единиц: {len(ts)} ("
          + ", ".join(f"{k} {v}" for k, v in sorted(unit.items(), key=lambda kv: -kv[1])) + ") | "
          f"ответ из таблицы: {tbl} | ответ в решении: {sol} | без ответа: {len(ts) - tbl - sol} | "
          f"принято человеком: {sum(1 for v in rev.values() if v.get('ok'))}")
    # список прогонов на стенде ведёт человек, и прогон без строчки в нём просто не виден
    # приёмщику: 12 готовых страниц, которых никто не открывал. Проверяем это, а не надеемся.
    page = os.path.join(ROOT, "web", "index.html")
    if os.path.isfile(page):
        if f"'{os.path.basename(out)}'" not in io.open(page, encoding="utf-8").read():
            print(f"ВНИМАНИЕ: {out} нет в списке RUNS (web/index.html) — на стенде прогон не открыть")
    else:
        print(f"ВНИМАНИЕ: {os.path.join('web', 'index.html')} не найден — стенд не проверить")
    if not u:
        print("учёт: usage.json нет — прогон собран до появления учёта или без шага API; "
              "сумм не выдумываем")
        return
    tot = u.get("total") or {}
    print(f"потрачено токенов: in {tot.get('paid_in', 0)} out {tot.get('paid_out', 0)} "
          f"think {tot.get('paid_th', 0)} | попыток API {tot.get('attempts', 0)} "
          f"(ретраев {tot.get('attempts', 0) - tot.get('live', 0)}) | из кэша {tot.get('cache', 0)}")
    p = u.get("price_per_mtok") or {}
    if p.get("in") or p.get("out"):
        print(f"деньги: {u.get('money', 0)} за запуск, {u.get('money_total', 0)} накоплено в прогоне")
    else:
        print("деньги не считаны: не задана ставка (--price-in/--price-out за млн токенов)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default="C:/Ocifrovka/скан.pdf")
    ap.add_argument("--out", required=True)
    ap.add_argument("--pages", default="")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--model", default="gemini-3.7-flash")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--prompt")
    ap.add_argument("--prompt-extra")
    ap.add_argument("--price-in", type=float, default=0.0)
    ap.add_argument("--price-out", type=float, default=0.0)
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--name", default="оцифровано", help="имя PDF для печати, без расширения")
    ap.add_argument("--skip-api", action="store_true", help="не звать ocr.py: пересобрать вид из того, что есть")
    ap.add_argument("--no-pdf", action="store_true", help="не собирать PDF для печати")
    a = ap.parse_args()

    py = sys.executable or "python"
    d = os.path.join(ROOT, a.out)
    pages = 0
    if not a.skip_api:
        argv = [py, os.path.join(HERE, "ocr.py"), "--pdf", a.pdf, "--out", a.out,
                "--dpi", str(a.dpi), "--model", a.model, "--workers", str(a.workers),
                "--price-in", str(a.price_in), "--price-out", str(a.price_out)]
        if a.pages:
            argv += ["--pages", a.pages]
        if a.prompt:
            argv += ["--prompt", a.prompt]
        if a.prompt_extra:
            argv += ["--prompt-extra", a.prompt_extra]
        if a.no_cache:
            argv += ["--no-cache"]
        step("распознавание", argv, keep_going=True)
    if not os.path.isdir(os.path.join(d, "pages")):
        sys.exit(f"{a.out}/pages нет — нечего собирать, сними --skip-api")
    pages = len([f for f in os.listdir(os.path.join(d, "pages")) if f.endswith(".json")])
    step("превью скана", [py, os.path.join(HERE, "index.py"), "--pdf", a.pdf, "--out", a.out])
    step("отчёт было/распознано", [py, os.path.join(HERE, "report.py"), "--out", a.out])
    step("разбор на задачи", [py, os.path.join(HERE, "tasks.py"), "--out", a.out])
    if not a.no_pdf:
        # print.html делает report.py в режиме --print: без этого шага topdf нечего читать
        step("вёрстка A4", [py, os.path.join(HERE, "report.py"), "--out", a.out, "--print"])
        step("pdf", [py, os.path.join(HERE, "topdf.py"), "--out", a.out, "--name", a.name])
    step("манифест прогона", [py, os.path.join(HERE, "manifest.py"), "--out", a.out, "--pdf", a.pdf])
    tail(a.out, pages)


if __name__ == "__main__":
    main()
