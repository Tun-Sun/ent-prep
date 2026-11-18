"""Заливка шести форм «Пробные от INTELLECT» в подготовленные варианты.

    python manage.py trial_import --form ent-01=https://docs.google.com/forms/d/<ID>/edit \
                                 --form ent-02=... --form nuet-03=...
    python manage.py trial_import --from-file links.json          # {"ent-01": "...", ...}
    python manage.py trial_import --form ent-01=<ID> --dry-run    # только проверить форму

Вариант должен существовать (`manage.py trial_variants`), но не обязан быть
видимым: команда заливает вопросы и сама выравнивает `question_count`/
`time_limit`, а показывать вариант ученикам будет `legacy_content --hide`.

Повторный запуск безопасен: импортёр пропускает вопросы, у которых уже есть
`external_id` этой формы, поэтому дозалить забытую форму можно в любой момент.
"""
from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from subjects.models import Subject
from subjects.trial_variants import (DEFAULT_SECONDS_PER_QUESTION, TRIAL_SLUGS,
                                     sync_counts)


class Command(BaseCommand):
    help = 'Импортирует Google Forms в варианты ЕНТ 01–03 / NUET 01–03'

    def add_arguments(self, parser):
        parser.add_argument('--form', action='append', default=[], metavar='SLUG=URL',
                            help='Пара «слаг варианта=ссылка на форму»; можно повторять')
        parser.add_argument('--from-file', default=None, metavar='JSON',
                            help='JSON-объект {"ent-01": "ссылка", ...} вместо --form')
        parser.add_argument('--topic', default='',
                            help='Название темы (по умолчанию — название варианта)')
        parser.add_argument('--dry-run', action='store_true',
                            help='Проверить формы и показать счётчики, ничего не писать')
        parser.add_argument('--no-sync', action='store_true',
                            help='Не трогать question_count/time_limit после импорта')
        parser.add_argument('--seconds-per-question', type=int,
                            default=DEFAULT_SECONDS_PER_QUESTION,
                            help='Сколько секунд на вопрос при автолимите (по умолчанию 60)')

    def handle(self, *args, **options):
        links = self._collect_links(options)
        if not links:
            raise CommandError(
                'Не указаны формы. Пример: --form ent-01=https://docs.google.com/'
                'forms/d/<ID>/edit')

        # Сначала проверяем весь список: половина залитых форм хуже, чем ни одной.
        subjects = {}
        for slug in links:
            if slug not in TRIAL_SLUGS:
                raise CommandError(f'Неизвестный вариант «{slug}». '
                                   f'Допустимые: {", ".join(TRIAL_SLUGS)}')
            subject = Subject.objects.filter(slug=slug).first()
            if subject is None:
                raise CommandError(
                    f'Вариант «{slug}» не создан. Сначала выполните: '
                    'python manage.py trial_variants')
            subjects[slug] = subject

        from subjects.import_views import import_from_google_form

        failed = []
        for slug, url in links.items():
            subject = subjects[slug]
            topic_name = options['topic'] or subject.name
            self.stdout.write(self.style.MIGRATE_HEADING(
                f'\n== {slug}: {subject.name}'))
            self.stdout.write(f'   форма: {url}')
            self.stdout.write(f'   тема:  {topic_name}')

            result = import_from_google_form(
                form_id=url,
                subject_slug=slug,
                topic_name=topic_name,
                dry_run=options['dry_run'],
            )

            meta = result.get('meta') or {}
            for warning in meta.get('warnings') or []:
                self.stdout.write(self.style.WARNING(f'   ! {warning}'))

            if not result.get('ok'):
                failed.append(slug)
                self.stderr.write(self.style.ERROR(
                    f'   ✗ {result.get("error", "импорт не удался")}'))
                continue

            if meta.get('dry_run'):
                self.stdout.write(
                    f'   ✓ вопросов в форме: {meta.get("questions_in_form")}, '
                    f'с ключом: {meta.get("with_correct_answers")}, '
                    f'картинок: {meta.get("with_images")}')
                continue

            stats = result.get('result') or {}
            self.stdout.write(
                f'   ✓ создано: {stats.get("created", 0)}, '
                f'дубликатов: {stats.get("skipped_duplicates", 0)}, '
                f'без ключа: {stats.get("drafted_no_correct", 0)}, '
                f'с картинками: {result.get("attached_images", 0)}')
            for error in stats.get('errors') or []:
                self.stderr.write(self.style.WARNING(f'   ! {error}'))

        if options['dry_run'] or options['no_sync'] or failed:
            if failed:
                raise CommandError('Не удалось импортировать: ' + ', '.join(failed))
            return

        report = sync_counts(seconds_per_question=options['seconds_per_question'])
        self.stdout.write('\n' + self.style.MIGRATE_HEADING('Счётчики после импорта:'))
        for row in report:
            if row.get('skipped'):
                self.stdout.write(f'  · {row["slug"]}: вопросов 0 — пропущен')
                continue
            self.stdout.write(
                f'  {row["slug"]}: вопросов {row["questions"]}, '
                f'question_count={row["question_count"]}, '
                f'time_limit={row["time_limit"]} ({row["time_limit"] // 60} мин)')

        self.stdout.write(self.style.NOTICE(
            '\nДальше: python manage.py legacy_content --hide '
            '— скрыть старый банк и оставить эти варианты.'))

    # --- helpers -----------------------------------------------------------

    def _collect_links(self, options) -> dict[str, str]:
        links: dict[str, str] = {}
        path = options['from_file']
        if path:
            file_path = Path(path)
            if not file_path.exists():
                raise CommandError(f'Файл не найден: {file_path}')
            try:
                data = json.loads(file_path.read_text(encoding='utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise CommandError(f'Не удалось прочитать {file_path}: {exc}')
            if not isinstance(data, dict):
                raise CommandError('Ожидался JSON-объект вида {"ent-01": "ссылка"}')
            for slug, url in data.items():
                links[str(slug).strip()] = str(url).strip()

        for item in options['form']:
            if '=' not in item:
                raise CommandError(
                    f'Ожидалось «слаг=ссылка», получено: {item}')
            slug, url = item.split('=', 1)
            slug, url = slug.strip(), url.strip()
            if not url:
                raise CommandError(f'Пустая ссылка для «{slug}»')
            links[slug] = url
        return links
