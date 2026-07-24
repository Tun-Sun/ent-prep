from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
import random

from users.models import User, StudyGroup
from subjects.models import Subject, Topic, Question, Answer
from tests.models import TestSession, TestSectionResult, AnswerRecord


class Command(BaseCommand):
    help = 'Заполняет базу моковыми данными для прототипа'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Принудительно запустить (без проверки DEBUG)')
        parser.add_argument('--keep-subjects', action='store_true', help='Не удалять предметы/вопросы, использовать существующие')

    def handle(self, *args, **options):
        if not settings.DEBUG and not options['force']:
            self.stdout.write(self.style.ERROR(
                'ОТМЕНЕНО: seed_data удаляет все вопросы (34K) и заменяет моковыми.\n'
                '  Используйте --force если уверены, или DEBUG=True для локальной разработки.'
            ))
            return
        self.stdout.write('Очищаем старые данные...')
        AnswerRecord.objects.all().delete()
        TestSectionResult.objects.all().delete()
        TestSession.objects.all().delete()
        StudyGroup.objects.all().delete()

        if not options['keep_subjects']:
            Answer.objects.all().delete()
            Question.objects.all().delete()
            Topic.objects.all().delete()
            Subject.objects.all().delete()

        # Удаляем пользователей (кроме admin), затем заново создадим
        User.objects.exclude(username='admin').delete()

        self._create_users()
        self._create_groups()
        self._create_subjects()
        self._create_test_sessions()
        self._create_authorial_tests()
        self.stdout.write(self.style.SUCCESS('Mock data loaded!'))

    def _create_users(self):
        self.stdout.write('Создаём пользователей...')
        users_data = [
            ('teacher', 'Айнура Касымовна', 'Школа-лицей №1', 'teacher'),
            ('student1',  'Алихан Нурланов',      'Школа-лицей №1', 'student'),
            ('student2',  'Дарья Смирнова',        'Школа-лицей №1', 'student'),
            ('student3',  'Бауыржан Жумабаев',     'Школа-лицей №1', 'student'),
            ('student4',  'Камила Абдрахманова',   'Школа-лицей №1', 'student'),
            ('student5',  'Руслан Оспанов',        'Школа-лицей №1', 'student'),
            ('student6',  'Елена Ким',             'Гимназия №12',   'student'),
            ('student7',  'Нурсултан Ермеков',     'Гимназия №12',   'student'),
            ('student8',  'Алия Муратова',         'Гимназия №12',   'student'),
            ('student9',  'Данил Попов',           'Гимназия №12',   'student'),
            ('student10', 'Индира Сагинтаева',     'Гимназия №12',   'student'),
            ('student11', 'Максим Волков',         'Лицей №7',       'student'),
            ('student12', 'Анель Жаксылыкова',     'Лицей №7',       'student'),
            ('student13', 'Темирлан Ахметов',      'Лицей №7',       'student'),
        ]
        created_users = []
        for username, full_name, school, role in users_data:
            pwd = 'teacher123' if role == 'teacher' else 'password123'
            user = User.objects.create_user(
                username=username,
                email=f'{username}@entprep.test',
                password=pwd,
                full_name=full_name,
                school=school,
                role=role,
            )
            created_users.append(user)
        self.stdout.write(f'   Создано {len(users_data)} пользователей')
        self.teacher = created_users[0]
        self.students = created_users[1:]

    def _create_groups(self):
        self.stdout.write('Создаём группы...')
        groups_data = [
            ('ЕНТ-2 Русский',  [1, 2, 3, 4, 5]),
            ('ЕНТ-2 Каз',      [5, 6, 7, 8]),
            ('ЕНТ-1 Физика',   [7, 8, 9, 10, 11, 12]),
        ]
        for name, student_indices in groups_data:
            group = StudyGroup.objects.create(name=name, teacher=self.teacher)
            for idx in student_indices:
                if idx - 1 < len(self.students):
                    group.students.add(self.students[idx - 1])
        self.stdout.write(f'   Создано {len(groups_data)} групп')

    def _create_subjects(self):
        self.stdout.write('Создаём предметы...')
        subjects_data = [
            {
                'name': 'История Казахстана', 'slug': 'history',
                'icon': '🏛', 'subject_type': 'mandatory',
                'question_count': 20, 'time_limit': 1800,
                'topics': ['Древняя история', 'Средневековье', 'Новейшая история'],
            },
            {
                'name': 'Грамотность чтения', 'slug': 'reading',
                'icon': '📖', 'subject_type': 'mandatory',
                'question_count': 10, 'time_limit': 900,
                'topics': ['Понимание текста', 'Анализ текста'],
            },
            {
                'name': 'Математическая грамотность', 'slug': 'math_profile',
                'icon': '📐', 'subject_type': 'mandatory',
                'question_count': 10, 'time_limit': 900,
                'topics': ['Арифметика', 'Геометрия', 'Логика'],
            },
            {
                'name': 'Физика', 'slug': 'physics',
                'icon': '⚡', 'subject_type': 'profile',
                'question_count': 40, 'time_limit': 2400,
                'topics': ['Механика', 'Термодинамика', 'Электричество'],
            },
            {
                'name': 'Биология', 'slug': 'biology',
                'icon': '🧬', 'subject_type': 'profile',
                'question_count': 40, 'time_limit': 2400,
                'topics': ['Ботаника', 'Зоология', 'Анатомия'],
            },
            {
                'name': 'Информатика', 'slug': 'informatics',
                'icon': '💻', 'subject_type': 'profile',
                'question_count': 40, 'time_limit': 2400,
                'topics': ['Алгоритмы', 'Программирование', 'Сети'],
            },
            {
                'name': 'Математика', 'slug': 'math',
                'icon': '📐', 'subject_type': 'profile',
                'question_count': 40, 'time_limit': 2400,
                'topics': ['Алгебра', 'Геометрия', 'Тригонометрия'],
            },
            {
                'name': 'Химия', 'slug': 'chemistry',
                'icon': '🧪', 'subject_type': 'profile',
                'question_count': 40, 'time_limit': 2400,
                'topics': ['Общая химия', 'Органическая химия'],
            },
            {
                'name': 'География', 'slug': 'geography',
                'icon': '🌍', 'subject_type': 'profile',
                'question_count': 40, 'time_limit': 2400,
                'topics': ['Физическая география', 'Экономическая география'],
            },
            {
                'name': 'Всемирная история', 'slug': 'world_history',
                'icon': '🏛️', 'subject_type': 'profile',
                'question_count': 40, 'time_limit': 2400,
                'topics': ['Древний мир', 'Новое время'],
            },
            {
                'name': 'Английский язык', 'slug': 'english',
                'icon': '🇬🇧', 'subject_type': 'profile',
                'question_count': 40, 'time_limit': 2400,
                'topics': ['Грамматика', 'Лексика', 'Чтение'],
            },
            {
                'name': 'Основы права', 'slug': 'law',
                'icon': '⚖️', 'subject_type': 'profile',
                'question_count': 40, 'time_limit': 2400,
                'topics': ['Конституционное право', 'Уголовное право'],
            },
            {
                'name': 'Русская литература', 'slug': 'literature',
                'icon': '📚', 'subject_type': 'profile',
                'question_count': 40, 'time_limit': 2400,
                'topics': ['Классицизм', 'Реализм', 'Современная литература'],
            },
            {
                'name': 'Казахская литература', 'slug': 'literature_kazakh',
                'icon': '📖', 'subject_type': 'profile',
                'question_count': 40, 'time_limit': 2400,
                'topics': ['Абай', 'Жамбыл', 'Современная литература'],
                'is_visible': False,
            },
            {
                'name': 'Русская литература (ЕНТ)', 'slug': 'literature_russian',
                'icon': '✍️', 'subject_type': 'profile',
                'question_count': 40, 'time_limit': 2400,
                'topics': ['Поэзия', 'Проза'],
            },
        ]

        for s in subjects_data:
            slug = s['slug']
            defaults = {
                'name': s['name'], 'icon': s['icon'],
                'subject_type': s['subject_type'],
                'question_count': s['question_count'],
                'time_limit': s['time_limit'],
            }
            if 'is_visible' in s:
                defaults['is_visible'] = s['is_visible']
            subject, created = Subject.objects.update_or_create(
                slug=slug, defaults=defaults,
            )
            if created:
                for tname in s['topics']:
                    Topic.objects.create(name=tname, subject=subject)
                self._add_questions(subject)

        self.stdout.write(f'   Создано/обновлено {len(subjects_data)} предметов')

    def _add_questions(self, subject):
        difficulties = ['easy', 'easy', 'medium', 'medium', 'hard']
        templates = [
            {'text': 'Вопрос по теме {topic}. Какой ответ верный?',
             'answers': [('Правильный ответ', True), ('Неправильный А', False), ('Неправильный Б', False), ('Неправильный В', False)]},
            {'text': 'Что из перечисленного относится к {topic}?',
             'answers': [('Верный вариант', True), ('Неверный А', False), ('Неверный Б', False), ('Неверный В', False)]},
            {'text': 'Какое утверждение о {topic} верно?',
             'answers': [('Правильное утверждение', True), ('Ложное А', False), ('Ложное Б', False), ('Ложное В', False)]},
            {'text': 'Выберите правильный вариант касательно {topic}:',
             'answers': [('Правильный вариант', True), ('Ошибочный А', False), ('Ошибочный Б', False), ('Ошибочный В', False)]},
            {'text': 'Что является основным понятием в разделе {topic}?',
             'answers': [('Основное понятие', True), ('Второстепенное А', False), ('Второстепенное Б', False), ('Второстепенное В', False)]},
            {'text': 'Какое из следующих определений соответствует {topic}?',
             'answers': [('Верное определение', True), ('Неверное А', False), ('Неверное Б', False), ('Неверное В', False)]},
            {'text': 'Решите задачу по теме {topic}: 2 + 2 × 2?',
             'answers': [('6', True), ('4', False), ('8', False), ('2', False)]},
            {'text': 'Закончите фразу: "{topic} — это..."',
             'answers': [('Правильное продолжение', True), ('Неверное А', False), ('Неверное Б', False), ('Неверное В', False)]},
            {'text': 'Какой из примеров иллюстрирует {topic}?',
             'answers': [('Правильный пример', True), ('Неправильный А', False), ('Неправильный Б', False), ('Неправильный В', False)]},
            {'text': 'В чём суть концепции {topic}?',
             'answers': [('Правильная суть', True), ('Неверная А', False), ('Неверная Б', False), ('Неверная В', False)]},
        ]

        for topic in subject.topics.all():
            for template in random.sample(templates, random.randint(6, 10)):
                text = template['text'].format(topic=topic.name)
                q = Question.objects.create(
                    text=text,
                    topic=topic,
                    difficulty=random.choice(difficulties),
                    question_type='single_choice',
                    points=random.choice([1, 1, 1, 2, 3]),
                    source_type='collected',
                    verification_status='verified',
                )
                for ans_text, is_correct in template['answers']:
                    Answer.objects.create(question=q, text=ans_text, is_correct=is_correct)

    def _create_test_sessions(self):
        self.stdout.write('Создаём историю тестов...')
        subjects = list(Subject.objects.all())
        now = timezone.now()
        total = 0

        for student in self.students:
            # 10-25 тестов на ученика за последние 60 дней
            num_sessions = random.randint(10, 25)
            for _ in range(num_sessions):
                subject = random.choice(subjects)
                num_q = random.choice([5, 10, 10, 15, 20])
                days_ago = random.randint(0, 60)
                started = now - timedelta(days=days_ago, hours=random.randint(0, 5))
                completed = started + timedelta(minutes=random.randint(5, 45))

                # Разные уровни успеваемости для разных учеников
                base_skill = {
                    'student1': 0.75, 'student2': 0.85, 'student3': 0.45,
                    'student4': 0.65, 'student5': 0.55, 'student6': 0.90,
                    'student7': 0.60, 'student8': 0.70, 'student9': 0.40,
                    'student10': 0.80, 'student11': 0.35, 'student12': 0.50,
                    'student13': 0.88,
                }.get(student.username, 0.6)

                skill = base_skill + random.uniform(-0.15, 0.15)
                skill = max(0.2, min(0.98, skill))

                # Answer records
                questions = list(Question.objects.filter(
                    topic__subject=subject
                ).order_by('?')[:num_q])

                total_points = sum(q.points for q in questions)
                earned = 0
                correct = 0

                for q in questions:
                    all_answers = list(q.answers.all())
                    if random.random() < skill:
                        chosen = random.choice([a for a in all_answers if a.is_correct] or all_answers)
                        is_correct = chosen.is_correct
                    else:
                        wrong = [a for a in all_answers if not a.is_correct]
                        chosen = random.choice(wrong) if wrong else random.choice(all_answers)
                        is_correct = False
                    if is_correct:
                        correct += 1
                        earned += q.points

                session = TestSession.objects.create(
                    student=student,
                    subject=subject,
                    total_questions=num_q,
                    correct_answers=correct,
                    total_points=float(total_points),
                    earned_points=round(earned, 1),
                    score_percent=round((earned / total_points) * 100, 1) if total_points else 0,
                    started_at=started,
                    completed_at=completed,
                    is_completed=True,
                    is_ent=False,
                )

                for q in questions:
                    all_answers = list(q.answers.all())
                    if random.random() < skill:
                        chosen = random.choice([a for a in all_answers if a.is_correct] or all_answers)
                        is_correct = chosen.is_correct
                    else:
                        wrong = [a for a in all_answers if not a.is_correct]
                        chosen = random.choice(wrong) if wrong else random.choice(all_answers)
                        is_correct = False

                    AnswerRecord.objects.create(
                        session=session, question=q,
                        selected_answer=chosen,
                        is_correct=is_correct,
                        points_earned=q.points if is_correct else 0,
                        points_max=q.points,
                    )

                total += 1

        total_sessions = TestSession.objects.filter(is_completed=True).count()
        self.stdout.write(f'   Создано {total_sessions} тестовых сессий')

    def _create_authorial_tests(self):
        self.stdout.write('Создаём авторские тесты...')
        from subjects.models import Question, Answer, Topic as T
        topics = list(T.objects.filter(subject__slug__in=['physics', 'biology']))
        authorial_forms = [
            {'form_id': 'mock-form-physics-001', 'subject_slug': 'physics', 'count': 5},
            {'form_id': 'mock-form-biology-001', 'subject_slug': 'biology', 'count': 5},
        ]
        total_q = 0
        for form in authorial_forms:
            form_topics = [t for t in topics if t.subject.slug == form['subject_slug']]
            if not form_topics:
                continue
            for i in range(form['count']):
                topic = random.choice(form_topics)
                q = Question.objects.create(
                    text=f'Авторский вопрос #{i + 1} по {topic.name}',
                    topic=topic,
                    difficulty=random.choice(['easy', 'medium', 'hard']),
                    question_type='single_choice',
                    points=random.choice([1, 1, 2]),
                    source_type='authorial',
                    verification_status='verified',
                    external_id=f"{form['form_id']}/{i + 1}",
                )
                Answer.objects.create(question=q, text='Правильный ответ', is_correct=True)
                Answer.objects.create(question=q, text='Неправильный А', is_correct=False)
                Answer.objects.create(question=q, text='Неправильный Б', is_correct=False)
                Answer.objects.create(question=q, text='Неправильный В', is_correct=False)
                total_q += 1
        self.stdout.write(f'   Создано {len(authorial_forms)} форм, {total_q} вопросов')
