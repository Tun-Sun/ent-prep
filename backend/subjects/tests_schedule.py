"""Окно доступности пробников: каталог и прямой запуск."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from subjects.models import Answer, Question, Subject, Topic
from users.models import User


class SubjectScheduleTest(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username='schedule-pupil', password='password', role='student',
            grade=9, track='school', full_name='Пробный Ученик')
        self.subject = Subject.objects.create(
            name='Пробник', slug='schedule-trial', track='school',
            is_visible=True, question_count=1, time_limit=600)
        topic = Topic.objects.create(name='Тема', subject=self.subject)
        question = Question.objects.create(
            text='Вопрос', topic=topic, question_type='single_choice',
            verification_status='verified')
        Answer.objects.create(question=question, text='Верно', is_correct=True)
        Answer.objects.create(question=question, text='Неверно', is_correct=False)
        self.api = APIClient()
        self.api.force_authenticate(self.student)

    def _slugs(self):
        return {s['slug'] for s in self.api.get('/api/subjects/').data}

    def test_subject_without_dates_is_always_visible(self):
        self.assertIn(self.subject.slug, self._slugs())

    def test_subject_before_opening_is_hidden(self):
        self.subject.available_from = timezone.now() + timedelta(days=1)
        self.subject.save(update_fields=['available_from'])
        self.assertNotIn(self.subject.slug, self._slugs())

    def test_subject_after_closing_is_hidden(self):
        self.subject.available_until = timezone.now() - timedelta(days=1)
        self.subject.save(update_fields=['available_until'])
        self.assertNotIn(self.subject.slug, self._slugs())

    def test_open_subject_is_shown(self):
        self.subject.available_from = timezone.now() - timedelta(days=1)
        self.subject.available_until = timezone.now() + timedelta(days=1)
        self.subject.save(update_fields=['available_from', 'available_until'])
        self.assertIn(self.subject.slug, self._slugs())

    def test_direct_start_cannot_bypass_schedule(self):
        self.subject.available_from = timezone.now() + timedelta(days=1)
        self.subject.save(update_fields=['available_from'])
        response = self.api.post('/api/tests/start/',
                                 {'subject_id': self.subject.id}, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertIn('недоступен', response.data['error'])

    def test_teacher_still_sees_scheduled_subject(self):
        teacher = User.objects.create_user(
            username='schedule-teacher', password='password', role='teacher')
        self.subject.available_from = timezone.now() + timedelta(days=1)
        self.subject.save(update_fields=['available_from'])
        api = APIClient()
        api.force_authenticate(teacher)
        self.assertIn(self.subject.slug,
                      {s['slug'] for s in api.get('/api/subjects/').data})
