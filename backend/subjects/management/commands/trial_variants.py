"""Создание шести пробных вариантов «Пробные от INTELLECT» и sync их счётчиков.

    python manage.py trial_variants                 # создать/выровнять метаданные
    python manage.py trial_variants --dry-run       # показать, что изменится
    python manage.py trial_variants --sync          # question_count/time_limit по факту
    python manage.py trial_variants --sync --time-limit 14400   # жёсткий регламент
    python manage.py trial_variants --hidden        # заготовить карточки, не показывать

Команда идемпотентна: повторный запуск ничего не дублирует и не затирает
импортированные вопросы — они живут в темах предмета.
"""
from django.core.management.base import BaseCommand, CommandError

from subjects.trial_variants import (DEFAULT_SECONDS_PER_QUESTION, TRIAL_SLUGS,
                                     ensure_trial_variants, sync_counts)


class Command(BaseCommand):
    help = 'Создаёт/обновляет 6 пробных вариантов ЕНТ 01–03 и NUET 01–03'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Только показать изменения, ничего не писать')
        parser.add_argument('--sync', action='store_true',
                            help='Проставить question_count/time_limit по факту вопросов')
        parser.add_argument('--seconds-per-question', type=int,
                            default=DEFAULT_SECONDS_PER_QUESTION,
                            help='Сколько секунд на вопрос при автолимите (по умолчанию 60)')
        parser.add_argument('--time-limit', type=int, default=None,
                            help='Общий лимит времени в секундах для всех шести вариантов')
        parser.add_argument('--hidden', action='store_true',
                            help='Создать/выровнять варианты скрытыми: показывать, '
                                 'только когда залиты вопросы')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        seconds = options['seconds_per_question']
        if seconds <= 0:
            raise CommandError('--seconds-per-question должен быть больше нуля')
        if options['time_limit'] is not None and options['time_limit'] <= 0:
            raise CommandError('--time-limit должен быть больше нуля')

        result = ensure_trial_variants(dry_run=dry_run,
                                      visible=not options['hidden'])
        prefix = 'DRY-RUN · ' if dry_run else ''
        self.stdout.write(f"{prefix}создано: {len(result['created'])}"
                          f" {', '.join(result['created']) or '—'}")
        self.stdout.write(f"{prefix}обновлено: {len(result['updated'])}"
                          f" {', '.join(result['updated']) or '—'}")
        self.stdout.write(f"{prefix}без изменений: {len(result['unchanged'])}")
        if options['hidden']:
            self.stdout.write(self.style.WARNING(
                'Варианты скрыты (is_visible=False): показывать их будет '
                'legacy_content --hide/--restore после импорта вопросов.'))

        if not options['sync']:
            self.stdout.write(self.style.NOTICE(
                f'\nВсего вариантов: {len(TRIAL_SLUGS)}. '
                f'Счётчики не трогали: добавьте --sync после импорта вопросов.'))
            return

        report = sync_counts(seconds_per_question=seconds,
                             time_limit=options['time_limit'], dry_run=dry_run)
        self.stdout.write('\n' + self.style.MIGRATE_HEADING('Счётчики по факту вопросов:'))
        for row in report:
            if row.get('missing'):
                self.stderr.write(f"  ⚠ {row['slug']}: предмет не создан")
                continue
            if row.get('skipped'):
                self.stdout.write(
                    f"  · {row['slug']}: вопросов 0 — оставил "
                    f"question_count={row['question_count']}, "
                    f"time_limit={row['time_limit']}")
                continue
            mark = '→' if row.get('changed') else '='
            self.stdout.write(
                f"  {mark} {row['slug']}: вопросов {row['questions']}, "
                f"question_count={row['question_count']}, "
                f"time_limit={row['time_limit']} "
                f"({row['time_limit'] // 60} мин)")

        if any(row.get('questions') == 0 for row in report):
            self.stdout.write(self.style.WARNING(
                '\nУ части вариантов нет вопросов — импортируйте формы '
                'через import_from_google_forms или /teacher/import-forms.'))
