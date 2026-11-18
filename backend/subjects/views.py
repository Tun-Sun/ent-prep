import re
import secrets

from rest_framework import viewsets, status, mixins
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.db.models.functions import Random
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (Subject, Topic, Question, Answer, Assignment, AssignmentBlock,
                     AssignmentSubmission, AssignmentAnswer)
from core.tracks import filter_subjects_by_track, is_valid_track
from .permissions import IsTeacherOrAdmin
from .serializers import (
    SubjectSerializer, SubjectMinimalSerializer,
    TopicSerializer, TopicListSerializer,
    QuestionListSerializer, QuestionDetailSerializer, QuestionCreateSerializer,
    BookScanEditSerializer,
    AssignmentListSerializer, AssignmentDetailSerializer, AssignmentWriteSerializer,
    AssignmentBlockSerializer, AssignmentAnswerSerializer,
    MyAssignmentListSerializer, MyAssignmentBlockSerializer,
)
from .lesson_grading import grade_assignment_answer, score_submission, close_submission
from .getcourse import report_submission, schedule_report
from . import sso


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
        # Анонимы и ученики — только видимые предметы. Ученику ещё и только
        # предметы своего трека: школа не видит ЕНТ-каталог, NUET — тоже.
        user = self.request.user
        if not user.is_authenticated or getattr(user, 'role', '') == 'student':
            qs = qs.filter(is_visible=True)
        if getattr(user, 'role', '') == 'student':
            qs = filter_subjects_by_track(qs, user.track)
        search = self.request.query_params.get('search', '')
        if search:
            qs = qs.filter(name__icontains=search)
        return qs

    @action(detail=False, methods=['get'], url_path='for-registration')
    def for_registration(self, request):
        """Публичный список предметов для регистрации ученика (без JWT).

        `?track=ent|nuet|school` отдаёт только предметы этого трека и общие:
        экран регистрации не должен предлагать школьнику ЕНТ-профиль.
        """
        qs = Subject.objects.filter(is_visible=True).order_by('sort_order', 'name')
        track = request.query_params.get('track')
        if track:
            if not is_valid_track(track):
                return Response({'error': 'Такого трека нет: school / ent / nuet'}, status=400)
            qs = filter_subjects_by_track(qs, track)
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
        # Банк целиком — учительский: `list` и `retrieve` под `IsAuthenticated`
        # отдавали ученику весь банк вместе с `latex_answer`. Свой сериализатор
        # ответ скрывал, этот эндпоинт — нет. Ученик видит свою задачу только
        # через `/api/my/assignments/`.
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
        grade = self.request.query_params.get('grade')
        # Язык строки банка: перевод — отдельная строка, а не правка русской, поэтому
        # без этого фильтра казахские условия утонули бы в русском списке, и «сколько
        # переводов в банке» пришлось бы считать руками.
        language = self.request.query_params.get('language')
        # «только переводы»: о переводе говорит паспорт строки, а не флаг в колонке —
        # отдельного поля под конвейер перевода мы не заводили
        translated = self.request.query_params.get('translated')
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
        if grade:
            # «none» — выбрать строки, которым класс ещё не проставлен: их надо
            # искать, а не угадывать, сколько осталось разметить. Значение вне 5..11
            # просто не совпадёт ни с чем, отдельной валидации здесь нет.
            queryset = queryset.filter(grade=None if grade == 'none' else grade)
        if language:
            queryset = queryset.filter(language=language)
        if translated:
            queryset = queryset.filter(provenance__translated_src_pk__isnull=False)
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

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        rows = response.data.get('results') or []
        pks = [r['id'] for r in rows]
        # Оригинал не знает, что его перевели, — это знает только копия. Метку «↔ #ID»
        # на русской карточке иначе можно увидеть лишь тогда, когда перевод случайно
        # попал на ту же страницу выдачи. Одной доп. выборкой на страницу добираем
        # копии, указывающие на видимые строки; переводов два (ошибка конвейера) —
        # показываем самый новый.
        copy_of_src = {}
        if pks:
            for src_pk, copy_pk in Question.objects.filter(
                    provenance__translated_src_pk__in=pks).order_by('pk').values_list(
                    'provenance__translated_src_pk', 'pk'):
                copy_of_src[src_pk] = copy_pk
        for r in rows:
            r['translation_id'] = copy_of_src.get(r['id'])
        return response

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


class AssignmentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                        mixins.CreateModelMixin, mixins.UpdateModelMixin,
                        viewsets.GenericViewSet):
    """Конструктор уроков: собрать четыре блока, опубликовать, смотреть матрицу результатов.

    Здесь нет удаления: отзыв — отдельное решение, которое должно остаться в базе
    следом, а не стереть, что ученик уже получил и что по нему уже спросили.
    """
    queryset = Assignment.objects.select_related('subject', 'teacher', 'group') \
        .prefetch_related('students', 'blocks')
    permission_classes = [IsTeacherOrAdmin]

    def get_serializer_class(self):
        if self.action in ('create', 'partial_update', 'update'):
            return AssignmentWriteSerializer
        if self.action == 'retrieve':
            return AssignmentDetailSerializer
        if self.action == 'matrix':
            return AssignmentAnswerSerializer
        return AssignmentListSerializer

    def perform_create(self, serializer):
        # автор — тот, кто сидит за экраном: урок это решение тренера,
        # и по нему потом спрашивают, кто положил эти задачи ученику
        serializer.save(teacher=self.request.user)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(AssignmentDetailSerializer(self.get_object(), context={'request': request}).data)

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role != 'admin':
            qs = qs.filter(teacher=self.request.user)
        subject = self.request.query_params.get('subject')
        if subject:
            qs = qs.filter(subject_id=subject)
        status_ = self.request.query_params.get('status')
        if status_:
            qs = qs.filter(status=status_)
        return qs

    @staticmethod
    def _pool(params, subject_id, difficulty):
        """Задачи в пуле блока. Черновики отсечены: наружу идёт только принятое.

        `answerable()` здесь не нужен нарочно: он режет по ключу варианта, а
        домашняя задача из книги answering именно открытым решением — ученик
        пишет, а не угадывает букву.
        """
        qs = Question.objects.filter(topic__subject_id=subject_id,
                                     verification_status='verified')
        if difficulty:
            qs = qs.filter(difficulty=difficulty)
        topic = params.get('topic')
        if topic:
            qs = qs.filter(topic_id=topic)
        src = params.get('source_type')
        if src:
            qs = qs.filter(source_type=src)
        grade = params.get('grade')
        if grade:
            qs = qs.filter(grade=grade)
        return qs

    @action(detail=False, methods=['get'])
    def pick(self, request):
        """Предпросмотр набора для одного блока: размеры пула и сами задачи.

        Порядок случайный на каждый вызов — это и есть кнопка «перемешать»,
        без неё тренер получал бы одни и те же первые N строк банка.
        `difficulty` больше не обязателен: ступень блока задаёт сам блок
        (`advanced` пулит hard, `simplified` — easy), а тренер поверх этого
        фильтрует по теме, книге и классу.
        """
        subject_id = request.query_params.get('subject')
        if not subject_id:
            return Response({'detail': 'Нужен subject'}, status=status.HTTP_400_BAD_REQUEST)
        level = request.query_params.get('difficulty', '')
        kind = request.query_params.get('kind', '')
        if kind in ('advanced', 'simplified') and not level:
            level = 'hard' if kind == 'advanced' else 'easy'
        if level and level not in dict(Question.DIFFICULTY_CHOICES):
            return Response({'detail': 'Такого уровня нет: easy / medium / hard'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            count = max(1, min(int(request.query_params.get('count', 10)), 50))
        except ValueError:
            return Response({'detail': 'count — целое число'}, status=status.HTTP_400_BAD_REQUEST)
        pool = self._pool(request.query_params, subject_id, level)
        picked = pool.annotate(_r=Random()).order_by('_r')[:count]
        # размеры по всем уровням одним запросом: экран показывает, куда вообще
        # хватает материала, и не даёт просить 30 задач там, где их 4
        by_level = {k: 0 for k, _ in Question.DIFFICULTY_CHOICES}
        rows = (Question.objects.filter(topic__subject_id=subject_id,
                                        verification_status='verified')
                .values('difficulty').annotate(n=Count('id')))
        for row in rows:
            by_level[row['difficulty']] = row['n']
        return Response({
            'pool': pool.count(),
            'levels': by_level,
            'questions': QuestionListSerializer(picked, many=True).data,
        })

    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """Черновик становится уроком: ученик начинает его видеть, состав больше не гадают."""
        assignment = self.get_object()
        if not assignment.publish():
            return Response({'detail': 'В уроке нет ни одной задачи — публиковать нечего'},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(AssignmentDetailSerializer(assignment, context={'request': request}).data)

    @action(detail=True, methods=['get'])
    def matrix(self, request, pk=None):
        """Матрица результатов: строки — ученики, колонки — блоки, ячейка — итог сдачи.

        Процент считается по проверенным задачам; `pending` показан рядом, потому что
        75 % при трёх из четырёх нерешённых руками задачах — это не тот процент,
        который можно показать родителю.
        """
        assignment = self.get_object()
        blocks = assignment.blocks_ordered
        submissions = {(s.block_id, s.student_id): s
                       for s in AssignmentSubmission.objects.filter(assignment=assignment)
                       .prefetch_related('answers__question')}
        rows = []
        for student in assignment.students.filter(role='student').order_by('full_name', 'username'):
            cells = []
            for block in blocks:
                sub = submissions.get((block.pk, student.pk))
                score = score_submission(sub) if sub else None
                cells.append({
                    'block': block.pk, 'kind': block.kind, 'label': block.label,
                    'state': sub.state if sub else '',
                    'submitted_at': sub.last_submitted_at if sub else None,
                    **(score or {'total': len(block.question_ids or []), 'answered': 0,
                                 'checked': 0, 'pending': 0, 'earned': None,
                                 'possible': None, 'percent': None}),
                })
            rows.append({'student': student.pk, 'name': student.full_name or student.username,
                         # «сдано» — и `submitted`, и `reviewed`: ученик свою часть закрыл
                         # в обоих случаях, `reviewed` добавляет к этому только вердикт тренера
                         'blocks_progress': {
                             'submitted': sum(1 for c in cells
                                              if c['state'] in ('submitted', 'reviewed')),
                             'total': len(blocks)},
                         'blocks': cells})
        pending = (AssignmentAnswer.objects.filter(submission__assignment=assignment,
                                                   verdict='pending_review')
                   .order_by('created_at'))
        return Response({
            'assignment': assignment.pk,
            'blocks': [{'id': b.pk, 'kind': b.kind, 'label': b.label, 'order': b.order,
                        'autocheck': b.autocheck, 'tasks': len(b.question_ids or [])}
                       for b in blocks],
            'rows': rows,
            'pending_review': self.get_serializer(pending, many=True).data,
        })

    @action(detail=True, methods=['post'])
    def revoke(self, request, pk=None):
        """Отозвать урок: ученик перестаёт его видеть, след в базе остаётся."""
        assignment = self.get_object()
        assignment.status = 'revoked'
        assignment.save(update_fields=['status'])
        return Response(AssignmentDetailSerializer(assignment, context={'request': request}).data)


class AssignmentBlockViewSet(mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Состав и порядок одного блока: PATCH /api/assignment-blocks/<id>/.

    Отдельно от урока блок правят стрелками «вверх/вниз» и галочками задач —
    whole-урок для этого выгружать и перезаливать не нужно.
    """
    queryset = AssignmentBlock.objects.select_related('assignment', 'assignment__subject')
    permission_classes = [IsTeacherOrAdmin]
    serializer_class = AssignmentBlockSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role != 'admin':
            qs = qs.filter(assignment__teacher=self.request.user)
        return qs

    def update(self, request, *args, **kwargs):
        block = self.get_object()
        if block.submissions.exists():
            return Response({'detail': 'Блок уже сдавали: править состав нельзя, '
                                       'иначе ответы учеников останутся без своей задачи'},
                            status=status.HTTP_400_BAD_REQUEST)
        serializer = self.get_serializer(block, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(self.get_serializer(block).data)


class AssignmentAnswerViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Ручная проверка: вердикт преподавателя по одной задаче сдачи."""
    queryset = AssignmentAnswer.objects.select_related('question', 'submission',
                                                      'submission__student',
                                                      'submission__block')
    permission_classes = [IsTeacherOrAdmin]
    serializer_class = AssignmentAnswerSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role != 'admin':
            qs = qs.filter(submission__assignment__teacher=self.request.user)
        verdict = self.request.query_params.get('verdict')
        if verdict:
            qs = qs.filter(verdict=verdict)
        assignment = self.request.query_params.get('assignment')
        if assignment:
            qs = qs.filter(submission__assignment_id=assignment)
        return qs

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        """Итоговый балл по задаче выставляет только человек.

        `judged_by='human'` — и после этого задача входит в процент блока; машина к
        строке уже не вернётся, даже если эталон потом поправят в банке.
        """
        answer = self.get_object()
        verdict = request.data.get('verdict', '')
        if verdict not in ('correct', 'partial', 'incorrect'):
            return Response({'detail': 'Нужен вердикт: correct / partial / incorrect'},
                            status=status.HTTP_400_BAD_REQUEST)
        answer.verdict = verdict
        answer.judged_by = 'human'
        answer.verdict_note = (request.data.get('note') or '').strip()[:2000]
        answer.reviewed_by = request.user
        answer.reviewed_at = timezone.now()
        answer.save()
        left = close_submission(answer.submission, reviewer=request.user)
        # Последняя ручная проверка может быть тем самым моментом, когда домашка
        # дозрела: до неё висел `pending_review`, и модуль сам разберётся, пора ли.
        report_submission(answer.submission)
        return Response({
            'answer': self.get_serializer(answer).data,
            'submission_state': answer.submission.state,
            'pending_left': left,
            'score': score_submission(answer.submission),
        })


class MyAssignmentViewSet(viewsets.GenericViewSet):
    """Ученик: свои уроки, ответ по задаче, сдача блока и фидбек по нему.

    До этого шага у ученика не было ни одного эндпоинта назначений: `AssignmentViewSet`
    закрыт `IsTeacherOrAdmin`, и назначенное домой ученик платформой не видел.
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Скрытый предмет уносит с собой и старые уроки: иначе мягкое скрытие
        # банка обходилось бы через раздел «Мои уроки» — задачи там те же.
        # Сдачи и ответы остаются в БД и вернутся вместе с предметом.
        return Assignment.objects.filter(students=self.request.user, status='active',
                                         subject__is_visible=True) \
            .select_related('subject').prefetch_related('blocks')

    def get_assignment(self):
        return get_object_or_404(self.get_queryset(), pk=self.kwargs['pk'])

    def list(self, request):
        qs = self.get_queryset().order_by('-published_at')
        # «Сдано блоков: X/4» на кабинете ученика: сданным считается и `submitted`,
        # и `reviewed` — блок уже закрыт для ребёнка в любом из этих состояний.
        # Один запрос на весь список, а не по уроку в цикле.
        sent = {}
        for assignment_id in (AssignmentSubmission.objects
                              .filter(student=request.user, assignment__in=qs,
                                      state__in=('submitted', 'reviewed'))
                              .values_list('assignment_id', flat=True)):
            sent[assignment_id] = sent.get(assignment_id, 0) + 1
        return Response(MyAssignmentListSerializer(
            qs, many=True, context={'sent_blocks': sent}).data)

    def retrieve(self, request, pk=None):
        assignment = self.get_assignment()
        blocks = assignment.blocks_ordered
        subs = {s.block_id: s for s in
                AssignmentSubmission.objects.filter(assignment=assignment, student=request.user)
                .prefetch_related('answers__question')}
        context = {'submissions': subs,
                   'scores': {b.pk: score_submission(subs[b.pk]) for b in blocks if b.pk in subs}}
        return Response({
            'id': assignment.pk,
            'title': assignment.title,
            'subject_name': assignment.subject.name,
            'due_at': assignment.due_at,
            'expired': assignment.is_expired,
            'blocks': MyAssignmentBlockSerializer(blocks, many=True, context=context).data,
        })

    @action(detail=False, methods=['post'], url_path='join-preview')
    def join_preview(self, request):
        """Карточка предпросмотра доводит человека до его же урока, а не на главную.

        Ссылку из шаблона GetCourse часто открывают, уже сидя в системе, —
        безпарольный переход такому человеку не нужен, ему нужна привязка и адрес
        карточки. Две роли и два адреса (Шаг 6.6, 21-й деплой):
        * ученик привязывается к уроку и уходит сдавать;
        * тренер-владелец урока ни к кому не привязывается — он открывается в
          собственном конструкторе, где он его и собирал.

        Чужой тренер здесь отказывается: `lesson_token` подписан под урок, а не под
        человека, и без проверки владельца одна подпись открывала бы чужой урок.
        """
        assignment_id = str(request.data.get('assignment_id') or '').strip()
        token = str(request.data.get('lesson_token') or '').strip()
        if not assignment_id.isdigit():
            return Response({'detail': 'Урок в ссылке не опознан'},
                            status=status.HTTP_403_FORBIDDEN)
        if not settings.GC_SSO_SECRET or not sso.lesson_token_is_valid(settings.GC_SSO_SECRET,
                                                                       assignment_id, token):
            return Response({'detail': 'Подпись урока не совпала'},
                            status=status.HTTP_403_FORBIDDEN)
        assignment = Assignment.objects.filter(pk=int(assignment_id), status='active').first()
        if not assignment:
            return Response({'detail': 'Урок не найден или уже отозван'},
                            status=status.HTTP_403_FORBIDDEN)
        if request.user.role == 'student' and not request.user.is_staff:
            assignment.students.add(request.user)
            return Response({'next': '/assignments?open=%s' % assignment.pk})
        if request.user.role == 'teacher' and assignment.teacher_id == request.user.pk:
            return Response({'next': '/teacher/assign?open=%s' % assignment.pk})
        return Response({'detail': 'Вход по подписи урока открыт ученику и тренеру-владельцу'},
                        status=status.HTTP_403_FORBIDDEN)

    @staticmethod
    def _submission(assignment, student, block):
        sub, _created = AssignmentSubmission.objects.get_or_create(
            assignment=assignment, student=student, block=block)
        return sub

    def _block_and_question(self, request, assignment):
        block = get_object_or_404(assignment.blocks, pk=request.data.get('block'))
        question = get_object_or_404(Question, pk=request.data.get('question'))
        if question.pk not in (block.question_ids or []):
            return None, None, Response({'detail': 'Этой задачи в блоке нет'},
                                        status=status.HTTP_400_BAD_REQUEST)
        return block, question, None

    @action(detail=True, methods=['post'], url_path='answer')
    def answer(self, request, pk=None):
        """Сохранить ответ одной задачи: правка ученика обнуляет прежний вердикт.

        Блок без автопроверки (`in_class`, `advanced`) ответ сохраняет, но сверки не
        делает: вердикт по нему ставит человек, и ложного нуля тут не будет.

        Ответ сервера сознательно молчит о правильности. Раньше сюда возвращались
        `verdict`, `judged_by` и `feedback`, и ученик, тапая `A`, `B`, `C`, `D` и
        глядя на «Верно / Неверно», снимал тест перебором за четыре нажатия — ещё до
        сдачи. Сверка по-прежнему идёт здесь (строка в базе получает вердикт сразу,
        иначе `submit` перепроверял бы то, что уже решено), но наружу уходит только
        факт сохранения: итог человек увидит в ответе `submit/` и в payload после сдачи.
        """
        assignment = self.get_assignment()
        block, question, error = self._block_and_question(request, assignment)
        if error:
            return error
        if assignment.is_expired:
            return Response({'detail': 'Срок сдачи вышел'}, status=status.HTTP_400_BAD_REQUEST)
        sub = self._submission(assignment, request.user, block)
        raw = (request.data.get('raw_answer') or '').strip()[:5000]
        answer, _created = AssignmentAnswer.objects.update_or_create(
            submission=sub, question=question,
            defaults={'raw_answer': raw, 'verdict': 'pending_review', 'judged_by': '',
                      'verdict_note': '', 'normalized_answer': '',
                      'reviewed_by': None, 'reviewed_at': None})
        if raw and block.autocheck:
            grade_assignment_answer(answer)
        return Response({'id': answer.pk, 'question': question.pk, 'saved': True,
                         'state': sub.state})

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """Сдать блок: сохранённые ответы проверяются заново, итог идёт в матрицу.

        Ответ, который ученик правил после первой сверки, обязан получить вердикт по
        последней редакции, а не по той строке, что была в момент сохранения.
        """
        assignment = self.get_assignment()
        block = get_object_or_404(assignment.blocks, pk=request.data.get('block'))
        if assignment.is_expired:
            return Response({'detail': 'Срок сдачи вышел'}, status=status.HTTP_400_BAD_REQUEST)
        sub = self._submission(assignment, request.user, block)
        if block.autocheck:
            for answer in sub.answers.select_related('question'):
                if answer.raw_answer.strip():
                    grade_assignment_answer(answer)
        sub.state = 'submitted'
        sub.last_submitted_at = timezone.now()
        sub.save(update_fields=['state', 'last_submitted_at'])
        # Домашка без висячих `pending_review` дозревает до отправки именно здесь;
        # если очередь не пуста, модуль сам решит, что слать ещё рано. Сеть уезжает
        # из ответа ученику в фоновый поток (24-й деплой, п.1).
        schedule_report(sub)
        return Response({'state': sub.state, 'autocheck': block.autocheck,
                         'score': score_submission(sub),
                         'pending': sub.answers.filter(verdict='pending_review').count()})


class LessonJoinView(APIView):
    """Вход из урока GetCourse по подписанной ссылке (Шаг 6.1, режимы A и B).

    Ученик не знает пароля платформы и не должен его узнавать: ссылку из урока
    подписывает секрет, который знает только сервер, — его достаточно, чтобы
    опознать человека и посадить его внутрь его же задания.

    Два режима, потому что у ссылки два разных происхождения:
    * `sign` + `ts` — подписанный переход на конкретного ученика (серверный
      вебхук, бот): подпись покрывает все поля, ссылка живёт `GC_SSO_MAX_AGE`.
    * `lesson_token` — подпись **урока**, она вкладывается в шаблон GetCourse один
      раз и живёт столько, сколько живёт урок: макросы `{uid}`/`{email}` подставит
      ГК на показе, а HMAC посчитать не может. Перебор `assignment_id` отсекает
      сама сверка токена, вход разрешён только роли «ученик».

    Отказ — `403` и ни одной новой строки в базе. Подделанная или просроченная
    ссылка не создаёт аккаунт, не привязывает урок и не выдаёт токен: иначе по ней
    можно было бы засорять базу или, наоборот, узнать, какой почты в платформе нет.

    Режим B с нераскрытыми макросами — не отказ, а предпросмотр (Шаг 6.6): ссылку
    чаще всего открывают во вкладке, чтобы проверить, и человек видел бы сырую
    страницу DRF вместо ответа. Если подпись урока верна и урок активен, а `gc_uid`
    или `email` пришли шаблонными либо пустыми, редиректим на `/sso` с карточкой на
    русском. `demo=1` рядом с верной подписью урока входит дежурным аккаунтом
    `GC_DEMO_STUDENT_EMAIL` — так тренер смотрит экран сдачи и матрицу своими глазами.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        from urllib.parse import urlencode
        values = sso.normalize({field: request.query_params.get(field, '')
                                for field in sso.SIGNED_FIELDS})
        sign = request.query_params.get('sign', '')
        lesson_token = request.query_params.get('lesson_token', '')
        demo = request.query_params.get('demo', '').strip().lower() in ('1', 'true', 'yes')
        if not settings.GC_SSO_SECRET:
            return Response({'detail': 'Вход из GetCourse на сервере не настроен'},
                            status=status.HTTP_403_FORBIDDEN)
        if lesson_token:
            if not sso.lesson_token_is_valid(settings.GC_SSO_SECRET,
                                             values['assignment_id'], lesson_token):
                return Response({'detail': 'Подпись урока не совпала'},
                                status=status.HTTP_403_FORBIDDEN)
        else:
            if not sso.sign_is_valid(settings.GC_SSO_SECRET, values, sign):
                return Response({'detail': 'Подпись ссылки не совпала'},
                                status=status.HTTP_403_FORBIDDEN)
            if not sso.ts_is_fresh(values['ts'], max_age=settings.GC_SSO_MAX_AGE):
                return Response({'detail': 'Ссылка просрочена, попросите новую у преподавателя'},
                                status=status.HTTP_403_FORBIDDEN)
            # Предпросмотр здесь не нужен: подпись Режима A считает сервер по конкретному
            # ученику, нераскрытый макрос сюда попасть не мог, а заводить аккаунт с
            # буквальным `{email}` в почте — это мусор в базе вместо отказа.
            if sso.unfilled_macro(values):
                return Response({'detail': 'Откройте ссылку изнутри урока GetCourse: '
                                           'имя и почту подставляет GetCourse'},
                                status=status.HTTP_400_BAD_REQUEST)
        assignment = Assignment.objects.filter(pk=values['assignment_id'] or 0,
                                                status='active').first()
        if not assignment:
            return Response({'detail': 'Урок не найден или уже отозван'},
                            status=status.HTTP_403_FORBIDDEN)
        if demo:
            if not lesson_token:
                return Response({'detail': 'Тестовый вход открыт только по подписи урока'},
                                status=status.HTTP_403_FORBIDDEN)
            values = sso.normalize({'assignment_id': values['assignment_id'],
                                    'email': settings.GC_DEMO_STUDENT_EMAIL,
                                    'first_name': 'Тестовый', 'last_name': 'ученик'})
        elif lesson_token and (sso.unfilled_macro(values) or sso.no_identity(values)):
            return HttpResponseRedirect('/sso?%s' % urlencode(
                {'preview_assignment': assignment.pk, 'lesson_token': lesson_token}))
        student, refusal = self._resolve_student(values['gc_uid'], values['email'],
                                                 values['first_name'], values['last_name'],
                                                 by_lesson_token=bool(lesson_token) and not demo)
        if student is None:
            return Response({'detail': refusal}, status=status.HTTP_403_FORBIDDEN)
        assignment.students.add(student)
        student.last_login = timezone.now()
        student.save(update_fields=['last_login'])
        tokens = RefreshToken.for_user(student)
        # `/assignments` — одна страница со списком уроков и внутренней открыткой
        # карточки, поэтому переход из GetCourse приходит параметром, а не маршрутом.
        frag = {'access': str(tokens.access_token), 'refresh': str(tokens),
                'next': '/assignments?open=%s' % assignment.pk}
        # Ученик из GetCourse может прийти без имени и класса: в журнале тренера его
        # баллы должны быть подписаны по-человечески, поэтому страница входа сама
        # спросит, если сервер видит незаполненную карточку.
        if not student.is_profile_completed:
            frag['need_profile'] = '1'
        return HttpResponseRedirect('/sso#%s' % urlencode(frag))

    @staticmethod
    def _resolve_student(gc_uid, email, first_name, last_name, by_lesson_token=False):
        """Найти ученика по коду GetCourse, затем по почте, иначе завести нового.

        Порядок не переставить: код ГК — единственный идентификатор, который человек
        не переписывает. Почва же в GetCourse правится, и по ней ученик уже может
        быть в платформе под другим кодом.

        Чужой аккаунт не отдаём никогда: учитель или админ с той же почтой — это
        отказ, а не «ну и войдёт как учитель». Право войти по подписанной ссылке
        есть только у ученика, и под «учеником» понимается роль **и** отсутствие
        служебных прав: аккаунт с ролью ученика, но `is_staff`, открывает тренерский
        экран, а вход без пароля такого аккаунта не должен давать.

        `by_lesson_token` — Режим B, где подписан только урок, а не человек. Такую
        почту мог написать кто угодно, кто знает ссылку из чата: вход по одной ей в
        уже существующий аккаунт запрещён, опознаёт человека только код GetCourse.
        Режима А это не касается — там подпись считает сервер по конкретному ученику.
        """
        User = get_user_model()
        if gc_uid:
            user = User.objects.filter(gc_uid=gc_uid).first()
            if user is not None:
                if user.role != 'student' or user.is_staff or not user.is_active:
                    return None, 'Код GetCourse привязан не к активному ученику'
                return user, ''
        if email:
            user = User.objects.filter(email__iexact=email).first()
            if user is not None:
                if by_lesson_token:
                    return None, ('Вход по подписи урока открывается по коду GetCourse, '
                                  'а не по почте из ссылки')
                if user.role != 'student' or user.is_staff or not user.is_active:
                    return None, 'Эта почта в платформе принадлежит не активному ученику'
                if gc_uid and user.gc_uid and user.gc_uid != gc_uid:
                    return None, 'На эту почту уже привязан другой код GetCourse'
                if gc_uid and not user.gc_uid:
                    user.gc_uid = gc_uid
                    user.save(update_fields=['gc_uid'])
                return user, ''
        if not gc_uid and not email:
            return None, 'В ссылке нет ни кода GetCourse, ни почты'
        if by_lesson_token and not gc_uid:
            # Завести нового ученика по одной почте в Режиме B — значит позволить
            # любому, у кого есть ссылка из чата, расставлять аккаунты-пустышки.
            return None, ('В ссылке нет кода GetCourse: вход по подписи урока '
                          'открывается только по нему')
        username = LessonJoinView._new_username(User, gc_uid, email)
        full_name = ' '.join(part for part in (first_name, last_name) if part).strip()[:150]
        try:
            with transaction.atomic():
                user = User.objects.create_user(username=username, email=email or '',
                                                password=None, role='student',
                                                gc_uid=gc_uid, full_name=full_name,
                                                first_name=first_name[:150],
                                                last_name=last_name[:150])
        except IntegrityError:
            # гонка двух ссылок на один код: побеждает тот, кто первый успел записаться
            user = User.objects.filter(Q(gc_uid=gc_uid) | Q(email__iexact=email)).first() if gc_uid or email else None
            if user is None or user.role != 'student':
                return None, 'Ученик с таким кодом уже заводится прямо сейчас'
        return user, ''

    @staticmethod
    def _new_username(User, gc_uid, email):
        """Логин нового ученика: имя почтового ящика, а код ГК — если почты нет.

        Правило символов то же, что требует экран профиля (`[A-Za-z0-9_]`): ученик
        потом сможет поменять ник сам, и его первый ник обязан пройти ту же проверку.
        """
        base = re.sub(r'[^A-Za-z0-9_]', '', (email.split('@')[0] if email else '')).lower()[:24]
        if not base:
            base = 'gc' + re.sub(r'[^A-Za-z0-9_]', '', gc_uid)[:20]
        candidate = base
        n = 0
        while User.objects.filter(username=candidate).exists():
            n += 1
            candidate = '%s%d' % (base, n)
            if n > 200:
                candidate = 'gc%s' % secrets.token_hex(4)
        return candidate
