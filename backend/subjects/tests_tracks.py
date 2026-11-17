"""Треки в каталоге предметов и в назначении уроков.

Каталог — первая граница контента: школьник не должен видеть ЕНТ-предмет даже
если знает его id. Вторая граница — урок: тренер не может назначить ЕНТ-урок
школьнику, иначе ученик получит задания из программы, которой у него нет.
Общий предмет (`track=''`) проходит везде, а ученик без трека не блокируется:
это старое поведение и 11-классник до заполнения карточки.
"""
from django.test import TestCase
from rest_framework.test import APIClient

from subjects.models import Question, Subject, Topic
from users.models import User

STRONG_PASSWORD = 'Str0ng-Test-Pass-2026'


def make_task(subject, text='Задача'):
    """Принятая задача для конструктора урока: без неё блок не собрать."""
    topic = Topic.objects.create(name=f'Тема · {subject.slug}', subject=subject)
    return Question.objects.create(
        topic=topic, text=text, question_type='open_answer',
        verification_status='verified',
    )


class CatalogTrackTest(TestCase):
    """`/api/subjects/` и `/api/subjects/minimal/` режут каталог по треку."""

    def setUp(self):
        self.school_subject = Subject.objects.create(
            name='Алгебра 8', slug='track-school', track='school', is_visible=True)
        self.ent_subject = Subject.objects.create(
            name='Физика ЕНТ', slug='track-ent', track='ent', is_visible=True)
        self.nuet_subject = Subject.objects.create(
            name='NUET Математика', slug='track-nuet', track='nuet', is_visible=True)
        self.shared_subject = Subject.objects.create(
            name='Логика', slug='track-shared', track='', is_visible=True)

        self.school = User.objects.create_user(
            username='cat-school', password=STRONG_PASSWORD, role='student',
            grade=8, track='school')
        self.ent = User.objects.create_user(
            username='cat-ent', password=STRONG_PASSWORD, role='student',
            grade=11, track='ent')
        self.nuet = User.objects.create_user(
            username='cat-nuet', password=STRONG_PASSWORD, role='student',
            grade=11, track='nuet')
        self.legacy = User.objects.create_user(
            username='cat-legacy', password=STRONG_PASSWORD, role='student', grade=10)
        self.teacher = User.objects.create_user(
            username='cat-teacher', password=STRONG_PASSWORD, role='teacher')
        self.api = APIClient()

    def slugs(self, response):
        self.assertEqual(response.status_code, 200, response.data)
        return {s['slug'] for s in response.data}

    def test_school_student_sees_school_and_shared(self):
        self.api.force_authenticate(self.school)
        self.assertEqual(self.slugs(self.api.get('/api/subjects/')),
                         {'track-school', 'track-shared'})

    def test_ent_student_sees_ent_and_shared(self):
        self.api.force_authenticate(self.ent)
        self.assertEqual(self.slugs(self.api.get('/api/subjects/')),
                         {'track-ent', 'track-shared'})

    def test_nuet_student_sees_nuet_and_shared(self):
        self.api.force_authenticate(self.nuet)
        self.assertEqual(self.slugs(self.api.get('/api/subjects/')),
                         {'track-nuet', 'track-shared'})

    def test_student_without_track_sees_the_whole_catalog(self):
        """Старый ученик без трека не должен потерять каталог из-за миграции."""
        self.api.force_authenticate(self.legacy)
        self.assertEqual(self.slugs(self.api.get('/api/subjects/')),
                         {'track-school', 'track-ent', 'track-nuet', 'track-shared'})

    def test_teacher_sees_every_track(self):
        self.api.force_authenticate(self.teacher)
        self.assertEqual(self.slugs(self.api.get('/api/subjects/')),
                         {'track-school', 'track-ent', 'track-nuet', 'track-shared'})

    def test_student_cannot_open_foreign_subject_by_id(self):
        self.api.force_authenticate(self.school)
        response = self.api.get(f'/api/subjects/{self.ent_subject.id}/')
        self.assertEqual(response.status_code, 404)

    def test_minimal_list_follows_the_track(self):
        self.api.force_authenticate(self.school)
        self.assertEqual(self.slugs(self.api.get('/api/subjects/minimal/')),
                         {'track-school', 'track-shared'})

    def test_registration_list_filters_by_track(self):
        response = self.api.get('/api/subjects/for-registration/', {'track': 'ent'})
        self.assertEqual(self.slugs(response), {'track-ent', 'track-shared'})

    def test_registration_list_without_track_returns_everything(self):
        self.assertEqual(self.slugs(self.api.get('/api/subjects/for-registration/')),
                         {'track-school', 'track-ent', 'track-nuet', 'track-shared'})

    def test_registration_list_refuses_unknown_track(self):
        response = self.api.get('/api/subjects/for-registration/', {'track': 'magistratura'})
        self.assertEqual(response.status_code, 400)


