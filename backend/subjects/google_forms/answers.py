"""
Получение правильных ответов из Google Forms API.

Использует тот же Service Account, что и Drive API.
Форма должна быть расшарена на email Service Account.

Google Forms API v1: forms.get()
https://developers.google.com/forms/api/reference/rest/v1/forms/get
"""
from __future__ import annotations

import json as _json
import logging
import threading
import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional

import requests
from django.conf import settings

try:
    import httplib2
    import google_auth_httplib2
    from google.auth.transport.requests import Request as _AuthRequest
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False
    httplib2 = None

logger = logging.getLogger(__name__)
FORMS_SCOPES = [
    'https://www.googleapis.com/auth/forms.body.readonly',
    'https://www.googleapis.com/auth/drive.readonly',
]

# Публичный responder-ID (ссылка /d/e/1FAIpQLS...) Forms API не принимает.
_RESPONDER_PREFIX = '1FAIpQLS'

# Полный обратный кеш: responder-ID → внутренний ID. Один скан покрывает
# ВСЕ расшаренные формы (их могут быть сотни), дальше — мгновенный lookup.
_RESPONDER_CACHE: dict[str, str] = {}
_NOT_FOUND_UNTIL: dict[str, float] = {}
_NOT_FOUND_TTL = 600  # сек: негативный результат живёт 10 минут
_SCAN_LOCK = threading.Lock()
_SA_CREDS: Any = None


def is_available() -> bool:
    """Доступен ли Forms API (Service Account)."""
    if not GOOGLE_API_AVAILABLE:
        return False
    creds_path = getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_FILE', None)
    if creds_path and Path(creds_path).exists():
        return True
    return False


def get_service_account_email() -> str:
    """Email сервисного аккаунта из ключевого файла (для подсказок юзеру)."""
    creds_path = getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_FILE', None)
    if creds_path and Path(creds_path).exists():
        try:
            with open(creds_path, encoding='utf-8') as f:
                return _json.load(f).get('client_email', '')
        except (OSError, _json.JSONDecodeError):
            pass
    return ''


def resolve_form_id(form_id: str) -> str:
    """
    Публичный responder-ID (1FAIpQLS...) → внутренний ID формы.

    Forms API принимает только внутренний ID (из /edit-ссылки). Внутренний ID
    находится сканом форм, расшаренных на сервисный аккаунт (Drive
    files.list + параллельный forms.get), с точным матчингом по responderUri.
    Результаты кешируются: один полный скан покрывает все расшаренные формы.

    Возвращает внутренний ID либо исходный ID, если разрешить не удалось
    (форма не расшарена на сервисный аккаунт).
    """
    if not form_id or not form_id.startswith(_RESPONDER_PREFIX):
        return form_id
    if form_id in _RESPONDER_CACHE:
        return _RESPONDER_CACHE[form_id]
    if _time.time() < _NOT_FOUND_UNTIL.get(form_id, 0):
        return form_id

    with _SCAN_LOCK:
        # могли отсканировать, пока ждали блокировку
        if form_id in _RESPONDER_CACHE:
            return _RESPONDER_CACHE[form_id]
        _scan_shared_forms(stop_on=form_id)

    if form_id in _RESPONDER_CACHE:
        return _RESPONDER_CACHE[form_id]
    _NOT_FOUND_UNTIL[form_id] = _time.time() + _NOT_FOUND_TTL
    return form_id


def _scan_shared_forms(stop_on: str = '') -> None:
    """Параллельно собирает responder-ID → внутренний ID по Drive files.list."""
    token = _get_access_token()
    if not token:
        return

    drive_service = _get_drive_service()
    if not drive_service:
        return

    candidates: list[str] = []
    page_token: Optional[str] = None
    try:
        while True:
            res = drive_service.files().list(
                q="mimeType='application/vnd.google-apps.form'",
                fields='nextPageToken, files(id)',
                pageSize=1000,
                pageToken=page_token,
            ).execute(num_retries=2)
            candidates.extend(f['id'] for f in res.get('files', []))
            page_token = res.get('nextPageToken')
            if not page_token:
                break
    except Exception as e:
        logger.error(f'resolve_form_id: Drive files.list error: {e}')
        return

    if not candidates:
        return

    logger.info(f'resolve_form_id: сканирую {len(candidates)} расшаренных форм')
    session = requests.Session()
    headers = {'Authorization': f'Bearer {token}'}
    pool = ThreadPoolExecutor(max_workers=12)
    try:
        futures = {
            pool.submit(_fetch_responder_id, session, headers, cid): cid
            for cid in candidates
        }
        for fut in as_completed(futures):
            pair = fut.result()
            if pair:
                _RESPONDER_CACHE[pair[0]] = pair[1]
            if stop_on and stop_on in _RESPONDER_CACHE:
                break
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    logger.info(
        f'resolve_form_id: просканировано, в кеше {len(_RESPONDER_CACHE)} форм'
    )


