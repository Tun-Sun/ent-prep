from rest_framework import serializers
from .models import TestSession, TestSectionResult, AnswerRecord
from subjects.serializers import AnswerDetailSerializer, QuestionDetailSerializer
from subjects.models import Question


class AnswerRecordSerializer(serializers.ModelSerializer):
    question_text = serializers.CharField(source='question.text', read_only=True)
    question_type = serializers.CharField(source='question.question_type', read_only=True)
    question_image = serializers.SerializerMethodField()
    selected_answer_text = serializers.SerializerMethodField()
    correct_answer_text = serializers.SerializerMethodField()
    matching_pairs = serializers.JSONField(read_only=True)
    selected_answers = serializers.JSONField(read_only=True)

    class Meta:
        model = AnswerRecord
        fields = ('id', 'question_text', 'question_type', 'question_image',
                  'selected_answer_text', 'correct_answer_text',
                  'selected_answers', 'matching_pairs',
                  'is_correct', 'points_earned', 'points_max')

    def get_selected_answer_text(self, obj):
        if obj.question.question_type == 'single_choice' and obj.selected_answer:
            return obj.selected_answer.text
        if obj.question.question_type == 'multiple_choice':
            correct = obj.question.answers.filter(id__in=obj.selected_answers)
            return ', '.join(a.text for a in correct) if correct else '—'
        if obj.question.question_type == 'matching':
            return '; '.join(f'{k}→{v}' for k, v in obj.matching_pairs.items()) if obj.matching_pairs else '—'
        return '—'

    def get_question_image(self, obj):
        q = obj.question
        if q.image:
            try:
                return q.image.url
            except Exception:
                pass
        if q.image_ref and '/' in q.image_ref:
            return q.image_ref
        return None

    def get_correct_answer_text(self, obj):
        q = obj.question
        correct = q.answers.filter(is_correct=True)
        if q.question_type == 'single_choice':
            first = correct.first()
            return first.text if first else '—'
        if q.question_type == 'multiple_choice':
            return ', '.join(a.text for a in correct) if correct else '—'
        if q.question_type == 'matching':
            pairs = getattr(q, '_matching_pairs', None)
            return str(pairs) if pairs else '—'
        return '—'


class AnswerRecordCreateSerializer(serializers.ModelSerializer):
    selected_answer = serializers.IntegerField(required=False, allow_null=True)
    selected_answers = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list,
        max_length=2, label='Выбранные ответы',
    )
    matching_pairs = serializers.JSONField(required=False, default=dict, label='Пары соответствия')
    question = serializers.IntegerField()

    class Meta:
        model = AnswerRecord
        fields = ('question', 'selected_answer', 'selected_answers', 'matching_pairs')

    def validate_question(self, value):
        if isinstance(value, int):
            try:
                return Question.objects.get(id=value)
            except Question.DoesNotExist:
                raise serializers.ValidationError('Вопрос не найден')
        return value


class TestSectionResultSerializer(serializers.ModelSerializer):
    section_display = serializers.CharField(source='get_section_display', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True, default='')

    class Meta:
        model = TestSectionResult
        fields = ('section', 'section_display', 'subject_name',
                  'total_questions', 'answered', 'correct_answers',
                  'points_earned', 'points_max')


class TestSessionListSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True, default='')
    subject_icon = serializers.CharField(source='subject.icon', read_only=True, default='')
    type_label = serializers.SerializerMethodField()

    class Meta:
        model = TestSession
        fields = ('id', 'subject_name', 'subject_icon', 'started_at', 'completed_at',
                  'total_questions', 'correct_answers', 'score_percent',
                  'is_completed', 'total_points', 'earned_points', 'is_ent', 'type_label')

    def get_type_label(self, obj):
        return 'ЕНТ' if obj.is_ent else (obj.subject.name if obj.subject else 'Тест')


class TestSessionDetailSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True, default='')
    answers = serializers.SerializerMethodField()
    sections = serializers.SerializerMethodField()

    class Meta:
        model = TestSession
        fields = ('id', 'subject_name', 'started_at', 'completed_at',
                  'total_questions', 'correct_answers', 'score_percent',
                  'is_completed', 'is_ent', 'time_limit',
                  'total_points', 'earned_points', 'answers', 'sections')

    def get_answers(self, obj):
        records = obj.answers.select_related('question', 'selected_answer').all()
        return AnswerRecordSerializer(records, many=True).data

    def get_sections(self, obj):
        records = obj.section_results.all()
        return TestSectionResultSerializer(records, many=True).data


class StartTestSerializer(serializers.Serializer):
    subject_id = serializers.IntegerField(required=False, allow_null=True)
    num_questions = serializers.IntegerField(required=False, min_value=1, max_value=40)
    topic_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list,
        label='ID тем (тренировка по темам)',
    )
    mode = serializers.ChoiceField(choices=['standard', 'rush'], default='standard')


class StartEntSerializer(serializers.Serializer):
    profile1_id = serializers.IntegerField(label='Профильный предмет 1')
    profile2_id = serializers.IntegerField(label='Профильный предмет 2')


class AnswerBulkSerializer(serializers.Serializer):
    answers = serializers.ListField(child=AnswerRecordCreateSerializer())


class TeacherTestSessionListSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True, default='')
    subject_icon = serializers.CharField(source='subject.icon', read_only=True, default='')
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    student_username = serializers.CharField(source='student.username', read_only=True)
    student_groups = serializers.SerializerMethodField()
    type_label = serializers.SerializerMethodField()

    class Meta:
        model = TestSession
        fields = ('id', 'student_name', 'student_username', 'subject_name', 'subject_icon',
                  'student_groups', 'started_at', 'completed_at', 'total_questions',
                  'correct_answers', 'score_percent', 'is_completed', 'is_ent', 'type_label')

    def get_type_label(self, obj):
        return 'ЕНТ' if obj.is_ent else (obj.subject.name if obj.subject else 'Тест')

    def get_student_groups(self, obj):
        return list(obj.student.student_groups.values_list('name', flat=True))


class TeacherTestSessionDetailSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True, default='')
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    student_username = serializers.CharField(source='student.username', read_only=True)
    answers = serializers.SerializerMethodField()
    sections = serializers.SerializerMethodField()

    class Meta:
        model = TestSession
        fields = ('id', 'student_name', 'student_username', 'subject_name',
                  'started_at', 'completed_at', 'total_questions', 'correct_answers',
                  'score_percent', 'is_completed', 'is_ent',
                  'total_points', 'earned_points', 'answers', 'sections')

    def get_answers(self, obj):
        records = obj.answers.select_related('question', 'selected_answer').all()
        return AnswerRecordSerializer(records, many=True).data

    def get_sections(self, obj):
        records = obj.section_results.all()
        return TestSectionResultSerializer(records, many=True).data
