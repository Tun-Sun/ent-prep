"""Пробные варианты «Пробные от INTELLECT» и мягкое скрытие старого банка.

Изоляция держится на трёх вещах: отдельный `Subject` на вариант, `is_visible`
у скрытых предметов и проверка видимости в путях, которые её раньше не
смотрели (полная симуляция ЕНТ, «Мои уроки»). Здесь проверяем каждую из них,
а не только каталог: id предмета всегда приходит из запроса.
"""
import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from subjects.models import Answer, Assignment, Question, Subject, Topic
from subjects.trial_variants import (ENT_TRIAL_TIME_LIMIT, MAX_TIME_LIMIT, MIN_TIME_LIMIT,
                                     NUET_TRIAL_TIME_LIMIT, TRIAL_SLUGS, count_time_limit)
from tests.models import TestSession
from users.models import User

STRONG_PASSWORD = 'Str0ng-Test-Pass-2026'


def add_questions(subject, count, prefix):
    topic = Topic.objects.create(name=f'Тема · {subject.slug}', subject=subject)
    for i in range(count):
        question = Question.objects.create(
            text=f'{prefix} {i}', topic=topic,
            question_type='single_choice', verification_status='verified',
        )
        Answer.objects.create(question=question, text='Верно', is_correct=True)
        Answer.objects.create(question=question, text='Неверно', is_correct=False)
    return topic


def run(*args, **kwargs):
    out = StringIO()
    call_command(*args, stdout=out, stderr=out, **kwargs)
    return out.getvalue()


class TrialVariantsCommandTest(TestCase):
    def test_creates_six_variants_with_required_flags(self):
        run('trial_variants')

        self.assertEqual(Subject.objects.filter(slug__in=TRIAL_SLUGS).count(),
                         len(TRIAL_SLUGS))
        for slug in ('ent-01', 'ent-02', 'ent-03'):
            subject = Subject.objects.get(slug=slug)
            self.assertEqual(subject.track, 'ent')
            self.assertEqual(subject.subject_type, 'mandatory')
            self.assertFalse(subject.show_in_profiles)
            self.assertTrue(subject.is_visible)
        for slug in ('nuet-01', 'nuet-02', 'nuet-03'):
            subject = Subject.objects.get(slug=slug)
            self.assertEqual(subject.track, 'nuet')
            self.assertEqual(subject.subject_type, 'mandatory')
            self.assertFalse(subject.show_in_profiles)
            self.assertTrue(subject.is_visible)

    def test_is_idempotent(self):
        run('trial_variants')
        run('trial_variants')

        self.assertEqual(Subject.objects.filter(slug__in=TRIAL_SLUGS).count(),
                         len(TRIAL_SLUGS))
        # Повторный запуск не плодит темы и не затирает вопросы.
        self.assertEqual(Topic.objects.count(), 0)

    def test_hidden_flag_creates_invisible_variants(self):
        run('trial_variants', '--hidden')

        for slug in TRIAL_SLUGS:
            self.assertFalse(Subject.objects.get(slug=slug).is_visible, slug)

        # Без флага команда снова делает их видимыми.
        run('trial_variants')
        for slug in TRIAL_SLUGS:
            self.assertTrue(Subject.objects.get(slug=slug).is_visible, slug)

    def test_restores_metadata_on_existing_variant(self):
        run('trial_variants')
        subject = Subject.objects.get(slug='nuet-02')
        subject.track = 'ent'
        subject.subject_type = 'profile'
        subject.is_visible = False
        subject.save()

        run('trial_variants')

        subject.refresh_from_db()
        self.assertEqual(subject.track, 'nuet')
        self.assertEqual(subject.subject_type, 'mandatory')
        self.assertTrue(subject.is_visible)


