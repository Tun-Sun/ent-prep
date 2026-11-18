from django.db import models
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
import re

from core.choices import TrackChoices

FIGURE_LINE = re.compile(r"^!\[[^\]]*\]\(([^)]+)\)\s*$")
MATH_NOISE = re.compile(r"\*\*|\\tag\{[^}]*\}")

# Типы, на которые ученик может ответить выбором. Открытый ответ варианта не имеет.
CHOICE_TYPES = ('single_choice', 'multiple_choice', 'matching')
# Короткий ответ: ученик вводит строку, а сверяем её с эталоном сами.
# Отличается от `open_answer` (задача из учебника без ключа): тот в тест не идёт.
SHORT_ANSWER = 'short_answer'


class QuestionQuerySet(models.QuerySet):
    def answerable(self):
        """Вопросы, которые вообще можно отдать ученику в тест или дуэль.

        Открытая задача из банка оцифровки не имеет вариантов: ответить нечем,
        а `_score_question` за любой тип вне CHOICE_TYPES начисляет 0. Молча
        набрать их в сессию — значит отнять у ученика баллы за то, что он их не терял.
        Второй признак — хоть один правильный вариант: тест без ключа проверять нечем.

        Короткий ответ — исключение: вариантов у него нет по определению, но
        эталон есть, и проверяется он сравнением строк. Без эталона он тоже
        не годится: такой вопрос остаётся черновиком.
        """
        return self.filter(
            Q(question_type__in=CHOICE_TYPES) | Q(question_type=SHORT_ANSWER)
        ).filter(
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
    # Пустая строка — общий предмет: он доступен школе, ЕНТ и NUET. Так новые
    # предметы, заведённые без решения о треке, не исчезают у учеников.
    track = models.CharField(max_length=10, choices=TrackChoices.choices, blank=True,
                             default='', db_index=True, verbose_name='Трек')
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
        # Короткий ответ с эталоном (Google Forms, тесты NUET): ученик вводит
        # строку, проверяем сравнением с вариантами, отмеченными is_correct.
        ('short_answer', 'Короткий ответ'),
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
    """Урок: четыре блока задач, набранных из банка.

    Набор задач фиксируется в момент публикации и живёт в `AssignmentBlock.question_ids`
    (как у `Duel`): ученик обязан видеть ровно то, что утвердил тренер, а не то, что
    через неделю покажет тот же фильтр — банк пополняется и правится.
    Проверкой на «балл» это не является, и специально: задачи оцифровки открытые,
    ключа варианта у них нет, поэтому здесь не нужен `answerable()` —
    ученик пишет решение, а не выбирает букву.
    """
    STATUS_CHOICES = [
        ('draft', 'Черновик'),
        ('active', 'Назначено'),
        ('revoked', 'Отозвано'),
    ]

    title = models.CharField(max_length=200, verbose_name='Название')
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='assignments', verbose_name='Учитель')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE,
                                related_name='assignments', verbose_name='Предмет')
    # историческая метка основного набора: экран конструктора её не спрашивает,
    # ступени теперь разложены по блокам (advanced / simplified)
    difficulty = models.CharField(max_length=10, choices=Question.DIFFICULTY_CHOICES,
                                  blank=True, default='', verbose_name='Уровень',
                                  help_text='Более не задаётся: ступени теперь в блоках')
    students = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True,
                                      related_name='student_assignments', verbose_name='Ученики')
    group = models.ForeignKey('users.StudyGroup', on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='assignments', verbose_name='Группа')
    due_at = models.DateTimeField(null=True, blank=True, verbose_name='Срок сдачи')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft',
                              verbose_name='Статус')
    published_at = models.DateTimeField(null=True, blank=True, verbose_name='Опубликовано')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')

    class Meta:
        verbose_name = 'Назначение'
        verbose_name_plural = 'Назначения'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} — {self.get_status_display()} ({self.questions_count} задач)'

    @property
    def blocks_ordered(self):
        return list(self.blocks.order_by('order', 'id'))

    @property
    def questions(self):
        """Задачи всех блоков: блоки по `order`, внутри блока — по позиции в списке."""
        out = []
        for block in self.blocks_ordered:
            out.extend(block.questions)
        return out

    @property
    def questions_count(self):
        return sum(len(b.question_ids or []) for b in self.blocks.all())

    @property
    def is_expired(self):
        return bool(self.due_at and self.due_at < timezone.now())

    def publish(self):
        """Черновик становится уроком: ученик видит его, состав больше не гадают.

        Пустой урок опубликовать нельзя — иначе ученик получил бы страницу без задач.
        """
        if not self.questions_count:
            return False
        self.status = 'active'
        self.published_at = timezone.now()
        self.save(update_fields=['status', 'published_at'])
        return True


