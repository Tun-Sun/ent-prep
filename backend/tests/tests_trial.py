"""ЕНТ-пробник: выбор двух профильных предметов и общий лимит 3 часа."""
from django.test import TestCase
from rest_framework.test import APIClient

from subjects.models import Answer, Question, Subject, Topic
from tests.models import TestSession, TestSessionQuestion
from users.models import User

STRONG_PASSWORD = 'Str0ng-Test-Pass-2026'


class TrialProfileChoiceTest(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username='trial-choice', password=STRONG_PASSWORD, role='student',
            grade=11, track='ent', full_name='Ахметов Арман')
        self.trial = Subject.objects.create(
            name='Пробные от INTELLECT · ЕНТ 01', slug='ent-01', track='ent',
            is_visible=True, question_count=90, time_limit=10800)
        self.math = Subject.objects.create(name='Математика', slug='math', track='ent', is_visible=True)
        self.physics = Subject.objects.create(name='Физика', slug='physics', track='ent', is_visible=True)
        self.geography = Subject.objects.create(name='География', slug='geography', track='ent', is_visible=True)
        for label, n in [('История Казахстана', 20),
                         ('Пробный тест по Математической грамотности №1', 10),
                         ('Пробный тест по Математике №1', 30),
                         ('Пробный тест по Физике №1', 30)]:
            self._add_topic(label, n)
        self.api = APIClient()
        self.api.force_authenticate(self.student)

    def _add_topic(self, name, count):
        topic = Topic.objects.create(name=name, subject=self.trial)
        for i in range(count):
            q = Question.objects.create(
                text=f'{name} {i}', topic=topic,
                question_type='single_choice', verification_status='verified')
            Answer.objects.create(question=q, text='Верно', is_correct=True)
            Answer.objects.create(question=q, text='Неверно', is_correct=False)

    def test_options_mark_geography_as_unavailable(self):
        response = self.api.get('/api/tests/trial-options/',
                                {'subject_id': self.trial.id})

        self.assertEqual(response.status_code, 200, response.content)
        options = {o['slug']: o for o in response.data}
        self.assertEqual(options['math']['questions'], 30)
        self.assertEqual(options['physics']['questions'], 30)
        self.assertFalse(options['geography']['available'])

    def test_start_builds_four_sections_in_three_hours(self):
        response = self.api.post('/api/tests/start-trial/', {
            'subject_id': self.trial.id,
            'profile_ids': [self.math.id, self.physics.id],
        }, format='json')

        self.assertEqual(response.status_code, 200, response.content)
        data = response.data
        self.assertEqual(data['total_questions'], 90)
        self.assertEqual(data['time_limit'], 10800)
        self.assertEqual([s['label'] for s in data['sections']], [
            'История Казахстана',
            'Пробный тест по Математической грамотности №1',
            'Математика', 'Физика',
        ])
        session = TestSession.objects.get(id=data['session_id'])
        self.assertEqual(session.time_limit, 10800)
        self.assertEqual(
            set(TestSessionQuestion.objects.filter(session=session)
                .values_list('section', flat=True)),
            {'history', 'math_lit', 'profile1', 'profile2'},
        )

    def test_geography_without_questions_is_rejected(self):
        response = self.api.post('/api/tests/start-trial/', {
            'subject_id': self.trial.id,
            'profile_ids': [self.math.id, self.geography.id],
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('География', response.data['error'])
        self.assertEqual(TestSession.objects.count(), 0)

    def test_two_different_profile_subjects_required(self):
        response = self.api.post('/api/tests/start-trial/', {
            'subject_id': self.trial.id,
            'profile_ids': [self.math.id, self.math.id],
        }, format='json')

        self.assertEqual(response.status_code, 400)

    def test_partial_answers_do_not_shrink_max_score(self):
        response = self.api.post('/api/tests/start-trial/', {
            'subject_id': self.trial.id,
            'profile_ids': [self.math.id, self.physics.id],
        }, format='json')
        data = response.data
        question = data['questions'][0]

        self.api.post(f"/api/tests/{data['session_id']}/answer/", {
            'question': question['id'],
            'selected_answer': question['answers'][0]['id'],
        }, format='json')
        finish = self.api.post(f"/api/tests/{data['session_id']}/finish/")

        self.assertEqual(finish.status_code, 200)
        self.assertEqual(finish.data['total_points'], 90)