def _fetch_responder_id(
    session: requests.Session, headers: dict, form_id: str
) -> Optional[tuple[str, str]]:
    """Одинарный forms.get: (responder_id, internal_id) или None."""
    try:
        resp = session.get(
            f'https://forms.googleapis.com/v1/forms/{form_id}',
            headers=headers,
            params={'fields': 'responderUri'},
            timeout=20,
        )
        if resp.status_code != 200:
            return None
        uri = resp.json().get('responderUri', '')
        m = uri.rsplit('/e/', 1)
        if len(m) == 2:
            responder = m[1].split('/')[0]
            if responder:
                return (responder, form_id)
    except Exception:
        pass
    return None


def _get_access_token() -> Optional[str]:
    """Access token сервисного аккаунта (с автопродлением)."""
    global _SA_CREDS
    if not GOOGLE_API_AVAILABLE:
        return None
    creds_path = getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_FILE', None)
    if not (creds_path and Path(creds_path).exists()):
        return None
    try:
        if _SA_CREDS is None:
            _SA_CREDS = Credentials.from_service_account_file(
                creds_path, scopes=FORMS_SCOPES
            )
        if not _SA_CREDS.valid:
            _SA_CREDS.refresh(_AuthRequest())
        return _SA_CREDS.token
    except Exception as e:
        logger.error(f'resolve_form_id: ошибка авторизации: {e}')
        return None


def get_form_quiz_data(form_id: str) -> Optional[dict]:
    """
    Получает правильные ответы и баллы из Google Forms API.

    Аргументы:
        form_id: ID формы из редактора (https://docs.google.com/forms/d/{ID}/edit)

    Возвращает:
        Словарь:
        {
            'answers': ['C', 'D', 'D', ...],  # правильные ответы
            'questions': [
                {'external_id': '...', 'points': 1.0},
                ...
            ]
        }
        или None при ошибке.
    """
    if not is_available():
        logger.warning('Google Forms API недоступен (нет Service Account)')
        return None

    service = _get_forms_service()
    if not service:
        return None

    try:
        form = service.forms().get(formId=form_id).execute(num_retries=2)
    except HttpError as e:
        logger.error(f'Forms API error ({form_id}): {e}')
        return None

    items = form.get('items', [])
    if not items:
        logger.warning('Нет items в форме')
        return None

    result_answers: list[str] = []
    result_questions: list[dict] = []

    for item in items:
        question_item = item.get('questionItem')
        if not question_item:
            continue

        question = question_item.get('question')
        if not question:
            continue

        choice = question.get('choiceQuestion')
        if not choice:
            continue

        grading = question.get('grading')
        if not grading:
            continue

        # Извлекаем баллы
        points = float(grading.get('pointValue', 1.0) or 1.0)

        correct_answers = grading.get('correctAnswers', {}).get('answers', [])
        if not correct_answers:
            continue

        correct_value = correct_answers[0].get('value', '')
        if correct_value:
            result_answers.append(correct_value)

        # item ID используем как external_id часть
        item_id = item.get('itemId', '')
        result_questions.append({
            'external_id': f'{form_id}/{item_id}',
            'points': points,
        })

    logger.info(
        f'Получено {len(result_answers)} правильных ответов, '
        f'{len(result_questions)} с баллами из Forms API'
    )
    if not result_answers:
        return None
    return {
        'answers': result_answers,
        'questions': result_questions,
    }


