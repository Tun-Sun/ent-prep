from django.test import TestCase
from rest_framework.test import APIClient

from tests.models import TestSession
from .models import User


class AccountDataTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='student', password='password', role='student')
        self.other_user = User.objects.create_user(username='other', password='password', role='student')
        TestSession.objects.create(student=self.user)
        TestSession.objects.create(student=self.other_user)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_clear_history_removes_only_current_user_sessions(self):
        response = self.client.delete('/api/auth/profile/history/')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(TestSession.objects.filter(student=self.user).exists())
        self.assertTrue(TestSession.objects.filter(student=self.other_user).exists())

    def test_delete_account_requires_correct_password(self):
        response = self.client.delete('/api/auth/profile/account/', {'password': 'wrong'}, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertTrue(User.objects.filter(id=self.user.id).exists())

    def test_delete_account_removes_current_user(self):
        response = self.client.delete('/api/auth/profile/account/', {'password': 'password'}, format='json')

        self.assertEqual(response.status_code, 204)
        self.assertFalse(User.objects.filter(id=self.user.id).exists())


class ChangePasswordTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='changer', password='oldpass123', role='student')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_change_password(self):
        response = self.client.post('/api/auth/login/change-password/', {
            'old_password': 'oldpass123', 'new_password': 'newpass12345',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('newpass12345'))

    def test_wrong_old_password(self):
        response = self.client.post('/api/auth/login/change-password/', {
            'old_password': 'wrong', 'new_password': 'newpass12345',
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_short_new_password(self):
        response = self.client.post('/api/auth/login/change-password/', {
            'old_password': 'oldpass123', 'new_password': 'short',
        }, format='json')
        self.assertEqual(response.status_code, 400)


class ResetStudentPasswordTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username='t', password='teachpass1', role='teacher')
        self.student = User.objects.create_user(username='pupil', password='pupilpass1', role='student')
        self.client = APIClient()

    def test_teacher_resets_and_gets_password_once(self):
        self.client.force_authenticate(self.teacher)
        response = self.client.post(f'/api/auth/students/{self.student.id}/reset-password/', {}, format='json')
        self.assertEqual(response.status_code, 200)
        new_password = response.data['new_password']
        self.assertTrue(len(new_password) >= 8)
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password(new_password))

    def test_teacher_sets_explicit_password(self):
        self.client.force_authenticate(self.teacher)
        response = self.client.post(f'/api/auth/students/{self.student.id}/reset-password/', {
            'password': 'explicit123',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password('explicit123'))

    def test_student_cannot_reset(self):
        self.client.force_authenticate(self.student)
        response = self.client.post(f'/api/auth/students/{self.student.id}/reset-password/', {}, format='json')
        self.assertEqual(response.status_code, 403)
