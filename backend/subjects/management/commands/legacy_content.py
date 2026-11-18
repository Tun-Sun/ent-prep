"""Мягкое скрытие старого банка и возврат его одной командой.

    python manage.py legacy_content --hide              # снимок + скрыть всё, кроме 6 вариантов
    python manage.py legacy_content --hide --allow-empty # то же, даже если варианты пустые
    python manage.py legacy_content --status
    python manage.py legacy_content --restore            # из последнего снимка

Ничего не удаляется: `is_visible=False` у `Subject` убирает предмет из каталога,
старта теста, выбора профилей, прогресса и дуэлей (`is_visible` проверяют
subjects/views, tests/views, users/views, dashboard/views, gamification/views).
Вопросы, темы, сессии и ответы остаются на месте.

Снимок нужен потому, что часть предметов скрыта осознанно ещё до этой задачи
(литературы, право, биология): «показать всё» вернуло бы лишнее, а снимок
восстанавливает ровно прежнее состояние.
"""
from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from subjects.models import Question, Subject
from subjects.trial_variants import TRIAL_SLUGS, answerable_count

SNAPSHOT_GLOB = 'legacy_visibility_*.json'


def snapshot_dir() -> Path:
    path = Path(settings.BASE_DIR) / 'var'
    path.mkdir(parents=True, exist_ok=True)
    return path


def latest_snapshot() -> Path | None:
    files = sorted(snapshot_dir().glob(SNAPSHOT_GLOB))
    return files[-1] if files else None


class Command(BaseCommand):
    help = 'Скрывает/возвращает старый банк, оставляя только пробные варианты'

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument('--hide', action='store_true',
                           help='Сделать снимок и скрыть всё, кроме пробных вариантов')
        group.add_argument('--restore', action='store_true',
                           help='Вернуть видимость из снимка')
        group.add_argument('--status', action='store_true',
                           help='Показать состояние (по умолчанию)')
        parser.add_argument('--keep', action='append', default=[],
                            metavar='SLUG',
                            help='Дополнительный слаг, который оставить видимым')
        parser.add_argument('--allow-empty', action='store_true',
                            help='Скрывать, даже если у пробных вариантов нет вопросов')
        parser.add_argument('--snapshot', default=None,
                            help='Путь к снимку для --restore (по умолчанию последний)')

    # === вход ==============================================================

    def handle(self, *args, **options):
        if options['hide']:
            return self._hide(options)
        if options['restore']:
            return self._restore(options)
        return self._status()

    # === скрытие ===========================================================

    def _hide(self, options):
        keep = set(TRIAL_SLUGS) | set(options['keep'])

        existing = set(Subject.objects.filter(slug__in=keep)
                       .values_list('slug', flat=True))
        missing = sorted(keep - existing)
        if missing:
            raise CommandError(
                'Не найдены пробные варианты: ' + ', '.join(missing) +
                '. Сначала выполните: python manage.py trial_variants')

        empty = [subject for subject in Subject.objects.filter(slug__in=keep)
                 if answerable_count(subject) == 0]
        if empty and not options['allow_empty']:
            names = ', '.join(f'{s.slug} ({s.name})' for s in empty)
            raise CommandError(
                f'У вариантов нет вопросов: {names}. '
                'Импортируйте формы (import_from_google_forms) и повторите, '
                'либо запустите с --allow-empty, чтобы скрыть банк заранее.')

        targets = list(Subject.objects.exclude(slug__in=keep)
                       .order_by('sort_order', 'name'))
        snapshot = {
            'created_at': timezone.now().isoformat(),
            'keep': sorted(keep),
            'subjects': [
                {'id': subject.id, 'slug': subject.slug,
                 'name': subject.name, 'was_visible': subject.is_visible}
                for subject in targets
            ],
        }

        path = snapshot_dir() / timezone.now().strftime('legacy_visibility_%Y-%m-%d_%H-%M-%S.json')
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2),
                        encoding='utf-8')

        with transaction.atomic():
            hidden = Subject.objects.filter(id__in=[t.id for t in targets]) \
                .update(is_visible=False)

        self.stdout.write(self.style.SUCCESS(
            f'Скрыто предметов: {hidden}. Снимок: {path}'))
        self.stdout.write(
            f'Оставлено видимыми: {", ".join(sorted(keep))}. '
            f'Вопросы и история решений не тронуты.')

    # === возврат ===========================================================

    def _restore(self, options):
        if options['snapshot']:
            path = Path(options['snapshot'])
            if not path.exists():
                raise CommandError(f'Снимок не найден: {path}')
        else:
            path = latest_snapshot()
            if path is None:
                raise CommandError(
                    f'В {snapshot_dir()} нет снимков ({SNAPSHOT_GLOB}). '
                    'Сначала выполните --hide.')

        data = json.loads(path.read_text(encoding='utf-8'))
        restored, missing = 0, []

        with transaction.atomic():
            for row in data.get('subjects', []):
                subject = Subject.objects.filter(id=row.get('id')).first() \
                    or Subject.objects.filter(slug=row.get('slug')).first()
                if subject is None:
                    missing.append(row.get('slug') or str(row.get('id')))
                    continue
                want = bool(row.get('was_visible'))
                if subject.is_visible != want:
                    subject.is_visible = want
                    subject.save(update_fields=['is_visible'])
                    restored += 1

        self.stdout.write(self.style.SUCCESS(
            f'Восстановлено из {path.name}: изменено {restored}'))
        if missing:
            self.stdout.write(self.style.WARNING(
                'Не найдены (пропущены): ' + ', '.join(missing)))

    # === состояние =========================================================

    def _status(self):
        trial = list(Subject.objects.filter(slug__in=TRIAL_SLUGS)
                     .order_by('sort_order', 'name'))
        self.stdout.write(self.style.MIGRATE_HEADING('Пробные варианты:'))
        if not trial:
            self.stdout.write('  нет — выполните manage.py trial_variants')
        for subject in trial:
            self.stdout.write(
                f'  {subject.slug}: visible={subject.is_visible} '
                f'track={subject.track or "—"} '
                f'вопросов={answerable_count(subject)} '
                f'question_count={subject.question_count} '
                f'time_limit={subject.time_limit}')

        others = Subject.objects.exclude(slug__in=TRIAL_SLUGS)
        self.stdout.write(
            f'\nСтарый банк: {others.count()} предметов, '
            f'видимых {others.filter(is_visible=True).count()}, '
            f'скрытых {others.filter(is_visible=False).count()}, '
            f'вопросов {Question.objects.exclude(topic__subject__slug__in=TRIAL_SLUGS).count()}')

        path = latest_snapshot()
        self.stdout.write(f'Последний снимок: {path if path else "нет"}')
