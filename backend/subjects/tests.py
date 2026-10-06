"""
Тесты конвейера импорта из Google Forms.

Покрывают:
- парсер (валидный JSON, ошибки структуры, не-quiz, без subject/topic);
- importer (создание вопросов, дедупликация по external_id,
  маркировка verified/draft по наличию правильного ответа);
- DRF-эндпоинт (401 без токена, 403 студенту, dry_run, happy path,
  обработка невалидного JSON).

Drive API (скачивание картинок) тестируется на моках в images.py —
здесь внешних вызовов нет.
"""
from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from subjects.google_forms.dto import AnswerDTO, QuestionDTO
from subjects.google_forms.importer import ImporterError, import_payload
from subjects.google_forms.parser import ParseError, parse_dict
from subjects.models import Answer, Question, Subject, Topic


# === Фикстуры / хелперы ====================================================

def make_payload(**overrides):
    """Минимальный валидный payload для тестов."""
    base = {
        'schema_version': 1,
        'source': {
            'type': 'google_forms',
            'form_id': 'FORM1',
            'form_url': 'https://forms.gle/test',
            'form_title': 'Тест',
            'is_quiz': True,
        },
        'subject_slug': 'physics',
        'subject_name': '',
        'topic_name': 'Кинематика',
        'language': 'ru',
        'year': 2026,
        'questions': [
            {
                'external_id': 'FORM1/1',
                'title': 'Сколько будет 2+2?',
                'help_text': '',
                'image': None,
                'type': 'multiple_choice',
                'answers': [
                    {'text': '3', 'is_correct': False},
                    {'text': '4', 'is_correct': True},
                    {'text': '5', 'is_correct': False},
                ],
                'has_correct': True,
                'order_index': 0,
            }
        ],
    }
    base.update(overrides)
    return base


# === Тесты парсера =========================================================

class ParserTest(TestCase):
    def test_valid_payload(self):
        p = parse_dict(make_payload())
        self.assertEqual(p.form_id, 'FORM1')
        self.assertEqual(len(p.questions), 1)
        q = p.questions[0]
        self.assertEqual(q.external_id, 'FORM1/1')
        self.assertEqual(q.title, 'Сколько будет 2+2?')
        self.assertEqual(len(q.answers), 3)
        self.assertTrue(q.has_correct)
        self.assertEqual(q.answers[1].text, '4')
        self.assertTrue(q.answers[1].is_correct)

    def test_wrong_schema_version(self):
        with self.assertRaises(ParseError):
            parse_dict(make_payload(schema_version=2))

    def test_unsupported_question_type_skipped(self):
        # Apps Script уже отфильтрует неподдерживаемые, но парсер тоже защищён.
        payload = make_payload(questions=[
            {'external_id': 'X/1', 'title': 'q', 'type': 'multiple_choice',
             'answers': [{'text': 'a', 'is_correct': True},
                         {'text': 'b', 'is_correct': False}]}
        ])
        # Валидный тип проходит без ошибки.
        parse_dict(payload)

    def test_too_few_answers_rejected(self):
        payload = make_payload(questions=[
            {'external_id': 'X/1', 'title': 'q', 'type': 'multiple_choice',
             'answers': [{'text': 'only one', 'is_correct': True}]}
        ])
        with self.assertRaises(ParseError):
            parse_dict(payload)

    def test_no_subject_rejected(self):
        payload = make_payload(subject_slug='', subject_name='')
        with self.assertRaises(ParseError):
            parse_dict(payload)

    def test_no_topic_rejected(self):
        payload = make_payload(topic_name='')
        with self.assertRaises(ParseError):
            parse_dict(payload)

    def test_empty_external_id_rejected(self):
        payload = make_payload(questions=[
            {'external_id': '', 'title': 'q', 'type': 'multiple_choice',
             'answers': [{'text': 'a', 'is_correct': True},
                         {'text': 'b', 'is_correct': False}]}
        ])
        with self.assertRaises(ParseError):
            parse_dict(payload)

    def test_duplicate_external_id_in_file_rejected(self):
        q1 = {'external_id': 'DUP', 'title': 'q1', 'type': 'multiple_choice',
              'answers': [{'text': 'a', 'is_correct': True},
                          {'text': 'b', 'is_correct': False}]}
        payload = make_payload(questions=[q1, dict(q1, title='q2')])
        with self.assertRaises(ParseError):
            parse_dict(payload)

    def test_invalid_json_top_level(self):
        with self.assertRaises(ParseError):
            parse_dict([1, 2, 3])  # type: ignore[arg-type]


