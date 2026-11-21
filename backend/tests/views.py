import json
import re
import urllib.request
import urllib.error
from decimal import Decimal, InvalidOperation
from django.conf import settings

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Q

from subjects.models import Question, Answer, Subject, Topic
from subjects.serializers import QuestionDetailSerializer
from subjects.permissions import IsTeacherOrAdmin
from core.choices import TrackChoices
from core.tracks import (available_tracks, can_use_subject, filter_subjects_for_user,
                         requires_track, student_track)
from subjects.trial_variants import (
    ENT_TRIAL_SLUGS, TRIAL_SLUGS,
    trial_topic_role as _trial_topic_role,
    trial_topics as _trial_topics,
)
from users.models import User, StudyGroup
from .access import can_take_subject
from .models import TestSession, TestSessionQuestion, TestSectionResult, AnswerRecord, TrialAccess
from .serializers import (
    StartTestSerializer, StartEntSerializer, StartTrialSerializer, AnswerBulkSerializer,
    AnswerRecordCreateSerializer,
    TestSessionListSerializer, TestSessionDetailSerializer,
    TeacherTestSessionListSerializer, TeacherTestSessionDetailSerializer,
)


ENT_SECTION_CONFIG = {
    'history':  {'count': 20, 'section_label': 'История Казахстана', 'subject_slug': 'history'},
    'reading':  {'count': 10, 'section_label': 'Грамотность чтения', 'subject_slug': 'reading'},
    'math_lit': {'count': 10, 'section_label': 'Математическая грамотность', 'subject_slug': 'math_profile'},
}

# Профильные предметы, которые ученик выбирает в окне старта ЕНТ-пробника.
TRIAL_PROFILE_SLUGS = ('math', 'physics', 'geography')
TRIAL_PROFILE_ROLE = {'math': 'math', 'physics': 'physics', 'geography': 'geography'}


def _build_question_data(questions, request):
    request_scheme = request.scheme
    host = request.get_host()

    def build_url(image_field):
        if not image_field:
            return None
        return f'{request_scheme}://{host}{image_field.url}'

    result = []
    for q in questions:
        answers = q.answers.all()
        # У короткого ответа `answers` — это эталон, а не варианты: отдать его
        # вместе с вопросом значит показать ученику ключ до ответа.
        visible_answers = [] if q.question_type == 'short_answer' else [
            {'id': a.id, 'text': a.text, 'image': build_url(a.image) if a.image else None}
            for a in answers
        ]
        result.append({
            'id': q.id,
            'text': q.text,
            'question_type': q.question_type,
            'points': q.points,
            'section': q.section,
            'topic': q.topic.name,
            'difficulty': q.difficulty,
            'image': build_url(q.image) if q.image else (q.image_ref if q.image_ref and '/' in q.image_ref else None),
            'answers': visible_answers,
            'matching_options': list(dict.fromkeys(
                a.text.rsplit(' → ', 1)[1]
                for a in answers if ' → ' in a.text
            )) if q.question_type == 'matching' else [],
        })
    return result


def _score_single_choice(question, selected_id):
    correct = question.answers.filter(is_correct=True)
    if correct and correct.first().id == selected_id:
        return question.points, question.points
    return 0, question.points


def _score_multiple_choice(question, selected_ids):
    correct_ids = set(question.answers.filter(is_correct=True).values_list('id', flat=True))
    selected = set(selected_ids)
    if not correct_ids:
        return 0, question.points
    correct_selected = len(correct_ids & selected)
    wrong_selected = len(selected - correct_ids)
    points_per_correct = question.points / len(correct_ids)
    earned = max(0, (correct_selected - wrong_selected) * points_per_correct)
    return round(earned, 1), question.points


def _score_matching(question, pairs):
    correct_pairs = {
        str(answer.id): answer.text.rsplit(' → ', 1)[1]
        for answer in question.answers.filter(is_correct=True)
        if ' → ' in answer.text
    }
    if not correct_pairs:
        return 0, question.points
    correct_count = sum(
        1 for left_id, right_text in pairs.items()
        if correct_pairs.get(str(left_id)) == right_text
    )
    earned = (correct_count / len(correct_pairs)) * question.points
    return round(earned, 1), question.points


def _normalize_short_answer(value):
    """Приводит ответ к сравнимому виду.

    В формах NUET эталоны записаны по-разному: «B=76», «x=2.3», «3/2» и «1.5»
    как два допустимых варианта, «(7, 10)». Ученик печатает с пробелами,
    запятой вместо точки и в другом регистре — это тот же ответ. Дроби
    специально не вычисляем: если нужен эквивалент, его добавляют вторым
    эталоном в форме.
    """
    text = (value or '').strip().casefold()
    text = (text.replace('ё', 'е')
                .replace('−', '-').replace('–', '-').replace('—', '-'))
    text = text.replace(',', '.')
    text = re.sub(r'\s+', '', text)
    return text.rstrip('.')


def _score_short_answer(question, text_answer):
    expected = [a.text for a in question.answers.filter(is_correct=True)]
    given = _normalize_short_answer(text_answer)
    if not expected or not given:
        return 0, question.points
    accepted = {_normalize_short_answer(value) for value in expected}
    if given in accepted:
        return question.points, question.points
    # «1,50» и «1,5» — одна и та же величина, но строки разные. Сравниваем
    # числами то, что числами и является; дроби вроде «3/2» остаются строками
    # (их эквивалент добавляют вторым эталоном в форме).
    try:
        given_number = Decimal(given)
    except InvalidOperation:
        return 0, question.points
    for value in accepted:
        try:
            if Decimal(value) == given_number:
                return question.points, question.points
        except InvalidOperation:
            continue
    return 0, question.points


def _score_question(question, selected_answer=None, selected_answers=None, matching_pairs=None,
                    text_answer=''):
    if question.question_type == 'single_choice':
        return _score_single_choice(question, selected_answer)
    if question.question_type == 'multiple_choice':
        return _score_multiple_choice(question, selected_answers or [])
    if question.question_type == 'matching':
        return _score_matching(question, matching_pairs or {})
    if question.question_type == 'short_answer':
        return _score_short_answer(question, text_answer)
    return 0, question.points


