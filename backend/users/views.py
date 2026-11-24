import re
import secrets
import string
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.db.models import Q
from django.shortcuts import get_object_or_404

from .serializers import (
    RegisterSerializer, UserSerializer,
    AdminUserSerializer, AdminUserUpdateSerializer, StudentTracksSerializer,
    StudyGroupSerializer, StudyGroupDetailSerializer,
    SystemSettingSerializer,
)
from .models import StudyGroup, SystemSetting
from core.choices import TrackChoices
from core.tracks import (GRADUATION_TRACKS, filter_subjects_by_track,
                         filter_subjects_for_user, is_valid_track, normalize_track)
from django.contrib.auth import get_user_model

User = get_user_model()


class LoginView(TokenObtainPairView):
    # Защита от перебора паролей
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            username = request.data.get('username', '')
            try:
                user = User.objects.get(username=username)
                user.last_login = timezone.now()
                user.save(update_fields=['last_login'])
            except User.DoesNotExist:
                pass
        return response


class PublicGroupListView(APIView):
    """Группы для экрана регистрации: только id и название, без учителей."""
    permission_classes = [AllowAny]

    def get(self, request):
        groups = StudyGroup.objects.order_by('name').values('id', 'name')
        return Response(list(groups))


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'register'

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response({
            'message': 'Пользователь успешно создан',
            'user': {
                'id': user.id,
                'username': user.username,
                'role': user.role,
                'full_name': user.full_name,
            }
        }, status=201)


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Sum, Avg
        from tests.models import TestSession

        serializer = UserSerializer(request.user)
        data = serializer.data

        sessions = TestSession.objects.filter(student=request.user, is_completed=True)
        total_tests = sessions.count()
        total_questions = sessions.aggregate(s=Sum('total_questions'))['s'] or 0
        total_correct = sessions.aggregate(
            s=Sum('correct_answers')
        )['s'] or 0
        avg_score = sessions.aggregate(a=Avg('score_percent'))['a'] or 0

        data['stats'] = {
            'total_tests': total_tests,
            'total_questions': total_questions,
            'correct_answers': total_correct,
            'avg_score': round(avg_score, 1),
        }
        return Response(data)

    def patch(self, request):
        from django.contrib.auth import get_user_model
        from .serializers import split_full_name
        User = get_user_model()
        update_fields = []
        if 'avatar' in request.FILES:
            request.user.avatar = request.FILES['avatar']
            update_fields.append('avatar')
        if 'username' in request.data:
            username = request.data.get('username', '').strip()
            if not username:
                return Response({'error': 'Никнейм не может быть пустым'}, status=400)
            if not re.match(r'^[a-zA-Z0-9_]+$', username):
                return Response({'error': 'Только латиница, цифры и _'}, status=400)
            if User.objects.exclude(pk=request.user.pk).filter(username=username).exists():
                return Response({'error': 'Этот никнейм занят'}, status=400)
            request.user.username = username
            update_fields.append('username')
        if 'full_name' in request.data:
            full_name = request.data.get('full_name', '').strip()
            if not full_name:
                return Response({'error': 'ФИО не может быть пустым'}, status=status.HTTP_400_BAD_REQUEST)
            request.user.full_name = full_name
            # Экран знает одно поле «Фамилия и Имя», а журнал тренера читает
            # first_name/last_name — поэтому правим их вместе, иначе карточка
            # «Представься» заполнит половину, а в журнале человек останется без имени.
            first_name, last_name = split_full_name(full_name)
            request.user.first_name = first_name
            request.user.last_name = last_name
            request.user.name_confirmed = True
            update_fields += ['full_name', 'first_name', 'last_name', 'name_confirmed']
        if 'grade' in request.data:
            # Класс и трек — не игрушка: смена класса пересчитывала бы трек и
            # открывала чужой каталог. Но пустая карточка Telegram/GetCourse
            # должна заполниться — без класса профиль не считается готовым.
            if (getattr(request.user, 'role', '') == 'student'
                    and request.user.is_profile_completed):
                return Response({'error': 'Класс меняет преподаватель или администратор'}, status=403)
            grade = request.data.get('grade')
            if grade in (None, '', 'null'):
                request.user.grade = None
            else:
                try:
                    grade = int(grade)
                except (TypeError, ValueError):
                    return Response({'error': 'Класс — число от 5 до 11'}, status=400)
                if grade not in dict(User.GRADE_CHOICES):
                    return Response({'error': 'Класс бывает 5–11'}, status=400)
                request.user.grade = grade
            update_fields.append('grade')
        # Трек пересчитывается и при смене класса: 9 → 11 сбрасывает школу, а
        # 11 → 9 принудительно возвращает её. PATCH одного трека тоже проходит.
        if 'track' in request.data or 'grade' in request.data:
            track_sent = 'track' in request.data
            requested = request.data.get('track') if track_sent else request.user.track
            if requested in ('', 'null'):
                requested = None
            if requested and not is_valid_track(requested):
                return Response({'error': 'Такого трека нет: school / ent / nuet'}, status=400)
            if request.user.role != 'student':
                request.user.track = None
            else:
                if request.user.track and requested != request.user.track:
                    return Response(
                        {'error': 'Трек меняет преподаватель или администратор'}, status=403)
                # Трек выбирают один раз — при первом входе/регистрации.
                # Дальше его меняет только учитель через карточку ученика.
                if track_sent and request.user.grade == 11 and requested not in GRADUATION_TRACKS:
                    return Response({'error': 'Для 11 класса выберите ЕНТ или NUET'}, status=400)
                request.user.track = normalize_track(request.user.grade, requested)
            update_fields.append('track')
        if 'school' in request.data:
            request.user.school = (request.data.get('school') or '').strip()
            update_fields.append('school')
        if update_fields:
            request.user.save(update_fields=update_fields)
        serializer = UserSerializer(request.user, context={'request': request})
        return Response(serializer.data)


