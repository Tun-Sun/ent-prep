"""
Скачивание картинок из Google Drive.

Стратегия:
  1. Прямая загрузка через requests (без авторизации) — для публичных файлов.
  2. Fallback через Drive API (Service Account), если настроен.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path
from typing import Iterable, Optional, Tuple

import requests
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

# Прямые ссылки для скачивания публичных файлов Drive
_DIRECT_DOWNLOAD_URL = 'https://drive.google.com/uc?export=download&id={file_id}'
_THUMBNAIL_URL = 'https://drive.google.com/thumbnail?id={file_id}&sz=w1000'


def is_available() -> bool:
    """Доступен ли Drive API (Service Account)."""
    if not GOOGLE_API_AVAILABLE:
        return False
    creds_path = getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_FILE', None)
    if creds_path and Path(creds_path).exists():
        return True
    return bool(getattr(settings, 'GOOGLE_OAUTH_TOKEN', None))


def download_image(file_id: str) -> Optional[bytes]:
    """
    Скачивает картинку по Drive file_id.

    Сначала пробует прямую загрузку (без авторизации),
    при неудаче — через Drive API (Service Account).
    """
    if file_id in _DOWNLOAD_CACHE:
        return _DOWNLOAD_CACHE[file_id]

    content = _download_unauthenticated(file_id)
    if content is not None:
        _DOWNLOAD_CACHE[file_id] = content
        return content

    if is_available():
        service = _get_drive_service()
        if service:
            content = _download_from_drive(service, file_id)
            if content is not None:
                _DOWNLOAD_CACHE[file_id] = content
                return content

    logger.warning(f'Не удалось скачать {file_id} ни одним способом')
    return None


def download_for_questions(
    external_ids: Iterable[str],
) -> Tuple[int, int]:
    """Скачивает картинки для списка external_id. Возвращает (успешно, ошибок)."""
    external_ids_list = list(external_ids)
    if not external_ids_list:
        return (0, 0)

    success_count = 0
    error_count = 0

    questions = Question.objects.filter(
        external_id__in=external_ids_list
    ).exclude(image_ref='')

    for question in questions:
        if not question.image_ref:
            continue
        image_ref = question.image_ref
        if '/' in image_ref:
            continue
        try:
            file_content = download_image(image_ref)
            if file_content:
                _save_image_to_question(question, file_content, image_ref)
                question.image_ref = ''
                question.save(update_fields=['image_ref'])
                success_count += 1
            else:
                error_count += 1
        except Exception as e:
            logger.error(f'Ошибка скачивания {image_ref} для {question.id}: {e}')
            error_count += 1

    return (success_count, error_count)


def download_batch(
    drive_ids: dict[int, str],
    max_workers: int = 5,
) -> dict[int, list[bytes]]:
    """
    Скачивает несколько картинок параллельно.

    Аргументы:
        drive_ids: {question_index: drive_file_id}
        max_workers: число параллельных потоков (по умолч. 5)

    Возвращает:
        {question_index: [content_bytes]} — только успешно скачанные.
    """
    result: dict[int, list[bytes]] = {}

    def _download_one(item: tuple[int, str]) -> Optional[tuple[int, bytes]]:
        q_index, drive_id = item
        try:
            content = download_image(drive_id)
            if content:
                return (q_index, content)
        except Exception as e:
            logger.error(f'Ошибка скачивания {drive_id} (q{q_index}): {e}')
        return None

    items = list(drive_ids.items())
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_download_one, item): item[0] for item in items}
        for future in as_completed(futures):
            outcome = future.result()
            if outcome:
                q_index, content = outcome
                result[q_index] = [content]

    return result


# ── Прямая загрузка (без авторизации) ──────────────────────────────────────

_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/125.0.0.0 Safari/537.36'
    ),
}


_IMAGE_MAGIC_BYTES = {
    b'\xff\xd8\xff': 'image/jpeg',
    b'\x89PNG\r\n\x1a\n': 'image/png',
    b'GIF87a': 'image/gif',
    b'GIF89a': 'image/gif',
    b'RIFF': 'image/webp',
    b'\x42\x4d': 'image/bmp',
}

_MAGIC_MAX_LEN = max(len(k) for k in _IMAGE_MAGIC_BYTES)


def _looks_like_image(content: bytes) -> bool:
    """Проверяет, что содержимое похоже на изображение по magic bytes."""
    if len(content) < _MAGIC_MAX_LEN:
        return False
    header = content[:_MAGIC_MAX_LEN]
    for magic in _IMAGE_MAGIC_BYTES:
        if header.startswith(magic):
            return True
    return False


def _download_unauthenticated(file_id: str) -> Optional[bytes]:
    """Пытается скачать публичный файл Drive напрямую через requests."""
    # Сначала пробуем thumbnail (быстрее, надёжнее для картинок)
    try:
        resp = requests.get(
            _THUMBNAIL_URL.format(file_id=file_id),
            headers=_HEADERS,
            timeout=15,
        )
        if resp.status_code == 200 and len(resp.content) > 100 and _looks_like_image(resp.content):
            return resp.content
    except requests.RequestException:
        pass

    # Пробуем прямую ссылку на скачивание
    try:
        resp = requests.get(
            _DIRECT_DOWNLOAD_URL.format(file_id=file_id),
            headers=_HEADERS,
            timeout=30,
        )
        if resp.status_code == 200 and len(resp.content) > 100 and _looks_like_image(resp.content):
            return resp.content
    except requests.RequestException:
        pass

    return None


# ── Drive API (Service Account) ────────────────────────────────────────────


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
    """Скачивает файл с Drive через Drive API."""
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


# ── Сохранение в БД ────────────────────────────────────────────────────────


_MIME_TO_EXT = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/gif': 'gif',
    'image/webp': 'webp',
    'image/bmp': 'bmp',
}


def _detect_ext(content: bytes) -> str:
    """Определяет расширение файла по magic bytes."""
    header = content[:_MAGIC_MAX_LEN]
    for magic, mime in _IMAGE_MAGIC_BYTES.items():
        if header.startswith(magic):
            return _MIME_TO_EXT.get(mime, 'jpg')
    return 'jpg'


def _save_image_to_question(
    question: Question, file_content: bytes, file_id: str
) -> None:
    """Сохраняет изображение к вопросу."""
    try:
        ext = _detect_ext(file_content)
        filename = f'q_{question.id}_{file_id[:8]}.{ext}'
        image_file = ImageFile(BytesIO(file_content), name=filename)
        question.image.save(filename, image_file, save=True)
        logger.info(f'Сохранена картинка для вопроса {question.id}')
    except Exception as e:
        logger.error(f'Ошибка сохранения картинки {question.id}: {e}')


def attach_to_question(question: Question) -> bool:
    """Скачивает и прикрепляет картинку к вопросу."""
    if not question.image_ref:
        return False
    image_ref = question.image_ref
    if '/' in image_ref:
        return False
    try:
        content = download_image(image_ref)
        if content:
            _save_image_to_question(question, content, image_ref)
            question.image_ref = ''
            question.save(update_fields=['image_ref'])
            return True
    except Exception as e:
        logger.error(f'Ошибка прикрепления картинки: {e}')
    return False
