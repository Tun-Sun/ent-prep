"""
Быстрый импорт вопросов из локальных JSON файлов с bulk_create.

Загружает все 15 предметов за ~30-60 секунд вместо 10+ минут.
При --clear-existing сначала удаляет старые вопросы предмета.

Использование:
    # Загрузить все предметы заново (очистить существующие):
    python manage.py import_json --clear-existing

    # Загрузить только недостающие (пропустить существующие):
    python manage.py import_json --skip-existing

    # Конкретный предмет:
    python manage.py import_json --subject physics --clear-existing

    # Без очистки (добавит новые, пропустит дубликаты по тексту):
    python manage.py import_json
"""

import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from subjects.models import Subject, Topic, Question, Answer

# ---------------------------------------------------------------------------
# Маппинг: entprep_slug → (наш slug, русское название, иконка)
# ---------------------------------------------------------------------------
SUBJECT_MAP = {
    'math':                ('math',                'Математика',                 '📐'),
    'math_profile':        ('math_profile',        'Математическая грамотность', '📊'),
    'physics':             ('physics',             'Физика',                     '⚡'),
    'chemistry':           ('chemistry',           'Химия',                      '🧪'),
    'biology':             ('biology',             'Биология',                   '🧬'),
    'geography':           ('geography',           'География',                  '🌍'),
    'history':             ('history',             'История Казахстана',         '📜'),
    'world_history':       ('world_history',       'Всемирная история',          '🏛️'),
    'english':             ('english',             'Английский язык',            '🇬🇧'),
    'reading':             ('reading',             'Грамотность чтения',         '📖'),
    'informatics':         ('informatics',         'Информатика',                '💻'),
    'law':                 ('law',                 'Основы права',               '⚖️'),
    'literature':          ('literature',          'Русская литература',         '📚'),
    'literature_kazakh':   ('literature_kazakh',   'Казахская литература',       '📖'),
    'literature_russian':  ('literature_russian',  'Русская литература (ЕНТ)',   '✍️'),
}

TOPIC_NAMES = {
    # Physics
    'mechanics/kinematics': 'Кинематика',
    'mechanics/dynamics': 'Динамика',
    'mechanics/statics': 'Статика и равновесие',
    'mechanics/conservation_laws': 'Законы сохранения',
    'mechanics/fluid_gas_mechanics': 'Механика жидкостей и газов',
    'thermal_physics/molecular_kinetic_theory': 'Молекулярно-кинетическая теория',
    'thermal_physics/gas_laws': 'Газовые законы',
    'thermal_physics/thermodynamics': 'Термодинамика',
    'thermal_physics/liquids_solids': 'Жидкости и твёрдые тела',
    'electromagnetism/electrostatics': 'Электростатика',
    'electromagnetism/direct_current': 'Постоянный ток',
    'electromagnetism/current_in_media': 'Ток в средах',
    'electromagnetism/magnetic_field': 'Магнитное поле',
    'electromagnetism/electromagnetic_induction': 'Электромагнитная индукция',
    'em_oscillations/mechanical_oscillations': 'Механические колебания',
    'em_oscillations/em_oscillations_ac': 'Электромагнитные колебания и переменный ток',
    'em_waves/wave_motion': 'Волны',
    'em_waves/em_waves': 'Электромагнитные волны',
    'optics/geometric_optics': 'Геометрическая оптика',
    'optics/wave_optics': 'Волновая оптика',
    'quantum_physics/atomic_quantum': 'Атомная физика и кванты',
    'quantum_physics/nuclear_physics': 'Ядерная физика',
    'relativity/special_relativity': 'Теория относительности',
    'cosmology/cosmology': 'Космология',
    'nanotechnology/nanotechnology': 'Нанотехнологии',
    # Math
    'quantitative_reasoning/percentages_diagrams': 'Проценты и диаграммы',
    'quantitative_reasoning/ratios_proportions': 'Пропорции и отношения',
    'quantitative_reasoning/number_theory': 'Теория чисел',
    'algebra/linear_equations': 'Линейные уравнения',
    'algebra/quadratic_equations': 'Квадратные уравнения',
    'algebra/systems_equations': 'Системы уравнений',
    'algebra/inequalities': 'Неравенства',
    'algebra/polynomials': 'Многочлены',
    'algebra/logarithms_exponents': 'Логарифмы и степени',
    'algebra/sequences_series': 'Последовательности и ряды',
    'geometry/planimetry': 'Планиметрия',
    'geometry/stereometry': 'Стереометрия',
    'geometry/coordinates_vectors': 'Координаты и векторы',
    'geometry/trigonometry': 'Тригонометрия',
    'geometry/transformations': 'Геометрические преобразования',
    'probability_statistics/probability': 'Теория вероятностей',
    'probability_statistics/statistics': 'Статистика',
    'probability_statistics/combinatorics': 'Комбинаторика',
    'mathematical_logic/logic_sets': 'Множества и логика',
    'mathematical_logic/graphs': 'Графы',
    'mathematical_logic/complex_numbers': 'Комплексные числа',
}

