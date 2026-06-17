"""
Парсер вопросов с entprep.org через публичный Supabase API.

entprep.org — это SPA на React/Netlify с бэкендом Supabase.
Вопросы доступны через PostgREST API без авторизации.

Структура данных:
  - type=single: обычный вопрос с 1 правильным ответом (поле c = индекс)
  - type=multiple: несколько правильных ответов (поле correct_indices = список)
  - type=matching: соответствие (поле pairs = [[левое, правое], ...])

Использование:
    # Сухой прогон (без сохранения):
    python manage.py parse_entprep --dry-run

    # Полная загрузка конкретного предмета:
    python manage.py parse_entprep --subject physics

    # Все предметы:
    python manage.py parse_entprep --all

    # Лимит вопросов:
    python manage.py parse_entprep --subject physics --max 50

    # Только конкретная тема:
    python manage.py parse_entprep --subject physics --topic electromagnetism
"""

import time
import urllib.request
import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from subjects.models import Subject, Topic, Question, Answer

# ---------------------------------------------------------------------------
# API конфигурация
# ---------------------------------------------------------------------------
API_BASE = 'https://api.entprep.org/rest/v1/questions'
ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im16dHVqbWV5a2hsZ3dxcGRvaWxmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzEyNjI0ODAsImV4cCI6MjA4NjgzODQ4MH0.6_ui3S3wM3uOd-4VuNAQd4h3KFWoXUH2fHrwTNn28fw'

HEADERS = {
    'apikey': ANON_KEY,
    'Authorization': f'Bearer {ANON_KEY}',
    'Accept': 'application/json',
}

# ---------------------------------------------------------------------------
# Маппинг предметов entprep.org → наш slug
# ---------------------------------------------------------------------------
# Маппинг: entprep_slug → (наш slug, русское название, иконка)
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

# ---------------------------------------------------------------------------
# Маппинг английских topic/subtopic → русские названия тем
# ---------------------------------------------------------------------------
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

# Паттерн для topic/subtopic → имя
# Если нет точного совпадения, используем topic как имя темы
def get_topic_name(topic, subtopic):
    """Получить русское название темы по topic/subtopic."""
    if subtopic:
        key = f'{topic}/{subtopic}'
        if key in TOPIC_NAMES:
            return TOPIC_NAMES[key]
    if topic in TOPIC_NAMES:
        return TOPIC_NAMES[topic]
    # Фоллбэк — просто topic на английском
    return topic.replace('_', ' ').title()


# ---------------------------------------------------------------------------
# API запросы
# ---------------------------------------------------------------------------
def fetch_page(select='*', filters='', limit=1000, offset=0):
    """Выполняет GET-запрос к API entprep.org."""
    url = f'{API_BASE}?select={select}&limit={limit}&offset={offset}'
    if filters:
        url += '&' + filters

    req = urllib.request.Request(url, headers=dict(HEADERS))
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read())


def fetch_all(select='*', filters='', delay=0.3, max_questions=0):
    """Загружает все вопросы по фильтру с пагинацией."""
    all_rows = []
    offset = 0

    while True:
        rows = fetch_page(select, filters, limit=1000, offset=offset)
        if not rows:
            break

        all_rows.extend(rows)

        if max_questions > 0 and len(all_rows) >= max_questions:
            all_rows = all_rows[:max_questions]
            break

        if len(rows) < 1000:
            break

        offset += 1000
        time.sleep(delay)

    return all_rows


