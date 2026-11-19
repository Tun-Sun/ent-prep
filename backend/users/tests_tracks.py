"""Трек ученика: регистрация, профиль, карточка «Представься».

Проверяем три правила, на которых держится вся система:
5–10 — принудительно школа, 11 — только ЕНТ/NUET, у тренера трека нет.
И четвёртое: профильные предметы чужого трека в профиль не прилипают.
"""
from django.test import TestCase
from rest_framework.test import APIClient

from subjects.models import Subject
from users.models import User

STRONG_PASSWORD = 'Str0ng-Test-Pass-2026'


class RegistrationTrackTest(TestCase):
    def setUp(self):
        self.api = APIClient()

    def register(self, **extra):
        body = {
            'username': 'track-pupil', 'email': 'p@example.test',
            'password': STRONG_PASSWORD, 'full_name': 'Ахметов Арман',
            'account_type': 'student',
        }
        body.update(extra)
        return self.api.post('/api/auth/register/', body, format='json')

    def test_grade_11_without_track_is_refused(self):
        response = self.register(grade=11)
        self.assertEqual(response.status_code, 400)
        self.assertIn('track', response.data)
        self.assertFalse(User.objects.filter(username='track-pupil').exists())

    def test_grade_11_nuet_is_saved(self):
        response = self.register(grade=11, track='nuet')
        self.assertEqual(response.status_code, 201, response.data)
        pupil = User.objects.get(username='track-pupil')
        self.assertEqual(pupil.track, 'nuet')
        self.assertTrue(pupil.is_profile_completed)

    def test_grade_10_forces_school_even_if_ent_asked(self):
        response = self.register(grade=10, track='ent')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(User.objects.get(username='track-pupil').track, 'school')

    def test_grade_9_gets_school_without_asking(self):
        response = self.register(grade=9)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(User.objects.get(username='track-pupil').track, 'school')

    def test_unknown_track_is_refused(self):
        response = self.register(grade=11, track='magistratura')
        self.assertEqual(response.status_code, 400)
        self.assertIn('track', response.data)


