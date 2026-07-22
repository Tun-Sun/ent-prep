"""
Парсер JSON-экспорта Google Forms (от ExportFormToJSON.gs) в DTO.

Отделяется от importer-а, чтобы:
- валидировать файл ДО записи в БД (fail fast);
- иметь чистый интерфейс для юнит-тестов;
- использовать один и тот же парсер из management-команды и DRF-эндпоинта.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from .dto import AnswerDTO, FormPayload, QuestionDTO

# Типы, которые мы поддерживаем (из scraper/fetcher)
_SUPPORTED_SCRAPER_TYPES = {'multiple_choice', 'list', 'checkbox'}


class ParseError(ValueError):
    """Некорректный JSON или структура — импорт невозможен."""


def parse_dict(data: dict) -> FormPayload:
    """
    Принимает словарь (уже раскрытый JSON), возвращает FormPayload
    или поднимает ParseError.

    Валидация данных происходит в DTO.validate() — здесь только
    извлечение полей и аккуратные сообщения об ошибках.
    """
    if not isinstance(data, dict):
        raise ParseError('Ожидается JSON-объект на верхнем уровне')

    try:
        source = data.get('source') or {}
        questions_raw = data.get('questions') or []
        questions: list[QuestionDTO] = []

        for i, q_raw in enumerate(questions_raw):
            try:
                questions.append(_parse_question(q_raw))
            except (KeyError, ValueError, TypeError) as e:
                raise ParseError(
                    f'Ошибка в вопросе #{i + 1}: {e}'
                ) from e

        payload = FormPayload(
            schema_version=int(data.get('schema_version', 0)),
            form_id=str(source.get('form_id', '')),
            form_title=str(source.get('form_title', '')),
            form_url=str(source.get('form_url', '')),
            is_quiz=bool(source.get('is_quiz', False)),
            subject_slug=str(data.get('subject_slug') or '').strip(),
            subject_name=str(data.get('subject_name') or '').strip(),
            topic_name=str(data.get('topic_name') or '').strip(),
            language=str(data.get('language') or 'ru').strip() or 'ru',
            year=_parse_int_or_none(data.get('year')),
            questions=questions,
        )
    except ParseError:
        raise
    except Exception as e:  # noqa: BLE001 — оборачиваем всё, что не предусмотрели
        raise ParseError(f'Неожиданная ошибка разбора: {e}') from e

    # Полная валидация на уровне payload.
    try:
        payload.validate()
    except ValueError as e:
        raise ParseError(str(e)) from e

    return payload


def parse_file(path: Union[str, Path]) -> FormPayload:
    """Читает JSON-файл с диска и парсит его."""
    p = Path(path)
    if not p.exists():
        raise ParseError(f'Файл не найден: {p}')
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        raise ParseError(f'Невалидный JSON в {p}: {e}') from e
    return parse_dict(data)


def parse_json(text: str) -> FormPayload:
    """Парсит JSON-строку (например, из тела HTTP-запроса)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ParseError(f'Невалидный JSON: {e}') from e
    return parse_dict(data)


# === Внутренние хелперы =====================================================

def _parse_question(raw: dict) -> QuestionDTO:
    answers_raw = raw.get('answers') or []
    answers = [_parse_answer(a) for a in answers_raw]

    # Картинка вопроса — пока просто прокидываем note как image_ref,
    # реальный Drive file id достанет images.py на сервере.
    image_ref = None
    img = raw.get('image')
    if isinstance(img, dict) and img.get('drive_file_id'):
        image_ref = str(img['drive_file_id'])
    elif isinstance(img, dict) and img.get('note'):
        # Помечаем, что картинка «возможно есть» — оставляем для images.py.
        image_ref = None

    return QuestionDTO(
        external_id=str(raw.get('external_id') or '').strip(),
        title=str(raw.get('title') or ''),
        type=str(raw.get('type') or ''),
        answers=answers,
        help_text=str(raw.get('help_text') or ''),
        image_ref=image_ref,
        order_index=int(raw.get('order_index') or 0),
        points=float(raw.get('points', 1.0) or 1.0),
    )


def _parse_answer(raw: dict) -> AnswerDTO:
    return AnswerDTO(
        text=str(raw.get('text') or '').strip(),
        is_correct=bool(raw.get('is_correct', False)),
        image_ref=str(raw.get('drive_file_id') or '') or None,
    )


def raw_to_payload(
    raw: dict,
    *,
    subject_slug: str = '',
    subject_name: str = '',
    topic_name: str = '',
    language: str = 'ru',
    year: int | None = None,
) -> FormPayload:
    """
    Конвертирует нормализованный dict от fetcher.py в FormPayload.

    Формат raw (от scraper/fetcher):
    ```
    {
        "form_id": "1abc",
        "form_title": "Physics Quiz",
        "questions": [
            {
                "external_id": "1abc/0",
                "title": "What is F=ma?",
                "type": "multiple_choice",
                "answers": [{"text": "...", "is_correct": true/false}, ...],
                "help_text": "",
                "image_urls": [],
                "order_index": 0,
            },
            ...
        ],
    }
    ```

    Мета-данные (subject, topic, language, year) приходят от учителя
    через веб-интерфейс и перекрывают/дополняют то, что вытащил fetcher.
    """
    if not isinstance(raw, dict):
        raise ParseError('raw_to_payload: ожидается dict')

    questions_raw = raw.get('questions') or []
    questions: list[QuestionDTO] = []

    for i, q_raw in enumerate(questions_raw):
        try:
            q_type = str(q_raw.get('type', 'multiple_choice'))
            if q_type not in _SUPPORTED_SCRAPER_TYPES:
                continue  # пропускаем неподдерживаемый тип

            answers = []
            for a in q_raw.get('answers', []):
                answers.append(AnswerDTO(
                    text=str(a.get('text', '')),
                    is_correct=bool(a.get('is_correct', False)),
                ))

            if len(answers) < 2:
                continue

            image_ref = None
            img_urls = q_raw.get('image_urls', [])
            if isinstance(img_urls, list) and img_urls:
                image_ref = img_urls[0]

            questions.append(QuestionDTO(
                external_id=str(q_raw.get('external_id', f'fetched_{i}')),
                title=str(q_raw.get('title', '')),
                type=q_type,
                answers=answers,
                help_text=str(q_raw.get('help_text', '')),
                image_ref=image_ref,
                order_index=int(q_raw.get('order_index', i)),
                points=float(q_raw.get('points', 1.0) or 1.0),
            ))
        except (KeyError, TypeError, ValueError):
            continue

    if not questions:
        raise ParseError('Не найдено поддерживаемых вопросов в данных формы')

    payload = FormPayload(
        schema_version=int(raw.get('schema_version', 1)),
        form_id=str(raw.get('form_id', '')),
        form_title=str(raw.get('form_title', '')),
        form_url=str(raw.get('form_url', '')),
        is_quiz=False,
        subject_slug=subject_slug,
        subject_name=subject_name,
        topic_name=topic_name,
        language=language,
        year=year,
        questions=questions,
    )

    if not (payload.subject_slug or payload.subject_name):
        raise ParseError('Не указан предмет: нужен subject_slug или subject_name')
    if not payload.topic_name:
        raise ParseError('Не указана тема (topic_name)')

    return payload


def _parse_int_or_none(value) -> int | None:
    if value in (None, '', 0):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
