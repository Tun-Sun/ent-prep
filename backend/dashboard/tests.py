from django.test import TestCase
from rest_framework.test import APIClient

from users.models import User


class TeacherStudentsPermissionTest(TestCase):
    def test_admin_can_open_teacher_students(self):
        admin = User.objects.create_user(username='admin', password='password', role='admin')
        client = APIClient()
        client.force_authenticate(admin)

        response = client.get('/api/dashboard/teacher/students/')

        self.assertEqual(response.status_code, 200)

# Create your tests here.
