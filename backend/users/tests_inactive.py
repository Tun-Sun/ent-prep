"""Деактивированные не теряются и не мешают: фильтр в админке и возврат доступа."""
from django.test import TestCase
from rest_framework.test import APIClient

from users.models import User

STRONG_PASSWORD = 'Str0ng-Test-Pass-2026'


class AdminUserStatusFilterTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='status-admin', password=STRONG_PASSWORD, role='admin')
        self.active = User.objects.create_user(
            username='status-active', password=STRONG_PASSWORD, role='student',
            full_name='Активный Ученик')
        self.gone = User.objects.create_user(
            username='status-gone', password=STRONG_PASSWORD, role='student',
            full_name='Снятый Ученик', is_active=False)
        self.api = APIClient()
        self.api.force_authenticate(self.admin)

    def usernames(self, **params):
        response = self.api.get('/api/auth/admin/users/', params)
        self.assertEqual(response.status_code, 200, response.data)
        return {row['username'] for row in response.data}

    def test_default_hides_deactivated(self):
        self.assertEqual(self.usernames(), {'status-admin', 'status-active'})

    def test_inactive_filter_finds_them(self):
        self.assertEqual(self.usernames(status='inactive'), {'status-gone'})

    def test_all_filter_returns_everyone(self):
        self.assertEqual(self.usernames(status='all'),
                         {'status-admin', 'status-active', 'status-gone'})


class StudentSearchStatusTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username='search-teacher', password=STRONG_PASSWORD, role='teacher')
        self.active = User.objects.create_user(
            username='search-active', password=STRONG_PASSWORD, role='student',
            full_name='Ищу Активного')
        self.gone = User.objects.create_user(
            username='search-gone', password=STRONG_PASSWORD, role='student',
            full_name='Ищу Снятого', is_active=False)
        self.api = APIClient()
        self.api.force_authenticate(self.teacher)

    def test_search_hides_deactivated_by_default(self):
        response = self.api.get('/api/auth/students/search/', {'search': 'Ищу'})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([row['username'] for row in response.data], ['search-active'])

    def test_search_can_return_deactivated(self):
        response = self.api.get('/api/auth/students/search/',
                                {'search': 'Ищу', 'status': 'inactive'})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([row['username'] for row in response.data], ['search-gone'])


class ReactivateStudentTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username='react-teacher', password=STRONG_PASSWORD, role='teacher')
        self.student = User.objects.create_user(
            username='react-student', password=STRONG_PASSWORD, role='student',
            is_active=False)
        self.admin = User.objects.create_user(
            username='react-admin', password=STRONG_PASSWORD, role='admin')

    def test_teacher_can_restore_access(self):
        api = APIClient()
        api.force_authenticate(self.teacher)
        response = api.post(f'/api/auth/students/{self.student.id}/reactivate/')

        self.assertEqual(response.status_code, 200, response.data)
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)

    def test_admin_can_restore_access(self):
        api = APIClient()
        api.force_authenticate(self.admin)
        response = api.post(f'/api/auth/students/{self.student.id}/reactivate/')

        self.assertEqual(response.status_code, 200, response.data)
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)

    def test_student_cannot_restore_own_access(self):
        api = APIClient()
        api.force_authenticate(self.student)
        response = api.post(f'/api/auth/students/{self.student.id}/reactivate/')

        self.assertEqual(response.status_code, 403)
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)

    def test_unknown_student_returns_404(self):
        api = APIClient()
        api.force_authenticate(self.teacher)
        response = api.post('/api/auth/students/999999/reactivate/')

        self.assertEqual(response.status_code, 404)
