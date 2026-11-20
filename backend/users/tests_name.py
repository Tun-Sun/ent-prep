"""Исправление ФИО учеников, пришедших из Telegram со своими никами."""
from django.test import TestCase
from rest_framework.test import APIClient

from users.models import User
from users.views import TelegramAuthView

STRONG_PASSWORD = 'Str0ng-Test-Pass-2026'


class StudentNameEditTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username='name-teacher', password=STRONG_PASSWORD, role='teacher')
        self.admin = User.objects.create_user(
            username='name-admin', password=STRONG_PASSWORD, role='admin')
        self.student = User.objects.create_user(
            username='telegram_nick', password=STRONG_PASSWORD, role='student',
            grade=11, track='ent', full_name='telegram_nick',
            first_name='Nick', last_name='')
        self.api = APIClient()

    def test_teacher_updates_full_name(self):
        self.api.force_authenticate(self.teacher)
        response = self.api.put(f'/api/auth/students/{self.student.id}/name/',
                                {'full_name': 'Ахметов Арман'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.student.refresh_from_db()
        self.assertEqual(self.student.full_name, 'Ахметов Арман')
        self.assertEqual(self.student.first_name, 'Арман')
        self.assertEqual(self.student.last_name, 'Ахметов')
        self.assertTrue(self.student.name_confirmed)

    def test_student_cannot_edit_someone_else(self):
        self.api.force_authenticate(self.student)
        response = self.api.put(f'/api/auth/students/{self.student.id}/name/',
                                {'full_name': 'Новое Имя'}, format='json')
        self.assertEqual(response.status_code, 403)
        self.student.refresh_from_db()
        self.assertEqual(self.student.full_name, 'telegram_nick')

    def test_empty_name_is_rejected(self):
        self.api.force_authenticate(self.teacher)
        response = self.api.put(f'/api/auth/students/{self.student.id}/name/',
                                {'full_name': '   '}, format='json')
        self.assertEqual(response.status_code, 400)
        self.student.refresh_from_db()
        self.assertFalse(self.student.name_confirmed)

    def test_admin_can_edit_name_from_admin_panel(self):
        self.api.force_authenticate(self.admin)
        response = self.api.patch(f'/api/auth/admin/users/{self.student.id}/',
                                  {'full_name': 'Иванов Иван'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.student.refresh_from_db()
        self.assertEqual(self.student.full_name, 'Иванов Иван')
        self.assertEqual(self.student.last_name, 'Иванов')
        self.assertTrue(self.student.name_confirmed)

    def test_telegram_does_not_overwrite_confirmed_name(self):
        TelegramAuthView._rename(self.student, 'Telegram', 'Nickname', 'telegram_nick')
        self.student.refresh_from_db()
        self.assertNotEqual(self.student.full_name, 'Telegram Nickname')

        # Пока ФИО не подтверждено, Telegram по-прежнему заполняет имя.
        self.student.name_confirmed = False
        self.student.save(update_fields=['name_confirmed'])
        TelegramAuthView._rename(self.student, 'Telegram', 'Nickname', 'telegram_nick')
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, 'Telegram')
        self.assertEqual(self.student.last_name, 'Nickname')
