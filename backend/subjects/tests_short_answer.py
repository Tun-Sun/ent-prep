"""Короткий ответ: импорт из Google Forms и попадание в тестовый пул.

Формы NUET содержат вопросы без вариантов: ученик вписывает число или
выражение сам. Это не `open_answer` из банка (там ключа нет вовсе) — здесь
эталон есть, и он лежит в `Answer` с `is_correct=True`. Поэтому короткий ответ
обязан и проходить `answerable()`, и не отдавать свой эталон в стартовом пакете.
"""
from django.test import TestCase

from subjects.google_forms.importer import import_payload
from subjects.google_forms.parser import parse_dict
from subjects.models import Answer, Question, Subject, Topic


def make_text_payload(*questions):
    """Payload как у scraper-экспорта, но с короткими ответами."""
    return {
        'schema_version': 1,
        'source': {
            'type': 'google_forms',
            'form_id': 'FORM-NUET',
            'form_url': 'https://docs.google.com/forms/d/FORM-NUET/edit',
            'form_title': 'NUET. Test 1. Math',
            'is_quiz': True,
        },
        'subject_slug': 'nuet-01',
        'subject_name': 'NUET 01',
        'topic_name': 'Math',
        'language': 'ru',
        'year': 2026,
        'questions': list(questions),
    }


def text_question(title, *key_values, external_id='FORM-NUET/q1'):
    return {
        'external_id': external_id,
        'title': title,
        'help_text': '',
        'image': None,
        'type': 'text',
        'answers': [{'text': value, 'is_correct': True} for value in key_values],
        'order_index': 0,
    }


class ShortAnswerParserTest(TestCase):
    def test_text_question_keeps_all_accepted_values(self):
        payload = parse_dict(make_text_payload(
            text_question('Найдите x, если 2x = 3', '3/2', '1.5')))

        self.assertEqual(len(payload.questions), 1)
        question = payload.questions[0]
        self.assertEqual(question.type, 'text')
        self.assertEqual([a.text for a in question.answers], ['3/2', '1.5'])
        self.assertTrue(question.has_correct)

    def test_single_key_is_not_treated_as_meta_field(self):
        """Один эталон у короткого ответа — норма, а не служебное поле."""
        payload = parse_dict(make_text_payload(
            text_question('Сколько будет 7 × 8?', '56')))

        self.assertEqual([q.external_id for q in payload.questions],
                         ['FORM-NUET/q1'])

    def test_text_question_without_key_is_kept_as_draft(self):
        """Без эталона вопрос живой, но в тест не попадёт — ключ добавит учитель."""
        payload = parse_dict(make_text_payload(
            text_question('Ответ без эталона')))

        self.assertEqual(len(payload.questions), 1)
        self.assertEqual(payload.questions[0].answers, [])
        self.assertFalse(payload.questions[0].has_correct)

    def test_name_field_is_still_filtered_out(self):
        payload = parse_dict(make_text_payload(
            text_question('Your name', 'Иван', external_id='FORM-NUET/name'),
            text_question('Сколько будет 2 + 2?', '4')))

        self.assertEqual([q.external_id for q in payload.questions],
                         ['FORM-NUET/q1'])


class ShortAnswerImporterTest(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(
            name='NUET 01', slug='nuet-01', track='nuet')

    def test_text_type_becomes_short_answer_question(self):
        payload = parse_dict(make_text_payload(
            text_question('Найдите x, если 2x = 3', '3/2', '1.5')))

        result = import_payload(payload)
        self.assertEqual(result.created, 1)

        question = Question.objects.get(external_id='FORM-NUET/q1')
        self.assertEqual(question.question_type, 'short_answer')
        self.assertEqual(question.verification_status, 'verified')
        self.assertEqual(
            set(question.answers.filter(is_correct=True)
                .values_list('text', flat=True)),
            {'3/2', '1.5'},
        )

    def test_imported_question_lands_in_requested_topic(self):
        payload = parse_dict(make_text_payload(
            text_question('Сколько будет 2 + 2?', '4')))

        import_payload(payload)

        self.assertEqual(self.subject.topics.get(name='Math').questions.count(), 1)


class ShortAnswerAnswerableTest(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(
            name='NUET 01', slug='nuet-01', track='nuet')
        self.topic = Topic.objects.create(name='Math', subject=self.subject)

    def _question(self, question_type, with_key=True):
        question = Question.objects.create(
            text='Вопрос', topic=self.topic, question_type=question_type,
            verification_status='verified',
        )
        if with_key:
            Answer.objects.create(question=question, text='42', is_correct=True)
        return question

    def test_keyed_short_answer_is_answerable(self):
        question = self._question('short_answer')
        self.assertTrue(
            Question.objects.filter(pk=question.pk).answerable().exists())

    def test_keyless_short_answer_is_not_answerable(self):
        question = self._question('short_answer', with_key=False)
        self.assertFalse(
            Question.objects.filter(pk=question.pk).answerable().exists())

    def test_open_answer_is_still_not_answerable(self):
        question = self._question('open_answer')
        self.assertFalse(
            Question.objects.filter(pk=question.pk).answerable().exists())
