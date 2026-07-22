"""
Импорт авторских тестов из JSON-экспорта Google Forms.

JSON получается запуском Apps Script ExportFormToJSON.gs в форме учителя
(см. subjects/google_forms/apps_script/ExportFormToJSON.gs).

Использование:
    # Один файл:
    python manage.py import_from_google_forms path/to/form.json

    # Папка с JSON'ами — все разом:
    python manage.py import_from_google_forms data/google_forms/

    # Дополнительно скачать картинки (Шаг 10, требует Drive API):
    python manage.py import_from_google_forms form.json --with-images

    # Сухой прогон — без записи в БД, только валидация:
    python manage.py import_from_google_forms form.json --dry-run

Повторный запуск того же файла безопасен: дубликаты пропускаются
по (source_type='authorial', external_id).
"""
from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from subjects.google_forms import images as images_mod
from subjects.google_forms.importer import ImporterError, import_payload
from subjects.google_forms.parser import ParseError, parse_file


SUPPORTED_EXT = {'.json'}


class Command(BaseCommand):
    help = 'Импорт авторских вопросов из JSON-экспорта Google Forms'

    def add_arguments(self, parser):
        parser.add_argument(
            'path',
            type=str,
            help='Путь к JSON-файлу или папке с JSON-экспортами Google Forms',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Только валидация, без записи в БД',
        )
        parser.add_argument(
            '--with-images',
            action='store_true',
            help='Доп. шаг: скачать картинки вопросов через Drive API (Шаг 10)',
        )
        parser.add_argument(
            '--difficulty',
            type=str,
            default='medium',
            choices=['easy', 'medium', 'hard'],
            help='Сложность по умолчанию для импортируемых вопросов',
        )

    def handle(self, *args, **options):
        root = Path(options['path'])
        if not root.exists():
            raise CommandError(f'Путь не найден: {root}')

        files = self._collect_files(root)
        if not files:
            raise CommandError(f'Не найдено JSON-файлов в: {root}')

        self.stdout.write(self.style.WARNING(
            f'\n  Импорт из Google Forms\n'
            f'  Файлов: {len(files)}\n'
            f'  Режим: {"сухой прогон" if options["dry_run"] else "импорт"}\n'
        ))

        if options['with_images'] and not images_mod.is_available():
            self.stdout.write(self.style.WARNING(
                '  ⚠ --with-images: Drive API недоступен (Шаг 10 не реализован). '
                'Картинки пропускаются, импорт продолжается.\n'
            ))

        total_created = 0
        total_skipped = 0
        total_drafted = 0
        all_image_ids: list[str] = []

        for fp in files:
            self.stdout.write(f'  ⬆ {fp.name}...', ending='')
            self.stdout.flush()
            try:
                payload = parse_file(fp)
            except ParseError as e:
                self.stdout.write(self.style.ERROR(f' parse error'))
                self.stderr.write(f'    {e}')
                continue

            if options['dry_run']:
                self.stdout.write(self.style.NOTICE(
                    f' OK (dry-run): {len(payload.questions)} вопросов, '
                    f'предмет="{payload.subject_slug or payload.subject_name}", '
                    f'тема="{payload.topic_name}"'
                ))
                continue

            try:
                result = import_payload(payload, default_difficulty=options['difficulty'])
            except ImporterError as e:
                self.stdout.write(self.style.ERROR(' importer error'))
                self.stderr.write(f'    {e}')
                continue
            except Exception as e:  # noqa: BLE001 — показываем пользователю полную ошибку
                self.stdout.write(self.style.ERROR(' unexpected error'))
                self.stderr.write(f'    {type(e).__name__}: {e}')
                continue

            total_created += result.created
            total_skipped += result.skipped_duplicates
            total_drafted += result.drafted_no_correct
            all_image_ids.extend(result.skipped_images)

            self.stdout.write(self.style.SUCCESS(
                f' создано {result.created}, '
                f'дубли {result.skipped_duplicates}, '
                f'без правильного {result.drafted_no_correct}'
            ))
            if result.errors:
                for err in result.errors:
                    self.stderr.write(f'    ⚠ {err}')

        self.stdout.write(f'\n{"="*60}')
        self.stdout.write(self.style.SUCCESS(
            f'  ИТОГО: создано {total_created}, '
            f'дубликатов пропущено {total_skipped}, '
            f'без правильного ответа {total_drafted}\n'
        ))

        # Шаг 10: догрузка картинок одной пачкой.
        if all_image_ids and options['with_images'] and images_mod.is_available():
            self.stdout.write(self.style.WARNING(
                f'  Скачивание {len(all_image_ids)} картинок из Drive...'
            ))
            ok, fail = images_mod.download_for_questions(all_image_ids)
            self.stdout.write(self.style.SUCCESS(
                f'  Картинки: успешно {ok}, ошибок {fail}\n'
            ))
        elif all_image_ids:
            self.stdout.write(self.style.NOTICE(
                f'  ℹ К картинок ({len(all_image_ids)}) привязка отложена '
                f'до реализации Шага 10.\n'
            ))

    # === Сбор файлов =======================================================

    def _collect_files(self, root: Path) -> list[Path]:
        if root.is_file():
            if root.suffix.lower() not in SUPPORTED_EXT:
                raise CommandError(f'Ожидался .json, получено: {root.name}')
            return [root]
        return sorted(
            p for p in root.rglob('*')
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXT
        )
