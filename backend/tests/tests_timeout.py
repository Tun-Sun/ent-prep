"""Ответы сохраняются даже после истечения времени теста."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from subjects.models import Answer, Question, Subject, Topic
from tests.models import TestSession, TestSessionQuestion
from users.models import User

STRONG_PASSWORD = 'Str0ng-Test-Pass-2026'


class TimeoutAnswersTest(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username='timeout-student', password=STRONG_PASSWORD, role='student',
            grade=11, track='nuet')
        self.subject = Subject.objects.create(
            name='Пробный NUET 01', slug='nuet-01', track='nuet',
            is_visible=True, available_until=timezone.now() + timedelta(hours=2))
        topic = Topic.objects.create(name='Математика', subject=self.subject)
        self.question = Question.objects.create(
            text='2+2', topic=topic, question_type='single_choice',
            verification_status='verified')
        self.answer = Answer.objects.create(question=self.question, text='4', is_correct=True)
        self.api = APIClient()
        self.api.force_authenticate(self.student)

    def _expired_session(self):
        session = TestSession.objects.create(
            student=self.student, subject=self.subject, total_questions=1,
            time_limit=60, total_points=1,
            started_at=timezone.now() - timedelta(hours=1))
        TestSessionQuestion.objects.create(session=session, question=self.question, position=1)
        return session

    def test_answer_after_timeout_is_saved(self):
        session = self._expired_session()
        response = self.api.post(f'/api/tests/{session.id}/answer/', {
            'question': self.question.id, 'selected_answer': self.answer.id,
        }, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['expired'])
        session.refresh_from_db()
        self.assertTrue(session.is_completed)
        self.assertEqual(session.answers.count(), 1)

    def test_bulk_answers_after_timeout_are_saved(self):
        session = self._expired_session()
        response = self.api.post(f'/api/tests/{session.id}/answers/bulk/', {
            'answers': [{'question': self.question.id, 'selected_answer': self.answer.id}],
        }, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['expired'])
        session.refresh_from_db()
        self.assertTrue(session.is_completed)
        self.assertEqual(session.answers.count(), 1)

    def test_finish_after_timeout_returns_result(self):
        session = self._expired_session()
        response = self.api.post(f'/api/tests/{session.id}/finish/')

        self.assertEqual(response.status_code, 200, response.data)
        session.refresh_from_db()
        self.assertTrue(session.is_completed)

    def test_finish_twice_is_safe(self):
        session = self._expired_session()
        self.api.post(f'/api/tests/{session.id}/finish/')

        response = self.api.post(f'/api/tests/{session.id}/finish/')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['session_id'], session.id)