def count_subjects():
    """Возвращает словарь {subject: count}."""
    # Получаем все subject'ы
    rows = fetch_page('subject', limit=1000)
    # Это только первая 1000 — нам нужно больше
    all_subjects = []
    offset = 0
    while True:
        rows = fetch_page('subject', limit=1000, offset=offset)
        if not rows:
            break
        all_subjects.extend(rows)
        offset += 1000
        if len(rows) < 1000:
            break

    counts = {}
    for r in all_subjects:
        s = r['subject']
        counts[s] = counts.get(s, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Обработка данных
# ---------------------------------------------------------------------------
def build_question_text(row):
    """Формирует текст вопроса из JSON-строки."""
    text = row.get('q', '')
    if not text:
        return ''

    # Если есть passage_text — добавляем как контекст
    passage = row.get('passage_text')
    if passage:
        text = f'<p><em>{passage}</em></p>\n<p>{text}</p>'
    else:
        text = f'<p>{text}</p>'

    return text


def build_explanation(row):
    """Формирует объяснение."""
    e = row.get('e', '')
    if not e:
        return ''
    return f'<p>{e}</p>'


def build_explanation_multi(row):
    """Формирует объяснение для multi-choice (с перечислением правильных)."""
    e = row.get('e', '')
    indices = row.get('correct_indices', [])
    options = row.get('o', [])

    if indices and options:
        correct_texts = [options[i] for i in indices if i < len(options)]
        prefix = 'Правильные ответы: ' + ', '.join(correct_texts) + '. '
        e = prefix + (e or '')
    elif not e:
        e = ''

    if e:
        return f'<p>{e}</p>'
    return ''


def build_explanation_matching(row):
    """Формирует объяснение для matching."""
    e = row.get('e', '')
    pairs = row.get('pairs', [])

    if pairs and not e:
        lines = ['<p><strong>Соответствия:</strong></p>']
        for left, right in pairs:
            lines.append(f'<p>{left} → {right}</p>')
        e = '\n'.join(lines)
    elif pairs and e:
        e = f'<p><strong>Соответствия:</strong></p>' + '\n'.join(
            f'<p>{left} → {right}</p>' for left, right in pairs
        ) + f'\n<p>{e}</p>'
    return e


# ---------------------------------------------------------------------------
# Команда
# ---------------------------------------------------------------------------
class Command(BaseCommand):
    help = 'Парсит вопросы с entprep.org через публичный Supabase API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--subject', type=str, default=None,
            help='Slug предмета на entprep.org (physics, math, chemistry, ...)',
        )
        parser.add_argument(
            '--all', action='store_true',
            help='Загрузить все предметы',
        )
        parser.add_argument(
            '--topic', type=str, default=None,
            help='Фильтр по topic (например electromagnetism)',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Тестовый режим без сохранения в БД',
        )
        parser.add_argument(
            '--max', type=int, default=0,
            help='Лимит вопросов (0 = все)',
        )
        parser.add_argument(
            '--delay', type=float, default=0.3,
            help='Пауза между страницами API (сек)',
        )
        parser.add_argument(
            '--list-subjects', action='store_true',
            help='Показать доступные предметы и количество вопросов',
        )
        parser.add_argument(
            '--from-json', type=str, default=None,
            help='Импорт из локальных JSON файлов (путь к директории, например data/entprep)',
        )

    def handle(self, *args, **options):
        # --list-subjects
        if options['list_subjects']:
            self._list_subjects()
            return

        json_dir = options['from_json']

        # Валидация аргументов
        if not options['subject'] and not options['all']:
            raise CommandError(
                'Укажите --subject physics или --all для загрузки всех предметов. '
                'Используйте --list-subjects чтобы увидеть доступные предметы.'
            )

        subjects_to_load = []
        if options['all']:
            subjects_to_load = list(SUBJECT_MAP.keys())
        elif options['subject']:
            subj = options['subject']
            if subj not in SUBJECT_MAP:
                raise CommandError(
                    f"Предмет '{subj}' не найден в маппинге. "
                    f"Доступные: {', '.join(sorted(SUBJECT_MAP.keys()))}"
                )
            subjects_to_load = [subj]

        topic_filter = options['topic']
        max_q = options['max']
        delay = options['delay']

        self.stdout.write(self.style.WARNING(
            f'\n  Парсер entprep.org — {"JSON файлы" if json_dir else "Supabase API"}\n'
        ))
        self.stdout.write(f'  Предметов: {len(subjects_to_load)}')
        self.stdout.write(f'  Topic filter: {topic_filter or "(все)"}')
        self.stdout.write(f'  Max: {max_q or "нет лимита"}')
        self.stdout.write(f'  Dry-run: {"да" if options["dry_run"] else "нет"}')
        if json_dir:
            self.stdout.write(f'  JSON dir: {json_dir}')
        self.stdout.write('')

        total_created = 0
        total_skipped = 0
        total_errors = 0

        for entprep_subject in subjects_to_load:
            self.stdout.write(f'\n{"="*60}')
            self.stdout.write(f'  Предмет: {entprep_subject}')

            # Ищем/создаём Subject в нашей БД
            mapping = SUBJECT_MAP.get(entprep_subject)
            if mapping:
                our_slug, our_name, our_icon = mapping
            else:
                our_slug = entprep_subject
                our_name = entprep_subject.replace('_', ' ').title()
                our_icon = '📚'

            subject, created = Subject.objects.get_or_create(
                slug=our_slug,
                defaults={'name': our_name, 'icon': our_icon},
            )
            if created:
                self.stdout.write(f'  📌 Создан предмет: {subject.name}')

            # Формируем фильтры (только для API)
            filters = f'subject=eq.{entprep_subject}'
            if topic_filter:
                filters += f'&topic=eq.{topic_filter}'

            # Загружаем данные
            self.stdout.write(f'  Загрузка вопросов...')
            if json_dir:
                rows = self._load_from_json(json_dir, entprep_subject, topic_filter, max_q)
            else:
                rows = fetch_all(
                    select='q,o,c,e,type,difficulty,topic,subtopic,'
                           'correct_indices,pairs,passage_text,source',
                    filters=filters,
                    delay=delay,
                    max_questions=max_q,
                )
            if not rows:
                self.stdout.write(self.style.WARNING('  ⚠ Нет данных, пропускаю'))
                continue
            self.stdout.write(f'  Получено: {len(rows)} вопросов')

            # Считаем по типам
            type_counts = {}
            for r in rows:
                t = r.get('type', 'single')
                type_counts[t] = type_counts.get(t, 0) + 1
            for t, c in sorted(type_counts.items()):
                self.stdout.write(f'    {t}: {c}')

            if options['dry_run']:
                self._show_preview(rows)
                continue

            # Сохраняем
            created, skipped, errors = self._save_rows(rows, subject)
            total_created += created
            total_skipped += skipped
            total_errors += errors

            self.stdout.write(self.style.SUCCESS(
                f'  ✅ Создано: {created}, пропущено (дубли): {skipped}, ошибок: {errors}'
            ))

            time.sleep(0.5)

        self.stdout.write(f'\n{"="*60}')
        self.stdout.write(self.style.SUCCESS(
            f'\n  ИТОГО: создано {total_created} вопросов, '
            f'пропущено {total_skipped}, ошибок {total_errors}\n'
        ))

    def _load_from_json(self, json_dir, subject, topic_filter, max_q):
        """Загружает вопросы из локального JSON файла."""
        filepath = Path(json_dir) / f'{subject}.json'
        if not filepath.exists():
            self.stdout.write(self.style.ERROR(f'  ❌ Файл не найден: {filepath}'))
            return []

        with open(filepath, 'r', encoding='utf-8') as f:
            rows = json.load(f)

        # Фильтруем по topic если нужно
        if topic_filter:
            rows = [r for r in rows if r.get('topic') == topic_filter]

        # Лимит
        if max_q > 0:
            rows = rows[:max_q]

        return rows

    def _save_rows(self, rows, subject):
        """Сохраняет список вопросов в БД. Возвращает (created, skipped, errors)."""
        created = 0
        skipped = 0
        errors = 0

        for row in rows:
            try:
                result = self._save_one(row, subject)
                if result == 1:
                    created += 1
                elif result == 0:
                    skipped += 1
            except Exception as e:
                errors += 1
                q_text = row.get('q', '')[:60]
                self.stdout.write(
                    self.style.ERROR(f'  ❌ Ошибка [{q_text}...]: {e}')
                )

        return created, skipped, errors

    def _save_one(self, row, subject):
        """Сохраняет один вопрос. Возвращает 1=создан, 0=дубликат."""
        q_type = row.get('type', 'single')

        if q_type == 'matching':
            return self._save_matching(row, subject)
        elif q_type == 'multiple':
            return self._save_multiple(row, subject)
        else:
            return self._save_single(row, subject)

    def _save_single(self, row, subject):
        """Сохраняет single-choice вопрос."""
        text = build_question_text(row)
        explanation = build_explanation(row)
        difficulty = row.get('difficulty', 'medium') or 'medium'

        # Проверка дубликата по тексту (первые 100 символов без HTML)
        plain = re.sub(r'<[^>]+>', '', text).strip()
        if len(plain) > 15 and Question.objects.filter(
                text__icontains=plain[:100]).exists():
            return 0

        # Тема
        topic_name = get_topic_name(row.get('topic', ''), row.get('subtopic', ''))
        topic, _ = Topic.objects.get_or_create(name=topic_name, subject=subject)

        question = Question.objects.create(
            text=text,
            topic=topic,
            difficulty=difficulty,
            explanation=explanation,
        )

        # Ответы
        options = row.get('o', [])
        correct_idx = row.get('c', 0)
        for i, opt_text in enumerate(options):
            if not opt_text:
                continue
            Answer.objects.create(
                question=question,
                text=opt_text,
                is_correct=(i == correct_idx),
            )

        return 1

    def _save_multiple(self, row, subject):
        """Сохраняет multiple-choice вопрос.

        В нашей модели Question/Answer пока нет native поддержки multiple.
        Сохраняем как обычный single с первым правильным ответом,
        а в explanation записываем все правильные индексы.
        """
        text = build_question_text(row)
        explanation = build_explanation_multi(row)
        difficulty = row.get('difficulty', 'medium') or 'medium'

        # Проверка дубликата
        plain = re.sub(r'<[^>]+>', '', text).strip()
        if len(plain) > 15 and Question.objects.filter(
                text__icontains=plain[:100]).exists():
            return 0

        topic_name = get_topic_name(row.get('topic', ''), row.get('subtopic', ''))
        topic, _ = Topic.objects.get_or_create(name=topic_name, subject=subject)

        question = Question.objects.create(
            text=text,
            topic=topic,
            difficulty=difficulty,
            explanation=explanation,
        )

        options = row.get('o', [])
        correct_indices = row.get('correct_indices', [])
        first_correct = correct_indices[0] if correct_indices else row.get('c', 0)

        for i, opt_text in enumerate(options):
            if not opt_text:
                continue
            Answer.objects.create(
                question=question,
                text=opt_text,
                is_correct=(i == first_correct),
            )

        return 1

    def _save_matching(self, row, subject):
        """Сохраняет matching вопрос.

        Matching вопросы не имеют стандартных A/B/C/D — формат «левое → правое».
        Сохраняем вопрос с текстом, а пары — в explanation.
        """
        text = build_question_text(row)
        explanation = build_explanation_matching(row)
        difficulty = row.get('difficulty', 'medium') or 'medium'

        # Проверка дубликата
        plain = re.sub(r'<[^>]+>', '', text).strip()
        if len(plain) > 15 and Question.objects.filter(
                text__icontains=plain[:100]).exists():
            return 0

        topic_name = get_topic_name(row.get('topic', ''), row.get('subtopic', ''))
        topic, _ = Topic.objects.get_or_create(name=topic_name, subject=subject)

        question = Question.objects.create(
            text=text,
            topic=topic,
            difficulty=difficulty,
            explanation=explanation,
        )

        # Для matching — варианты ответа это левые части пар
        pairs = row.get('pairs', [])
        if pairs:
            # Каждый левый элемент — это "вариант", правильный — соответствующая правая часть
            for i, (left, right) in enumerate(pairs):
                if not left:
                    continue
                # Сохраняем все как правильные (т.к. matching — все верны)
                Answer.objects.create(
                    question=question,
                    text=f'{left} → {right}',
                    is_correct=True,
                )

        # Если пар нет, но есть text — хотя бы сохраним вопрос
        if not pairs:
            Answer.objects.create(
                question=question,
                text='См. объяснение',
                is_correct=True,
            )

        return 1

    def _show_preview(self, rows):
        """Показывает превью вопросов в dry-run."""
        self.stdout.write(self.style.SUCCESS(
            f'\n  === DRY RUN: {len(rows)} вопросов ===\n'
        ))

        for i, row in enumerate(rows[:10], 1):
            q_type = row.get('type', 'single')
            text = row.get('q', '')[:80]
            topic_name = get_topic_name(row.get('topic', ''), row.get('subtopic', ''))
            difficulty = row.get('difficulty', 'medium') or 'medium'

            type_badge = f'[{q_type}]'
            self.stdout.write(f'  {i}. {type_badge} [{topic_name}] {text}')

            if q_type == 'single':
                options = row.get('o', [])
                correct = row.get('c', 0)
                for j, opt in enumerate(options):
                    mark = '✓' if j == correct else ' '
                    self.stdout.write(f'     [{mark}] {opt}')
            elif q_type == 'multiple':
                options = row.get('o', [])
                correct_indices = row.get('correct_indices', [])
                for j, opt in enumerate(options):
                    mark = '✓' if j in correct_indices else ' '
                    self.stdout.write(f'     [{mark}] {opt}')
            elif q_type == 'matching':
                pairs = row.get('pairs', [])
                for left, right in (pairs or []):
                    self.stdout.write(f'     {left} → {right}')

            e = row.get('e', '')
            if e:
                self.stdout.write(f'     💡 {e[:100]}')
            self.stdout.write('')

        if len(rows) > 10:
            self.stdout.write(f'  ... и ещё {len(rows) - 10} вопросов')

    def _list_subjects(self):
        """Показывает доступные предметы и количество вопросов."""
        self.stdout.write(self.style.WARNING(
            '\n  Предметы на entprep.org:\n'
        ))

        counts = count_subjects()
        for subj in sorted(counts):
            our_slug = SUBJECT_MAP.get(subj, '—')
            self.stdout.write(
                f'  {subj:25s}  {counts[subj]:5d} вопросов  →  slug: {our_slug}'
            )

        self.stdout.write(f'\n  Всего: {sum(counts.values())} вопросов')
        self.stdout.write('')
