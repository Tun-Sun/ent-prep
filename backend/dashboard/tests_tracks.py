"""Треки в кабинетах: срез учеников у тренера и старые результаты.

Тренеру нужен фильтр «школа / ЕНТ / NUET» — иначе в журнале все ученики в куче.
А ученику, сменившему трек, старые результаты нельзя прятать: ЕНТ-тесты, сданные
до перехода в школу, остаются его историей, хотя каталог уже другой.
"""
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from subjects.models import Subject
from tests.models import TestSession
from users.models import User

STRONG_PASSWORD = 'Str0ng-Test-Pass-2026'


class TeacherStudentsTrackFilterTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username='dash-teacher', password=STRONG_PASSWORD, role='teacher')
        self.school = User.objects.create_user(
            username='dash-school', password=STRONG_PASSWORD, role='student',
            grade=8, track='school', full_name='Школьник Восьмой')
        self.ent = User.objects.create_user(
            username='dash-ent', password=STRONG_PASSWORD, role='student',
            grade=11, track='ent', full_name='Выпускник ЕНТ')
        self.nuet = User.objects.create_user(
            username='dash-nuet', password=STRONG_PASSWORD, role='student',
            grade=11, track='nuet', full_name='Выпускник NUET')
        self.api = APIClient()

    def get(self, user, **params):
        self.api.force_authenticate(user)
        return self.api.get('/api/dashboard/teacher/students/', params)

    def usernames(self, response):
        self.assertEqual(response.status_code, 200, response.data)
        return {row['username'] for row in response.data}

    def test_ent_filter_returns_only_ent_students(self):
        response = self.get(self.teacher, track='ent')
        self.assertEqual(self.usernames(response), {'dash-ent'})
        row = response.data[0]
        self.assertEqual(row['track'], 'ent')
        self.assertEqual(row['grade'], 11)

    def test_nuet_filter_returns_only_nuet_students(self):
        self.assertEqual(self.usernames(self.get(self.teacher, track='nuet')),
                         {'dash-nuet'})

    def test_school_filter_returns_only_school_students(self):
        self.assertEqual(self.usernames(self.get(self.teacher, track='school')),
                         {'dash-school'})

    def test_without_filter_every_student_is_listed(self):
        self.assertEqual(self.usernames(self.get(self.teacher)),
                         {'dash-school', 'dash-ent', 'dash-nuet'})

    def test_unknown_track_is_refused(self):
        response = self.get(self.teacher, track='magistratura')
        self.assertEqual(response.status_code, 400)

    def test_student_cannot_open_the_teacher_journal(self):
        response = self.get(self.school, track='ent')
        self.assertEqual(response.status_code, 403)


class OldEntResultsStayVisibleTest(TestCase):
    """История не переписывается задним числом при смене трека."""

    def setUp(self):
        self.student = User.objects.create_user(
            username='dash-pupil', password=STRONG_PASSWORD, role='student',
            grade=9, track='school', full_name='Ученик Девятый')
        self.teacher = User.objects.create_user(
            username='dash-owner', password=STRONG_PASSWORD, role='teacher')
        self.ent_subject = Subject.objects.create(
            name='Физика ЕНТ', slug='dash-ent-subj', track='ent', is_visible=True)
        self.student.profile_subjects.add(self.ent_subject)
        TestSession.objects.create(
            student=self.student, subject=self.ent_subject,
            total_questions=10, correct_answers=7, score_percent=70,
            completed_at=timezone.now(), is_completed=True,
        )
        self.api = APIClient()
        self.api.force_authenticate(self.student)

    def test_dashboard_keeps_the_old_ent_result(self):
        response = self.api.get('/api/dashboard/student/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['total_tests'], 1)
        names = {row['name'] for row in response.data['subject_progress']}
        self.assertEqual(names, {'Физика ЕНТ'})

    def test_catalog_no_longer_offers_the_ent_subject(self):
        """Каталог режется по треку, история — нет. Это разные вещи."""
        response = self.api.get('/api/subjects/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('dash-ent-subj', {s['slug'] for s in response.data})

    def test_old_ent_lesson_stays_in_my_assignments(self):
        """Старый урок от тренера не блокируется сменой трека — он уже назначен."""
        from subjects.models import Assignment, AssignmentBlock, Question, Topic

        topic = Topic.objects.create(name='Тема', subject=self.ent_subject)
        question = Question.objects.create(
            topic=topic, text='Старая задача', question_type='open_answer',
            verification_status='verified')
        lesson = Assignment.objects.create(
            title='Старый ЕНТ-урок', subject=self.ent_subject, teacher=self.teacher,
            status='active')
        AssignmentBlock.objects.create(assignment=lesson, kind='homework',
                                       question_ids=[question.id])
        lesson.students.add(self.student)

        response = self.api.get('/api/my/assignments/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('Старый ЕНТ-урок', {a['title'] for a in response.data})
