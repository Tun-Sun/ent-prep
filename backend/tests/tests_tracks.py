"""Треки в запуске тестов: обычный тест, Question Rush и симуляция ЕНТ.

Id предмета приходит из запроса, поэтому одной фильтрации каталога мало: прямой
вызов обязан упереться в тот же трек. Отдельно проверяем 11-классника без трека:
он получает `code: track_required`, но старые уроки и результаты это не трогает.
"""
from django.test import TestCase
from rest_framework.test import APIClient

from subjects.models import Answer, Question, Subject, Topic
from tests.models import TestSession
from users.models import User

STRONG_PASSWORD = 'Str0ng-Test-Pass-2026'


def make_choice_questions(subject, count, prefix):
    topic = Topic.objects.create(name=f'Тема · {subject.slug}', subject=subject)
    for i in range(count):
        question = Question.objects.create(
            text=f'{prefix} {i}', topic=topic,
            question_type='single_choice', verification_status='verified',
        )
        Answer.objects.create(question=question, text='Верно', is_correct=True)
        Answer.objects.create(question=question, text='Неверно', is_correct=False)


class StartTestTrackTest(TestCase):
    def setUp(self):
        self.school_subject = Subject.objects.create(
            name='Алгебра 8', slug='start-school', track='school',
            is_visible=True, question_count=3, time_limit=600)
        self.ent_subject = Subject.objects.create(
            name='Физика ЕНТ', slug='start-ent', track='ent',
            is_visible=True, question_count=3, time_limit=600)
        self.shared_subject = Subject.objects.create(
            name='Логика', slug='start-shared', track='',
            is_visible=True, question_count=3, time_limit=600)
        for subject in (self.school_subject, self.ent_subject, self.shared_subject):
            make_choice_questions(subject, 5, subject.name)

        self.school = User.objects.create_user(
            username='start-school', password=STRONG_PASSWORD, role='student',
            grade=8, track='school')
        self.ent = User.objects.create_user(
            username='start-ent', password=STRONG_PASSWORD, role='student',
            grade=11, track='ent')
        self.nuet = User.objects.create_user(
            username='start-nuet', password=STRONG_PASSWORD, role='student',
            grade=11, track='nuet')
        self.legacy = User.objects.create_user(
            username='start-legacy', password=STRONG_PASSWORD, role='student', grade=10)
        self.teacher = User.objects.create_user(
            username='start-teacher', password=STRONG_PASSWORD, role='teacher')
        self.api = APIClient()

    def start(self, user, subject):
        self.api.force_authenticate(user)
        return self.api.post('/api/tests/start/', {'subject_id': subject.id}, format='json')

    def test_school_student_starts_school_subject(self):
        response = self.start(self.school, self.school_subject)
        self.assertEqual(response.status_code, 200, response.data)

    def test_school_student_cannot_start_ent_subject(self):
        response = self.start(self.school, self.ent_subject)
        self.assertEqual(response.status_code, 403, response.data)
        self.assertIn('другому треку', response.data['error'])
        self.assertEqual(TestSession.objects.count(), 0)

    def test_school_student_can_start_shared_subject(self):
        response = self.start(self.school, self.shared_subject)
        self.assertEqual(response.status_code, 200, response.data)

    def test_ent_student_starts_ent_subject(self):
        response = self.start(self.ent, self.ent_subject)
        self.assertEqual(response.status_code, 200, response.data)

    def test_nuet_student_cannot_start_ent_subject(self):
        response = self.start(self.nuet, self.ent_subject)
        self.assertEqual(response.status_code, 403, response.data)

    def test_student_without_track_is_not_blocked(self):
        response = self.start(self.legacy, self.ent_subject)
        self.assertEqual(response.status_code, 200, response.data)

    def test_grade_11_without_track_gets_track_required(self):
        pupil = User.objects.create_user(
            username='start-no-track', password=STRONG_PASSWORD, role='student', grade=11)
        response = self.start(pupil, self.shared_subject)
        self.assertEqual(response.status_code, 403, response.data)
        self.assertEqual(response.data.get('code'), 'track_required')
        self.assertEqual(TestSession.objects.count(), 0)

    def test_teacher_starts_any_subject(self):
        response = self.start(self.teacher, self.ent_subject)
        self.assertEqual(response.status_code, 200, response.data)


