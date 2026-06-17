from django.db import models


class Subject(models.Model):
    name = models.CharField(max_length=100, verbose_name='Название')
    slug = models.SlugField(max_length=50, unique=True)
    icon = models.CharField(max_length=50, default='📚')
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Предмет'
        verbose_name_plural = 'Предметы'
        ordering = ['name']

    def __str__(self):
        return self.name


class Topic(models.Model):
    name = models.CharField(max_length=200, verbose_name='Название темы')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='topics')

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

    text = models.TextField(verbose_name='Текст вопроса')
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='questions')
    difficulty = models.CharField(
        max_length=10, choices=DIFFICULTY_CHOICES, default='medium'
    )
    explanation = models.TextField(blank=True, verbose_name='Объяснение')
    # Картинка к вопросу (график, схема, чертёж, формула-картинка)
    image = models.ImageField(upload_to='questions/', blank=True, null=True, verbose_name='Картинка')

    class Meta:
        verbose_name = 'Вопрос'
        verbose_name_plural = 'Вопросы'

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
