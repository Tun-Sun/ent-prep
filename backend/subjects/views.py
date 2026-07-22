from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404

from .models import Subject, Topic, Question, Answer
from .permissions import IsTeacherOrAdmin
from .serializers import (
    SubjectSerializer, SubjectMinimalSerializer,
    TopicSerializer, TopicListSerializer,
    QuestionListSerializer, QuestionDetailSerializer, QuestionCreateSerializer,
)


class SubjectViewSet(viewsets.ModelViewSet):
    queryset = Subject.objects.all()

    def get_serializer_class(self):
        if self.action in ('minimal', 'for_registration'):
            return SubjectMinimalSerializer
        return SubjectSerializer

    def get_permissions(self):
        # Публичный список для экрана регистрации (только видимые)
        if self.action == 'for_registration':
            return [AllowAny()]
        if self.action in ['list', 'retrieve', 'minimal']:
            return [IsAuthenticated()]
        return [IsTeacherOrAdmin()]

    def get_queryset(self):
        qs = Subject.objects.all()
        # Анонимы и ученики — только видимые предметы
        user = self.request.user
        if not user.is_authenticated or getattr(user, 'role', '') == 'student':
            qs = qs.filter(is_visible=True)
        search = self.request.query_params.get('search', '')
        if search:
            qs = qs.filter(name__icontains=search)
        return qs

    @action(detail=False, methods=['get'], url_path='for-registration')
    def for_registration(self, request):
        """Публичный список предметов для регистрации ученика (без JWT)."""
        qs = Subject.objects.filter(is_visible=True).order_by('sort_order', 'name')
        return Response(SubjectSerializer(qs, many=True).data)

    @action(detail=False, methods=['get'])
    def minimal(self, request):
        """Только id, name, slug, icon — для выпадающих списков"""
        qs = self.filter_queryset(self.get_queryset())
        return Response(SubjectMinimalSerializer(qs, many=True).data)

    @action(detail=True, methods=['post'])
    def toggle_visibility(self, request, pk=None):
        """Учитель вкл/выкл видимость предмета"""
        subject = self.get_object()
        subject.is_visible = not subject.is_visible
        subject.save()
        return Response({'id': subject.id, 'is_visible': subject.is_visible})

    @action(detail=True, methods=['get'])
    def topics(self, request, pk=None):
        subject = self.get_object()
        topics = subject.topics.all()
        return Response(TopicSerializer(topics, many=True).data)


class TopicViewSet(viewsets.ModelViewSet):
    queryset = Topic.objects.select_related('subject')

    def get_serializer_class(self):
        return TopicListSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsTeacherOrAdmin()]

    def get_queryset(self):
        queryset = Topic.objects.select_related('subject')
        subject_id = self.request.query_params.get('subject')
        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)
        return queryset


class QuestionViewSet(viewsets.ModelViewSet):
    queryset = Question.objects.select_related('topic__subject')

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsTeacherOrAdmin()]

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return QuestionCreateSerializer
        if self.action == 'retrieve':
            return QuestionDetailSerializer
        return QuestionListSerializer

    def get_queryset(self):
        queryset = Question.objects.select_related('topic__subject')
        subject_id = self.request.query_params.get('subject')
        topic_id = self.request.query_params.get('topic')
        difficulty = self.request.query_params.get('difficulty')
        source_type = self.request.query_params.get('source_type')

        if subject_id:
            queryset = queryset.filter(topic__subject_id=subject_id)
        if topic_id:
            queryset = queryset.filter(topic_id=topic_id)
        if difficulty:
            queryset = queryset.filter(difficulty=difficulty)
        if source_type:
            queryset = queryset.filter(source_type=source_type)
        return queryset

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        instance = Question.objects.select_related('topic__subject').prefetch_related('answers').get(pk=instance.pk)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({'message': 'Вопрос удалён'}, status=status.HTTP_200_OK)