class AssignmentTrackTest(TestCase):
    """Урок наследует трек предмета; чужой трек в аудитории — ошибка."""

    def setUp(self):
        self.ent_subject = Subject.objects.create(
            name='Физика ЕНТ', slug='assign-ent', track='ent', is_visible=True)
        self.shared_subject = Subject.objects.create(
            name='Логика', slug='assign-shared', track='', is_visible=True)
        self.ent_task = make_task(self.ent_subject, 'ЕНТ-задача')
        self.shared_task = make_task(self.shared_subject, 'Общая задача')

        self.teacher = User.objects.create_user(
            username='assign-teacher', password=STRONG_PASSWORD, role='teacher')
        self.school = User.objects.create_user(
            username='assign-school', password=STRONG_PASSWORD, role='student',
            grade=8, track='school', full_name='Школьник Восьмой')
        self.ent = User.objects.create_user(
            username='assign-ent', password=STRONG_PASSWORD, role='student',
            grade=11, track='ent', full_name='Выпускник ЕНТ')
        self.legacy = User.objects.create_user(
            username='assign-legacy', password=STRONG_PASSWORD, role='student',
            grade=10, full_name='Ученик Без Трека')
        self.api = APIClient()
        self.api.force_authenticate(self.teacher)

    def create(self, subject, task, students):
        return self.api.post('/api/assignments/', {
            'title': 'Урок', 'subject': subject.id,
            'students': [s.id for s in students],
            'blocks': [{'kind': 'homework', 'question_ids': [task.id]}],
        }, format='json')

    def test_ent_lesson_for_school_student_is_refused(self):
        response = self.create(self.ent_subject, self.ent_task, [self.school])
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('Трек ученика', str(response.data))

    def test_ent_lesson_for_ent_student_is_saved(self):
        response = self.create(self.ent_subject, self.ent_task, [self.ent])
        self.assertEqual(response.status_code, 201, response.data)

    def test_shared_lesson_reaches_every_track(self):
        response = self.create(self.shared_subject, self.shared_task, [self.school, self.ent])
        self.assertEqual(response.status_code, 201, response.data)

    def test_student_without_track_does_not_block_the_lesson(self):
        response = self.create(self.ent_subject, self.ent_task, [self.legacy])
        self.assertEqual(response.status_code, 201, response.data)

    def test_one_foreign_student_stops_the_whole_lesson(self):
        response = self.create(self.ent_subject, self.ent_task, [self.ent, self.school])
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(Subject.objects.filter(slug='assign-ent').count(), 1)

    def test_subject_change_rechecks_the_existing_audience(self):
        """Предмет урока тоже можно поменять — тогда сверяется уже сохранённый класс."""
        created = self.create(self.shared_subject, self.shared_task, [self.school])
        self.assertEqual(created.status_code, 201, created.data)
        response = self.api.patch(f"/api/assignments/{created.data['id']}/",
                                  {'subject': self.ent_subject.id}, format='json')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('Трек ученика', str(response.data))
