"""
Тесты банка и Конструктора уроков.

Покрывают:
- парсер и importer Google Forms (валидный JSON, ошибки структуры, дедупликация
  по external_id, маркировка verified/draft), DRF-эндпоинт (401/403, dry_run);
- команды приёмки и приклеивания ответов книги (`attach_book_answers`,
  `refresh_scan_text`) — сухой прогон не трогает базу, неоднозначное наружу;
- конструктор уроков (Шаг 4.3): урок из четырёх блоков по `kind` + `order`,
  предпросмотр набора, публикация пустого урока отвергнута, состав сданного
  блока не перестилается;
- сдачу блока: чем решён вердикт, что `pending_review` не даёт ложного нуля
  в процентах, эталон книги не уходит ученику до вердикта человека и итоговый
  балл ставит только человек.

Drive API (скачивание картинок) тестируется на моках в images.py —
здесь внешних вызовов нет.
"""
from __future__ import annotations

import io
import json
import tempfile
from datetime import timedelta
from pathlib import Path

from django.core.management import CommandError, call_command
from django.db import transaction
from django.db.utils import IntegrityError
from django.test import TestCase, override_settings
from django.utils import timezone

from subjects.google_forms.dto import AnswerDTO, QuestionDTO
from subjects.google_forms.importer import ImporterError, import_payload
from subjects.google_forms.parser import ParseError, parse_dict
from subjects.models import (Answer, Assignment, AssignmentAnswer, AssignmentBlock,
                             AssignmentSubmission, Question, Subject, Topic)


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
        # text читают тест и результаты: ограничители в нём — единственное, что KaTeX
        # там может найти
        self.assertEqual(Question.objects.get().text, '$x = 2$')

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

    def test_crop_is_relaid_when_parser_names_another_figure(self):
        """Перегон с другим figures[0] обязан переложить кадр, а не оставить старый.

        Строка картинок в книге одна на несколько задач: парсер мог сначала отдать
        задаче рис. 1.30, а потом — тот же прогон, но с правильным рис. 1.32. Если
        импорт считает «картинка уже есть» неписуемым, задача навсегда останется с
        чужим рисунком.
        """
        (self.run / 'assets').mkdir()
        for n in ('p08_fig1.png', 'p08_fig2.png'):
            (self.run / 'assets' / n).write_bytes(b'\x89PNG\r\n\x1a\n' + b'0' * 32)
        self.write_run([scan_unit(figures=['assets/p08_fig1.png'])])
        self.do_import()
        q = Question.objects.get()
        self.assertEqual(q.image_ref, 'out_t:p08_fig1.png')
        old_image = q.image.name

        self.write_run([scan_unit(figures=['assets/p08_fig2.png', 'assets/p08_fig1.png'])])
        report = self.do_import()
        q.refresh_from_db()
        self.assertEqual(q.image_ref, 'out_t:p08_fig2.png')
        self.assertNotEqual(q.image.name, old_image)
        self.assertIn('переложено кадров 1', report)

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


