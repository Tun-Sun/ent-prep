# -*- coding: utf-8 -*-
"""Вынуть разбор решения из условия задачи в `solution_latex`.

    python manage.py split_solution_from_text [--book "..."] [--full 34533,34419] [--apply --decision "..."]

Правило, из которого растёт этот файл: условие задачи кончается там, где кончается
вопрос. Книги печатают разбор в том же абзаце, что и условие (Касаткина — таблицей
`| Дано: | Решение. … |`, Сборник МКТ — блоком `*Ответ:*`), и скан-конвейер клал
страницу целиком в `text`: ученик видел ответ задачи до того, как решил её, а
автопроверка могла прочитать его из собственного условия.

Разрезается ровно первая строка-маркер: таблица «Дано», абзац «Решение.»/«Решение:»
(в том числе внутри `$$…$$` и в курсиве) или строка «Ответ:». Всё до неё остаётся
условием, всё от неё и дальше уезжает в `solution_latex`.

Ничего не выдумываем: если маркер не найден, строка не тронута; если до маркера
ничего не осталось (вся строка — разбор, а условия нет), строка выходит списком,
а не пустым условием в банке. Правятся оба поля условия (`text` и `latex`), потому
что экран ученика читает `latex || text`, и left-only правка leave-бы спойлер живым.

Список old/new пишется файлом в обоих режимах: им же и откатывать.
"""
import collections
import io
import json
import os
import re

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from subjects.models import Question

# «$$Ответ: …$$» и «| *Дано:* | …» — маркер может тонуть в обёрстке, но всегда стоит
# в начале строки: внутри строки «Решение.» бывает частью условия, и резать по нему
# нельзя.
LEAD = re.compile(r'^\s*(?:\$\$)?\s*')
MARKER = re.compile(
    r'^(?:'
    r'\|\s*\*{0,2}\s*Дано\b'          # | Дано: |, | *Дано:*<br>…
    r'|_?\*{0,2}\s*Решение\s*[.:_]'   # Решение., _Решение._, *Решение:*
    r'|\*{0,2}\s*Ответ\s*:'           # *Ответ:* , Ответ:
    r')')

# грубый отбор в SQL: дословных совпаданий достаточно, точный разрез решает Python
COARSE = ('Дано', 'Решение', 'Ответ')


def split_condition(text):
    """(индекс строки-маркера, условие, разбор) или None, если разбора в тексте нет."""
    lines = (text or '').split('\n')
    for i, line in enumerate(lines):
        if MARKER.match(LEAD.sub('', line)):
            condition = '\n'.join(lines[:i]).rstrip()
            solution = '\n'.join(lines[i:]).strip()
            if not condition or not solution:
                return None
            return i, condition, solution
    return None


class Command(BaseCommand):
    help = ("Перенести разбор решения из условия в solution_latex; "
            "без --apply база не трогается.")

    def add_arguments(self, parser):
        parser.add_argument("--book", default="",
                            help="ограничить одной книгой (provenance.book, целиком и точно)")
        parser.add_argument("--apply", action="store_true", help="записать разрез в базу")
        parser.add_argument("--decision", default="",
                            help="чьё решение правит текст — ляжет в provenance.solution_split.by")
        parser.add_argument("--out", default="", help="куда положить список old/new (json)")
        parser.add_argument("--limit", type=int, default=8, help="сколько строк показать в консоли")
        parser.add_argument("--full", default="",
                            help="id через запятую: показать условие и разбор целиком")

    def handle(self, *args, **opt):
        if opt["apply"] and not opt["decision"]:
            raise CommandError("--apply без --decision: непонятно, чьё решение правит условия")

        plan, skipped = self.collect(opt["book"])
        self.stdout.write(f"строк с разбором в условии: {len(plan)} | не тронуто: {len(skipped)}")
        for why, n in sorted(collections.Counter(r["why"] for r in skipped).items()):
            self.stdout.write(f"   не тронута: {why} — {n}")
        for r in plan[:opt["limit"]]:
            self.stdout.write(f"   id {r['id']:>6} {r['book'][:28]:<28} стр {r['page']} · "
                              f"условие {len(r['old_text'])} → {len(r['new_text'])} | "
                              f"разбор {len(r['solution'])}")
        if len(plan) > opt["limit"]:
            self.stdout.write(f"   … ещё {len(plan) - opt['limit']}")
        for pk in self.full_ids(opt["full"]):
            row = next((r for r in plan if r["id"] == pk), None)
            if row is None:
                self.stdout.write(self.style.WARNING(f"--- id {pk}: в плане не найден"))
                continue
            self.stdout.write(f"--- id {pk} {row['book']} стр {row['page']} № {row['num']}")
            self.stdout.write(f"    СТАЛО (text):\n{row['new_text']}")
            self.stdout.write(f"    УЕХАЛО В solution_latex:\n{row['solution']}")

        listing = self.dump(plan, skipped, opt)
        self.stdout.write(f"список: {listing}")
        if not opt["apply"]:
            self.stdout.write(self.style.WARNING("сухой прогон: база не тронута"))
            return
        self.write(plan, opt["decision"])
        self.stdout.write(self.style.SUCCESS(
            f"разборов вынесено: {len(plan)} | список для откат: {listing}"))

    def full_ids(self, raw):
        return [int(x) for x in re.findall(r'\d+', raw or '')]

    def collect(self, book):
        """Что разрежется и почему остальное не тронуто."""
        qs = Question.objects.all()
        if book:
            qs = qs.filter(provenance__book=book)
        plan, skipped = [], []
        for q in qs.iterator(chunk_size=500):
            if not any(word in (q.text or '') or word in (q.latex or '') for word in COARSE):
                continue
            prov = q.provenance or {}
            base = {"id": q.pk, "book": prov.get("book") or "", "page": prov.get("page"),
                    "num": prov.get("num"), "human_edited": bool(prov.get("human_edited"))}
            cut_text = split_condition(q.text or '')
            cut_latex = split_condition(q.latex or '')
            if not cut_text and not cut_latex:
                # слово есть, а разбора отдельной строкой нет: «Дано» упоминается внутри
                # условия — резать нечего, строка остаётся как есть.
                skipped.append({**base, "why": "маркера нет отдельной строкой"})
                continue
            if q.solution_latex:
                skipped.append({**base, "why": "solution_latex уже занят — решает редактура"})
                continue
            plan.append({**base,
                         "old_text": q.text, "new_text": cut_text[1] if cut_text else q.text,
                         "old_latex": q.latex, "new_latex": cut_latex[1] if cut_latex else q.latex,
                         "old_solution": q.solution_latex,
                         "solution": (cut_text or cut_latex)[2]})
        return plan, skipped

    def dump(self, plan, skipped, opt):
        stamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        path = opt["out"] or f"solution_split_{stamp}.json"
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        json.dump({"book": opt["book"], "apply": bool(opt["apply"]),
                   "decision": opt["decision"], "prepared_at": timezone.now().isoformat(),
                   "counts": {"plan": len(plan), "skipped": len(skipped)},
                   "plan": plan, "skipped": skipped},
                  io.open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return path

    def write(self, plan, decision):
        now = timezone.now().isoformat()
        for r in plan:
            q = Question.objects.get(pk=r["id"])
            prov = dict(q.provenance or {})
            prov["solution_split"] = {"at": now, "by": decision,
                                      "chars": len(r["old_text"]) - len(r["new_text"])}
            q.text = r["new_text"]
            q.latex = r["new_latex"]
            q.solution_latex = r["solution"]
            q.provenance = prov
            q.save(update_fields=["text", "latex", "solution_latex", "provenance"])
