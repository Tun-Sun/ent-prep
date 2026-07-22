"""
Импорт авторских тестов из Google Form по URL или ID.

Использование:
    python manage.py import_form <form_id> --subject=<slug> --topic="Название темы"

    # Сухой прогон
    python manage.py import_form <form_id> --subject=math --topic="Тест" --dry-run

    # С указанием года и языка
    python manage.py import_form <form_id> --subject=physics --topic="Механика" --year=2026 --lang=kk
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from subjects.import_views import import_from_google_form


class Command(BaseCommand):
    help = 'Импорт авторских тестов из Google Form по URL или ID'

    def add_arguments(self, parser):
        parser.add_argument('form_id', type=str, help='URL формы или голый ID редактора')
        parser.add_argument('--subject', type=str, default='', help='Slug предмета')
        parser.add_argument('--topic', type=str, default='', help='Название темы')
        parser.add_argument('--lang', type=str, default='ru', help='Язык вопросов (ru/kk)')
        parser.add_argument('--year', type=int, default=None, help='Год (опционально)')
        parser.add_argument('--dry-run', action='store_true', help='Сухой прогон')

    def handle(self, *args, **options):
        form_id = options['form_id']
        subject_slug = options.get('subject', '')
        topic_name = options.get('topic', '')
        dry_run = options['dry_run']

        if not subject_slug:
            raise CommandError('Укажите --subject (slug предмета)')
        if not topic_name:
            raise CommandError('Укажите --topic (название темы)')

        result = import_from_google_form(
            form_id=form_id,
            subject_slug=subject_slug,
            topic_name=topic_name,
            language=options.get('lang', 'ru'),
            year=options.get('year'),
            dry_run=dry_run,
        )

        if not result['ok']:
            raise CommandError(result.get('error', 'Неизвестная ошибка'))

        meta = result.get('meta', {})
        self.stdout.write(self.style.SUCCESS(
            f'\n  Форма: {meta.get("form_title", "")}'
            f'\n  Предмет: {meta.get("subject", "")}'
            f'\n  Тема: {meta.get("topic", "")}'
            f'\n  Вопросов: {meta.get("questions_in_form", 0)}'
            f'\n  С правильными ответами: {meta.get("with_correct_answers", 0)}'
            f'\n  С картинками: {meta.get("with_images", 0)}'
            f'\n  Источник: {meta.get("source", "")}'
        ))

        if result.get('warnings'):
            for w in result.get('warnings', []):
                self.stdout.write(self.style.WARNING(f'  ⚠ {w}'))

        if dry_run:
            self.stdout.write(self.style.NOTICE('\n  Сухой прогон — данные не сохранены'))
            return

        result_data = result.get('result', {})
        self.stdout.write(self.style.SUCCESS(
            f'\n  Импортировано: {result_data.get("created", 0)}'
            f'\n  Пропущено (дубли): {result_data.get("skipped_duplicates", 0)}'
            f'\n  В черновиках (без ответа): {result_data.get("drafted_no_correct", 0)}'
            f'\n  Привязано картинок: {result.get("attached_images", 0)}'
        ))
