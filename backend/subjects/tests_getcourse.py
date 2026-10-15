"""Мост GetCourse ⇄ платформа (Шаг 6): вход по подписанной ссылке и отчёт о домашке.

Что здесь проверяется глазами будущего читателя:

1. Подпись покрывает **каждое** поле перехода — подменённая почта, чужой урок или
   просроченное время обязаны давать `403` и ни одной новой строки в базе.
2. Войти по ссылке может только ученик: почта, под которой в платформе живёт
   преподаватель, — отказ, а не «автоматически подняли роль».
3. В GetCourse уезжают только числа, и ровно один раз на (урок, ученик, блок):
   повторный клик «Сдать» не должен присылать методисту второй тот же процент,
   а ключей GetCourse нет — значит отправки нет, но журнал есть.
"""
from __future__ import annotations

import json
import time
from unittest import mock
from urllib.parse import parse_qs

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from subjects import getcourse, sso
from subjects.models import (Assignment, AssignmentAnswer, AssignmentBlock,
                             AssignmentSubmission, LessonReport, Question, Subject, Topic)
from users.models import User

SECRET = 'тест-секрет-подписи-6'


def make_client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@override_settings(GC_SSO_SECRET=SECRET, GC_SSO_MAX_AGE=300)
class SsoJoinTest(TestCase):
    """Вход из урока: подпись, срок, поиск ученика и редирект внутрь задания."""

    @classmethod
    def setUpTestData(cls):
        cls.math = Subject.objects.create(name='Математика', slug='math-sso', icon='📐')
        cls.topic = Topic.objects.create(subject=cls.math, name='Сканави · Глава 1')
        cls.teacher = User.objects.create_user(username='sso_teacher', password='x',
                                               role='teacher', email='pro@intellect.kz')
        cls.lesson = Assignment.objects.create(
            teacher=cls.teacher, subject=cls.math, title='Урок из GetCourse',
            status='active', published_at=timezone.now())
        task = Question.objects.create(topic=cls.topic, text='объём', latex='объём',
                                       latex_answer='$18$ см', difficulty='easy',
                                       source_type='book_scan', question_type='open_answer',
                                       verification_status='verified', points=1)
        cls.task = task
        cls.homework = AssignmentBlock.objects.create(assignment=cls.lesson, kind='homework',
                                                      order=0, question_ids=[task.pk])
        cls.base = {'gc_uid': '48123', 'email': 'Aidar@Mail.KZ', 'first_name': 'Айдар',
                    'last_name': 'Сатов', 'assignment_id': str(cls.lesson.pk)}

    def _join(self, **overrides):
        values = dict(self.base)
        values.update(overrides)
        values.setdefault('ts', str(int(time.time())))
        values['sign'] = sso.make_sign(SECRET, values)
        return self.client.get('/api/lesson/join/', values)

    def _students(self):
        return User.objects.filter(role='student')

    def test_signed_link_lands_the_student_inside_the_lesson(self):
        before = self._students().count()
        r = self._join()
        self.assertEqual(r.status_code, 302, r.content)
        self.assertTrue(r['Location'].startswith('/sso#'), r['Location'])
        frag = parse_qs(r['Location'].split('#', 1)[1])
        self.assertEqual(frag['next'], ['/assignments?open=%s' % self.lesson.pk])
        self.assertTrue(frag.get('access'))
        self.assertEqual(self._students().count(), before + 1)
        student = self._students().order_by('-id').first()
        self.assertEqual(student.gc_uid, '48123')
        self.assertEqual(student.email, 'aidar@mail.kz')
        self.assertEqual(student.full_name, 'Айдар Сатов')
        self.assertFalse(student.has_usable_password())
        self.assertTrue(self.lesson.students.filter(pk=student.pk).exists())

    def test_the_token_from_the_link_is_a_real_session(self):
        r = self._join()
        access = parse_qs(r['Location'].split('#', 1)[1])['access'][0]
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION='Bearer ' + access)
        mine = c.get('/api/my/assignments/')
        self.assertEqual(mine.status_code, 200, mine.data)
        self.assertEqual([a['id'] for a in mine.data], [self.lesson.pk])

    def test_tampered_email_breaks_the_signature(self):
        """Подпись считает по всем полям: подменить почту в готовой ссылке нельзя."""
        before = self._students().count()
        values = dict(self.base, ts=str(int(time.time())))
        values['email'] = 'victims@other.kz'
        values['sign'] = sso.make_sign(SECRET, self.base)  # подпись от прежней почты
        r = self.client.get('/api/lesson/join/', values)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self._students().count(), before)
        self.assertEqual(LessonReport.objects.count(), 0)

    def test_another_lesson_in_the_same_link_is_refused(self):
        before = self._students().count()
        other = Assignment.objects.create(teacher=self.teacher, subject=self.math,
                                          title='Чужой урок', status='active',
                                          published_at=timezone.now())
        values = dict(self.base, assignment_id=str(other.pk), ts=str(int(time.time())))
        values['sign'] = sso.make_sign(SECRET, self.base)
        r = self.client.get('/api/lesson/join/', values)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self._students().count(), before)
        self.assertEqual(other.students.count(), 0)

    def test_missing_or_forged_signature_is_refused(self):
        for sign in ('', 'deadbeef', sso.make_sign('другой-секрет', dict(self.base, ts='1'))):
            r = self.client.get('/api/lesson/join/', dict(self.base, ts=str(int(time.time())),
                                                           sign=sign))
            self.assertEqual(r.status_code, 403, sign)
        self.assertEqual(self._students().count(), 0)

    def test_expired_link_is_refused(self):
        stale = str(int(time.time()) - 301)
        r = self._join(ts=stale)
        self.assertEqual(r.status_code, 403)
        self.assertIn('просрочена', r.data['detail'])
        self.assertEqual(self._students().count(), 0)

    def test_link_from_the_future_is_refused(self):
        # заготовка «оживёт через час» — это не переход из текущего урока
        r = self._join(ts=str(int(time.time()) + 3600))
        self.assertEqual(r.status_code, 403)

    def test_unconfigured_secret_refuses_everything(self):
        with override_settings(GC_SSO_SECRET=''):
            r = self.client.get('/api/lesson/join/', dict(
                self.base, ts=str(int(time.time())),
                sign=sso.make_sign('что-то', self.base)))
            self.assertEqual(r.status_code, 403)
            self.assertIn('не настроен', r.data['detail'])
        self.assertEqual(self._students().count(), 0)

    def test_revoked_lesson_is_refused(self):
        self.lesson.status = 'revoked'
        self.lesson.save(update_fields=['status'])
        r = self._join()
        self.assertEqual(r.status_code, 403)
        self.assertIn('отозван', r.data['detail'])

    def test_draft_lesson_is_refused(self):
        self.lesson.status = 'draft'
        self.lesson.save(update_fields=['status'])
        self.assertEqual(self._join().status_code, 403)

    def test_existing_student_is_found_by_code_and_not_duplicated(self):
        aidar = User.objects.create_user(username='aidar', password='x', role='student',
                                         gc_uid='48123')
        r = self._join()
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self._students().count(), 1)
        self.assertTrue(self.lesson.students.filter(pk=aidar.pk).exists())

    def test_email_reuses_the_platform_account_and_binds_the_code(self):
        aidar = User.objects.create_user(username='aidar', password='x', role='student',
                                         email='aidar@mail.kz')
        r = self._join()
        self.assertEqual(r.status_code, 302)
        aidar.refresh_from_db()
        self.assertEqual(aidar.gc_uid, '48123')
        self.assertEqual(self._students().count(), 1)

    def test_a_teachers_email_is_never_handed_out_as_a_student(self):
        """Совпадение почты с преподавателем — отказ: подписанная ссылка не имеет
        права превращать чужой аккаунт в ученика или отдавать его сессию."""
        r = self._join(email='pro@intellect.kz')
        self.assertEqual(r.status_code, 403)
        self.assertIn('не активному ученику', r.data['detail'])
        self.assertEqual(self.lesson.students.count(), 0)

    def test_two_codes_on_one_email_are_refused(self):
        User.objects.create_user(username='aidar', password='x', role='student',
                                 email='aidar@mail.kz', gc_uid='777')
        r = self._join()
        self.assertEqual(r.status_code, 403)
        self.assertIn('другой код', r.data['detail'])

    def test_second_click_of_the_same_link_creates_nothing_new(self):
        first = self._join()
        second = self._join()
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(self._students().count(), 1)
        self.assertEqual(self.lesson.students.count(), 1)

    def test_username_collision_gets_a_suffix(self):
        User.objects.create_user(username='aidar', password='x', role='student',
                                 email='someone@else.kz')
        r = self._join()
        self.assertEqual(r.status_code, 302, getattr(r, 'data', None))
        self.assertTrue(self._students().filter(username='aidar1').exists())

    def test_code_without_email_still_creates_a_student(self):
        r = self._join(email='', first_name='', last_name='')
        self.assertEqual(r.status_code, 302)
        self.assertTrue(self._students().filter(gc_uid='48123', username='gc48123').exists())


