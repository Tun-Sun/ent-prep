# -*- coding: utf-8 -*-
"""Прогнать книгу через конвейер оцифровки и положить результат в банк.

    python manage.py run_book_ingest <id прогона>

Команду запускает не веб-процесс, а отдельный процесс из ingest.runner: шаг
распознавания говорит с API десятки минут. Здесь же — единственное место, где
прогон может честно сказать, сколько страниц он видел и сколько денег потратил.
"""
import io
import json
import subprocess
import sys
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ingest import runner
from ingest.models import STATUS_DONE, STATUS_FAILED, STATUS_PENDING, STATUS_RUNNING, IngestRun


def counted_pages(out):
    d = Path(out) / "pages"
    return len([f for f in d.glob("*.json")]) if d.is_dir() else 0


def counted_units(out):
    f = Path(out) / "tasks.json"
    if not f.is_file():
        return 0
    return len((json.loads(f.read_text(encoding="utf-8")) or {}).get("tasks") or [])


def missing_pages(out):
    """Номера страниц, которых нет в pages/, хотя они есть в источнике.

    index.json считает страницы PDF, pages/*.json — то, что реально вернула модель.
    Расхождение означает «книга легла в банк дырявой», а коды выхода шагов при этом
    ноль: потерянная страница молчала бы до самой вычитки.
    """
    idx = Path(out) / "index.json"
    if not idx.is_file():
        return []
    try:
        expected = {int(p["page"]) for p in json.loads(idx.read_text(encoding="utf-8"))}
    except (ValueError, KeyError, TypeError):
        return []
    d = Path(out) / "pages"
    got = set()
    for f in d.glob("*.json") if d.is_dir() else []:
        try:
            got.add(int(f.stem.lstrip("p")))
        except ValueError:
            pass
    return sorted(expected - got)


def spent(out):
    """Деньги — только из usage.json и только если ставка была задана. Без ставки
    возвращаем None: «не считано» и «потрачено ноль» — разные новости для владельца.
    """
    f = Path(out) / "usage.json"
    if not f.is_file():
        return None
    u = json.loads(f.read_text(encoding="utf-8"))
    price = u.get("price_per_mtok") or {}
    if not (price.get("in") or price.get("out")):
        return None
    return round(float(u.get("money_total") or 0.0), 4)


class Command(BaseCommand):
    help = "Оцифровать загруженную книгу и импортировать её единицы в банк вопросов."

    def add_arguments(self, parser):
        parser.add_argument("run_id", type=int)

    def handle(self, *args, **opt):
        run = IngestRun.objects.filter(pk=opt["run_id"]).first()
        if run is None:
            raise CommandError(f"прогона {opt['run_id']} нет в базе")
        if run.status != STATUS_PENDING:
            raise CommandError(f"{run.name}: состояние «{run.status}» — прогон уже шёл или не ждёт очереди")
        out = runner.run_dir(run.name)
        pdf = run.pdf_path or str(out / "source.pdf")
        if not Path(pdf).is_file():
            self.fail(run, f"PDF не найден: {pdf}")
            return
        if not runner.conf()["key_file"] or not Path(runner.conf()["key_file"]).is_file():
            self.fail(run, "ключа Gemini нет на сервере: задай GEMINI_KEY_FILE — без него прогон нечем оплачивать")
            return

        run.status = STATUS_RUNNING
        run.step = "распознавание"
        run.save(update_fields=["status", "step"])
        self.log(run, f"=== {run.name}: {Path(pdf).name}, {run.subject.slug}/{run.language}, «{run.book}»")

        for name, argv in runner.steps(run.name, pdf):
            run.step = name
            run.save(update_fields=["step"])
            self.log(run, f"--- {name}: {' '.join(argv[1:])}")
            r = subprocess.run(argv)
            if r.returncode:
                self.fail(run, f"шаг «{name}» завершился кодом {r.returncode} — в банк ничего не легло")
                return
            run.pages = counted_pages(out)
            run.units = counted_units(out)
            run.money = spent(out)
            run.save(update_fields=["pages", "units", "money"])

        if run.pages == 0:
            self.fail(run, "ни одной страницы не распознано — в банке нечего строить")
            return
        holes = missing_pages(out)
        if holes:
            listing = ", ".join(f"с.{p}" for p in holes[:10])
            if len(holes) > 10:
                listing += f" и ещё {len(holes) - 10}"
            run.error = (f"страниц не получено: {listing} — их отбил фильтр модели или "
                         f"обрыв; книга легла в банк без них")
            run.save(update_fields=["error"])
            self.log(run, f"!!! {run.error}")

        run.step = "импорт в банк"
        run.save(update_fields=["step"])
        buf = io.StringIO()
        try:
            call_command("import_scanned_tasks", str(out), subject=run.subject.slug,
                         language=run.language, book=run.book, stdout=buf, stderr=buf)
        except Exception as e:
            self.fail(run, f"импорт в банк: {e.__class__.__name__}: {e}")
            return
        run.report = buf.getvalue().strip()
        self.log(run, run.report)
        run.status = STATUS_DONE
        run.step = ""
        run.finished_at = timezone.now()
        run.save(update_fields=["report", "status", "step", "finished_at"])

    def log(self, run, text):
        self.stdout.write(text)

    def fail(self, run, text):
        run.status = STATUS_FAILED
        run.error = text
        run.step = ""
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error", "step", "finished_at"])
        self.stderr.write(f"{run.name}: {text}")
        sys.exit(1)