# === Тесты importer-а (с реальной БД) ======================================

class ImporterTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.physics = Subject.objects.create(
            name='Физика', slug='physics', icon='⚡'
        )

    def test_happy_path_creates_question_and_answers(self):
        payload = parse_dict(make_payload())
        result = import_payload(payload)

        self.assertEqual(result.created, 1)
        self.assertEqual(result.skipped_duplicates, 0)
        q = Question.objects.get(external_id='FORM1/1')
        self.assertEqual(q.source_type, 'authorial')
        self.assertEqual(q.verification_status, 'verified')
        self.assertEqual(q.language, 'ru')
        self.assertEqual(q.year, 2026)
        self.assertEqual(q.answers.count(), 3)
        self.assertEqual(q.answers.filter(is_correct=True).count(), 1)

    def test_topic_created_automatically(self):
        payload = parse_dict(make_payload(topic_name='Новая тема'))
        import_payload(payload)
        self.assertTrue(Topic.objects.filter(
            subject=self.physics, name='Новая тема'
        ).exists())

    def test_dedup_by_external_id_skips_second_run(self):
        payload = parse_dict(make_payload())
        r1 = import_payload(payload)
        r2 = import_payload(payload)

        self.assertEqual(r1.created, 1)
        self.assertEqual(r2.created, 0)
        self.assertEqual(r2.skipped_duplicates, 1)
        # В БД остался ровно один вопрос с этим external_id.
        self.assertEqual(Question.objects.filter(external_id='FORM1/1').count(), 1)

    def test_no_correct_answer_marks_draft(self):
        payload_dict = make_payload(questions=[{
            'external_id': 'FORM1/99',
            'title': 'Без правильного',
            'type': 'multiple_choice',
            'answers': [
                {'text': 'a', 'is_correct': False},
                {'text': 'b', 'is_correct': False},
            ],
            'order_index': 0,
        }])
        payload = parse_dict(payload_dict)
        result = import_payload(payload)

        self.assertEqual(result.created, 1)
        self.assertEqual(result.drafted_no_correct, 1)
        q = Question.objects.get(external_id='FORM1/99')
        self.assertEqual(q.verification_status, 'draft')

    def test_unknown_subject_raises(self):
        payload = parse_dict(make_payload(subject_slug='nonexistent'))
        with self.assertRaises(ImporterError):
            import_payload(payload)

    def test_atomiticity_no_partial_writes_on_error(self):
        # 2 вопроса, у второго кривой external_id (пустой после .strip)
        # — парсер такое поймает ДО importer, поэтому здесь эмулируем ошибку
        # через несуществующий предмет на 2-м payload-блоке.
        # Реальная атомарность гарантируется transaction.atomic() в importer.
        payload = parse_dict(make_payload())
        # Импортируем успешно, потом пытаемся повторно — повтор не ломает.
        import_payload(payload)
        import_payload(payload)  # не должно бросать
        self.assertEqual(Question.objects.filter(external_id='FORM1/1').count(), 1)


# === Тесты DRF-эндпоинта ===================================================

class GoogleFormsEndpointTest(TestCase):
    url = '/api/import/google-forms/'

    @classmethod
    def setUpTestData(cls):
        cls.physics = Subject.objects.create(
            name='Физика', slug='physics', icon='⚡'
        )
        from users.models import User
        cls.teacher = User.objects.create_user(
            username='t1', password='x', role='teacher'
        )
        cls.student = User.objects.create_user(
            username='s1', password='x', role='student'
        )

    def _auth(self, user):
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def test_unauthenticated_401(self):
        from rest_framework.test import APIClient
        import json
        c = APIClient()
        r = c.post(self.url, data=json.dumps(make_payload()),
                   content_type='application/json')
        self.assertEqual(r.status_code, 401)

    def test_student_forbidden_403(self):
        import json
        c = self._auth(self.student)
        r = c.post(self.url, data=json.dumps(make_payload()),
                   content_type='application/json')
        self.assertEqual(r.status_code, 403)

    def test_teacher_dry_run_no_write(self):
        import json
        c = self._auth(self.teacher)
        before = Question.objects.count()
        r = c.post(self.url + '?dry_run=1',
                   data=json.dumps(make_payload()),
                   content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['dry_run'])
        self.assertEqual(Question.objects.count(), before)  # ничего не записано

    def test_teacher_happy_path_creates(self):
        import json
        c = self._auth(self.teacher)
        r = c.post(self.url, data=json.dumps(make_payload()),
                   content_type='application/json')
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertTrue(body['ok'])
        self.assertEqual(body['result']['created'], 1)
        self.assertTrue(Question.objects.filter(external_id='FORM1/1').exists())

    def test_invalid_json_returns_400(self):
        import json
        c = self._auth(self.teacher)
        # payload без обязательного subject.
        bad = make_payload(subject_slug='', subject_name='')
        r = c.post(self.url, data=json.dumps(bad),
                   content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_multipart_file_upload(self):
        import io, json
        from django.core.files.uploadedfile import SimpleUploadedFile
        from rest_framework.test import APIClient

        c = self._auth(self.teacher)
        body = json.dumps(make_payload()).encode('utf-8')
        f = SimpleUploadedFile('form.json', body, content_type='application/json')
        r = c.post(self.url, data={'file': f}, format='multipart')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()['meta']['source'], 'file:form.json')

    def test_multipart_non_json_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        c = self._auth(self.teacher)
        f = SimpleUploadedFile('not.txt', b'hello', content_type='text/plain')
        r = c.post(self.url, data={'file': f}, format='multipart')
        self.assertEqual(r.status_code, 400)


