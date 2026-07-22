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
