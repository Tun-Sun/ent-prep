"""Ручной доступ к пробнику и отчёт «кто сдал / кто не сдал» по группе."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from subjects.models import Answer, Question, Subject, Topic
from tests.models import TestSession, TestSessionQuestion, TrialAccess
from users.models import StudyGroup, User

STRONG_PASSWORD = 'Str0ng-Test-Pass-2026'


class TrialAccessTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username='access-teacher', password=STRONG_PASSWORD, role='teacher')
        self.student = User.objects.create_user(
            username='access-student', password=STRONG_PASSWORD, role='student',
            grade=11, track='ent', full_name='Иванов Иван')
        self.other = User.objects.create_user(
            username='access-other', password=STRONG_PASSWORD, role='student',
            grade=11, track='ent', full_name='Петров Пётр')
        self.group = StudyGroup.objects.create(name='ЕНТ-1', teacher=self.teacher)
        self.group.students.add(self.student, self.other)

        self.subject = Subject.objects.create(
            name='Пробный вариант ЕНТ №1', slug='ent-01', track='ent',
            is_visible=True, question_count=10, time_limit=600,
            available_until=timezone.now() - timedelta(days=1))
        topic = Topic.objects.create(name='История Казахстана', subject=self.subject)
        self.question = Question.objects.create(
            text='2 + 2', topic=topic, question_type='single_choice',
            verification_status='verified')
        self.correct = Answer.objects.create(question=self.question, text='4', is_correct=True)

        self.api = APIClient()
        self.api.force_authenticate(self.teacher)

    def test_teacher_can_grant_and_revoke_manual_access(self):
        response = self.api.post('/api/tests/trial-access/', {
            'student_id': self.student.id, 'subject_id': self.subject.id,
            'note': 'Не успел',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(TrialAccess.objects.filter(
            student=self.student, subject=self.subject).exists())

        listing = self.api.get('/api/tests/trial-access/',
                               {'subject_id': self.subject.id})
        self.assertEqual(listing.status_code, 200, listing.data)
        self.assertEqual([row['student_id'] for row in listing.data], [self.student.id])

        removed = self.api.delete(
            f'/api/tests/trial-access/?student_id={self.student.id}'
            f'&subject_id={self.subject.id}')
        self.assertEqual(removed.status_code, 200)
        self.assertFalse(TrialAccess.objects.exists())

    def test_grant_is_idempotent(self):
        payload = {'student_id': self.student.id, 'subject_id': self.subject.id}
        self.api.post('/api/tests/trial-access/', payload, format='json')
        self.api.post('/api/tests/trial-access/', payload, format='json')
        self.assertEqual(TrialAccess.objects.count(), 1)

    def test_student_cannot_grant_access(self):
        self.api.force_authenticate(self.student)
        response = self.api.post('/api/tests/trial-access/', {
            'student_id': self.student.id, 'subject_id': self.subject.id,
        }, format='json')
        self.assertEqual(response.status_code, 403)

    def test_regular_subject_cannot_be_granted(self):
        regular = Subject.objects.create(name='Математика', slug='math', is_visible=True)
        response = self.api.post('/api/tests/trial-access/', {
            'student_id': self.student.id, 'subject_id': regular.id,
        }, format='json')
        self.assertEqual(response.status_code, 404)

    def test_deadline_blocks_start_and_manual_access_reopens(self):
        learner = APIClient()
        learner.force_authenticate(self.student)
        payload = {'subject_id': self.subject.id}
        blocked = learner.post('/api/tests/start/', payload, format='json')
        self.assertEqual(blocked.status_code, 403)
        self.assertIn('недоступен', blocked.data['error'])

        self.api.post('/api/tests/trial-access/', {
            'student_id': self.student.id, 'subject_id': self.subject.id,
        }, format='json')
        opened = learner.post('/api/tests/start/', payload, format='json')
        self.assertEqual(opened.status_code, 200, opened.data)

    def test_deadline_blocks_submission_until_access_is_opened(self):
        session = TestSession.objects.create(
            student=self.student, subject=self.subject, total_questions=1,
            time_limit=600, total_points=1, is_completed=False)
        TestSessionQuestion.objects.create(
            session=session, question=self.question, position=1)
        learner = APIClient()
        learner.force_authenticate(self.student)
        url = f'/api/tests/{session.id}/answer/'
        payload = {'question': self.question.id, 'selected_answer': self.correct.id}

        blocked = learner.post(url, payload, format='json')
        self.assertEqual(blocked.status_code, 403)
        self.assertIn('истёк', blocked.data['error'])

        self.api.post('/api/tests/trial-access/', {
            'student_id': self.student.id, 'subject_id': self.subject.id,
        }, format='json')
        allowed = learner.post(url, payload, format='json')
        self.assertEqual(allowed.status_code, 200, allowed.data)

    def test_catalog_hides_closed_trial_but_shows_it_to_granted_student(self):
        learner = APIClient()
        learner.force_authenticate(self.student)
        before = learner.get('/api/subjects/')
        self.assertNotIn('ent-01', {row['slug'] for row in before.data})

        self.api.post('/api/tests/trial-access/', {
            'student_id': self.student.id, 'subject_id': self.subject.id,
        }, format='json')
        after = learner.get('/api/subjects/')
        self.assertIn('ent-01', {row['slug'] for row in after.data})

        other_api = APIClient()
        other_api.force_authenticate(self.other)
        other_catalog = other_api.get('/api/subjects/')
        self.assertNotIn('ent-01', {row['slug'] for row in other_catalog.data})


class TrialStatsTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username='stats-teacher', password=STRONG_PASSWORD, role='teacher')
        self.group = StudyGroup.objects.create(name='NU-2', teacher=self.teacher)
        self.submitted = User.objects.create_user(
            username='stats-done', password=STRONG_PASSWORD, role='student',
            grade=11, track='nuet', full_name='Сдавший Ученик')
        self.missed = User.objects.create_user(
            username='stats-missed', password=STRONG_PASSWORD, role='student',
            grade=11, track='nuet', full_name='Несдавший Ученик')
        self.outsider = User.objects.create_user(
            username='stats-outsider', password=STRONG_PASSWORD, role='student',
            grade=11, track='nuet', full_name='Другая Группа')
        self.group.students.add(self.submitted, self.missed)
        self.subject = Subject.objects.create(
            name='Пробный NUET 01', slug='nuet-01', track='nuet', is_visible=True)
        TestSession.objects.create(
            student=self.submitted, subject=self.subject, total_questions=10,
            time_limit=600, total_points=10, earned_points=8, correct_answers=8,
            score_percent=80, is_completed=True, completed_at=timezone.now())
        TrialAccess.objects.create(student=self.missed, subject=self.subject,
                                   granted_by=self.teacher)
        self.api = APIClient()
        self.api.force_authenticate(self.teacher)

    def test_stats_cover_only_group_members(self):
        response = self.api.get('/api/tests/trial-access/stats/', {
            'group_id': self.group.id, 'subject_id': self.subject.id,
        })
        self.assertEqual(response.status_code, 200, response.data)
        data = response.data
        self.assertEqual(data['summary'], {'total': 2, 'submitted': 1,
                                          'not_submitted': 1, 'manual_access': 1})
        rows = {row['username']: row for row in data['results']}
        self.assertNotIn('stats-outsider', rows)
        self.assertTrue(rows['stats-done']['submitted'])
        self.assertEqual(rows['stats-done']['score_percent'], 80)
        self.assertFalse(rows['stats-missed']['submitted'])
        self.assertTrue(rows['stats-missed']['manual_access'])

    def test_stats_reflect_new_submission(self):
        url = '/api/tests/trial-access/stats/'
        params = {'group_id': self.group.id, 'subject_id': self.subject.id}
        self.assertEqual(self.api.get(url, params).data['summary']['submitted'], 1)

        TestSession.objects.create(
            student=self.missed, subject=self.subject, total_questions=10,
            time_limit=600, total_points=10, earned_points=5, correct_answers=5,
            score_percent=50, is_completed=True, completed_at=timezone.now())
        self.assertEqual(self.api.get(url, params).data['summary']['submitted'], 2)

    def test_teacher_cannot_open_stats_for_non_trial_subject(self):
        regular = Subject.objects.create(name='Математика', slug='math', is_visible=True)
        response = self.api.get('/api/tests/trial-access/stats/', {
            'group_id': self.group.id, 'subject_id': regular.id,
        })
        self.assertEqual(response.status_code, 404)
