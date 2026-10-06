# -*- coding: utf-8 -*-
"""Чем и как платформа гонит конвейер оцифровки.

Конвейер — те же скрипты, что я годами запускал руками (pipeline/*.py), только
теперь они лежат в этом репозитории и едут на сервер вместе с бэкендом. Здесь
собраны два решения: порядок шагов и как запустить часовой прогон из-под
веб-процесса, не удерживая gunicorn-worker.
"""
import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings

PIPELINE_DIR = Path(__file__).resolve().parent / "pipeline"
BACKEND_DIR = PIPELINE_DIR.parent.parent


def runs_root():
    return Path(settings.INGEST_RUNS_DIR)


def run_dir(name):
    return runs_root() / name


def log_path(name):
    return run_dir(name) / "ingest.log"


def conf():
    """Ставка берётся только из окружения: без неё деньги считаются «не считаны»,
    а не выдумываются по среднему тарифу."""
    return {
        "dpi": settings.INGEST_DPI,
        "model": settings.INGEST_MODEL,
        "workers": settings.INGEST_WORKERS,
        "price_in": settings.INGEST_PRICE_IN,
        "price_out": settings.INGEST_PRICE_OUT,
        "key_file": settings.GEMINI_KEY_FILE,
    }


def steps(name, pdf, c=None):
    """Шаги прогона: распознавание → превью скана → отчёт «было/распознано» → разбор
    на единицы. PDF для печати и вёрстка A4 в платформе не делаются: тренеру нужны
    строки в банке, а печать — отдельный разговор.
    """
    c = c or conf()
    out = str(run_dir(name))
    script = lambda m: str(PIPELINE_DIR / m)  # noqa: E731
    py = sys.executable or "python"
    return [
        ("распознавание", [py, script("ocr.py"), "--pdf", pdf, "--out", out,
                           "--dpi", str(c["dpi"]), "--model", c["model"],
                           "--workers", str(c["workers"]),
                           "--price-in", str(c["price_in"]), "--price-out", str(c["price_out"]),
                           "--key-file", c["key_file"]]),
        ("превью скана", [py, script("index.py"), "--pdf", pdf, "--out", out]),
        ("отчёт было/распознано", [py, script("report.py"), "--out", out]),
        ("разбор на задачи", [py, script("tasks.py"), "--out", out]),
    ]


def spawn(run_id):
    """Запуск оторванным процессом: книга — это десятки минут API-вызовов, держать
    их внутри HTTP-запроса значит получить таймаут и второй прогон от нетерпеливого
    повтора клика. Выход и ошибки уходят в ingest.log прогона.
    """
    from .models import IngestRun

    cmd = [sys.executable or "python", str(BACKEND_DIR / "manage.py"), "run_book_ingest", str(run_id)]
    log = log_path(IngestRun.objects.values_list("name", flat=True).get(pk=run_id))
    log.parent.mkdir(parents=True, exist_ok=True)
    handle = open(log, "ab", buffering=0)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    proc = subprocess.Popen(cmd, cwd=str(BACKEND_DIR), stdout=handle, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, start_new_session=True, env=env)
    return proc.pid
