# -*- coding: utf-8 -*-
"""Эндпоинты оцифровки: загрузил PDF — получил черновики в банке.

Экран только запускает прогон и смотрит, чем он кончился. Правку и приёмку
строк делает банк из книг: здесь нет кнопки «принять», потому что приёмка —
решение владельца, и она уже живёт одним окном.
"""
from pathlib import Path

from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from subjects.models import Subject
from subjects.permissions import IsTeacherOrAdmin

from . import runner
from .models import LANGUAGES, STATUS_PENDING, STATUS_RUNNING, IngestRun, folder_name

LOG_TAIL = 4000


def payload(run, log=""):
    return {
        "id": run.pk,
        "name": run.name,
        "book": run.book,
        "subject": run.subject.slug,
        "subject_name": run.subject.name,
        "language": run.language,
        "status": run.status,
        "status_display": run.get_status_display(),
        "step": run.step,
        "pages": run.pages,
        "units": run.units,
        "money": run.money,
        "report": run.report,
        "error": run.error,
        "created_by": getattr(run.created_by, "username", ""),
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "log": log,
    }


class RunView(APIView):
    """POST — завести прогон, GET — показать последние прогоны."""

    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]
    parser_classes = [MultiPartParser]

    def get(self, request):
        return Response([payload(r) for r in IngestRun.objects.select_related("subject", "created_by")[:20]])

    def post(self, request):
        upload = request.FILES.get("pdf")
        if upload is None:
            return Response({"detail": "файла pdf нет"}, status=status.HTTP_400_BAD_REQUEST)
        if not upload.name.lower().endswith(".pdf"):
            return Response({"detail": "нужен PDF скана, а не " + Path(upload.name).suffix},
                            status=status.HTTP_400_BAD_REQUEST)
        limit = settings.INGEST_MAX_PDF_MB * 1024 * 1024
        if upload.size > limit:
            return Response({"detail": f"файл больше {settings.INGEST_MAX_PDF_MB} МБ — "
                                       "прогон такой книги надо резать на части"},
                            status=status.HTTP_400_BAD_REQUEST)
        slug = (request.data.get("subject") or "").strip()
        try:
            subject = Subject.objects.get(slug=slug)
        except Subject.DoesNotExist:
            return Response({"detail": f"предмета {slug} нет"}, status=status.HTTP_400_BAD_REQUEST)
        language = (request.data.get("language") or "ru").strip()
        if language not in dict(LANGUAGES):
            return Response({"detail": f"языка {language} нет в списке"}, status=status.HTTP_400_BAD_REQUEST)
        book = (request.data.get("book") or "").strip()
        if not book:
            return Response({"detail": "нужна метка книги: по ней тема строки отличается от темы "
                                       "другой книги с тем же разделом"}, status=status.HTTP_400_BAD_REQUEST)
        # Два прогона одновременно — это и двойной счёт по API, и спор за диск:
        # платформа отказывает второму, а не молча запускает его.
        busy = IngestRun.objects.filter(status__in=(STATUS_PENDING, STATUS_RUNNING)).first()
        if busy:
            return Response({"detail": f"прогон {busy.name} ещё идёт: дождись или разберись с ним"},
                            status=status.HTTP_409_CONFLICT)

        name = folder_name(upload.name)
        out = runner.run_dir(name)
        out.mkdir(parents=True, exist_ok=True)
        pdf = out / "source.pdf"
        with pdf.open("wb") as fh:
            for chunk in upload.chunks():
                fh.write(chunk)
        run = IngestRun.objects.create(name=name, pdf_path=str(pdf), subject=subject,
                                       language=language, book=book[:120], created_by=request.user)
        runner.spawn(run.pk)
        run.refresh_from_db()
        return Response(payload(run), status=status.HTTP_201_CREATED)


class RunDetailView(APIView):
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]

    def get(self, request, pk):
        run = IngestRun.objects.select_related("subject", "created_by").filter(pk=pk).first()
        if run is None:
            raise NotFound("прогона нет")
        log = ""
        f = runner.log_path(run.name)
        if f.is_file():
            text = f.read_text(encoding="utf-8", errors="replace")
            log = text[-LOG_TAIL:]
        return Response(payload(run, log))
