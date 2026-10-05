from rest_framework import serializers
from django.conf import settings
from django.utils import timezone
from .models import Subject, Topic, Question, Answer, plain_from_latex

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
    total_questions = serializers.SerializerMethodField()

    class Meta:
        model = Subject
        fields = ('id', 'name', 'slug', 'icon', 'description',
                  'topic_count', 'total_questions', 'question_count', 'time_limit',
                  'is_visible', 'sort_order', 'subject_type', 'show_in_profiles')

    def get_topic_count(self, obj):
        return obj.topics.count()

    def get_total_questions(self, obj):
        from .models import Question
        return Question.objects.filter(topic__subject=obj).count()


class SubjectMinimalSerializer(serializers.ModelSerializer):
    """Для списка выбора профильных предметов — без лишних полей"""
    class Meta:
        model = Subject
        fields = ('id', 'name', 'slug', 'icon', 'question_count', 'time_limit', 'show_in_profiles')


class TopicListSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True)

    class Meta:
        model = Topic
        fields = ('id', 'name', 'subject', 'subject_name')


class QuestionListSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source='topic.name', read_only=True)
    subject_name = serializers.CharField(source='topic.subject.name', read_only=True)
    # id предмета, а не только название: без него окно редактуры не сможет
    # подставить список тем этого предмета
    subject = serializers.IntegerField(source='topic.subject_id', read_only=True)
    source_pages = serializers.SerializerMethodField()

    def get_source_pages(self, obj):
        """Страницы скана, на которых напечатана эта единица.

        Вычитка — сравнение распознанного с источником, поэтому одного кадра-выкройки
        мало: ответ мог уйти в таблицу ответов на другой странице, а номер —
        оказаться под чужим заголовком. Путь собирается из паспорта строки, новой
        колонки нет; если растра на диске нет, ссылка всё равно отдаётся — экран
        сам покажет битую картинку, а молча пустое поле выглядело бы как «страницы
        не было».
        """
        prov = obj.provenance or {}
        run, pages = prov.get("run"), prov.get("pages") or []
        if not run or not pages:
            return []
        return ["%sscans/%s/p%02d.png" % (settings.MEDIA_URL, run, int(p)) for p in pages]

    class Meta:
        model = Question
        fields = ('id', 'text', 'topic', 'topic_name', 'subject', 'subject_name',
                  'difficulty', 'source_type', 'verification_status', 'language', 'year', 'image',
                  # поля оцифровки: без них экран банка задач показал бы вместо формул
                  # обрывки, а без паспорта — не откуда вопрос взялся
                  'latex', 'latex_answer', 'uncertain', 'provenance', 'external_id',
                  'source_pages')


class QuestionDetailSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source='topic.name', read_only=True)
    answers = AnswerDetailSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = ('id', 'text', 'topic', 'topic_name', 'difficulty',
                  'explanation', 'image', 'image_ref', 'points',
                  'source_type', 'verification_status', 'language', 'year',
                  'external_id', 'ai_explanation', 'answers')


class QuestionCreateSerializer(serializers.ModelSerializer):
    """Создание вопроса вместе с ответами (nested)"""
    answers = AnswerCreateSerializer(many=True)

    class Meta:
        model = Question
        fields = ('id', 'text', 'topic', 'difficulty', 'explanation', 'points', 'answers')

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
        instance.points = validated_data.get('points', instance.points)
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


class BookScanEditSerializer(serializers.ModelSerializer):
    """Правка задачи, оцифрованной из книги.

    QuestionCreateSerializer для неё не годится: требует вложенные варианты
    ответа, а у открытого ответа вариантов нет. Здесь правятся поля оцифровки
    и классификация, и правка переживает повторный импорт — import_scanned_tasks
    обходит своим текстом/темой/статусом именно строки с human_edited.
    """
    DIFFICULTY_KEYS = {k for k, _ in Question.DIFFICULTY_CHOICES}
    STATUS_KEYS = {k for k, _ in Question.VERIFICATION_CHOICES}

    topic = serializers.PrimaryKeyRelatedField(queryset=Topic.objects.all())

    class Meta:
        model = Question
        fields = ('latex', 'latex_answer', 'difficulty', 'verification_status', 'topic')

    def validate_difficulty(self, v):
        if v not in self.DIFFICULTY_KEYS:
            raise serializers.ValidationError('Такой сложности нет: easy / medium / hard')
        return v

    def validate_verification_status(self, v):
        if v not in self.STATUS_KEYS:
            raise serializers.ValidationError('Такого статуса нет: draft / verified / rejected')
        return v

    def update(self, instance, validated_data):
        changed = [f for f, v in validated_data.items() if v != getattr(instance, f)]
        if not changed:
            # «Сохранить» без правки не должно оставлять метку «правил человек»:
            # она значит, что строку видел глаз, а не что кто-то открыл окно
            return instance
        # Оригинал храним один раз: после второй правки в нём должна лежать
        # строка из прогона, а не то, что стало после первой опечатки.
        prov = dict(instance.provenance or {})
        orig = dict(prov.get('ocr_original') or {})
        for f in ('latex', 'latex_answer'):
            if f in changed:
                orig.setdefault(f, getattr(instance, f))
        for f in changed:
            setattr(instance, f, validated_data[f])
        if 'latex' in changed:
            # text читает весь остальной UI (тест, админка, выгрузка) — он обязан
            # идти за latex, иначе на экране теста останется исправленная опечатка
            instance.text = plain_from_latex(instance.latex)[:4000] or '(пустое условие)'
        if orig:
            prov['ocr_original'] = orig
        prov['human_edited'] = True
        prov['edited_at'] = timezone.now().isoformat()
        prov['edited_by'] = str(self.context['request'].user)
        instance.provenance = prov
        instance.save()
        return instance
