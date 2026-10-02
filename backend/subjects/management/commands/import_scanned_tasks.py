# -*- coding: utf-8 -*-
"""Импорт оцифрованных задач из папки прогона пайплайна оцифровки.

    python manage.py import_scanned_tasks C:/path/out_kasatkina_em [--subject physics]

Ключ перезаписи — уже существующее ограничение uniq_external_id_per_source:
external_id = "<прогон>:p<страница>:<слово><номер>:<тема>". Второй запуск обновляет
запись, а не заводит дубль, поэтому вычитку можно перегонять сколько угодно.
Отмеченное на стенде «проверено» приходит по ключу единицы из tasks.json
(тот же ключ пишет review.json), а не по external_id.

Черновиком остаётся всё, что человек не отметил как проверенное: молча показать
это ученикам — значит выставить наружу догадки модели наравне с вычитанным.

Правка, сделанная тренером в окне редактуры банка (provenance.human_edited),
перегоном не затирается: условие, ответ и статус такой задачи остаются как их
исправил человек. Остальные поля паспорта обновляются — они из прогона.
"""
import json
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from subjects.models import Question, Subject, Topic, plain_from_latex


def topic_name(book, scope):
    return f"{book} · {scope}" if book else scope


def unit_format(t):
    """Тест или задача — по тому, что парсер уже насчитал вариантов A)/А).

    Отдельная метка нужна, потому что тест без ключа ответа в банке мешает
    вычитке задач: тренер листает 300 условий, а 20 из них — совсем другой формат.
    """
    return "тест" if (t.get("options") or 0) >= 2 or t.get("options_cyr") else "задача"


class Command(BaseCommand):
    help = "Загрузить оцифрованные из книги задачи в базу вопросов (перезаписью по external_id)."

    def add_arguments(self, parser):
        parser.add_argument("run_dir", help="папка прогона: tasks.json, run.json, pages/, assets/")
        parser.add_argument("--subject", default="physics")
        # Кабарга/қазақша листы лежат в том же предмете, но язык строки обязан быть
        # настоящим: дефолт 'ru' на казахский лист молча наврал бы про 20 задач.
        parser.add_argument("--language", default="ru", help="ru / kk / uz — язык задач прогона")
        # Тема одна на десяток задач и в разных книгах называется одинаково:
        # «Решение отдельных задач» от Касаткиной и от МКТ слилось бы в одну тему.
        # Метка книги разносит их, а правится она потом в окне банка, если это отрывок.
        parser.add_argument("--book", default="", help="метка книги/источника для имени темы")
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
        units = tasks.get("tasks") or []
        if not units:
            raise CommandError(
                f"{run}/tasks.json пуст — парсер границ не нашёл ни одной задачи. "
                "Это не «задач нет», это «формат не распознан»: сначала дорабатывай pipeline/tasks.py.")
        # тема берётся из «области» страницы, и её у десятка задач одна — считаем новые темы
        # по множеством имён, иначе отчёт рисовал бы «новых тем 136» на трёх настоящих
        book = opt["book"].strip()
        scopes = {topic_name(book, t.get("scope") or name) for t in units}
        known = set(Topic.objects.filter(subject=subject, name__in=scopes).values_list("name", flat=True))

        made = upd = drawn = took = kept_edited = 0
        tnew = len(scopes - known)
        for t in units:
            page = (t.get("pages") or [0])[0]
            scope = t.get("scope") or name
            # Номер задачи на странице не уникален: на одном листе уровни пишут свои «3»,
            # и две разные задачи на одном ключе молча переписывают друг друга.
            # Тема входит в ключ — из-за этого перегон из out_v2 съел 8 задач.
            ext = f"{name}:p{page}:{t.get('word') or ''}{t['num']}:{scope}"[:150]
            # приёмка на стенде keyed по ключу единицы (блок#словономер), а не по external_id:
            # стенд про БД ничего не знает, и по внешнему ID он бы не нашёл, что отмечено
            accepted = bool((review.get(t.get("key") or "") or {}).get("ok"))
            took += accepted
            figures = [f for f in (t.get("figures") or []) if isinstance(f, str)]
            old = Question.objects.filter(source_type="book_scan", external_id=ext).first()
            # Правка тренера в банке важнее перегоня: второй импорт молча вернул бы
            # опечатку, которую человек уже исправил глазами, и снял бы его статус.
            edited = bool((old.provenance or {}).get("human_edited")) if old else False
            kept_edited += edited
            if opt["dry_run"]:
                # dry-run только считает: ни тему, ни вопрос, ни файл картинки не трогаем
                made += old is None
                upd += old is not None
                # считаем ровно тот кадр, который положим: на задачу один, первый по списку
                if figures and (old is None or not old.image) and (run / figures[0]).is_file():
                    drawn += 1
                continue
            topic, _ = Topic.objects.get_or_create(subject=subject, name=topic_name(book, scope))
            defaults = {
                "topic": topic,
                "text": plain_from_latex(t.get("markdown"))[:4000] or "(пустое условие)",
                "latex": t.get("markdown") or "",
                "latex_answer": t.get("answer") or "; ".join(t.get("answer_in") or []),
                "question_type": "open_answer",
                "language": opt["language"],
                "verification_status": "verified" if accepted else "draft",
                "uncertain": t.get("uncertain") or [],
                "provenance": {
                    "run": name, "page": page, "unit": t.get("word") or "задача",
                    "kind": t.get("kind"), "scope": t.get("scope"),
                    "book": book, "format": unit_format(t),
                    "pages": t.get("pages"), "loc": t.get("spans"),
                    "answer_pages": t.get("answer_pages") or [],
                    "answer_note": t.get("answer_note") or "",
                    "figures": figures,
                    "src": src.get("src"), "src_sha256": src.get("sha256"),
                    "scan_dpi": src.get("raster_dpi"), "render_dpi": render.get("dpi"),
                    "model": render.get("model"), "prompt_sha256": used.get("prompt_sha256"),
                },
            }
            if edited:
                # тему тоже бережём: если тренер перенёс задачу в свою тему
                # («это не книга, а отрывок»), перегон не должен вернуть её назад
                for f in ("text", "latex", "latex_answer", "verification_status", "topic"):
                    defaults[f] = getattr(old, f)
                for k in ("human_edited", "edited_at", "edited_by", "ocr_original"):
                    if k in old.provenance:
                        defaults["provenance"][k] = old.provenance[k]
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
            f"предмет «{subject.name}», язык {opt['language']}, принято человеком {took} из {len(review)} записей приёмки, "
            f"ручных правок сохранено {kept_edited}"
            + (" — dry-run, в базу не писано" if opt["dry_run"] else "")))
        if not opt["dry_run"]:
            self.stdout.write("сложность у всех проставлена дефолтом «Средний»: в оцифровке её нет, "
                              "разметку сделаем отдельно — не принимать её за размеченную")