def merge_into_questions(
    questions: list[dict[str, Any]],
    correct_answers: list[str],
    quiz_questions: Optional[list[dict]] = None,
) -> list[dict[str, Any]]:
    """
    Встраивает правильные ответы и баллы в список вопросов.

    Матчит по порядку: answers[i] → questions[i].
    quiz_questions — список {'external_id': ..., 'points': ...} для простановки баллов.
    """
    updated = 0
    points_set = 0

    # Строим карту баллов по external_id
    points_map = {}
    if quiz_questions:
        for qq in quiz_questions:
            eid = qq.get('external_id', '')
            if eid:
                points_map[eid] = qq.get('points', 1.0)

    for idx, q in enumerate(questions):
        # Проставляем правильные ответы
        if idx < len(correct_answers):
            correct_value = correct_answers[idx]
            if correct_value:
                for answer in q.get('answers', []):
                    if answer.get('text', '').strip() == correct_value.strip():
                        answer['is_correct'] = True
                        updated += 1
                        break

        # Проставляем баллы по external_id
        eid = q.get('external_id', '')
        if eid in points_map:
            q['points'] = points_map[eid]
            points_set += 1

    if updated:
        logger.info(f'Проставлено {updated} правильных ответов')
    if points_set:
        logger.info(f'Проставлено баллов для {points_set} вопросов')
    return questions


def get_form_images_via_api(form_id: str) -> Optional[dict[int, list[bytes]]]:
    """
    Получает картинки вопросов через Google Forms API.

    Использует forms.get() → questionItem.image.contentUri — прямые URL
    на Google CDN, не требующие авторизации.

    Возвращает {question_index: [bytes]} — маппинг, совместимый с
    FetchResult.images / download_batch().
    """
    import requests as _requests

    service = _get_forms_service()
    if not service:
        return None

    try:
        form = service.forms().get(formId=form_id).execute(num_retries=2)
    except HttpError as e:
        logger.error(f'Forms API error ({form_id}): {e}')
        return None

    result: dict[int, list[bytes]] = {}
    choice_idx = 0

    for item in form.get('items', []):
        qi = item.get('questionItem', {})
        if not qi:
            continue

        q = qi.get('question', {})
        if not q.get('choiceQuestion'):
            continue

        img = qi.get('image', {}).get('contentUri', '') or q.get('image', {}).get('contentUri', '')
        if not img:
            choice_idx += 1
            continue

        try:
            resp = _requests.get(img, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }, timeout=15)

            if resp.status_code == 200 and len(resp.content) > 100:
                result[choice_idx] = [resp.content]
                logger.info(f'Forms API: скачана картинка Q{choice_idx} ({len(resp.content)} bytes)')
            else:
                logger.warning(f'Forms API: ошибка скачивания Q{choice_idx}: status={resp.status_code}')

        except Exception as e:
            logger.warning(f'Forms API: ошибка скачивания Q{choice_idx}: {e}')

        choice_idx += 1

    if result:
        logger.info(f'Forms API: скачано {len(result)} картинок из {choice_idx} вопросов')
    else:
        logger.warning('Forms API: картинки не найдены')

    return result


def _get_forms_service():
    """Возвращает авторизованный Google Forms service или None."""
    return _build_service('forms', 'v1')


def _get_drive_service():
    """Возвращает авторизованный Google Drive service или None."""
    return _build_service('drive', 'v3')


def _build_service(service_name: str, version: str):
    """
    Собирает googleapiclient-сервис с явным socket-timeout.

    По умолчанию httplib2 висит бесконечно при отвале соединения —
    из-за этого сканирование форм в resolve_form_id могло подвисать.
    """
    if not GOOGLE_API_AVAILABLE:
        return None
    try:
        creds_path = getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_FILE', None)
        if creds_path and Path(creds_path).exists():
            creds = Credentials.from_service_account_file(
                creds_path, scopes=FORMS_SCOPES
            )
            http = google_auth_httplib2.AuthorizedHttp(
                creds, http=httplib2.Http(timeout=30)
            )
            return build(
                service_name, version, http=http, cache_discovery=False,
                static_discovery=False,
            )
        logger.warning('GOOGLE_SERVICE_ACCOUNT_FILE не настроен')
        return None
    except Exception as e:
        logger.error(f'Ошибка подключения к {service_name} API: {e}')
        return None