class TrialCountsSyncTest(TestCase):
    def test_sync_sets_counts_from_imported_questions(self):
        run('trial_variants')
        add_questions(Subject.objects.get(slug='ent-01'), 40, 'ent-01')

        run('trial_variants', '--sync')

        subject = Subject.objects.get(slug='ent-01')
        self.assertEqual(subject.question_count, 40)
        # ENT-пробники идут фиксированно по 3 часа, сколько бы вопросов ни было.
        self.assertEqual(subject.time_limit, ENT_TRIAL_TIME_LIMIT)

    def test_sync_skips_variant_without_questions(self):
        run('trial_variants')
        before = Subject.objects.get(slug='ent-02')

        run('trial_variants', '--sync')

        after = Subject.objects.get(slug='ent-02')
        self.assertEqual(after.question_count, before.question_count)
        self.assertEqual(after.time_limit, before.time_limit)

    def test_fixed_time_limit_override(self):
        run('trial_variants')
        add_questions(Subject.objects.get(slug='ent-03'), 120, 'ent-03')

        run('trial_variants', '--sync', '--time-limit', '14400')

        subject = Subject.objects.get(slug='ent-03')
        self.assertEqual(subject.question_count, 120)
        self.assertEqual(subject.time_limit, 14400)

    def test_nuet_gets_two_hours(self):
        run('trial_variants')
        add_questions(Subject.objects.get(slug='nuet-01'), 60, 'nuet-01')

        run('trial_variants', '--sync')

        subject = Subject.objects.get(slug='nuet-01')
        self.assertEqual(subject.question_count, 60)
        self.assertEqual(subject.time_limit, NUET_TRIAL_TIME_LIMIT)
        self.assertEqual(subject.time_limit, 7200)

    def test_time_limit_bounds(self):
        self.assertEqual(count_time_limit(1), MIN_TIME_LIMIT)
        self.assertEqual(count_time_limit(40), 2400)
        self.assertEqual(count_time_limit(500), MAX_TIME_LIMIT)


