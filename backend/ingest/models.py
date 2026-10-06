# -*- coding: utf-8 -*-
"""Прогон оцифровки книги: загруженный PDF и то, чем он кончился.

Строка банка появляется только в конце пути: PDF → распознавание → разбор на
единицы → импорт. Всё, что до импорта, для тренера — чёрный ящик, поэтому у
прогона есть статус и журнал: без них «книга оцифровывается» означает «верь на
слово», а падение шага API выглядит как пустой банк.
"""
import re
from datetime import datetime

from django.conf import settings
from django.db import models

from subjects.models import Subject

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

STATUSES = [
    (STATUS_PENDING, "ждёт своей очереди"),
    (STATUS_RUNNING, "оцифровывается"),
    (STATUS_DONE, "готово"),
    (STATUS_FAILED, "упало"),
]

LANGUAGES = [("ru", "русский"), ("kk", "қазақша"), ("uz", "o'zbekcha")]


def folder_name(original, when=None):
    """Имя папки прогона. Оно же — префикс external_id у всех строк импорта,
    поэтому два прогона одной книги не должны дать одну папку: отсюда метка
    времени в конце. Кириллицу не выкидываем: «касаткина_эм» читается лучше,
    чем «book», а внешнему ID она не мешает.
    """
    stem = re.sub(r"\.pdf$", "", (original or "").split("/")[-1], flags=re.I)
    # Всё кириллическое поле \u0400–\u04FF, а не А-Я: в казахских именах файлов
    # ү, і, ә, ң лежат за русскими буквами и иначе шумели бы подчёркиваниями.
    stem = re.sub(r"[^A-Za-zЀ-ӿ0-9]+", "_", stem).strip("_").lower()[:28] or "book"
    return f"{stem}_{(when or datetime.now()).strftime('%Y%m%d_%H%M%S')}"


class IngestRun(models.Model):
    class Meta:
        verbose_name = "прогон оцифровки"
        verbose_name_plural = "прогоны оцифровки"
        ordering = ["-created_at"]

    name = models.CharField("папка прогона", max_length=80, unique=True)
    pdf_path = models.CharField("файл источника", max_length=300, blank=True)
    subject = models.ForeignKey(Subject, verbose_name="предмет", on_delete=models.PROTECT,
                                related_name="ingest_runs")
    language = models.CharField("язык задач", max_length=8, choices=LANGUAGES, default="ru")
    book = models.CharField("метка книги", max_length=120)
    status = models.CharField("состояние", max_length=12, choices=STATUSES, default=STATUS_PENDING)
    step = models.CharField("что делает сейчас", max_length=60, blank=True)
    pages = models.IntegerField("страниц распознано", default=0)
    units = models.IntegerField("единиц разбора", default=0)
    # None означает «ставки в окружении нет» — деньги не выдумываем, а честим пустотой
    money = models.FloatField("потрачено, ₽", null=True, blank=True)
    report = models.TextField("импорт в банк", blank=True)
    error = models.TextField("почему упало", blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="кто запустил", null=True,
                                   blank=True, on_delete=models.SET_NULL, related_name="ingest_runs")
    created_at = models.DateTimeField("запущен", auto_now_add=True)
    finished_at = models.DateTimeField("закончен", null=True, blank=True)

    def __str__(self):
        return f"{self.name} · {self.get_status_display()}"

    @property
    def busy(self):
        return self.status in (STATUS_PENDING, STATUS_RUNNING)
