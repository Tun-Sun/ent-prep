"""
Получение правильных ответов из Google Forms API.

Использует тот же Service Account, что и Drive API.
Форма должна быть расшарена на email Service Account.

Google Forms API v1: forms.get()
https://developers.google.com/forms/api/reference/rest/v1/forms/get
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from django.conf import settings

try:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False

logger = logging.getLogger(__name__)
FORMS_SCOPES = [
    'https://www.googleapis.com/auth/forms.body.readonly',
    'https://www.googleapis.com/auth/drive.readonly',
]


def is_available() -> bool:
    """Доступен ли Forms API (Service Account)."""
    if not GOOGLE_API_AVAILABLE:
        return False
    creds_path = getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_FILE', None)
    if creds_path and Path(creds_path).exists():
        return True
    return False


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
        form = service.forms().get(formId=form_id).execute()
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
        form = service.forms().get(formId=form_id).execute()
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
    if not GOOGLE_API_AVAILABLE:
        return None
    try:
        creds_path = getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_FILE', None)
        if creds_path and Path(creds_path).exists():
            creds = Credentials.from_service_account_file(
                creds_path, scopes=FORMS_SCOPES
            )
            return build('forms', 'v1', credentials=creds)
        logger.warning('GOOGLE_SERVICE_ACCOUNT_FILE не настроен')
        return None
    except Exception as e:
        logger.error(f'Ошибка подключения к Forms API: {e}')
        return None
