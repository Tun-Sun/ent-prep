"""Лента результатов тренера: деактивированные — только по фильтру."""
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from subjects.models import Subject
from tests.models import TestSession
from users.models import User

STRONG_PASSWORD = 'Str0ng-Test-Pass-2026'


class TeacherHistoryInactiveTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username='history-teacher', password=STRONG_PASSWORD, role='teacher')
        self.subject = Subject.objects.create(
            name='Физика', slug='history-physics', is_visible=True)
        self.active = User.objects.create_user(
            username='history-active', password=STRONG_PASSWORD, role='student',
            full_name='Активный Ученик')
        self.gone = User.objects.create_user(
            username='history-gone', password=STRONG_PASSWORD, role='student',
            full_name='Снятый Ученик', is_active=False)
        for student in (self.active, self.gone):
            TestSession.objects.create(
                student=student, subject=self.subject, total_questions=10,
                time_limit=600, total_points=10, earned_points=5,
                correct_answers=5, score_percent=50, is_completed=True,
                completed_at=timezone.now(),
            )
        self.api = APIClient()
        self.api.force_authenticate(self.teacher)

    def names(self, **params):
        response = self.api.get('/api/tests/teacher/history/', params)
        self.assertEqual(response.status_code, 200, response.data)
        return [row['student_name'] for row in response.data]

    def test_default_hides_deactivated_results(self):
        self.assertEqual(self.names(), ['Активный Ученик'])

    def test_inactive_filter_shows_only_deactivated_results(self):
        self.assertEqual(self.names(status='inactive'), ['Снятый Ученик'])

    def test_all_filter_returns_both(self):
        self.assertEqual(sorted(self.names(status='all')),
                         ['Активный Ученик', 'Снятый Ученик'])
