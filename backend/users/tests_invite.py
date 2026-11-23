"""Инвайт-код учителя виден только администратору."""
from django.conf import settings
from django.test import TestCase
from rest_framework.test import APIClient

from users.models import User

STRONG_PASSWORD = 'Str0ng-Test-Pass-2026'


class AdminInviteCodeTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='invite-admin', password=STRONG_PASSWORD, role='admin')
        self.teacher = User.objects.create_user(
            username='invite-teacher', password=STRONG_PASSWORD, role='teacher')
        self.student = User.objects.create_user(
            username='invite-student', password=STRONG_PASSWORD, role='student')
        self.api = APIClient()

    def test_admin_sees_code(self):
        self.api.force_authenticate(self.admin)
        response = self.api.get('/api/auth/admin/invite-code/')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['invite_code'], settings.TEACHER_INVITE_CODE)

    def test_teacher_cannot_see_code(self):
        self.api.force_authenticate(self.teacher)
        response = self.api.get('/api/auth/admin/invite-code/')
        self.assertEqual(response.status_code, 403)

    def test_student_cannot_see_code(self):
        self.api.force_authenticate(self.student)
        response = self.api.get('/api/auth/admin/invite-code/')
        self.assertEqual(response.status_code, 403)