class RushTrackTest(TestCase):
    """Rush — игра ЕНТ-подготовки: школе и NUET она не принадлежит."""

    def setUp(self):
        self.subject = Subject.objects.create(
            name='История Казахстана', slug='rush-hist', track='ent',
            is_visible=True, question_count=30, time_limit=600)
        make_choice_questions(self.subject, 30, 'Rush')
        self.school = User.objects.create_user(
            username='rush-school', password=STRONG_PASSWORD, role='student',
            grade=9, track='school')
        self.ent = User.objects.create_user(
            username='rush-ent', password=STRONG_PASSWORD, role='student',
            grade=11, track='ent')
        self.nuet = User.objects.create_user(
            username='rush-nuet', password=STRONG_PASSWORD, role='student',
            grade=11, track='nuet')
        self.api = APIClient()

    def rush(self, user):
        self.api.force_authenticate(user)
        return self.api.post('/api/tests/start/', {'mode': 'rush'}, format='json')

    def test_school_cannot_start_rush(self):
        response = self.rush(self.school)
        self.assertEqual(response.status_code, 403, response.data)
        self.assertIn('только в треке ЕНТ', response.data['error'])

    def test_nuet_cannot_start_rush(self):
        response = self.rush(self.nuet)
        self.assertEqual(response.status_code, 403, response.data)

    def test_ent_starts_rush(self):
        response = self.rush(self.ent)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['mode'], 'rush')

    def test_grade_11_without_track_gets_track_required(self):
        pupil = User.objects.create_user(
            username='rush-no-track', password=STRONG_PASSWORD, role='student', grade=11)
        response = self.rush(pupil)
        self.assertEqual(response.status_code, 403, response.data)
        self.assertEqual(response.data.get('code'), 'track_required')


class StartEntTrackTest(TestCase):
    """Полная симуляция ЕНТ: только трек ЕНТ, без трека — сначала выбор."""

    def setUp(self):
        self.first = Subject.objects.create(
            name='Физика', slug='ent-first', track='', is_visible=True)
        self.second = Subject.objects.create(
            name='Математика', slug='ent-second', track='', is_visible=True)
        self.school = User.objects.create_user(
            username='ent-school', password=STRONG_PASSWORD, role='student',
            grade=10, track='school')
        self.nuet = User.objects.create_user(
            username='ent-nuet', password=STRONG_PASSWORD, role='student',
            grade=11, track='nuet')
        self.teacher = User.objects.create_user(
            username='ent-teacher', password=STRONG_PASSWORD, role='teacher')
        self.api = APIClient()

    def start(self, user):
        self.api.force_authenticate(user)
        return self.api.post('/api/tests/start-ent/', {
            'profile1_id': self.first.id, 'profile2_id': self.second.id,
        }, format='json')

    def test_school_cannot_start_ent_simulation(self):
        response = self.start(self.school)
        self.assertEqual(response.status_code, 403, response.data)
        self.assertIn('только в треке ЕНТ', response.data['error'])

    def test_nuet_cannot_start_ent_simulation(self):
        response = self.start(self.nuet)
        self.assertEqual(response.status_code, 403, response.data)

    def test_grade_11_without_track_gets_track_required(self):
        pupil = User.objects.create_user(
            username='ent-no-track', password=STRONG_PASSWORD, role='student', grade=11)
        response = self.start(pupil)
        self.assertEqual(response.status_code, 403, response.data)
        self.assertEqual(response.data.get('code'), 'track_required')

    def test_teacher_is_not_blocked_by_track(self):
        """Тренер собирает симуляцию для проверки банка — ограничение не про него."""
        response = self.start(self.teacher)
        self.assertNotEqual(response.status_code, 403)
