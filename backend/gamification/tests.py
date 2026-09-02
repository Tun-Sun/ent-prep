from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from subjects.models import Answer, Question, Subject, Topic
from tests.models import AnswerRecord, TestSession, TestSessionQuestion
from users.models import User

from .models import Duel, UserAchievement
from .services import check_achievements, get_streak, resolve_duel


def _make_subject_with_questions(name='Математика', slug='math', n=12, is_profile=True):
    subject = Subject.objects.create(
        name=name, slug=slug,
        subject_type='profile' if is_profile else 'mandatory',
        is_visible=True, question_count=10, time_limit=600,
    )
    topic = Topic.objects.create(name='Тема 1', subject=subject)
    questions = []
    for i in range(n):
        q = Question.objects.create(
            text=f'Вопрос {i + 1}?', topic=topic,
            verification_status='verified', question_type='single_choice',
        )
        Answer.objects.create(question=q, text='Да', is_correct=True)
        Answer.objects.create(question=q, text='Нет', is_correct=False)
        questions.append(q)
    return subject, topic, questions


def _complete_session(student, questions, correct_count=None, mode='standard', subject=None):
    session = TestSession.objects.create(
        student=student, subject=subject,
        total_questions=len(questions), time_limit=600, mode=mode,
        total_points=len(questions),
    )
    TestSessionQuestion.objects.bulk_create([
        TestSessionQuestion(session=session, question=q, position=i + 1)
        for i, q in enumerate(questions)
    ])
    if correct_count is None:
        correct_count = len(questions)
    for i, q in enumerate(questions):
        correct = q.answers.filter(is_correct=True).first()
        wrong = q.answers.filter(is_correct=False).first()
        record = AnswerRecord.objects.create(
            session=session, question=q,
            selected_answer=correct if i < correct_count else wrong,
            is_correct=i < correct_count,
            points_earned=1 if i < correct_count else 0,
            points_max=1,
        )
    session.correct_answers = correct_count
    session.earned_points = correct_count
    session.score_percent = round(correct_count / len(questions) * 100, 1)
    session.completed_at = timezone.now()
    session.is_completed = True
    session.save()
    return session


class AchievementsTest(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username='s1', password='pass12345', role='student')
        self.subject, self.topic, self.questions = _make_subject_with_questions()

    def test_first_test_achievement(self):
        _complete_session(self.student, self.questions[:5])
        newly = check_achievements(self.student)
        self.assertIn('first_test', newly)
        self.assertTrue(
            UserAchievement.objects.filter(user=self.student, code='first_test').exists()
        )

    def test_no_duplicate_awards(self):
        _complete_session(self.student, self.questions[:5])
        check_achievements(self.student)
        newly = check_achievements(self.student)
        self.assertEqual(newly, [])

    def test_perfect_run(self):
        _complete_session(self.student, self.questions[:5], correct_count=5)
        newly = check_achievements(self.student)
        self.assertIn('perfect_run', newly)

    def test_rush_master(self):
        _complete_session(self.student, self.questions, correct_count=27, mode='rush')
        newly = check_achievements(self.student)
        self.assertIn('rush_master', newly)

    def test_streak_calculation(self):
        now = timezone.now()
        for days_ago in (2, 1, 0):
            s = _complete_session(self.student, self.questions[:5])
            s.completed_at = now - timedelta(days=days_ago)
            s.save(update_fields=['completed_at'])
        streak = get_streak(self.student)
        self.assertEqual(streak['current'], 3)
        self.assertEqual(streak['best'], 3)

    def test_achievements_endpoint(self):
        _complete_session(self.student, self.questions[:5])
        client = APIClient()
        client.force_authenticate(self.student)
        response = client.get('/api/gamification/achievements/')
        self.assertEqual(response.status_code, 200)
        codes = [a['code'] for a in response.data['achievements']]
        self.assertIn('first_test', codes)
        first = next(a for a in response.data['achievements'] if a['code'] == 'first_test')
        self.assertTrue(first['unlocked'])
        self.assertIn('streak', response.data)


