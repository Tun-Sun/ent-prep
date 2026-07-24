from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from subjects.models import Answer, Question, Subject, Topic
from users.models import User

from .models import AnswerRecord, TestSectionResult, TestSession, TestSessionQuestion
from .views import _recalc_session, _score_matching


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
