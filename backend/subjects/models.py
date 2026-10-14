from django.db import models
from django.conf import settings
from django.db.models import Q
import re

FIGURE_LINE = re.compile(r"^!\[[^\]]*\]\(([^)]+)\)\s*$")
MATH_NOISE = re.compile(r"\*\*|\\tag\{[^}]*\}")

# Типы, на которые ученик может ответить выбором. Открытый ответ варианта не имеет.
CHOICE_TYPES = ('single_choice', 'multiple_choice', 'matching')


class QuestionQuerySet(models.QuerySet):
    def answerable(self):
        """Вопросы, которые вообще можно отдать ученику в тест или дуэль.

        Открытая задача из банка оцифровки не имеет вариантов: ответить нечем,
        а `_score_question` за любой тип вне CHOICE_TYPES начисляет 0. Молча
        набрать их в сессию — значит отнять у ученика баллы за то, что он их не терял.
        Второй признак — хоть один правильный вариант: тест без ключа проверять нечем.
        """
        return self.filter(question_type__in=CHOICE_TYPES).filter(
            id__in=Answer.objects.filter(is_correct=True).values('question_id'),
        )


def plain_from_latex(latex):
    """Условие по-человечески из Markdown+LaTeX.

    Ограничители формул остаются в тексте: весь UI читает text через FormattedText, а без
    `$…$` ему нечего отдавать KaTeX — на экране стояло `10\\text{ м}` вместо 10 м. Снимаем
    markdown-шум и напечатанный номер формулы (\\tag), он в external_id.
    Это не замена latex, а то, что видно везде, где банк из книг не подключён
    (игровой тест, админка, выгрузка). Одна функция на генератор и на правку:
    иначе отредактированная задача разошлась бы по text с импортированной.
    """
    lines = []
    for ln in (latex or "").split("\n"):
        if FIGURE_LINE.match(ln.strip()):
            lines.append("[рисунок]")
            continue
        lines.append(MATH_NOISE.sub("", ln))
    return "\n".join(lines).strip()


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
    ent_question_count = models.IntegerField(default=40, verbose_name='Вопросов на ЕНТ')
    ent_max_score = models.FloatField(default=50, verbose_name='Макс. баллов на ЕНТ')
    ent_threshold = models.FloatField(default=5, verbose_name='Пороговый балл ЕНТ')

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
        # Оцифровка бумажного задачника: скан → Gemini Vision → Markdown+LaTeX.
        ('book_scan', 'Оцифровано из книги'),
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
        # Задача из учебника: ответ студент пишет сам, варианта нет.
        ('open_answer', 'Открытый ответ'),
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
    # Школьный класс, к которому задачу относит тренер (5..11). Поле `year` для этого
    # не годится: там год ЕНТ или сборника, а не программа класса. Книга остаётся
    # в provenance.book — класс из неё не выводится, его решает человек.
    grade = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True,
                                             verbose_name='Класс')
    # Внешний идентификатор для дедупликации при импорте.
    # Для Google Forms: "<formId>/<itemId>". Пустой для собранных вопросов.
    external_id = models.CharField(
        max_length=150, blank=True, default='', db_index=True,
        verbose_name='Внешний ID',
    )
    # Закладка под AI-разбор ошибок (Этап 2.1).
    ai_explanation = models.TextField(blank=True, default='', verbose_name='AI-объяснение')

    # --- Оцифровка бумажного задачника (Этап 1: скан → Gemini Vision → KaTeX) ---
    # text остаётся HTML'ом для текущих 34k вопросов; формулы в нём терять нельзя,
    # поэтому LaTeX живёт отдельными полями и рендерится на фронте тем же KaTeX.
    latex = models.TextField(blank=True, default='', verbose_name='Условие в LaTeX')
    latex_answer = models.TextField(
        blank=True, default='', verbose_name='Ответ в LaTeX',
        help_text='Заполняется только когда в источнике есть отдельный ответ.',
    )
    solution_latex = models.TextField(blank=True, default='', verbose_name='Решение в LaTeX')
    # Паспорт задачи: прогон, страница и строка скана, хэш источника, разрешение,
    # модель, хэш промпта. Нужен, чтобы спорный знак вели не «по странице отчёта»,
    # а по конкретной задаче, и чтобы правку можно было откатить к оригиналу.
    provenance = models.JSONField(null=True, blank=True, verbose_name='Паспорт источника')
    # Спорные знаки распознавания: [{char, page, line, why}]. Пока пусто — значит
    # модель не ставила под вопрос ни один знак, а не то что вопрос проверен.
    uncertain = models.JSONField(default=list, blank=True, verbose_name='Спорные знаки')

    objects = QuestionQuerySet.as_manager()

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

    def restore_ocr_original(self):
        """Вернуть условие и ответ к снимку из оцифровки (provenance.ocr_original).

        True, если откатывать есть к чему. Метку «правил человек» снимаем:
        строка снова машинная, и утверждать, что её видел глаз, было бы ложью.
        Статус вычитки и сложность не трогаем — их откат не просили.
        """
        prov = dict(self.provenance or {})
        orig = prov.get('ocr_original') or {}
        if not orig:
            return False
        for f in ('latex', 'latex_answer'):
            if f in orig:
                setattr(self, f, orig[f])
        self.text = plain_from_latex(self.latex) or '(пустое условие)'
        for k in ('ocr_original', 'human_edited', 'edited_at', 'edited_by'):
            prov.pop(k, None)
        self.provenance = prov
        self.save()
        return True


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


class Assignment(models.Model):
    """Домашнее задание, набранное по уровню сложности из банка.

    Список задач фиксируется в момент создания (`question_ids`, как у `Duel`):
    ученик обязан видеть ровно то, что утвердил тренер, а не то, что через
    неделю покажет тот же фильтр по уровню — банк пополняется и правится.
    Проверкой на «балл» это не является, и специально: задачи оцифровки открытые,
    ключа варианта у них нет, поэтому здесь не нужен `answerable()` —
    ученик пишет решение, а не выбирает букву.
    """
    STATUS_CHOICES = [
        ('active', 'Назначено'),
        ('revoked', 'Отозвано'),
    ]

    title = models.CharField(max_length=200, verbose_name='Название')
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='assignments', verbose_name='Учитель')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE,
                                related_name='assignments', verbose_name='Предмет')
    # уровень — тот же вопрос, что и у задачи: один список подписей на банк и на назначение
    difficulty = models.CharField(max_length=10, choices=Question.DIFFICULTY_CHOICES,
                                  verbose_name='Уровень')
    students = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True,
                                      related_name='student_assignments', verbose_name='Ученики')
    question_ids = models.JSONField(default=list, verbose_name='ID задач')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active',
                              verbose_name='Статус')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')

    class Meta:
        verbose_name = 'Назначение'
        verbose_name_plural = 'Назначения'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} — {self.get_difficulty_display()} ({len(self.question_ids or [])} задач)'

    @property
    def questions(self):
        """Задачи в том порядке, в каком их набрал экран, а не в порядке БД."""
        found = {q.pk: q for q in Question.objects.filter(pk__in=self.question_ids)}
        return [found[i] for i in (self.question_ids or []) if i in found]
