"""Деактивированные ученики не висят в общих журналах и аналитике.

Снятый доступ — не удаление: история остаётся, но в списке «все ученики» и в
результатах такой человек только мешает. Его показывает отдельный фильтр.
"""
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from subjects.models import Subject
from tests.models import TestSession
from users.models import User

STRONG_PASSWORD = 'Str0ng-Test-Pass-2026'


def _session(student, subject, *, score=50.0):
    return TestSession.objects.create(
        student=student, subject=subject, total_questions=10, time_limit=600,
        total_points=10, earned_points=round(score / 10), correct_answers=5,
        score_percent=score, completed_at=timezone.now(), is_completed=True,
    )


class TeacherStudentsInactiveTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username='inactive-teacher', password=STRONG_PASSWORD, role='teacher')
        self.active = User.objects.create_user(
            username='inactive-active', password=STRONG_PASSWORD, role='student',
            grade=9, track='school', full_name='Активный Ученик')
        self.gone = User.objects.create_user(
            username='inactive-gone', password=STRONG_PASSWORD, role='student',
            grade=9, track='school', full_name='Снятый Ученик', is_active=False)
        self.api = APIClient()
        self.api.force_authenticate(self.teacher)

    def usernames(self, **params):
        response = self.api.get('/api/dashboard/teacher/students/', params)
        self.assertEqual(response.status_code, 200, response.data)
        return {row['username'] for row in response.data}

    def test_default_list_hides_deactivated(self):
        self.assertEqual(self.usernames(), {'inactive-active'})

    def test_inactive_filter_finds_them(self):
        self.assertEqual(self.usernames(status='inactive'), {'inactive-gone'})

    def test_all_filter_returns_everyone(self):
        self.assertEqual(self.usernames(status='all'),
                         {'inactive-active', 'inactive-gone'})

    def test_garbage_status_stays_on_active(self):
        self.assertEqual(self.usernames(status='???'), {'inactive-active'})


class TeacherAnalyticsInactiveTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username='analytics-teacher', password=STRONG_PASSWORD, role='teacher')
        self.subject = Subject.objects.create(
            name='История', slug='inactive-history', is_visible=True)
        self.active = User.objects.create_user(
            username='analytics-active', password=STRONG_PASSWORD, role='student',
            grade=11, track='ent', full_name='Активный Выпускник')
        self.gone = User.objects.create_user(
            username='analytics-gone', password=STRONG_PASSWORD, role='student',
            grade=11, track='ent', full_name='Снятый Выпускник', is_active=False)
        _session(self.active, self.subject, score=80)
        _session(self.gone, self.subject, score=30)
        self.api = APIClient()
        self.api.force_authenticate(self.teacher)

    def analytics(self, **params):
        response = self.api.get('/api/dashboard/teacher/analytics/', params)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_default_analytics_skips_deactivated(self):
        data = self.analytics()
        self.assertEqual(data['total_count'], 1)
        self.assertEqual([row['student_name'] for row in data['results']],
                         ['Активный Выпускник'])

    def test_inactive_filter_shows_only_deactivated(self):
        data = self.analytics(status='inactive')
        self.assertEqual(data['total_count'], 1)
        self.assertEqual([row['student_name'] for row in data['results']],
                         ['Снятый Выпускник'])

    def test_all_filter_counts_both(self):
        data = self.analytics(status='all')
        self.assertEqual(data['total_count'], 2)


class TeacherDashboardCountersInactiveTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username='counter-teacher', password=STRONG_PASSWORD, role='teacher')
        self.subject = Subject.objects.create(
            name='Математика', slug='inactive-math', is_visible=True)
        self.active = User.objects.create_user(
            username='counter-active', password=STRONG_PASSWORD, role='student',
            grade=11, track='ent', full_name='Активный')
        self.gone = User.objects.create_user(
            username='counter-gone', password=STRONG_PASSWORD, role='student',
            grade=11, track='ent', full_name='Снятый', is_active=False)
        _session(self.active, self.subject)
        _session(self.gone, self.subject)
        self.api = APIClient()
        self.api.force_authenticate(self.teacher)

    def test_dashboard_does_not_count_deactivated(self):
        response = self.api.get('/api/dashboard/teacher/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['total_students'], 1)
        self.assertEqual(response.data['total_tests'], 1)

    def test_leaderboard_hides_deactivated(self):
        self.api.force_authenticate(self.active)
        response = self.api.get('/api/dashboard/leaderboard/')
        self.assertEqual(response.status_code, 200, response.data)
        names = {row['full_name'] for row in response.data}
        self.assertNotIn('Снятый', names)
