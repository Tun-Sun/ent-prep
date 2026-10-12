# -*- coding: utf-8 -*-
"""Пересобрать `text` у строк банка из `latex` — вернуть формулы тем экранам, что читают text.

    python manage.py refresh_scan_text
    python manage.py refresh_scan_text --book "Сканави, стериометрия" \
        --apply --decision "текст не меняется, ограничители возвращает правка plain_from_latex"

`text` — поле производное: его пишет plain_from_latex из latex. Функция снимала `$`, и там,
где экран читает text (тест, результаты ученика и тренера, «Вопросы»), KaTeX стало нечего
выделять: на проде 433 строки банка из 663 показывали сырые `\\text{ м}` и `0{,}029`.
Содержательного здесь ничего не меняется — latex не трогается, пересборка показывает то же
самое, что банк показывает уже.

Пишется ровно одно поле: text. Тема, сложность, статус приёмки, ответ и сам latex не
трогаются. Строку, которую правил человек, не трогаем тоже: её text мог быть вычитан по
скану, а пересборка берёт latex — спорное уходит списком. Список old/new пишется файлом в
обоих режимах: им же и откатывать.
"""
import io, json, os, re
from collections import Counter

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from subjects.models import Question, plain_from_latex

INLINE = re.compile(r"\$[^$\n]+?\$")


class Command(BaseCommand):
    help = ("Пересобрать text из latex у строк банка; без --apply база не тронута.")

    def add_arguments(self, parser):
        parser.add_argument("--book", default="",
                            help="provenance.book, целиком и точно; пусто — весь банк")
        parser.add_argument("--apply", action="store_true", help="записать пересобранный text")
        parser.add_argument("--decision", default="",
                            help="чьё решение — ляжет в provenance.text_refresh.by")
        parser.add_argument("--out", default="", help="куда положить список (json)")
        parser.add_argument("--limit", type=int, default=12, help="сколько строк показать в консоли")

    def handle(self, *args, **opt):
        if opt["apply"] and not opt["decision"]:
            raise CommandError("--apply без --decision: непонятно, чьё решение пересобирает текст")

        qs = Question.objects.filter(source_type="book_scan").exclude(latex="")
        if opt["book"]:
            qs = qs.filter(provenance__book=opt["book"])
            if not qs.exists():
                raise CommandError(f"в банке нет строк книги {opt['book']!r} — проверьте --book")

        plan, edited, same = [], [], 0
        for q in qs.order_by("id"):
            new = plain_from_latex(q.latex)[:4000] or "(пустое условие)"
            if new == q.text:
                same += 1
                continue
            row = {"id": q.id, "num": (q.provenance or {}).get("num") or "",
                   "book": (q.provenance or {}).get("book") or "",
                   "old": q.text, "new": new,
                   "формул стало": len(INLINE.findall(new)) - len(INLINE.findall(q.text))}
            (edited if (q.provenance or {}).get("human_edited") else plan).append(row)

        total_bank = Question.objects.filter(source_type="book_scan").count()
        without_latex = total_bank - qs.count()
        self.stdout.write(f"строк банка: {total_bank} | с latex: {qs.count()} | "
                          f"без latex (не трогаем): {without_latex}")
        self.stdout.write(f"text уже совпадает: {same} | пересоберётся: {len(plan)} | "
                          f"правил человек (не пишем): {len(edited)}")
        self.stdout.write(f"формул вернётся: {sum(p['формул стало'] for p in plan)} "
                          f"на {sum(1 for p in plan if p['формул стало'] > 0)} строках")
        for p in plan[:opt["limit"]]:
            self.stdout.write(f"   id {p['id']:>6} № {p['num']:<9} +{p['формул стало']:>2} формул | "
                              f"{p['old'][:60]!r} → {p['new'][:60]!r}")
        if len(plan) > opt["limit"]:
            self.stdout.write(f"   … ещё {len(plan) - opt['limit']}")
        for p in edited[:opt["limit"]]:
            self.stdout.write(f"   спорно: id {p['id']:>6} № {p['num']:<9} — строка правил человек, "
                              f"её текст правится только окном банка")

        listing = self.write_listing(opt, plan, edited, same, without_latex)
        self.stdout.write(f"список: {listing}")
        if not opt["apply"]:
            self.stdout.write(self.style.WARNING("сухой прогон: база не тронута"))
            return

        self.write(plan, opt["decision"])
        silent = sum(1 for p in plan if not INLINE.search(p["new"]))
        self.stdout.write(self.style.SUCCESS(
            f"пересобрано: {len(plan)} | строк без формул и после пересборки: {silent} "
            f"(в них latex напечатан текстом)"))

    def write_listing(self, opt, plan, edited, same, without_latex):
        stamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        slug = re.sub(r"[^0-9A-Za-zЀ-ӿ]+", "_", opt["book"] or "весь_банк").strip("_")[:40]
        path = opt["out"] or os.path.join(settings.INGEST_RUNS_DIR, f"refresh_text_{slug}_{stamp}.json")
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        json.dump({"book": opt["book"] or "весь банк", "apply": bool(opt["apply"]),
                   "decision": opt["decision"], "prepared_at": timezone.now().isoformat(),
                   "counts": {"plan": len(plan), "human_edited": len(edited),
                              "already_same": same, "without_latex": without_latex},
                   "plan": plan, "unsure": edited},
                  io.open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return path

    def write(self, plan, decision):
        now = timezone.now().isoformat()
        for p in plan:
            q = Question.objects.get(pk=p["id"])
            if q.text != p["old"]:
                continue  # строку правили между списком и записью: перетирать чужое не будем
            prov = dict(q.provenance or {})
            prov["text_refresh"] = {"by": decision, "at": now, "from": "latex"}
            q.text = p["new"]
            q.provenance = prov
            q.save(update_fields=["text", "provenance"])
