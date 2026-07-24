from django.db import models
from django.db.models import Q


class Subject(models.Model):
    SUBJECT_TYPE_CHOICES = [
        ('mandatory', 'Обязательный (ЕНТ)'),
        ('profile', 'Профильный (ЕНТ)'),
        ('other', 'Дополнительный'),
    ]

    name = models.CharField(max_length=100, verbose_name='Название')
    slug = models.SlugField(max_length=50, unique=True)
    icon = models.CharField(max_length=50, default='📚')
    description = models.TextField(blank=True)
    is_visible = models.BooleanField(default=True, verbose_name='Виден ученикам')
    sort_order = models.IntegerField(default=0, verbose_name='Порядок сортировки')
    subject_type = models.CharField(
        max_length=12, choices=SUBJECT_TYPE_CHOICES, default='profile',
        verbose_name='Тип предмета',
    )
    question_count = models.IntegerField(default=10, verbose_name='Кол-во вопросов')
    time_limit = models.IntegerField(default=600, verbose_name='Лимит времени (сек)')
    show_in_profiles = models.BooleanField(default=True, verbose_name='Показывать в выборе профилей')

    class Meta:
        verbose_name = 'Предмет'
        verbose_name_plural = 'Предметы'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class Variant(models.Model):
    number = models.IntegerField(verbose_name='Номер варианта')
    name = models.CharField(max_length=200, blank=True, default='', verbose_name='Название')
    year = models.PositiveIntegerField(null=True, blank=True, verbose_name='Год')

    class Meta:
        verbose_name = 'Вариант'
        verbose_name_plural = 'Варианты'
        ordering = ['number']

    def __str__(self):
        return self.name or f'Вариант {self.number}'


class Topic(models.Model):
    name = models.CharField(max_length=200, verbose_name='Название темы')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='topics')
    variant = models.ForeignKey(Variant, on_delete=models.SET_NULL, null=True, blank=True, related_name='topics')

    class Meta:
        verbose_name = 'Тема'
        verbose_name_plural = 'Темы'
        ordering = ['name']

    def __str__(self):
        return f'{self.subject.name} — {self.name}'


class Question(models.Model):
    DIFFICULTY_CHOICES = [
        ('easy', 'Лёгкий'),
        ('medium', 'Средний'),
        ('hard', 'Сложный'),
    ]
    SOURCE_CHOICES = [
        ('collected', 'Собранный'),
        ('authorial', 'Авторский'),
    ]
    VERIFICATION_CHOICES = [
        ('draft', 'Черновик'),
        ('verified', 'Проверен'),
        ('rejected', 'Отклонён'),
    ]
    QUESTION_TYPE_CHOICES = [
        ('single_choice', 'Один правильный'),
        ('multiple_choice', 'Несколько правильных'),
        ('matching', 'На соответствие'),
    ]
    SECTION_CHOICES = [
        ('history', 'История Казахстана'),
        ('reading', 'Грамотность чтения'),
        ('math_lit', 'Математическая грамотность'),
        ('profile1', 'Профильный предмет 1'),
        ('profile2', 'Профильный предмет 2'),
    ]

    text = models.TextField(verbose_name='Текст вопроса')
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='questions')
    difficulty = models.CharField(
        max_length=10, choices=DIFFICULTY_CHOICES, default='medium'
    )
    question_type = models.CharField(
        max_length=20, choices=QUESTION_TYPE_CHOICES, default='single_choice',
        verbose_name='Тип вопроса',
    )
    points = models.FloatField(default=1, verbose_name='Баллы')
    section = models.CharField(
        max_length=12, choices=SECTION_CHOICES, blank=True, default='',
        verbose_name='Секция ЕНТ',
    )
    explanation = models.TextField(blank=True, verbose_name='Объяснение')
    image = models.ImageField(upload_to='questions/', blank=True, null=True, verbose_name='Картинка')
    image_ref = models.CharField(max_length=255, blank=True, default='', db_index=True, verbose_name='Drive file ID')

    # --- Поля происхождения и верификации (Этап 1.1) ---
    source_type = models.CharField(
        max_length=12, choices=SOURCE_CHOICES, default='collected',
        db_index=True, verbose_name='Источник',
    )
    verification_status = models.CharField(
        max_length=12, choices=VERIFICATION_CHOICES, default='draft',
        db_index=True, verbose_name='Статус проверки',
    )
    language = models.CharField(
        max_length=5, default='ru', verbose_name='Язык',
    )
    year = models.PositiveIntegerField(null=True, blank=True, verbose_name='Год')
    # Внешний идентификатор для дедупликации при импорте.
    # Для Google Forms: "<formId>/<itemId>". Пустой для собранных вопросов.
    external_id = models.CharField(
        max_length=150, blank=True, default='', db_index=True,
        verbose_name='Внешний ID',
    )
    # Закладка под AI-разбор ошибок (Этап 2.1).
    ai_explanation = models.TextField(blank=True, default='', verbose_name='AI-объяснение')

    class Meta:
        verbose_name = 'Вопрос'
        verbose_name_plural = 'Вопросы'
        constraints = [
            # Авторские вопросы уникальны по внешнему ID — защищает от повторного импорта.
            # Собранные вопросы имеют external_id='', поэтому в условие не попадают.
            models.UniqueConstraint(
                fields=['source_type', 'external_id'],
                condition=Q(external_id__isnull=False) & ~Q(external_id=''),
                name='uniq_external_id_per_source',
            ),
        ]

    def __str__(self):
        return self.text[:80]


class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers')
    text = models.CharField(max_length=300, verbose_name='Текст ответа')
    is_correct = models.BooleanField(default=False)
    # Картинка к варианту ответа (редко, но бывает на ЕНТ)
    image = models.ImageField(upload_to='answers/', blank=True, null=True, verbose_name='Картинка ответа')

    class Meta:
        verbose_name = 'Вариант ответа'
        verbose_name_plural = 'Варианты ответов'

    def __str__(self):
        return f'{self.text} ({("✓" if self.is_correct else "✗")})'