class ProfileTrackTest(TestCase):
    def setUp(self):
        self.pupil = User.objects.create_user(
            username='profile-pupil', password=STRONG_PASSWORD, role='student',
            grade=11, track=None, full_name='Ахметов Арман')
        self.api = APIClient()
        self.api.force_authenticate(self.pupil)

    def patch(self, **data):
        return self.api.patch('/api/auth/profile/', data, format='json')

    def test_grade_11_without_track_leaves_profile_incomplete(self):
        response = self.patch(full_name='Ахметов Арман')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(self.pupil.track)
        self.assertFalse(self.pupil.is_profile_completed)
        self.assertFalse(response.data['profile_completed'])

    def test_grade_11_accepts_nuet_and_completes_profile(self):
        response = self.patch(track='nuet')
        self.assertEqual(response.status_code, 200, response.data)
        self.pupil.refresh_from_db()
        self.assertEqual(self.pupil.track, 'nuet')
        self.assertTrue(self.pupil.is_profile_completed)
        self.assertEqual(response.data['track'], 'nuet')

    def test_school_track_for_grade_11_is_refused(self):
        response = self.patch(track='school')
        self.assertEqual(response.status_code, 400)
        self.pupil.refresh_from_db()
        self.assertIsNone(self.pupil.track)

    def test_student_cannot_change_chosen_track_or_grade(self):
        """Трек выбирается один раз; класс и смену трека задаёт учитель."""
        self.pupil.track = 'ent'
        self.pupil.save(update_fields=['track'])
        self.assertEqual(self.patch(track='nuet').status_code, 403)
        self.assertEqual(self.patch(grade=9).status_code, 403)
        self.pupil.refresh_from_db()
        self.assertEqual(self.pupil.track, 'ent')
        self.assertEqual(self.pupil.grade, 11)

    def test_teacher_never_gets_a_track(self):
        teacher = User.objects.create_user(
            username='profile-teacher', password=STRONG_PASSWORD, role='teacher')
        api = APIClient()
        api.force_authenticate(teacher)
        response = api.patch('/api/auth/profile/', {'track': 'ent'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        teacher.refresh_from_db()
        self.assertIsNone(teacher.track)


class ProfileSubjectsTrackTest(TestCase):
    """Профильные предметы чужого трека не попадают в профиль ни одной дорогой."""

    def setUp(self):
        self.pupil = User.objects.create_user(
            username='subj-pupil', password=STRONG_PASSWORD, role='student',
            grade=8, track='school', full_name='Ахметов Арман')
        self.ent = Subject.objects.create(name='Физика', slug='track-phys', track='ent')
        self.shared = Subject.objects.create(name='Логика', slug='track-logic', track='')
        self.api = APIClient()
        self.api.force_authenticate(self.pupil)

    def test_serializer_hides_foreign_track_subject(self):
        self.pupil.profile_subjects.set([self.ent, self.shared])
        response = self.api.get('/api/auth/profile/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['profile_subjects'], [self.shared.id])

    def test_update_drops_foreign_track_subject(self):
        response = self.api.put('/api/auth/profile/subjects/', {
            'profile_subjects': [self.ent.id, self.shared.id],
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['profile_subjects'], [self.shared.id])
        self.assertEqual(list(self.pupil.profile_subjects.values_list('id', flat=True)),
                         [self.shared.id])


class ExtraTracksTest(TestCase):
    """Учитель меняет трек и выдает дополнительные; ученик сам это не может."""

    def setUp(self):
        self.student = User.objects.create_user(
            username='extra-pupil', password=STRONG_PASSWORD, role='student',
            grade=11, track='nuet', full_name='Ахметов Арман')
        self.teacher = User.objects.create_user(
            username='extra-teacher', password=STRONG_PASSWORD, role='teacher')
        self.nuet = Subject.objects.create(
            name='NUET', slug='extra-nuet', track='nuet', is_visible=True)
        self.ent = Subject.objects.create(
            name='ЕНТ', slug='extra-ent', track='ent', is_visible=True)
        self.api = APIClient()

    def test_teacher_sets_primary_and_extra_tracks(self):
        self.api.force_authenticate(self.teacher)
        response = self.api.put(
            f'/api/auth/students/{self.student.id}/tracks/',
            {'track': 'nuet', 'extra_tracks': ['ent']}, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.student.refresh_from_db()
        self.assertEqual(self.student.track, 'nuet')
        self.assertEqual(self.student.extra_tracks, ['ent'])

    def test_student_cannot_grant_himself_a_track(self):
        self.api.force_authenticate(self.student)
        response = self.api.put(
            f'/api/auth/students/{self.student.id}/tracks/',
            {'track': 'nuet', 'extra_tracks': ['ent']}, format='json')

        self.assertEqual(response.status_code, 403)
        self.student.refresh_from_db()
        self.assertEqual(self.student.extra_tracks, [])

    def test_invalid_extra_track_is_rejected(self):
        self.api.force_authenticate(self.teacher)
        response = self.api.put(
            f'/api/auth/students/{self.student.id}/tracks/',
            {'extra_tracks': ['magistratura']}, format='json')

        self.assertEqual(response.status_code, 400)

    def test_extra_track_opens_subject_catalog(self):
        self.api.force_authenticate(self.teacher)
        self.api.put(
            f'/api/auth/students/{self.student.id}/tracks/',
            {'extra_tracks': ['ent']}, format='json')

        self.student.refresh_from_db()
        self.api.force_authenticate(self.student)
        response = self.api.get('/api/subjects/')

        self.assertEqual(response.status_code, 200)
        slugs = {s['slug'] for s in response.data}
        self.assertIn(self.nuet.slug, slugs)
        self.assertIn(self.ent.slug, slugs)
