from rest_framework import serializers
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()

from .models import StudyGroup, SystemSetting

# Ученик без выбранного предмета приходит готовиться к физике и математике — так
# решает владелец платформы, а не пустой список в профиле.
DEFAULT_STUDENT_SLUGS = ('physics', 'math')


def split_full_name(value):
    """Экран знает одно поле «Фамилия и Имя», а в базе живут `first_name` и
    `last_name`: первое слово — фамилия, остальное — имя. Одно слово считаем именем
    (так приходят и имена из Telegram, и обращения в журнале)."""
    parts = (value or '').split()
    if len(parts) < 2:
        return ' '.join(parts), ''
    return ' '.join(parts[1:]), parts[0]


class RegisterSerializer(serializers.ModelSerializer):
    """Регистрация на платформе INTELLECT: ученик 5–11 класса или преподаватель.

    Преподавателя пускаем только по коду из `TEACHER_INVITE_CODE`: в банке задач
    лежат ответы и разборы, поэтому без кода любой школьник зарегистрировал бы
    себе тренерский вход. Пустой код в настройках — закрыта именно ветка
    преподавателя, ученик регистрируется как раньше.
    """
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True, required=False, allow_blank=True)
    profile_subjects = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)
    account_type = serializers.ChoiceField(choices=('student', 'teacher'), required=False, write_only=True)
    # role принимаем для совместимости со старым фронтом, но всегда игнорируем
    role = serializers.CharField(required=False, write_only=True)
    grade = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    subject = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    invite_code = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'password_confirm', 'role', 'account_type',
                  'full_name', 'school', 'grade', 'subject', 'invite_code', 'profile_subjects')

    def validate_grade(self, value):
        if value is not None and value not in dict(User.GRADE_CHOICES):
            raise serializers.ValidationError('Класс бывает 5–11')
        return value

    def validate(self, attrs):
        # Подтверждение оставили компактным: сверяем его, только если фронт прислал.
        confirm = attrs.get('password_confirm')
        if confirm and attrs['password'] != confirm:
            raise serializers.ValidationError({'password_confirm': 'Пароли не совпадают'})
        if not (attrs.get('full_name') or '').strip():
            raise serializers.ValidationError({'full_name': 'Напишите фамилию и имя'})

        account_type = attrs.get('account_type') or 'student'
        if account_type == 'teacher':
            code = (settings.TEACHER_INVITE_CODE or '').strip()
            if not code:
                raise serializers.ValidationError(
                    {'invite_code': 'Регистрация преподавателей закрыта — обратитесь к администратору'})
            # Код короткий, поэтому регистр и случайные пробелы не считаются ошибкой.
            if (attrs.get('invite_code') or '').strip().upper() != code.upper():
                raise serializers.ValidationError({'invite_code': 'Неверный инвайт-код преподавателя'})
            if not (attrs.get('email') or '').strip():
                raise serializers.ValidationError({'email': 'Преподавателю нужна почта'})
            attrs['role'] = 'teacher'
        else:
            attrs['role'] = 'student'
            if not attrs.get('grade'):
                raise serializers.ValidationError({'grade': 'Выберите класс'})
        attrs['account_type'] = account_type
        return attrs

    def create(self, validated_data):
        subjects_ids = validated_data.pop('profile_subjects', [])
        subject_id = validated_data.pop('subject', None)
        validated_data.pop('password_confirm', None)
        validated_data.pop('invite_code', None)
        validated_data.pop('account_type')
        password = validated_data.pop('password')
        first_name, last_name = split_full_name(validated_data.get('full_name'))
        validated_data.update(first_name=first_name, last_name=last_name)
        user = User(**validated_data)
        user.set_password(password)
        user.save()

        from subjects.models import Subject
        if user.role == 'student':
            # Скрытый предмет не должен оседать в профиле ученика: id приходят из
            # запроса, а экран регистрации показывает только видимые предметы.
            chosen = Subject.objects.filter(id__in=subjects_ids, is_visible=True)
            if not chosen.exists():
                chosen = Subject.objects.filter(slug__in=DEFAULT_STUDENT_SLUGS)
            user.profile_subjects.set(chosen)
        elif subject_id:
            user.dashboard_subjects.set(Subject.objects.filter(id=subject_id))
        return user


class UserSerializer(serializers.ModelSerializer):
    profile_subjects = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    profile_completed = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'role', 'full_name', 'first_name', 'last_name',
                  'grade', 'school', 'profile_subjects', 'avatar', 'is_staff', 'is_superuser',
                  'telegram_username', 'profile_completed')
        read_only_fields = ('id', 'username', 'role', 'is_staff', 'is_superuser',
                            'telegram_username')

    def get_avatar(self, obj):
        if obj.avatar:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.avatar.url)
            return obj.avatar.url
        return None

    def get_profile_subjects(self, obj):
        return list(obj.profile_subjects.values_list('id', flat=True))

    def get_profile_completed(self, obj):
        return obj.is_profile_completed


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