class UpdateProfileSubjectsView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request):
        from subjects.models import Subject
        subject_ids = request.data.get('profile_subjects', [])
        if not isinstance(subject_ids, list):
            return Response({'error': 'Ожидается список ID предметов'}, status=400)
        # Скрытый предмет в профиль ученика не кладём: иначе он висел бы в его
        # выборке, хотя на платформе его нет. Предмет чужого трека — тоже.
        subjects = filter_subjects_for_user(
            Subject.objects.filter(id__in=subject_ids, is_visible=True), request.user)
        request.user.profile_subjects.set(subjects)
        return Response({'profile_subjects': list(subjects.values_list('id', flat=True))})


class ClearTestHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        from tests.models import TestSession

        sessions = TestSession.objects.filter(student=request.user)
        deleted = sessions.count()
        sessions.delete()
        return Response({'deleted': deleted})


class DeleteOwnAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        password = request.data.get('password', '')
        if not request.user.check_password(password):
            return Response({'error': 'Неверный пароль'}, status=status.HTTP_400_BAD_REQUEST)

        request.user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class UpdateStudentSubjectsView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, student_id):
        if request.user.role not in ('teacher', 'admin'):
            return Response({'error': 'Доступ только для учителей'}, status=403)
        from subjects.models import Subject
        try:
            student = User.objects.get(id=student_id, role='student')
        except User.DoesNotExist:
            return Response({'error': 'Ученик не найден'}, status=404)
        subject_ids = request.data.get('profile_subjects', [])
        if not isinstance(subject_ids, list):
            return Response({'error': 'Ожидается список ID предметов'}, status=400)
        # Тренеру скрытый предмет в списке доступен, но в профиль ученика он лечь
        # не должен: ответ возвращает только то, что действительно прикрепилось.
        # Трек ученика здесь важнее желания тренера: школа не получает ЕНТ-предмет.
        subjects = filter_subjects_for_user(
            Subject.objects.filter(id__in=subject_ids, is_visible=True), student)
        student.profile_subjects.set(subjects)
        return Response({'profile_subjects': list(subjects.values_list('id', flat=True))})


