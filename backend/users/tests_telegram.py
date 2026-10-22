# -*- coding: utf-8 -*-
"""Вход через Telegram (24-й деплой, п.3): подпись виджета, учётка и привязка урока.

Ученики сидят в учебном чате, поэтому вход без пароля идёт по данным Telegram, а не
по почте и не по паролю. Проверяем три вещи:

1. **Подпись.** Её считает сервер по токену бота; подделанная, пустая или протухшая —
   отказ и ни одной новой строки в базе.
2. **Кем становится человек.** Новый — отдельный ученик без пароля; уже вошедший по
   ссылке GetCourse — тот же аккаунт, а не второй на него.
3. **Урок.** `assignment_id` + `lesson_token` из ссылки чата привязывают ученика к
   уроку и уводят его на карточку задания; неверная подпись урока урок не открывает.
"""
import hashlib
import time

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from subjects import sso
from subjects.models import Assignment, Subject
from users import telegram
from users.models import User

BOT = '123456:test-telegram-bot-token'
SSO_SECRET = 'тест-секрет-подписи-6'
URL = '/api/auth/telegram/'


def widget_data(**overrides):
    """Поля так, как их отдаёт Telegram Login Widget: подпись поверх отсортированных."""
    data = {'id': '481234567', 'first_name': 'Айдар', 'last_name': 'Сатов',
            'username': 'aidar_satov', 'auth_date': str(int(time.time()))}
    data.update(overrides)
    data['hash'] = telegram.make_hash(BOT, telegram.normalize(data))
    return data


@override_settings(TELEGRAM_BOT_TOKEN=BOT, TELEGRAM_BOT_USERNAME='entprep_bot',
                   TELEGRAM_AUTH_MAX_AGE=86400)
class TelegramSignatureTest(TestCase):
    """Формула подписи — внешняя, её нельзя «подогнать» под свой код."""

    def test_the_check_string_is_sorted_fields_without_the_hash(self):
        data = {'auth_date': '1700000000', 'first_name': 'Айдар', 'id': '42',
                'username': 'aidar', 'hash': 'любая', 'web_app_hash': 'любая'}
        self.assertEqual(telegram.data_check_string(data),
                         'auth_date=1700000000\nfirst_name=Айдар\nid=42\nusername=aidar')

    def test_the_secret_key_is_sha256_of_the_bot_token(self):
        self.assertEqual(telegram.secret_key('123:abc'),
                         hashlib.sha256(b'123:abc').digest())

    def test_a_field_changed_after_signing_breaks_the_signature(self):
        data = widget_data()
        data['username'] = 'someone_else'
        data_, error = telegram.verify(BOT, data)
        self.assertIsNone(data_)
        self.assertIn('не совпала', error)

    def test_empty_fields_do_not_join_the_signature(self):
        """Telegram не подписывает пустое поле: `last_name=''` в запросе не должен
        требовать строчки `last_name=` в строке проверки."""
        data = widget_data(last_name='')
        signed = telegram.normalize(data)
        self.assertNotIn('last_name', signed)
        data_, error = telegram.verify(BOT, data)
        self.assertIsNotNone(data_, error)

    def test_stale_auth_date_is_refused(self):
        data = widget_data(auth_date=str(int(time.time()) - 90000))
        self.assertFalse(telegram.is_fresh(data['auth_date'], max_age=86400))

    def test_a_broken_auth_date_is_not_fresh(self):
        self.assertFalse(telegram.is_fresh('не число'))


@override_settings(TELEGRAM_BOT_TOKEN=BOT, TELEGRAM_BOT_USERNAME='entprep_bot',
                   TELEGRAM_AUTH_MAX_AGE=86400, GC_SSO_SECRET=SSO_SECRET)
class TelegramLoginTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.math = Subject.objects.create(name='Физика', slug='phys-tg', icon='⚛️')
        cls.teacher = User.objects.create_user(username='tg_teacher', password='x',
                                                role='teacher', email='pro@intellect.kz')
        cls.lesson = Assignment.objects.create(
            teacher=cls.teacher, subject=cls.math, title='Термодинамика из чата',
            status='active', published_at=timezone.now())
        cls.token = sso.make_lesson_token(SSO_SECRET, cls.lesson.pk)

    def _post(self, payload, user=None):
        c = APIClient()
        if user is not None:
            c.force_authenticate(user=user)
        return c.post(URL, payload, format='json')

    def test_the_config_answers_whether_the_button_is_ready(self):
        r = APIClient().get(URL + 'config/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, {'enabled': True, 'telegram_bot_username': 'entprep_bot'})

    def test_without_a_bot_token_the_config_switches_the_button_off(self):
        with override_settings(TELEGRAM_BOT_TOKEN=''):
            r = APIClient().get(URL + 'config/')
        self.assertFalse(r.data['enabled'])

    def test_without_a_bot_token_the_login_is_closed(self):
        with override_settings(TELEGRAM_BOT_TOKEN=''):
            r = self._post(widget_data())
        self.assertEqual(r.status_code, 403, r.data)
        self.assertIn('не настроен', r.data['detail'])
        self.assertEqual(User.objects.filter(telegram_id=481234567).count(), 0)

    def test_a_class_pressing_the_button_together_does_not_hit_a_wall(self):
        """Лимит `telegram_auth` — 60 входов с одного IP в минуту: весь класс с телефона
        заходит, а перебор чужих подписей всё равно упирается в 429."""
        cache.clear()
        codes = [self._post(widget_data()).status_code for _ in range(61)]
        self.assertEqual(codes[:60], [200] * 60, codes[55:61])
        self.assertEqual(codes[60], 429)
        cache.clear()

    def test_a_new_student_enters_and_gets_his_own_account(self):
        r = self._post(widget_data())
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data['access'] and r.data['refresh'])
        self.assertEqual(r.data['next'], '/assignments')
        self.assertTrue(r.data['created'])
        student = User.objects.get(telegram_id=481234567)
        self.assertEqual(student.role, 'student')
        self.assertEqual(student.username, 'aidar_satov')
        self.assertEqual(student.full_name, 'Айдар Сатов')
        self.assertFalse(student.has_usable_password())

    def test_a_second_login_reuses_the_same_account(self):
        first = self._post(widget_data())
        second = self._post(widget_data())
        self.assertEqual(second.data['user']['id'], first.data['user']['id'])
        self.assertFalse(second.data['created'])
        self.assertEqual(User.objects.filter(telegram_id=481234567).count(), 1)

    def test_a_forged_signature_enters_nobody(self):
        data = widget_data()
        data['id'] = '999'
        r = self._post(data)
        self.assertEqual(r.status_code, 403, r.data)
        self.assertIn('не совпала', r.data['detail'])
        self.assertEqual(User.objects.count(), 1)  # только тренер из фикстуры

    def test_a_missing_hash_is_refused(self):
        data = widget_data()
        data.pop('hash')
        r = self._post(data)
        self.assertEqual(r.status_code, 403, r.data)
        self.assertIn('подписи', r.data['detail'])

    def test_a_stale_answer_is_refused(self):
        r = self._post(widget_data(auth_date=str(int(time.time()) - 3 * 86400)))
        self.assertEqual(r.status_code, 403, r.data)
        self.assertIn('старый', r.data['detail'])

    def test_a_taken_username_gets_a_suffix(self):
        User.objects.create_user(username='aidar_satov', password='x', role='student')
        r = self._post(widget_data())
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(User.objects.get(telegram_id=481234567).username, 'aidar_satov1')

    def test_a_student_without_a_username_is_named_by_his_telegram_number(self):
        r = self._post(widget_data(username=''))
        self.assertEqual(User.objects.get(telegram_id=481234567).username, 'tg481234567')
        self.assertEqual(r.status_code, 200, r.data)

    def test_the_lesson_from_the_chat_link_attaches_the_student(self):
        r = self._post(dict(widget_data(), assignment_id=str(self.lesson.pk),
                            lesson_token=self.token))
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['next'], '/assignments?open=%s' % self.lesson.pk)
        self.assertEqual(r.data['notice'], '')
        self.assertTrue(self.lesson.students.filter(telegram_id=481234567).exists())

    def test_a_forged_lesson_token_logs_in_but_opens_no_lesson(self):
        """Человек вошёл честно, а подпись урока не сошлась: сессия есть, урока нет,
        и причина названа — иначе ученик решит, что ссылка не работает."""
        r = self._post(dict(widget_data(), assignment_id=str(self.lesson.pk),
                            lesson_token='deadbeef'))
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['next'], '/assignments')
        self.assertIn('подпись урока не совпала', r.data['notice'])
        self.assertEqual(self.lesson.students.count(), 0)

    def test_a_revoked_lesson_is_not_attached(self):
        self.lesson.status = 'revoked'
        self.lesson.save(update_fields=['status'])
        r = self._post(dict(widget_data(), assignment_id=str(self.lesson.pk),
                            lesson_token=self.token))
        self.assertEqual(r.status_code, 200, r.data)
        self.assertIn('не найден или уже отозван', r.data['notice'])
        self.assertEqual(self.lesson.students.count(), 0)

    def test_an_already_signed_in_student_keeps_his_account_and_binds_telegram(self):
        """Пришёл по ссылке GetCourse, а потом нажал «Войти через Telegram» — тот же
        человек и тот же аккаунт, уроки остаются на нём."""
        aidar = User.objects.create_user(username='tg_aidar', password='x', role='student',
                                         email='aidar@mail.kz', gc_uid='777')
        r = self._post(widget_data(), user=aidar)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data['bound'])
        self.assertEqual(r.data['user']['id'], aidar.pk)
        aidar.refresh_from_db()
        self.assertEqual(aidar.telegram_id, 481234567)
        self.assertEqual(User.objects.filter(telegram_id=481234567).count(), 1)

    def test_binding_a_telegram_that_already_belongs_to_someone_is_refused(self):
        other = User.objects.create_user(username='tg_other', password='x', role='student',
                                         telegram_id=481234567)
        aidar = User.objects.create_user(username='tg_aidar', password='x', role='student')
        r = self._post(widget_data(), user=aidar)
        self.assertEqual(r.status_code, 403, r.data)
        self.assertIn('другому аккаунту', r.data['detail'])
        aidar.refresh_from_db()
        self.assertIsNone(aidar.telegram_id)

    def test_a_second_telegram_on_one_account_is_refused(self):
        aidar = User.objects.create_user(username='tg_aidar', password='x', role='student',
                                         telegram_id=111)
        r = self._post(widget_data(), user=aidar)
        self.assertEqual(r.status_code, 403, r.data)
        self.assertIn('другой Telegram', r.data['detail'])

    def test_a_teacher_does_not_get_a_passwordless_key(self):
        """Подпись Telegram опознаёт человека, но право войти без пароля есть только
        у ученика: иначе виджет в чате открывал бы тренерский экран."""
        r = self._post(widget_data(), user=self.teacher)
        self.assertEqual(r.status_code, 403, r.data)
        self.assertIn('по логину и паролю', r.data['detail'])
        self.assertEqual(User.objects.filter(telegram_id=481234567).count(), 0)

    def test_a_staff_student_is_refused(self):
        insider = User.objects.create_user(username='tg_insider', password='x',
                                           role='student', telegram_id=481234567)
        insider.is_staff = True
        insider.save(update_fields=['is_staff'])
        r = self._post(widget_data())
        self.assertEqual(r.status_code, 403, r.data)
        self.assertIn('не к активному ученику', r.data['detail'])

    def test_the_key_from_the_login_works_on_the_students_own_list(self):
        r = self._post(dict(widget_data(), assignment_id=str(self.lesson.pk),
                            lesson_token=self.token))
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION='Bearer ' + r.data['access'])
        rows = c.get('/api/my/assignments/').data
        self.assertIn(self.lesson.pk, [row['id'] for row in rows['results']]
                      if isinstance(rows, dict) and 'results' in rows else [row['id'] for row in rows])
