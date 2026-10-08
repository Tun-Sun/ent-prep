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

Отдельно стоит пакетная приёмка (provenance.accepted_by): она решена про статус,
а не про текст, поэтому перегон оставляет «проверено», но условие обновляет —
иначе принятая строка навсегда застыла бы в текущем состоянии оцифровки.

Из книги в паспорт строки едут и её печатные метки: номер задачи (provenance.num)
и буква уровня (provenance.level). По ним банк сверяют с разворотом, а по букве
уровня ещё и проставляют сложность (A → Лёгкий, B → Сложный) — но только там, где
её не решал человек: ни ручная правка, ни прежняя разметка не перемалываются.
"""
import json
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from subjects.models import Answer, Question, Subject, Topic, plain_from_latex


def topic_name(book, scope):
    return f"{book} · {scope}" if book else scope


# Буква напечатанного уровня в сборниках ЕНТ: под «A» дают базовый, под «B» —
# повышенный. Парсер уже свёл кириллические гомоглифы к латинице, поэтому здесь
# два символа, а не четыре. Перевод «А → Лёгкий, В → Сложный» решил владелец банка.
LEVEL_TO_DIFFICULTY = {"A": "easy", "B": "hard"}


def unit_format(t):
    """Тест, задача или теория — по тому, что уже насчитал парсер границ.

    Отдельная метка нужна, потому что тест без ключа ответа в банке мешает
    вычитке задач: тренер листает 300 условий, а 20 из них — совсем другой формат.
    Теоретический лист — третий: единицу для него задаёт не номер, а вся страница,
    и называть её задачей было бы вранём в фильтре.
    """
    if t.get("kind") == "theory":
        return "теория"
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

        made = upd = drawn = took = kept_edited = kept_accepted = orphaned = noted = relaid = 0
        opts_written = 0
        levelled = 0
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
            rev = review.get(t.get("key") or "") or {}
            accepted = bool(rev.get("ok"))
            took += accepted
            # Заметка приёмки — не флаг «проверено». Её пишут, когда знак сверен глазами,
            # но спор остался (опечатка книги, а не ошибка распознавания): строка остаётся
            # черновиком, а вывод глаз доезжает до банка и переживает перегон.
            if rev.get("note"):
                noted += 1
            figures = [f for f in (t.get("figures") or []) if isinstance(f, str)]
            # Варианты теста: их две десятки на весь банк, и без строк ответа они
            # остаются куском текста, который нечем отрендерить как выбор.
            opts = t.get("options_list") or []
            is_test = len(opts) >= 2
            old = Question.objects.filter(source_type="book_scan", external_id=ext).first()
            # Правка тренера в банке важнее перегоня: второй импорт молча вернул бы
            # опечатку, которую человек уже исправил глазами, и снял бы его статус.
            edited = bool((old.provenance or {}).get("human_edited")) if old else False
            kept_edited += edited
            # Приёмка пакетом в окне банка — решение про статус, а не про текст:
            # строку человек видел глазами, а условие мы ещё дооцифровываем. Поэтому
            # перегон оставляет её статус, но обновляет latex (в edited-строках статус
            # и так берётся из базы, там приёмка просто переезжает вместе с меткой).
            bank_accepted = bool((old.provenance or {}).get("accepted_by")) if old else False
            kept_accepted += bank_accepted
            # Сложность из напечатанной буквы уровня. Ставим только там, где её ещё
            # никто не решал: difficulty_source — след любого решённого уровня (этим
            # импортом или командой разметки), а ручная правка — слово человека.
            level = (t.get("level") or "").upper()
            diff = LEVEL_TO_DIFFICULTY.get(level)
            premarked = bool((old.provenance or {}).get("difficulty_source")) if old else False
            sets_level = bool(diff) and not edited and not premarked
            if opt["dry_run"]:
                # dry-run только считает: ни тему, ни вопрос, ни файл картинки не трогаем
                made += old is None
                upd += old is not None
                # считаем ровно тот кадр, который положим: на задачу один, первый по списку
                if figures and (run / figures[0]).is_file() and (
                        old is None or not old.image
                        # или прогон стал показывать другой вырез той же страницы
                        or (old.image_ref or "") not in ("", f"{name}:{Path(figures[0]).name}")):
                    drawn += 1
                if is_test and not edited:
                    opts_written += len(opts)
                levelled += sets_level
                continue
            topic, _ = Topic.objects.get_or_create(subject=subject, name=topic_name(book, scope))
            defaults = {
                "topic": topic,
                "text": plain_from_latex(t.get("markdown"))[:4000] or "(пустое условие)",
                "latex": t.get("markdown") or "",
                "latex_answer": t.get("answer") or "; ".join(t.get("answer_in") or []),
                "question_type": "single_choice" if is_test else "open_answer",
                "language": opt["language"],
                "verification_status": "verified" if accepted else "draft",
                "uncertain": t.get("uncertain") or [],
                "provenance": {
                    "run": name, "page": page, "unit": t.get("word") or "задача",
                    # напечатанный номер и буква уровня: по номеру строку и сверяют с
                    # книгой («это задача 12 блока 2»), а в банке её раньше не было видно —
                    # номер жил только внутри external_id, который никто не показывает
                    "num": t.get("num") or "", "level": level,
                    "kind": t.get("kind"), "scope": t.get("scope"),
                    "book": book, "format": unit_format(t),
                    "pages": t.get("pages"), "loc": t.get("spans"),
                    "answer_pages": t.get("answer_pages") or [],
                    "answer_note": t.get("answer_note") or "",
                    "figures": figures,
                    # заметка приёмки: что увидел глаз на скане и почему спор не снят
                    "review_note": rev.get("note") or "", "review_by": rev.get("by") or "",
                    "src": src.get("src"), "src_sha256": src.get("sha256"),
                    "scan_dpi": src.get("raster_dpi"), "render_dpi": render.get("dpi"),
                    "model": render.get("model"), "prompt_sha256": used.get("prompt_sha256"),
                },
            }
            # Пометка «сложность взята из напечатанного уровня книги» — вывод из
            # разворота скана, а не из распознавания: новый прогон её не опровергает.
            # Без переноса перегон стирал 62 пометки, и размеченное строкой
            # «Средний» становилось неразличимым от «Средний, потому что никто не трогал».
            if old is not None and (old.provenance or {}).get("difficulty_source"):
                defaults["provenance"]["difficulty_source"] = old.provenance["difficulty_source"]
            if sets_level:
                # дефолт «Средний» снят книгой: строка стоит на той ступени, которую
                # напечатал составитель, и паспорт говорит, откуда это взялось
                defaults["difficulty"] = diff
                defaults["provenance"]["difficulty_source"] = f"буква уровня из книги: {level}"
                levelled += 1
            if edited:
                # тему тоже бережём: если тренер перенёс задачу в свою тему
                # («это не книга, а отрывок»), перегон не должен вернуть её назад
                for f in ("text", "latex", "latex_answer", "verification_status", "topic"):
                    defaults[f] = getattr(old, f)
                for k in ("human_edited", "edited_at", "edited_by", "ocr_original"):
                    if k in old.provenance:
                        defaults["provenance"][k] = old.provenance[k]
            if bank_accepted:
                if not edited:
                    defaults["verification_status"] = old.verification_status
                for k in ("accepted_by", "accepted_at"):
                    defaults["provenance"][k] = old.provenance[k]
            q, new = Question.objects.update_or_create(
                source_type="book_scan", external_id=ext, defaults=defaults)
            made += new
            upd += not new
            if is_test and not edited:
                # Варианты едут отдельными строками, а условие с ними — нет: напечатанный
                # список остаётся в тексте как был. Ключ ответа не выдумываем: в отсканированной
                # части его нет, поэтому ни один вариант не помечен правильным.
                q.answers.all().delete()
                for o in opts:
                    Answer.objects.create(question=q, text=o["text"][:300], is_correct=False)
                opts_written += len(opts)
            # выкройка — один кадр на задачу: второй в источнике бывает дублем с оборота
            if figures:
                want = f"{name}:{Path(figures[0]).name}"
                prev_ref = q.image_ref or ""
                # image_ref — ссылка на файл прогона; присвоить до save(), иначе save()
                # уйдёт в БД с тем, что было раньше, и поле останется пустым
                if prev_ref != want:
                    q.image_ref = want
                    q.save(update_fields=["image_ref"])
                f = run / figures[0]
                # Кадр перекладываем, когда прогон стал показывать другой вырез той же
                # страницы: «картинка уже есть» для импорта раньше значило «трогать
                # нечего», и задача про рис. 1.32 вечно сидела с рисунком 1.30.
                if f.is_file() and (not q.image or (prev_ref and prev_ref != want)):
                    q.image.save(f"{name}_p{page:02d}_{f.name}", ContentFile(f.read_bytes()), save=True)
                    drawn += 1
                    relaid += bool(prev_ref) and prev_ref != want
            elif not edited and (q.image_ref or "").startswith(f"{name}:"):
                # Картинка задачи обязана быть рисунком из её тела: прогон перестал
                # считать выкройку содержимым — и на задаче Касаткиной оставался логотип
                # бланка «INTELLECT», положенный до того, как шапку стали срезать.
                # Файл в media не сносим: поле снимаем, удаление решает человек.
                q.image_ref = ""
                q.image = None
                q.save(update_fields=["image_ref", "image"])
                orphaned += 1
        self.stdout.write(self.style.SUCCESS(
            f"{name}: создано {made}, обновлено {upd}, новых тем {tnew}, картинок положено {drawn}, "
            f"вариантов теста строками ответа {opts_written}, "
            f"картинок снято по чужому кадру {orphaned}, переложено кадров {relaid}, "
            f"предмет «{subject.name}», язык {opt['language']}, принято человеком {took} из {len(review)} записей приёмки, "
            f"со заметкой со скана {noted}, ручных правок сохранено {kept_edited}, "
            f"принято пакетом в банке {kept_accepted}, сложности по букве уровня {levelled}"
            + (" — dry-run, в базу не писано" if opt["dry_run"] else "")))
        if not opt["dry_run"]:
            self.stdout.write(self.style.SUCCESS(
                f"по букве уровня из книги сложность проставлена {levelled} строкам "
                "(A → Лёгкий, B → Сложный), остальным — дефолт «Средний»: в оцифровке "
                "своей сложности нет, и не принимать этот «Средний» за размеченный"))
