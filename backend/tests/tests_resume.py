"""Возобновление теста, если дедлайн закрылся раньше нажатия «Завершить»."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from subjects.models import Answer, Question, Subject, Topic
from tests.models import TestSession, TestSessionQuestion
from users.models import User

STRONG_PASSWORD = 'Str0ng-Test-Pass-2026'


class ResumeTestTest(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username='resume-student', password=STRONG_PASSWORD, role='student',
            grade=11, track='nuet')
        self.subject = Subject.objects.create(
            name='Пробный NUET 01', slug='nuet-01', track='nuet',
            is_visible=True, time_limit=7200,
            available_from=timezone.now() - timedelta(hours=3),
            available_until=timezone.now() + timedelta(hours=1))
        topic = Topic.objects.create(name='Математика', subject=self.subject)
        self.question = Question.objects.create(
            text='2+2', topic=topic, question_type='single_choice',
            verification_status='verified')
        self.answer = Answer.objects.create(question=self.question, text='4', is_correct=True)
        self.session = TestSession.objects.create(
            student=self.student, subject=self.subject, total_questions=1,
            time_limit=7200, total_points=1)
        TestSessionQuestion.objects.create(session=self.session, question=self.question,
                                           position=1)
        self.api = APIClient()
        self.api.force_authenticate(self.student)

    def test_resume_returns_saved_session_and_answers(self):
        self.api.post(f'/api/tests/{self.session.id}/answer/', {
            'question': self.question.id, 'selected_answer': self.answer.id,
        }, format='json')

        response = self.api.get(f'/api/tests/resume/{self.subject.id}/')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['session_id'], self.session.id)
        self.assertEqual(len(response.data['questions']), 1)
        self.assertEqual(
            response.data['answer_map'][self.question.id]['selected_answer'],
            self.answer.id)
        self.assertGreater(response.data['time_limit'], 0)

    def test_resume_blocked_after_deadline(self):
        self.subject.available_until = timezone.now() - timedelta(hours=1)
        self.subject.save(update_fields=['available_until'])
        response = self.api.get(f'/api/tests/resume/{self.subject.id}/')
        self.assertEqual(response.status_code, 403)
        self.assertIn('истёк', response.data['error'])

    def test_manual_access_allows_resume_after_deadline(self):
        from tests.models import TrialAccess
        self.subject.available_until = timezone.now() - timedelta(hours=1)
        self.subject.save(update_fields=['available_until'])
        self.api.get(f'/api/tests/resume/{self.subject.id}/')
        TrialAccess.objects.create(student=self.student, subject=self.subject)

        response = self.api.get(f'/api/tests/resume/{self.subject.id}/')
        self.assertEqual(response.status_code, 200, response.data)

    def test_no_open_session_returns_404(self):
        self.session.is_completed = True
        self.session.save(update_fields=['is_completed'])
        response = self.api.get(f'/api/tests/resume/{self.subject.id}/')
        self.assertEqual(response.status_code, 404)