class UpdateStudentTracksView(APIView):
    """Учитель/админ меняет основной трек и выдаёт дополнительные."""
    permission_classes = [IsAuthenticated]

    def put(self, request, student_id):
        if request.user.role not in ('teacher', 'admin'):
            return Response({'error': 'Доступ только для учителей'}, status=403)
        student = User.objects.filter(id=student_id, role='student').first()
        if not student:
            return Response({'error': 'Ученик не найден'}, status=404)
        serializer = StudentTracksSerializer(data=request.data, context={'student': student})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        student.track = data['track']
        student.extra_tracks = data['extra_tracks']
        student.save(update_fields=['track', 'extra_tracks'])
        return Response({
            'id': student.id,
            'track': student.track or '',
            'extra_tracks': student.extra_tracks,
        })


class UpdateStudentNameView(APIView):
    """Учитель/админ исправляет ФИО ученика, пришедшего из Telegram с ником."""
    permission_classes = [IsAuthenticated]

    def put(self, request, student_id):
        if request.user.role not in ('teacher', 'admin'):
            return Response({'error': 'Доступ только для учителей'}, status=403)
        student = User.objects.filter(id=student_id, role='student').first()
        if not student:
            return Response({'error': 'Ученик не найден'}, status=404)
        from .serializers import split_full_name
        full_name = str(request.data.get('full_name', '')).strip()
        if not full_name:
            return Response({'error': 'ФИО не может быть пустым'}, status=400)
        if len(full_name) > 150:
            return Response({'error': 'ФИО слишком длинное'}, status=400)

        student.full_name = full_name
        student.first_name, student.last_name = split_full_name(full_name)
        student.name_confirmed = True
        student.save(update_fields=['full_name', 'first_name', 'last_name', 'name_confirmed'])
        return Response({'id': student.id, 'full_name': student.full_name,
                         'name_confirmed': True})


class DeactivateStudentView(APIView):
    """Снять ученику доступ без удаления истории тестов и журнала."""
    permission_classes = [IsAuthenticated]

    def delete(self, request, student_id):
        if request.user.role not in ('teacher', 'admin'):
            return Response({'error': 'Доступ только для учителей'}, status=403)
        student = User.objects.filter(id=student_id, role='student').first()
        if not student:
            return Response({'error': 'Ученик не найден'}, status=404)
        student.is_active = False
        student.save(update_fields=['is_active'])
        return Response({'id': student.id, 'username': student.username,
                         'is_active': False, 'message': 'Ученик деактивирован'})


class ReactivateStudentView(APIView):
    """Вернуть доступ деактивированному ученику.

    Без этого снятие было дорогой в одну сторону: найти ученика в фильтре
    можно, а включить обратно — только через Django admin.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, student_id):
        if request.user.role not in ('teacher', 'admin'):
            return Response({'error': 'Доступ только для учителей'}, status=403)
        student = User.objects.filter(id=student_id, role='student').first()
        if not student:
            return Response({'error': 'Ученик не найден'}, status=404)
        student.is_active = True
        student.save(update_fields=['is_active'])
        return Response({'id': student.id, 'username': student.username,
                         'is_active': True, 'message': 'Доступ восстановлен'})


class SetPasswordView(APIView):
    """Задать пароль ученику, который вошёл через Telegram без пароля.

   Так человек может зайти с ноутбука по логину и паролю, если Telegram-вход
   на другом устройстве не проходит. Требуется уже действующая сессия.
   """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if user.has_usable_password():
            return Response({'error': 'У вас уже есть пароль — используйте смену пароля'},
                            status=status.HTTP_400_BAD_REQUEST)
        password = str(request.data.get('password', ''))
        if len(password) < 8:
            return Response({'error': 'Пароль — минимум 8 символов'},
                            status=status.HTTP_400_BAD_REQUEST)
        user.set_password(password)
        user.save(update_fields=['password'])
        return Response({'ok': True, 'username': user.username})


class ChangePasswordView(APIView):
    """Смена собственного пароля (все роли)."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        old_password = request.data.get('old_password', '')
        new_password = request.data.get('new_password', '')
        if not request.user.check_password(old_password):
            return Response({'error': 'Неверный текущий пароль'}, status=400)
        if len(new_password) < 8:
            return Response({'error': 'Новый пароль — минимум 8 символов'}, status=400)
        if old_password == new_password:
            return Response({'error': 'Новый пароль совпадает с текущим'}, status=400)
        request.user.set_password(new_password)
        request.user.save(update_fields=['password'])
        return Response({'message': 'Пароль изменён'})


