from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from .models import Subject, Topic, Question, Answer
from .permissions import IsTeacherOrAdmin
from .serializers import (
    SubjectSerializer, TopicSerializer, TopicListSerializer,
    QuestionListSerializer, QuestionDetailSerializer, QuestionCreateSerializer,
)


class SubjectViewSet(viewsets.ModelViewSet):
    queryset = Subject.objects.all()

    def get_serializer_class(self):
        return SubjectSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsTeacherOrAdmin()]

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
    queryset = Question.objects.select_related('topic__subject').prefetch_related('answers')

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
        queryset = Question.objects.select_related('topic__subject').prefetch_related('answers')
        subject_id = self.request.query_params.get('subject')
        topic_id = self.request.query_params.get('topic')
        difficulty = self.request.query_params.get('difficulty')

        if subject_id:
            queryset = queryset.filter(topic__subject_id=subject_id)
        if topic_id:
            queryset = queryset.filter(topic_id=topic_id)
        if difficulty:
            queryset = queryset.filter(difficulty=difficulty)
        return queryset

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({'message': 'Вопрос удалён'}, status=status.HTTP_200_OK)