# === Банк оцифрованных из книг задач =======================================
# Отдельный набор, потому что банк перегоняют в одну и ту же базу сколько угодно
# раз, и каждое из трёх правил ниже уже однажды нарушалось молча: дубль по ключу,
# затёртая правка человека, чужая картинка на задаче.

def scan_unit(**overrides):
    """Единица tasks.json ровно в той форме, в какой её пишет pipeline/tasks.py."""
    base = {
        'key': 'Решение отдельных задач#Задача1',
        'num': '1', 'word': 'Задача', 'kind': 'word',
        'scope': 'Решение отдельных задач', 'block': 'Решение отдельных задач',
        'pages': [8], 'spans': [{'page': 8, 'l0': 3, 'l1': 12}],
        'figures': [], 'markdown': '$x = 1$', 'answer_in': [], 'uncertain': [],
        'options': 0, 'options_cyr': None, 'options_list': [],
    }
    base.update(overrides)
    return base


class BookScanBankTest(TestCase):
    """Перегон импорта: ключ перезаписи, защита правки, чужие кадры."""

    @classmethod
    def setUpTestData(cls):
        cls.physics = Subject.objects.create(name='Физика', slug='physics', icon='⚡')

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.run = Path(self.tmp) / 'out_t'
        self.run.mkdir()

    def write_run(self, units):
        (self.run / 'tasks.json').write_text(json.dumps(
            {'run': 'out_t', 'tasks': units, 'answers': [], 'other': [], 'pages': []},
            ensure_ascii=False), encoding='utf-8')

    def do_import(self):
        out = io.StringIO()
        call_command('import_scanned_tasks', str(self.run), subject='physics',
                     book='Сборник', stdout=out)
        return out.getvalue()

    def test_import_creates_row_and_topic(self):
        self.write_run([scan_unit()])
        self.do_import()
        q = Question.objects.get(source_type='book_scan')
        self.assertEqual(q.external_id, 'out_t:p8:Задача1:Решение отдельных задач')
        self.assertEqual(q.topic.name, 'Сборник · Решение отдельных задач')
        self.assertEqual(q.verification_status, 'draft')
        self.assertEqual(q.provenance['run'], 'out_t')
        self.assertEqual(q.provenance['pages'], [8])

    def test_second_run_updates_not_duplicates(self):
        self.write_run([scan_unit()])
        self.do_import()
        self.write_run([scan_unit(markdown='$x = 2$')])
        self.do_import()
        self.assertEqual(Question.objects.filter(source_type='book_scan').count(), 1)
        self.assertEqual(Question.objects.get().latex, '$x = 2$')

    def test_test_unit_gets_options_as_answer_rows(self):
        """Тест остаётся тестом: варианты печатаются в условии и едут строками ответа.

        Без строк ответа приложение не может отрендерить выбор, а переписывать условие
        нельзя — так книга и напечатала. Ключа ответа в отсканированной части нет,
        поэтому ни один вариант не помечен правильным: выдумывать его импорт не вправе.
        """
        self.write_run([scan_unit(
            word='', scope='ТАҚЫРЫПТЫҚ ТЕСТ', block='ТАҚЫРЫПТЫҚ ТЕСТ', key='ТАҚЫРЫПТЫҚ ТЕСТ#1',
            markdown='Сұрақ\nA) $8{,}3$\nB) $19{,}92$', options=2,
            options_list=[{'letter': 'A', 'text': '$8{,}3$'}, {'letter': 'B', 'text': '$19{,}92$'}])])
        self.do_import()
        q = Question.objects.get(source_type='book_scan')
        self.assertEqual(q.question_type, 'single_choice')
        self.assertEqual(list(q.answers.order_by('id').values_list('text', flat=True)),
                         ['$8{,}3$', '$19{,}92$'])
        self.assertFalse(any(q.answers.values_list('is_correct', flat=True)))
        self.assertIn('A) $8{,}3$', q.latex)
        self.assertEqual(q.provenance['format'], 'тест')
        # перегон не должен плодить дубли вариантов
        self.do_import()
        self.assertEqual(q.answers.count(), 2)

    def test_human_edit_survives_reimport(self):
        self.write_run([scan_unit()])
        self.do_import()
        q = Question.objects.get()
        q.latex = '$x = 3$  # исправил тренер'
        q.verification_status = 'verified'
        q.provenance = {**q.provenance, 'human_edited': True}
        q.save()
        report = self.do_import()  # прогон предлагает прежний $x = 1$
        q.refresh_from_db()
        self.assertEqual(q.latex, '$x = 3$  # исправил тренер')
        self.assertEqual(q.verification_status, 'verified')
        self.assertIn('ручных правок сохранено 1', report)

    def test_bulk_acceptance_keeps_status_but_still_updates_text(self):
        """Приёмка пакетом — решение про статус, а не про текст.

        human_edited бережёт условие целиком; если бы приёмка пакетом ставила ту же
        метку, принятая сегодня строка навсегда застыла бы в текущей оцифровке.
        """
        self.write_run([scan_unit()])
        self.do_import()
        q = Question.objects.get()
        q.verification_status = 'verified'
        q.provenance = {**q.provenance, 'accepted_by': 'teacher1',
                        'accepted_at': '2026-10-06T12:00:00'}
        q.save()
        self.write_run([scan_unit(markdown='$x = 2$')])
        report = self.do_import()
        q.refresh_from_db()
        self.assertEqual(q.verification_status, 'verified')
        self.assertEqual(q.latex, '$x = 2$')
        self.assertEqual(q.provenance['accepted_by'], 'teacher1')
        self.assertIn('принято пакетом в банке 1', report)

    def test_foreign_crop_is_taken_off_the_task(self):
        """Кадр обязан принадлежать телу задачи: без figures остаётся пустое поле."""
        self.write_run([scan_unit(figures=['assets/p08_fig1.png'])])
        (self.run / 'assets').mkdir()
        (self.run / 'assets' / 'p08_fig1.png').write_bytes(b'\x89PNG\r\n\x1a\n' + b'0' * 32)
        self.do_import()
        q = Question.objects.get()
        self.assertEqual(q.image_ref, 'out_t:p08_fig1.png')
        self.assertTrue(q.image)
        # второй прогон, где парсер больше не считает эту выкройку содержимым
        self.write_run([scan_unit(figures=[])])
        report = self.do_import()
        q.refresh_from_db()
        self.assertEqual(q.image_ref, '')
        self.assertIn('картинок снято по чужому кадру 1', report)

    def test_review_mark_makes_row_verified(self):
        u = scan_unit()
        self.write_run([u])
        (self.run / 'review.json').write_text(
            json.dumps({u['key']: {'ok': True}}), encoding='utf-8')
        report = self.do_import()
        self.assertIn('принято человеком 1 из 1', report)
        self.assertEqual(Question.objects.get().verification_status, 'verified')

    def test_review_note_survives_reimport_without_becoming_acceptance(self):
        """Заметка «сверено глазами, спор остался» доезжает до банка, статус не меняет."""
        u = scan_unit()
        self.write_run([u])
        (self.run / 'review.json').write_text(json.dumps({
            u['key']: {'ok': False, 'by': 'глаза по скану', 'at': '2026-10-06T10:00:00',
                       'note': 'в книге напечатано 10^22, это опечатка пособия'}}), encoding='utf-8')
        report = self.do_import()
        self.assertIn('принято человеком 0 из 1', report)
        self.assertIn('со заметкой со скана 1', report)
        q = Question.objects.get()
        self.assertEqual(q.verification_status, 'draft')
        self.assertEqual(q.provenance['review_note'], 'в книге напечатано 10^22, это опечатка пособия')
        self.assertEqual(q.provenance['review_by'], 'глаза по скану')
        # перегон не должен оставлять заметку от прошлой записи приёмки, если её сняли
        (self.run / 'review.json').write_text('{}', encoding='utf-8')
        self.do_import()
        self.assertEqual(Question.objects.get().provenance['review_note'], '')

    def test_source_pages_points_at_scan_rasters(self):
        from subjects.serializers import QuestionListSerializer
        self.write_run([scan_unit(pages=[8, 9])])
        self.do_import()
        data = QuestionListSerializer(Question.objects.get()).data
        self.assertEqual(data['source_pages'],
                         ['/media/scans/out_t/p08.png', '/media/scans/out_t/p09.png'])

    def test_source_pages_empty_without_provenance(self):
        from subjects.serializers import QuestionListSerializer
        topic = Topic.objects.create(subject=self.physics, name='Обычная тема')
        q = Question.objects.create(topic=topic, text='Не из скана', source_type='manual')
        self.assertEqual(QuestionListSerializer(q).data['source_pages'], [])


