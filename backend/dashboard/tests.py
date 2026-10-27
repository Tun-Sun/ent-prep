from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from subjects import sso
from subjects.models import (
    Answer, Assignment, AssignmentAnswer, AssignmentBlock, AssignmentSubmission,
    Question, Subject, Topic,
)
from tests.models import AnswerRecord, TestSectionResult, TestSession, TestSessionQuestion
from users.models import User

from .views import _ent_forecast_for, _weak_topics_for


def _subject(name, slug, subject_type='profile'):
    return Subject.objects.create(
        name=name, slug=slug, subject_type=subject_type,
        is_visible=True, question_count=5, time_limit=600,
        ent_question_count=40, ent_max_score=50, ent_threshold=5,
    )


def _add_questions(topic, n=5):
    questions = []
    for i in range(n):
        q = Question.objects.create(
            text=f'Вопрос {topic.name} {i}', topic=topic,
            question_type='single_choice', verification_status='verified',
        )
        Answer.objects.create(question=q, text='Верно', is_correct=True)
        Answer.objects.create(question=q, text='Неверно', is_correct=False)
        questions.append(q)
    return questions


def _completed_session(student, questions, correct_count, subject=None, is_ent=False):
    session = TestSession.objects.create(
        student=student, subject=subject, is_ent=is_ent,
        total_questions=len(questions), time_limit=600,
        total_points=len(questions), earned_points=correct_count,
        correct_answers=correct_count,
        score_percent=round(correct_count / len(questions) * 100, 1),
        completed_at=timezone.now(), is_completed=True,
    )
    AnswerRecord.objects.bulk_create([
        AnswerRecord(
            session=session, question=q,
            selected_answer=q.answers.filter(is_correct=i < correct_count).first(),
            is_correct=i < correct_count,
            points_earned=1 if i < correct_count else 0, points_max=1,
        )
        for i, q in enumerate(questions)
    ])
    return session


