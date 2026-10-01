# -*- coding: utf-8 -*-
"""Импорт оцифрованных задач из папки прогона пайплайна оцифровки.

    python manage.py import_scanned_tasks C:/path/out_kasatkina_em [--subject physics]

Ключ перезаписи — уже существующее ограничение uniq_external_id_per_source:
external_id = "<прогон>:p<страница>:<слово><номер>". Второй запуск обновляет
запись, а не заводит дубль, поэтому вычитку можно перегонять сколько угодно.
Отмеченное на стенде «проверено» приходит по ключу единицы из tasks.json
(тот же ключ пишет review.json), а не по external_id.

Черновиком остаётся всё, что человек не отметил как проверенное: молча показать
это ученикам — значит выставить наружу догадки модели наравне с вычитанным.
"""
import json
import re
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from subjects.models import Question, Subject, Topic

IMG = re.compile(r"^!\[[^\]]*\]\(([^)]+)\)\s*$")


def as_text(latex):
    """text существующему UI нужен читаемый: он рендерит HTML, а не KaTeX.
    Это не замена latex — это то, что видно, пока экран банка не дописан."""
    lines = []
    for ln in (latex or "").split("\n"):
        m = IMG.match(ln.strip())
        if m:
            lines.append("[рисунок]")
            continue
        lines.append(re.sub(r"\*\*|\$|\\tag\{[^}]*\}", "", ln))
    return "\n".join(lines).strip()


class Command(BaseCommand):
    help = "Загрузить оцифрованные из книги задачи в базу вопросов (перезаписью по external_id)."

    def add_arguments(self, parser):
        parser.add_argument("run_dir", help="папка прогона: tasks.json, run.json, pages/, assets/")
        parser.add_argument("--subject", default="physics")
        parser.add_argument("--dry-run", action="store_true")

    def load(self, path, default=None):
        p = Path(path)
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else default

    def handle(self, *args, **opt):
        run = Path(opt["run_dir"])
        tasks = self.load(run / "tasks.json")
        if not tasks:
            raise CommandError(f"{run}/tasks.json нет — сначала прогнай pipeline/tasks.py")
        try:
            subject = Subject.objects.get(slug=opt["subject"])
        except Subject.DoesNotExist:
            raise CommandError("нет предмета %s; есть: %s"
                               % (opt["subject"], ", ".join(Subject.objects.values_list("slug", flat=True))))
        man = (self.load(run / "run.json") or {})
        src = man.get("source") or {}
        used = man.get("used") or {}
        render = man.get("render") or {}
        review = self.load(run / "review.json", {}) or {}
        name = tasks["run"]
        # тема берётся из «области» страницы, и её у десятка задач одна — считаем новые темы
        # по множеством имён, иначе отчёт рисовал бы «новых тем 136» на трёх настоящих
        scopes = {t.get("scope") or name for t in (tasks.get("tasks") or [])}
        known = set(Topic.objects.filter(subject=subject, name__in=scopes).values_list("name", flat=True))

        made = upd = drawn = took = 0
        tnew = len(scopes - known)
        for t in tasks.get("tasks") or []:
            page = (t.get("pages") or [0])[0]
            ext = f"{name}:p{page}:{t.get('word') or ''}{t['num']}"[:150]
            scope = t.get("scope") or name
            # приёмка на стенде keyed по ключу единицы (блок#словономер), а не по external_id:
            # стенд про БД ничего не знает, и по внешнему ID он бы не нашёл, что отмечено
            accepted = bool((review.get(t.get("key") or "") or {}).get("ok"))
            took += accepted
            figures = [f for f in (t.get("figures") or []) if isinstance(f, str)]
            old = Question.objects.filter(source_type="book_scan", external_id=ext).first()
            if opt["dry_run"]:
                # dry-run только считает: ни тему, ни вопрос, ни файл картинки не трогаем
                made += old is None
                upd += old is not None
                # считаем ровно тот кадр, который положим: на задачу один, первый по списку
                if figures and (old is None or not old.image) and (run / figures[0]).is_file():
                    drawn += 1
                continue
            topic, _ = Topic.objects.get_or_create(subject=subject, name=scope)
            defaults = {
                "topic": topic,
                "text": as_text(t.get("markdown"))[:4000] or "(пустое условие)",
                "latex": t.get("markdown") or "",
                "latex_answer": t.get("answer") or "; ".join(t.get("answer_in") or []),
                "question_type": "open_answer",
                "verification_status": "verified" if accepted else "draft",
                "uncertain": t.get("uncertain") or [],
                "provenance": {
                    "run": name, "page": page, "unit": t.get("word") or "задача",
                    "kind": t.get("kind"), "scope": t.get("scope"),
                    "pages": t.get("pages"), "loc": t.get("spans"),
                    "answer_pages": t.get("answer_pages") or [],
                    "answer_note": t.get("answer_note") or "",
                    "figures": figures,
                    "src": src.get("src"), "src_sha256": src.get("sha256"),
                    "scan_dpi": src.get("raster_dpi"), "render_dpi": render.get("dpi"),
                    "model": render.get("model"), "prompt_sha256": used.get("prompt_sha256"),
                },
            }
            q, new = Question.objects.update_or_create(
                source_type="book_scan", external_id=ext, defaults=defaults)
            made += new
            upd += not new
            # выкройка — один кадр на задачу: второй в источнике бывает дублем с оборота
            if figures:
                # image_ref — ссылка на файл прогона; присвоить до save(), иначе save()
                # уйдёт в БД с тем, что было раньше, и поле останется пустым
                if not q.image_ref:
                    q.image_ref = f"{name}:{Path(figures[0]).name}"
                    q.save(update_fields=["image_ref"])
                f = run / figures[0]
                if not q.image and f.is_file():
                    q.image.save(f"{name}_p{page:02d}_{f.name}", ContentFile(f.read_bytes()), save=True)
                    drawn += 1
        self.stdout.write(self.style.SUCCESS(
            f"{name}: создано {made}, обновлено {upd}, новых тем {tnew}, картинок положено {drawn}, "
            f"предмет «{subject.name}», принято человеком {took} из {len(review)} записей приёмки"
            + (" — dry-run, в базу не писано" if opt["dry_run"] else "")))
        if not opt["dry_run"]:
            self.stdout.write("сложность у всех проставлена дефолтом «Средний»: в оцифровке её нет, "
                              "разметку сделаем отдельно — не принимать её за размеченную")