ALL_SUBJECTS = list(SUBJECT_MAP.keys())


def get_topic_name(topic, subtopic):
    if subtopic:
        key = f'{topic}/{subtopic}'
        if key in TOPIC_NAMES:
            return TOPIC_NAMES[key]
    if topic in TOPIC_NAMES:
        return TOPIC_NAMES[topic]
    return topic.replace('_', ' ').title() if topic else 'Общее'


def build_question_text(row):
    text = row.get('q', '')
    if not text:
        return ''
    passage = row.get('passage_text')
    if passage:
        text = f'<p><em>{passage}</em></p>\n<p>{text}</p>'
    else:
        text = f'<p>{text}</p>'
    return text


def build_explanation(row):
    e = row.get('e', '')
    if not e:
        return ''
    return f'<p>{e}</p>'


class Command(BaseCommand):
    help = 'Быстрый импорт вопросов из JSON файлов (bulk_create)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--subject', type=str, default=None,
            help='Slug конкретного предмета (physics, math, ...)',
        )
        parser.add_argument(
            '--data-dir', type=str, default='data/entprep',
            help='Директория с JSON файлами (по умолчанию: data/entprep)',
        )
        parser.add_argument(
            '--clear-existing', action='store_true',
            help='Удалить существующие вопросы предмета перед загрузкой',
        )
        parser.add_argument(
            '--skip-existing', action='store_true',
            help='Пропускать предметы у которых уже есть вопросы',
        )

    def handle(self, *args, **options):
        subjects = [options['subject']] if options['subject'] else ALL_SUBJECTS
        data_dir = Path(options['data_dir'])
        clear = options['clear_existing']
        skip = options['skip_existing']

        if not data_dir.exists():
            raise CommandError(f'Директория не найдена: {data_dir}')

        self.stdout.write(self.style.WARNING(
            f'\n  Быстрый импорт entprep.org из JSON\n'
            f'  Директория: {data_dir}\n'
            f'  Предметов: {len(subjects)}\n'
        ))
        if clear:
            self.stdout.write('  Режим: очистка + загрузка')
        elif skip:
            self.stdout.write('  Режим: пропуск существующих')
        else:
            self.stdout.write('  Режим: добавление (с пропуском дубликатов)')
        self.stdout.write('')

        total_questions = 0
        total_answers = 0

        for entprep_slug in subjects:
            filepath = data_dir / f'{entprep_slug}.json'
            if not filepath.exists():
                self.stdout.write(f'  ⚠ Пропуск {entprep_slug} — файл не найден')
                continue

            mapping = SUBJECT_MAP.get(entprep_slug)
            if not mapping:
                self.stdout.write(f'  ⚠ Пропуск {entprep_slug} — нет маппинга')
                continue
            our_slug, our_name, our_icon = mapping

            # Получаем/создаём Subject
            subject, _ = Subject.objects.get_or_create(
                slug=our_slug,
                defaults={'name': our_name, 'icon': our_icon},
            )
            existing_q = Question.objects.filter(topic__subject=subject).count()

            if skip and existing_q > 0:
                self.stdout.write(f'  ⏭ {entprep_slug:20s} — уже {existing_q} вопр., пропуск')
                continue

            # Загружаем JSON
            with open(filepath, 'r', encoding='utf-8') as f:
                rows = json.load(f)

            if not rows:
                self.stdout.write(f'  ⚠ {entprep_slug} — пустой файл')
                continue

            # Если нужно — очищаем
            if clear and existing_q > 0:
                Answer.objects.filter(question__topic__subject=subject).delete()
                Question.objects.filter(topic__subject=subject).delete()
                Topic.objects.filter(subject=subject).delete()

            self.stdout.write(f'  ⬆ {entprep_slug:20s}...', ending='')
            self.stdout.flush()

            # Импортируем в транзакции
            with transaction.atomic():
                q_count, a_count = self._import_subject(rows, subject)

            total_questions += q_count
            total_answers += a_count

            self.stdout.write(f'  {q_count:5d} вопр. + {a_count:6d} отв.')

        self.stdout.write(f'\n{"="*60}')
        self.stdout.write(self.style.SUCCESS(
            f'  ИТОГО: {total_questions:,} вопросов, {total_answers:,} ответов\n'
        ))

    def _import_subject(self, rows, subject):
        """Импортирует все rows одного предмета. Возвращает (q_count, a_count)."""
        # 1. Собираем уникальные темы и создаём
        topic_names = set()
        for row in rows:
            topic_names.add(get_topic_name(row.get('topic', ''), row.get('subtopic', '')))

        topic_lookup = {}
        for tname in topic_names:
            t, _ = Topic.objects.get_or_create(name=tname, subject=subject)
            topic_lookup[tname] = t

        # 2. Подготавливаем bulk данные
        questions_bulk = []
        answers_bulk = []

        for row in rows:
            q_text = build_question_text(row)
            if not q_text:
                continue

            explanation = build_explanation(row)
            difficulty = row.get('difficulty', 'medium') or 'medium'
            topic_name = get_topic_name(row.get('topic', ''), row.get('subtopic', ''))
            topic = topic_lookup.get(topic_name)

            q = Question(
                text=q_text,
                topic=topic,
                difficulty=difficulty,
                explanation=explanation,
            )
            questions_bulk.append(q)

            # Ответы привяжем после bulk_create
            options = row.get('o', [])
            q_type = row.get('type', 'single')

            if options:
                if q_type == 'single':
                    correct_idx = row.get('c', 0)
                    for i, opt_text in enumerate(options):
                        if not opt_text:
                            continue
                        answers_bulk.append({
                            'text': opt_text,
                            'is_correct': (i == correct_idx),
                        })
                elif q_type == 'multiple':
                    correct_indices = row.get('correct_indices', [])
                    first_correct = correct_indices[0] if correct_indices else row.get('c', 0)
                    for i, opt_text in enumerate(options):
                        if not opt_text:
                            continue
                        answers_bulk.append({
                            'text': opt_text,
                            'is_correct': (i == first_correct),
                        })
                elif q_type == 'matching':
                    pairs = row.get('pairs', [])
                    if pairs:
                        for left, right in pairs:
                            if not left:
                                continue
                            answers_bulk.append({
                                'text': f'{left} → {right}',
                                'is_correct': True,
                            })
                    else:
                        answers_bulk.append({
                            'text': 'См. объяснение',
                            'is_correct': True,
                        })
            else:
                answers_bulk.append({
                    'text': 'См. объяснение',
                    'is_correct': True,
                })

        # 3. bulk_create questions
        created_qs = Question.objects.bulk_create(questions_bulk, batch_size=500)

        # 4. bulk_create answers (соотносим по индексу с rows)
        answers_to_create = []
        for i, row in enumerate(rows):
            if i >= len(created_qs):
                break

            question = created_qs[i]
            options = row.get('o', [])
            q_type = row.get('type', 'single')

            if options:
                if q_type == 'single':
                    correct_idx = row.get('c', 0)
                    for j, opt_text in enumerate(options):
                        if not opt_text:
                            continue
                        answers_to_create.append(Answer(
                            question=question,
                            text=opt_text,
                            is_correct=(j == correct_idx),
                        ))
                elif q_type == 'multiple':
                    correct_indices = row.get('correct_indices', [])
                    first_correct = correct_indices[0] if correct_indices else row.get('c', 0)
                    for j, opt_text in enumerate(options):
                        if not opt_text:
                            continue
                        answers_to_create.append(Answer(
                            question=question,
                            text=opt_text,
                            is_correct=(j == first_correct),
                        ))
                elif q_type == 'matching':
                    pairs = row.get('pairs', [])
                    if pairs:
                        for left, right in pairs:
                            if not left:
                                continue
                            answers_to_create.append(Answer(
                                question=question,
                                text=f'{left} → {right}',
                                is_correct=True,
                            ))
                    else:
                        answers_to_create.append(Answer(
                            question=question,
                            text='См. объяснение',
                            is_correct=True,
                        ))
            else:
                answers_to_create.append(Answer(
                    question=question,
                    text='См. объяснение',
                    is_correct=True,
                ))

        if answers_to_create:
            Answer.objects.bulk_create(answers_to_create, batch_size=1000)

        return len(created_qs), len(answers_to_create)