class WeakTopicsTest(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username='weak-student', password='password', role='student')
        self.subject = _subject('Биология', 'bio-weak')
        self.topic = Topic.objects.create(name='Генетика', subject=self.subject)
        self.questions = _add_questions(self.topic, n=6)

    def test_weak_topic_detected(self):
        _completed_session(self.student, self.questions, correct_count=1)
        topics = _weak_topics_for(self.student)
        self.assertEqual(len(topics), 1)
        self.assertEqual(topics[0]['topic'], 'Генетика')
        self.assertLess(topics[0]['accuracy'], 50)

    def test_strong_topic_not_listed(self):
        _completed_session(self.student, self.questions, correct_count=5)
        topics = _weak_topics_for(self.student)
        self.assertEqual(topics, [])

    def test_endpoint_groups_by_subject(self):
        _completed_session(self.student, self.questions, correct_count=1)
        client = APIClient()
        client.force_authenticate(self.student)
        response = client.get('/api/dashboard/student/weak-topics/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['groups']), 1)
        group = response.data['groups'][0]
        self.assertEqual(group['subject'], 'Биология')
        self.assertEqual(len(group['topic_ids']), 1)


class EntForecastTest(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username='forecast-student', password='password', role='student')
        self.history = _subject('История КЗ', 'history-f', subject_type='mandatory')
        self.profile = _subject('Физика', 'physics-f')

    def _ent_session(self, history_correct, profile_correct):
        hq = _add_questions(Topic.objects.create(name='Ист', subject=self.history), 20)
        pq = _add_questions(Topic.objects.create(name='Физ', subject=self.profile), 40)
        session = TestSession.objects.create(
            student=self.student, is_ent=True,
            total_questions=60, time_limit=14400,
            total_points=60, earned_points=history_correct + profile_correct,
            correct_answers=history_correct + profile_correct,
            completed_at=timezone.now(), is_completed=True,
        )
        TestSessionQuestion.objects.bulk_create([
            TestSessionQuestion(session=session, question=q, position=i + 1, section='history')
            for i, q in enumerate(hq)
        ] + [
            TestSessionQuestion(session=session, question=q, position=21 + i, section='profile1')
            for i, q in enumerate(pq)
        ])
        for i, q in enumerate(hq):
            AnswerRecord.objects.create(
                session=session, question=q,
                selected_answer=q.answers.filter(is_correct=i < history_correct).first(),
                is_correct=i < history_correct,
                points_earned=1 if i < history_correct else 0, points_max=1,
            )
        for i, q in enumerate(pq):
            AnswerRecord.objects.create(
                session=session, question=q,
                selected_answer=q.answers.filter(is_correct=i < profile_correct).first(),
                is_correct=i < profile_correct,
                points_earned=1 if i < profile_correct else 0, points_max=1,
            )
        TestSectionResult.objects.create(
            session=session, section='history', subject=None,
            total_questions=20, answered=20, correct_answers=history_correct,
            points_earned=history_correct, points_max=20,
        )
        TestSectionResult.objects.create(
            session=session, section='profile1', subject=self.profile,
            total_questions=40, answered=40, correct_answers=profile_correct,
            points_earned=profile_correct, points_max=40,
        )
        return session

    def test_forecast_scales_to_140(self):
        # 10/20 истории и 20/40 физики → 10 + 25 = 35 из 140
        self._ent_session(10, 20)
        forecast = _ent_forecast_for(self.student)
        self.assertTrue(forecast['has_ent_sessions'])
        self.assertEqual(forecast['score'], 35.0)

        sections = {s['name']: s for s in forecast['sections']}
        self.assertEqual(sections['История Казахстана']['score'], 10.0)
        self.assertEqual(sections['Физика']['score'], 25.0)
        self.assertTrue(sections['Физика']['passes'])

    def test_forecast_empty_without_sessions(self):
        forecast = _ent_forecast_for(self.student)
        self.assertFalse(forecast['has_ent_sessions'])
        self.assertIsNone(forecast['score'])

    def test_forecast_trend_falling(self):
        s1 = self._ent_session(18, 36)
        s1.completed_at = timezone.now() - timedelta(days=10)
        s1.save(update_fields=['completed_at'])
        self._ent_session(8, 16)
        forecast = _ent_forecast_for(self.student)
        self.assertEqual(forecast['trend'], 'falling')


class StudentReportPdfTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username='report-teacher', password='password', role='teacher')
        self.student = User.objects.create_user(
            username='report-student', password='password', role='student', full_name='Иван Иванов',
        )
        self.subject = _subject('Химия', 'chem-report')
        self.topic = Topic.objects.create(name='Органика', subject=self.subject)
        self.questions = _add_questions(self.topic, n=5)

    def test_teacher_downloads_pdf(self):
        _completed_session(self.student, self.questions, correct_count=4, subject=self.subject)
        client = APIClient()
        client.force_authenticate(self.teacher)
        response = client.get(f'/api/dashboard/teacher/students/{self.student.id}/report.pdf/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_student_cannot_download(self):
        client = APIClient()
        client.force_authenticate(self.student)
        response = client.get(f'/api/dashboard/teacher/students/{self.student.id}/report.pdf/')
        self.assertEqual(response.status_code, 403)


class TeacherStudentsPermissionTest(TestCase):
    def test_admin_can_open_teacher_students(self):
        admin = User.objects.create_user(username='admin', password='password', role='admin')
        client = APIClient()
        client.force_authenticate(admin)

        response = client.get('/api/dashboard/teacher/students/')

        self.assertEqual(response.status_code, 200)


def _client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


class TeacherCabinetOverviewTest(TestCase):
    """Что тренер видит на `/teacher` после того, как платформа стала общей для 5–11.

    Три вещи здесь раньше были не те: дашборд показывал все 15 предметов ЕНТ, очередь
    ручной проверки была невидимой, а активные уроки не отдавали счётчик сдавших.
    """

    def setUp(self):
        self.teacher = User.objects.create_user(username='cab-teacher', password='password', role='teacher')
        self.other_teacher = User.objects.create_user(username='cab-teacher2', password='password', role='teacher')
        self.student = User.objects.create_user(username='cab-student', password='password', role='student')
        self.second = User.objects.create_user(username='cab-student2', password='password', role='student')

        self.math = _subject('Математика', 'math')
        self.physics = _subject('Физика', 'physics')
        self.history = _subject('История', 'history')
        self.topic = Topic.objects.create(name='Алгебра', subject=self.math)
        self.questions = _add_questions(self.topic, n=2)
        self.block = self._lesson(self.teacher, self.math, 'Термодинамика · 10 класс')

    def _lesson(self, teacher, subject, title, status='active'):
        lesson = Assignment.objects.create(
            teacher=teacher, subject=subject, title=title, status=status,
            published_at=timezone.now(), due_at=timezone.now() + timedelta(days=3),
        )
        block = AssignmentBlock.objects.create(
            assignment=lesson, kind='homework', order=0,
            question_ids=[q.pk for q in self.questions])
        lesson.students.set([self.student, self.second])
        return block

    def _submit(self, block, student, state, verdict):
        submission = AssignmentSubmission.objects.create(
            assignment=block.assignment, block=block, student=student, state=state)
        AssignmentAnswer.objects.create(
            submission=submission, question=self.questions[0],
            raw_answer='18 см', verdict=verdict,
        )
        return submission

    def _book_question(self, subject, language):
        """Строка книжного банка: предмет в неё смотрит через тему."""
        topic = Topic.objects.create(name=f'Тема книги · {subject.name}', subject=subject)
        return Question.objects.create(
            text='Задача из книги', topic=topic,
            source_type='book_scan', language=language, verification_status='verified',
        )

    def test_shows_pending_review_queue_for_own_lessons(self):
        # своя сдача: ответ ждёт вердикта
        self._submit(self.block, self.student, 'submitted', 'pending_review')
        # чужой урок тренера тоже содержит непроверенный ответ — в очередь он не входит
        foreign_block = self._lesson(self.other_teacher, self.physics, 'Чужой урок')
        self._submit(foreign_block, self.second, 'submitted', 'pending_review')

        response = _client(self.teacher).get('/api/dashboard/teacher/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['pending_review'], 1)

    def test_reviewed_submission_still_counts_as_sent(self):
        self._submit(self.block, self.student, 'submitted', 'pending_review')
        self._submit(self.block, self.second, 'reviewed', 'correct')

        lessons = _client(self.teacher).get('/api/dashboard/teacher/').data['active_lessons']

        self.assertEqual(len(lessons), 1)
        self.assertEqual(lessons[0]['title'], 'Термодинамика · 10 класс')
        self.assertEqual(lessons[0]['subject_name'], 'Математика')
        self.assertEqual(lessons[0]['assigned_count'], 2)
        self.assertEqual(lessons[0]['submitted_count'], 2)

    def test_two_blocks_from_one_student_count_once(self):
        """Ученик, сдавший два блока, — один сдавший, а не «Сдали: 2 из 1».

        Строка сдачи привязана к блоку, поэтому счётчик обязан идти по людям.
        """
        second_block = AssignmentBlock.objects.create(
            assignment=self.block.assignment, kind='in_class', order=1,
            question_ids=[q.pk for q in self.questions])
        self._submit(self.block, self.student, 'submitted', 'pending_review')
        self._submit(second_block, self.student, 'submitted', 'pending_review')

        lesson = _client(self.teacher).get('/api/dashboard/teacher/').data['active_lessons'][0]

        self.assertEqual(lesson['submitted_count'], 1)
        self.assertEqual(lesson['assigned_count'], 2)

    def test_draft_lesson_is_not_active(self):
        self._lesson(self.teacher, self.math, 'Черновик урока', status='draft')

        lessons = _client(self.teacher).get('/api/dashboard/teacher/').data['active_lessons']

        self.assertEqual([l['title'] for l in lessons], ['Термодинамика · 10 класс'])

    def test_admin_sees_every_lesson(self):
        self._lesson(self.other_teacher, self.physics, 'Урок collegi')
        admin = User.objects.create_user(username='cab-admin', password='password', role='admin')

        lessons = _client(admin).get('/api/dashboard/teacher/').data['active_lessons']

        self.assertEqual(len(lessons), 2)

    def test_subject_stats_default_to_profile_subjects_not_ent_list(self):
        _completed_session(self.student, self.questions, correct_count=2, subject=self.math)
        _completed_session(self.student, self.questions, correct_count=1, subject=self.history)

        stats = _client(self.teacher).get('/api/dashboard/teacher/').data['subject_stats']

        # Физика в списке предметов по умолчанию, но ни урока, ни банка, ни тестов в ней
        # нет — в кабинете это пустая позиция-призрак, её не показываем
        self.assertEqual([s['name'] for s in stats], ['Математика'])

    def test_subject_with_only_book_bank_is_shown(self):
        self._book_question(self.physics, 'kk')

        stats = _client(self.teacher).get('/api/dashboard/teacher/').data['subject_stats']

        self.assertEqual(sorted(s['name'] for s in stats), ['Математика', 'Физика'])
        physics = [s for s in stats if s['name'] == 'Физика'][0]
        self.assertEqual(physics['bank_count'], 1)

    def test_chosen_dashboard_subjects_override_the_default(self):
        _completed_session(self.student, self.questions, correct_count=1, subject=self.history)
        self.teacher.dashboard_subjects.set([self.history])

        stats = _client(self.teacher).get('/api/dashboard/teacher/').data['subject_stats']

        self.assertEqual([s['name'] for s in stats], ['История'])

    def test_four_cards_on_top(self):
        """Метрики сверху: активные уроки, очередь проверки, ученики, книжный банк RU/KK."""
        self._submit(self.block, self.student, 'submitted', 'pending_review')
        self._book_question(self.math, 'ru')
        self._book_question(self.physics, 'kk')
        self._lesson(self.teacher, self.physics, 'Второй урок')

        data = _client(self.teacher).get('/api/dashboard/teacher/').data

        self.assertEqual(data['active_lesson_count'], 2)
        self.assertEqual(data['pending_review'], 1)
        self.assertEqual(data['total_students'], 2)
        self.assertEqual(data['book_bank'], {'ru': 1, 'kk': 1})

    def test_lesson_token_travels_with_the_lesson(self):
        """Ссылка урока для GetCourse строится на фронте, поэтому подпись нужна в дашборде."""
        lesson = self._lesson(self.teacher, self.math, 'Урок со ссылкой')
        with override_settings(GC_SSO_SECRET='dashboard-secret'):
            data = _client(self.teacher).get('/api/dashboard/teacher/').data

        row = [l for l in data['active_lessons'] if l['title'] == 'Урок со ссылкой'][0]
        self.assertEqual(row['lesson_token'], sso.make_lesson_token('dashboard-secret', lesson.assignment_id))

    def test_without_a_secret_the_lesson_carries_no_token(self):
        """Без `GC_SSO_SECRET` ссылка не работает — фронт по пустому токену гасит кнопку."""
        with override_settings(GC_SSO_SECRET=''):
            lessons = _client(self.teacher).get('/api/dashboard/teacher/').data['active_lessons']

        self.assertEqual(lessons[0]['lesson_token'], '')


class TeacherStudentsGradeFilterTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username='grade-teacher', password='password', role='teacher')
        self.ninth = User.objects.create_user(username='g9', password='password', role='student', grade=9)
        self.tenth = User.objects.create_user(username='g10', password='password', role='student', grade=10)
        self.tenth2 = User.objects.create_user(username='g10b', password='password', role='student', grade=10)
        self.unknown = User.objects.create_user(username='g-none', password='password', role='student')

    def _usernames(self, response):
        return sorted(s['username'] for s in response.data)

    def test_filter_by_grade(self):
        response = _client(self.teacher).get('/api/dashboard/teacher/students/?grade=10')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._usernames(response), ['g10', 'g10b'])

    def test_rows_carry_grade(self):
        response = _client(self.teacher).get('/api/dashboard/teacher/students/?grade=9')

        self.assertEqual(response.data[0]['grade'], 9)

    def test_no_filter_returns_every_student(self):
        response = _client(self.teacher).get('/api/dashboard/teacher/students/')

        self.assertEqual(len(response.data), 4)

    def test_non_numeric_grade_is_an_error_not_empty_list(self):
        response = _client(self.teacher).get('/api/dashboard/teacher/students/?grade=abc')

        self.assertEqual(response.status_code, 400)
