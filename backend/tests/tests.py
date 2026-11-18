from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from subjects.models import Answer, Question, Subject, Topic
from users.models import User

from .models import AnswerRecord, TestSectionResult, TestSession, TestSessionQuestion
from .views import _normalize_short_answer, _recalc_session, _score_matching, _score_short_answer


class TestSessionApiTest(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username='student', password='password', role='student')
        self.client = APIClient()
        self.client.force_authenticate(self.student)
        self.subject = Subject.objects.create(name='Математика', slug='math', question_count=1, time_limit=600)
        self.topic = Topic.objects.create(name='Алгебра', subject=self.subject)
        self.question = self._question('2 + 2?', verified=True)
        self.correct = Answer.objects.create(question=self.question, text='4', is_correct=True)
        self.wrong = Answer.objects.create(question=self.question, text='5', is_correct=False)
        self.outside_question = self._question('Не из попытки?')
        self.outside_answer = Answer.objects.create(question=self.outside_question, text='Да', is_correct=True)

    def _question(self, text, verified=False, question_type='single_choice'):
        return Question.objects.create(
            text=text,
            topic=self.topic,
            question_type=question_type,
            verification_status='verified' if verified else 'draft',
        )

    def _start(self):
        response = self.client.post('/api/tests/start/', {'subject_id': self.subject.id}, format='json')
        self.assertEqual(response.status_code, 200)
        return response.json()['session_id']

    def test_start_persists_issued_questions(self):
        session_id = self._start()
        session = TestSession.objects.get(id=session_id)
        self.assertEqual(list(session.session_questions.values_list('question_id', flat=True)), [self.question.id])

    def test_answer_for_question_outside_session_is_rejected(self):
        session_id = self._start()
        response = self.client.post(
            f'/api/tests/{session_id}/answer/',
            {'question': self.outside_question.id, 'selected_answer': self.outside_answer.id},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(AnswerRecord.objects.count(), 0)

    def test_answer_option_from_another_question_is_rejected(self):
        session_id = self._start()
        response = self.client.post(
            f'/api/tests/{session_id}/answer/',
            {'question': self.question.id, 'selected_answer': self.outside_answer.id},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(AnswerRecord.objects.count(), 0)

    def test_expired_session_rejects_answers_and_completes(self):
        session_id = self._start()
        session = TestSession.objects.get(id=session_id)
        session.started_at = timezone.now() - timedelta(seconds=session.time_limit + 1)
        session.save(update_fields=['started_at'])

        response = self.client.post(
            f'/api/tests/{session_id}/answer/',
            {'question': self.question.id, 'selected_answer': self.correct.id},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        session.refresh_from_db()
        self.assertTrue(session.is_completed)

    def test_multiple_choice_rejects_more_than_two_answers(self):
        question = self._question('Выберите два', question_type='multiple_choice')
        answers = [
            Answer.objects.create(question=question, text=str(index), is_correct=index < 2)
            for index in range(3)
        ]
        session = TestSession.objects.create(student=self.student, subject=self.subject, total_questions=1)
        TestSessionQuestion.objects.create(session=session, question=question, position=1)

        response = self.client.post(
            f'/api/tests/{session.id}/answer/',
            {'question': question.id, 'selected_answers': [answer.id for answer in answers]},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(AnswerRecord.objects.count(), 0)


class StartTestModesTest(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username='modes-student', password='password', role='student')
        self.client = APIClient()
        self.client.force_authenticate(self.student)
        self.subject = Subject.objects.create(
            name='Физика', slug='physics-modes', is_visible=True,
            subject_type='profile', question_count=10, time_limit=600,
        )
        self.topic_a = Topic.objects.create(name='Механика', subject=self.subject)
        self.topic_b = Topic.objects.create(name='Оптика', subject=self.subject)
        for topic in (self.topic_a, self.topic_b):
            for i in range(8):
                q = Question.objects.create(
                    text=f'{topic.name} вопрос {i}', topic=topic,
                    question_type='single_choice', verification_status='verified',
                )
                Answer.objects.create(question=q, text='Верно', is_correct=True)
                Answer.objects.create(question=q, text='Неверно', is_correct=False)

    def test_start_with_topic_ids_filters_questions(self):
        response = self.client.post('/api/tests/start/', {
            'subject_id': self.subject.id,
            'topic_ids': [self.topic_a.id],
        }, format='json')
        self.assertEqual(response.status_code, 200)
        session = TestSession.objects.get(id=response.data['session_id'])
        topic_ids = set(session.session_questions.values_list('question__topic_id', flat=True))
        self.assertEqual(topic_ids, {self.topic_a.id})

    def test_rush_mode(self):
        # Недостаточно вопросов в одном предмете — Rush берёт из всех видимых
        other = Subject.objects.create(
            name='Химия', slug='chemistry-modes', is_visible=True,
            subject_type='mandatory', question_count=10, time_limit=600,
        )
        other_topic = Topic.objects.create(name='Органика', subject=other)
        for i in range(30):
            q = Question.objects.create(
                text=f'Химия вопрос {i}', topic=other_topic,
                question_type='single_choice', verification_status='verified',
            )
            Answer.objects.create(question=q, text='Верно', is_correct=True)
            Answer.objects.create(question=q, text='Неверно', is_correct=False)

        response = self.client.post('/api/tests/start/', {'mode': 'rush'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['mode'], 'rush')
        self.assertEqual(response.data['total_questions'], 30)
        self.assertEqual(response.data['time_limit'], 300)
        session = TestSession.objects.get(id=response.data['session_id'])
        self.assertEqual(session.mode, 'rush')
        self.assertFalse(
            session.session_questions.filter(question__question_type='matching').exists()
        )

    def test_finish_awards_first_achievement(self):
        from gamification.models import UserAchievement
        response = self.client.post('/api/tests/start/', {
            'subject_id': self.subject.id,
            'num_questions': 5,
        }, format='json')
        session_id = response.data['session_id']
        response = self.client.post(f'/api/tests/{session_id}/finish/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            UserAchievement.objects.filter(user=self.student, code='first_test').exists()
        )


class BankQuestionsNotIssuedTest(TestCase):
    """Банк оцифровки — учебный материал, а не тестовый пул.

    Открытая задача из книги не имеет вариантов: ученик не может ответить, а
    `_score_question` начисляет 0. Тест без правильного варианта нечем проверить.
    """

    def setUp(self):
        self.student = User.objects.create_user(
            username='bank-student', password='password', role='student')
        self.client = APIClient()
        self.client.force_authenticate(self.student)
        self.subject = Subject.objects.create(
            name='Физика-банк', slug='physics-bank', is_visible=True,
            question_count=2, time_limit=600,
        )
        self.topic = Topic.objects.create(name='Механика-банк', subject=self.subject)

    def _open_bank(self):
        return Question.objects.create(
            text='Задача из Касаткиной', topic=self.topic,
            question_type='open_answer', verification_status='verified',
            source_type='book_scan', latex_answer='V=0{,}74\\ \\text{л}',
        )

    def _choice(self, with_key=True, verified=True):
        q = Question.objects.create(
            text='Тестовый вопрос', topic=self.topic,
            question_type='single_choice',
            verification_status='verified' if verified else 'draft',
        )
        if with_key:
            Answer.objects.create(question=q, text='Верно', is_correct=True)
        Answer.objects.create(question=q, text='Неверно', is_correct=False)
        return q

    def _start(self):
        return self.client.post(
            '/api/tests/start/', {'subject_id': self.subject.id}, format='json')

    def test_open_answer_verified_is_not_issued_even_alone(self):
        self._open_bank()
        response = self._start()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(TestSession.objects.count(), 0)

    def test_open_answer_never_mixes_into_a_session(self):
        bank = self._open_bank()
        good = [self._choice() for _ in range(4)]
        response = self._start()
        self.assertEqual(response.status_code, 200)
        ids = {q['id'] for q in response.data['questions']}
        self.assertNotIn(bank.id, ids)
        self.assertTrue(ids <= {g.id for g in good})

    def test_choice_without_correct_option_is_not_issued(self):
        keyless = self._choice(with_key=False)
        self._open_bank()
        response = self._start()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(TestSessionQuestion.objects.filter(question=keyless).count(), 0)


class MatchingScoreTest(TestCase):
    def test_matching_scores_only_exact_right_side(self):
        subject = Subject.objects.create(name='История', slug='history-test')
        topic = Topic.objects.create(name='Тема', subject=subject)
        question = Question.objects.create(
            text='Соответствие', topic=topic, question_type='matching', points=2,
        )
        first = Answer.objects.create(question=question, text='A → 1', is_correct=True)
        second = Answer.objects.create(question=question, text='B → 2', is_correct=True)

        earned, maximum = _score_matching(question, {str(first.id): '2', str(second.id): '1'})
        self.assertEqual((earned, maximum), (0, 2))

        earned, maximum = _score_matching(question, {str(first.id): '1', str(second.id): '2'})
        self.assertEqual((earned, maximum), (2, 2))


class EntSectionScoreTest(TestCase):
    def test_section_result_uses_section_assigned_in_session(self):
        student = User.objects.create_user(username='ent-student', password='password', role='student')
        subject = Subject.objects.create(name='ЕНТ предмет', slug='ent-subject')
        topic = Topic.objects.create(name='Тема', subject=subject)
        question = Question.objects.create(text='Вопрос', topic=topic, section='', points=1)
        correct = Answer.objects.create(question=question, text='Верно', is_correct=True)
        session = TestSession.objects.create(student=student, is_ent=True, total_questions=1)
        TestSessionQuestion.objects.create(session=session, question=question, position=1, section='history')
        TestSectionResult.objects.create(session=session, section='history', total_questions=1, points_max=1)
        AnswerRecord.objects.create(
            session=session, question=question, selected_answer=correct,
            is_correct=True, points_earned=1, points_max=1,
        )

        _recalc_session(session)

        result = session.section_results.get(section='history')
        self.assertEqual((result.answered, result.correct_answers, result.points_earned), (1, 1, 1))

    def test_legacy_ent_section_result_uses_subject(self):
        student = User.objects.create_user(username='legacy-student', password='password', role='student')
        subject = Subject.objects.create(name='История', slug='history')
        topic = Topic.objects.create(name='Тема', subject=subject)
        question = Question.objects.create(text='Вопрос', topic=topic, points=1)
        correct = Answer.objects.create(question=question, text='Верно', is_correct=True)
        session = TestSession.objects.create(student=student, is_ent=True, total_questions=1)
        TestSectionResult.objects.create(session=session, section='history', total_questions=1, points_max=1)
        AnswerRecord.objects.create(
            session=session, question=question, selected_answer=correct,
            is_correct=True, points_earned=1, points_max=1,
        )

        _recalc_session(session)

        result = session.section_results.get(section='history')
        self.assertEqual((result.answered, result.correct_answers, result.points_earned), (1, 1, 1))


class ShortAnswerScoreTest(TestCase):
    """Сверка строки с эталоном: пробелы, регистр, запятая и пунктуация."""

    def setUp(self):
        subject = Subject.objects.create(name='NUET 01', slug='nuet-01')
        topic = Topic.objects.create(name='Math', subject=subject)
        self.question = Question.objects.create(
            text='Найдите x, если 2x = 3', topic=topic,
            question_type='short_answer', points=1,
        )
        Answer.objects.create(question=self.question, text='3/2', is_correct=True)
        Answer.objects.create(question=self.question, text='1.5', is_correct=True)

    def test_exact_value_is_accepted(self):
        self.assertEqual(_score_short_answer(self.question, '3/2'), (1, 1))

    def test_alternative_key_is_accepted(self):
        self.assertEqual(_score_short_answer(self.question, '1.5'), (1, 1))

    def test_spaces_case_and_comma_are_ignored(self):
        for typed in (' 1,5 ', '1.5', '1,50', '3 / 2'):
            self.assertEqual(
                _score_short_answer(self.question, typed), (1, 1), typed)

    def test_wrong_value_scores_zero(self):
        self.assertEqual(_score_short_answer(self.question, '2'), (0, 1))

    def test_empty_value_scores_zero(self):
        self.assertEqual(_score_short_answer(self.question, '   '), (0, 1))

    def test_labels_are_compared_case_insensitively(self):
        question = Question.objects.create(
            text='Найдите B', topic=self.question.topic,
            question_type='short_answer', points=1,
        )
        Answer.objects.create(question=question, text='B=76', is_correct=True)
        self.assertEqual(_score_short_answer(question, 'b = 76'), (1, 1))

    def test_normalizer_keeps_significant_characters(self):
        self.assertEqual(_normalize_short_answer(' B = 76 '), 'b=76')
        self.assertNotEqual(_normalize_short_answer('B=76'),
                            _normalize_short_answer('B=77'))


class ShortAnswerApiTest(TestCase):
    """Короткий ответ в живом тесте: ключ не утекает, ответ проверяется."""

    def setUp(self):
        self.student = User.objects.create_user(
            username='short-student', password='password', role='student')
        self.client = APIClient()
        self.client.force_authenticate(self.student)
        self.subject = Subject.objects.create(
            name='NUET 01', slug='nuet-01', question_count=1, time_limit=600)
        self.topic = Topic.objects.create(name='Math', subject=self.subject)
        self.question = Question.objects.create(
            text='Найдите x, если 2x = 3', topic=self.topic,
            question_type='short_answer', verification_status='verified',
            points=1,
        )
        Answer.objects.create(question=self.question, text='3/2', is_correct=True)
        Answer.objects.create(question=self.question, text='1.5', is_correct=True)

    def _start(self):
        response = self.client.post(
            '/api/tests/start/', {'subject_id': self.subject.id}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return response.json()

    def _answer(self, session_id, text_answer):
        return self.client.post(
            f'/api/tests/{session_id}/answer/',
            {'question': self.question.id, 'text_answer': text_answer},
            format='json',
        )

    def test_start_does_not_leak_the_accepted_values(self):
        data = self._start()
        self.assertEqual(data['total_questions'], 1)
        question = data['questions'][0]
        self.assertEqual(question['question_type'], 'short_answer')
        self.assertEqual(question['answers'], [])

    def test_correct_typed_answer_is_scored(self):
        session_id = self._start()['session_id']
        response = self._answer(session_id, '1,5')

        self.assertEqual(response.status_code, 200, response.data)
        record = AnswerRecord.objects.get(session_id=session_id)
        self.assertEqual(record.text_answer, '1,5')
        self.assertTrue(record.is_correct)
        self.assertEqual(record.points_earned, 1)

    def test_wrong_typed_answer_is_saved_and_marked_wrong(self):
        session_id = self._start()['session_id']
        response = self._answer(session_id, '2')

        self.assertEqual(response.status_code, 200, response.data)
        record = AnswerRecord.objects.get(session_id=session_id)
        self.assertEqual(record.text_answer, '2')
        self.assertFalse(record.is_correct)
        self.assertEqual(record.points_earned, 0)

    def test_blank_answer_is_rejected(self):
        session_id = self._start()['session_id']
        response = self._answer(session_id, '   ')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(AnswerRecord.objects.count(), 0)

    def test_bulk_submit_accepts_text_answer(self):
        session_id = self._start()['session_id']
        response = self.client.post(
            f'/api/tests/{session_id}/answers/bulk/',
            {'answers': [{'question': self.question.id, 'text_answer': '3/2'}]},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        record = AnswerRecord.objects.get(session_id=session_id)
        self.assertTrue(record.is_correct)

    def test_state_returns_typed_answer_after_reload(self):
        session_id = self._start()['session_id']
        self._answer(session_id, '3/2')

        response = self.client.get(f'/api/tests/{session_id}/state/')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            response.data['answer_map'][self.question.id]['text_answer'],
            '3/2',
        )

    def test_finish_counts_short_answer_in_score(self):
        session_id = self._start()['session_id']
        self._answer(session_id, '1.5')

        response = self.client.post(f'/api/tests/{session_id}/finish/',
                                    format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['correct_answers'], 1)
        self.assertEqual(response.data['score_percent'], 100.0)

    def test_results_show_typed_and_expected_values(self):
        session_id = self._start()['session_id']
        self._answer(session_id, '2')
        self.client.post(f'/api/tests/{session_id}/finish/', format='json')

        response = self.client.get(f'/api/tests/{session_id}/result/')

        self.assertEqual(response.status_code, 200, response.data)
        record = response.data['answers'][0]
        self.assertEqual(record['text_answer'], '2')
        self.assertEqual(record['selected_answer_text'], '2')
        self.assertIn('3/2', record['correct_answer_text'])
        self.assertIn('1.5', record['correct_answer_text'])
