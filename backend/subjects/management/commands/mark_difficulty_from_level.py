# -*- coding: utf-8 -*-
"""Сложность из напечатанного в книге уровня.

    python manage.py mark_difficulty_from_level [--subject physics] [--dry-run]

Импорт ставит «Средний» молча — это дефолт поля, а не разметка. Здесь проставляем
только то, что книга сказала сама: у листа «Криволинейное движение» задачи подписаны
уровнем («Начальный», «Достаточный», «Высокий» …), и этот уровень лежит в паспорте
строки (provenance.scope). Всё остальное остаётся «Средний» и честно помечено как
неразмеченное — выдумывать сложность по длине формул не будем.

Значение пишем в provenance.difficulty_source, чтобы в банке было видно, откуда
взялась сложность: человек её правит, а мы не перемалываем данные без следа.
"""
from collections import Counter

from django.core.management.base import BaseCommand

from subjects.models import Question

# Шкала книги — не три градации, а восемь подписей. Сводим к трём, стараясь держать
# порядок «начальный < средний < достаточный < высокий» и нумерованную лесенку
# «первый < второй < третий < четвёртый» на тех же местах.
LEVEL_TO_DIFFICULTY = {
    "начальный уровень": "easy",
    "первый уровень": "easy",
    "средний уровень": "medium",
    "второй уровень": "medium",
    "третий уровень": "medium",
    "достаточный уровень": "medium",
    "высокий уровень": "hard",
    "четвертый уровень": "hard",
    "четвёртый уровень": "hard",
}


class Command(BaseCommand):
    help = "Проставить сложность там, где книга напечатала уровень задачи."

    def add_arguments(self, parser):
        parser.add_argument("--subject", default="physics")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opt):
        qs = Question.objects.filter(source_type="book_scan", topic__subject__slug=opt["subject"])
        hit = Counter()
        miss = Counter()
        for q in qs:
            scope = ((q.provenance or {}).get("scope") or "").strip().lower()
            new = LEVEL_TO_DIFFICULTY.get(scope)
            if not new:
                miss[scope or "(без области)"] += 1
                continue
            hit[(scope, new, q.difficulty != new)] += 1
            if not opt["dry_run"]:
                prov = dict(q.provenance or {})
                # метку ставим и когда значение совпало с дефолтом: «Средний» по уровню
                # книги и «Средний» потому, что никто не размечал — это разные строки,
                # и на глаз они неразличимы
                prov["difficulty_source"] = f"уровень из книги: {(q.provenance or {}).get('scope')}"
                q.difficulty = new
                q.provenance = prov
                q.save(update_fields=["difficulty", "provenance"])
        marked = sum(c for (s, n, changed), c in hit.items() if changed)
        self.stdout.write(self.style.SUCCESS(
            "{}: поставили сложность {} строкам по {} напечатанным уровням, "
            "{} уже стояла правильно — {}".format(
                opt["subject"], marked, len({k[0] for k in hit}),
                sum(c for (s, n, changed), c in hit.items() if not changed),
                "dry-run, в базу не писано" if opt["dry_run"] else "в базе")))
        for (scope, new, changed), c in sorted(hit.items()):
            self.stdout.write("    {:26s} -> {:6s} {:>3} строки".format(scope, new, c))
        if miss:
            self.stdout.write("  без напечатанного уровня (остались «Средний» без разметки): {} строк, {}".format(
                sum(miss.values()),
                ", ".join("{} ({})".format(k, v) for k, v in sorted(miss.items(), key=lambda kv: -kv[1])[:6])))
