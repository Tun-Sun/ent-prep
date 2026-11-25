"""Шесть пробных вариантов «Пробные от INTELLECT»: ЕНТ 01–03 и NUET 01–03.

Один `Subject` на вариант — единственная надёжная изоляция. `StartTestView`
набирает вопросы по `topic__subject_id`, поэтому в вариант 01 физически не может
попасть ни вопрос варианта 02, ни старый банк: расширить выборку из запроса
нельзя. Один предмет с тремя темами так не работает — без `topic_ids` он
смешал бы все варианты.

Метаданные держим здесь, а не в миграции: это контент, а не схема. Команда
`manage.py trial_variants` идемпотентно создаёт/выравнивает записи, а
`legacy_content --hide` по этому же списку понимает, что оставить ученикам.
"""
from __future__ import annotations

from django.db import transaction

from .models import Question, Subject

UMBRELLA = 'Пробные от INTELLECT'

# sort_order отрицательный: варианты должны стоять первыми и в каталоге, и в
# выпадающих списках админки, не сдвигая прежние 15 предметов.
TRIAL_VARIANTS = (
    {'slug': 'ent-01', 'track': 'ent', 'number': 1, 'icon': '📘', 'sort_order': -6},
    {'slug': 'ent-02', 'track': 'ent', 'number': 2, 'icon': '📘', 'sort_order': -5},
    {'slug': 'ent-03', 'track': 'ent', 'number': 3, 'icon': '📘', 'sort_order': -4},
    {'slug': 'nuet-01', 'track': 'nuet', 'number': 1, 'icon': '📗', 'sort_order': -3},
    {'slug': 'nuet-02', 'track': 'nuet', 'number': 2, 'icon': '📗', 'sort_order': -2},
    {'slug': 'nuet-03', 'track': 'nuet', 'number': 3, 'icon': '📗', 'sort_order': -1},
    {'slug': 'nuet-04', 'track': 'nuet', 'number': 4, 'icon': '📗', 'sort_order': 0},
)

TRIAL_SLUGS = tuple(variant['slug'] for variant in TRIAL_VARIANTS)

# Пробные ЕНТ идут как полноценная симуляция: три часа на вариант,
# сколько бы вопросов ни залилось. NUET — по часу на каждый из двух предметов
# (математика и критическое мышление), то есть два часа на вариант.
ENT_TRIAL_TIME_LIMIT = 3 * 60 * 60
NUET_TRIAL_TIME_LIMIT = 2 * 60 * 60
ENT_TRIAL_SLUGS = tuple(v['slug'] for v in TRIAL_VARIANTS if v['track'] == 'ent')
NUET_TRIAL_SLUGS = tuple(v['slug'] for v in TRIAL_VARIANTS if v['track'] == 'nuet')

# Ориентир для автолимита: минута на вопрос — та же цена, что у прежних
# профильных предметов (40 вопросов / 2400 секунд). Полный вариант на 120
# вопросов так получит 2 часа, поэтому для реального регламента ЕНТ (4 часа)
# есть явный оверрайд `--time-limit`.
DEFAULT_SECONDS_PER_QUESTION = 60
MIN_TIME_LIMIT = 600
MAX_TIME_LIMIT = 14400


# Роли тем пробника определяются по названию формы: одной теме — одна роль.
# Функции живут здесь, чтобы каталог пробников и старт теста считали вопросы
# по одним и тем же правилам.
def trial_topic_role(topic_name: str) -> str:
    name = (topic_name or '').casefold()
    # Матграмотность проверяем раньше математики: иначе «математическая
    # грамотность» попала бы в профильную математику.
    if 'грамотност' in name:
        return 'math_lit'
    if 'истори' in name:
        return 'history'
    if 'географ' in name:
        return 'geography'
    if 'физ' in name:
        return 'physics'
    if 'математи' in name:
        return 'math'
    return ''


def trial_topics(subject, role: str):
    return [t for t in subject.topics.all() if trial_topic_role(t.name) == role]


def variant_name(variant: dict) -> str:
    label = 'ЕНТ' if variant['track'] == 'ent' else 'NUET'
    return f"{UMBRELLA} · {label} {variant['number']:02d}"