class ResetStudentPasswordView(APIView):
    """Сброс пароля ученика учителем/админом.

    Возвращает новый пароль ровно один раз — показать ученику и попросить
    сменить в настройках.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, student_id):
        if request.user.role not in ('teacher', 'admin'):
            return Response({'error': 'Доступ только для учителей'}, status=403)
        try:
            student = User.objects.get(id=student_id, role='student')
        except User.DoesNotExist:
            return Response({'error': 'Ученик не найден'}, status=404)

        password = (request.data.get('password') or '').strip()
        if not password:
            alphabet = string.ascii_letters + string.digits
            password = ''.join(secrets.choice(alphabet) for _ in range(10))
        if len(password) < 8:
            return Response({'error': 'Пароль — минимум 8 символов'}, status=400)

        student.set_password(password)
        student.save(update_fields=['password'])
        return Response({
            'username': student.username,
            'full_name': student.full_name,
            'new_password': password,
        })


# ─── Study Groups ──────────────────────────────────────────────────────

class TeacherGroupMixin:
    permission_classes = [IsAuthenticated]

    def check_access(self, request):
        return request.user.role in ('teacher', 'admin')


class StudyGroupListCreateView(TeacherGroupMixin, generics.ListCreateAPIView):
    serializer_class = StudyGroupSerializer

    def get_queryset(self):
        # Группы видны всем тренерам: учитель может быть прикреплён к другой
        # группе или только что заведён, а список нужен для фильтров и отчётов.
        # Менять остаётся только свои группы (см. detail/добавление учеников).
        return StudyGroup.objects.all()

    def perform_create(self, serializer):
        serializer.save(teacher=self.request.user)


class StudyGroupDetailView(TeacherGroupMixin, generics.RetrieveUpdateDestroyAPIView):
    def get_serializer_class(self):
        if self.request.method == 'GET':
            return StudyGroupDetailSerializer
        return StudyGroupSerializer

    def get_queryset(self):
        return StudyGroup.objects.all()

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if (request.method != 'GET' and request.user.role != 'admin'
                and obj.teacher_id != request.user.id):
            self.permission_denied(request, message='Нет доступа к чужой группе')


class StudyGroupAddStudentsView(TeacherGroupMixin, APIView):
    def post(self, request, pk):
        group = get_object_or_404(StudyGroup, pk=pk)
        if request.user.role != 'admin' and group.teacher != request.user:
            return Response({'error': 'Нет доступа'}, status=403)
        student_ids = request.data.get('student_ids', [])
        students = User.objects.filter(id__in=student_ids, role='student')
        group.students.add(*students)
        return Response({'added': list(students.values_list('id', flat=True))})

    def delete(self, request, pk):
        group = get_object_or_404(StudyGroup, pk=pk)
        if request.user.role != 'admin' and group.teacher != request.user:
            return Response({'error': 'Нет доступа'}, status=403)
        student_id = request.query_params.get('student_id')
        if student_id:
            group.students.remove(student_id)
        return Response({'ok': True})


class CreateStudentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role not in ('teacher', 'admin'):
            return Response({'error': 'Доступ только для учителей'}, status=403)
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '')
        full_name = request.data.get('full_name', '').strip()
        group_id = request.data.get('group_id')
        if not username or not password:
            return Response({'error': 'Username и пароль обязательны'}, status=400)
        if User.objects.filter(username=username).exists():
            return Response({'error': 'Username уже занят'}, status=400)
        user = User.objects.create_user(
            username=username, password=password,
            full_name=full_name or username, role='student',
        )
        if group_id:
            try:
                group = StudyGroup.objects.get(id=group_id)
                group.students.add(user)
            except StudyGroup.DoesNotExist:
                pass
        return Response({'id': user.id, 'username': user.username, 'full_name': user.full_name}, status=201)


class StudentListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ('teacher', 'admin'):
            return Response({'error': 'Доступ только для учителей'}, status=403)
        search = request.query_params.get('search', '')
        group_id = request.query_params.get('group_id')
        track = request.query_params.get('track', '')
        # В поиске по умолчанию только активные: деактивированного нельзя
        # случайно записать в группу или выбрать в фильтр результатов.
        status_param = request.query_params.get('status', 'active')
        students = User.objects.filter(role='student')
        if status_param != 'all':
            students = students.filter(is_active=status_param != 'inactive')
        if track:
            if track not in ('school', 'ent', 'nuet'):
                return Response({'error': 'Такого трека нет: school / ent / nuet'}, status=400)
            students = students.filter(track=track)
        if group_id:
            from .models import StudyGroup
            try:
                group = StudyGroup.objects.get(id=group_id)
                students = students.filter(student_groups=group)
            except StudyGroup.DoesNotExist:
                pass
        if search:
            students = students.filter(
                Q(full_name__icontains=search) | Q(username__icontains=search)
            )
        return Response([
            {'id': s.id, 'username': s.username, 'full_name': s.full_name,
             'grade': s.grade, 'track': s.track or ''}
            for s in students.order_by('full_name')
        ])


# ─── Admin panel views ────────────────────────────────────────────────

class AdminRequiredMixin:
    permission_classes = [IsAuthenticated]

    def check_admin(self, request):
        return request.user.is_authenticated and request.user.role == 'admin'

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not self.check_admin(request):
            self.permission_denied(request, message='Только администратор')


class AdminUserListView(AdminRequiredMixin, generics.ListAPIView):
    serializer_class = AdminUserSerializer

    def get_queryset(self):
        qs = User.objects.all()
        search = self.request.query_params.get('search', '')
        role = self.request.query_params.get('role', '')
        status_param = self.request.query_params.get('status', 'active')
        if status_param != 'all':
            qs = qs.filter(is_active=status_param != 'inactive')
        if search:
            qs = qs.filter(
                Q(username__icontains=search) |
                Q(full_name__icontains=search) |
                Q(email__icontains=search)
            )
        if role:
            qs = qs.filter(role=role)
        return qs.order_by('-date_joined')


class AdminUserDetailView(AdminRequiredMixin, generics.RetrieveUpdateAPIView):
    queryset = User.objects.all()
    serializer_class = AdminUserUpdateSerializer

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return AdminUserUpdateSerializer
        return AdminUserSerializer

    def perform_update(self, serializer):
        super().perform_update(serializer)
        if 'full_name' not in self.request.data:
            return
        from .serializers import split_full_name
        user = serializer.instance
        user.first_name, user.last_name = split_full_name(user.full_name)
        user.name_confirmed = True
        user.save(update_fields=['first_name', 'last_name', 'name_confirmed'])


class AdminUserDeleteView(AdminRequiredMixin, generics.DestroyAPIView):
    queryset = User.objects.all()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance == request.user:
            return Response({'error': 'Нельзя удалить себя'}, status=status.HTTP_400_BAD_REQUEST)
        self.perform_destroy(instance)
        return Response({'message': 'Пользователь удалён'}, status=status.HTTP_200_OK)


class AdminInviteCodeView(AdminRequiredMixin, APIView):
    """Инвайт-код для регистрации учителей — только администратору."""

    def get(self, request):
        return Response({'invite_code': settings.TEACHER_INVITE_CODE or ''})


class AdminSettingListView(AdminRequiredMixin, generics.ListCreateAPIView):
    queryset = SystemSetting.objects.all()
    serializer_class = SystemSettingSerializer


class AdminSettingDetailView(AdminRequiredMixin, generics.RetrieveUpdateAPIView):
    queryset = SystemSetting.objects.all()
    serializer_class = SystemSettingSerializer


class TelegramConfigView(APIView):
    """Сконфигурирован ли вход через Telegram, как зовут бота и его номер.

    Имя и номер бота не секрет: номер виджет Telegram всё равно подставляет в
    открытый адрес `oauth.telegram.org/auth?bot_id=…`. Отдаём с сервера, чтобы смена
    ника бота не требовала пересборки фронта: `enabled: false` — и кнопки на экране
    нет. Токен бота наружу не уходит: номер берётся из его левой части.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        token = settings.TELEGRAM_BOT_TOKEN or ''
        bot_id = token.split(':')[0]
        return Response({
            'enabled': bool(token and settings.TELEGRAM_BOT_USERNAME),
            'telegram_bot_username': settings.TELEGRAM_BOT_USERNAME or '',
            'telegram_bot_id': bot_id if bot_id.isdigit() else '',
        })


