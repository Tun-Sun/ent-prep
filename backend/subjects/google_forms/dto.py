"""
DTO (Data Transfer Objects) для конвейера импорта из Google Forms.

Чистые dataclasses без зависимости от Django — чтобы парсер и тесты
работали изолированно и не требовали настройки БД.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Union


# Поддерживаемые типы вопроса из Apps Script.
CHOICE_TYPES = {'multiple_choice', 'list', 'checkbox'}


@dataclass(frozen=True)
class AnswerDTO:
    text: str
    is_correct: bool = False
    # URL/путь к картинке (Drive file id). Заполняется images.py на сервере.
    image_ref: Optional[str] = None

    def validate(self) -> None:
        if not self.text or not self.text.strip():
            raise ValueError('Вариант ответа не может быть пустым')


@dataclass(frozen=True)
class QuestionDTO:
    external_id: str
    title: str
    type: str
    answers: List[AnswerDTO]
    help_text: str = ''
    # Ссылка на картинку в теле вопроса (Drive file id), None если нет.
    image_ref: Optional[str] = None
    order_index: int = 0
    # Баллы за вопрос (из Google Forms Quiz)
    points: float = 1.0

    def validate(self) -> None:
        if not self.external_id:
            raise ValueError('Вопрос без external_id — невозможно найти дубликат')
        if not self.title.strip():
            raise ValueError(f'Вопрос {self.external_id}: пустой текст')
        if self.type not in CHOICE_TYPES:
            raise ValueError(
                f'Вопрос {self.external_id}: неподдерживаемый тип "{self.type}"'
            )
        if len(self.answers) < 2:
            raise ValueError(
                f'Вопрос {self.external_id}: должно быть минимум 2 варианта, '
                f'сейчас {len(self.answers)}'
            )
        for a in self.answers:
            a.validate()

    @property
    def has_correct(self) -> bool:
        return any(a.is_correct for a in self.answers)


@dataclass(frozen=True)
class FormPayload:
    """Распарсенный JSON из Apps Script, готовый к импорту."""
    schema_version: int
    form_id: str
    form_title: str
    form_url: str
    is_quiz: bool
    subject_slug: str
    subject_name: str
    topic_name: str
    language: str
    year: Optional[int]
    questions: List[QuestionDTO] = field(default_factory=list)

    def validate(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                f'Неподдерживаемая schema_version={self.schema_version}; '
                f'ожидается 1. Обновите Apps Script.'
            )
        if not self.questions:
            raise ValueError('Форма не содержит вопросов для импорта')
        for q in self.questions:
            q.validate()
        # Уникальность external_id в рамках файла.
        ids = [q.external_id for q in self.questions]
        if len(ids) != len(set(ids)):
            dup = next(x for x in ids if ids.count(x) > 1)
            raise ValueError(f'Дубли external_id внутри файла: {dup}')
        if not (self.subject_slug or self.subject_name):
            raise ValueError(
                'Не указан предмет: нужен subject_slug или subject_name'
            )
        if not self.topic_name:
            raise ValueError('Не указана тема (topic_name)')