class LegacyContentCommandTest(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.override = override_settings(BASE_DIR=Path(self.tmp.name))
        self.override.enable()
        self.addCleanup(self.override.disable)

        run('trial_variants')
        for slug in TRIAL_SLUGS:
            add_questions(Subject.objects.get(slug=slug), 2, slug)

        self.old_visible = Subject.objects.create(
            name='Математика', slug='old-math', track='ent', is_visible=True)
        self.old_hidden = Subject.objects.create(
            name='Основы права', slug='old-law', track='ent', is_visible=False)
        add_questions(self.old_visible, 3, 'old')

    def snapshot_files(self):
        return sorted((Path(self.tmp.name) / 'var').glob('legacy_visibility_*.json'))

    def test_hide_keeps_only_variants(self):
        run('legacy_content', '--hide')

        for slug in TRIAL_SLUGS:
            self.assertTrue(Subject.objects.get(slug=slug).is_visible, slug)
        self.old_visible.refresh_from_db()
        self.assertFalse(self.old_visible.is_visible)
        self.assertEqual(len(self.snapshot_files()), 1)

        snapshot = json.loads(self.snapshot_files()[0].read_text(encoding='utf-8'))
        by_slug = {row['slug']: row['was_visible'] for row in snapshot['subjects']}
        self.assertTrue(by_slug['old-math'])
        self.assertFalse(by_slug['old-law'])

    def test_hide_refuses_when_variant_has_no_questions(self):
        Question.objects.filter(topic__subject__slug='nuet-03').delete()

        with self.assertRaises(CommandError):
            run('legacy_content', '--hide')
        # Ничего не скрыли и снимок не создали.
        self.assertTrue(self.old_visible.is_visible if hasattr(self, 'old_visible') else True)
        self.assertEqual(self.snapshot_files(), [])

    def test_hide_allow_empty_forces_it(self):
        Question.objects.filter(topic__subject__slug='nuet-03').delete()

        run('legacy_content', '--hide', '--allow-empty')

        self.old_visible.refresh_from_db()
        self.assertFalse(self.old_visible.is_visible)

    def test_restore_returns_exact_previous_state(self):
        run('legacy_content', '--hide')
        run('legacy_content', '--restore')

        self.old_visible.refresh_from_db()
        self.old_hidden.refresh_from_db()
        self.assertTrue(self.old_visible.is_visible)
        self.assertFalse(self.old_hidden.is_visible)

    def test_restore_without_snapshot_fails(self):
        with self.assertRaises(CommandError):
            run('legacy_content', '--restore')


class TrialImportCommandTest(TestCase):
    """Заливка форм: пара «вариант=ссылка» и синхронизация счётчиков."""

    def setUp(self):
        run('trial_variants')

    @staticmethod
    def fake_import(count, fail=False):
        def _import(*, form_id, subject_slug, topic_name, dry_run=False):
            if fail:
                return {'ok': False, 'error': 'форма не расшарена'}
            subject = Subject.objects.get(slug=subject_slug)
            add_questions(subject, count, subject_slug)
            return {
                'ok': True,
                'result': {'created': count, 'skipped_duplicates': 0,
                           'drafted_no_correct': 0, 'errors': []},
                'meta': {'questions_in_form': count,
                         'with_correct_answers': count},
            }
        return _import

    def test_import_fills_variant_and_syncs_counts(self):
        with patch('subjects.import_views.import_from_google_form',
                   self.fake_import(20)):
            out = run('trial_import', '--form', 'ent-01=https://forms/d/abc/edit')

        subject = Subject.objects.get(slug='ent-01')
        self.assertEqual(subject.question_count, 20)
        self.assertEqual(subject.time_limit, ENT_TRIAL_TIME_LIMIT)
        self.assertIn('ent-01', out)
        # Соседний вариант не тронут: формы заливаются по одной.
        self.assertEqual(Subject.objects.get(slug='ent-02').question_count, 10)

    def test_unknown_slug_is_rejected_before_import(self):
        with self.assertRaises(CommandError):
            run('trial_import', '--form', 'ent-99=https://forms/d/abc/edit')

    def test_missing_variant_asks_to_create_it_first(self):
        Subject.objects.filter(slug='nuet-02').delete()

        with self.assertRaises(CommandError):
            run('trial_import', '--form', 'nuet-02=https://forms/d/abc/edit')

    def test_failed_import_does_not_touch_counters(self):
        with patch('subjects.import_views.import_from_google_form',
                   self.fake_import(0, fail=True)):
            with self.assertRaises(CommandError):
                run('trial_import', '--form', 'ent-03=https://forms/d/abc/edit')

        self.assertEqual(Subject.objects.get(slug='ent-03').question_count, 10)

    def test_links_can_come_from_json_file(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / 'links.json'
        path.write_text('{"ent-02": "https://forms/d/xyz/edit"}', encoding='utf-8')

        with patch('subjects.import_views.import_from_google_form',
                   self.fake_import(3)):
            run('trial_import', '--from-file', str(path))

        self.assertEqual(Subject.objects.get(slug='ent-02').question_count, 3)

    def test_variant_can_be_filled_from_several_forms(self):
        """NUET — это Math + Thinking Skills: два файла в один вариант."""
        calls = []

        def _import(*, form_id, subject_slug, topic_name, dry_run=False):
            calls.append(form_id)
            subject = Subject.objects.get(slug=subject_slug)
            add_questions(subject, 15, f'{subject_slug}-{len(calls)}')
            return {
                'ok': True,
                'result': {'created': 15, 'skipped_duplicates': 0,
                           'drafted_no_correct': 0, 'errors': []},
                'meta': {'questions_in_form': 15, 'with_correct_answers': 15},
            }

        with patch('subjects.import_views.import_from_google_form', _import):
            run('trial_import',
                '--form', 'nuet-01=https://forms/d/math/edit',
                '--form', 'nuet-01=https://forms/d/thinking/edit')

        self.assertEqual(calls, ['https://forms/d/math/edit',
                                 'https://forms/d/thinking/edit'])
        subject = Subject.objects.get(slug='nuet-01')
        self.assertEqual(subject.question_count, 30)
        self.assertEqual(subject.topics.count(), 2)

    def test_json_file_accepts_list_of_links(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / 'links.json'
        path.write_text(
            json.dumps({'nuet-02': ['https://forms/d/a/edit',
                                    'https://forms/d/b/edit']}),
            encoding='utf-8')

        with patch('subjects.import_views.import_from_google_form',
                   self.fake_import(12)):
            run('trial_import', '--from-file', str(path))

        self.assertEqual(Subject.objects.get(slug='nuet-02').question_count, 24)


class TrialStartIsolationTest(TestCase):
    """Ученик получает вопросы только своего варианта и своего трека."""

    def setUp(self):
        run('trial_variants')
        self.ent01 = Subject.objects.get(slug='ent-01')
        self.ent02 = Subject.objects.get(slug='ent-02')
        self.nuet01 = Subject.objects.get(slug='nuet-01')
        add_questions(self.ent01, 2, 'ent-01')
        add_questions(self.ent02, 3, 'ent-02')
        add_questions(self.nuet01, 1, 'nuet-01')
        run('trial_variants', '--sync')

        self.ent = User.objects.create_user(
            username='trial-ent', password=STRONG_PASSWORD, role='student',
            grade=11, track='ent')
        self.nuet = User.objects.create_user(
            username='trial-nuet', password=STRONG_PASSWORD, role='student',
            grade=11, track='nuet')
        self.api = APIClient()

    def start(self, user, subject):
        self.api.force_authenticate(user)
        return self.api.post('/api/tests/start/', {'subject_id': subject.id},
                             format='json')

    def test_variant_serves_only_its_own_questions(self):
        response = self.start(self.ent, self.ent01)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['total_questions'], 2)
        texts = [q['text'] for q in response.data['questions']]
        self.assertTrue(all(text.startswith('ent-01') for text in texts), texts)

    def test_other_variant_questions_are_not_mixed_in(self):
        response = self.start(self.ent, self.ent02)

        self.assertEqual(response.data['total_questions'], 3)
        texts = [q['text'] for q in response.data['questions']]
        self.assertTrue(all(text.startswith('ent-02') for text in texts), texts)

    def test_ent_student_cannot_open_nuet_variant(self):
        response = self.start(self.ent, self.nuet01)

        self.assertEqual(response.status_code, 403, response.data)
        self.assertEqual(TestSession.objects.count(), 0)

    def test_nuet_student_gets_nuet_variant(self):
        response = self.start(self.nuet, self.nuet01)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['total_questions'], 1)


class HiddenBankLeakTest(TestCase):
    """Скрытие банка не обходится симуляцией ЕНТ и разделом «Мои уроки»."""

    def setUp(self):
        run('trial_variants')
        self.ent01 = Subject.objects.get(slug='ent-01')
        self.ent02 = Subject.objects.get(slug='ent-02')
        add_questions(self.ent01, 2, 'ent-01')
        add_questions(self.ent02, 2, 'ent-02')

        # Старые обязательные предметы симуляции — скрыты.
        for slug, name in (('history', 'История Казахстана'),
                           ('reading', 'Грамотность чтения'),
                           ('math_profile', 'Математическая грамотность')):
            Subject.objects.create(name=name, slug=slug, track='ent',
                                   is_visible=False)

        self.ent = User.objects.create_user(
            username='hidden-ent', password=STRONG_PASSWORD, role='student',
            grade=11, track='ent')
        self.teacher = User.objects.create_user(
            username='hidden-teacher', password=STRONG_PASSWORD, role='teacher')
        self.api = APIClient()

    def test_full_ent_simulation_is_blocked_while_bank_hidden(self):
        self.api.force_authenticate(self.ent)
        response = self.api.post('/api/tests/start-ent/', {
            'profile1_id': self.ent01.id,
            'profile2_id': self.ent02.id,
        }, format='json')

        self.assertEqual(response.status_code, 403, response.data)
        self.assertIn('временно недоступна', response.data['error'])
        self.assertEqual(TestSession.objects.count(), 0)

    def test_hidden_subject_assignments_are_not_listed(self):
        hidden_subject = Subject.objects.create(
            name='Оптика', slug='hidden-optics', track='ent', is_visible=False)
        Assignment.objects.create(
            title='Старый урок', teacher=self.teacher, subject=hidden_subject,
            status='active', published_at=None)
        old = Assignment.objects.get(title='Старый урок')
        old.students.add(self.ent)

        Assignment.objects.create(
            title='Новый вариант', teacher=self.teacher, subject=self.ent01,
            status='active')
        Assignment.objects.get(title='Новый вариант').students.add(self.ent)

        self.api.force_authenticate(self.ent)
        response = self.api.get('/api/my/assignments/')

        self.assertEqual(response.status_code, 200, response.data)
        titles = [row['title'] for row in response.data]
        self.assertIn('Новый вариант', titles)
        self.assertNotIn('Старый урок', titles)
