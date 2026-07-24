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

# Create your tests here.
