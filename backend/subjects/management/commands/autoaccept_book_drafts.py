# -*- coding: utf-8 -*-
"""Приёмка черновиков банка автоматом — с честной меткой, кто их принял.

    python manage.py autoaccept_book_drafts --dry-run \
        --decision "решение владельца 2026-10-07: ресурсов на вычитку нет"

Поле «проверено» решает показ: такие строки уже уходят в тесты и дуэли ученикам
(tests/views.py, gamification/views.py). Поэтому здесь статус меняется ровно так
же, как от кнопки приёмки, но provenance.accepted_mode = "auto" и accepted_by
хранит текст решения, а не логин аккаунта. Без этой разницы «проверено» значило
бы «человек смотрел», и через месяц никто не отличил бы вычитанное от догадки
модели — ни в интерфейсе, ни при разборе претензии от ученика.

Перегон импорта такую строку оставит «проверено» (он бережёт accepted_by как
факт приёмки) и обновит условие — ровно как с пакетной приёмкой человека.
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from subjects.models import Question


class Command(BaseCommand):
    help = ("Отметить черновики оцифровки принятыми автоматом: статус «проверено» "
            "с меткой, что глаз человека на строке не был.")

    def add_arguments(self, parser):
        parser.add_argument("--decision", required=True,
                            help="чьё это решение и почему — ляжет в accepted_by")
        parser.add_argument("--run", default="", help="только этот прогон (provenance.run)")
        parser.add_argument("--subject", default="", help="slug предмета, по умолчанию все")
        parser.add_argument("--only-with-answer", action="store_true",
                            help="не трогать строки, где в источнике нет ответа")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opt):
        qs = Question.objects.filter(source_type="book_scan", verification_status="draft")
        if opt["run"]:
            qs = qs.filter(provenance__run=opt["run"])
        if opt["subject"]:
            qs = qs.filter(topic__subject__slug=opt["subject"])
        total = qs.count()
        if total == 0:
            raise CommandError("черновиков под этот фильтр нет — менять нечего")

        no_answer = qs.exclude(latex_answer="").count()
        no_answer = total - no_answer
        self.stdout.write(f"черновиков под фильтр: {total} | с напечатанным ответом: "
                          f"{total - no_answer} | без ответа: {no_answer}")
        if opt["only_with_answer"]:
            qs = qs.exclude(latex_answer="")
            self.stdout.write(f"из них возьмём с ответом: {qs.count()}")

        now = timezone.now().isoformat()
        stamp = f"автоматом: {opt['decision']}"
        changed = 0
        for q in qs:
            changed += 1
            if opt["dry_run"]:
                continue
            prov = dict(q.provenance or {})
            q.verification_status = "verified"
            prov["accepted_by"] = stamp
            prov["accepted_at"] = now
            prov["accepted_mode"] = "auto"
            q.provenance = prov
            q.save(update_fields=["verification_status", "provenance"])
        verb = "сухой прогон: принято было бы" if opt["dry_run"] else "принято автоматом"
        self.stdout.write(self.style.SUCCESS(f"{verb} {changed} строк"))
        left = Question.objects.filter(source_type="book_scan", verification_status="draft").count()
        self.stdout.write(f"осталось черновиков: {left}")
