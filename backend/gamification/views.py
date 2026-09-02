from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from subjects.models import Question, Subject
from tests.models import TestSession, TestSessionQuestion
from users.models import User
from django.contrib.auth import get_user_model

from .models import Duel
from .services import (
    achievements_payload, check_achievements,
    expire_stale_duels, resolve_duel, resolve_user_duels,
)

User = get_user_model()

DUEL_TIME_LIMIT = 600  # 10 минут на дуэль


class AchievementsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Self-healing: пересчитываем при каждом запросе (идемпотентно)
        check_achievements(request.user)
        return Response(achievements_payload(request.user))


class OpponentsView(APIView):
    """Список учеников для выбора соперника дуэли."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ('student', 'teacher', 'admin'):
            return Response({'error': 'Доступ запрещён'}, status=403)
        search = request.query_params.get('search', '').strip()
        qs = User.objects.filter(role='student', is_active=True).exclude(pk=request.user.pk)
        if search:
            qs = qs.filter(
                Q(full_name__icontains=search) | Q(username__icontains=search)
            )
        return Response([
            {'id': u.id, 'username': u.username, 'full_name': u.full_name or u.username}
            for u in qs.order_by('full_name')[:50]
        ])


def _pick_duel_questions(user, subject_id=None, num=10):
    """Набор вопросов для дуэли: без matching (медленный тип), с fallback."""
    base = Question.objects.filter(topic__subject__is_visible=True).exclude(question_type='matching')
    if subject_id:
        base = base.filter(topic__subject_id=subject_id)
    else:
        profile_ids = list(user.profile_subjects.values_list('id', flat=True))
        if profile_ids:
            base = base.filter(
                Q(topic__subject__subject_type='mandatory') | Q(topic__subject_id__in=profile_ids)
            )

    questions = list(base.filter(verification_status='verified').order_by('?')[:num])
    if len(questions) < num:
        extra = num - len(questions)
        questions.extend(
            base.exclude(id__in=[q.id for q in questions]).order_by('?')[:extra]
        )
    return questions[:num]


class DuelListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        expire_stale_duels()
        duels = (
            Duel.objects.filter(Q(challenger=request.user) | Q(opponent=request.user))
            .select_related('challenger', 'opponent', 'subject',
                            'challenger_session', 'opponent_session')
            .order_by('-created_at')[:60]
        )
        # Лениво доигрываем завершившиеся дуэли
        for d in duels:
            resolve_duel(d)

        data = []
        for d in duels:
            my_session, opp_session = (
                (d.challenger_session, d.opponent_session)
                if d.challenger_id == request.user.id
                else (d.opponent_session, d.challenger_session)
            )
            opponent = d.opponent if d.challenger_id == request.user.id else d.challenger
            data.append({
                'id': d.id,
                'opponent': {'id': opponent.id, 'full_name': opponent.full_name or opponent.username} if opponent else None,
                'subject': {'id': d.subject.id, 'name': d.subject.name, 'icon': d.subject.icon} if d.subject else None,
                'num_questions': d.num_questions,
                'status': d.status,
                'status_display': d.get_status_display(),
                'i_am_challenger': d.challenger_id == request.user.id,
                'my_score': my_session.earned_points if my_session and my_session.is_completed else None,
                'opp_score': opp_session.earned_points if opp_session and opp_session.is_completed else None,
                'my_done': bool(my_session and my_session.is_completed),
                'i_won': d.winner_id == request.user.id if d.winner else False,
                'is_draw': d.is_draw,
                'winner_name': (d.winner.full_name or d.winner.username) if d.winner else None,
                'created_at': d.created_at.strftime('%d.%m %H:%M'),
                'can_accept': d.status == 'pending' and d.challenger_id != request.user.id
                              and (d.opponent_id is None or d.opponent_id == request.user.id),
                'can_play': d.status == 'active' and not (my_session and my_session.is_completed),
            })
        return Response(data)

    def post(self, request):
        if request.user.role not in ('student', 'teacher', 'admin'):
            return Response({'error': 'Дуэли доступны ученикам'}, status=403)

        opponent_id = request.data.get('opponent_id')
        subject_id = request.data.get('subject_id')
        try:
            num_questions = int(request.data.get('num_questions', 10))
        except (TypeError, ValueError):
            num_questions = 10
        num_questions = max(5, min(30, num_questions))

        opponent = None
        if opponent_id is not None:
            try:
                opponent = User.objects.get(id=opponent_id, role='student')
            except User.DoesNotExist:
                return Response({'error': 'Соперник не найден'}, status=400)
            if opponent.id == request.user.id:
                return Response({'error': 'Нельзя вызвать самого себя'}, status=400)

        subject = None
        if subject_id:
            subject = Subject.objects.filter(id=subject_id).first()
            if not subject:
                return Response({'error': 'Предмет не найден'}, status=400)

        questions = _pick_duel_questions(request.user, subject_id, num_questions)
        if len(questions) < 5:
            return Response({'error': 'Недостаточно вопросов для дуэли'}, status=400)

        duel = Duel.objects.create(
            challenger=request.user,
            opponent=opponent,
            subject=subject,
            question_ids=[q.id for q in questions],
            num_questions=len(questions),
        )
        return Response({'id': duel.id, 'status': duel.status}, status=201)


class DuelRespondView(APIView):
    """Ответ на дуэль: accept / decline / cancel."""
    permission_classes = [IsAuthenticated]

    def post(self, request, duel_id):
        duel = get_object_or_404(Duel, id=duel_id)
        action = request.data.get('action')

        if action == 'accept':
            if duel.status != 'pending':
                return Response({'error': 'Дуэль уже не активна'}, status=400)
            if duel.challenger_id == request.user.id:
                return Response({'error': 'Нельзя принять свою дуэль'}, status=400)
            if duel.opponent_id and duel.opponent_id != request.user.id:
                return Response({'error': 'Эта дуэль адресована другому'}, status=403)
            duel.opponent = request.user
            duel.status = 'active'
            duel.save()
            return Response({'status': duel.status})

        if action == 'decline':
            if duel.status != 'pending':
                return Response({'error': 'Дуэль уже не активна'}, status=400)
            if duel.opponent_id != request.user.id:
                return Response({'error': 'Нет прав на отклонение'}, status=403)
            duel.status = 'declined'
            duel.save()
            return Response({'status': duel.status})

        if action == 'cancel':
            if duel.status != 'pending' or duel.challenger_id != request.user.id:
                return Response({'error': 'Отменить может только автор активной дуэли'}, status=403)
            duel.status = 'expired'
            duel.save()
            return Response({'status': duel.status})

        return Response({'error': 'Неизвестное действие'}, status=400)


class DuelPlayView(APIView):
    """Создаёт (или возвращает) сессию текущего игрока дуэли.

    Идемпотентно: повторный вызов возвращает ту же незавершённую сессию.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, duel_id):
        from tests.views import _build_question_data, _expire_session

        duel = get_object_or_404(Duel, id=duel_id)
        is_challenger = duel.challenger_id == request.user.id
        is_opponent = duel.opponent_id == request.user.id
        if not (is_challenger or is_opponent):
            return Response({'error': 'Вы не участник этой дуэли'}, status=403)
        if duel.status != 'active':
            return Response({'error': 'Дуэль не в активной стадии'}, status=400)

        my_session = duel.challenger_session if is_challenger else duel.opponent_session
        if my_session and my_session.is_completed:
            return Response({'already_completed': True, 'session_id': my_session.id}, status=409)
        if my_session:
            # Сессия могла истечь по таймеру
            from tests.views import _session_expired
            if _session_expired(my_session):
                _expire_session(my_session)
                resolve_duel(duel)
                return Response({'already_completed': True, 'session_id': my_session.id}, status=409)
        else:
            questions = list(Question.objects.in_bulk(duel.question_ids).values())
            order = {qid: i for i, qid in enumerate(duel.question_ids)}
            questions.sort(key=lambda q: order.get(q.id, 0))
            if len(questions) != len(duel.question_ids):
                return Response({'error': 'Вопросы дуэли повреждены'}, status=400)

            my_session = TestSession.objects.create(
                student=request.user,
                subject=duel.subject,
                total_questions=len(questions),
                time_limit=DUEL_TIME_LIMIT,
                mode='duel',
                duel=duel,
                total_points=sum(q.points for q in questions),
            )
            TestSessionQuestion.objects.bulk_create([
                TestSessionQuestion(session=my_session, question=q, position=i + 1)
                for i, q in enumerate(questions)
            ])
            if is_challenger:
                duel.challenger_session = my_session
            else:
                duel.opponent_session = my_session
            duel.save(update_fields=['challenger_session', 'opponent_session'])

        questions = [sq.question for sq in my_session.session_questions.select_related('question').all()]
        return Response({
            'session_id': my_session.id,
            'duel_id': duel.id,
            'total_questions': my_session.total_questions,
            'questions': _build_question_data(questions, request),
            'time_limit': my_session.time_limit,
            'total_points': my_session.total_points,
        })