class AssignmentBlock(models.Model):
    """Один из четырёх блоков урока.

    `kind` + `order` вместо произвольных названий — решение владельца: четыре блока
    покрывают назначения из реальной практики центра, а свободные блоки заставили бы
    на каждом уроке заново решать, чем «блок 3» отличается от «домашки».
    Порядок задач — позиция в `question_ids`, отдельного поля `position` нет: список
    пишет человек экраном, и порядок в нём — единственный источник истины.
    """
    KIND_CHOICES = [
        ('in_class', 'Классная работа'),
        ('homework', 'Домашка'),
        ('advanced', 'Сложные'),
        ('simplified', 'Упрощённые'),
    ]
    # автопроверку ведут только эти два блока; in_class решают вместе, advanced — запас
    GRADED_KINDS = ('homework', 'simplified')

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='blocks',
                                   verbose_name='Урок')
    kind = models.CharField(max_length=12, choices=KIND_CHOICES, verbose_name='Блок')
    title = models.CharField(max_length=200, blank=True, default='', verbose_name='Заголовок')
    order = models.PositiveSmallIntegerField(default=0, verbose_name='Порядок')
    question_ids = models.JSONField(default=list, verbose_name='ID задач')

    class Meta:
        verbose_name = 'Блок урока'
        verbose_name_plural = 'Блоки урока'
        ordering = ['assignment', 'order', 'id']
        constraints = [
            models.UniqueConstraint(fields=['assignment', 'kind'], name='uniq_kind_per_assignment'),
        ]

    def __str__(self):
        return f'{self.get_kind_display()} — {self.title or self.assignment_id} ({len(self.question_ids or [])})'

    @property
    def label(self):
        return self.title or self.get_kind_display()

    @property
    def autocheck(self):
        """Проверяем ли этот блок машиной.

        `in_class` и `advanced` сдавать не обязаны: их решение и так разбирают на уроке,
        а ложный `pending_review` на каждую такую задачу забил бы очередь ручной
        проверки материалом, который никто в очередь не просил.
        """
        return self.kind in self.GRADED_KINDS

    @property
    def questions(self):
        found = {q.pk: q for q in Question.objects.filter(pk__in=self.question_ids)}
        return [found[i] for i in (self.question_ids or []) if i in found]


class AssignmentSubmission(models.Model):
    """Сдача одного блока одним учеником. Одна строка на (урок, ученик, блок)."""
    STATE_CHOICES = [
        ('in_progress', 'Решает'),
        ('submitted', 'Сдал'),
        ('reviewed', 'Проверено'),
    ]

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions')
    block = models.ForeignKey(AssignmentBlock, on_delete=models.CASCADE, null=True, blank=True,
                              related_name='submissions')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='submissions')
    state = models.CharField(max_length=12, choices=STATE_CHOICES, default='in_progress')
    started_at = models.DateTimeField(auto_now_add=True, verbose_name='Начал')
    last_submitted_at = models.DateTimeField(null=True, blank=True, verbose_name='Сдал')
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name='Проверено')
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='reviewed_submissions',
                                    verbose_name='Кто проверил')

    class Meta:
        verbose_name = 'Сдача'
        verbose_name_plural = 'Сдачи'
        constraints = [
            models.UniqueConstraint(fields=['assignment', 'student', 'block'],
                                    name='uniq_submission_per_block'),
        ]

    def __str__(self):
        return f'{self.student} — {self.block} ({self.get_state_display()})'


