from rest_framework import serializers
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()

from core.choices import TrackChoices
from core.tracks import (GRADUATION_TRACKS, available_tracks, filter_subjects_by_track,
                         filter_subjects_for_user, is_valid_track, normalize_track,
                         subject_track)

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
    track = serializers.CharField(required=False, allow_null=True, allow_blank=True, write_only=True)
    subject = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    invite_code = serializers.CharField(required=False, allow_blank=True, write_only=True)
    # Группа необязательна: 11-классник может выбрать её при регистрации,
    # позже её привяжет учитель или система по классу.
    group_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'password_confirm', 'role', 'account_type',
                  'full_name', 'school', 'grade', 'track', 'subject', 'invite_code',
                  'profile_subjects', 'group_id')

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
        requested_track = attrs.get('track') or None
        if requested_track and not is_valid_track(requested_track):
            raise serializers.ValidationError({'track': 'Такого трека нет: school / ent / nuet'})
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
            attrs['track'] = None
        else:
            attrs['role'] = 'student'
            if not attrs.get('grade'):
                raise serializers.ValidationError({'grade': 'Выберите класс'})
            # 11 класс — развилка ЕНТ/NUET, и без ответа профиль не считается
            # заполненным. Младшие классы принудительно школа.
            if attrs['grade'] == 11 and requested_track not in GRADUATION_TRACKS:
                raise serializers.ValidationError({'track': 'Для 11 класса выберите ЕНТ или NUET'})
            attrs['track'] = normalize_track(attrs['grade'], requested_track)
            group_id = attrs.get('group_id')
            if group_id:
                from .models import StudyGroup
                if not StudyGroup.objects.filter(id=group_id).exists():
                    raise serializers.ValidationError({'group_id': 'Группа не найдена'})
        attrs['account_type'] = account_type
        return attrs

    def create(self, validated_data):
        subjects_ids = validated_data.pop('profile_subjects', [])
        subject_id = validated_data.pop('subject', None)
        validated_data.pop('password_confirm', None)
        validated_data.pop('invite_code', None)
        validated_data.pop('account_type')
        group_id = validated_data.pop('group_id', None)
        password = validated_data.pop('password')
        first_name, last_name = split_full_name(validated_data.get('full_name'))
        validated_data.update(first_name=first_name, last_name=last_name)
        user = User(**validated_data)
        user.set_password(password)
        user.save()

        if group_id and user.role == 'student':
            from .models import StudyGroup
            group = StudyGroup.objects.filter(id=group_id).first()
            if group:
                user.student_groups.add(group)

        from subjects.models import Subject
        if user.role == 'student':
            # Скрытый предмет не должен оседать в профиле ученика: id приходят из
            # запроса, а экран регистрации показывает только видимые предметы.
            # Предмет чужого трека тоже не прикрепляем — школа не получает ЕНТ.
            chosen = filter_subjects_by_track(
                Subject.objects.filter(id__in=subjects_ids, is_visible=True), user.track)
            if not chosen.exists() and user.track == TrackChoices.ENT:
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
                  'grade', 'track', 'extra_tracks', 'school', 'profile_subjects', 'avatar',
                  'is_staff', 'is_superuser', 'telegram_username', 'profile_completed')
        read_only_fields = ('id', 'username', 'role', 'track', 'extra_tracks',
                            'is_staff', 'is_superuser', 'telegram_username')

    def get_avatar(self, obj):
        if obj.avatar:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.avatar.url)
            return obj.avatar.url
        return None

    def get_profile_subjects(self, obj):
        """Только предметы своего трека: ЕНТ-предмет в профиле школьника — это
        каталог, из которого он всё равно не сможет начать тест."""
        tracks = available_tracks(obj)
        subjects = obj.profile_subjects.all()
        return [s.id for s in subjects
                if not subject_track(s) or subject_track(s) in tracks]

    def get_profile_completed(self, obj):
        return obj.is_profile_completed


class AdminUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'role', 'full_name', 'school', 'grade', 'track',
                  'extra_tracks', 'is_active', 'date_joined', 'last_login')
        read_only_fields = ('id', 'date_joined', 'last_login')


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('role', 'is_active', 'grade', 'track', 'extra_tracks')

    def validate(self, attrs):
        """Админ меняет класс и трек теми же правилами, что и ученик в профиле."""
        if not ({'role', 'grade', 'track', 'extra_tracks'} & set(attrs)):
            # PATCH только `is_active` не должен пересчитывать трек: иначе снятие
            # блокировки молча меняло бы профиль ученика.
            return attrs
        role = attrs.get('role', self.instance.role if self.instance else 'student')
        grade = attrs.get('grade', self.instance.grade if self.instance else None)
        track = attrs.get('track', self.instance.track if self.instance else None)
        if role != 'student':
            attrs['track'] = None
            attrs['extra_tracks'] = []
        else:
            if track and not is_valid_track(track):
                raise serializers.ValidationError({'track': 'Такого трека нет: school / ent / nuet'})
            attrs['track'] = normalize_track(grade, track)
            if 'extra_tracks' in attrs:
                extra = attrs['extra_tracks']
                if not isinstance(extra, list):
                    raise serializers.ValidationError({'extra_tracks': 'Ожидается список треков'})
                bad = [value for value in extra if not is_valid_track(value)]
                if bad:
                    raise serializers.ValidationError({'extra_tracks': 'Такого трека нет'})
                attrs['extra_tracks'] = [
                    value for value in dict.fromkeys(extra)
                    if value and value != attrs['track']
                ]
                if grade != 11:
                    attrs['extra_tracks'] = []
        return attrs


class StudentTracksSerializer(serializers.Serializer):
    """Смена трека ученика учителем/админом (ученик сам менять не может)."""
    track = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    extra_tracks = serializers.ListField(
        child=serializers.CharField(), required=False, allow_empty=True)

    def validate(self, attrs):
        student = self.context['student']
        track = attrs.get('track', student.track)
        if track in ('', 'null', None):
            track = None
        if track and not is_valid_track(track):
            raise serializers.ValidationError({'track': 'Такого трека нет: school / ent / nuet'})
        track = normalize_track(student.grade, track)
        extra = attrs.get('extra_tracks', getattr(student, 'extra_tracks', None) or [])
        if not isinstance(extra, list):
            raise serializers.ValidationError({'extra_tracks': 'Ожидается список треков'})
        bad = [value for value in extra if not is_valid_track(value)]
        if bad:
            raise serializers.ValidationError({'extra_tracks': 'Такого трека нет'})
        if student.grade != 11:
            # Школьнику нечего открывать дополнительными выпускными треками.
            extra = []
        return {
            'track': track,
            'extra_tracks': [v for v in dict.fromkeys(extra) if v and v != track],
        }


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
