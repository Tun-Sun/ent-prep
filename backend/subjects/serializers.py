from rest_framework import serializers
from .models import Subject, Topic, Question, Answer


class AnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Answer
        fields = ('id', 'text', 'image')


class AnswerDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Answer
        fields = ('id', 'text', 'is_correct', 'image')


class AnswerCreateSerializer(serializers.ModelSerializer):
    """Сериализатор для создания/редактирования ответа с флагом правильности"""
    class Meta:
        model = Answer
        fields = ('id', 'text', 'is_correct')


class TopicSerializer(serializers.ModelSerializer):
    question_count = serializers.SerializerMethodField()

    class Meta:
        model = Topic
        fields = ('id', 'name', 'question_count')

    def get_question_count(self, obj):
        return obj.questions.count()


class SubjectSerializer(serializers.ModelSerializer):
    topic_count = serializers.SerializerMethodField()
    question_count = serializers.SerializerMethodField()

    class Meta:
        model = Subject
        fields = ('id', 'name', 'slug', 'icon', 'description', 'topic_count', 'question_count')

    def get_topic_count(self, obj):
        return obj.topics.count()

    def get_question_count(self, obj):
        return Question.objects.filter(topic__subject=obj).count()


class TopicListSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True)

    class Meta:
        model = Topic
        fields = ('id', 'name', 'subject', 'subject_name')


class QuestionListSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source='topic.name', read_only=True)
    subject_name = serializers.CharField(source='topic.subject.name', read_only=True)

    class Meta:
        model = Question
        fields = ('id', 'text', 'topic', 'topic_name', 'subject_name', 'difficulty')


class QuestionDetailSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source='topic.name', read_only=True)
    answers = AnswerDetailSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = ('id', 'text', 'topic', 'topic_name', 'difficulty', 'explanation', 'image', 'answers')


class QuestionCreateSerializer(serializers.ModelSerializer):
    """Создание вопроса вместе с ответами (nested)"""
    answers = AnswerCreateSerializer(many=True)

    class Meta:
        model = Question
        fields = ('id', 'text', 'topic', 'difficulty', 'explanation', 'answers')

    def create(self, validated_data):
        answers_data = validated_data.pop('answers')
        question = Question.objects.create(**validated_data)
        for ans_data in answers_data:
            Answer.objects.create(question=question, **ans_data)
        return question

    def update(self, instance, validated_data):
        answers_data = validated_data.pop('answers', None)

        instance.text = validated_data.get('text', instance.text)
        instance.topic = validated_data.get('topic', instance.topic)
        instance.difficulty = validated_data.get('difficulty', instance.difficulty)
        instance.explanation = validated_data.get('explanation', instance.explanation)
        instance.save()

        if answers_data is not None:
            instance.answers.all().delete()
            for ans_data in answers_data:
                Answer.objects.create(question=instance, **ans_data)
        return instance

    def validate_answers(self, answers):
        if len(answers) < 2:
            raise serializers.ValidationError('Должно быть минимум 2 ответа')
        if not any(a.get('is_correct') for a in answers):
            raise serializers.ValidationError('Должен быть хотя бы один правильный ответ')
        return answers