class AssignmentAnswer(models.Model):
    """Одна задача одной сдачи: что ученик написал и чем это стало после сверки.

    `raw_answer` неизменяем: «ученик так написал» тренер обязан видеть, даже когда
    сам ставит `partial`. `verdict` — четыре значения, а не булев: `pending_review`
    — это «ещё не проверено», а не «ноль», и в процент блока такие задачи входят
    только после ручной проверки.
    """
    VERDICT_CHOICES = [
        ('correct', 'Верно'),
        ('partial', 'Неполно'),
        ('incorrect', 'Неверно'),
        ('pending_review', 'Ждёт проверки'),
    ]
    JUDGED_BY_CHOICES = [
        ('', 'Машина не решила'),
        ('level1', 'Нормализатор'),
        ('cas', 'SymPy'),
        # значение возможно только если модель реально вызывалась и записала
        # подсказку; сама подсказка живёт в `verdict_note` и итоговый балл не выставляет
        ('model_suggestion', 'Подсказка модели'),
        ('human', 'Преподаватель'),
    ]

    submission = models.ForeignKey(AssignmentSubmission, on_delete=models.CASCADE,
                                   related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='assignment_answers')
    raw_answer = models.TextField(verbose_name='Ответ ученика как есть')
    normalized_answer = models.TextField(blank=True, default='', verbose_name='Что вычленил нормализатор')
    verdict = models.CharField(max_length=14, choices=VERDICT_CHOICES, default='pending_review',
                               verbose_name='Вердикт')
    judged_by = models.CharField(max_length=18, choices=JUDGED_BY_CHOICES, blank=True, default='',
                                 verbose_name='Чем решён вердикт')
    verdict_note = models.TextField(blank=True, default='', verbose_name='Пояснение вердикта')
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='reviewed_answers',
                                    verbose_name='Кто проверил')
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name='Проверена')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Изменена')

    class Meta:
        verbose_name = 'Ответ в уроке'
        verbose_name_plural = 'Ответы в уроке'
        constraints = [
            models.UniqueConstraint(fields=['submission', 'question'], name='uniq_answer_per_submission'),
        ]

    def __str__(self):
        return f'{self.question_id} — {self.verdict} ({self.judged_by or "не решено"})'

    @property
    def points_earned(self):
        """Балл по вердикту. У `pending_review` балла нет — он не начислен и не снят."""
        if self.verdict == 'correct':
            return self.question.points
        if self.verdict == 'partial':
            return self.question.points / 2
        if self.verdict == 'incorrect':
            return 0.0
        return None

    @property
    def feedback(self):
        """Что видит ученик.

        Эталон книги отдаём только после вердикта человека: и в незавершённой сдаче,
        и в «неверно» от машины ответ задачи был бы виден до того, как ученик
        успел её разобрать. Машина сообщает вердикт и свою причину, не показывая ключ.
        """
        return {
            'verdict': self.verdict,
            'verdict_display': self.get_verdict_display(),
            'judged_by': self.judged_by,
            'note': self.verdict_note if self.verdict != 'pending_review'
                    else 'ответ у преподавателя, оценка будет после проверки',
            'etalon': self.question.latex_answer if self.judged_by == 'human' else '',
        }


class LessonReport(models.Model):
    """Журнал отправок итога домашнего блока в GetCourse (Шаг 6.2).

    Строка на (урок, ученик, блок): `external_key` уникален, поэтому повторный клик
    «Сдать блок» не порождает вторую отправку и не заводит дубликат в журнале.
    Ключи GetCourse могут не быть заданы — тогда строка всё равно появляется со
    статусом «не отправлено»: урок виден, а что именно платформа собиралась сообщить
    методисту — читается в журнале, а не додумывается по логам.
    """
    STATUS_CHOICES = [
        ('skipped', 'Не отправлено (ключей GetCourse нет)'),
        ('sent', 'Отправлено'),
        ('failed', 'Ошибка отправки'),
    ]

    external_key = models.CharField(max_length=160, unique=True, verbose_name='Ключ идемпотентности')
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='reports',
                                   verbose_name='Урок')
    block = models.ForeignKey(AssignmentBlock, on_delete=models.CASCADE, null=True, blank=True,
                              related_name='reports', verbose_name='Блок')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='lesson_reports', verbose_name='Ученик')
    gc_uid = models.CharField(max_length=64, blank=True, default='', verbose_name='Код ученика в GetCourse')
    event_type = models.CharField(max_length=48, default='lesson.homework.completed',
                                  verbose_name='Событие')
    percent = models.FloatField(null=True, blank=True, verbose_name='Процент по проверенным')
    total = models.PositiveIntegerField(default=0, verbose_name='Задач в блоке')
    correct = models.PositiveIntegerField(default=0, verbose_name='Решено верно')
    pending_review = models.PositiveIntegerField(default=0, verbose_name='Ждут проверки')
    # наружу идут только числа — ни ответа ученика, ни эталона книги здесь нет
    payload = models.JSONField(default=dict, verbose_name='Что ушло в GetCourse')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='skipped',
                              verbose_name='Итог отправки')
    attempts = models.PositiveIntegerField(default=0, verbose_name='Попыток')
    last_error = models.TextField(blank=True, default='', verbose_name='Последняя ошибка')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Изменено')
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name='Отправлено')

    class Meta:
        verbose_name = 'Отправка в GetCourse'
        verbose_name_plural = 'Отправки в GetCourse'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.external_key} — {self.get_status_display()}'



