from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import random

from users.models import User
from subjects.models import Subject, Topic, Question, Answer
from tests.models import TestSession, AnswerRecord


class Command(BaseCommand):
    help = 'Заполняет базу моковыми данными для прототипа'

    def handle(self, *args, **options):
        self.stdout.write('🗑  Очищаем старые данные...')
        AnswerRecord.objects.all().delete()
        TestSession.objects.all().delete()
        Answer.objects.all().delete()
        Question.objects.all().delete()
        Topic.objects.all().delete()
        Subject.objects.all().delete()
        User.objects.exclude(username='admin').delete()

        self._create_users()
        self._create_math()
        self._create_russian()
        self._create_test_sessions()
        self.stdout.write(self.style.SUCCESS('✅ Моковые данные успешно загружены!'))

    def _create_users(self):
        self.stdout.write('👥 Создаём пользователей...')
        users_data = [
            ('student1', 'Алихан Нурланов', 'Школа №1', 'student'),
            ('student2', 'Дарья Смирнова', 'Школа №3', 'student'),
            ('student3', 'Бауыржан Жумабаев', 'Лицей №7', 'student'),
            ('teacher', 'Мария Ивановна', 'Школа №1', 'teacher'),
        ]
        for username, full_name, school, role in users_data:
            User.objects.create_user(
                username=username,
                email=f'{username}@entprep.test',
                password='password123',
                full_name=full_name,
                school=school,
                role=role,
            )
        self.stdout.write(f'   Создано {len(users_data)} пользователей')

    def _create_math(self):
        self.stdout.write('🔢 Создаём Математику...')
        math = Subject.objects.create(
            name='Математика', slug='math',
            icon='📐', description='Алгебра, геометрия и теория вероятностей'
        )

        topics_data = [
            ('Алгебра', [
                {
                    'text': 'Решите уравнение: 2x + 5 = 13',
                    'explanation': '2x = 13 - 5 = 8, x = 4',
                    'answers': [
                        ('x = 3', False), ('x = 4', True),
                        ('x = 5', False), ('x = 6', False),
                    ],
                    'difficulty': 'easy',
                },
                {
                    'text': 'Упростите выражение: (a + b)² - (a - b)²',
                    'explanation': 'Раскрываем квадраты: a²+2ab+b² - (a²-2ab+b²) = 4ab',
                    'answers': [
                        ('2ab', False), ('4ab', True),
                        ('2a² + 2b²', False), ('0', False),
                    ],
                    'difficulty': 'medium',
                },
                {
                    'text': 'Найдите значение выражения: 3² + 4²',
                    'explanation': '9 + 16 = 25',
                    'answers': [
                        ('12', False), ('24', False), ('25', True), ('7', False),
                    ],
                    'difficulty': 'easy',
                },
                {
                    'text': 'Решите систему: x + y = 10, x - y = 4',
                    'explanation': 'Сложим: 2x = 14, x = 7. Тогда y = 10 - 7 = 3',
                    'answers': [
                        ('(7, 3)', True), ('(6, 4)', False),
                        ('(5, 5)', False), ('(8, 2)', False),
                    ],
                    'difficulty': 'medium',
                },
                {
                    'text': 'Чему равна сумма арифметической прогрессии: 2, 5, 8, 11, 14?',
                    'explanation': 'S = (2 + 14) * 5 / 2 = 40',
                    'answers': [
                        ('35', False), ('38', False), ('40', True), ('42', False),
                    ],
                    'difficulty': 'medium',
                },
                {
                    'text': 'Найдите корень уравнения: x² - 9 = 0',
                    'explanation': 'x² = 9, x = ±3. Ответ: x = 3',
                    'answers': [
                        ('x = 3', True), ('x = -3', False),
                        ('x = 9', False), ('x = 0', False),
                    ],
                    'difficulty': 'easy',
                },
                {
                    'text': 'Какой из множителей является разложением x² - 16?',
                    'explanation': 'Разность квадратов: x² - 16 = (x-4)(x+4)',
                    'answers': [
                        ('(x-4)(x+4)', True), ('(x-16)(x+1)', False),
                        ('(x-8)(x+2)', False), ('(x-4)²', False),
                    ],
                    'difficulty': 'easy',
                },
            ]),
            ('Геометрия', [
                {
                    'text': 'Чему равна площадь прямоугольника со сторонами 5 и 8?',
                    'explanation': 'S = 5 × 8 = 40',
                    'answers': [
                        ('26', False), ('30', False), ('40', True), ('45', False),
                    ],
                    'difficulty': 'easy',
                },
                {
                    'text': 'Чему равен диаметр окружности, если радиус равен 7?',
                    'explanation': 'D = 2R = 2 × 7 = 14',
                    'answers': [
                        ('3.5', False), ('7', False), ('14', True), ('21', False),
                    ],
                    'difficulty': 'easy',
                },
                {
                    'text': 'Чему равна площадь треугольника с основанием 10 и высотой 6?',
                    'explanation': 'S = (10 × 6) / 2 = 30',
                    'answers': [
                        ('60', False), ('30', True), ('16', False), ('36', False),
                    ],
                    'difficulty': 'medium',
                },
                {
                    'text': 'Сумма углов треугольника равна:',
                    'explanation': 'Сумма внутренних углов треугольника всегда равна 180°',
                    'answers': [
                        ('90°', False), ('180°', True), ('270°', False), ('360°', False),
                    ],
                    'difficulty': 'easy',
                },
                {
                    'text': 'В прямоугольном треугольнике один катет 3, другой 4. Чему равна гипотенуза?',
                    'explanation': 'c² = 3² + 4² = 9 + 16 = 25, c = 5',
                    'answers': [
                        ('5', True), ('6', False), ('7', False), ('12', False),
                    ],
                    'difficulty': 'medium',
                },
                {
                    'text': 'Сколько градусов в одном внутреннем угле правильного шестиугольника?',
                    'explanation': '180(6-2)/6 = 120°',
                    'answers': [
                        ('100°', False), ('120°', True), ('135°', False), ('150°', False),
                    ],
                    'difficulty': 'hard',
                },
            ]),
            ('Теория вероятностей', [
                {
                    'text': 'Какова вероятность выпадения орла при подбрасывании монеты?',
                    'explanation': 'Всего 2 исхода, орёл — 1. P = 1/2 = 0.5',
                    'answers': [
                        ('0.25', False), ('0.5', True), ('0.75', False), ('1', False),
                    ],
                    'difficulty': 'easy',
                },
                {
                    'text': 'В колоде 36 карт. Какова вероятность вытянуть туза?',
                    'explanation': '4 туза из 36: P = 4/36 = 1/9 ≈ 0.11',
                    'answers': [
                        ('1/36', False), ('1/18', False), ('1/9', True), ('4/36', True),
                    ],
                    'difficulty': 'medium',
                },
                {
                    'text': 'Бросают два кубика. Какова вероятность суммы 7?',
                    'explanation': '6 комбинаций из 36: (1,6),(2,5),(3,4),(4,3),(5,2),(6,1). P=6/36=1/6',
                    'answers': [
                        ('1/12', False), ('1/6', True), ('1/4', False), ('1/3', False),
                    ],
                    'difficulty': 'hard',
                },
                {
                    'text': 'Из урны с 5 белыми и 3 чёрными шарами вынимают один шар. Какова вероятность, что он белый?',
                    'explanation': '5 белых из 8 всего: P = 5/8 = 0.625',
                    'answers': [
                        ('3/8', False), ('5/8', True), ('5/3', False), ('1/2', False),
                    ],
                    'difficulty': 'easy',
                },
                {
                    'text': 'Среднее арифметическое чисел 4, 6, 8 равно:',
                    'explanation': '(4 + 6 + 8) / 3 = 18 / 3 = 6',
                    'answers': [
                        ('4', False), ('5', False), ('6', True), ('8', False),
                    ],
                    'difficulty': 'easy',
                },
                {
                    'text': 'Дисперсия чисел 2, 4, 6, 8 равна:',
                    'explanation': 'M=(2+4+6+8)/4=5. D=((9+1+1+9)/4)=5',
                    'answers': [
                        ('3', False), ('4', False), ('5', True), ('6', False),
                    ],
                    'difficulty': 'hard',
                },
            ]),
        ]

        total_questions = 0
        for topic_name, questions in topics_data:
            topic = Topic.objects.create(name=topic_name, subject=math)
            for q_data in questions:
                q = Question.objects.create(
                    text=q_data['text'],
                    topic=topic,
                    difficulty=q_data['difficulty'],
                    explanation=q_data['explanation'],
                )
                for ans_text, is_correct in q_data['answers']:
                    Answer.objects.create(question=q, text=ans_text, is_correct=is_correct)
                total_questions += 1

        self.stdout.write(f'   Математика: {total_questions} вопросов')

    def _create_russian(self):
        self.stdout.write('📝 Создаём Русский язык...')
        russian = Subject.objects.create(
            name='Русский язык', slug='russian_language',
            icon='📖', description='Орфография, пунктуация, морфология'
        )

        topics_data = [
            ('Орфография', [
                {
                    'text': 'В каком слове пишется НН? (Кожа..ый)',
                    'explanation': 'В полном прилагательном, образованном от существительного «кожа» с основой на -н, пишется НН',
                    'answers': [
                        ('Кожаный (Н)', False), ('Кожанный (НН)', True),
                        ('Кожаный и Кожанный', False), ('Ни Н, ни НН', False),
                    ],
                    'difficulty': 'medium',
                },
                {
                    'text': 'Какое слово пишется через Ы? (Ц..ток)',
                    'explanation': 'После Ц пишется Ы (исключения: цыган, цыплёнок, цокнуть, на цыпочках)',
                    'answers': [
                        ('Цыток', False), ('Цыток (в некоторых случаях)', False),
                        ('Циток (Н)', False), ('Цыток (Н)', True),
                    ],
                    'difficulty': 'easy',
                },
                {
                    'text': 'В каком слове пишется НЕ слитно? (Н..думал)',
                    'explanation': 'НЕ с глаголами всегда пишется раздельно',
                    'answers': [
                        ('Недумал', True), ('Недомысл', True),
                        ('Ненависть (слитно)', False), ('Негодовать (слитно)', False),
                    ],
                    'difficulty': 'easy',
                },
                {
                    'text': 'В каком слове пишется Ь? (Меч..)',
                    'explanation': 'Мечь (существительное 3 склонения), а меч — глагол',
                    'answers': [
                        ('Меч (без Ь)', False), ('Мечь (с Ь)', True),
                        ('Мечтать (с Ь)', False), ('Меченый (без Ь)', False),
                    ],
                    'difficulty': 'medium',
                },
                {
                    'text': 'Как пишется: (при)ехать или (пре)ехать?',
                    'explanation': 'ПРИ — приближение (приехать = приехать к месту)',
                    'answers': [
                        ('Приехать', True), ('Преехать', False),
                        ('Оба варианта правильные', False), ('Зависит от контекста', False),
                    ],
                    'difficulty': 'easy',
                },
                {
                    'text': 'В каком ряду все слова пишутся через чередующуюся гласную корня?',
                    'explanation': 'Выр..сли, отр..сли, подр..сли — корень -раст-/-ращ-/-рос-',
                    'answers': [
                        ('Каскадёр, косить, космический', False),
                        ('Выросли, отрасль, растение', True),
                        ('Положить, лагерь, полежать', False),
                        ('Скачок, скакать, снизить', False),
                    ],
                    'difficulty': 'hard',
                },
            ]),
            ('Пунктуация', [
                {
                    'text': 'Где нужна запятая? «Ветер то усиливался то стихал»',
                    'explanation': 'При повторении союза ТО...ТО ставится запятая между ними',
                    'answers': [
                        ('Ветер, то усиливался, то стихал', False),
                        ('Ветер то усиливался, то стихал', True),
                        ('Запятые не нужны', False),
                        ('Ветер то усиливался то, стихал', False),
                    ],
                    'difficulty': 'easy',
                },
                {
                    'text': 'Какое предложение с прямой речью оформлено верно?',
                    'explanation': 'Прямая речь в кавычках, слова автора с большой буквы после закрывающей кавычки',
                    'answers': [
                        ('Он сказал: «Привет!»', True),
                        ('Он сказал: «Привет!»', True),
                        ('«Привет!» он сказал.', False),
                        ('Оба первых варианта верны', True),
                    ],
                    'difficulty': 'medium',
                },
                {
                    'text': 'Где нужна запятая? «Мы шли по лесу и вдруг увидели озеро»',
                    'explanation': 'Перед словом «вдруг» при однородных сказуемых запятая не нужна',
                    'answers': [
                        ('Мы шли по лесу, и, вдруг увидели озеро', False),
                        ('Мы шли по лесу, и вдруг увидели озеро', True),
                        ('Мы шли по лесу и вдруг, увидели озеро', False),
                        ('Запятые не нужны', False),
                    ],
                    'difficulty': 'medium',
                },
                {
                    'text': 'Какое предложение с деепричастным оборотом оформлено верно?',
                    'explanation': 'Деепричастный оборот выделяется запятыми',
                    'answers': [
                        ('Улыбаясь, он подошёл к двери.', True),
                        ('Улыбаясь он подошёл к двери.', False),
                        ('Он, улыбаясь, подошёл к двери.', True),
                        ('Оба варианта 1 и 3 верны', True),
                    ],
                    'difficulty': 'medium',
                },
                {
                    'text': 'В каком предложении нужна тире?',
                    'explanation': 'Тире ставится между подлежащим и сказуемым, выраженными существительными',
                    'answers': [
                        ('Москва — столица России.', True),
                        ('Москва — столица России', True),
                        ('Москва есть столица России.', False),
                        ('Столица России это Москва.', False),
                    ],
                    'difficulty': 'easy',
                },
                {
                    'text': 'Где нужно поставить двоеточие?',
                    'explanation': 'Двоеточие ставится перед обобщающим словом',
                    'answers': [
                        ('Всё было готово: рюкзак, палатка, еда.', True),
                        ('Всё было готово: рюкзак палатка еда.', False),
                        ('Всё было готово рюкзак, палатка, еда.', False),
                        ('Ни один из вариантов', False),
                    ],
                    'difficulty': 'medium',
                },
            ]),
            ('Морфология', [
                {
                    'text': 'Какая часть речи выражает действие?',
                    'explanation': 'Глагол обозначает действие предмета',
                    'answers': [
                        ('Существительное', False), ('Глагол', True),
                        ('Прилагательное', False), ('Наречие', False),
                    ],
                    'difficulty': 'easy',
                },
                {
                    'text': 'Укажите наречие:',
                    'explanation': 'Наречие отвечает на вопрос «как?»: быстро',
                    'answers': [
                        ('Быстрый', False), ('Быстрота', False),
                        ('Быстро', True), ('Ускорить', False),
                    ],
                    'difficulty': 'easy',
                },
                {
                    'text': 'Какое слово является причастием?',
                    'explanation': 'Причастие — особая форма глагола: прочитанный (что сделанный?)',
                    'answers': [
                        ('Читающий', True), ('Чтение', False),
                        ('Читатель', False), ('Прочитать', False),
                    ],
                    'difficulty': 'medium',
                },
                {
                    'text': 'В каком падеже слово «книга» в предложении «Нет книги на столе»?',
                    'explanation': 'При отрицании «нет» — родительный падеж',
                    'answers': [
                        ('Именительный', False), ('Родительный', True),
                        ('Дательный', False), ('Винительный', False),
                    ],
                    'difficulty': 'easy',
                },
                {
                    'text': 'Укажите словосочетание со связью УПРАВЛЕНИЕ:',
                    'explanation': 'Управление: главное слово + зависимое в косвенном падеже с предлогом или без',
                    'answers': [
                        ('Красивый сад', False), ('Читать книгу', True),
                        ('Очень быстро', False), ('Бежать навстречу', True),
                    ],
                    'difficulty': 'hard',
                },
                {
                    'text': 'Какое предложение является сложносочинённым?',
                    'explanation': 'ССП — части соединены сочинительными союзами (и, а, но)',
                    'answers': [
                        ('Солнце село, и стало холодно.', True),
                        ('Когда солнце село, стало холодно.', False),
                        ('Мне нравится читать.', False),
                        ('Я знаю, что он придёт.', False),
                    ],
                    'difficulty': 'medium',
                },
            ]),
        ]

        total_questions = 0
        for topic_name, questions in topics_data:
            topic = Topic.objects.create(name=topic_name, subject=russian)
            for q_data in questions:
                q = Question.objects.create(
                    text=q_data['text'],
                    topic=topic,
                    difficulty=q_data['difficulty'],
                    explanation=q_data['explanation'],
                )
                for ans_text, is_correct in q_data['answers']:
                    Answer.objects.create(question=q, text=ans_text, is_correct=is_correct)
                total_questions += 1

        self.stdout.write(f'   Русский язык: {total_questions} вопросов')

    def _create_test_sessions(self):
        self.stdout.write('📊 Создаём историю тестов...')
        students = User.objects.filter(role='student')
        subjects = Subject.objects.all()
        now = timezone.now()

        for student in students:
            for subject in subjects:
                # Создаём 2-4 теста на ученика по предмету
                num_sessions = random.randint(2, 4)
                for i in range(num_sessions):
                    session = TestSession.objects.create(
                        student=student,
                        subject=subject,
                        total_questions=10,
                        started_at=now - timedelta(days=random.randint(1, 30)),
                        completed_at=now - timedelta(days=random.randint(0, 29)),
                        is_completed=True,
                    )

                    # Случайные вопросы
                    questions = list(
                        Question.objects.filter(topic__subject=subject).order_by('?')[:10]
                    )

                    correct_count = 0
                    for q in questions:
                        answers = list(q.answers.all())
                        # 50-90% шанс правильного ответа для разнообразия
                        if random.random() < 0.65:
                            correct_ans = [a for a in answers if a.is_correct]
                            selected = correct_ans[0] if correct_ans else random.choice(answers)
                            is_correct = True
                            correct_count += 1
                        else:
                            wrong_answers = [a for a in answers if not a.is_correct]
                            selected = random.choice(wrong_answers) if wrong_answers else random.choice(answers)
                            is_correct = False

                        AnswerRecord.objects.create(
                            session=session,
                            question=q,
                            selected_answer=selected,
                            is_correct=is_correct,
                        )

                    session.correct_answers = correct_count
                    session.score_percent = round((correct_count / 10) * 100, 1)
                    session.save()

        total_sessions = TestSession.objects.filter(is_completed=True).count()
        self.stdout.write(f'   Создано {total_sessions} тестовых сессий')