class DuelFlowTest(TestCase):
    def setUp(self):
        self.challenger = User.objects.create_user(username='ch', password='pass12345', role='student')
        self.opponent = User.objects.create_user(username='op', password='pass12345', role='student')
        self.subject, self.topic, self.questions = _make_subject_with_questions(n=10)
        self.client = APIClient()

    def test_full_duel_flow(self):
        self.client.force_authenticate(self.challenger)
        response = self.client.post('/api/gamification/duels/', {
            'opponent_id': self.opponent.id,
            'subject_id': self.subject.id,
            'num_questions': 8,
        }, format='json')
        self.assertEqual(response.status_code, 201)
        duel_id = response.data['id']
        duel = Duel.objects.get(id=duel_id)
        self.assertEqual(duel.status, 'pending')
        self.assertEqual(len(duel.question_ids), 8)

        # Соперник не может играть до принятия
        self.client.force_authenticate(self.opponent)
        response = self.client.post(f'/api/gamification/duels/{duel_id}/play/')
        self.assertEqual(response.status_code, 400)

        # Принятие
        response = self.client.post(f'/api/gamification/duels/{duel_id}/respond/', {'action': 'accept'})
        self.assertEqual(response.status_code, 200)
        duel.refresh_from_db()
        self.assertEqual(duel.status, 'active')

        # Оба играют
        response = self.client.post(f'/api/gamification/duels/{duel_id}/play/')
        self.assertEqual(response.status_code, 200)
        opp_session_id = response.data['session_id']
        self.assertEqual(len(response.data['questions']), 8)

        self.client.force_authenticate(self.challenger)
        response = self.client.post(f'/api/gamification/duels/{duel_id}/play/')
        self.assertEqual(response.status_code, 200)
        ch_session_id = response.data['session_id']

        # Идемпотентность play
        response = self.client.post(f'/api/gamification/duels/{duel_id}/play/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['session_id'], ch_session_id)

        # Одинаковый набор вопросов у обоих
        ch_qs = list(TestSession.objects.get(id=ch_session_id).session_questions.values_list('question_id', flat=True))
        op_qs = list(TestSession.objects.get(id=opp_session_id).session_questions.values_list('question_id', flat=True))
        self.assertEqual(ch_qs, op_qs)

        # Завершение: чемпион отвечает верно, соперник — нет
        ch_session = TestSession.objects.get(id=ch_session_id)
        for sq in ch_session.session_questions.select_related('question'):
            correct = sq.question.answers.filter(is_correct=True).first()
            AnswerRecord.objects.create(
                session=ch_session, question=sq.question,
                selected_answer=correct, is_correct=True,
                points_earned=1, points_max=1,
            )
        ch_session.correct_answers = 8
        ch_session.earned_points = 8
        ch_session.score_percent = 100
        ch_session.completed_at = timezone.now()
        ch_session.is_completed = True
        ch_session.save()

        duel.refresh_from_db()
        self.assertEqual(duel.status, 'active')  # соперник ещё не закончил

        op_session = TestSession.objects.get(id=opp_session_id)
        op_session.completed_at = timezone.now()
        op_session.is_completed = True
        op_session.save()

        resolve_duel(duel)
        duel.refresh_from_db()
        self.assertEqual(duel.status, 'completed')
        self.assertEqual(duel.winner_id, self.challenger.id)
        self.assertTrue(
            UserAchievement.objects.filter(user=self.challenger, code='duel_winner').exists()
        )

    def test_decline_duel(self):
        self.client.force_authenticate(self.challenger)
        response = self.client.post('/api/gamification/duels/', {
            'opponent_id': self.opponent.id,
        }, format='json')
        duel_id = response.data['id']

        self.client.force_authenticate(self.opponent)
        response = self.client.post(f'/api/gamification/duels/{duel_id}/respond/', {'action': 'decline'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Duel.objects.get(id=duel_id).status, 'declined')

    def test_cannot_duel_self(self):
        self.client.force_authenticate(self.challenger)
        response = self.client.post('/api/gamification/duels/', {
            'opponent_id': self.challenger.id,
        }, format='json')
        self.assertEqual(response.status_code, 400)
