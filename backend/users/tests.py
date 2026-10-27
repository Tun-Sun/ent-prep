from django.test import TestCase, override_settings
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


class RegistrationTest(TestCase):
    """Регистрация на платформе: ученик 5–11 с классом, преподаватель — только по коду."""

    def setUp(self):
        self.client = APIClient()

    def post(self, **data):
        payload = {'username': 'pupil1', 'password': 'strongpass1',
                   'full_name': 'Ахметов Арман', 'grade': 10}
        payload.update(data)
        return self.client.post('/api/auth/register/', payload, format='json')

    def test_student_registered_with_grade(self):
        response = self.post()
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(username='pupil1')
        self.assertEqual(user.role, 'student')
        self.assertEqual(user.grade, 10)
        self.assertEqual(user.last_name, 'Ахметов')
        self.assertEqual(user.first_name, 'Арман')
        self.assertFalse(user.is_staff)

    def test_student_requires_grade(self):
        response = self.post(grade=None)
        self.assertEqual(response.status_code, 400)
        self.assertIn('grade', response.data)
        self.assertFalse(User.objects.filter(username='pupil1').exists())

    def test_grade_out_of_range_rejected(self):
        for grade in (4, 12):
            response = self.post(grade=grade)
            self.assertEqual(response.status_code, 400)
            self.assertIn('grade', response.data)

    def test_old_frontend_role_is_still_ignored(self):
        """Старый фронт присылал `role` без вкладки — регистрация всё равно ученик."""
        response = self.post(role='teacher')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(User.objects.get(username='pupil1').role, 'student')

    def test_teacher_needs_invite_code(self):
        response = self.post(account_type='teacher', email='t@pmci.kz', invite_code='oops')
        self.assertEqual(response.status_code, 400)
        self.assertIn('invite_code', response.data)
        self.assertEqual(response.data['invite_code'][0], 'Неверный инвайт-код преподавателя')

    def test_teacher_with_code_and_email(self):
        response = self.post(account_type='teacher', email='t@pmci.kz',
                             invite_code='PMCI', username='teacher2')
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(username='teacher2')
        self.assertEqual(user.role, 'teacher')
        # Код открывает тренерский экран платформы, но не Django-админку.
        self.assertFalse(user.is_staff)

    def test_invite_code_is_case_insensitive(self):
        """Пишут код с телефона: `pmci` и ` pmci ` должны подходить."""
        for i, code in enumerate(('pmci', ' PMCI ', 'PmCi')):
            response = self.post(account_type='teacher', email=f't{i}@pmci.kz',
                                 invite_code=code, username=f'teacher{i}')
            self.assertEqual(response.status_code, 201, response.data)

    def test_teacher_without_email(self):
        response = self.post(account_type='teacher', invite_code='PMCI',
                             email='')
        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.data)

    @override_settings(TEACHER_INVITE_CODE='')
    def test_empty_code_closes_teacher_branch(self):
        response = self.post(account_type='teacher', email='t@pmci.kz', invite_code='')
        self.assertEqual(response.status_code, 400)
        self.assertIn('invite_code', response.data)
        self.assertFalse(User.objects.filter(username='pupil1').exists())


class ProfileCardTest(TestCase):
    """Карточка «Представься»: без класса и имени баллы не к чему приложить."""

    def setUp(self):
        self.pupil = User.objects.create_user(username='tg_pupil', password='strongpass1',
                                              role='student', first_name='Арман',
                                              full_name='Арман')
        self.client = APIClient()
        self.client.force_authenticate(self.pupil)

    def test_incomplete_until_grade_and_name(self):
        self.assertFalse(self.pupil.is_profile_completed)
        response = self.client.patch('/api/auth/profile/',
                                     {'grade': 9, 'full_name': 'Ахметов Арман'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.pupil.refresh_from_db()
        self.assertEqual(self.pupil.grade, 9)
        self.assertEqual(self.pupil.last_name, 'Ахметов')
        self.assertEqual(self.pupil.first_name, 'Арман')
        self.assertTrue(self.pupil.is_profile_completed)
        self.assertTrue(response.data['profile_completed'])

    def test_bad_grade_rejected(self):
        response = self.client.patch('/api/auth/profile/', {'grade': 14}, format='json')
        self.assertEqual(response.status_code, 400)
        self.pupil.refresh_from_db()
        self.assertIsNone(self.pupil.grade)

    def test_teacher_is_never_asked(self):
        teacher = User.objects.create_user(username='tg_teacher', password='strongpass1',
                                           role='teacher')
        self.assertTrue(teacher.is_profile_completed)
