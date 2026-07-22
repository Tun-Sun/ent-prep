from django.contrib import admin
from django.shortcuts import render
from django.contrib import messages
from functools import wraps

from .models import Subject, Topic, Question, Answer
from .import_views import import_from_google_form


class TopicInline(admin.TabularInline):
    """Темы прямо на странице предмета — удобно при первичном наполнении."""
    model = Topic
    extra = 0
    show_change_link = True


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'icon', 'topics_count', 'questions_count')
    list_display_links = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name', 'slug')
    inlines = [TopicInline]

    @admin.display(description='Тем')
    def topics_count(self, obj):
        return obj.topics.count()

    @admin.display(description='Вопросов')
    def questions_count(self, obj):
        return Question.objects.filter(topic__subject=obj).count()


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject', 'questions_count')
    list_filter = ('subject',)
    search_fields = ('name',)
    autocomplete_fields = ('subject',)

    @admin.display(description='Вопросов')
    def questions_count(self, obj):
        return obj.questions.count()


class AnswerInline(admin.TabularInline):
    """Варианты ответов прямо в карточке вопроса."""
    model = Answer
    extra = 0
    fields = ('text', 'is_correct', 'image')
    readonly_fields = ()


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = (
        'short_text', 'subject_column', 'topic', 'difficulty',
        'source_type', 'verification_status', 'language', 'year',
        'has_image',
    )
    list_display_links = ('short_text',)
    list_filter = (
        'source_type', 'verification_status', 'difficulty',
        'language', 'year', 'topic__subject',
    )
    search_fields = ('text', 'external_id', 'explanation')
    autocomplete_fields = ('topic',)
    list_select_related = ('topic__subject',)
    inlines = [AnswerInline]
    actions = ['mark_verified', 'mark_draft', 'mark_rejected']

    fieldsets = (
        ('Содержание', {
            'fields': ('text', 'topic', 'difficulty', 'explanation', 'image'),
        }),
        ('Происхождение и проверка', {
            'fields': (
                'source_type', 'verification_status',
                'language', 'year', 'external_id',
            ),
            'description': (
                'Поля используются конвейером импорта из Google Forms. '
                'external_id защищает от повторного импорта — не меняйте '
                'его для авторских вопросов без необходимости.'
            ),
        }),
        ('Картинка из Google Drive', {
            'fields': ('image_ref',),
            'classes': ('collapse',),
            'description': (
                'Drive file ID для отложенной загрузки картинки. '
                'После скачивания очищается.'
            ),
        }),
        ('AI-разбор (Этап 2)', {
            'fields': ('ai_explanation',),
            'classes': ('collapse',),
            'description': 'Объяснение генерируется через Google Gemini.',
        }),
    )

    @admin.display(description='Вопрос', ordering='text')
    def short_text(self, obj):
        return obj.text[:80]

    @admin.display(description='Предмет', ordering='topic__subject')
    def subject_column(self, obj):
        return obj.topic.subject.name

    @admin.display(description='Картинка', boolean=True)
    def has_image(self, obj):
        return bool(obj.image)

    @admin.action(description='✅ Пометить проверенными')
    def mark_verified(self, request, queryset):
        updated = queryset.update(verification_status='verified')
        self.message_user(request, f'Проверено вопросов: {updated}')

    @admin.action(description='✏️ Перевести в черновики')
    def mark_draft(self, request, queryset):
        updated = queryset.update(verification_status='draft')
        self.message_user(request, f'В черновики переведено: {updated}')

    @admin.action(description='⛔ Пометить отклонёнными')
    def mark_rejected(self, request, queryset):
        updated = queryset.update(verification_status='rejected')
        self.message_user(request, f'Отклонено вопросов: {updated}')


# ── Admin-страница импорта из Google Forms ────────────────────────────────

def _import_google_form_admin_view(request):
    """Страница импорта авторских тестов из Google Form в админке."""
    result = None
    if request.method == 'POST':
        form_id = request.POST.get('form_id', '').strip()
        subject_slug = request.POST.get('subject_slug', '').strip()
        topic_name = request.POST.get('topic_name', '').strip()
        language = request.POST.get('language', 'ru').strip() or 'ru'
        dry_run = request.POST.get('dry_run') == 'on'
        year_raw = request.POST.get('year', '').strip()
        year = int(year_raw) if year_raw.isdigit() else None

        if not form_id:
            messages.error(request, 'Укажите form_id')
        elif not subject_slug:
            messages.error(request, 'Укажите предмет')
        elif not topic_name:
            messages.error(request, 'Укажите тему')
        else:
            result = import_from_google_form(
                form_id=form_id,
                subject_slug=subject_slug,
                topic_name=topic_name,
                language=language,
                year=year,
                dry_run=dry_run,
            )
            if result['ok']:
                if result.get('dry_run'):
                    messages.warning(request, 'Сухой прогон — данные не сохранены')
                else:
                    created = result.get('result', {}).get('created', 0)
                    messages.success(request, f'Импортировано вопросов: {created}')
            else:
                messages.error(request, result.get('error', 'Неизвестная ошибка'))

    return render(request, 'admin/subjects/import_google_form.html', {
        'subjects': Subject.objects.all().order_by('name'),
        'result': result,
        'title': 'Импорт из Google Forms',
    })


# Добавляем URL в админку
_orig_get_urls = admin.site.get_urls

@wraps(_orig_get_urls)
def _admin_get_urls():
    from django.urls import path
    urls = _orig_get_urls()
    urls.insert(0, path(
        'import-google-form/',
        admin.site.admin_view(_import_google_form_admin_view),
        name='import-google-form',
    ))
    return urls

admin.site.get_urls = _admin_get_urls

# Используем кастомный index-шаблон со ссылкой на импорт
admin.site.index_template = 'admin/index_with_import.html'
