"""Мягкое скрытие предмета с платформы (`Subject.is_visible`).

Галочку снимает человек в админке. Тесты проверяют две вещи: что скрытый предмет
не протёк ни в один ученический интерфейс (каталог, регистрация, тренажёр,
симуляция ЕНТ, профиль, дашборды) и что тренер и админ его по-прежнему видят —
иначе экраном предметов нельзя было бы вернуть предмет обратно.
"""
from __future__ import annotations

import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from subjects.models import Answer, Question, Subject, Topic
from tests.models import TestSession

User = get_user_model()

STRONG_PASSWORD = 'Str0ng-Test-Pass-2026'


def make_choice_questions(topic, count, prefix):
    """Задачи, которые движок вообще может проверить: вариант + ключ."""
    for i in range(count):
        q = Question.objects.create(
            text=f'{prefix} {i}', topic=topic,
            question_type='single_choice', verification_status='verified',
        )
        Answer.objects.create(question=q, text='Верно', is_correct=True)
        Answer.objects.create(question=q, text='Неверно', is_correct=False)


class CatalogVisibilityTest(TestCase):
    """Каталог предметов: ученику — только видимые, тренеру — весь список."""

    def setUp(self):
        self.student = User.objects.create_user(
            username='cat-student', password=STRONG_PASSWORD, role='student')
        self.teacher = User.objects.create_user(
            username='cat-teacher', password=STRONG_PASSWORD, role='teacher')
        self.visible = Subject.objects.create(
            name='Физика', slug='cat-phys', is_visible=True)
        self.hidden = Subject.objects.create(
            name='Химия', slug='cat-chem', is_visible=False)
        self.api = APIClient()

    def slugs(self, response):
        return {s['slug'] for s in response.data}

    def test_student_catalog_excludes_hidden(self):
        self.api.force_authenticate(self.student)
        response = self.api.get('/api/subjects/')
        self.assertEqual(self.slugs(response), {'cat-phys'})

    def test_anonymous_registration_list_excludes_hidden(self):
        response = self.api.get('/api/subjects/for-registration/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.slugs(response), {'cat-phys'})

    def test_student_minimal_excludes_hidden(self):
        """Выпадающий список настроек и дуэлей строится на `/minimal`."""
        self.api.force_authenticate(self.student)
        response = self.api.get('/api/subjects/minimal/')
        self.assertEqual(self.slugs(response), {'cat-phys'})

    def test_student_cannot_open_hidden_by_id(self):
        self.api.force_authenticate(self.student)
        response = self.api.get(f'/api/subjects/{self.hidden.id}/')
        self.assertEqual(response.status_code, 404)

    def test_teacher_still_sees_hidden(self):
        """Без этого редактор предметов не смог бы вернуть снятую галочку."""
        self.api.force_authenticate(self.teacher)
        response = self.api.get('/api/subjects/')
        self.assertEqual(self.slugs(response), {'cat-phys', 'cat-chem'})


class HiddenSubjectTrainingTest(TestCase):
    """Скрытый предмет нельзя запустить ни как тренажёр, ни как секцию ЕНТ."""

    def setUp(self):
        self.student = User.objects.create_user(
            username='train-student', password=STRONG_PASSWORD, role='student')
        self.teacher = User.objects.create_user(
            username='train-teacher', password=STRONG_PASSWORD, role='teacher')
        self.hidden = Subject.objects.create(
            name='Химия', slug='train-chem', is_visible=False,
            question_count=5, time_limit=600)
        self.visible = Subject.objects.create(
            name='Физика', slug='train-phys', is_visible=True,
            question_count=5, time_limit=600)
        for subj in (self.hidden, self.visible):
            topic = Topic.objects.create(name='Тема', subject=subj)
            make_choice_questions(topic, 8, subj.name)
        self.api = APIClient()

    def test_student_start_hidden_subject_forbidden(self):
        self.api.force_authenticate(self.student)
        response = self.api.post('/api/tests/start/',
                                 {'subject_id': self.hidden.id}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_teacher_start_hidden_subject_allowed(self):
        self.api.force_authenticate(self.teacher)
        response = self.api.post('/api/tests/start/',
                                 {'subject_id': self.hidden.id}, format='json')
        self.assertEqual(response.status_code, 200)

    def test_student_start_ent_with_hidden_profile_subject(self):
        """Id профиля приходят в запросе, а не из меню — проверка обязана быть."""
        self.api.force_authenticate(self.student)
        response = self.api.post('/api/tests/start-ent/', {
            'profile1_id': self.visible.id, 'profile2_id': self.hidden.id,
        }, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(TestSession.objects.count(), 0)

    def test_ent_for_teacher_is_not_blocked_by_visibility(self):
        self.api.force_authenticate(self.teacher)
        response = self.api.post('/api/tests/start-ent/', {
            'profile1_id': self.visible.id, 'profile2_id': self.hidden.id,
        }, format='json')
        self.assertNotEqual(response.status_code, 403)


class ProfileSubjectsVisibilityTest(TestCase):
    """Скрытый предмет не ложится в профиль ученика ни одной из трёх дорог."""

    def setUp(self):
        self.student = User.objects.create_user(
            username='prof-student', password=STRONG_PASSWORD, role='student', grade=10)
        self.teacher = User.objects.create_user(
            username='prof-teacher', password=STRONG_PASSWORD, role='teacher')
        self.visible = Subject.objects.create(name='Физика', slug='prof-phys', is_visible=True)
        self.hidden = Subject.objects.create(name='Химия', slug='prof-chem', is_visible=False)
        self.api = APIClient()

    def test_registration_ignores_hidden_subject(self):
        response = self.api.post('/api/auth/register/', {
            'username': 'fresh-pupil', 'email': 'fresh@example.test',
            'password': STRONG_PASSWORD, 'full_name': 'Иванов Иван', 'grade': 10,
            'account_type': 'student',
            'profile_subjects': [self.hidden.id, self.visible.id],
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        created = User.objects.get(username='fresh-pupil')
        self.assertEqual(list(created.profile_subjects.values_list('slug', flat=True)),
                         ['prof-phys'])

    def test_student_profile_update_drops_hidden(self):
        self.api.force_authenticate(self.student)
        response = self.api.put('/api/auth/profile/subjects/', {
            'profile_subjects': [self.visible.id, self.hidden.id],
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['profile_subjects'], [self.visible.id])

    def test_teacher_cannot_attach_hidden_to_student(self):
        """Ответ возвращает только то, что действительно прикрепилось."""
        self.api.force_authenticate(self.teacher)
        response = self.api.put(f'/api/auth/students/{self.student.id}/subjects/', {
            'profile_subjects': [self.hidden.id],
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['profile_subjects'], [])
        self.assertEqual(self.student.profile_subjects.count(), 0)


class DashboardVisibilityTest(TestCase):
    """Скрытый предмет уходит и из дашборда ученика, и из таблицы лидеров."""

    def setUp(self):
        self.student = User.objects.create_user(
            username='dash-student', password=STRONG_PASSWORD, role='student')
        self.other = User.objects.create_user(
            username='dash-other', password=STRONG_PASSWORD, role='student')
        self.teacher = User.objects.create_user(
            username='dash-teacher', password=STRONG_PASSWORD, role='teacher')
        self.visible = Subject.objects.create(name='Физика', slug='dash-phys', is_visible=True)
        self.hidden = Subject.objects.create(name='Химия', slug='dash-chem', is_visible=False)
        for who in (self.student, self.other):
            for subj in (self.visible, self.hidden):
                TestSession.objects.create(
                    student=who, subject=subj, is_completed=True,
                    score_percent=80, total_questions=10, correct_answers=8)
        self.api = APIClient()

    def test_student_progress_excludes_hidden_subject(self):
        """Сессии в скрытом предмете были — но показывать их ученику уже не надо."""
        self.api.force_authenticate(self.student)
        response = self.api.get('/api/dashboard/student/')
        self.assertEqual(response.status_code, 200)
        names = {row['name'] for row in response.data['subject_progress']}
        self.assertEqual(names, {'Физика'})

    def test_leaderboard_by_hidden_subject_forbidden_for_student(self):
        self.api.force_authenticate(self.student)
        response = self.api.get(f'/api/dashboard/leaderboard/?subject_id={self.hidden.id}')
        self.assertEqual(response.status_code, 403)

    def test_leaderboard_by_hidden_subject_open_for_teacher(self):
        self.api.force_authenticate(self.teacher)
        response = self.api.get(f'/api/dashboard/leaderboard/?subject_id={self.hidden.id}')
        self.assertEqual(response.status_code, 200)

    def test_leaderboard_by_visible_subject_still_works(self):
        self.api.force_authenticate(self.student)
        response = self.api.get(f'/api/dashboard/leaderboard/?subject_id={self.visible.id}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)


class SubjectAdminBulkActionsTest(TestCase):
    """Админка: галочка видимости в списке и две массовые акции."""

    def setUp(self):
        self.owner = User.objects.create_superuser(
            username='owner-admin', email='owner@example.test', password=STRONG_PASSWORD)
        self.client.force_login(self.owner)
        self.visible = Subject.objects.create(name='Физика', slug='adm-phys', is_visible=True)
        self.hidden = Subject.objects.create(name='Химия', slug='adm-chem', is_visible=False)

    def run_action(self, action, ids):
        return self.client.post('/admin/subjects/subject/', {
            'action': action,
            '_selected_action': [str(i) for i in ids],
        })

    def test_changelist_has_visibility_checkbox_and_filter(self):
        response = self.client.get('/admin/subjects/subject/')
        self.assertEqual(response.status_code, 200)
        page = response.content.decode()
        # Галочка стоит прямо в строке списка. Админка на Grappelli, поэтому
        # list_editable рендерится formset-полем (`form-0-is_visible`), а не
        # стандартным для Django `is_visible__<pk>`.
        self.assertEqual(page.count('name="form-0-is_visible"'), 1)
        checkbox_count = len(re.findall(r'name="form-\d+-is_visible"', page))
        self.assertEqual(checkbox_count, 2)
        # фильтр «видимые / скрытые» в боковой панели
        self.assertIn('is_visible__exact=0', page)
        self.assertIn('is_visible__exact=1', page)
        # обе массовые акции в выпадающем списке
        self.assertIn('Скрыть выбранные предметы', page)
        self.assertIn('Показать / активировать выбранные предметы', page)

    def test_hide_action_hides_both_selected(self):
        response = self.run_action('hide_subjects', [self.visible.pk, self.hidden.pk])
        self.assertEqual(response.status_code, 302)
        self.visible.refresh_from_db()
        self.hidden.refresh_from_db()
        self.assertFalse(self.visible.is_visible)
        self.assertFalse(self.hidden.is_visible)

    def test_show_action_returns_subjects(self):
        self.run_action('show_subjects', [self.hidden.pk])
        self.hidden.refresh_from_db()
        self.assertTrue(self.hidden.is_visible)

    def test_hide_does_not_delete_topics_or_questions(self):
        """Удаление предмета снесло бы банк по CASCADE — акция обязана быть мягкой."""
        topic = Topic.objects.create(name='Механика', subject=self.visible)
        make_choice_questions(topic, 3, 'задача')
        self.run_action('hide_subjects', [self.visible.pk])
        self.assertTrue(Subject.objects.filter(pk=self.visible.pk).exists())
        self.assertEqual(Topic.objects.filter(pk=topic.pk).count(), 1)
        self.assertEqual(Question.objects.filter(topic=topic).count(), 3)
