from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()

from .models import StudyGroup, SystemSetting


class RegisterSerializer(serializers.ModelSerializer):
    """Публичная регистрация — только ученики. Учителей/админов создаёт администратор."""
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    profile_subjects = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)
    # role принимаем для совместимости со старым фронтом, но всегда игнорируем
    role = serializers.CharField(required=False, write_only=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'password_confirm', 'role', 'full_name', 'school', 'profile_subjects')

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({'password_confirm': 'Пароли не совпадают'})
        # Публично регистрируются только ученики
        attrs['role'] = 'student'
        subjects = attrs.get('profile_subjects') or []
        if len(subjects) < 1:
            raise serializers.ValidationError({'profile_subjects': 'Выберите хотя бы один предмет'})
        return attrs

    def create(self, validated_data):
        subjects_ids = validated_data.pop('profile_subjects', [])
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        validated_data['role'] = 'student'
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        if subjects_ids:
            from subjects.models import Subject
            user.profile_subjects.set(Subject.objects.filter(id__in=subjects_ids))
        return user


class UserSerializer(serializers.ModelSerializer):
    profile_subjects = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'role', 'full_name', 'school', 'profile_subjects')
        read_only_fields = ('id', 'username', 'role')

    def get_profile_subjects(self, obj):
        return list(obj.profile_subjects.values_list('id', flat=True))


class AdminUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'role', 'full_name', 'school',
                  'is_active', 'date_joined', 'last_login')
        read_only_fields = ('id', 'date_joined', 'last_login')


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('role', 'is_active')


class StudyGroupSerializer(serializers.ModelSerializer):
    student_count = serializers.SerializerMethodField()

    class Meta:
        model = StudyGroup
        fields = ('id', 'name', 'teacher', 'student_count', 'created_at')
        read_only_fields = ('id', 'teacher', 'student_count', 'created_at')

    def get_student_count(self, obj):
        return obj.students.count()


class StudyGroupDetailSerializer(serializers.ModelSerializer):
    student_list = serializers.SerializerMethodField()

    class Meta:
        model = StudyGroup
        fields = ('id', 'name', 'teacher', 'student_list', 'created_at')
        read_only_fields = ('id', 'teacher', 'created_at')

    def get_student_list(self, obj):
        return [{'id': s.id, 'username': s.username, 'full_name': s.full_name}
                for s in obj.students.all()]


class SystemSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemSetting
        fields = ('id', 'key', 'value', 'description')