class TelegramAuthView(APIView):
    """Быстрый вход из учебного чата Telegram (24-й деплой, п.3; строгий учёт — 26-й).

    Ученики сидят в чате, поэтому пароль и почта им не нужны: виджет Telegram присылает
    свои поля с подписью, сервер сверяет её по токену бота и узнаёт человека по
    `telegram_id`.

    Запрос идёт **анонимно**: `authentication_classes = []`. Живой `Authorization`
    здесь ignor'уется намеренно. Пока вьюха читала сессию, телефон с засевшим в
    `localStorage` чужим токеном (например, после тестовой ссылки) молча привязывал
    `telegram_id` к чужому аккаунту, и человек попадал в чужой профиль. Вход по
    подписи Telegram теперь заводит или находит **своего** ученика и выдаёт его же
    токены, которые фронт кладёт поверх старых.

    Право войти без пароля есть только у ученика: если на этот `telegram_id` заведён
    преподаватель, сотрудник или отключённый аккаунт — отказ; одна подпись не должна
    открывать тренерский экран. Единственное исключение — ник из
    `TELEGRAM_OWNER_BINDINGS` (владелец центра): его подпись привязывается к уже
    заведённому вручную аккаунту, а не создаёт пустого ученика.

    `assignment_id` + `lesson_token` — подпись урока из ссылки шаблона: по ней ученик
    привязывается к уроку и уходит сразу на его карточку.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'telegram_auth'

    def post(self, request):
        from subjects import sso
        from subjects.models import Assignment
        from . import telegram

        payload = request.data if hasattr(request.data, 'get') else {}
        if not settings.TELEGRAM_BOT_TOKEN:
            return Response({'detail': 'Вход через Telegram на сервере не настроен'},
                            status=status.HTTP_403_FORBIDDEN)
        data, error = telegram.verify(settings.TELEGRAM_BOT_TOKEN, payload,
                                      max_age=settings.TELEGRAM_AUTH_MAX_AGE)
        if data is None:
            return Response({'detail': error}, status=status.HTTP_403_FORBIDDEN)

        tg_id = int(data['id'])
        tg_username = (data.get('username') or '').strip()[:64]
        first = (data.get('first_name') or '').strip()[:150]
        last = (data.get('last_name') or '').strip()[:150]
        created = False

        owner_login = settings.TELEGRAM_OWNER_BINDINGS.get(tg_username.lower())
        student = User.objects.filter(telegram_id=tg_id).first()
        if student is not None:
            is_owner = bool(owner_login) and student.username == owner_login
            if not is_owner and (student.role != 'student' or student.is_staff
                                 or not student.is_active):
                return Response({'detail': 'Этот Telegram привязан не к активному ученику'},
                                status=status.HTTP_403_FORBIDDEN)
            self._rename(student, first, last, tg_username)
        else:
            owner = self._owner(owner_login)
            if owner is not None:
                # Хозяин аккаунта уже заведён вручную и вход без пароля ему разрешён
                # по его слову: привязываем подпись к нему, а не заводим пустого ученика.
                owner.telegram_id = tg_id
                owner.telegram_username = tg_username
                owner.save(update_fields=['telegram_id', 'telegram_username'])
                student = owner
            else:
                try:
                    with transaction.atomic():
                        student = User.objects.create_user(
                            username=self._new_username(User, tg_id, tg_username),
                            password=None, role='student', telegram_id=tg_id,
                            telegram_username=tg_username, first_name=first, last_name=last,
                            full_name=self._full_name(first, last))
                except IntegrityError:
                    # гонка двух тапов по кнопке на один Telegram-аккаунт
                    student = User.objects.filter(telegram_id=tg_id).first()
                    if student is None:
                        return Response({'detail': 'Этот Telegram заводится прямо сейчас, '
                                                   'попробуйте ещё раз'},
                                        status=status.HTTP_403_FORBIDDEN)
                else:
                    created = True

        next_url, notice = ('/assignments' if student.role == 'student' else '/teacher'), ''
        assignment_id = str(payload.get('assignment_id') or '').strip()
        token = str(payload.get('lesson_token') or '').strip()
        if assignment_id or token:
            if student.role != 'student':
                # Тренер, открывший ссылку своего урока, не должен становиться его
                # учеником: иначе его строка появится в собственной матрице результатов.
                notice = 'Урок по ссылке не открылся: этот вход не ученический.'
            elif (not assignment_id.isdigit() or not settings.GC_SSO_SECRET
                    or not sso.lesson_token_is_valid(settings.GC_SSO_SECRET, assignment_id, token)):
                notice = 'Урок по ссылке не открылся: подпись урока не совпала.'
            else:
                assignment = Assignment.objects.filter(pk=int(assignment_id),
                                                       status='active').first()
                if assignment is None:
                    notice = 'Урок не найден или уже отозван.'
                else:
                    assignment.students.add(student)
                    next_url = '/assignments?open=%s' % assignment.pk

        student.last_login = timezone.now()
        student.save(update_fields=['last_login'])
        tokens = RefreshToken.for_user(student)
        return Response({
            'access': str(tokens.access_token),
            'refresh': str(tokens),
            'next': next_url,
            'notice': notice,
            'created': created,
            # Карточка «Представься для преподавателя»: в Telegram человек может сидеть
            # под ником и без фамилии, а в журнале тренера его баллы обязаны быть
            # подписаны настоящим именем и классом. Экран решает показ, не сервер.
            'need_profile': not student.is_profile_completed,
            'user': {'id': student.pk, 'username': student.username, 'role': student.role,
                     'full_name': student.full_name, 'grade': student.grade,
                     'track': student.track or ''},
        })

    @staticmethod
    def _full_name(first, last):
        return ' '.join(p for p in (first, last) if p).strip()[:150]

    @staticmethod
    def _owner(login):
        """Аккаунт, к которому привязывается ник из `TELEGRAM_OWNER_BINDINGS`.

        Пустой `login` (ник не хозяйский) — None, и тогда идёт обычная ветка «завести
        ученика». Подпись Telegram доказывает владение именно этим ником, поэтому
        прежний `telegram_id` переключаем: человек мог сменить аккаунт в мессенджере.
        """
        if not login:
            return None
        return User.objects.filter(username=login, is_active=True).first()

    @staticmethod
    def _rename(student, first, last, tg_username):
        """Имя ученика берётся из Telegram, а не из старой строки базы.

        Пустое поле не затирает: мессенджер отдаёт `last_name` только если человек его
        заполнял, а пустая строка в ответе виджета — не его вердикт.

        Как только человек представился сам (карточка «Представься») или ФИО
        поправил учитель (`name_confirmed`), ник из Telegram перестаёт быть
        истиной — иначе каждый вход стирал бы фамилию из журнала.
        """
        introduced = student.is_profile_completed or student.name_confirmed
        changed = []
        for field, value in (('first_name', first), ('last_name', last),
                             ('telegram_username', tg_username)):
            if introduced and field in ('first_name', 'last_name'):
                continue
            if value and getattr(student, field) != value:
                setattr(student, field, value)
                changed.append(field)
        if changed:
            if any(f in changed for f in ('first_name', 'last_name')):
                student.full_name = TelegramAuthView._full_name(student.first_name,
                                                                student.last_name)
                changed.append('full_name')
            student.save(update_fields=changed)

    @staticmethod
    def _new_username(User, tg_id, tg_username):
        """Логин нового ученика: его ник из Telegram, а номер — если ника нет.

        Правило символов то же, что требует экран профиля (`[A-Za-z0-9_]`), чтобы
        человек потом смог поменять ник сам и он прошёл ту же проверку.
        """
        base = re.sub(r'[^A-Za-z0-9_]', '', (tg_username or '')).lower()[:24]
        if not base:
            base = 'tg%d' % tg_id
        candidate, n = base, 0
        while User.objects.filter(username=candidate).exists():
            n += 1
            candidate = '%s%d' % (base, n)
            if n > 200:
                candidate = 'tg%s' % secrets.token_hex(4)
                break
        return candidate