@override_settings(GC_FRAME_ANCESTORS=['https://school.getcourse.ru'],
                   GC_FRAME_PATHS=('/sso', '/assignments'))
class SsoFrameTest(TestCase):
    """Урок GetCourse встраивает платформу в iframe: заголовки решают, кто может."""

    def test_lesson_pages_allow_the_getcourse_domain(self):
        for path in ('/sso', '/assignments/12'):
            r = self.client.get(path)
            self.assertNotIn('X-Frame-Options', r, path)
            self.assertIn("'self' https://school.getcourse.ru",
                          r.get('Content-Security-Policy', ''), path)

    def test_other_pages_stay_unframable(self):
        r = self.client.get('/teacher/assign')
        self.assertEqual(r['X-Frame-Options'], 'DENY')
        self.assertNotIn('Content-Security-Policy', r)

    def test_similar_path_prefix_is_not_enough(self):
        # `/assignments-extra` — не `/assignments/…`, фреймить его никто не просил
        r = self.client.get('/assignments-extra')
        self.assertEqual(r['X-Frame-Options'], 'DENY')

    def test_without_named_ancestors_nothing_is_framable(self):
        with override_settings(GC_FRAME_ANCESTORS=[]):
            r = self.client.get('/assignments/12')
        self.assertEqual(r['X-Frame-Options'], 'DENY')
        self.assertNotIn('Content-Security-Policy', r)


