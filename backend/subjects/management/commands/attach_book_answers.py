# -*- coding: utf-8 -*-
"""Присоединить ответы книги к уже залитым строкам банка — по напечатанному номеру.

    python manage.py attach_book_answers \\
        --answers-run сканави_ответы_глава11_20261010_120000 \\
        --book "Сканави, стериометрия"

Нужен отдельный шаг, потому что ответы в книгах печатаются не под задачей, а блоком
в конце главы (или в конце книги), и этот блок чаще всего лежит вне отсканированных
условий: у Сканави 239 строк и 0 ответов именно поэтому — скан 253–274 кончается там,
где условия. Перегон импорта тут не поможет: external_id единицы содержит её страницу,
поэтому ответы из другого прогона пришли бы новыми строками-дублями.

Ничего не выдумываем: берётся только то, что напечатано в доске ответов другого
прогона, и только там, где номер в книге один. Спорное выходит списком, а не в базу:
номер под несколькими заголовками, тот же номер в нескольких разделах одной области
(у Касаткиной «Решение отдельных задач» напечатано трижды, и из трёх счётов собирается
один ответ из двух чужих записей), ответ задачи с другой страницы того же прогона
(номера в главах Касаткиной идут отдельными счётами: условие с.31 и задача с.99 — это
два разных «17»), номер-дубль внутри книги, запись длиной с условие (так выглядит
чужое решение), строка с правкой человека (её ответ правится только редактурой в окне
банка).

Пишутся ровно два поля: latex_answer и provenance.answer_from. Текст, тема, статус
приёмки, сложность и спорные знаки не трогаются — это решения не наши. Список old/new
уходит файлом в обоих режимах: им же и откатывать.
"""
import collections, io, json, os, re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from subjects.models import Question

# «11.198.» и «11.198» — один номер: в доске ответов точка при числе знак конца записи,
# а не часть нумерации главы, поэтому сверка без её снятия не сходится.
TAIL = ".*°'′”\\ \t"
MAX_ANSWER = 300      # длиннее — не ответ, а разбор: в поле ответа он читается чужим решением
MAX_VALUES = 3        # сколько записей склеивать в одно поле — столько же берёт tasks.attach


def norm(n):
    return (n or "").strip().strip(TAIL).replace(" ", "")


