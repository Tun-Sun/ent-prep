"""Видимость групп и запасной вход по паролю для Telegram-учеников."""
from django.test import TestCase
from rest_framework.test import APIClient

from users.models import StudyGroup, User

STRONG_PASSWORD = 'Str0ng-Test-Pass-2026'


class GroupVisibilityTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='group-owner', password=STRONG_PASSWORD, role='teacher')
        self.other = User.objects.create_user(
            username='group-other', password=STRONG_PASSWORD, role='teacher')
        self.own = StudyGroup.objects.create(name='Моя группа', teacher=self.owner)
        self.foreign = StudyGroup.objects.create(name='Чужая группа', teacher=self.owner)
        self.api = APIClient()

    def test_teacher_sees_all_groups(self):
        self.api.force_authenticate(self.other)
        response = self.api.get('/api/auth/groups/')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual({row['id'] for row in response.data},
                         {self.own.id, self.foreign.id})

    def test_teacher_cannot_edit_foreign_group(self):
        self.api.force_authenticate(self.other)
        response = self.api.patch(f'/api/auth/groups/{self.own.id}/', {'name': 'Взлом'})
        self.assertEqual(response.status_code, 403)

    def test_teacher_can_edit_own_group(self):
        self.api.force_authenticate(self.owner)
        response = self.api.patch(f'/api/auth/groups/{self.own.id}/', {'name': 'Переименована'})
        self.assertEqual(response.status_code, 200, response.data)


class SetPasswordTest(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username='tg_student', password=None, role='student',
            full_name='Телеграм Ученик', telegram_id=123456)
        self.api = APIClient()
        self.api.force_authenticate(self.student)

    def test_telegram_student_can_set_password(self):
        response = self.api.post('/api/auth/login/set-password/',
                                 {'password': 'NewPass-2026'})

        self.assertEqual(response.status_code, 200, response.data)
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password('NewPass-2026'))

    def test_short_password_rejected(self):
        response = self.api.post('/api/auth/login/set-password/', {'password': '123'})
        self.assertEqual(response.status_code, 400)

    def test_existing_password_cannot_be_overwritten(self):
        self.student.set_password('Already-Set')
        self.student.save(update_fields=['password'])

        response = self.api.post('/api/auth/login/set-password/',
                                 {'password': 'Another-Pass'})

        self.assertEqual(response.status_code, 400)
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password('Already-Set'))

    def test_profile_exposes_password_flag(self):
        response = self.api.get('/api/auth/profile/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data['has_password'])
