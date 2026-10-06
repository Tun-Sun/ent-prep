from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import Subject, Topic, Question, Answer
from .permissions import IsTeacherOrAdmin
from .serializers import (
    SubjectSerializer, SubjectMinimalSerializer,
    TopicSerializer, TopicListSerializer,
    QuestionListSerializer, QuestionDetailSerializer, QuestionCreateSerializer,
    BookScanEditSerializer,
)


class SubjectViewSet(viewsets.ModelViewSet):
    queryset = Subject.objects.all()
    lookup_value_regex = r'\d+'  # prevent actions shadowed by detail route

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


class QuestionPagination(PageNumberPagination):
    """34 592 вопроса одним ответом — это 30 МБ JSON, экран висит. Листаем по 50."""
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


class QuestionViewSet(viewsets.ModelViewSet):
    queryset = Question.objects.select_related('topic__subject')
    pagination_class = QuestionPagination

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsTeacherOrAdmin()]

    def get_serializer_class(self):
        if self.action in ('create', 'update'):
            return QuestionCreateSerializer
        if self.action == 'retrieve':
            return QuestionDetailSerializer
        return QuestionListSerializer

    def get_queryset(self):
        # порядок обязателен: без него LIMIT/OFFSET на разных страницах может
        # показать одну строку дважды и пропустить другую
        queryset = Question.objects.select_related('topic__subject').order_by('id')
        subject_id = self.request.query_params.get('subject')
        topic_id = self.request.query_params.get('topic')
        difficulty = self.request.query_params.get('difficulty')
        source_type = self.request.query_params.get('source_type')
        status = self.request.query_params.get('verification_status')
        # формат из паспорта прогона: 'задача' / 'тест' — тесты без ключа ответа
        # в общем списке только мешают вычитке, их прячут отдельным фильтром.
        # Параметр не называем `format`: DRF резервирует его под согласование
        # контента, и ?format=задача давало 404 вместо списка.
        fmt = self.request.query_params.get('task_format')

        if subject_id:
            queryset = queryset.filter(topic__subject_id=subject_id)
        if topic_id:
            queryset = queryset.filter(topic_id=topic_id)
        if difficulty:
            queryset = queryset.filter(difficulty=difficulty)
        if source_type:
            queryset = queryset.filter(source_type=source_type)
        if status:
            queryset = queryset.filter(verification_status=status)
        if fmt:
            # Значения через запятую: «и задачи, и теорию» — это не одно значение,
            # а просить «всё, кроме тестов» отдельным параметром значит удвоить фильтр.
            queryset = queryset.filter(
                provenance__format__in=[f for f in fmt.split(',') if f])
        needle = self.request.query_params.get('q', '').strip()
        if needle:
            # Подстрока, а не «похожие задачи»: вычитчику нужно найти, где ещё в банке
            # встречается этот знак или этот номер, и промахнуться он не имеет права.
            # Ищем и по тексту, и по LaTeX: у условия с формулой «text» — это то, что
            # видит глаз на экране, а «latex» — то, что набрано в книге.
            queryset = queryset.filter(
                Q(text__icontains=needle) | Q(latex__icontains=needle)
                | Q(latex_answer__icontains=needle) | Q(external_id__icontains=needle))
        return queryset

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        instance = Question.objects.select_related('topic__subject').prefetch_related('answers').get(pk=instance.pk)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        """Окно редактуры в банке из книг: PATCH по полям оцифровки.

        Отдельный сериализатор, а не общий PUT: у задачи с открытым ответом
        вариантов ответа нет, и QuestionCreateSerializer отклонил бы правку.
        """
        instance = self.get_object()
        serializer = BookScanEditSerializer(instance, data=request.data,
                                           partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(QuestionListSerializer(serializer.instance).data)

    @action(detail=False, methods=['post'], url_path='bulk-verify')
    def bulk_verify(self, request, *args, **kwargs):
        """Пакетная приёмка: статус сразу по всей выборке, а не по окну на каждую задачу.

        Решает человек, здесь только его рука: accepted_by значит «эту строку принял
        этот аккаунт», а не «её поправили». В отличие от human_edited метка бережёт
        один статус — условие следующий прогон всё равно обновит.
        """
        to = request.data.get('verification_status', 'verified')
        if to not in dict(Question.VERIFICATION_CHOICES):
            return Response({'detail': 'Такого статуса нет: draft / verified / rejected'},
                            status=status.HTTP_400_BAD_REQUEST)
        ids = request.data.get('ids') or []
        whole = bool(request.data.get('all_matching'))
        if whole and ids:
            return Response({'detail': 'ids или all_matching — что-то одно, не оба'},
                            status=status.HTTP_400_BAD_REQUEST)
        if not whole and not ids:
            return Response({'detail': 'Не выбрано ни одной задачи'},
                            status=status.HTTP_400_BAD_REQUEST)
        # выборка берётся тем же фильтром, что и список: «все под фильтр» обязана
        # принять ровно то, что человек сейчас видит, а не то, что он описал заново
        qs = self.filter_queryset(self.get_queryset()) if whole \
            else self.get_queryset().filter(pk__in=ids)
        now = timezone.now().isoformat()
        changed = []
        with transaction.atomic():
            for q in qs:
                if q.verification_status == to:
                    continue
                prov = dict(q.provenance or {})
                q.verification_status = to
                if to == 'draft':
                    # вернули в черновик — и метка приёмки обязана уйти, иначе
                    # перегон по ей молча восстановил бы «проверено»
                    for k in ('accepted_by', 'accepted_at'):
                        prov.pop(k, None)
                else:
                    prov['accepted_by'] = str(request.user)
                    prov['accepted_at'] = now
                q.provenance = prov
                q.save(update_fields=['verification_status', 'provenance'])
                changed.append(q.pk)
        return Response({'verification_status': to, 'changed': len(changed), 'ids': changed})

    @action(detail=True, methods=['post'], url_path='revert-ocr')
    def revert_ocr(self, request, pk=None):
        """Откат правки: условие и ответ возвращаются к снимку из оцифровки."""
        question = self.get_object()
        restored = question.restore_ocr_original()
        return Response({'restored': restored, 'question': QuestionListSerializer(question).data})

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({'message': 'Вопрос удалён'}, status=status.HTTP_200_OK)
