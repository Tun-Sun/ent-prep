from rest_framework import serializers
from .models import TestSession, AnswerRecord
from subjects.serializers import AnswerDetailSerializer, QuestionDetailSerializer


class AnswerRecordSerializer(serializers.ModelSerializer):
    question_text = serializers.CharField(source='question.text', read_only=True)
    question_image = serializers.ImageField(source='question.image', read_only=True)
    selected_answer_text = serializers.CharField(source='selected_answer.text', read_only=True, default='—')
    correct_answer_text = serializers.SerializerMethodField()

    class Meta:
        model = AnswerRecord
        fields = ('id', 'question_text', 'question_image', 'selected_answer_text', 'correct_answer_text', 'is_correct')

    def get_correct_answer_text(self, obj):
        correct = obj.question.answers.filter(is_correct=True).first()
        return correct.text if correct else '—'


class AnswerRecordCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnswerRecord
        fields = ('question', 'selected_answer')


class TestSessionListSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    subject_icon = serializers.CharField(source='subject.icon', read_only=True)

    class Meta:
        model = TestSession
        fields = ('id', 'subject_name', 'subject_icon', 'started_at', 'completed_at',
                  'total_questions', 'correct_answers', 'score_percent', 'is_completed')


class TestSessionDetailSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    answers = serializers.SerializerMethodField()

    class Meta:
        model = TestSession
        fields = ('id', 'subject_name', 'started_at', 'completed_at',
                  'total_questions', 'correct_answers', 'score_percent', 'is_completed', 'answers')

    def get_answers(self, obj):
        records = obj.answers.select_related('question', 'selected_answer').all()
        return AnswerRecordSerializer(records, many=True).data


class StartTestSerializer(serializers.Serializer):
    subject_id = serializers.IntegerField()
    num_questions = serializers.IntegerField(default=10, min_value=1, max_value=40)
