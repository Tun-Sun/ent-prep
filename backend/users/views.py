import re
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from django.utils import timezone
from django.db.models import Q
from django.shortcuts import get_object_or_404

from .serializers import (
    RegisterSerializer, UserSerializer,
    AdminUserSerializer, AdminUserUpdateSerializer,
    StudyGroupSerializer, StudyGroupDetailSerializer,
    SystemSettingSerializer,
)
from .models import StudyGroup, SystemSetting
from django.contrib.auth import get_user_model

User = get_user_model()


class LoginView(TokenObtainPairView):
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


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

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
            request.user.full_name = full_name
            update_fields.append('full_name')
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
        subjects = Subject.objects.filter(id__in=subject_ids)
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
        subjects = Subject.objects.filter(id__in=subject_ids)
        student.profile_subjects.set(subjects)
        return Response({'profile_subjects': list(subjects.values_list('id', flat=True))})


# ─── Study Groups ──────────────────────────────────────────────────────

class TeacherGroupMixin:
    permission_classes = [IsAuthenticated]

    def check_access(self, request):
        return request.user.role in ('teacher', 'admin')


class StudyGroupListCreateView(TeacherGroupMixin, generics.ListCreateAPIView):
    serializer_class = StudyGroupSerializer

    def get_queryset(self):
        if self.request.user.role == 'admin':
            return StudyGroup.objects.all()
        return StudyGroup.objects.filter(teacher=self.request.user)

    def perform_create(self, serializer):
        serializer.save(teacher=self.request.user)


class StudyGroupDetailView(TeacherGroupMixin, generics.RetrieveUpdateDestroyAPIView):
    def get_serializer_class(self):
        if self.request.method == 'GET':
            return StudyGroupDetailSerializer
        return StudyGroupSerializer

    def get_queryset(self):
        if self.request.user.role == 'admin':
            return StudyGroup.objects.all()
        return StudyGroup.objects.filter(teacher=self.request.user)


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
        students = User.objects.filter(role='student')
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
            {'id': s.id, 'username': s.username, 'full_name': s.full_name}
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


class AdminUserDeleteView(AdminRequiredMixin, generics.DestroyAPIView):
    queryset = User.objects.all()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance == request.user:
            return Response({'error': 'Нельзя удалить себя'}, status=status.HTTP_400_BAD_REQUEST)
        self.perform_destroy(instance)
        return Response({'message': 'Пользователь удалён'}, status=status.HTTP_200_OK)


class AdminSettingListView(AdminRequiredMixin, generics.ListCreateAPIView):
    queryset = SystemSetting.objects.all()
    serializer_class = SystemSettingSerializer


class AdminSettingDetailView(AdminRequiredMixin, generics.RetrieveUpdateAPIView):
    queryset = SystemSetting.objects.all()
    serializer_class = SystemSettingSerializer