def variant_description(variant: dict) -> str:
    label = 'ЕНТ' if variant['track'] == 'ent' else 'NUET'
    return (f'Пробный вариант {label} №{variant["number"]} от INTELLECT. '
            f'Вопросы импортируются из Google Forms.')


def _defaults(variant: dict, visible: bool = True) -> dict:
    return {
        'name': variant_name(variant),
        'track': variant['track'],
        'icon': variant['icon'],
        'description': variant_description(variant),
        'is_visible': visible,
        'subject_type': 'mandatory',
        'show_in_profiles': False,
        'sort_order': variant['sort_order'],
    }


@transaction.atomic
def ensure_trial_variants(*, dry_run: bool = False,
                          visible: bool = True) -> dict:
    """Создаёт недостающие варианты и выравнивает метаданные у существующих.

    Возвращает {'created': [...], 'updated': [...], 'unchanged': [...]} со
    слагами. `dry_run` ничего не пишет, но считает так же. `visible=False`
    готовит карточки заранее: пустой вариант не должен попадать в каталог
    раньше, чем в него залиты вопросы.
    """
    created, updated, unchanged = [], [], []

    for variant in TRIAL_VARIANTS:
        defaults = _defaults(variant, visible)
        subject = Subject.objects.filter(slug=variant['slug']).first()

        if subject is None:
            if not dry_run:
                Subject.objects.create(slug=variant['slug'], **defaults)
            created.append(variant['slug'])
            continue

        changed = [field for field, value in defaults.items()
                   if getattr(subject, field) != value]
        if not changed:
            unchanged.append(variant['slug'])
            continue
        if not dry_run:
            for field in changed:
                setattr(subject, field, defaults[field])
            subject.save(update_fields=changed)
        updated.append(variant['slug'])

    return {'created': created, 'updated': updated, 'unchanged': unchanged}


def answerable_count(subject: Subject) -> int:
    """Сколько вопросов предмета ученик реально может получить."""
    return Question.objects.filter(topic__subject=subject).answerable().count()


def count_time_limit(questions: int,
                     seconds_per_question: int = DEFAULT_SECONDS_PER_QUESTION) -> int:
    return min(MAX_TIME_LIMIT, max(MIN_TIME_LIMIT, questions * seconds_per_question))


@transaction.atomic
def sync_counts(*, seconds_per_question: int = DEFAULT_SECONDS_PER_QUESTION,
                time_limit: int | None = None,
                dry_run: bool = False) -> list[dict]:
    """Проставляет `question_count`/`time_limit` по факту импортированных вопросов.

    Предмет без вопросов не трогаем: ноль в карточке выглядит как поломка, а
    тест всё равно не стартует, пока не залита форма.
    """
    report = []
    for variant in TRIAL_VARIANTS:
        subject = Subject.objects.filter(slug=variant['slug']).first()
        if subject is None:
            report.append({'slug': variant['slug'], 'missing': True})
            continue

        total = answerable_count(subject)
        if total == 0:
            report.append({'slug': variant['slug'], 'questions': 0,
                           'question_count': subject.question_count,
                           'time_limit': subject.time_limit, 'skipped': True})
            continue

        new_count = total
        if variant['slug'] in ENT_TRIAL_SLUGS:
            fixed_limit = ENT_TRIAL_TIME_LIMIT
        elif variant['slug'] in NUET_TRIAL_SLUGS:
            fixed_limit = NUET_TRIAL_TIME_LIMIT
        else:
            fixed_limit = None
        new_limit = (time_limit
                     or fixed_limit
                     or count_time_limit(total, seconds_per_question))
        changed = (subject.question_count != new_count
                   or subject.time_limit != new_limit)
        if changed and not dry_run:
            subject.question_count = new_count
            subject.time_limit = new_limit
            subject.save(update_fields=['question_count', 'time_limit'])

        report.append({'slug': variant['slug'], 'questions': total,
                       'question_count': new_count, 'time_limit': new_limit,
                       'changed': changed})

    return report
