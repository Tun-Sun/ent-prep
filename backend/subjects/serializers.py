from rest_framework import serializers
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from users.models import StudyGroup
from .models import (Subject, Topic, Question, Answer, Assignment, AssignmentBlock,
                     AssignmentSubmission, AssignmentAnswer, plain_from_latex)
from . import sso

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
                  'difficulty', 'source_type', 'verification_status', 'language', 'year', 'grade', 'image',
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
    # Школьная программа, а не год ЕНТ: класс в сборнике не печатают, его решает
    # тренер, и записать это решение в поле «год» значило бы соврать.
    GRADES = set(range(5, 12))

    topic = serializers.PrimaryKeyRelatedField(queryset=Topic.objects.all())

    class Meta:
        model = Question
        fields = ('latex', 'latex_answer', 'difficulty', 'verification_status', 'topic', 'grade')

    def validate_grade(self, v):
        # null — «класс не решён», снятие отметки; число вне 5..11 — опечатка, её
        # не записываем: фильтр по классу обязан доверять тому, что лежит в базе
        if v is not None and v not in self.GRADES:
            raise serializers.ValidationError('Такого класса нет: 5…11')
        return v

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
            instance.text = plain_from_latex(instance.latex) or '(пустое условие)'
        if orig:
            prov['ocr_original'] = orig
        prov['human_edited'] = True
        prov['edited_at'] = timezone.now().isoformat()
        prov['edited_by'] = str(self.context['request'].user)
        instance.provenance = prov
        instance.save()
        return instance


class AssignmentStudentSerializer(serializers.ModelSerializer):
    """Кому ушло назначение — имя ученика экран обязан показывать, а не только id."""
    class Meta:
        model = get_user_model()
        fields = ('id', 'username', 'full_name')


class AssignmentBlockSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source='get_kind_display', read_only=True)
    label = serializers.CharField(read_only=True)
    autocheck = serializers.BooleanField(read_only=True)
    tasks = serializers.SerializerMethodField()

    class Meta:
        model = AssignmentBlock
        fields = ('id', 'kind', 'kind_display', 'title', 'label', 'order',
                  'question_ids', 'autocheck', 'tasks')
        # вид блока не переименовывают: четыре блока — это схема, а не подпись
        read_only_fields = ('kind',)

    def get_tasks(self, obj):
        return len(obj.question_ids or [])

    def validate_order(self, v):
        if v < 0:
            raise serializers.ValidationError('Порядок не бывает отрицательным')
        return v

    def validate_question_ids(self, ids):
        clean_block_questions(ids, self.instance.assignment.subject)
        return ids


class AssignmentBlockQuestionsSerializer(AssignmentBlockSerializer):
    """Блок вместе с задачами: карточка урока и страница ученика."""
    questions = serializers.SerializerMethodField()

    class Meta(AssignmentBlockSerializer.Meta):
        fields = AssignmentBlockSerializer.Meta.fields + ('questions',)

    def get_questions(self, obj):
        return QuestionListSerializer(obj.questions, many=True).data


class AssignmentListSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    difficulty_display = serializers.CharField(source='get_difficulty_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    teacher_name = serializers.CharField(source='teacher.full_name', read_only=True)
    group_name = serializers.SerializerMethodField()
    tasks = serializers.SerializerMethodField()
    lesson_token = serializers.SerializerMethodField()
    students = AssignmentStudentSerializer(many=True, read_only=True)
    blocks = AssignmentBlockSerializer(many=True, read_only=True)

    class Meta:
        model = Assignment
        fields = ('id', 'title', 'teacher', 'teacher_name', 'subject', 'subject_name',
                  'difficulty', 'difficulty_display', 'tasks', 'students', 'blocks',
                  'group', 'group_name', 'due_at', 'published_at',
                  'status', 'status_display', 'created_at', 'lesson_token')

    def get_tasks(self, obj):
        return obj.questions_count

    def get_group_name(self, obj):
        return obj.group.name if obj.group_id else ''

    def get_lesson_token(self, obj):
        """Подпись урока для ссылки, которую методист вкладывает в шаблон GetCourse.

        Пусто без `GC_SSO_SECRET`: тогда ссылку всё равно отклонит эндпоинт, и
        показывать методисту фиктивный токен смысла нет — экран честно остаётся без
        рабочей ссылки. Сериализатор только тренерский, ученику токен не уходит.
        """
        return sso.make_lesson_token(settings.GC_SSO_SECRET, obj.pk)


class AssignmentDetailSerializer(AssignmentListSerializer):
    blocks = AssignmentBlockQuestionsSerializer(many=True, read_only=True)
    expired = serializers.BooleanField(source='is_expired', read_only=True)

    class Meta(AssignmentListSerializer.Meta):
        fields = AssignmentListSerializer.Meta.fields + ('expired',)


class AssignmentBlockWriteSerializer(serializers.Serializer):
    """Один блок в payload тренера: kind обязателен, порядок и заголовок — нет."""
    kind = serializers.ChoiceField(choices=AssignmentBlock.KIND_CHOICES)
    title = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')
    order = serializers.IntegerField(required=False, min_value=0)
    question_ids = serializers.ListField(child=serializers.IntegerField(min_value=1),
                                         required=False, default=list)


def clean_block_questions(ids, subject):
    """Задачи блока: существующие, принятые, одного предмета. Порядок набора сохраняем.

    Одна функция на запись whole-урока и на правку одного блока: иначе PATCH блока
    пропускал бы черновик или чужой предмет, которые create уже отвергает.
    """
    if not ids:
        return []
    found = {q.pk: q for q in Question.objects.filter(pk__in=ids).select_related('topic')}
    missing = [i for i in ids if i not in found]
    if missing:
        raise serializers.ValidationError(
            {'question_ids': 'Задач с такими id в банке нет: ' +
                             ', '.join(str(i) for i in missing[:10])})
    # черновик наружу не уходит: ученик не должен получать недооцифрованную
    # формулу только потому, что предпросмотр успел её показать
    drafts = [q for q in found.values() if q.verification_status != 'verified']
    if drafts:
        raise serializers.ValidationError(
            {'question_ids': f'В наборе {len(drafts)} черновиков — назначать можно только принятые задачи'})
    # перекос предмета — это не мелочь: под «Математикой» ученик получил бы
    # физику, и ни один фильтр банка после этого его не выправит
    off = [q.pk for q in found.values() if subject and q.topic.subject_id != subject.pk]
    if off:
        raise serializers.ValidationError(
            {'question_ids': f'{len(off)} задач из другого предмета — урок собирается в рамках одного'})
    return [found[i] for i in ids]



class AssignmentWriteSerializer(serializers.ModelSerializer):
    """Создание и правка урока: четыре блока тем же списком задач, что видел экран.

    Экран присылает явные наборы, а не «набери сам по уровню»: между предпросмотром
    и сохранением сняли галочку, добавили задачу — и урок обязан быть ровно этим
    набором. Порядок внутри блока — позиция в списке.
    """
    students = serializers.PrimaryKeyRelatedField(
        many=True, queryset=get_user_model().objects.filter(role='student'), required=False)
    group = serializers.PrimaryKeyRelatedField(
        queryset=StudyGroup.objects.all(), required=False, allow_null=True)
    blocks = AssignmentBlockWriteSerializer(many=True)

    class Meta:
        model = Assignment
        fields = ('id', 'title', 'subject', 'students', 'group', 'due_at', 'blocks')
        read_only_fields = ('id',)

    def _clean_questions(self, ids, subject):
        return clean_block_questions(ids, subject)

    def validate_blocks(self, blocks):
        kinds = [b['kind'] for b in blocks]
        dupes = sorted({k for k in kinds if kinds.count(k) > 1})
        if dupes:
            raise serializers.ValidationError(
                {'blocks': 'Блок может быть только один: ' + ', '.join(dupes)})
        return blocks

    def validate(self, attrs):
        subject = attrs.get('subject') or (self.instance.subject if self.instance else None)
        for i, b in enumerate(attrs.get('blocks', [])):
            try:
                b['questions'] = self._clean_questions(b.get('question_ids') or [], subject)
            except serializers.ValidationError as e:
                detail = e.detail if isinstance(e.detail, list) else list(e.detail.values())
                raise serializers.ValidationError({'blocks': f'Блок {i + 1}: {detail[0]}'})
            b.setdefault('order', i)
        group = attrs.get('group')
        user = self.context['request'].user
        if group and user.role != 'admin' and group.teacher_id != user.pk:
            raise serializers.ValidationError({'group': 'Это не ваша группа'})
        if group and 'students' not in attrs:
            attrs['students_to_add'] = list(group.students.all())
        return attrs

    def create(self, validated_data):
        blocks = validated_data.pop('blocks')
        students = validated_data.pop('students', [])
        to_add = validated_data.pop('students_to_add', [])
        with transaction.atomic():
            assignment = Assignment.objects.create(**validated_data)
            assignment.students.set(list({*students, *to_add}))
            for b in blocks:
                assignment.blocks.create(kind=b['kind'], title=b.get('title', ''),
                                         order=b.get('order', 0),
                                         question_ids=[q.pk for q in b['questions']])
        return assignment

    def update(self, instance, validated_data):
        blocks = validated_data.pop('blocks', None)
        students = validated_data.pop('students', None)
        to_add = validated_data.pop('students_to_add', [])
        with transaction.atomic():
            for field, value in validated_data.items():
                setattr(instance, field, value)
            instance.save()
            if students is not None:
                instance.students.set(list({*students, *to_add}))
            if blocks is not None:
                self._replace_blocks(instance, blocks)
        return instance

    def _replace_blocks(self, instance, blocks):
        """Сверяем набор блоков с тем, что прислал экран.

        Блок с ответами учеников не удаляем: вместе с ним ушли бы и результаты,
        а этого тренер не просил — он просил править состав.
        """
        keep = set()
        for b in blocks:
            ids = [q.pk for q in b['questions']]
            obj, _created = instance.blocks.update_or_create(
                kind=b['kind'],
                defaults={'title': b.get('title', ''), 'order': b.get('order', 0),
                          'question_ids': ids})
            keep.add(obj.pk)
        for old in instance.blocks.exclude(pk__in=keep):
            if old.submissions.exists():
                raise serializers.ValidationError(
                    {'blocks': f'Блок «{old.get_kind_display()}» уже сдавали — '
                               'удалить его нельзя, правьте состав'})
            old.delete()


class AssignmentAnswerSerializer(serializers.ModelSerializer):
    """Ячейка матрицы тренера: ответ ученика, эталон книги и чем решён вердикт."""
    verdict_display = serializers.CharField(source='get_verdict_display', read_only=True)
    judged_by_display = serializers.CharField(source='get_judged_by_display', read_only=True)
    etalon = serializers.CharField(source='question.latex_answer', read_only=True)
    points_max = serializers.FloatField(source='question.points', read_only=True)
    points_earned = serializers.FloatField(read_only=True)
    student_name = serializers.CharField(source='submission.student.full_name', read_only=True)
    student_id = serializers.IntegerField(source='submission.student_id', read_only=True)
    block_kind = serializers.CharField(source='submission.block.kind', read_only=True)
    question_text = serializers.CharField(source='question.text', read_only=True)

    class Meta:
        model = AssignmentAnswer
        fields = ('id', 'submission', 'student_id', 'student_name', 'block_kind',
                  'question', 'question_text', 'raw_answer', 'normalized_answer',
                  'etalon', 'verdict', 'verdict_display', 'judged_by', 'judged_by_display',
                  'verdict_note', 'points_earned', 'points_max',
                  'reviewed_by', 'reviewed_at', 'updated_at')


class StudentAnswerSerializer(serializers.ModelSerializer):
    """Ответ ученика ему самому: только то, что показывает `AssignmentAnswer.feedback`."""
    feedback = serializers.SerializerMethodField()

    class Meta:
        model = AssignmentAnswer
        fields = ('id', 'question', 'raw_answer', 'verdict', 'feedback')

    def get_feedback(self, obj):
        return obj.feedback


class MyAssignmentListSerializer(serializers.ModelSerializer):
    """«Мои уроки»: что назначено, когда срок и из каких блоков состоит."""
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    expired = serializers.BooleanField(source='is_expired', read_only=True)
    blocks = serializers.SerializerMethodField()

    class Meta:
        model = Assignment
        fields = ('id', 'title', 'subject', 'subject_name', 'status', 'status_display',
                  'due_at', 'expired', 'published_at', 'blocks')

    def get_blocks(self, obj):
        return [{'kind': b.kind, 'label': b.label, 'order': b.order,
                 'tasks': len(b.question_ids or []), 'autocheck': b.autocheck}
                for b in obj.blocks_ordered]


class StudentQuestionSerializer(serializers.ModelSerializer):
    """Задача глазами ученика: условие, картинка, ступень и балл.

    `latex_answer` тут нет нарочно. Страница ученика собиралась тем же
    `QuestionListSerializer`, что и экран банка, — и вместе с условием уносила ключ
    книги: правило «эталон показываем только после вердикта человека» обходилось
    одним открытым DevTools. Внутренности приёмки (`provenance`, `uncertain`,
    `verification_status`) ученику тоже нечего делать в ответе.
    """
    class Meta:
        model = Question
        fields = ('id', 'text', 'latex', 'image', 'difficulty', 'points')


class MyAssignmentBlockSerializer(AssignmentBlockQuestionsSerializer):
    """Один блок глазами ученика: задачи, его ответы по ним и итог сдачи."""
    expired = serializers.BooleanField(source='assignment.is_expired', read_only=True)
    answers = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()

    class Meta(AssignmentBlockQuestionsSerializer.Meta):
        fields = AssignmentBlockQuestionsSerializer.Meta.fields + ('expired', 'answers', 'progress')

    def get_questions(self, obj):
        return StudentQuestionSerializer(obj.questions, many=True).data

    def get_answers(self, obj):
        submission = self.context.get('submissions', {}).get(obj.pk)
        if submission is None:
            return []
        return StudentAnswerSerializer(submission.answers.all(), many=True).data

    def get_progress(self, obj):
        return self.context.get('scores', {}).get(obj.pk)


