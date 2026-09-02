from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from subjects.models import Answer, Question, Subject, Topic
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