RUSH_QUESTIONS = 30
RUSH_TIME_LIMIT = 300  # 5 минут


def _pick_questions(base_qs, num_questions):
    """Предпочитаем проверенные вопросы; если их мало — добираем остальные.

    Открытые задачи банка оцифровки (401 строка) отсядаются: см. QuestionQuerySet.answerable.
    """
    base_qs = base_qs.answerable()
    questions = list(base_qs.filter(verification_status='verified').order_by('?')[:num_questions])
    if len(questions) < num_questions:
        extra = num_questions - len(questions)
        questions.extend(
            base_qs.exclude(id__in=[q.id for q in questions]).order_by('?')[:extra]
        )
    return questions


class StartTestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = StartTestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        mode = serializer.validated_data.get('mode', 'standard')
        topic_ids = serializer.validated_data.get('topic_ids') or []

        if mode == 'rush':
            return self._start_rush(request)

        subject_id = serializer.validated_data.get('subject_id')
        subject = get_object_or_404(Subject, id=subject_id)

        # 11-классник без трека: новые тесты не стартуют, пока не выбран ЕНТ/NUET.
        # Старые уроки и результаты это не трогает — блокируется только каталог.
        if requires_track(request.user):
            return Response(
                {'error': 'Выберите трек: ЕНТ или NUET', 'code': 'track_required'},
                status=status.HTTP_403_FORBIDDEN,
            )
        # Предмет чужого трека — не «невидимый», а именно недоступный: id приходит
        # из запроса, и обойти каталог прямым вызовом нельзя.
        if not can_use_subject(request.user, subject):
            return Response(
                {'error': 'Этот предмет относится к другому треку'},
                status=status.HTTP_403_FORBIDDEN,
            )
        # Прямая ссылка на /test/start/<id> не должна обходить расписание.
        if (getattr(request.user, 'role', '') == 'student'
                and not can_take_subject(request.user, subject)):
            return Response(
                {'error': 'Пробный тест сейчас недоступен'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Ученики не стартуют скрытые предметы (учителя/админы — могут для проверки)
        if getattr(request.user, 'role', '') == 'student' and not subject.is_visible:
            return Response(
                {'error': 'Этот предмет сейчас недоступен'},
                status=status.HTTP_403_FORBIDDEN,
            )

        num_questions = serializer.validated_data.get('num_questions') or subject.question_count
        time_limit = subject.time_limit

        base_qs = Question.objects.filter(topic__subject_id=subject_id)
        if topic_ids:
            base_qs = base_qs.filter(topic_id__in=topic_ids)
            # При тренировке по темам разрешаем больше вопросов, чем в предмете по умолчанию
            if not serializer.validated_data.get('num_questions'):
                num_questions = min(max(len(topic_ids) * 5, 10), 40)

        questions = _pick_questions(base_qs, num_questions)

        if not questions:
            return Response(
                {'error': 'По выбранным темам нет вопросов'},
                status=status.HTTP_400_BAD_REQUEST
            )

        session = TestSession.objects.create(
            student=request.user,
            subject_id=subject_id,
            total_questions=len(questions),
            time_limit=time_limit,
        )
        TestSessionQuestion.objects.bulk_create([
            TestSessionQuestion(session=session, question=question, position=position)
            for position, question in enumerate(questions, start=1)
        ])

        question_data = _build_question_data(questions, request)

        return Response({
            'session_id': session.id,
            'total_questions': len(questions),
            'questions': question_data,
            'time_limit': time_limit,
        })

    def _start_rush(self, request):
        """Question Rush: 30 быстрых вопросов за 5 минут, без matching."""
        user = request.user
        if getattr(user, 'role', '') == 'student':
            if requires_track(user):
                return Response(
                    {'error': 'Выберите трек: ЕНТ или NUET', 'code': 'track_required'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            # Rush — игра ЕНТ-подготовки. Школе и NUET её не показывают и не
            # запускают: тратить 5 минут на чужие вопросы ученику незачем.
            if student_track(user) in (TrackChoices.SCHOOL, TrackChoices.NUET) and TrackChoices.ENT not in available_tracks(user):
                return Response(
                    {'error': 'Question Rush доступен только в треке ЕНТ'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            profile_ids = list(user.profile_subjects.values_list('id', flat=True))
            subjects = filter_subjects_for_user(Subject.objects.filter(is_visible=True), user)
            if profile_ids:
                subjects = subjects.filter(
                    Q(subject_type='mandatory') | Q(id__in=profile_ids)
                )
            subject_ids = list(subjects.values_list('id', flat=True))
        else:
            subject_ids = list(
                Subject.objects.filter(is_visible=True).values_list('id', flat=True)
            )

        base_qs = Question.objects.filter(
            topic__subject_id__in=subject_ids,
        ).exclude(question_type='matching')

        questions = _pick_questions(base_qs, RUSH_QUESTIONS)
        if len(questions) < RUSH_QUESTIONS:
            return Response(
                {'error': f'Недостаточно вопросов для Rush. Доступно: {len(questions)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session = TestSession.objects.create(
            student=request.user,
            total_questions=RUSH_QUESTIONS,
            time_limit=RUSH_TIME_LIMIT,
            mode='rush',
        )
        TestSessionQuestion.objects.bulk_create([
            TestSessionQuestion(session=session, question=question, position=position)
            for position, question in enumerate(questions, start=1)
        ])

        return Response({
            'session_id': session.id,
            'mode': 'rush',
            'total_questions': RUSH_QUESTIONS,
            'questions': _build_question_data(questions, request),
            'time_limit': RUSH_TIME_LIMIT,
        })


class StartEntView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = StartEntSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        profile1_id = serializer.validated_data['profile1_id']
        profile2_id = serializer.validated_data['profile2_id']

        try:
            profile1_subj = Subject.objects.get(id=profile1_id)
            profile2_subj = Subject.objects.get(id=profile2_id)
        except Subject.DoesNotExist:
            return Response({'error': 'Предмет не найден'}, status=status.HTTP_400_BAD_REQUEST)

        # Тот же запрет, что в StartTestView: id предмета приходит из запроса, а не
        # из меню ученика, поэтому скрытый предмет нельзя протащить в симуляцию ЕНТ.
        if getattr(request.user, 'role', '') == 'student':
            if requires_track(request.user):
                return Response(
                    {'error': 'Выберите трек: ЕНТ или NUET', 'code': 'track_required'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if student_track(request.user) in (TrackChoices.SCHOOL, TrackChoices.NUET) and TrackChoices.ENT not in available_tracks(request.user):
                return Response(
                    {'error': 'Полная симуляция ЕНТ доступна только в треке ЕНТ'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            # Фиксированные секции ищутся по слагу и на видимость не смотрят:
            # пока старый банк скрыт, симуляция выдала бы ровно его, в обход
            # каталога. Проверяем те же слаги, что и выборка ниже.
            hidden_sections = [
                cfg['section_label'] for cfg in ENT_SECTION_CONFIG.values()
                if not Subject.objects.filter(
                    slug=cfg['subject_slug'], is_visible=True).exists()
            ]
            if hidden_sections:
                return Response(
                    {'error': 'Полная симуляция ЕНТ временно недоступна: '
                              'база обязательных предметов скрыта'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            for subj in (profile1_subj, profile2_subj):
                if not subj.is_visible:
                    return Response(
                        {'error': 'Этот предмет сейчас недоступен'},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                if not can_use_subject(request.user, subj):
                    return Response(
                        {'error': 'Этот предмет относится к другому треку'},
                        status=status.HTTP_403_FORBIDDEN,
                    )

        selected = {}
        selected_question_ids = set()
        sections_order = ['history', 'reading', 'math_lit', 'profile1', 'profile2']

        # Фиксированные секции — предпочитаем verified, но берём любые
        for sect, cfg in ENT_SECTION_CONFIG.items():
            qs = list(Question.objects.filter(
                topic__subject__slug=cfg['subject_slug'],
                verification_status='verified',
            ).answerable().exclude(id__in=selected_question_ids).order_by('?')[:cfg['count']])
            if len(qs) < cfg['count']:
                extra = cfg['count'] - len(qs)
                extra_qs = Question.objects.filter(
                    topic__subject__slug=cfg['subject_slug'],
                ).answerable().exclude(id__in=selected_question_ids | {q.id for q in qs}).order_by('?')[:extra]
                qs.extend(extra_qs)
            selected[sect] = qs
            selected_question_ids.update(q.id for q in qs)

        # Профильные предметы
        for sect, subj_id, subj_obj in [
            ('profile1', profile1_id, profile1_subj),
            ('profile2', profile2_id, profile2_subj),
        ]:
            qs = list(Question.objects.filter(
                topic__subject_id=subj_id,
                verification_status='verified',
            ).answerable().exclude(id__in=selected_question_ids).order_by('?')[:40])
            if len(qs) < 40:
                extra = 40 - len(qs)
                extra_qs = Question.objects.filter(
                    topic__subject_id=subj_id,
                ).answerable().exclude(id__in=selected_question_ids | {q.id for q in qs}).order_by('?')[:extra]
                qs.extend(extra_qs)
            selected[sect] = qs
            selected_question_ids.update(q.id for q in qs)

        # Проверка
        for sect, qs in selected.items():
            expected = 20 if sect == 'history' else 10 if sect in ('reading', 'math_lit') else 40
            if len(qs) < expected:
                return Response({
                    'error': f'Недостаточно вопросов для секции "{sect}". Нужно {expected}, доступно {len(qs)}'
                }, status=status.HTTP_400_BAD_REQUEST)

        # Создаём сессию
        all_questions = []
        for sect in sections_order:
            all_questions.extend(selected[sect])

        session = TestSession.objects.create(
            student=request.user,
            total_questions=len(all_questions),
            time_limit=14400,
            is_ent=True,
            total_points=sum(q.points for q in all_questions),
            ent_data={
                'profile1': {'id': profile1_id, 'name': profile1_subj.name},
                'profile2': {'id': profile2_id, 'name': profile2_subj.name},
            },
        )
        session_questions = []
        position = 1
        for sect in sections_order:
            for question in selected[sect]:
                session_questions.append(
                    TestSessionQuestion(
                        session=session, question=question, position=position, section=sect,
                    )
                )
                position += 1
        TestSessionQuestion.objects.bulk_create(session_questions)

        # Создаём section results
        for sect in sections_order:
            qs = selected[sect]
            subj = profile1_subj if sect == 'profile1' else profile2_subj if sect == 'profile2' else None
            TestSectionResult.objects.create(
                session=session,
                section=sect,
                subject=subj,
                total_questions=len(qs),
                points_max=sum(q.points for q in qs),
            )

        question_data = _build_question_data(all_questions, request)

        # Добавляем информацию о секциях
        sections_info = []
        idx = 0
        for sect in sections_order:
            qs = selected[sect]
            sections_info.append({
                'id': sect,
                'label': dict(Question.SECTION_CHOICES).get(sect, sect),
                'start': idx + 1,
                'end': idx + len(qs),
                'count': len(qs),
                'points_max': sum(q.points for q in qs),
            })
            idx += len(qs)

        return Response({
            'session_id': session.id,
            'total_questions': len(all_questions),
            'total_points': session.total_points,
            'time_limit': session.time_limit,
            'sections': sections_info,
            'questions': question_data,
        })


class TrialProfileOptionsView(APIView):
    """Какие профильные предметы доступны в конкретном ЕНТ-пробнике."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        subject_id = request.query_params.get('subject_id')
        subject = Subject.objects.filter(id=subject_id, slug__in=ENT_TRIAL_SLUGS).first()
        if not subject:
            return Response({'error': 'Пробный вариант не найден'}, status=status.HTTP_404_NOT_FOUND)
        result = []
        for profile in Subject.objects.filter(slug__in=TRIAL_PROFILE_SLUGS).order_by('sort_order', 'name'):
            role = TRIAL_PROFILE_ROLE[profile.slug]
            topics = _trial_topics(subject, role)
            count = Question.objects.filter(topic__in=topics).answerable().count()
            result.append({
                'id': profile.id, 'slug': profile.slug, 'name': profile.name,
                'questions': count, 'available': count > 0,
            })
        return Response(result)


class StartTrialView(APIView):
    """ЕНТ-пробник: история + матграмотность + два выбранных профильных предмета."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = StartTrialSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        subject = Subject.objects.filter(
            id=serializer.validated_data['subject_id'],
            slug__in=ENT_TRIAL_SLUGS,
        ).first()
        if not subject:
            return Response({'error': 'Пробный вариант не найден'}, status=status.HTTP_404_NOT_FOUND)
        if getattr(request.user, 'role', '') == 'student' and not subject.is_visible:
            return Response({'error': 'Этот предмет сейчас недоступен'},
                            status=status.HTTP_403_FORBIDDEN)
        if not can_use_subject(request.user, subject):
            return Response({'error': 'Этот предмет относится к другому треку'},
                            status=status.HTTP_403_FORBIDDEN)
        if (getattr(request.user, 'role', '') == 'student'
                and not can_take_subject(request.user, subject)):
            return Response({'error': 'Пробный тест сейчас недоступен'},
                            status=status.HTTP_403_FORBIDDEN)

        profiles = list(Subject.objects.filter(id__in=serializer.validated_data['profile_ids']))
        if len(profiles) != 2:
            return Response({'error': 'Выберите два профильных предмета'},
                            status=status.HTTP_400_BAD_REQUEST)
        chosen = []
        for profile in profiles:
            role = TRIAL_PROFILE_ROLE.get(profile.slug)
            if not role:
                return Response({'error': f'«{profile.name}» не профильный предмет'},
                                status=status.HTTP_400_BAD_REQUEST)
            chosen.append((role, profile))
        if len({role for role, _ in chosen}) != 2:
            return Response({'error': 'Выберите разные профильные предметы'},
                            status=status.HTTP_400_BAD_REQUEST)

        selected = {}
        labels = {}
        for role in ('history', 'math_lit'):
            topics = _trial_topics(subject, role)
            need = 20 if role == 'history' else 10
            qs = _pick_questions(Question.objects.filter(topic__in=topics), need)
            if len(qs) < need:
                return Response({
                    'error': f'В варианте не хватает вопросов: {role} — '
                             f'нужно {need}, есть {len(qs)}',
                }, status=status.HTTP_400_BAD_REQUEST)
            selected[role] = qs
            labels[role] = topics[0].name if topics else role

        for role, profile in chosen:
            qs = _pick_questions(
                Question.objects.filter(topic__in=_trial_topics(subject, role)), 40)
            if not qs:
                return Response({
                    'error': f'По предмету «{profile.name}» в этом варианте '
                             f'пока нет вопросов',
                }, status=status.HTTP_400_BAD_REQUEST)
            selected[role] = qs
            labels[role] = profile.name

        section_keys = {'history': 'history', 'math_lit': 'math_lit',
                        chosen[0][0]: 'profile1', chosen[1][0]: 'profile2'}
        order = ['history', 'math_lit', chosen[0][0], chosen[1][0]]
        all_questions = []
        for role in order:
            all_questions.extend(selected[role])

        session = TestSession.objects.create(
            student=request.user,
            subject=subject,
            total_questions=len(all_questions),
            time_limit=subject.time_limit,
            total_points=sum(q.points for q in all_questions),
        )
        TestSessionQuestion.objects.bulk_create([
            TestSessionQuestion(
                session=session, question=question, position=position,
                section=section_keys[role],
            )
            for role in order
            for position, question in enumerate(selected[role],
                                                start=1 + sum(len(selected[r]) for r in order[:order.index(role)]))
        ])

        sections_info = []
        idx = 0
        for role in order:
            qs = selected[role]
            sections_info.append({
                'id': section_keys[role],
                'label': labels[role],
                'start': idx + 1,
                'end': idx + len(qs),
                'count': len(qs),
                'points_max': sum(q.points for q in qs),
            })
            idx += len(qs)

        return Response({
            'session_id': session.id,
            'total_questions': len(all_questions),
            'total_points': session.total_points,
            'time_limit': session.time_limit,
            'sections': sections_info,
            'questions': _build_question_data(all_questions, request),
        })


def _save_answer_record(session, question, selected_answer=None, selected_answers=None,
                        matching_pairs=None, text_answer=''):
    earned, max_pts = _score_question(question, selected_answer, selected_answers,
                                      matching_pairs, text_answer)
    is_correct = earned >= max_pts and max_pts > 0

    record, created = AnswerRecord.objects.update_or_create(
        session=session,
        question=question,
        defaults={
            'selected_answer_id': selected_answer,
            'selected_answers': selected_answers or [],
            'matching_pairs': matching_pairs or {},
            'text_answer': (text_answer or '')[:500],
            'is_correct': is_correct,
            'points_earned': earned,
            'points_max': max_pts,
        },
    )
    return record


def _recalc_session(session):
    answers = session.answers.select_related('question__topic__subject').all()
    correct_count = answers.filter(is_correct=True).count()
    earned = sum(a.points_earned for a in answers)
    total = sum(a.points_max for a in answers)

    session.correct_answers = correct_count
    session.earned_points = earned
    # Максимум — это все выданные в сессию вопросы, а не только те, на которые
    # успели ответить. Иначе в результате было бы «2 из 5» при 90 вопросах.
    session.total_points = max(session.total_points, total)
    session.calculate_score()

    # Обновляем section results
    legacy_sections = {}
    if session.is_ent and not session.session_questions.exists():
        profile1_id = session.ent_data.get('profile1', {}).get('id')
        profile2_id = session.ent_data.get('profile2', {}).get('id')
        for answer in answers:
            subject = answer.question.topic.subject
            if subject.slug == 'history':
                section = 'history'
            elif subject.slug == 'reading':
                section = 'reading'
            elif subject.slug == 'math_profile':
                section = 'math_lit'
            elif subject.id == profile1_id:
                section = 'profile1'
            elif subject.id == profile2_id:
                section = 'profile2'
            else:
                continue
            legacy_sections.setdefault(section, []).append(answer.id)

    for sr in session.section_results.all():
        if legacy_sections:
            qs = answers.filter(id__in=legacy_sections.get(sr.section, []))
        else:
            question_ids = session.session_questions.filter(section=sr.section).values('question_id')
            qs = answers.filter(question_id__in=question_ids)
        sr.answered = qs.count()
        sr.correct_answers = qs.filter(is_correct=True).count()
        sr.points_earned = sum(a.points_earned for a in qs)
        sr.points_max = sum(a.points_max for a in qs)
        sr.save()


def _session_expired(session):
    return timezone.now() >= session.started_at + timezone.timedelta(seconds=session.time_limit)


def _expire_session(session):
    _recalc_session(session)
    session.completed_at = timezone.now()
    session.is_completed = True
    session.save()
    _on_session_completed(session)


def _session_access_error(session, user):
    """После дедлайна ответы не принимаем, пока тренер не откроет доступ."""
    if session.subject_id and not can_take_subject(user, session.subject):
        return Response({'error': 'Срок прохождения теста истёк'},
                        status=status.HTTP_403_FORBIDDEN)
    return None


def _on_session_completed(session):
    """Пост-обработка завершённой сессии: достижения и дуэли."""
    try:
        from gamification.services import check_achievements, resolve_user_duels
        check_achievements(session.student)
        resolve_user_duels(session.student)
    except Exception:
        # Геймификация не должна ломать завершение теста
        import logging
        logging.getLogger(__name__).exception('gamification post-processing failed')


def _validate_answer_payload(question, selected_answer, selected_answers, matching_pairs,
                             text_answer=''):
    if question.question_type == 'short_answer':
        if not (text_answer or '').strip():
            return 'Введите ответ'
        return None
    answer_ids = set(question.answers.values_list('id', flat=True))
    if selected_answer is not None and selected_answer not in answer_ids:
        return 'Выбранный вариант не относится к вопросу'
    if len(selected_answers) != len(set(selected_answers)) or not set(selected_answers).issubset(answer_ids):
        return 'Выбранные варианты не относятся к вопросу'
    if question.question_type == 'matching':
        correct_pairs = {
            str(answer.id): answer.text.rsplit(' → ', 1)[1]
            for answer in question.answers.filter(is_correct=True)
            if ' → ' in answer.text
        }
        allowed_right_values = set(correct_pairs.values())
        if any(
            str(left_id) not in correct_pairs or right_text not in allowed_right_values
            for left_id, right_text in matching_pairs.items()
        ):
            return 'Пары не относятся к вопросу'
    return None


class SubmitAnswerView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        try:
            session = TestSession.objects.get(id=session_id, student=request.user)
        except TestSession.DoesNotExist:
            return Response({'error': 'Сессия не найдена'}, status=status.HTTP_404_NOT_FOUND)

        access_error = _session_access_error(session, request.user)
        if access_error:
            return access_error

        if session.is_completed:
            return Response({'error': 'Тест уже завершён'}, status=status.HTTP_400_BAD_REQUEST)
        if _session_expired(session):
            _expire_session(session)
            return Response({'error': 'Время теста истекло'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = AnswerRecordCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        question = serializer.validated_data['question']
        selected_answer = serializer.validated_data.get('selected_answer')
        selected_answers = serializer.validated_data.get('selected_answers', [])
        matching_pairs = serializer.validated_data.get('matching_pairs', {})
        text_answer = serializer.validated_data.get('text_answer', '')

        if not session.session_questions.filter(question=question).exists():
            return Response({'error': 'Вопрос не относится к этой попытке'}, status=status.HTTP_400_BAD_REQUEST)

        if question.question_type == 'single_choice' and selected_answer:
            selected_answers = [selected_answer]

        validation_error = _validate_answer_payload(
            question, selected_answer, selected_answers, matching_pairs, text_answer
        )
        if validation_error:
            return Response({'error': validation_error}, status=status.HTTP_400_BAD_REQUEST)

        _save_answer_record(session, question, selected_answer, selected_answers,
                            matching_pairs, text_answer)
        _recalc_session(session)

        return Response({
            'answered': session.answers.count(),
            'total': session.total_questions,
            'correct': session.correct_answers,
            'earned_points': session.earned_points,
        })


class SubmitBulkAnswersView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        try:
            session = TestSession.objects.get(id=session_id, student=request.user)
        except TestSession.DoesNotExist:
            return Response({'error': 'Сессия не найдена'}, status=status.HTTP_404_NOT_FOUND)

        access_error = _session_access_error(session, request.user)
        if access_error:
            return access_error

        if session.is_completed:
            return Response({'error': 'Тест уже завершён'}, status=status.HTTP_400_BAD_REQUEST)
        if _session_expired(session):
            _expire_session(session)
            return Response({'error': 'Время теста истекло'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = AnswerBulkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        prepared_answers = []
        for ans_data in serializer.validated_data['answers']:
            question = ans_data['question']
            selected_answer = ans_data.get('selected_answer')
            selected_answers = ans_data.get('selected_answers', [])
            matching_pairs = ans_data.get('matching_pairs', {})
            text_answer = ans_data.get('text_answer', '')
            if question.question_type == 'single_choice' and selected_answer:
                selected_answers = [selected_answer]
            if not session.session_questions.filter(question=question).exists():
                return Response({'error': 'Вопрос не относится к этой попытке'}, status=status.HTTP_400_BAD_REQUEST)
            validation_error = _validate_answer_payload(
                question, selected_answer, selected_answers, matching_pairs, text_answer
            )
            if validation_error:
                return Response({'error': validation_error}, status=status.HTTP_400_BAD_REQUEST)
            prepared_answers.append((question, selected_answer, selected_answers,
                                     matching_pairs, text_answer))

        with transaction.atomic():
            for prepared in prepared_answers:
                _save_answer_record(session, *prepared)

        _recalc_session(session)

        return Response({
            'answered': session.answers.count(),
            'total': session.total_questions,
            'correct': session.correct_answers,
            'earned_points': session.earned_points,
        })


class FinishTestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        try:
            session = TestSession.objects.get(id=session_id, student=request.user)
        except TestSession.DoesNotExist:
            return Response({'error': 'Сессия не найдена'}, status=status.HTTP_404_NOT_FOUND)

        access_error = _session_access_error(session, request.user)
        if access_error:
            return access_error

        if session.is_completed:
            return Response({'error': 'Тест уже завершён'}, status=status.HTTP_400_BAD_REQUEST)

        if _session_expired(session):
            _expire_session(session)
            return Response({'error': 'Время теста истекло'}, status=status.HTTP_400_BAD_REQUEST)

        _recalc_session(session)
        session.completed_at = timezone.now()
        session.is_completed = True
        session.save()
        _on_session_completed(session)

        return Response({
            'session_id': session.id,
            'total_questions': session.total_questions,
            'correct_answers': session.correct_answers,
            'score_percent': session.score_percent,
            'earned_points': session.earned_points,
            'total_points': session.total_points,
        })


class ResumeTestView(APIView):
    """Продолжить незавершённую сессию вместо создания новой.

    Когда окно доступности закрылось раньше, чем ученик нажал «Завершить»,
    ответы уже сохранены, а сам тест висит незавершённым. После открытия
    доступа человек должен договорить её, а не начинать заново.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, subject_id):
        session = TestSession.objects.filter(
            student=request.user, subject_id=subject_id, is_completed=False,
        ).select_related('subject').order_by('-started_at').first()
        if not session or not session.session_questions.exists():
            return Response({'error': 'Незавершённой попытки нет'},
                            status=status.HTTP_404_NOT_FOUND)
        if not can_take_subject(request.user, session.subject):
            return Response({'error': 'Срок прохождения теста истёк'},
                            status=status.HTTP_403_FORBIDDEN)

        questions = [row.question for row in
                     session.session_questions.select_related('question')]
        answer_map = {}
        for answer in session.answers.all():
            answer_map[answer.question_id] = {
                'selected_answer': answer.selected_answer_id,
                'selected_answers': answer.selected_answers,
                'matching_pairs': answer.matching_pairs,
                'text_answer': answer.text_answer,
            }
        time_left = max(0, session.time_limit
                        - int((timezone.now() - session.started_at).total_seconds()))

        sections = []
        idx = 0
        for result in session.section_results.all().order_by('id'):
            sections.append({
                'id': result.section,
                'label': result.get_section_display(),
                'start': idx + 1,
                'end': idx + result.total_questions,
                'count': result.total_questions,
            })
            idx += result.total_questions

        return Response({
            'session_id': session.id,
            'total_questions': len(questions),
            'questions': _build_question_data(questions, request),
            'sections': sections,
            'time_limit': time_left,
            'answer_map': answer_map,
            'total_points': session.total_points,
        })


class TestStateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        try:
            session = TestSession.objects.get(id=session_id, student=request.user)
        except TestSession.DoesNotExist:
            return Response({'error': 'Сессия не найдена'}, status=status.HTTP_404_NOT_FOUND)

        access_error = _session_access_error(session, request.user)
        if access_error:
            return access_error

        answers = session.answers.all()
        time_elapsed = (timezone.now() - session.started_at).total_seconds()
        time_left = max(0, session.time_limit - int(time_elapsed))

        answered_ids = set()
        flagged_ids = []
        answer_map = {}
        for a in answers:
            answered_ids.add(a.question_id)
            answer_map[a.question_id] = {
                'selected_answer': a.selected_answer_id,
                'selected_answers': a.selected_answers,
                'matching_pairs': a.matching_pairs,
                'text_answer': a.text_answer,
            }

        return Response({
            'session_id': session.id,
            'is_completed': session.is_completed,
            'time_left': time_left,
            'answered': list(answered_ids),
            'flagged': flagged_ids,
            'answer_map': answer_map,
            'earned_points': session.earned_points,
            'total_points': session.total_points,
            'correct_answers': session.correct_answers,
            'total_questions': session.total_questions,
        })


class TestResultView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        try:
            session = TestSession.objects.get(id=session_id, student=request.user)
        except TestSession.DoesNotExist:
            return Response({'error': 'Сессия не найдена'}, status=status.HTTP_404_NOT_FOUND)

        # Legacy ENT sessions predate the immutable section assignment.
        if session.is_ent and not session.session_questions.exists():
            _recalc_session(session)

        serializer = TestSessionDetailSerializer(session)
        return Response(serializer.data)


class StudentTestHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sessions = TestSession.objects.filter(
            student=request.user, is_completed=True
        ).select_related('subject')
        serializer = TestSessionListSerializer(sessions, many=True)
        return Response(serializer.data)


class TeacherTestHistoryView(APIView):
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]

    def get(self, request):
        sessions = TestSession.objects.filter(
            is_completed=True
        ).select_related('subject', 'student')

        student_id = request.query_params.get('student')
        subject_id = request.query_params.get('subject')
        status_param = request.query_params.get('status', 'active')

        # Результаты деактивированных не висят в общей ленте: доступ снят,
        # но история осталась и находится фильтром «Деактивированные».
        if status_param != 'all':
            sessions = sessions.filter(student__is_active=status_param != 'inactive')

        if student_id:
            sessions = sessions.filter(student_id=student_id)
        if subject_id:
            sessions = sessions.filter(subject_id=subject_id)

        sessions = sessions.order_by('-completed_at')
        serializer = TeacherTestSessionListSerializer(sessions, many=True)
        return Response(serializer.data)


class TeacherTestResultView(APIView):
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]

    def get(self, request, session_id):
        try:
            session = TestSession.objects.get(id=session_id)
        except TestSession.DoesNotExist:
            return Response({'error': 'Сессия не найдена'}, status=status.HTTP_404_NOT_FOUND)

        if session.is_ent and not session.session_questions.exists():
            _recalc_session(session)

        serializer = TeacherTestSessionDetailSerializer(session)
        return Response(serializer.data)


class TrialAccessView(APIView):
    """Тренер открывает/закрывает пробник конкретному ученику вручную."""
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]

    def _targets(self, request, from_body=False):
        source = request.data if from_body else request.query_params
        student_id = source.get('student_id')
        subject_id = source.get('subject_id')
        student = User.objects.filter(id=student_id, role='student').first()
        subject = Subject.objects.filter(id=subject_id, slug__in=TRIAL_SLUGS).first()
        if not student or not subject:
            return None, None, Response(
                {'error': 'Ученик или пробный вариант не найден'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return student, subject, None

    def get(self, request):
        subject_id = request.query_params.get('subject_id')
        qs = TrialAccess.objects.select_related('student', 'subject', 'granted_by')
        if subject_id:
            qs = qs.filter(subject_id=subject_id)
        return Response([
            {
                'student_id': row.student_id,
                'student_name': row.student.full_name or row.student.username,
                'subject_id': row.subject_id,
                'subject_name': row.subject.name,
                'granted_by': row.granted_by.username if row.granted_by else '',
                'created_at': row.created_at.isoformat(),
                'note': row.note,
            }
            for row in qs.order_by('-created_at')
        ])

    def post(self, request):
        student, subject, error = self._targets(request, from_body=True)
        if error:
            return error
        access, _ = TrialAccess.objects.get_or_create(
            student=student, subject=subject,
            defaults={
                'granted_by': request.user,
                'note': str(request.data.get('note', ''))[:500],
            },
        )
        return Response({
            'student_id': student.id, 'subject_id': subject.id,
            'is_open': True, 'created_at': access.created_at.isoformat(),
        }, status=status.HTTP_201_CREATED)

    def delete(self, request):
        student, subject, error = self._targets(request)
        if error:
            return error
        TrialAccess.objects.filter(student=student, subject=subject).delete()
        return Response({'student_id': student.id, 'subject_id': subject.id,
                         'is_open': False})


class TrialAccessStatsView(APIView):
    """Кто сдал и кто не сдал пробник из учеников выбранной группы."""
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]

    def get(self, request):
        group_id = request.query_params.get('group_id')
        subject_id = request.query_params.get('subject_id')
        group = StudyGroup.objects.filter(id=group_id).first()
        subject = Subject.objects.filter(id=subject_id, slug__in=TRIAL_SLUGS).first()
        if not group or not subject:
            return Response({'error': 'Группа или пробный вариант не найден'},
                            status=status.HTTP_404_NOT_FOUND)

        # В отчёте нужны все зарегистрированные в группе, включая тех, у кого
        # доступ уже снят: факт сдачи/несдачи от этого не меняется.
        students = group.students.filter(role='student').order_by('full_name', 'username')
        opened = set(TrialAccess.objects.filter(
            subject=subject, student__in=students).values_list('student_id', flat=True))

        latest = {}
        sessions = TestSession.objects.filter(
            subject=subject, student__in=students, is_completed=True,
        ).select_related('student').order_by('completed_at', 'id')
        for session in sessions:
            latest[session.student_id] = session

        results = []
        for student in students:
            session = latest.get(student.id)
            results.append({
                'student_id': student.id,
                'student_name': student.full_name or student.username,
                'username': student.username,
                'is_active': student.is_active,
                'submitted': session is not None,
                'completed_at': session.completed_at.isoformat() if session else None,
                'score_percent': round(session.score_percent, 1) if session else None,
                'session_id': session.id if session else None,
                'manual_access': student.id in opened,
            })

        submitted = sum(1 for row in results if row['submitted'])
        return Response({
            'group': {'id': group.id, 'name': group.name},
            'subject': {'id': subject.id, 'name': subject.name, 'slug': subject.slug,
                        'available_from': subject.available_from.isoformat()
                        if subject.available_from else None,
                        'available_until': subject.available_until.isoformat()
                        if subject.available_until else None,
                        'is_open_now': subject.is_available_now()},
            'summary': {
                'total': len(results),
                'submitted': submitted,
                'not_submitted': len(results) - submitted,
                'manual_access': len(opened),
            },
            'results': results,
        })


class TestPreviewView(APIView):
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]

    def post(self, request):
        subject_id = request.data.get('subject_id')
        num_questions = request.data.get('num_questions', 24)
        topic_id = request.data.get('topic_id')
        source_type = request.data.get('source_type')

        try:
            subject_id = int(subject_id)
        except (TypeError, ValueError):
            return Response({'error': 'subject_id required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            num_questions = max(1, min(100, int(num_questions)))
        except (TypeError, ValueError):
            num_questions = 24

        qs = Question.objects.filter(topic__subject_id=subject_id)
        if topic_id:
            qs = qs.filter(topic_id=topic_id)
        if source_type:
            qs = qs.filter(source_type=source_type)

        questions = list(qs.order_by('?')[:num_questions])

        if not questions:
            return Response({'error': 'Нет вопросов по заданным фильтрам'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = QuestionDetailSerializer(questions, many=True, context={'request': request})
        return Response({
            'subject_id': subject_id,
            'total_questions': len(questions),
            'questions': serializer.data,
        })


class AuthorialTestListView(APIView):
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]

    def get(self, request):
        from collections import defaultdict
        qs = Question.objects.filter(source_type='authorial').select_related('topic')
        groups = defaultdict(lambda: {'topic': '', 'topic_id': 0, 'subject': '', 'count': 0, 'form_id': ''})
        for q in qs:
            parts = q.external_id.rsplit('/', 1)
            form_id = parts[0] if len(parts) > 1 else q.external_id
            groups[form_id]['topic'] = q.topic.name
            groups[form_id]['topic_id'] = q.topic.id
            groups[form_id]['subject'] = q.topic.subject.name
            groups[form_id]['count'] += 1
            groups[form_id]['form_id'] = form_id

        result = sorted(groups.values(), key=lambda x: -x['count'])
        return Response(result)


class AuthorialTestDetailView(APIView):
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]

    def get(self, request, form_id):
        from subjects.serializers import QuestionDetailSerializer
        qs = Question.objects.filter(source_type='authorial').select_related('topic')
        questions = []
        for q in qs:
            parts = q.external_id.rsplit('/', 1)
            q_form_id = parts[0] if len(parts) > 1 else q.external_id
            if q_form_id == form_id:
                questions.append(q)
        serializer = QuestionDetailSerializer(questions, many=True)
        topic_name = questions[0].topic.name if questions else ''
        subject_name = questions[0].topic.subject.name if questions else ''
        return Response({
            'form_id': form_id,
            'subject': subject_name,
            'topic': topic_name,
            'count': len(questions),
            'questions': serializer.data,
        })


class AuthorialTestDeleteView(APIView):
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]

    def delete(self, request, form_id):
        qs = Question.objects.filter(source_type='authorial')
        deleted = 0
        for q in qs:
            parts = q.external_id.rsplit('/', 1)
            q_form_id = parts[0] if len(parts) > 1 else q.external_id
            if q_form_id == form_id:
                q.delete()
                deleted += 1
        if deleted:
            return Response({'deleted': deleted, 'form_id': form_id})
        return Response({'error': 'Тест не найден'}, status=status.HTTP_404_NOT_FOUND)


class AIExplainView(APIView):
    permission_classes = [IsAuthenticated]
    # Лимит AI-запросов в сутки (для авторизованных — по пользователю)
    from rest_framework.throttling import ScopedRateThrottle
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'ai_explain'

    def post(self, request, session_id):
        answer_id = request.data.get('answer_record_id')
        try:
            session = TestSession.objects.get(id=session_id)
            # Студент может разбирать только свои тесты
            if request.user.role == 'student' and session.student != request.user:
                return Response({'error': 'Доступ запрещён'}, status=403)
            record = AnswerRecord.objects.get(id=answer_id, session=session)
        except (TestSession.DoesNotExist, AnswerRecord.DoesNotExist):
            return Response({'error': 'Не найдено'}, status=404)

        question = record.question

        # Формируем текст ответа ученика
        if record.text_answer:
            selected_text = record.text_answer
        elif record.selected_answer:
            selected_text = record.selected_answer.text
        elif record.selected_answers:
            selected_text = ', '.join(
                Answer.objects.filter(id__in=record.selected_answers).values_list('text', flat=True)
            )
        elif record.matching_pairs:
            selected_text = ', '.join(f'{k}→{v}' for k, v in record.matching_pairs.items())
        else:
            selected_text = '—'

        # Формируем текст правильного ответа
        if question.question_type == 'single_choice':
            correct = question.answers.filter(is_correct=True).first()
            correct_text = correct.text if correct else '—'
        elif question.question_type == 'multiple_choice':
            correct_text = ', '.join(
                question.answers.filter(is_correct=True).values_list('text', flat=True)
            )
        elif question.question_type == 'matching':
            correct_text = ', '.join(
                question.answers.filter(is_correct=True).values_list('text', flat=True)
            )
        elif question.question_type == 'short_answer':
            correct_text = ' или '.join(
                question.answers.filter(is_correct=True).values_list('text', flat=True)
            )
        else:
            correct_text = '—'

        prompt = (
            f"Вопрос: {question.text}\n"
            f"Правильный ответ: {correct_text}\n"
            f"Ответ ученика: {selected_text}\n\n"
            f"Объясни на русском, почему ответ ученика неверный. "
            f"Дай краткое пояснение (3-5 предложений) и подсказку к правильному решению."
        )

        hf_token = getattr(settings, 'HF_API_TOKEN', '')
        gemini_key = getattr(settings, 'GEMINI_API_KEY', '')
        ai_explanation = ''

        system_prompt = 'Ты репетитор по подготовке к ЕНТ. Отвечай кратко, понятно, на русском языке.'
        full_prompt = f'{system_prompt}\n\n{prompt}'

        # Сначала пробуем Gemini (основной)
        if gemini_key:
            try:
                data = json.dumps({
                    'contents': [{
                        'parts': [{'text': full_prompt}]
                    }],
                    'generationConfig': {
                        'maxOutputTokens': 500,
                        'temperature': 0.7,
                    },
                }).encode('utf-8')
                url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}'
                req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    result = json.loads(resp.read())
                    ai_explanation = result['candidates'][0]['content']['parts'][0]['text'].strip()
            except Exception:
                ai_explanation = ''  # fallback to HF

        # Если Gemini не сработал — пробуем Hugging Face
        if not ai_explanation and hf_token:
            try:
                data = json.dumps({
                    'inputs': f'<s>[INST] {full_prompt} [/INST]',
                    'parameters': {'max_new_tokens': 500, 'temperature': 0.7},
                }).encode('utf-8')
                req = urllib.request.Request(
                    'https://router.huggingface.co/hf-inference/models/mistralai/Mistral-7B-Instruct-v0.3',
                    data=data, headers={
                        'Content-Type': 'application/json',
                        'Authorization': f'Bearer {hf_token}',
                    },
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    result = json.loads(resp.read())
                    ai_explanation = result[0]['generated_text'].strip()
                    if '[/INST]' in ai_explanation:
                        ai_explanation = ai_explanation.split('[/INST]')[-1].strip()
            except urllib.error.HTTPError as e:
                body = e.read().decode('utf-8')[:200]
                ai_explanation = f'⚠️ Ошибка AI ({e.code}): {body}'
            except Exception as e:
                ai_explanation = f'⚠️ Ошибка AI-разбора: {str(e)[:100]}'

        return Response({
            'answer_record_id': answer_id,
            'question_text': question.text,
            'correct_answer': correct_text,
            'selected_answer': selected_text,
            'explanation': ai_explanation,
        })