class SsoSignatureUnitTest(TestCase):
    """Чистые функции подписи: тот же код считает подпись для ссылки и проверяет её."""

    def test_case_and_spaces_of_the_email_do_not_change_the_signature(self):
        a = {'gc_uid': '1', 'email': 'A@Mail.KZ', 'first_name': '', 'last_name': '',
             'assignment_id': '2', 'ts': '3'}
        b = dict(a, email=' a@mail.kz ')
        self.assertEqual(sso.make_sign(SECRET, a), sso.make_sign(SECRET, b))

    def test_signature_is_not_valid_without_a_secret_or_a_value(self):
        values = {'gc_uid': '1', 'email': '', 'first_name': '', 'last_name': '',
                  'assignment_id': '2', 'ts': str(int(time.time()))}
        self.assertFalse(sso.sign_is_valid('', values, sso.make_sign(SECRET, values)))
        self.assertFalse(sso.sign_is_valid(SECRET, values, ''))

    def test_broken_timestamp_is_not_fresh(self):
        for ts in ('', 'не-число', None):
            self.assertFalse(sso.ts_is_fresh(ts))
        self.assertTrue(sso.ts_is_fresh(str(int(time.time()))))


@override_settings(GC_ACCOUNT_NAME='', GC_SECRET_KEY='', GC_SSO_SECRET=SECRET)
class HomeworkReportTest(TestCase):
    """Аутбат в Tech API: триггер, журнал и идемпотентность — без ключей."""

    @classmethod
    def setUpTestData(cls):
        cls.math = Subject.objects.create(name='Физика', slug='phys-gc', icon='⚛️')
        cls.topic = Topic.objects.create(subject=cls.math, name='Кинематика')
        cls.teacher = User.objects.create_user(username='gc_teacher', password='x',
                                               role='teacher')
        cls.student = User.objects.create_user(username='gc_student', password='x',
                                               role='student', gc_uid='9001')
        cls.stray = User.objects.create_user(username='gc_stray', password='x', role='student')
        cls.with_key = cls.task('равноускоренное', '$5$ м/с')
        cls.no_key = cls.task('доказать', '')
        cls.lesson = Assignment.objects.create(
            teacher=cls.teacher, subject=cls.math, title='Домашка в GetCourse',
            status='active', published_at=timezone.now())
        cls.homework = AssignmentBlock.objects.create(
            assignment=cls.lesson, kind='homework', order=0,
            question_ids=[cls.with_key.pk, cls.no_key.pk])
        cls.classwork = AssignmentBlock.objects.create(
            assignment=cls.lesson, kind='in_class', order=1, question_ids=[cls.with_key.pk])
        cls.lesson.students.set([cls.student])

    @classmethod
    def task(cls, text, answer):
        return Question.objects.create(topic=cls.topic, text=text, latex=text,
                                       latex_answer=answer, difficulty='easy',
                                       source_type='book_scan', question_type='open_answer',
                                       verification_status='verified', points=2)

    def _answer(self, block, question, raw):
        return make_client(self.student).post(
            f'/api/my/assignments/{self.lesson.pk}/answer/',
            {'block': block.pk, 'question': question.pk, 'raw_answer': raw}, format='json')

    def _submit(self, block):
        return make_client(self.student).post(
            f'/api/my/assignments/{self.lesson.pk}/submit/', {'block': block.pk},
            format='json')

    def _close_pending(self, question):
        answer = AssignmentAnswer.objects.get(submission__student=self.student,
                                             question=question)
        return make_client(self.teacher).post(
            f'/api/assignment-answers/{answer.pk}/review/', {'verdict': 'correct'},
            format='json')

    def test_pending_review_holds_the_report_back(self):
        self._answer(self.homework, self.with_key, '5 м/с')
        self._answer(self.homework, self.no_key, 'много букв')
        self._submit(self.homework)
        self.assertEqual(LessonReport.objects.count(), 0)

    def test_last_human_verdict_triggers_the_report(self):
        self._answer(self.homework, self.with_key, '5 м/с')
        self._answer(self.homework, self.no_key, 'много букв')
        self._submit(self.homework)
        r = self._close_pending(self.no_key)
        self.assertEqual(r.status_code, 200, r.data)
        row = LessonReport.objects.get()
        self.assertEqual(row.status, 'skipped')
        self.assertEqual(row.external_key,
                         '%s:%s:%s' % (self.lesson.pk, self.student.pk, self.homework.pk))
        self.assertEqual(row.gc_uid, '9001')
        self.assertEqual((row.total, row.correct, row.pending_review, row.percent),
                         (2, 2, 0, 100.0))

    def test_numbers_match_the_matrix_exactly(self):
        """Процент в отчёте и процент в матрице тренера обязаны сойтись: правило
        «pending не входит в знаменатель» одно на оба экрана."""
        self._answer(self.homework, self.with_key, '7 м/с')
        self._answer(self.homework, self.no_key, 'как-то так')
        self._submit(self.homework)
        self._close_pending(self.no_key)
        row = LessonReport.objects.get()
        matrix = make_client(self.teacher).get(
            f'/api/assignments/{self.lesson.pk}/matrix/').data
        cell = [r for r in matrix['rows'] if r['student'] == self.student.pk][0]
        percent = [b for b in cell['blocks'] if b['block'] == self.homework.pk][0]['percent']
        self.assertEqual(row.percent, percent)
        self.assertEqual(row.percent, 50.0)

    def test_classwork_block_is_never_reported(self):
        self._answer(self.classwork, self.with_key, '5 м/с')
        self._submit(self.classwork)
        self.assertEqual(LessonReport.objects.count(), 0)

    def test_empty_block_is_not_reported(self):
        """Пустой домашний блок не отправляется: нулевой урок — это не итог,
        а незаполненный. Другой урок, потому что блоков `homework` на урок один."""
        lesson2 = Assignment.objects.create(teacher=self.teacher, subject=self.math,
                                            title='Пустая домашка', status='active',
                                            published_at=timezone.now())
        empty = AssignmentBlock.objects.create(assignment=lesson2, kind='homework',
                                               order=0, question_ids=[])
        sub = AssignmentSubmission.objects.create(assignment=lesson2, block=empty,
                                                  student=self.stray, state='submitted')
        self.assertIsNone(getcourse.report_submission(sub))

    def test_without_keys_the_post_is_never_attempted(self):
        with mock.patch.object(getcourse, '_post', return_value=(True, '')) as post:
            self._answer(self.homework, self.with_key, '5 м/с')
            self._answer(self.homework, self.no_key, 'текст')
            self._submit(self.homework)
            self._close_pending(self.no_key)
            post.assert_not_called()
        self.assertEqual(LessonReport.objects.count(), 1)
        self.assertEqual(LessonReport.objects.get().status, 'skipped')

    def test_student_without_gc_uid_is_not_sent_even_with_keys(self):
        with override_settings(GC_ACCOUNT_NAME='school', GC_SECRET_KEY='sekret'):
            with mock.patch.object(getcourse, '_post', return_value=(True, '')) as post:
                sub = AssignmentSubmission.objects.create(
                    assignment=self.lesson, block=self.homework, student=self.stray,
                    state='reviewed')
                AssignmentAnswer.objects.create(submission=sub, question=self.with_key,
                                                raw_answer='5', verdict='correct')
                row = getcourse.report_submission(sub)
                self.assertEqual(row.status, 'skipped')
                self.assertIn('gc_uid', row.last_error)
                post.assert_not_called()

    def test_with_keys_the_event_carries_only_numbers(self):
        with override_settings(GC_ACCOUNT_NAME='school', GC_SECRET_KEY='sekret'):
            with mock.patch.object(getcourse, '_post', return_value=(True, '')) as post:
                self._answer(self.homework, self.with_key, '5 м/с')
                self._answer(self.homework, self.no_key, 'моё решение целиком')
                self._submit(self.homework)
                self._close_pending(self.no_key)
                event = post.call_args[0][0]
                self.assertEqual(event['type'], 'lesson.homework.completed')
                self.assertEqual(event['gc_uid'], '9001')
                self.assertEqual(event['percent'], 100.0)
                self.assertEqual(event['correct'], 2)
                body = json.dumps(event, ensure_ascii=False)
                # ответ ученика и эталон книги наружу не уходят никогда
                self.assertNotIn('моё решение целиком', body)
                self.assertNotIn('5$ м/с', body)
        row = LessonReport.objects.get()
        self.assertEqual(row.status, 'sent')
        self.assertEqual(row.attempts, 1)
        self.assertIsNotNone(row.sent_at)

    def test_second_click_sends_nothing_twice(self):
        with override_settings(GC_ACCOUNT_NAME='school', GC_SECRET_KEY='sekret'):
            with mock.patch.object(getcourse, '_post', return_value=(True, '')) as post:
                self._answer(self.homework, self.with_key, '5 м/с')
                self._answer(self.homework, self.no_key, 'текст')
                self._submit(self.homework)
                self._close_pending(self.no_key)
                self.assertEqual(post.call_count, 1)
                # ученик жмёт «Сдать» ещё раз: итог не изменился → второй отправки нет
                self._submit(self.homework)
                self.assertEqual(post.call_count, 1)
                self.assertEqual(LessonReport.objects.count(), 1)

    def test_changed_result_is_sent_again_over_the_same_row(self):
        with override_settings(GC_ACCOUNT_NAME='school', GC_SECRET_KEY='sekret'):
            with mock.patch.object(getcourse, '_post', return_value=(True, '')) as post:
                self._answer(self.homework, self.with_key, '7 м/с')
                self._answer(self.homework, self.no_key, 'текст')
                self._submit(self.homework)
                self._close_pending(self.no_key)
                self.assertEqual(post.call_count, 1)
                self.assertEqual(LessonReport.objects.get().correct, 1)
                # тренер пересмотрел вердикт и итог стал другим — это не дубль, а новое число
                self._close_pending(self.with_key)
                self.assertEqual(post.call_count, 2)
                self.assertEqual(LessonReport.objects.count(), 1)
                row = LessonReport.objects.get()
                self.assertEqual((row.correct, row.percent), (2, 100.0))
                self.assertEqual(row.attempts, 2)

    def test_failed_send_is_journalled_and_retried_next_time(self):
        with override_settings(GC_ACCOUNT_NAME='school', GC_SECRET_KEY='sekret'):
            with mock.patch.object(getcourse, '_post', return_value=(False, 'HTTP 503')) as post:
                self._answer(self.homework, self.with_key, '5 м/с')
                self._answer(self.homework, self.no_key, 'текст')
                self._submit(self.homework)
                self._close_pending(self.no_key)
                row = LessonReport.objects.get()
                self.assertEqual(row.status, 'failed')
                self.assertEqual(row.attempts, 1)
                self.assertEqual(row.last_error, 'HTTP 503')
                post.return_value = (True, '')
                getcourse.report_submission(row.block.submissions.get(student=self.student))
                row.refresh_from_db()
                self.assertEqual(row.status, 'sent')
                self.assertEqual(row.attempts, 2)

    def test_a_broken_network_never_breaks_the_lesson(self):
        """Сдача и ручная проверка обязаны дойти до конца, даже если GetCourse легл:
        отчёт — побочный эффект урока, а не его условие."""
        self._answer(self.homework, self.with_key, '5 м/с')
        self._answer(self.homework, self.no_key, 'текст')
        with override_settings(GC_ACCOUNT_NAME='school', GC_SECRET_KEY='sekret'):
            with mock.patch.object(getcourse, '_post', side_effect=RuntimeError('сеть легла')):
                self.assertEqual(self._submit(self.homework).status_code, 200)
                r = self._close_pending(self.no_key)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['pending_left'], 0)
        row = LessonReport.objects.get()
        self.assertEqual(row.status, 'failed')
        self.assertIn('RuntimeError', row.last_error)