class Command(BaseCommand):
    help = ("Приклеить ответы из доски ответов другого прогона к строкам банка по "
            "напечатанному номеру; без --apply база не трогается.")

    def add_arguments(self, parser):
        parser.add_argument("--answers-run", required=True,
                            help="прогон с ответами: имя в INGEST_RUNS_DIR или путь к папке")
        parser.add_argument("--book", required=True,
                            help="provenance.book целевых строк, целиком и точно")
        parser.add_argument("--apply", action="store_true", help="записать ответы в базу")
        parser.add_argument("--decision", default="",
                            help="чьё решение — ляжет в provenance.answer_from.by")
        parser.add_argument("--out", default="", help="куда положить список (json)")
        parser.add_argument("--limit", type=int, default=12,
                            help="сколько строк показать в консоли")

    def handle(self, *args, **opt):
        if opt["apply"] and not opt["decision"]:
            raise CommandError("--apply без --decision: непонятно, чьё решение кладёт ответы")
        folder = self.resolve_folder(opt["answers_run"])
        run_name = os.path.basename(folder.rstrip("/\\"))
        answers = self.read_board(folder)
        if not answers:
            raise CommandError(
                f"в {folder} нет ни одной записи ответа — ни блоком «Ответы / Жауаптар», "
                f"ни напечатанным внутри единицы. Либо страницы с ответами не сканированы, "
                f"либо их заголовок парсер не узнал: сначала сверьте папку прогона глазами, "
                f"приклеивать нечего")

        qs = Question.objects.filter(source_type="book_scan", provenance__book=opt["book"])
        if not qs.count():
            raise CommandError(f"в банке нет строк книги {opt['book']!r} — проверьте --book")

        rows, skipped, seen = self.index_rows(qs)
        plan, unsure, no_board = self.match(rows, answers, run_name, seen)
        if no_board:
            skipped["номера нет на доске ответов"] = no_board

        self.stdout.write(f"прогон с ответами: {run_name} | записей ответа {len(answers)}, "
                          f"из них номеров {len({a['num'] for a in answers})}")
        self.stdout.write(f"строк книги {opt['book']!r}: {qs.count()} | с напечатанным "
                          f"номером и пустым ответом: {sum(len(v) for v in rows.values())}")
        for why, n in sorted(skipped.items()):
            self.stdout.write(f"   не участвует: {why} — {n}")
        self.stdout.write(f"подходит к приклеиванию: {len(plan)} | спорных: {len(unsure)}")
        for why, n in sorted(collections.Counter(u["why"] for u in unsure).items()):
            self.stdout.write(f"   спорно: {why} — {n}")
        for p in plan[:opt["limit"]]:
            self.stdout.write(f"   id {p['id']:>6} № {p['num']:<9} → "
                              f"{p['answer'][:80]!r} (с. {p['answer_page']})")
        if len(plan) > opt["limit"]:
            self.stdout.write(f"   … ещё {len(plan) - opt['limit']}")

        listing = self.write_listing(opt, folder, run_name, plan, unsure, skipped,
                                     qs.count(), sum(len(v) for v in rows.values()))
        self.stdout.write(f"список: {listing}")
        if not opt["apply"]:
            self.stdout.write(self.style.WARNING("сухой прогон: база не тронута"))
            return
        self.write(plan, run_name, opt["decision"])
        left = Question.objects.filter(source_type="book_scan", provenance__book=opt["book"],
                                       latex_answer="").count()
        self.stdout.write(self.style.SUCCESS(f"ответов положено: {len(plan)} | "
                                             f"без ответа у этой книги осталось: {left}"))

    def resolve_folder(self, name):
        p = Path(name)
        if not p.is_absolute():
            p = Path(settings.INGEST_RUNS_DIR) / name
        if not (p / "tasks.json").is_file():
            raise CommandError(f"нет {p / 'tasks.json'} — прогон с ответами надо сначала "
                               f"распознать и разобрать на единицы")
        return str(p)

    def read_board(self, folder):
        """Доска ответов как её положил tasks.py; своих интерпретаций не добавляем.

        Ответы читаем из двух мест прогона: блок «Ответы» отдельной страницей (там и
        лежит в основном) и ответ, напечатанный внутри самой единицы («Ответ: …») —
        по-разному они расходятся по страницам, и у Касаткиной второй случай единственный.
        """
        d = json.load(io.open(os.path.join(folder, "tasks.json"), encoding="utf-8"))
        out = []
        for entry in d.get("answers") or []:
            num = norm(entry.get("num"))
            if not num:
                continue
            for v in entry.get("values") or []:
                text = (v.get("text") or "").strip()
                if text:
                    out.append({"num": num, "scope": entry.get("scope") or "",
                                "text": text, "page": v.get("page"),
                                "block": v.get("block") or "", "pages": [],
                                "from_unit": False})
        for t in d.get("tasks") or []:
            num = norm(t.get("num"))
            if not num:
                continue
            pages = list(t.get("pages") or [])
            for text in ([t["answer"]] if t.get("answer") else []) + list(t.get("answer_in") or []):
                text = (text or "").strip()
                if text:
                    out.append({"num": num, "scope": t.get("scope") or "",
                                "text": text, "page": pages[0] if pages else None,
                                "block": t.get("block") or "", "pages": pages,
                                "from_unit": True})
        return out

    def index_rows(self, qs):
        """Ключ сверки — provenance.num, тот же напечатанный номер, что и в доске.
        Дубль номера в одной книге не разбираем: у Касаткиной задачи и разобранные
        решения идут двумя независимыми счётами, и «первый по номеру» — чужое решение.

        seen — все номера книги, включая отброшенные: без него номер строки, которую
        правил человек, попал бы в «такого номера в банке нет», хотя строка в банке есть.
        """
        rows, skipped, seen = {}, {}, set()
        for q in qs.only("id", "latex_answer", "provenance"):
            prov = q.provenance or {}
            num = norm(prov.get("num"))
            if num:
                seen.add(num)
            why = None
            if not num:
                why = "в паспорте нет напечатанного номера"
            elif (q.latex_answer or "").strip():
                why = "ответ уже есть в банке"
            elif prov.get("human_edited"):
                why = "строка правилась человеком — ответ только редактурой"
            if why:
                skipped[why] = skipped.get(why, 0) + 1
                continue
            rows.setdefault(num, []).append({"id": q.id, "num": num,
                                             "scope": prov.get("scope") or "",
                                             "run": prov.get("run") or "",
                                             "page": prov.get("page")})
        return rows, skipped, seen

    def match(self, rows, answers, run_name="", seen=frozenset()):
        by_num = {}
        for a in answers:
            by_num.setdefault(a["num"], []).append(a)
        # строки с напечатанным номером, которого на доске нет: без этой цифры
        # «подходит к приклеиванию: 2» читается как «больше нечего», а это не так
        no_board = sum(len(v) for num, v in rows.items() if num not in by_num)

        plan, unsure = [], []
        for num, targets in sorted(rows.items()):
            got = by_num.get(num)
            if not got:
                continue
            if len(targets) > 1:
                unsure.append({"id": [t["id"] for t in targets], "num": num,
                               "why": "номер в книге стоит на нескольких строках"})
                continue
            t = targets[0]
            # Ответ, напечатанный внутри самой задачи, живёт на её страницах: если прогон
            # с ответами — тот же прогон, что у строки, номер без страницы не различает
            # главы (на Касаткиной условие с.31 получило ответ задачи с.99 той же книги).
            if t["run"] == run_name and any(g["from_unit"] for g in got):
                got = [g for g in got if not g["from_unit"] or t["page"] in g["pages"]]
                if not got:
                    unsure.append({"id": t["id"], "num": num,
                                   "why": "ответ напечатан в другой задаче с тем же номером"})
                    continue
            same = [g for g in got if not t["scope"] or g["scope"] == t["scope"]] or got
            if len({g["scope"] for g in same}) > 1:
                unsure.append({"id": t["id"], "num": num,
                               "why": "номер под несколькими заголовками"})
                continue
            # Раздел — вторая половина той же ловушки: имя области у Касаткиной
            # «Решение отдельных задач» напечатано трижды, по разу на параграф, и без
            # него из трёх разных счётов собирается один ответ из двух чужих записей.
            blocks = {g["block"] for g in same if g.get("block")}
            if len(blocks) > 1:
                unsure.append({"id": t["id"], "num": num,
                               "why": "один номер в нескольких разделах с одинаковым "
                                      "заголовком области"})
                continue
            text = "; ".join(g["text"] for g in same[:MAX_VALUES])
            if len(text) > MAX_ANSWER:
                unsure.append({"id": t["id"], "num": num,
                               "why": f"запись {len(text)} зн. — разбор, а не ответ"})
                continue
            plan.append({"id": t["id"], "num": num, "scope": t["scope"], "answer": text,
                         "answer_page": sorted({g["page"] for g in same if g.get("page")}),
                         "answer_block": sorted(blocks), "old_answer": ""})
        covered = {p["num"] for p in plan} | {u["num"] for u in unsure} | set(seen)
        for num in sorted(set(by_num) - covered):
            unsure.append({"id": None, "num": num, "why": "такого номера в банке нет"})
        return plan, unsure, no_board

    def write_listing(self, opt, folder, run_name, plan, unsure, skipped, total, candidates):
        stamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        slug = re.sub(r"[^0-9A-Za-z\u0400-\u04FF]+", "_", opt["book"]).strip("_")[:40]
        path = opt["out"] or os.path.join(folder, f"attach_answers_{slug}_{stamp}.json")
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        json.dump({"book": opt["book"], "answers_run": run_name, "apply": bool(opt["apply"]),
                   "decision": opt["decision"], "prepared_at": timezone.now().isoformat(),
                   "counts": {"bank_rows": total,
                              "candidates": candidates,
                              "plan": len(plan), "unsure": len(unsure), "skipped": skipped},
                   "plan": plan, "unsure": unsure},
                  io.open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return path

    def write(self, plan, run_name, decision):
        now = timezone.now().isoformat()
        for p in plan:
            q = Question.objects.get(pk=p["id"])
            prov = dict(q.provenance or {})
            # метка «ответа в отсканированной части нет» остаётся: она про скан условий,
            # и экран показывает её только там, где ответа по-прежнему нет
            prov["answer_from"] = {"run": run_name, "pages": p["answer_page"],
                                   "by": decision, "at": now}
            q.latex_answer = p["answer"]
            q.provenance = prov
            q.save(update_fields=["latex_answer", "provenance"])
