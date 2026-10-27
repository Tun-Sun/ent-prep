# -*- coding: utf-8 -*-
"""Вход через Telegram (24-й деплой, п.3): подпись виджета, учётка и привязка урока.

Ученики сидят в учебном чате, поэтому вход без пароля идёт по данным Telegram, а не
по почте и не по паролю. Проверяем три вещи:

1. **Подпись.** Её считает сервер по токену бота; подделанная, пустая или протухшая —
   отказ и ни одной новой строки в базе.
2. **Кем становится человек.** Новый — отдельный ученик без пароля; уже заведённый по
   этому `telegram_id` — тот же аккаунт. Чужая сессия в `Authorization` не влияет ни
   на что: вход по Telegram никогда не привязывается к тому, под чьим токеном пришёл
   запрос (26-й деплой). Ник из `TELEGRAM_OWNER_BINDINGS` (владелец центра) —
   исключение: он привязывается к уже заведённому вручную аккаунту (28-й деплой).
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

    def _post(self, payload):
        return APIClient().post(URL, payload, format='json')

    def test_the_config_answers_whether_the_button_is_ready(self):
        r = APIClient().get(URL + 'config/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, {'enabled': True, 'telegram_bot_username': 'entprep_bot',
                                  'telegram_bot_id': '123456'})

    def test_the_config_never_leaks_the_bot_token(self):
        """Номер бота — левая часть токена, она открыта в адресе `oauth.telegram.org`.
        Правая часть (секрет) наружу не уходит ни целиком, ни хвостом."""
        r = APIClient().get(URL + 'config/')
        self.assertNotIn('test-telegram-bot-token', str(r.data))
        with override_settings(TELEGRAM_BOT_TOKEN='без-двоеточия'):
            self.assertEqual(APIClient().get(URL + 'config/').data['telegram_bot_id'], '')

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

    def test_a_stale_token_never_binds_telegram_to_that_account(self):
        """26-й деплой: в `localStorage` телефона мог остаться чужим (тестовая ссылка
        с `gc_uid`/`email`). Живой `Authorization` теперь не читается вовсе: подпись
        Telegram заводит **своего** ученика, а чужой аккаунт остаётся чистым.
        Иначе человек входил в чужой профиль, сам того не заметив."""
        from rest_framework_simplejwt.tokens import RefreshToken
        other = User.objects.create_user(username='tg_admin1', password='x', role='student',
                                         email='admin@pmci.kz', gc_uid='361272234')
        r = APIClient().post(URL, widget_data(), format='json',
                             HTTP_AUTHORIZATION='Bearer ' + str(RefreshToken.for_user(other).access_token))
        self.assertEqual(r.status_code, 200, r.data)
        self.assertNotEqual(r.data['user']['id'], other.pk)
        other.refresh_from_db()
        self.assertIsNone(other.telegram_id)
        student = User.objects.get(telegram_id=481234567)
        self.assertEqual(student.username, 'aidar_satov')
        self.assertEqual(student.full_name, 'Айдар Сатов')

    def test_a_teacher_session_does_not_become_a_passwordless_key(self):
        """Подпись Telegram опознаёт человека, но право войти без пароля есть только
        у ученика: тренер под своей сессией получает своего же ученика, а не ключ
        от тренерского экрана."""
        from rest_framework_simplejwt.tokens import RefreshToken
        r = APIClient().post(URL, widget_data(), format='json',
                             HTTP_AUTHORIZATION='Bearer ' +
                             str(RefreshToken.for_user(self.teacher).access_token))
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['user']['role'], 'student')
        self.assertEqual(User.objects.get(telegram_id=481234567).pk, r.data['user']['id'])
        self.teacher.refresh_from_db()
        self.assertIsNone(self.teacher.telegram_id)

    def test_the_key_the_server_returns_belongs_to_the_telegram_student(self):
        """Выданный токен открывает список уроков **своего** ученика: фронт кладёт его
        поверх старых токенов, и чужая сессия не остаётся в браузере."""
        from rest_framework_simplejwt.tokens import RefreshToken
        other = User.objects.create_user(username='tg_admin1', password='x', role='student')
        c = APIClient()
        r = c.post(URL, widget_data(), format='json',
                   HTTP_AUTHORIZATION='Bearer ' + str(RefreshToken.for_user(other).access_token))
        fresh = APIClient()
        fresh.credentials(HTTP_AUTHORIZATION='Bearer ' + r.data['access'])
        self.assertEqual(fresh.get('/api/auth/profile/').data['id'], r.data['user']['id'])

    def test_an_existing_account_is_named_as_telegram_sees_it(self):
        """Человек поменял имя в Telegram — платформа называет его так же, а не держит
        старую строку: по имени тренера ищут ученика."""
        student = User.objects.create_user(username='tg_aidar', password='x', role='student',
                                           telegram_id=481234567, first_name='Старый',
                                           last_name='', full_name='Старый')
        r = self._post(widget_data(first_name='Айдар', last_name='Сатов'))
        self.assertEqual(r.status_code, 200, r.data)
        self.assertFalse(r.data['created'])
        self.assertEqual(r.data['user']['id'], student.pk)
        student.refresh_from_db()
        self.assertEqual(student.first_name, 'Айдар')
        self.assertEqual(student.full_name, 'Айдар Сатов')

    def test_an_empty_field_from_telegram_keeps_the_name_in_the_base(self):
        """Виджет отдаёт `last_name` только если человек его заполнял: пустая строка
        в ответе — не отказ от фамилии, затирать её нельзя."""
        student = User.objects.create_user(username='tg_aidar', password='x', role='student',
                                           telegram_id=481234567, first_name='Айдар',
                                           last_name='Сатов', full_name='Айдар Сатов')
        self._post(widget_data(last_name=''))
        student.refresh_from_db()
        self.assertEqual(student.last_name, 'Сатов')
        self.assertEqual(student.full_name, 'Айдар Сатов')

    def test_a_new_student_is_asked_to_introduce_himself(self):
        """Без класса ученика тренера не знают, кого они видят в журнале: сервер сам
        говорит экрану показать карточку «Представься»."""
        r = self._post(widget_data())
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data['need_profile'])
        self.assertEqual(r.data['user']['grade'], None)

    def test_a_student_who_already_introduced_skips_the_card(self):
        student = User.objects.create_user(username='tg_aidar', password='x', role='student',
                                           telegram_id=481234567, first_name='Айдар',
                                           last_name='Сатов', full_name='Сатов Айдар', grade=10)
        r = self._post(widget_data(first_name='Ник', last_name='ИзТелеграма'))
        self.assertEqual(r.status_code, 200, r.data)
        self.assertFalse(r.data['need_profile'])
        student.refresh_from_db()
        # Представился сам — значит ник мессенджера не пересиливает то, что читает
        # тренер в журнале.
        self.assertEqual(student.full_name, 'Сатов Айдар')
        self.assertEqual(student.grade, 10)

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


@override_settings(TELEGRAM_BOT_TOKEN=BOT, TELEGRAM_BOT_USERNAME='entprep_bot',
                   TELEGRAM_AUTH_MAX_AGE=86400,
                   TELEGRAM_OWNER_BINDINGS={'mr.axmetov': 'bolatkhan'})
class TelegramOwnerBindingTest(TestCase):
    """Ник владельца центра привязывается к его аккаунту, а не заводит пустого ученика.

    Владелец входит через тот же виджет, что и ученики, но его аккаунт заведён вручную.
    Подпись Telegram доказывает владение ником, поэтому её достаточно для привязки.
    """

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username='bolatkhan', password='x',
                                             role='teacher', first_name='Болатхан',
                                             full_name='Болатхан')
        cls.owner.is_staff = True
        cls.owner.save(update_fields=['is_staff'])
        cls.subject = Subject.objects.create(name='Математика', slug='own-tg', icon='📐')
        cls.lesson = Assignment.objects.create(title='Урок владельца', subject=cls.subject,
                                               teacher=cls.owner, status='active',
                                               published_at=timezone.now())

    def login(self, **overrides):
        cache.clear()
        return APIClient().post(URL, widget_data(**overrides), format='json')

    def test_the_owner_nick_lands_on_his_existing_account(self):
        res = self.login(id='777000222', username='mr.axmetov', first_name='Bolatkhan',
                         last_name='')
        self.assertEqual(res.status_code, 200, res.data)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.telegram_id, 777000222)
        self.assertEqual(self.owner.telegram_username, 'mr.axmetov')
        self.assertEqual(res.data['user']['id'], self.owner.pk)
        self.assertFalse(res.data['created'])
        # пустого ученика с таким ником база не получила
        self.assertEqual(User.objects.filter(telegram_id=777000222).count(), 1)

    def test_the_nick_registr_is_not_the_case(self):
        res = self.login(id='777000223', username='MR.AXmetov')
        self.assertEqual(res.status_code, 200, res.data)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.telegram_id, 777000223)

    def test_the_owner_goes_to_his_cabinet_not_the_student_list(self):
        res = self.login(id='777000224', username='mr.axmetov')
        self.assertEqual(res.data['next'], '/teacher')

    def test_the_owner_is_not_written_as_a_student_into_his_own_lesson(self):
        token = sso.make_lesson_token(SSO_SECRET, self.lesson.pk)
        res = self.login(id='777000225', username='mr.axmetov',
                         assignment_id=str(self.lesson.pk), lesson_token=token)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertIn('не ученический', res.data['notice'])
        self.assertNotIn(self.owner.pk,
                         [u.pk for u in self.lesson.students.all()])

    def test_the_owner_moves_his_bind_when_his_number_changed(self):
        self.owner.telegram_id = 777000111
        self.owner.save(update_fields=['telegram_id'])
        res = self.login(id='777000226', username='mr.axmetov')
        self.assertEqual(res.status_code, 200, res.data)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.telegram_id, 777000226)

    def test_the_owner_enters_again_after_the_first_tap(self):
        """Второй тап по кнопке — тот же вход, а не «привязан не к активному ученику».

        После первой привязки аккаунт владельца перестал быть «не учеником» только для
        этого ника: без исключения в проверке второй вход дал бы 403.
        """
        first = self.login(id='777000228', username='mr.axmetov')
        self.assertEqual(first.status_code, 200, first.data)
        again = self.login(id='777000228', username='mr.axmetov')
        self.assertEqual(again.status_code, 200, again.data)
        self.assertEqual(again.data['user']['id'], self.owner.pk)
        self.assertEqual(User.objects.filter(telegram_id=777000228).count(), 1)

    def test_an_ordinary_student_is_still_created_as_a_student(self):
        res = self.login(id='777000227', username='some_kid')
        self.assertEqual(res.status_code, 200, res.data)
        kid = User.objects.get(telegram_id=777000227)
        self.assertEqual(kid.role, 'student')
        self.assertFalse(kid.is_staff)
        self.assertEqual(res.data['next'], '/assignments')
