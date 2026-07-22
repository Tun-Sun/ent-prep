"""
Fetcher данных Google Forms по публичной ссылке.

Поддерживает два формата FB_PUBLIC_LOAD_DATA_:
  1. Классический: вопросы вложены в страницы (data[1][6] → pages → questions)
  2. Плоский: все вопросы в data[1][1] (форматы ЕНТ с картинками)

Вопросы-картинки: ImageItem + ChoiceItem связываются в один вопрос.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


class FetcherError(Exception):
    pass


class FetchResult:
    def __init__(self) -> None:
        self.form_id: str = ''
        self.form_title: str = ''
        self.questions: list[dict[str, Any]] = []
        self.images: dict[int, list[bytes]] = {}
        self.image_drive_ids: dict[int, str] = {}
        self.unmatched_images: list[str] = []
        self.used_api: bool = False
        self.used_scrape: bool = False
        self.warnings: list[str] = []


def fetch_form(form_url: str) -> FetchResult:
    result = FetchResult()

    form_id = _extract_form_id(form_url)
    if not form_id:
        raise FetcherError(
            f'Не удалось извлечь form_id из URL: {form_url}'
        )
    result.form_id = form_id

    html = _fetch_html(form_url)
    result.used_scrape = True

    payload = _extract_fb_data(html)
    result.form_title = _extract_title(payload, form_url)

    # Пробуем классический формат (страницы)
    items = _extract_items_classic(payload)
    # Если не нашли — пробуем плоский (ЕНТ с картинками)
    if not items:
        items = _extract_items_flat(payload)

    questions = _build_questions(items, form_id, result)
    result.questions = questions

    if not questions:
        result.warnings.append(
            'Не найдено вопросов поддерживаемых типов '
            '(multiple_choice, checkbox, list)'
        )

    return result


# ── Извлечение form_id из URL ────────────────────────────────────────────

_FORM_ID_PATTERN = re.compile(r'/forms/d/(?:e/)?([a-zA-Z0-9_-]+)')


def _extract_form_id(url: str) -> str:
    m = _FORM_ID_PATTERN.search(url)
    if m:
        return m.group(1)
    parsed = urlparse(url)
    parts = parsed.path.rstrip('/').split('/')
    for i, part in enumerate(parts):
        if part == 'd' and i + 1 < len(parts):
            return parts[i + 1]
    return ''


# ── HTTP ──────────────────────────────────────────────────────────────────

_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/125.0.0.0 Safari/537.36'
    ),
}


def _fetch_html(url: str) -> str:
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        raise FetcherError(f'Ошибка загрузки формы: {e}') from e


# ── Парсинг FB_PUBLIC_LOAD_DATA_ ─────────────────────────────────────────

_FB_PATTERN = re.compile(
    r'FB_PUBLIC_LOAD_DATA_\s*=\s*(\[.+?\])\s*;',
    re.DOTALL,
)


def _extract_fb_data(html: str) -> list:
    m = _FB_PATTERN.search(html)
    if not m:
        raise FetcherError(
            'Не найден FB_PUBLIC_LOAD_DATA_ в HTML формы'
        )
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError as e:
        raise FetcherError(f'Ошибка парсинга FB_PUBLIC_LOAD_DATA_: {e}') from e


def _extract_title(payload: list, fallback_url: str) -> str:
    # Пробуем несколько позиций
    for path in [(1, 8), (1, 0), (1, 3)]:
        try:
            title = payload
            for idx in path:
                title = title[idx]
            if isinstance(title, str) and title.strip():
                return title.strip()
        except (IndexError, TypeError):
            continue
    return f'Google Form ({_extract_form_id(fallback_url)})'


# ── Извлечение элементов: два формата ────────────────────────────────────

def _extract_items_classic(payload: list) -> list[dict]:
    """Классический формат: страницы в data[1][6]."""
    items: list[dict] = []

    for path in [(1, 6), (1, 0, 6)]:
        try:
            pages = payload
            for idx in path:
                pages = pages[idx]
            if not isinstance(pages, list):
                continue

            for page in pages:
                if not isinstance(page, list) or len(page) < 2:
                    continue
                entries = page[1]
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    parsed = _parse_entry_classic(entry)
                    if parsed:
                        items.append(parsed)
            if items:
                return items
        except (IndexError, TypeError):
            continue

    return items


def _parse_entry_classic(entry: list) -> Optional[dict]:
    """Парсит один entry классического формата."""
    if not isinstance(entry, list) or len(entry) < 2:
        return None
    data = entry[1]
    if not isinstance(data, list) or len(data) < 2:
        return None

    type_code = data[0]
    if not isinstance(type_code, int):
        return None

    qtype_map = {0: 'multiple_choice', 1: 'checkbox', 2: 'list'}
    is_supported = type_code in qtype_map or type_code == 13  # IMAGE

    if not is_supported and type_code not in (0, 1, 2):
        return None

    item_id = str(entry[0]) if entry[0] is not None else None
    result = {
        'type_code': type_code,
        'item_id': item_id,
    }

    if type_code == 13:
        result['title'] = _extract_image_title_classic(data)
        result['drive_file_id'] = _extract_image_drive_id_classic(data)
    elif type_code in qtype_map:
        result['qtype'] = qtype_map[type_code]
        result['title'] = _extract_text_title_classic(data)
        result['options'] = _extract_options_classic(data)

    return result


def _extract_items_flat(payload: list) -> list[dict]:
    """
    Плоский формат: все элементы в data[1][1].
    Используется в формах ЕНТ, где вопросы — картинки.
    """
    items: list[dict] = []

    try:
        entries = payload[1][1]
    except (IndexError, TypeError):
        return items

    if not isinstance(entries, list):
        return items

    for entry in entries:
        parsed = _parse_entry_flat(entry)
        if parsed:
            items.append(parsed)

    return items


def _parse_entry_flat(entry: list) -> Optional[dict]:
    """
    Парсит один entry плоского формата.
    Структура: [id, text, null, type, options_data, ..., image_data, ...]
      type: 0=text, 2=multiple_choice
      options_data[0] = [group_id, [[letter, ...], ...]]
      image_data[0] = [drive_file_id, ...]
    """
    if not isinstance(entry, list) or len(entry) < 4:
        return None

    type_code = entry[3] if len(entry) > 3 else None
    if not isinstance(type_code, int):
        return None

    if type_code not in (0, 2, 1):
        return None

    item_id = str(entry[0]) if entry[0] is not None else None
    text = str(entry[1] or '').strip() if len(entry) > 1 else ''

    result: dict[str, Any] = {
        'type_code': type_code,
        'item_id': item_id,
        'title': text,
    }

    if type_code == 0:
        # Текстовое поле (ФИО и т.п.) — пропускаем
        result['qtype'] = 'text'
        result['options'] = []
        return result

    if type_code in (1, 2):
        qtype_map = {1: 'checkbox', 2: 'multiple_choice'}
        result['qtype'] = qtype_map.get(type_code, 'multiple_choice')

        # Извлекаем варианты ответов
        result['options'] = _extract_options_flat(entry)

        # Извлекаем картинку
        drive_id = _extract_drive_id_flat(entry)
        if drive_id:
            result['drive_file_id'] = drive_id

    return result


# ── Извлечение данных: классический формат ───────────────────────────────

def _extract_text_title_classic(data: list) -> str:
    try:
        raw = data[1]
        if isinstance(raw, list):
            parts: list[str] = []
            for item in raw:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, list):
                    for sub in item:
                        if isinstance(sub, str):
                            parts.append(sub)
            return ' '.join(parts).strip()
        if isinstance(raw, str):
            return raw.strip()
    except (IndexError, TypeError):
        pass
    return ''


def _extract_image_title_classic(data: list) -> str:
    try:
        raw = data[2]
        if isinstance(raw, list):
            parts = [str(s) for s in raw if isinstance(s, str) and s.strip()]
            return ' '.join(parts).strip()
        if isinstance(raw, str):
            return raw.strip()
    except (IndexError, TypeError):
        pass
    return ''


def _extract_image_drive_id_classic(data: list) -> Optional[str]:
    for pos in (3, 1):
        try:
            raw = data[pos]
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, str) and re.match(r'^[a-zA-Z0-9_-]{20,}$', item):
                        return item
        except (IndexError, TypeError):
            continue
    return None


def _extract_options_classic(data: list) -> list[dict]:
    options: list[dict] = []
    try:
        raw = data[4]
        if not isinstance(raw, list):
            return options
    except IndexError:
        return options

    for opt in raw:
        if not isinstance(opt, list) or len(opt) < 2:
            continue
        text = str(opt[0]) if opt[0] is not None else ''
        if not text.strip():
            idx = opt[1] if isinstance(opt[1], int) else len(options)
            text = f'Вариант {idx + 1}'
        options.append({'text': text.strip(), 'is_correct': False})

    return options


# ── Извлечение данных: плоский формат (ЕНТ) ──────────────────────────────

def _extract_options_flat(entry: list) -> list[dict]:
    options: list[dict] = []
    try:
        raw = entry[4]
        if not isinstance(raw, list) or len(raw) == 0:
            return options
        opt_group = raw[0]
        if not isinstance(opt_group, list) or len(opt_group) < 2:
            return options
        opt_list = opt_group[1]
        if not isinstance(opt_list, list):
            return options
    except (IndexError, TypeError):
        return options

    for opt in opt_list:
        if not isinstance(opt, list) or len(opt) == 0:
            continue
        text = str(opt[0]) if opt[0] is not None else ''
        if text.strip():
            options.append({'text': text.strip(), 'is_correct': False})

    return options


def _extract_drive_id_flat(entry: list) -> Optional[str]:
    """Извлекает Drive file ID из entry плоского формата."""
    try:
        img_data = entry[9]
        if isinstance(img_data, list) and len(img_data) > 0:
            img_entry = img_data[0]
            if isinstance(img_entry, list) and len(img_entry) > 0:
                drive_id = str(img_entry[0])
                if re.match(r'^[a-zA-Z0-9_-]{20,}$', drive_id):
                    return drive_id
    except (IndexError, TypeError):
        pass
    return None


# ── Сборка вопросов ──────────────────────────────────────────────────────

def _build_questions(
    items: list[dict],
    form_id: str,
    result: FetchResult,
) -> list[dict]:
    """Собирает вопросы из списка элементов."""
    questions: list[dict] = []
    pending_image: Optional[dict] = None
    order = 0

    for item in items:
        tc = item.get('type_code')
        qtype = item.get('qtype', '')

        if tc == 13:
            pending_image = item
            continue

        if tc == 0 and qtype == 'text':
            continue

        if qtype in ('multiple_choice', 'checkbox', 'list'):
            title = item.get('title', '')
            options = item.get('options', [])

            image_urls: list[str] = []
            drive_id = item.get('drive_file_id') or (
                pending_image.get('drive_file_id') if pending_image else None
            )
            alt_text = ''

            if drive_id:
                image_urls = [drive_id]
                result.image_drive_ids[order] = drive_id
                alt_text = item.get('title', '')

                if alt_text.strip():
                    question_text = alt_text
                elif pending_image:
                    question_text = pending_image.get('title', '')
                else:
                    question_text = ''
            else:
                question_text = title

            if not question_text.strip():
                question_text = f'Вопрос {order + 1}'

            # Убираем опции "не знаю" и пустые
            options = [o for o in options if o['text'].strip() and o['text'] not in ('не знаю', 'не знаю', 'Не знаю')]
            if len(options) < 2:
                options = [{'text': 'A', 'is_correct': False},
                           {'text': 'B', 'is_correct': False},
                           {'text': 'C', 'is_correct': False},
                           {'text': 'D', 'is_correct': False}]

            external_id = f'{form_id}/{item.get("item_id", order)}'

            questions.append({
                'external_id': external_id,
                'item_id': str(item.get('item_id', '')),
                'title': question_text.strip(),
                'type': qtype,
                'answers': options,
                'help_text': '',
                'image_urls': image_urls,
                'order_index': order,
            })
            order += 1
            pending_image = None

    return questions
