from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.utils import timezone

from subjects.models import Question, Answer
from .models import TestSession, AnswerRecord
from .serializers import (
    StartTestSerializer, AnswerRecordCreateSerializer,
    TestSessionListSerializer, TestSessionDetailSerializer
)


class StartTestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = StartTestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        subject_id = serializer.validated_data['subject_id']
        num_questions = serializer.validated_data['num_questions']

        # Выбираем случайные вопросы по предмету
        questions = list(
            Question.objects.filter(topic__subject_id=subject_id)
            .order_by('?')[:num_questions]
        )

        if len(questions) < num_questions:
            return Response(
                {'error': f'Недостаточно вопросов. Доступно: {len(questions)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        session = TestSession.objects.create(
            student=request.user,
            subject_id=subject_id,
            total_questions=num_questions,
        )

        # Возвращаем вопросы с ответами (без указания правильного)
        # Строим абсолютный URL для картинок
        request_scheme = request.scheme
        host = request.get_host()

        def build_url(image_field):
            if not image_field:
                return None
            return f'{request_scheme}://{host}{image_field.url}'

        question_data = []
        for q in questions:
            answers = q.answers.all()
            question_data.append({
                'id': q.id,
                'text': q.text,
                'topic': q.topic.name,
                'difficulty': q.difficulty,
                'image': build_url(q.image) if q.image else None,
                'answers': [
                    {'id': a.id, 'text': a.text, 'image': build_url(a.image) if a.image else None}
                    for a in answers
                ],
            })

        return Response({
            'session_id': session.id,
            'total_questions': num_questions,
            'questions': question_data,
        })


class SubmitAnswerView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        try:
            session = TestSession.objects.get(id=session_id, student=request.user)
        except TestSession.DoesNotExist:
            return Response({'error': 'Сессия не найдена'}, status=status.HTTP_404_NOT_FOUND)

        if session.is_completed:
            return Response({'error': 'Тест уже завершён'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = AnswerRecordCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        question_id = serializer.validated_data['question'].id
        selected_answer_id = serializer.validated_data['selected_answer'].id

        # Проверяем, что вопрос принадлежит предмету этой сессии
        question_belongs = Question.objects.filter(
            id=question_id,
            topic__subject=session.subject,
        ).exists()

        if not question_belongs:
            return Response(
                {'error': 'Вопрос не принадлежит этому предмету'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Проверяем, что ответ ещё не был дан
        if not session.answers.filter(question_id=question_id).exists():
            selected = Answer.objects.get(id=selected_answer_id)
            is_correct = selected.is_correct
            AnswerRecord.objects.create(
                session=session,
                question_id=question_id,
                selected_answer=selected,
                is_correct=is_correct,
            )

        # Пересчитываем правильные ответы
        correct_count = session.answers.filter(is_correct=True).count()
        session.correct_answers = correct_count
        session.calculate_score()

        return Response({
            'answered': session.answers.count(),
            'total': session.total_questions,
            'correct': correct_count,
        })


class FinishTestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        try:
            session = TestSession.objects.get(id=session_id, student=request.user)
        except TestSession.DoesNotExist:
            return Response({'error': 'Сессия не найдена'}, status=status.HTTP_404_NOT_FOUND)

        if session.is_completed:
            return Response({'error': 'Тест уже завершён'}, status=status.HTTP_400_BAD_REQUEST)

        session.completed_at = timezone.now()
        session.is_completed = True
        correct_count = session.answers.filter(is_correct=True).count()
        session.correct_answers = correct_count
        session.calculate_score()

        return Response({
            'session_id': session.id,
            'total_questions': session.total_questions,
            'correct_answers': session.correct_answers,
            'score_percent': session.score_percent,
        })


class TestResultView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        try:
            session = TestSession.objects.get(id=session_id, student=request.user)
        except TestSession.DoesNotExist:
            return Response({'error': 'Сессия не найдена'}, status=status.HTTP_404_NOT_FOUND)

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