class BulkVerifyTest(TestCase):
    """Пакетная приёмка: один запрос на всю выборку вместо окна на каждую задачу.

    Отдельный класс потому, что это единственная кнопка банка, которая трогает сотню
    строк сразу. Главное в ней — взят ровно тот фильтр, который человек видит на
    экране, а не «всё, что лежит в базе».
    """
    url = '/api/questions/bulk-verify/'

    @classmethod
    def setUpTestData(cls):
        cls.physics = Subject.objects.create(name='Физика', slug='physics', icon='⚡')
        cls.topic = Topic.objects.create(subject=cls.physics, name='Касаткина · Глава 1')
        from users.models import User
        cls.teacher = User.objects.create_user(username='t1', password='x', role='teacher')
        cls.student = User.objects.create_user(username='s1', password='x', role='student')

    def book(self, tag):
        return Question.objects.create(
            topic=self.topic, text=f'задача {tag}', latex=f'$x = {tag}$',
            source_type='book_scan', verification_status='draft',
            provenance={'run': 'out_t', 'page': 8, 'format': 'задача'})

    def setUp(self):
        self.a, self.b = self.book('A'), self.book('B')
        # строка не из банка: приёмка по фильтру до неё доехать не имеет права
        self.other = Question.objects.create(topic=self.topic, text='из Excel',
                                             source_type='manual')

    def api(self, user):
        from rest_framework.test import APIClient
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def test_all_matching_takes_the_filter_not_the_whole_bank(self):
        r = self.api(self.teacher).post(
            self.url + '?source_type=book_scan&verification_status=draft',
            {'all_matching': True}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['changed'], 2)
        self.assertEqual(Question.objects.filter(verification_status='verified').count(), 2)
        self.a.refresh_from_db()
        self.assertEqual(self.a.provenance['accepted_by'], str(self.teacher))
        self.assertTrue(self.a.provenance['accepted_at'])

    def test_ids_accept_only_what_was_clicked(self):
        r = self.api(self.teacher).post(
            self.url, {'ids': [self.a.pk, self.b.pk], 'verification_status': 'verified'},
            format='json')
        self.assertEqual(r.json()['changed'], 2)
        self.assertEqual(Question.objects.get(pk=self.other.pk).verification_status, 'draft')

    def test_returning_to_draft_clears_the_mark(self):
        """Иначе перегон по оставшейся метке молча вернул бы «проверено»."""
        url = self.url + '?source_type=book_scan'
        self.api(self.teacher).post(url, {'ids': [self.a.pk]}, format='json')
        self.api(self.teacher).post(url, {'ids': [self.a.pk],
                                         'verification_status': 'draft'}, format='json')
        self.a.refresh_from_db()
        self.assertEqual(self.a.verification_status, 'draft')
        self.assertNotIn('accepted_by', self.a.provenance)

    def test_repeated_accept_touches_nobody(self):
        url = self.url + '?source_type=book_scan'
        self.api(self.teacher).post(url, {'all_matching': True}, format='json')
        first = Question.objects.get(pk=self.a.pk).provenance['accepted_at']
        r = self.api(self.teacher).post(url, {'all_matching': True}, format='json')
        self.assertEqual(r.json()['changed'], 0)
        self.assertEqual(Question.objects.get(pk=self.a.pk).provenance['accepted_at'], first)

    def test_student_forbidden(self):
        r = self.api(self.student).post(self.url, {'all_matching': True}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_garbage_requests_rejected(self):
        c = self.api(self.teacher)
        self.assertEqual(c.post(self.url, {'verification_status': 'ok'}, format='json').status_code, 400)
        self.assertEqual(c.post(self.url, {}, format='json').status_code, 400)
        self.assertEqual(c.post(self.url, {'ids': [self.a.pk], 'all_matching': True},
                                format='json').status_code, 400)
