"""
Импортер DTO FormPayload в базу данных.

Создаёт/находит Subject и Topic, пишет вопросы и ответы, помечает
дубликаты по external_id (через UniqueConstraint на модели Question).

Соглашения:
- Все импортированные вопросы получают source_type='authorial'.
- verification_status по умолчанию 'verified' ЕСЛИ у вопроса есть
  правильный ответ (форма была в режиме Quiz). Иначе 'draft' —
  учитель должен сверить ответы вручную.
- Картинки НЕ скачиваются тут (это images.py). При наличии image_ref
  вопрос создаётся без файла, а в result.skipped_images копится список
  для последующей догрузки.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from django.db import transaction

from subjects.models import Answer, Question, Subject, Topic

from .dto import FormPayload, QuestionDTO

_TYPE_MAP = {
    'multiple_choice': 'single_choice',
    'list':            'single_choice',
    'checkbox':        'multiple_choice',
}


@dataclass
class ImportResult:
    """Отчёт об импорте — показывается командой/эндпоинтом пользователю."""
    subject: str
    topic: str
    created: int = 0
    skipped_duplicates: int = 0
    drafted_no_correct: int = 0
    skipped_images: List[str] = field(default_factory=list)  # external_id вопросов
    errors: List[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.created + self.skipped_duplicates

    def as_dict(self) -> dict:
        return {
            'subject': self.subject,
            'topic': self.topic,
            'created': self.created,
            'skipped_duplicates': self.skipped_duplicates,
            'drafted_no_correct': self.drafted_no_correct,
            'skipped_images_count': len(self.skipped_images),
            'errors': self.errors,
        }


class ImporterError(RuntimeError):
    """Неустранимая ошибка импорта (например, не найден предмет)."""


def import_payload(
    payload: FormPayload,
    *,
    default_difficulty: str = 'medium',
) -> ImportResult:
    """
    Импортирует FormPayload в БД.

    Весь импорт выполняется в одной транзакции — либо все вопросы
    конкретной формы залетают в БД, либо ни одного (атомарность).
    """
    result = ImportResult(subject='', topic='')

    try:
        with transaction.atomic():
            subject = _resolve_subject(payload)
            topic = _resolve_topic(subject, payload.topic_name)
            result.subject = subject.name
            result.topic = topic.name

            for q in payload.questions:
                _import_one(q, topic, payload, default_difficulty, result)
    except Exception as e:
        result.errors.append(f'Импорт прерван: {e}')
        raise

    return result


# === Разрешение Subject / Topic ============================================

def _resolve_subject(payload: FormPayload) -> Subject:
    """По slug или имени находит существующий предмет."""
    slug = payload.subject_slug
    name = payload.subject_name

    if slug:
        try:
            return Subject.objects.get(slug=slug)
        except Subject.DoesNotExist:
            pass

    if name:
        try:
            return Subject.objects.get(name__iexact=name)
        except Subject.DoesNotExist:
            pass

    # Не нашлось — ошибка: предмет должен существовать заранее,
    # чтобы не плодить опечатки от учителей.
    raise ImporterError(
        f'Предмет не найден (slug="{slug}", name="{name}"). '
        f'Создайте предмет в админке перед импортом.'
    )


def _resolve_topic(subject: Subject, topic_name: str) -> Topic:
    """Тема создаётся автоматически, если её ещё нет — в отличие от предмета."""
    topic, _created = Topic.objects.get_or_create(
        subject=subject,
        name=topic_name,
    )
    return topic


# === Запись одного вопроса ==================================================

def _import_one(
    q: QuestionDTO,
    topic: Topic,
    payload: FormPayload,
    default_difficulty: str,
    result: ImportResult,
) -> None:
    language = payload.language or 'ru'
    year = payload.year
    # Дубликат по external_id в рамках authorial — пропускаем.
    # UniqueConstraint защищает на уровне БД, но проверим заранее,
    # чтобы вернуть пользователю осмысленный счётчик.
    if q.external_id and Question.objects.filter(
        source_type='authorial', external_id=q.external_id
    ).exists():
        result.skipped_duplicates += 1
        return

    # Статус верификации зависит от наличия правильного ответа.
    has_correct = q.has_correct
    if not has_correct:
        result.drafted_no_correct += 1
    verification = 'verified' if has_correct else 'draft'

    explanation_parts = []
    if q.help_text:
        explanation_parts.append(q.help_text)
    explanation_parts.append(
        f'Импортировано из Google Forms: {q.external_id}'
    )

    question = Question.objects.create(
        text=q.title,
        topic=topic,
        difficulty=default_difficulty,
        question_type=_TYPE_MAP.get(q.type, 'single_choice'),
        explanation='\n\n'.join(explanation_parts),
        source_type='authorial',
        verification_status=verification,
        language=language,
        year=year,
        external_id=q.external_id,
        image_ref=q.image_ref or '',
        points=q.points,
    )

    if q.image_ref:
        result.skipped_images.append(q.external_id)

    for ans in q.answers:
        Answer.objects.create(
            question=question,
            text=ans.text,
            is_correct=ans.is_correct,
        )

    result.created += 1
