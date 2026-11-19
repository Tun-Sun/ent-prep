"""Карточка «Пробное тестирование INTELLECT»: метаданные пробников, включая даты.

Обычный каталог прячет предметы вне окна доступности, но ученик должен видеть,
когда пробник откроется. Этот список отдаёт только метаданные и статус.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from subjects.models import Answer, Question, Subject, Topic
from users.models import User

STRONG_PASSWORD = 'Str0ng-Test-Pass-2026'


class TrialCatalogEndpointTest(TestCase):
    def setUp(self):
        self.ent_student = User.objects.create_user(
            username='trial-catalog-ent', password=STRONG_PASSWORD, role='student',
            grade=11, track='ent')
        self.nuet_student = User.objects.create_user(
            username='trial-catalog-nuet', password=STRONG_PASSWORD, role='student',
            grade=11, track='nuet')
        self.teacher = User.objects.create_user(
            username='trial-catalog-teacher', password=STRONG_PASSWORD, role='teacher')
        self.ent1 = self._trial('ent-01', 'ent')
        self.ent2 = self._trial('ent-02', 'ent')
        self.nuet1 = self._trial('nuet-01', 'nuet')
        self.api = APIClient()

    def _trial(self, slug, track, **extra):
        return Subject.objects.create(
            name=slug, slug=slug, track=track, is_visible=True,
            question_count=10, time_limit=600, **extra)

    def _question(self, subject):
        topic, _ = Topic.objects.get_or_create(name='Math', subject=subject)
        question = Question.objects.create(
            text='2 + 2', topic=topic, question_type='single_choice',
            verification_status='verified')
        Answer.objects.create(question=question, text='4', is_correct=True)
        return question

    def rows(self, user):
        self.api.force_authenticate(user)
        response = self.api.get('/api/subjects/trials/')
        self.assertEqual(response.status_code, 200, response.data)
        return {row['slug']: row for row in response.data}

    def test_scheduled_trial_shows_dates_even_when_hidden_from_catalog(self):
        self._question(self.ent1)
        starts = timezone.now() + timedelta(days=2)
        self.ent1.available_from = starts
        self.ent1.save(update_fields=['available_from'])

        row = self.rows(self.ent_student)['ent-01']
        self.assertEqual(row['status'], 'upcoming')
        self.assertTrue(row['available_from'])
        self.assertIsNone(row['available_until'])

        self.api.force_authenticate(self.ent_student)
        catalog = self.api.get('/api/subjects/')
        slugs = {s['slug'] for s in catalog.data}
        self.assertNotIn('ent-01', slugs)
        self.assertIn('ent-02', slugs)

    def test_trials_respect_student_track(self):
        self.assertEqual(set(self.rows(self.ent_student)), {'ent-01', 'ent-02'})
        self.assertEqual(set(self.rows(self.nuet_student)), {'nuet-01'})

    def test_teacher_sees_all_tracks(self):
        self.assertEqual(set(self.rows(self.teacher)),
                         {'ent-01', 'ent-02', 'nuet-01'})

    def test_hidden_trial_is_not_listed(self):
        self.ent2.is_visible = False
        self.ent2.save(update_fields=['is_visible'])
        self.assertNotIn('ent-02', self.rows(self.ent_student))

    def test_trial_without_questions_is_marked_empty(self):
        self.assertEqual(self.rows(self.ent_student)['ent-01']['status'], 'empty')

    def test_open_trial_is_ready(self):
        self._question(self.ent1)
        row = self.rows(self.ent_student)['ent-01']
        self.assertEqual(row['status'], 'open')
        self.assertEqual(row['total_questions'], 1)

    def test_closed_trial_is_marked_closed(self):
        self._question(self.ent1)
        self.ent1.available_until = timezone.now() - timedelta(hours=1)
        self.ent1.save(update_fields=['available_until'])
        self.assertEqual(self.rows(self.ent_student)['ent-01']['status'], 'closed')