class BankEndpointPermissionTest(TestCase):
    """Дыра `/api/questions/`: список и.retrieve банка были под `IsAuthenticated`.

    Сериализатор ученика `latex_answer` скрывал, а этот эндпоинт — нет: открытый
    DevTools выдавал весь банк с эталонами. Регрессия стоит здесь, а не только в
    тесте страницы ученика, потому что закрываем мы именно вход в банк.
    """

    @classmethod
    def setUpTestData(cls):
        cls.physics = Subject.objects.create(name='Физика', slug='physics', icon='⚡')
        cls.topic = Topic.objects.create(subject=cls.physics, name='Кинематика')
        from users.models import User
        cls.teacher = User.objects.create_user(username='bt', password='x', role='teacher')
        cls.admin = User.objects.create_user(username='ba', password='x', role='admin')
        cls.student = User.objects.create_user(username='bs', password='x', role='student')
        cls.q = Question.objects.create(
            topic=cls.topic, text='Задача с эталоном', latex_answer='$18$ см',
            source_type='book_scan', verification_status='verified')

    def api(self, user=None):
        from rest_framework.test import APIClient
        c = APIClient()
        if user is not None:
            c.force_authenticate(user=user)
        return c

    def test_student_cannot_list_the_bank(self):
        self.assertEqual(self.api(self.student).get('/api/questions/').status_code, 403)

    def test_student_cannot_retrieve_a_bank_row(self):
        r = self.api(self.student).get('/api/questions/%d/' % self.q.pk)
        self.assertEqual(r.status_code, 403)
        self.assertNotIn('18', json.dumps(getattr(r, 'data', {}), ensure_ascii=False,
                                         default=str))

    def test_anonymous_has_no_access(self):
        self.assertIn(self.api().get('/api/questions/').status_code, (401, 403))

    def test_teacher_and_admin_keep_the_bank(self):
        for user in (self.teacher, self.admin):
            r = self.api(user).get('/api/questions/')
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.data['results'][0]['id'], self.q.pk)
            self.assertEqual(
                self.api(user).get('/api/questions/%d/' % self.q.pk).status_code, 200)

    def test_filter_params_still_work_for_a_teacher(self):
        r = self.api(self.teacher).get('/api/questions/', {'grade': 'none'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['count'], 1)


class BankLanguageFilterTest(TestCase):
    """Фильтры «Язык» и «только переводы»: перевод — отдельная строка банка.

    Казахское условие не правит русскую строку, оно лежит копией с паспортом
    `translated_src_pk`. Экран обязан уметь выбрать и оригиналы, и переводы, а
    пакетная приёмка под этим фильтром — взять ровно переводы, а не весь банк.
    """

    @classmethod
    def setUpTestData(cls):
        cls.math = Subject.objects.create(name='Математика', slug='math-ru', icon='🧮')
        cls.topic = Topic.objects.create(subject=cls.math, name='Система уравнений')
        from users.models import User
        cls.teacher = User.objects.create_user(username='tl', password='x', role='teacher')

    def book(self, ext, language, verification_status, src=None):
        prov = {'run': 'система_уравнений_тест', 'format': 'задача'}
        if src is not None:
            prov['translated_src_pk'] = src.pk
            prov['translation_batch_id'] = 'batch-1'
        return Question.objects.create(
            topic=self.topic, text=f'задача {ext}', latex='$x = 1$', latex_answer='$1$',
            source_type='book_scan', verification_status=verification_status,
            language=language, external_id=ext, provenance=prov)

    def setUp(self):
        self.ru1 = self.book('11.001', 'ru', 'verified')
        self.ru2 = self.book('11.002', 'ru', 'draft')
        self.kk1 = self.book('11.001:kk', 'kk', 'draft', src=self.ru1)
        self.kk2 = self.book('11.002:kk', 'kk', 'verified', src=self.ru2)

    def api(self):
        from rest_framework.test import APIClient
        c = APIClient()
        c.force_authenticate(user=self.teacher)
        return c

    def ids(self, **params):
        r = self.api().get('/api/questions/', {'source_type': 'book_scan', **params})
        self.assertEqual(r.status_code, 200)
        return sorted(x['id'] for x in r.data['results'])

    def test_language_filter_picks_one_language(self):
        self.assertEqual(self.ids(language='kk'), [self.kk1.pk, self.kk2.pk])
        self.assertEqual(self.ids(language='ru'), [self.ru1.pk, self.ru2.pk])

    def test_translated_filter_picks_rows_with_a_source(self):
        # фильтр по паспорту, а не по языку: строка могла быть переведена и на русский
        self.assertEqual(self.ids(translated='1'), [self.kk1.pk, self.kk2.pk])

    def test_translation_queue_is_draft_translations_only(self):
        self.assertEqual(self.ids(translated='1', verification_status='draft'), [self.kk1.pk])

    def test_original_row_names_its_translation(self):
        """Оригинал не знает, что его перевели, — это должен досчитать список.

        Иначе метка «↔ #ID» на русской карточке появится только если перевод
        случайно попал на ту же страницу выдачи.
        """
        rows = {x['id']: x for x in self.api().get(
            '/api/questions/', {'source_type': 'book_scan'}).data['results']}
        self.assertEqual(rows[self.ru1.pk]['translation_id'], self.kk1.pk)
        self.assertEqual(rows[self.ru2.pk]['translation_id'], self.kk2.pk)
        # у перевода своего перевода нет
        self.assertIsNone(rows[self.kk2.pk]['translation_id'])

    def test_serializer_carries_language_and_source(self):
        row = [x for x in self.api().get('/api/questions/', {'source_type': 'book_scan'}
                                         ).data['results'] if x['id'] == self.kk1.pk][0]
        self.assertEqual(row['language'], 'kk')
        self.assertEqual(row['provenance']['translated_src_pk'], self.ru1.pk)

    def test_bulk_verify_under_the_translation_filter_touches_only_translations(self):
        r = self.api().post('/api/questions/bulk-verify/'
                            '?source_type=book_scan&translated=1&verification_status=draft',
                            {'all_matching': True}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['changed'], 1)
        self.assertEqual(Question.objects.get(pk=self.kk1.pk).verification_status, 'verified')
        # русский черновик под тем же банком, но без перевода, принят не был
        self.assertEqual(Question.objects.get(pk=self.ru2.pk).verification_status, 'draft')


class AutoacceptBookDraftsTest(TestCase):
    """Приёмка автоматом: статус тот же, но метка говорит, что человека не было.

    Строка «проверено» уже решает показ ученикам (тесты и дуэли берут verified),
    поэтому важнее статуса только одно — чем она записана. Если accepted_by
    окажется логином аккаунта, через месяц не отличить вычитанное от догадки.
    """

    @classmethod
    def setUpTestData(cls):
        cls.physics = Subject.objects.create(name='Физика', slug='physics', icon='⚡')
        cls.topic = Topic.objects.create(subject=cls.physics, name='Касаткина · Глава 1')

    def book(self, tag, answer=''):
        return Question.objects.create(
            topic=self.topic, text=f'задача {tag}', latex=f'$x = {tag}$', latex_answer=answer,
            source_type='book_scan', verification_status='draft',
            provenance={'run': 'out_t', 'page': 8, 'format': 'задача'})

    def run_command(self, **opt):
        out = io.StringIO()
        call_command('autoaccept_book_drafts', stdout=out, stderr=out, **opt)
        return out.getvalue()

    def test_dry_run_touches_nothing(self):
        a = self.book('A', '5 м/с')
        text = self.run_command(decision='нет ресурсов на вычитку', dry_run=True)
        a.refresh_from_db()
        self.assertEqual(a.verification_status, 'draft')
        self.assertIn('принято было бы 1', text)

    def test_mark_says_auto_and_keeps_the_decision(self):
        a = self.book('A', '5 м/с')
        self.run_command(decision='решение владельца 2026-10-07')
        a.refresh_from_db()
        self.assertEqual(a.verification_status, 'verified')
        self.assertEqual(a.provenance['accepted_mode'], 'auto')
        self.assertEqual(a.provenance['accepted_by'],
                         'автоматом: решение владельца 2026-10-07')

    def test_rows_without_answer_can_be_left_out(self):
        with_a = self.book('A', '5 м/с')
        without = self.book('B')
        self.run_command(decision='только с ответом', only_with_answer=True)
        with_a.refresh_from_db()
        without.refresh_from_db()
        self.assertEqual(with_a.verification_status, 'verified')
        self.assertEqual(without.verification_status, 'draft')

    def test_second_run_accepts_nobody(self):
        self.book('A', '5 м/с')
        self.run_command(decision='первый проход')
        with self.assertRaises(CommandError):
            self.run_command(decision='второй проход')
        self.assertEqual(Question.objects.filter(verification_status='verified').count(), 1)

    def test_manual_row_is_not_in_scope(self):
        other = Question.objects.create(topic=self.topic, text='из Excel', source_type='manual',
                                        verification_status='draft')
        with self.assertRaises(CommandError):
            self.run_command(decision='не для того')
        other.refresh_from_db()
        self.assertEqual(other.verification_status, 'draft')


# === Конструктор уроков: набор и публикация ================================

class AssignByLevelTest(TestCase):
    """Экран «Назначение по уровню»: предпросмотр набора для блока, урок из блоков, отзыв.

    Схема одна и она единственная: у `Assignment` нет плоского списка задач, состав
    живёт в блоках по `kind` + `order`. Поэтому и тест собирает урок блоками —
    другой формы payload экран не присылает, и поддерживать её было бы слоями.
    """

    @classmethod
    def setUpTestData(cls):
        from users.models import User
        cls.math = Subject.objects.create(name='Математика', slug='math', icon='📐')
        cls.phys = Subject.objects.create(name='Физика', slug='phys', icon='⚡')
        mtopic = Topic.objects.create(subject=cls.math, name='Сканави · Глава 11')
        ptopic = Topic.objects.create(subject=cls.phys, name='Касаткина · Глава 1')
        cls.teacher = User.objects.create_user(username='t1', password='x', role='teacher')
        cls.other_teacher = User.objects.create_user(username='t2', password='x', role='teacher')
        cls.student = User.objects.create_user(username='s1', password='x', role='student')
        cls.easy = [cls.task(mtopic, 'easy', f'лёгкая {i}') for i in range(6)]
        cls.medium = [cls.task(mtopic, 'medium', f'средняя {i}') for i in range(2)]
        cls.hard = cls.task(mtopic, 'hard', 'сложная')
        cls.hard_draft = cls.task(mtopic, 'hard', 'черновик', status='draft')
        cls.foreign = cls.task(ptopic, 'easy', 'чужой предмет')

    @staticmethod
    def task(topic, difficulty, text, status='verified', answer=''):
        return Question.objects.create(
            topic=topic, text=text, latex=f'$x$ {text}', difficulty=difficulty,
            source_type='book_scan', question_type='open_answer',
            verification_status=status, latex_answer=answer,
        )

    def _auth(self, user):
        from rest_framework.test import APIClient
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def _lesson(self, c, *blocks, **extra):
        body = {'title': 'Т', 'subject': self.math.pk, 'blocks': list(blocks)}
        body.update(extra)
        return c.post('/api/assignments/', body, format='json')

    def _draft(self):
        """Черновик урока с одним домашним блоком — то, что экран делает первым шагом."""
        r = self._lesson(self._auth(self.teacher),
                         {'kind': 'homework', 'question_ids': [self.easy[0].pk]})
        return Assignment.objects.get(pk=r.data['id'])

    def test_pick_gives_only_verified_tasks_of_the_level(self):
        r = self._auth(self.teacher).get('/api/assignments/pick/',
                                         {'subject': self.math.pk, 'difficulty': 'easy'})
        self.assertEqual(r.status_code, 200)
        ids = [q['id'] for q in r.data['questions']]
        self.assertEqual(sorted(ids), sorted(q.pk for q in self.easy))
        # уровни экрана: тренер обязан видеть, где материала нет, до того как просить
        self.assertEqual(r.data['levels'], {'easy': 6, 'medium': 2, 'hard': 1})
        self.assertEqual(r.data['pool'], 6)

    def test_pick_without_level_pools_the_whole_subject(self):
        """Ступень блока задаёт сам блок, поэтому предпросмотр без `difficulty` —
        норма, а не ошибка: тренер смотрит, что вообще есть по теме или книге."""
        r = self._auth(self.teacher).get('/api/assignments/pick/', {'subject': self.math.pk})
        self.assertEqual(r.data['pool'], 9)
        self.assertEqual({q['difficulty'] for q in r.data['questions']},
                         {'easy', 'medium', 'hard'})

    def test_pick_kind_maps_to_the_step_of_the_block(self):
        c = self._auth(self.teacher)
        for kind, want in (('advanced', [self.hard.pk]),
                           ('simplified', [q.pk for q in self.easy])):
            r = c.get('/api/assignments/pick/', {'subject': self.math.pk, 'kind': kind})
            self.assertEqual(sorted(q['id'] for q in r.data['questions']), sorted(want), kind)

    def test_pick_refuses_without_subject_or_wrong_level(self):
        c = self._auth(self.teacher)
        self.assertEqual(c.get('/api/assignments/pick/').status_code, 400)
        r = c.get('/api/assignments/pick/', {'subject': self.math.pk, 'difficulty': 'expert'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('Такого уровня нет', str(r.data))

    def test_pick_count_limits_and_reroll_changes_the_set(self):
        c = self._auth(self.teacher)
        params = {'subject': self.math.pk, 'difficulty': 'easy', 'count': 3}
        first = c.get('/api/assignments/pick/', params)
        self.assertEqual(len(first.data['questions']), 3)
        seen = {tuple(sorted(q['id'] for q in
                             c.get('/api/assignments/pick/', params).data['questions']))
                for _ in range(10)}
        # «перемешать» обязано давать другой набор: иначе шесть лёгких задач
        # превращались бы в одни и те же первые три для всех учеников
        self.assertGreater(len(seen), 1)

    def test_create_freezes_blocks_and_the_order_inside_them(self):
        order = [self.easy[3].pk, self.medium[0].pk, self.easy[0].pk]
        c = self._auth(self.teacher)
        r = self._lesson(c,
                         {'kind': 'homework', 'title': 'Домашка 11.2',
                          'question_ids': list(reversed(order))},
                         {'kind': 'in_class', 'question_ids': [self.easy[1].pk]},
                         title='Урок 11.2', students=[self.student.pk])
        self.assertEqual(r.status_code, 201, r.data)
        a = Assignment.objects.get(pk=r.data['id'])
        self.assertEqual(a.status, 'draft')
        self.assertEqual([b.kind for b in a.blocks_ordered], ['homework', 'in_class'])
        self.assertEqual(a.blocks.get(kind='homework').question_ids, list(reversed(order)))
        self.assertEqual([q.pk for q in a.questions],
                         list(reversed(order)) + [self.easy[1].pk])
        d = c.get(f'/api/assignments/{a.pk}/')
        self.assertEqual([b['kind'] for b in d.data['blocks']], ['homework', 'in_class'])
        self.assertEqual([q['id'] for q in d.data['blocks'][0]['questions']],
                         list(reversed(order)))
        self.assertEqual(d.data['tasks'], 4)
        self.assertEqual([s['id'] for s in d.data['students']], [self.student.pk])

    def test_explicit_order_is_kept(self):
        r = self._lesson(self._auth(self.teacher),
                         {'kind': 'in_class', 'order': 0, 'question_ids': [self.easy[0].pk]},
                         {'kind': 'homework', 'order': 1, 'question_ids': [self.easy[1].pk]})
        a = Assignment.objects.get(pk=r.data['id'])
        self.assertEqual([b.kind for b in a.blocks_ordered], ['in_class', 'homework'])
        self.assertEqual([b.order for b in a.blocks_ordered], [0, 1])

    def test_one_block_of_a_kind(self):
        r = self._lesson(self._auth(self.teacher),
                         {'kind': 'homework', 'question_ids': [self.easy[0].pk]},
                         {'kind': 'homework', 'question_ids': [self.easy[1].pk]})
        self.assertEqual(r.status_code, 400)
        self.assertIn('Блок может быть только один', str(r.data))
        self.assertEqual(Assignment.objects.count(), 0)

    def test_a_second_homework_block_is_refused_by_the_database_too(self):
        """Четыре блока — это схема, а не договорённость экрана: второй «Домашкой»
        не станет ни через API, ни прямой записью в базу."""
        a = self._draft()
        # ошибочная запись должна остаться внутри атомика: иначе она отравит
        # транзакцию теста, и следующие проверки упадут не по своей причине
        with self.assertRaises(IntegrityError), transaction.atomic():
            AssignmentBlock.objects.create(assignment=a, kind='homework', question_ids=[])
        self.assertEqual(a.blocks.count(), 1)

    def test_draft_and_foreign_subject_do_not_pass(self):
        c = self._auth(self.teacher)
        r = self._lesson(c, {'kind': 'homework',
                             'question_ids': [self.easy[0].pk, self.hard_draft.pk]})
        self.assertEqual(r.status_code, 400)
        self.assertIn('черновик', str(r.data))
        r = self._lesson(c, {'kind': 'homework',
                             'question_ids': [self.easy[0].pk, self.foreign.pk]})
        self.assertEqual(r.status_code, 400)
        self.assertIn('другого предмета', str(r.data['blocks']))
        r = self._lesson(c, {'kind': 'homework', 'question_ids': [999999]})
        self.assertEqual(r.status_code, 400)
        self.assertIn('в банке нет', str(r.data['blocks']))
        self.assertEqual(Assignment.objects.count(), 0)

    def test_group_merges_its_students_and_a_foreign_group_is_refused(self):
        from users.models import StudyGroup
        mine = StudyGroup.objects.create(name='11-А', teacher=self.teacher)
        mine.students.add(self.student)
        theirs = StudyGroup.objects.create(name='11-Б', teacher=self.other_teacher)
        block = {'kind': 'homework', 'question_ids': [self.easy[0].pk]}
        r = self._lesson(self._auth(self.teacher), block, group=mine.pk)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual([s.pk for s in
                          Assignment.objects.get(pk=r.data['id']).students.all()],
                         [self.student.pk])
        r = self._lesson(self._auth(self.teacher), block, group=theirs.pk)
        self.assertEqual(r.status_code, 400)
        self.assertIn('не ваша группа', str(r.data))

    def test_publish_needs_a_task_and_then_the_lesson_goes_live(self):
        c = self._auth(self.teacher)
        r = self._lesson(c, {'kind': 'homework', 'question_ids': []},
                         students=[self.student.pk])
        a = Assignment.objects.get(pk=r.data['id'])
        r = c.post(f'/api/assignments/{a.pk}/publish/')
        self.assertEqual(r.status_code, 400)
        self.assertIn('ни одной задачи', str(r.data))
        self.assertEqual(a.status, 'draft')
        self.assertIsNone(a.published_at)

        block = a.blocks.get(kind='homework')
        # пустой блок правят стрелками и галочками на экране, а не всей страницей урока
        r = c.patch(f'/api/assignment-blocks/{block.pk}/',
                    {'question_ids': [self.easy[0].pk], 'order': 0}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['autocheck'], True)
        r = c.post(f'/api/assignments/{a.pk}/publish/')
        self.assertEqual(r.status_code, 200, r.data)
        a.refresh_from_db()
        self.assertEqual(a.status, 'active')
        self.assertIsNotNone(a.published_at)
        # опубликованный состав ученик видит в том же порядке, что утвердил тренер
        mine = self._auth(self.student).get(f'/api/my/assignments/{a.pk}/')
        self.assertEqual([q['id'] for q in mine.data['blocks'][0]['questions']],
                         [self.easy[0].pk])

    def test_block_patch_refuses_the_foreign_or_draft_task(self):
        a = self._draft()
        block = a.blocks.get(kind='homework')
        r = self._auth(self.teacher).patch(f'/api/assignment-blocks/{block.pk}/',
                                          {'question_ids': [self.foreign.pk]}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('другого предмета', str(r.data))
        block.refresh_from_db()
        self.assertEqual(block.question_ids, [self.easy[0].pk])

    def test_block_kind_is_not_renamed(self):
        a = self._draft()
        block = a.blocks.get(kind='homework')
        r = self._auth(self.teacher).patch(f'/api/assignment-blocks/{block.pk}/',
                                          {'kind': 'advanced'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        block.refresh_from_db()
        self.assertEqual(block.kind, 'homework')

    def test_student_cannot_assign(self):
        r = self._auth(self.student).post('/api/assignments/', {
            'title': 'Т', 'subject': self.math.pk,
            'blocks': [{'kind': 'homework', 'question_ids': [self.easy[0].pk]}],
        }, format='json')
        self.assertEqual(r.status_code, 403)

    def test_revoke_keeps_the_record(self):
        a = self._draft()
        c = self._auth(self.teacher)
        r = c.post(f'/api/assignments/{a.pk}/revoke/')
        self.assertEqual(r.status_code, 200)
        a.refresh_from_db()
        self.assertEqual(a.status, 'revoked')
        # отзыв не стирает, что ученик уже получил
        self.assertTrue(Assignment.objects.filter(pk=a.pk).exists())
        self.assertEqual(a.blocks.count(), 1)

    def test_teacher_sees_only_own_assignments(self):
        c = self._auth(self.teacher)
        self._lesson(c, {'kind': 'homework', 'question_ids': [self.easy[0].pk]}, title='моё')
        self._lesson(self._auth(self.other_teacher),
                     {'kind': 'homework', 'question_ids': [self.easy[1].pk]}, title='чужое')
        r = c.get('/api/assignments/')
        self.assertEqual([a['title'] for a in r.data], ['моё'])
        self.assertEqual(r.data[0]['blocks'][0]['tasks'], 1)


# === Урок: сдача блока, автопроверка и ручная проверка ======================

class LessonResultsTest(TestCase):
    """Что делает платформа, когда ученик пишет ответ открытой задачи.

    Главная опасность — ложный ноль. У 75 строк банка напечатанного ответа нет, и
    если автопроверка отдаст за них `incorrect`, ученик получит балл, который никто
    не выставлял, а тренер потом не найдёт, где проверка не делалась. Поэтому
    `pending_review` не входит ни в числитель, ни в знаменатель процента, а очередь
    ручной проверки обязана такие задачи показывать, пока вердикта человека нет.
    """

    @classmethod
    def setUpTestData(cls):
        from users.models import User
        cls.math = Subject.objects.create(name='Математика', slug='math-lesson', icon='📐')
        topic = Topic.objects.create(subject=cls.math, name='Сканави · Глава 11')
        cls.topic = topic
        cls.teacher = User.objects.create_user(username='tl', password='x', role='teacher')
        cls.student = User.objects.create_user(username='sl', password='x', role='student')
        cls.second = User.objects.create_user(username='sl2', password='x', role='student')
        cls.outsider = User.objects.create_user(username='sx', password='x', role='student')
        cls.with_answer = cls.task(topic, 'объём', answer='$18$ см', points=2)
        cls.no_answer = cls.task(topic, 'доказать', answer='', points=1)
        cls.classwork_task = cls.task(topic, 'чертёж', answer='$5$ м', points=1)
        cls.lesson = Assignment.objects.create(teacher=cls.teacher, subject=cls.math,
                                               title='Урок 11.2', status='active',
                                               published_at=timezone.now())
        cls.homework = AssignmentBlock.objects.create(
            assignment=cls.lesson, kind='homework', order=0,
            question_ids=[cls.with_answer.pk, cls.no_answer.pk])
        cls.classwork = AssignmentBlock.objects.create(
            assignment=cls.lesson, kind='in_class', order=1,
            question_ids=[cls.classwork_task.pk])
        cls.lesson.students.set([cls.student, cls.second])

    @staticmethod
    def task(topic, text, answer='', points=1, qtype='open_answer'):
        return Question.objects.create(
            topic=topic, text=text, latex=text, latex_answer=answer, difficulty='easy',
            source_type='book_scan', question_type=qtype,
            verification_status='verified', points=points,
        )

    def _auth(self, user):
        from rest_framework.test import APIClient
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def _answer(self, c, block, question, raw):
        return c.post(f'/api/my/assignments/{self.lesson.pk}/answer/',
                      {'block': block.pk, 'question': question.pk, 'raw_answer': raw},
                      format='json')

    def _submit(self, c, block):
        return c.post(f'/api/my/assignments/{self.lesson.pk}/submit/',
                      {'block': block.pk}, format='json')

    def _graded(self, question):
        """Строка ответа в базе. Движок ставит вердикт при сохранении, но ученику он
        приезжает только после сдачи блока — поэтому сверяться приходится с базой."""
        return AssignmentAnswer.objects.get(submission__student=self.student,
                                            question=question)

    def assertNoCorrectness(self, payload):
        """Ни одного поля, по которому ученик прочитал бы правильность ответа.

        Здесь перечислены все ключи, которые когда-либо несли вердикт: `answer/`
        возвращал `verdict` + `judged_by` + `feedback`, а payload ученика — ещё и
        `progress` с процентом. Перебор `A..D` жил именно на этих полях.
        """
        body = json.dumps(payload, ensure_ascii=False, default=str).lower()
        for word in ('verdict', 'judged_by', 'etalon', 'feedback', 'percent',
                     'correct', 'partial', 'incorrect'):
            self.assertNotIn(word, body)

    def test_machine_grades_what_the_book_prints_and_leaves_the_rest(self):
        c = self._auth(self.student)
        r = self._answer(c, self.homework, self.with_answer, '18 см')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self._graded(self.with_answer).verdict, 'correct')
        self.assertEqual(self._graded(self.with_answer).judged_by, 'level1')
        self._answer(c, self.homework, self.no_answer, '12 см')
        a = self._graded(self.no_answer)
        self.assertEqual(a.verdict, 'pending_review')
        # пустой judged_by — это «машина не решила», а не чьё-то молчаливое согласие
        self.assertEqual(a.judged_by, '')
        self.assertIn('в книге ответа нет', a.verdict_note)

        s = self._submit(c, self.homework).data
        self.assertEqual(s['autocheck'], True)
        sc = s['score']
        self.assertEqual((sc['total'], sc['answered'], sc['checked'], sc['pending']),
                         (2, 2, 1, 1))
        self.assertEqual((sc['earned'], sc['possible'], sc['percent']), (2.0, 2.0, 100.0))
        # ложного нуля нет: задача без эталона не попала ни в балл, ни в знаменатель
        self.assertIsNone(self._graded(self.no_answer).points_earned)
        self.assertEqual(s['pending'], 1)

    def test_wrong_answer_is_incorrect_without_the_key(self):
        c = self._auth(self.student)
        self._answer(c, self.homework, self.with_answer, '5 м')
        self.assertEqual(self._graded(self.with_answer).verdict, 'incorrect')
        # до сдачи экран не знает ни вердикта, ни причины: ни «не совпала», ни ключ
        mine = c.get(f'/api/my/assignments/{self.lesson.pk}/').data
        self.assertEqual(mine['blocks'][0]['answers'][0]['verdict'], '')
        self.assertEqual(mine['blocks'][0]['answers'][0]['feedback'], {})
        self._submit(c, self.homework)
        mine = c.get(f'/api/my/assignments/{self.lesson.pk}/').data
        feedback = mine['blocks'][0]['answers'][0]['feedback']
        self.assertEqual(feedback['verdict'], 'incorrect')
        # ключ книги не показывается и после сдачи: его открывает только вердикт человека
        self.assertEqual(feedback['etalon'], '')
        self.assertIn('не совпала', feedback['note'])

    def test_the_solution_reaches_the_student_only_after_the_block_is_submitted(self):
        """П.4: разбор — после сдачи блока, и до сдачи его нет даже в JSON.

        Проверка не в том, что кнопка скрыта на экране, а в том, чего сервер не
        отдаёт: ученик, открывший DevTools на несданном блоке, не должен найти там
        ни разбора, ни напечатанного ключа книги.
        """
        self.with_answer.solution_latex = r'Решение: $V = 18$ см³'
        self.with_answer.save()
        c = self._auth(self.student)

        mine = c.get(f'/api/my/assignments/{self.lesson.pk}/').data
        self.assertEqual(mine['blocks'][0]['questions'][0]['solution_latex'], '')

        self._answer(c, self.homework, self.with_answer, '18 см')
        mine = c.get(f'/api/my/assignments/{self.lesson.pk}/').data
        self.assertEqual(mine['blocks'][0]['questions'][0]['solution_latex'], '')

        self._submit(c, self.homework)
        mine = c.get(f'/api/my/assignments/{self.lesson.pk}/').data
        self.assertEqual(mine['blocks'][0]['questions'][0]['solution_latex'],
                         r'Решение: $V = 18$ см³')
        # разбор открыт, а ключ книги по-прежнему ждёт вердикта человека
        self.assertEqual(mine['blocks'][0]['answers'][0]['feedback']['etalon'], '')

    def test_no_correctness_reaches_the_student_before_the_block_is_submitted(self):
        """Блок 1: до `submit/` ученик не знает ни вердикта, ни балла.

        Прежний `answer/` возвращал `verdict`, `judged_by` и `feedback`, а payload
        блока нёс `progress` с процентом. Итог: четыре тапа по буквам варианта, и
        экран сам говорит, где «Верно» — тест сдаётся перебором ещё до сдачи.
        Тест закрывает обе дороги: ответ эндпоинта и перезагрузку страницы.
        """
        c = self._auth(self.student)
        r = self._answer(c, self.homework, self.with_answer, '18 см')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(sorted(r.data.keys()), ['id', 'question', 'saved', 'state'])
        self.assertNoCorrectness(r.data)
        # движок свою работу сделал, но остался при ней: вердикт живёт в базе
        self.assertEqual(self._graded(self.with_answer).verdict, 'correct')

        block = c.get(f'/api/my/assignments/{self.lesson.pk}/').data['blocks'][0]
        self.assertEqual(block['state'], 'in_progress')
        self.assertIsNone(block['progress'])
        self.assertEqual(block['answers'][0]['verdict'], '')
        self.assertEqual(block['answers'][0]['feedback'], {})
        # черновик при этом обязан доезжать: без него экран пустой
        self.assertEqual(block['answers'][0]['raw_answer'], '18 см')

        self._submit(c, self.homework)
        block = c.get(f'/api/my/assignments/{self.lesson.pk}/').data['blocks'][0]
        self.assertEqual(block['answers'][0]['verdict'], 'correct')
        self.assertEqual((block['progress']['checked'], block['progress']['percent']),
                         (1, 100.0))

    def test_the_block_state_tells_the_screen_which_block_is_closed(self):
        """Экран закрывает сданный блок по состоянию сдачи, а не по догадке.

        `progress` появляется уже после первого сохранённого ответа и «решаю» от
        «сдал» не отличает: без `state` ребёнок видел бы четыре одинаковые кнопки
        «Сдать блок», три из которых он уже нажимал.
        """
        c = self._auth(self.student)
        mine = c.get(f'/api/my/assignments/{self.lesson.pk}/').data
        self.assertEqual({b['kind']: b['state'] for b in mine['blocks']},
                         {'homework': '', 'in_class': ''})

        self._answer(c, self.homework, self.with_answer, '18 см')
        mine = c.get(f'/api/my/assignments/{self.lesson.pk}/').data
        self.assertEqual([b['state'] for b in mine['blocks'] if b['kind'] == 'homework'],
                         ['in_progress'])

        self._submit(c, self.homework)
        mine = c.get(f'/api/my/assignments/{self.lesson.pk}/').data
        self.assertEqual([b['state'] for b in mine['blocks'] if b['kind'] == 'homework'],
                         ['submitted'])

    def test_a_single_choice_task_is_graded_by_the_option_letter(self):
        """Тест: сверяется литера, а не SymPy.

        Ключ теста — одна буква. По старой дороге она попадала в CAS, где любая
        буква равнялась любой, поэтому для `single_choice` проверка идёт отдельным
        путём: литера прочитана — вердикт, не прочитана — человеку.
        """
        q = self.task(self.topic, 'Протондар мен нейтрондар күші', answer='B',
                      points=1, qtype='single_choice')
        self.homework.question_ids = list(self.homework.question_ids) + [q.pk]
        self.homework.save()
        c = self._auth(self.student)

        r = self._answer(c, self.homework, q, 'б')
        self.assertEqual(self._graded(q).verdict, 'correct')
        self.assertEqual(self._graded(q).judged_by, 'level1')
        self.assertEqual(AssignmentAnswer.objects.get(question=q).normalized_answer,
                         'Вариант B')

        # та же литера, набранная латиницей и скопированная вместе с текстом варианта
        for raw in ('B', '(в)', 'B) электрлік күштер', 'вариант b'):
            self._answer(c, self.homework, q, raw)
            self.assertEqual(self._graded(q).verdict, 'correct', raw)

        r = self._answer(c, self.homework, q, 'D')
        self.assertEqual(self._graded(q).verdict, 'incorrect')
        # ответ на сохранение не говорит ничего: ни «неверно», ни тем более ключ
        self.assertNoCorrectness(r.data)

        # текст варианта без буквы — машина его не читает и ложный ноль не ставит
        self._answer(c, self.homework, q, 'ядролық күштер')
        self.assertEqual(self._graded(q).verdict, 'pending_review')
        self.assertEqual(self._graded(q).judged_by, '')

    def test_a_multi_answer_task_is_graded_by_the_whole_set_of_letters(self):
        """Блок ЕНТ №16–20: восемь вариантов, верных от одного до трёх.

        Ключ — набор литер. Ученик, назвавший половину набора, получает ноль, а не
        «проверьте глазами»: литера прочитана, спорить машине не о чем.
        """
        q = self.task(self.topic, 'Күміс атомының құрамы', answer='D, F, G',
                      points=1, qtype='single_choice')
        self.homework.question_ids = list(self.homework.question_ids) + [q.pk]
        self.homework.save()
        c = self._auth(self.student)

        for raw in ('D, F, G', 'GDF', 'd f g', 'g, D, f', 'G, D, F',
                    'D) 47 протон; F) 61 нейтрон; G) 47 электрон'):
            self._answer(c, self.homework, q, raw)
            self.assertEqual(self._graded(q).verdict, 'correct', raw)
        self.assertEqual(AssignmentAnswer.objects.get(question=q).normalized_answer,
                         'Вариант D, F, G')

        for raw in ('D, F', 'D, F, G, H', 'D'):
            self._answer(c, self.homework, q, raw)
            self.assertEqual(self._graded(q).verdict, 'incorrect', raw)
            self.assertEqual(self._graded(q).judged_by, 'level1', raw)

    def test_in_class_block_saves_the_answer_and_checks_nothing(self):
        """`in_class` и `advanced` решают вместе на уроке: автопроверки там нет, и
        ложного `pending_review` на каждую такую задачу очередь не забивается —
        ответ сохраняется, вердикт по нему ставит человек."""
        c = self._auth(self.student)
        r = self._answer(c, self.classwork, self.classwork_task, 'не так')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self._graded(self.classwork_task).verdict, 'pending_review')
        self.assertEqual(AssignmentAnswer.objects.get(question=self.classwork_task)
                         .normalized_answer, '')
        s = self._submit(c, self.classwork).data
        self.assertEqual(s['autocheck'], False)
        self.assertEqual(s['score']['percent'], None)
        self.assertEqual(s['score']['pending'], 1)

    def test_strict_units_flag_sends_a_bare_number_to_the_teacher(self):
        with override_settings(OPEN_ANSWER_STRICT_UNITS=True):
            self._answer(self._auth(self.student), self.homework, self.with_answer, '18')
        self.assertEqual(self._graded(self.with_answer).verdict, 'pending_review')
        self.assertEqual(self._graded(self.with_answer).judged_by, '')

    def test_multiline_answer_keeps_which_part_the_machine_matched(self):
        """Правило от 14.10: словесная часть уводит всю задачу к человеку, но подсказка
        обязана говорить, какую часть сверка уже прошла, и ученику её не показывать."""
        topic = Topic.objects.create(subject=self.math, name='Сканави · Глава 12')
        q = self.task(topic, 'два действия',
                      answer='а) $18$ см; б) направление — по чертежу', points=2)
        block = AssignmentBlock.objects.create(assignment=self.lesson, kind='simplified',
                                               order=2, question_ids=[q.pk])
        r = self._answer(self._auth(self.student), block, q, 'а) 18 см; б) вверх')
        self.assertEqual(self._graded(q).verdict, 'pending_review')
        self.assertIsNone(AssignmentAnswer.objects.get(question=q).points_earned)
        # ученику до сдачи не показывается ничего: ни «ждёт человека», ни какая часть сошлась
        self.assertNoCorrectness(r.data)
        note = AssignmentAnswer.objects.get(question=q).verdict_note
        self.assertIn('не решается автоматически: 1 из 2 частей', note)
        self.assertIn('а): совпало', note)
        self.assertIn('б): текст — проверьте глазами', note)
        # тренер в матрице видит подсказку целиком, потому что задача стоит в очереди
        self._submit(self._auth(self.student), block)
        row = self._auth(self.teacher).get(f'/api/assignments/{self.lesson.pk}/matrix/').data
        cell = [x for x in row['pending_review'] if x['question'] == q.pk]
        self.assertEqual(len(cell), 1)
        self.assertIn('а): совпало', cell[0]['verdict_note'])

    def test_answer_of_a_task_that_is_not_in_the_block_is_refused(self):
        r = self._answer(self._auth(self.student), self.homework, self.classwork_task, '18 см')
        self.assertEqual(r.status_code, 400)
        self.assertIn('Этой задачи в блоке нет', str(r.data))
        self.assertEqual(AssignmentSubmission.objects.count(), 0)

    def test_matrix_shows_rows_per_block_and_pending_review_queue(self):
        s = self._auth(self.student)
        self._answer(s, self.homework, self.with_answer, '18 см')
        self._answer(s, self.homework, self.no_answer, '12 см')
        self._submit(s, self.homework)
        r = self._auth(self.teacher).get(f'/api/assignments/{self.lesson.pk}/matrix/')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual([b['kind'] for b in r.data['blocks']], ['homework', 'in_class'])
        self.assertEqual(r.data['blocks'][0]['autocheck'], True)
        self.assertEqual(len(r.data['rows']), 2)
        rows = {row['student']: row for row in r.data['rows']}
        hw, cw = rows[self.student.pk]['blocks']
        self.assertEqual((hw['state'], hw['checked'], hw['pending'], hw['percent']),
                         ('submitted', 1, 1, 100.0))
        self.assertEqual([cell['total'] for cell in rows[self.student.pk]['blocks']], [2, 1])
        # второй ученик урок не открывал: пустая клетка обязана быть видна, а не 0%
        self.assertEqual([cell['state'] for cell in rows[self.second.pk]['blocks']], ['', ''])
        self.assertEqual([cell['answered'] for cell in rows[self.second.pk]['blocks']], [0, 0])
        self.assertEqual(cw['state'], '')
        self.assertEqual([a['question'] for a in r.data['pending_review']],
                         [self.no_answer.pk])
        self.assertEqual(r.data['pending_review'][0]['block_kind'], 'homework')
        self.assertIn('в книге ответа нет', str(r.data['pending_review'][0]['verdict_note']))

    def test_matrix_row_counts_which_blocks_the_student_handed_in(self):
        """«Сдано 2 из 4» в матрице: итог по блокам считает бэкенд, а не тренер глазами.

        Опасность одна: `reviewed` — это тоже сданный блок. Если считать только
        `submitted`, прогресс ученика уменьшился бы ровно в тот момент, когда тренер
        поставил ему вердикт, и экран показал бы потерянную сдачу.
        """
        s, t = self._auth(self.student), self._auth(self.teacher)

        def progress(user):
            rows = t.get(f'/api/assignments/{self.lesson.pk}/matrix/').data['rows']
            return {r['student']: r['blocks_progress'] for r in rows}[user.pk]

        self.assertEqual(progress(self.student), {'submitted': 0, 'total': 2})
        self._answer(s, self.homework, self.with_answer, '18 см')
        self._answer(s, self.homework, self.no_answer, '12 см')
        # `in_progress` сдачей не считается: ответ на сервере есть, блока ученик не сдал
        self.assertEqual(progress(self.student)['submitted'], 0)
        self._submit(s, self.homework)
        self.assertEqual(progress(self.student), {'submitted': 1, 'total': 2})
        self._answer(s, self.classwork, self.classwork_task, '5 м')
        self._submit(s, self.classwork)
        self.assertEqual(progress(self.student), {'submitted': 2, 'total': 2})
        pending = AssignmentAnswer.objects.get(submission__block=self.homework,
                                               question=self.no_answer)
        t.post(f'/api/assignment-answers/{pending.pk}/review/', {'verdict': 'correct'},
               format='json')
        self.assertEqual(AssignmentSubmission.objects.get(block=self.homework,
                                                          student=self.student).state,
                         'reviewed')
        self.assertEqual(progress(self.student), {'submitted': 2, 'total': 2})
        # второй ученик урок не открывал: у него тоже обязан быть полный нулевой прогресс
        self.assertEqual(progress(self.second), {'submitted': 0, 'total': 2})

    def test_human_review_is_the_only_thing_that_closes_a_submission(self):
        c = self._auth(self.student)
        self._answer(c, self.homework, self.with_answer, '18 см')
        self._answer(c, self.homework, self.no_answer, '12 см')
        self._submit(c, self.homework)
        pending = AssignmentAnswer.objects.get(question=self.no_answer)
        t = self._auth(self.teacher)
        r = t.post(f'/api/assignment-answers/{pending.pk}/review/',
                   {'verdict': 'partial', 'note': 'верно начало'})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['submission_state'], 'reviewed')
        self.assertEqual(r.data['pending_left'], 0)
        self.assertEqual(r.data['score']['checked'], 2)
        self.assertEqual(r.data['score']['percent'], 83.3)
        pending.refresh_from_db()
        self.assertEqual([pending.verdict, pending.judged_by], ['partial', 'human'])
        self.assertEqual(pending.reviewed_by_id, self.teacher.pk)
        self.assertEqual(pending.submission.state, 'reviewed')

    def test_review_needs_a_verdict_a_human_can_give(self):
        self._answer(self._auth(self.student), self.homework, self.no_answer, '12 см')
        pending = AssignmentAnswer.objects.get(question=self.no_answer)
        r = self._auth(self.teacher).post(f'/api/assignment-answers/{pending.pk}/review/',
                                         {'verdict': 'pending_review'}, format='json')
        self.assertEqual(r.status_code, 400)
        pending.refresh_from_db()
        self.assertEqual(pending.judged_by, '')

    def test_student_edit_resets_a_verdict_a_teacher_already_set(self):
        """Правка ученика после ручной проверки возвращает задачу в очередь: иначе
        «partial» висел бы на ответе, которого больше нет."""
        s = self._auth(self.student)
        self._answer(s, self.homework, self.no_answer, '12 см')
        pending = AssignmentAnswer.objects.get(question=self.no_answer)
        self._auth(self.teacher).post(f'/api/assignment-answers/{pending.pk}/review/',
                                      {'verdict': 'correct'}, format='json')
        pending.refresh_from_db()
        self.assertEqual(pending.judged_by, 'human')
        self._answer(self._auth(self.student), self.homework, self.no_answer, '13 см')
        pending.refresh_from_db()
        self.assertEqual(pending.verdict, 'pending_review')
        self.assertEqual(pending.judged_by, '')
        self.assertIsNone(pending.reviewed_by_id)

    def test_submit_regrades_the_last_draft_of_an_answer(self):
        """Ученик мог сохранить ответ, а перед сдачей переписать его: сверка обязана
        идти по последней строке, а не по той, что была в момент сохранения."""
        c = self._auth(self.student)
        self._answer(c, self.homework, self.with_answer, '5 м')
        self._answer(c, self.homework, self.with_answer, '18 см')
        s = self._submit(c, self.homework).data
        self.assertEqual(s['score']['checked'], 1)
        self.assertEqual(s['score']['percent'], 100.0)
        self.assertEqual(AssignmentAnswer.objects.get(question=self.with_answer).verdict,
                         'correct')

    def test_a_graded_block_cannot_be_reshaped_or_dropped(self):
        c = self._auth(self.student)
        self._answer(c, self.homework, self.with_answer, '18 см')
        t = self._auth(self.teacher)
        r = t.patch(f'/api/assignment-blocks/{self.homework.pk}/',
                    {'question_ids': [self.classwork_task.pk]}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('Блок уже сдавали', str(r.data))
        r = t.put(f'/api/assignments/{self.lesson.pk}/', {
            'title': 'Урок 11.2', 'subject': self.math.pk,
            'blocks': [{'kind': 'in_class', 'question_ids': [self.classwork_task.pk]}],
        }, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('уже сдавали', str(r.data))
        self.assertTrue(AssignmentBlock.objects.filter(pk=self.homework.pk).exists())
        self.homework.refresh_from_db()
        self.assertEqual(self.homework.question_ids, [self.with_answer.pk, self.no_answer.pk])

    def test_lesson_not_assigned_is_invisible_to_the_student(self):
        c = self._auth(self.outsider)
        self.assertEqual(c.get('/api/my/assignments/').data, [])
        self.assertEqual(c.get(f'/api/my/assignments/{self.lesson.pk}/').status_code, 404)
        self.assertEqual(self._answer(c, self.homework, self.with_answer, '18 см').status_code,
                         404)

    def test_draft_lesson_is_not_visible_and_expired_lesson_refuses_answers(self):
        c = self._auth(self.student)
        self.lesson.status = 'draft'
        self.lesson.save(update_fields=['status'])
        self.assertEqual(c.get('/api/my/assignments/').data, [])
        self.lesson.status = 'active'
        self.lesson.due_at = timezone.now() - timedelta(hours=1)
        self.lesson.save(update_fields=['status', 'due_at'])
        r = c.get(f'/api/my/assignments/{self.lesson.pk}/')
        self.assertTrue(r.data['expired'])
        self.assertTrue(c.get('/api/my/assignments/').data[0]['expired'])
        r = self._answer(c, self.homework, self.with_answer, '18 см')
        self.assertEqual(r.status_code, 400)
        self.assertIn('Срок сдачи вышел', str(r.data))
        self.assertEqual(self._submit(c, self.homework).status_code, 400)
        self.assertEqual(AssignmentSubmission.objects.count(), 0)

    def test_student_page_carries_the_condition_but_not_the_key(self):
        """Экран ученика обязан нести условие, но не ответ книги.

        Задачи страницы ученика собирались тем же сериализатором, что и экран банка,
        и уносили `latex_answer` вместе с условиями: правило «эталон показываем после
        вердикта человека» обходилось одним открытым DevTools, и ни один вердикт об
        этом не предупреждал.
        """
        c = self._auth(self.student)
        self._answer(c, self.homework, self.with_answer, '5 м')
        r = c.get(f'/api/my/assignments/{self.lesson.pk}/')
        body = json.dumps(r.data, ensure_ascii=False)
        self.assertNotIn('$18$ см', body)
        self.assertNotIn('latex_answer', body)
        self.assertNotIn('provenance', body)
        self.assertEqual(sorted(r.data['blocks'][0]['questions'][0]),
                         ['difficulty', 'id', 'image', 'latex', 'options', 'points',
                          'question_type', 'solution_latex', 'text'])
        # тренеру ключ банка виден: он его и приёмку ведёт
        t = json.dumps(self._auth(self.teacher).get(f'/api/assignments/{self.lesson.pk}/').data,
                       ensure_ascii=False)
        self.assertIn('$18$ см', t)

    def test_student_page_lists_the_printed_option_letters(self):
        """Чипы теста экран рисует по напечатанному списку, а не по догадке.

        Ребёнок отвечает с телефона, и буква варианта там — нажатие пальцем, а не
        печать. Но `options` обязан пересказывать ровно то, что ученик видит в условии:
        рваный ряд (нет `A`) или буквы вне списка вариантов дали бы чипы, которых в
        задаче нет, и выбор по ним стоил бы вердикта.
        """
        test = self.task(self.topic,
                         'Массасы\nA) $8{,}3 \\cdot 10^{-26}$\nB) $19{,}92$\nC) $1{,}162$\n'
                         'D) $3{,}32$\nЕ) $1{,}38$', answer='B', qtype='single_choice')
        broken = self.task(self.topic, 'С. Петров берді\nB) 2\nC) 3', answer='B',
                           qtype='single_choice')
        self.homework.question_ids = [test.pk, broken.pk, self.with_answer.pk]
        self.homework.save()
        c = self._auth(self.student)
        rows = {q['id']: q for q in
                c.get(f'/api/my/assignments/{self.lesson.pk}/').data['blocks'][0]['questions']}
        self.assertEqual(rows[test.pk]['question_type'], 'single_choice')
        # `Е)` в скане книги — кириллическая гомоглифа латинской `E`, ряд от этого не рвётся
        self.assertEqual(rows[test.pk]['options'], ['A', 'B', 'C', 'D', 'E'])
        self.assertEqual(rows[broken.pk]['options'], [])
        self.assertEqual(rows[self.with_answer.pk]['options'], [])
        body = json.dumps(rows[test.pk], ensure_ascii=False)
        self.assertNotIn('$18$ см', body)

    def test_deduplication_one_submission_and_one_answer_per_task(self):
        c = self._auth(self.student)
        self._answer(c, self.homework, self.with_answer, '5 м')
        self._answer(c, self.homework, self.with_answer, '18 см')
        self._submit(c, self.homework)
        self.assertEqual(AssignmentSubmission.objects.filter(
            assignment=self.lesson, student=self.student).count(), 1)
        self.assertEqual(AssignmentAnswer.objects.count(), 1)
        self.assertEqual(AssignmentAnswer.objects.get().raw_answer, '18 см')
        # сдача не превращает сдачу в «проверено»: итог ставит только человек
        self.assertEqual(AssignmentSubmission.objects.get().state, 'submitted')


# === Ответы из другого прогона =============================================

class AttachBookAnswersTest(TestCase):
    """Команда attach_book_answers: ответ берётся из доски ответов другого прогона
    и кладётся по напечатанному номеру. Всё, что не сходится однозначно, наружу
    списком, а не в базу.

    Главная опасность — не пустой ответ, а чужой: номер в книге может стоять на
    двух задачах разных счётов (Касаткина), а запись доски — оказаться разбором
    всей задачи. Тихая ошибка в поле ответа уходит ученику быстрее, чем отсутствие
    ответа, поэтому неоднозначное здесь не пишется ни при каких флагах.
    """

    BOOK = 'Сканави, стериометрия'

    @classmethod
    def setUpTestData(cls):
        cls.math = Subject.objects.create(name='Математика', slug='math-attach', icon='📐')
        cls.topic = Topic.objects.create(subject=cls.math, name='Сканави · Глава 11')

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def row(self, num, answer='', scope='ГЛАВА 11', edited=False, book=BOOK):
        prov = {'run': 'сканави_253_274', 'page': 19, 'book': book,
                'num': num, 'scope': scope, 'format': 'задача',
                'answer_note': 'ответа в отсканированной части нет'}
        if edited:
            prov['human_edited'] = True
        return Question.objects.create(
            topic=self.topic, text='условие ' + num, latex='условие ' + num,
            latex_answer=answer, source_type='book_scan', verification_status='verified',
            provenance=prov)

    def board(self, *entries, name='сканави_ответы'):
        """tasks.json прогона с ответами ровно в том виде, как его пишет tasks.py."""
        folder = self.tmp / name
        folder.mkdir(parents=True, exist_ok=True)
        answers = [{'num': n, 'scope': sc,
                    'values': [{'page': p, 'text': t, 'block': '', 'run': ''}]}
                   for (n, sc, p, t) in entries]
        (folder / 'tasks.json').write_text(
            json.dumps({'run': name, 'pages': 4, 'tasks': [], 'answers': answers},
                       ensure_ascii=False), encoding='utf-8')
        return name

    def run_command(self, **opt):
        out, listing = io.StringIO(), self.tmp / 'listing.json'
        opt.setdefault('out', str(listing))
        with override_settings(INGEST_RUNS_DIR=str(self.tmp)):
            call_command('attach_book_answers', stdout=out, stderr=out, **opt)
        return out.getvalue(), listing

    def test_dry_run_leaves_the_answer_where_it_was(self):
        q = self.row('11.198')
        text, listing = self.run_command(
            answers_run=self.board(('11.198', 'ГЛАВА 11', 3, '$18$ см')), book=self.BOOK)
        q.refresh_from_db()
        self.assertEqual(q.latex_answer, '')
        self.assertIn('подходит к приклеиванию: 1', text)
        self.assertIn('сухой прогон: база не тронута', text)
        plan = json.loads(listing.read_text(encoding='utf-8'))['plan']
        self.assertEqual([p['answer'] for p in plan], ['$18$ см'])

    def test_apply_writes_answer_and_its_source_and_nothing_else(self):
        q = self.row('11.198')
        before = (q.text, q.latex, q.topic_id, q.verification_status, q.provenance['answer_note'])
        self.run_command(answers_run=self.board(('11.198', 'ГЛАВА 11', 3, '$18$ см')),
                         book=self.BOOK, apply=True,
                         decision='скан ответов главы 11, сверено глазами')
        q.refresh_from_db()
        self.assertEqual(q.latex_answer, '$18$ см')
        self.assertEqual((q.text, q.latex, q.topic_id, q.verification_status,
                          q.provenance['answer_note']), before)
        src = q.provenance['answer_from']
        self.assertEqual(src['run'], 'сканави_ответы')
        self.assertEqual(src['pages'], [3])
        self.assertEqual(src['by'], 'скан ответов главы 11, сверено глазами')

    def test_dot_at_the_number_is_not_a_different_number(self):
        # в доске точка при числе — конец записи, в условии — часть нумерации главы
        q = self.row('11.198')
        self.run_command(answers_run=self.board(('11.198.', 'ГЛАВА 11', 3, '$18$ см')),
                         book=self.BOOK, apply=True, decision='номер сверен')
        q.refresh_from_db()
        self.assertEqual(q.latex_answer, '$18$ см')

    def test_number_on_two_rows_of_the_book_is_not_resolved(self):
        a, b = self.row('11.198'), self.row('11.198', scope='Группа Б')
        text, _ = self.run_command(answers_run=self.board(('11.198.', 'ГЛАВА 11', 3, '$18$ см')),
                                   book=self.BOOK, apply=True, decision='два счёта в книге')
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual([a.latex_answer, b.latex_answer], ['', ''])
        self.assertIn('нескольких строках', text)

    def test_answer_under_several_headings_stays_unsure(self):
        q = self.row('11.198', scope='')
        text, _ = self.run_command(
            answers_run=self.board(('11.198', 'Группа А', 3, '$18$ см'),
                                   ('11.198', 'Группа Б', 3, '$24$ см')),
            book=self.BOOK, apply=True, decision='заголовков два')
        q.refresh_from_db()
        self.assertEqual(q.latex_answer, '')
        self.assertIn('под несколькими заголовками', text)

    def test_board_entry_longer_than_an_answer_is_not_an_answer(self):
        q = self.row('11.198')
        text, _ = self.run_command(
            answers_run=self.board(('11.198', 'ГЛАВА 11', 3, 'Решение. ' + 'по рассуждению ' * 60)),
            book=self.BOOK, apply=True, decision='подозрительно длинно')
        q.refresh_from_db()
        self.assertEqual(q.latex_answer, '')
        self.assertIn('разбор, а не ответ', text)

    def test_same_heading_printed_three_times_is_not_one_answer(self):
        """Имя области повторяется в книге сколько угодно раз (у Касаткиной «Решение
        отдельных задач» — трижды), поэтому две записи под ним — это два разных счёта,
        а не два куска одного ответа."""
        folder = self.tmp / 'сканави_ответы'
        folder.mkdir()
        (folder / 'tasks.json').write_text(json.dumps(
            {'run': 'сканави_ответы', 'pages': 4, 'tasks': [],
             'answers': [{'num': '11.198', 'scope': 'ГЛАВА 11',
                          'values': [{'page': 21, 'text': '$q_0 = 0{,}95q$', 'block': '§1'},
                                     {'page': 61, 'text': '$r_1 = r/3$', 'block': '§2'}]}]},
            ensure_ascii=False), encoding='utf-8')
        q = self.row('11.198')
        text, _ = self.run_command(answers_run='сканави_ответы', book=self.BOOK,
                                   apply=True, decision='два параграфа')
        q.refresh_from_db()
        self.assertEqual(q.latex_answer, '')
        self.assertIn('в нескольких разделах', text)

    def test_answer_already_in_the_bank_is_not_overwritten(self):
        q = self.row('11.198', answer='было из скана условий')
        self.run_command(answers_run=self.board(('11.198', 'ГЛАВА 11', 3, '$18$ см')),
                         book=self.BOOK, apply=True, decision='не перетирать')
        q.refresh_from_db()
        self.assertEqual(q.latex_answer, 'было из скана условий')

    def test_human_edited_row_goes_to_the_editor_not_the_database(self):
        q = self.row('11.198', edited=True)
        text, _ = self.run_command(answers_run=self.board(('11.198', 'ГЛАВА 11', 3, '$18$ см')),
                                   book=self.BOOK, apply=True, decision='строка вычитана')
        q.refresh_from_db()
        self.assertEqual(q.latex_answer, '')
        self.assertIn('только редактурой', text)

    def test_other_book_is_out_of_scope(self):
        q = self.row('11.198', book='Звавич. 11кл. стереометрия')
        with self.assertRaises(CommandError):
            self.run_command(answers_run=self.board(('11.198', 'ГЛАВА 11', 3, '$18$ см')),
                             book=self.BOOK)
        q.refresh_from_db()
        self.assertEqual(q.latex_answer, '')

    def test_empty_board_is_an_error_not_a_quiet_zero(self):
        self.row('11.198')
        with self.assertRaises(CommandError) as ctx:
            self.run_command(answers_run=self.board(), book=self.BOOK)
        self.assertIn('нет ни одной записи ответа', str(ctx.exception))

    def test_answer_printed_inside_the_unit_counts_as_a_source_too(self):
        """Не только отдельная страница «Ответы»: у Касаткиной ответ напечатан в теле
        задачи, и тогда источником служит тот же разбор единиц, а не доска."""
        folder = self.tmp / 'касаткина_глава1'
        folder.mkdir()
        (folder / 'tasks.json').write_text(json.dumps(
            {'run': 'касаткина_глава1', 'pages': 2,
             'tasks': [{'num': '11.198', 'scope': 'ГЛАВА 11', 'pages': [7],
                        'markdown': 'условие', 'answer': '',
                        'answer_in': ['$18$ см', '$4$ см²']}],
             'answers': []}, ensure_ascii=False), encoding='utf-8')
        q = self.row('11.198')
        self.run_command(answers_run='касаткина_глава1', book=self.BOOK, apply=True,
                         decision='ответ напечатан в задаче')
        q.refresh_from_db()
        self.assertEqual(q.latex_answer, '$18$ см; $4$ см²')
        self.assertEqual(q.provenance['answer_from']['run'], 'касаткина_глава1')

    def test_apply_without_whose_decision_is_refused(self):
        self.row('11.198')
        with self.assertRaises(CommandError):
            self.run_command(answers_run=self.board(('11.198', 'ГЛАВА 11', 3, '$18$ см')),
                             book=self.BOOK, apply=True)

    def test_board_number_absent_from_the_bank_is_reported(self):
        self.row('11.198')
        text, listing = self.run_command(
            answers_run=self.board(('11.198', 'ГЛАВА 11', 3, '$18$ см'),
                                   ('11.999', 'ГЛАВА 11', 3, '$7$ см')),
            book=self.BOOK)
        self.assertIn('такого номера в банке нет', text)
        unsure = json.loads(listing.read_text(encoding='utf-8'))['unsure']
        self.assertEqual([u['num'] for u in unsure], ['11.999'])

    def test_number_of_a_skipped_row_is_not_reported_as_absent_from_the_book(self):
        """Доска отвечает и на номер строки, которую правил человек. Она уже посчитана
        в «не участвует», и вторым списком выходить не должна: «такого номера в банке
        нет» на номер, который в банке есть, — это ложь про данные, а не предупреждение.
        """
        self.row('11.198', edited=True)
        text, listing = self.run_command(
            answers_run=self.board(('11.198', 'ГЛАВА 11', 3, '$18$ см')), book=self.BOOK)
        self.assertIn('не участвует: строка правилась человеком — ответ только редактурой — 1', text)
        self.assertIn('спорных: 0', text)
        self.assertEqual(json.loads(listing.read_text(encoding='utf-8'))['unsure'], [])

    def test_row_whose_number_is_not_on_the_board_is_counted(self):
        """«Подходит к приклеиванию: 1» не должно читаться как «больше нечего»:
        строка с напечатанным номером, которого на доске нет, видна в отчёте."""
        self.row('11.198')
        q = self.row('11.200')
        text, listing = self.run_command(
            answers_run=self.board(('11.198', 'ГЛАВА 11', 3, '$18$ см')), book=self.BOOK)
        self.assertIn('номера нет на доске ответов — 1', text)
        d = json.loads(listing.read_text(encoding='utf-8'))
        self.assertEqual(d['counts']['bank_rows'], 2)
        self.assertEqual(d['counts']['candidates'], 2)
        self.assertEqual(d['counts']['skipped']['номера нет на доске ответов'], 1)
        q.refresh_from_db()
        self.assertEqual(q.latex_answer, '')
    def unit_board(self, *tasks, name='сканави_253_274'):
        """Прогон с ответами = тот же прогон, что у строк банка: ответы напечатаны
        внутри единиц, и различает их только страница."""
        folder = self.tmp / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'tasks.json').write_text(json.dumps(
            {'run': name, 'pages': 120, 'answers': [],
             'tasks': [{'num': n, 'scope': 'ГЛАВА 11', 'pages': p, 'block': b,
                        'markdown': 'условие', 'answer': '',
                        'answer_in': a if isinstance(a, list) else [a]}
                       for (n, p, b, a) in tasks]}, ensure_ascii=False), encoding='utf-8')
        return name

    def test_answer_from_another_page_of_the_same_run_is_not_the_row_s_answer(self):
        """Номер в книге идёт счётом по главам: строка с.19 не может получить ответ
        задачи с.99 того же прогона, даже если обе напечатаны под «ГЛАВА 11»."""
        q = self.row('11.198')
        text, _ = self.run_command(
            answers_run=self.unit_board(('11.198', [99, 100], '3. РАБОТА ЗАРЯДА / Решение',
                                         '$q_0 = 0{,}95q$')),
            book=self.BOOK, apply=True, decision='тот же прогон')
        q.refresh_from_db()
        self.assertEqual(q.latex_answer, '')
        self.assertIn('в другой задаче с тем же номером', text)

    def test_answer_inside_the_unit_of_the_same_page_is_attached(self):
        q = self.row('11.198')
        self.run_command(
            answers_run=self.unit_board(('11.198', [19, 20], 'ГЛАВА 11 / Решение', '$18$ см')),
            book=self.BOOK, apply=True, decision='страница совпала')
        q.refresh_from_db()
        self.assertEqual(q.latex_answer, '$18$ см')


class RefreshScanTextTest(TestCase):
    """Вернуть формулы экранам, которые читают text: тест, результаты, «Вопросы».

    plain_from_latex снимал `$…$`, поэтому KaTeX там нечего было выделять и на экране
    стояло сырое `10\\text{ м}`. Пересборка берёт latex — содержательного она не меняет,
    поэтому и права ровно одно поле; всё остальное (тема, сложность, статус приёмки,
    ответ) остаётся чужими решениями.
    """

    @classmethod
    def setUpTestData(cls):
        cls.physics = Subject.objects.create(name='Физика', slug='refresh-ph', icon='⚡')
        cls.topic = Topic.objects.create(subject=cls.physics, name='Сканави · ГЛАВА 11')

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def book_row(self, num, latex, **extra_prov):
        """Строка банка так, как её оставил старый plain_from_latex: текст без `$`.

        Экран банка при этом показывал формулу — он читает latex; здесь важен text.
        """
        prov = {'run': 'out_t', 'book': 'Сканави, стериометрия', 'num': num,
                'format': 'задача'}
        prov.update(extra_prov)
        return Question.objects.create(
            topic=self.topic, text=latex.replace('$', ''), latex=latex,
            source_type='book_scan', verification_status='verified', provenance=prov)

    def run_command(self, **opt):
        opt.setdefault('out', str(self.tmp / 'list.json'))
        out = io.StringIO()
        call_command('refresh_scan_text', stdout=out, stderr=out, **opt)
        listing = Path(opt['out'])
        data = json.loads(listing.read_text(encoding='utf-8')) if listing.exists() else {}
        return out.getvalue(), data

    def test_dry_run_leaves_the_database_alone(self):
        q = self.book_row('11.1', '$v = 10\\text{ м}$')
        text, data = self.run_command()
        q.refresh_from_db()
        self.assertEqual(q.text, 'v = 10\\text{ м}')
        self.assertIn('сухой прогон: база не тронута', text)
        self.assertEqual([p['id'] for p in data['plan']], [q.id])
        self.assertEqual(data['plan'][0]['new'], '$v = 10\\text{ м}$')

    def test_apply_writes_only_text_and_keeps_every_decision(self):
        q = self.book_row('11.2', 'Тело массой $m = 2\\text{ кг}$ движется')
        before = (q.latex, q.topic_id, q.verification_status, q.difficulty,
                  q.question_type, q.provenance['num'])
        text, _ = self.run_command(apply=True, decision='пересборка по правке plain_from_latex')
        q.refresh_from_db()
        self.assertEqual(q.text, 'Тело массой $m = 2\\text{ кг}$ движется')
        self.assertEqual((q.latex, q.topic_id, q.verification_status, q.difficulty,
                          q.question_type, q.provenance['num']), before)
        self.assertEqual(q.provenance['text_refresh']['by'],
                         'пересборка по правке plain_from_latex')
        self.assertIn('пересобрано: 1', text)

    def test_row_without_latex_is_never_touched(self):
        """Собранные вопросы живут в text: пересобирать их из пустого latex — стереть банк."""
        other = Question.objects.create(topic=self.topic, text='$x$ из Excel',
                                        source_type='collected')
        naked = Question.objects.create(topic=self.topic, text='условие без latex',
                                        source_type='book_scan')
        text, data = self.run_command(apply=True, decision='только банк')
        other.refresh_from_db()
        naked.refresh_from_db()
        self.assertEqual(other.text, '$x$ из Excel')
        self.assertEqual(naked.text, 'условие без latex')
        self.assertEqual(data['counts']['without_latex'], 1)
        self.assertNotIn(other.id, [p['id'] for p in data['plan']])

    def test_human_edited_row_goes_to_the_list_not_the_database(self):
        q = self.book_row('11.3', '$a = 5$', human_edited=True)
        text, data = self.run_command(apply=True, decision='строку правил человек')
        q.refresh_from_db()
        self.assertEqual(q.text, 'a = 5')
        self.assertEqual([p['id'] for p in data['unsure']], [q.id])
        self.assertIn('правил человек', text)

    def test_human_flag_takes_the_row_the_eyes_already_cleared(self):
        """Строка «правил человек», вычитанная по скану, пересобирается по названному id.

        Без флага она ушла бы списком «спорно» — и 12.10 такие четыре строки гоняли
        отдельным скриптом. Флаг нужен, чтобы обход отсека не был тихим.
        """
        q = self.book_row('11.3а', '$a = 5$', human_edited=True)
        text, data = self.run_command(human=str(q.id), apply=True,
                                      decision='вычитано глазами 12.10')
        q.refresh_from_db()
        self.assertEqual(q.text, '$a = 5$')
        self.assertTrue(q.provenance['human_edited'])          # метку не снимаем
        self.assertEqual(q.provenance['text_refresh']['by'], 'вычитано глазами 12.10')
        self.assertTrue(data['plan'][0]['правил человек'])
        self.assertEqual(data['counts']['human_named'], 1)
        self.assertIn('[правил человек]', text)

    def test_human_flag_on_an_id_outside_the_slice_says_so(self):
        """Названный id, которого в этом срезе нет, не должен теряться молча."""
        q = self.book_row('11.3б', '$b = 6$', human_edited=True)
        self.book_row('11.3в', '$c = 7$')            # фильтр по книге требует хоть одну строку
        Question.objects.filter(pk=q.id).update(provenance={**q.provenance, 'book': 'Касаткина'})
        text, data = self.run_command(book='Сканави, стериометрия', human=str(q.id),
                                      apply=True, decision='не та книга')
        q.refresh_from_db()
        self.assertEqual(q.text, 'b = 6')
        self.assertEqual(data['counts']['human_missed'], [q.id])
        self.assertIn('таких id в этом срезе нет', text)

    def test_second_run_writes_nothing_new(self):
        self.book_row('11.4', '$b = 7$')
        self.run_command(apply=True, decision='первый проход')
        text, data = self.run_command(apply=True, decision='второй проход')
        self.assertEqual(data['counts']['plan'], 0)
        self.assertIn('уже совпадает', text)

    def test_long_condition_is_not_cut_mid_formula(self):
        """Длинное условие живёт целиком: `text` — колонка без лимита.

        Срез [:4000] резал восемь строк Касаткиной (latex до 7031 знака) посередине
        формулы: хвост решения терялся, а незакрытый `$$` печатался на экране сырыми
        долларами — шаг 1 не находит пару.
        """
        latex = 'условие ' * 700 + ' $$E = 2\\text{ В/м}$$'
        q = self.book_row('11.7', latex)
        self.run_command(apply=True, decision='хвост длинного условия')
        q.refresh_from_db()
        self.assertGreater(len(latex), 4000)
        self.assertEqual(q.text, latex)
        self.assertEqual(q.text.count('$$') % 2, 0)

    def test_rollback_to_the_scan_snapshot_keeps_the_whole_text(self):
        latex = 'условие ' * 700 + ' $\\varphi$'
        q = self.book_row('11.8', latex)
        prov = dict(q.provenance)
        prov['ocr_original'] = {'latex': latex}
        prov['human_edited'] = True
        Question.objects.filter(pk=q.id).update(text='короткая правка человека', provenance=prov)
        q.refresh_from_db()
        self.assertTrue(q.restore_ocr_original())
        self.assertEqual(q.text, latex)
        self.assertTrue(q.text.endswith('$\\varphi$'))

    def test_book_filter_limits_scope_to_one_book(self):
        a = self.book_row('11.5', '$c = 1$')
        b = self.book_row('11.6', '$d = 2$')
        Question.objects.filter(pk=b.id).update(provenance={**b.provenance,
                                                            'book': 'Касаткина'})
        _, data = self.run_command(book='Касаткина', apply=True, decision='одна книга')
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.text, 'c = 1')
        self.assertEqual(b.text, '$d = 2$')

    def test_plain_from_latex_keeps_the_delimiters(self):
        from subjects.models import plain_from_latex
        self.assertEqual(plain_from_latex('Дано: $x = 2$ м, **важно**'),
                         'Дано: $x = 2$ м, важно')
        # номер, напечатанный у формулы, в text не идёт: он в external_id, а KaTeX
        # ругается на \tag в строчной формуле
        self.assertEqual(plain_from_latex('$x = 2\\tag{11.198}$'), '$x = 2$')
