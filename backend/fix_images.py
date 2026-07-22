#!/usr/bin/env python
"""Fix images.py - remove duplicates and implement Drive API."""
import sys

content = '''"""
Скачивание картинок из Google Drive (Drive API).

ШАГ 10 — интеграция с Google Drive API для загрузки изображений.
"""
from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Iterable, Optional, Tuple

from django.conf import settings
from django.core.files.images import ImageFile

try:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaIoBaseDownload
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False

from subjects.models import Question

logger = logging.getLogger(__name__)
_DOWNLOAD_CACHE: dict[str, bytes] = {}
DRIVE_SCOPES = ['https://www.googleapis.com/auth/drive.readonly']


def is_available() -> bool:
    """Доступен ли Drive API."""
    if not GOOGLE_API_AVAILABLE:
        return False
    creds_path = getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_FILE', None)
    if creds_path and Path(creds_path).exists():
        return True
    return bool(getattr(settings, 'GOOGLE_OAUTH_TOKEN', None))


def download_for_questions(
    external_ids: Iterable[str],
) -> Tuple[int, int]:
    """Скачивает картинки для списка external_id. Возвращает (успешно, ошибок)."""
    if not is_available():
        logger.warning('Google Drive API недоступен')
        return (0, 0)

    external_ids_list = list(external_ids)
    if not external_ids_list:
        return (0, 0)

    success_count = 0
    error_count = 0

    questions = Question.objects.filter(
        external_id__in=external_ids_list
    ).exclude(image='')

    service = _get_drive_service()
    if not service:
        logger.error('Не удалось подключиться к Google Drive')
        return (0, len(external_ids_list))

    for question in questions:
        if not question.image:
            continue
        image_ref = str(question.image) if question.image else None
        if not image_ref or '/' in image_ref:
            continue
        try:
            file_content = _download_from_drive(service, image_ref)
            if file_content:
                _save_image_to_question(question, file_content, image_ref)
                success_count += 1
            else:
                error_count += 1
        except Exception as e:
            logger.error(f'Ошибка скачивания {image_ref} для {question.id}: {e}')
            error_count += 1

    return (success_count, error_count)


def _get_drive_service():
    """Возвращает авторизованный Google Drive service или None."""
    if not GOOGLE_API_AVAILABLE:
        return None
    try:
        creds_path = getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_FILE', None)
        if creds_path and Path(creds_path).exists():
            creds = Credentials.from_service_account_file(
                creds_path, scopes=DRIVE_SCOPES
            )
            return build('drive', 'v3', credentials=creds)
        token = getattr(settings, 'GOOGLE_OAUTH_TOKEN', None)
        if token:
            creds = Credentials(token=token, scopes=DRIVE_SCOPES)
            return build('drive', 'v3', credentials=creds)
        logger.warning('GOOGLE_SERVICE_ACCOUNT_FILE или GOOGLE_OAUTH_TOKEN не настроены')
        return None
    except Exception as e:
        logger.error(f'Ошибка подключения к Drive: {e}')
        return None


def _download_from_drive(service, file_id: str) -> Optional[bytes]:
    """Скачивает файл с Drive по file_id."""
    if file_id in _DOWNLOAD_CACHE:
        return _DOWNLOAD_CACHE[file_id]
    try:
        request = service.files().get_media(fileId=file_id)
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        content = fh.getvalue()
        _DOWNLOAD_CACHE[file_id] = content
        return content
    except HttpError as e:
        logger.error(f'Drive API error ({file_id}): {e}')
        return None
    except Exception as e:
        logger.error(f'Ошибка скачивания {file_id}: {e}')
        return None


def _save_image_to_question(
    question: Question, file_content: bytes, file_id: str
) -> None:
    """Сохраняет изображение к вопросу."""
    try:
        filename = f'q_{question.id}_{file_id[:8]}.jpg'
        image_file = ImageFile(BytesIO(file_content), name=filename)
        question.image.save(filename, image_file, save=True)
        logger.info(f'Сохранена картинка для вопроса {question.id}')
    except Exception as e:
        logger.error(f'Ошибка сохранения картинки {question.id}: {e}')


def attach_to_question(question: Question) -> bool:
    """Скачивает и прикрепляет картинку к вопросу."""
    if not question.image or not is_available():
        return False
    service = _get_drive_service()
    if not service:
        return False
    image_ref = str(question.image)
    if '/' in image_ref:
        return False
    try:
        content = _download_from_drive(service, image_ref)
        if content:
            _save_image_to_question(question, content, image_ref)
            return True
    except Exception as e:
        logger.error(f'Ошибка прикрепления картинки: {e}')
    return False
'''

with open('subjects/google_forms/images.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('✓ images.py переписан без дублирования')
