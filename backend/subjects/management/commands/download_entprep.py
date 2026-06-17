"""
Скачивает все вопросы с entprep.org в локальные JSON файлы.

Использование:
    python manage.py download_entprep
    python manage.py download_entprep --subject physics
    python manage.py download_entprep --output-dir data/
"""

import time
import json
import urllib.request
from pathlib import Path

from django.core.management.base import BaseCommand

# ---------------------------------------------------------------------------
# API конфигурация (та же что в parse_entprep.py)
# ---------------------------------------------------------------------------
API_BASE = 'https://api.entprep.org/rest/v1/questions'
ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im16dHVqbWV5a2hsZ3dxcGRvaWxmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzEyNjI0ODAsImV4cCI6MjA4NjgzODQ4MH0.6_ui3S3wM3uOd-4VuNAQd4h3KFWoXUH2fHrwTNn28fw'

HEADERS = {
    'apikey': ANON_KEY,
    'Authorization': f'Bearer {ANON_KEY}',
    'Accept': 'application/json',
}

SUBJECTS = [
    'biology', 'chemistry', 'english', 'geography', 'history',
    'informatics', 'law', 'literature', 'literature_kazakh',
    'literature_russian', 'math', 'math_profile', 'physics',
    'reading', 'world_history',
]

SELECT = 'q,o,c,e,type,difficulty,topic,subtopic,correct_indices,pairs,passage_text,source'


def fetch_page(filters='', limit=1000, offset=0):
    url = f'{API_BASE}?select={SELECT}&limit={limit}&offset={offset}'
    if filters:
        url += '&' + filters
    req = urllib.request.Request(url, headers=dict(HEADERS))
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read())


def fetch_subject(subject, delay=0.3):
    """Скачивает все вопросы одного предмета с пагинацией."""
    all_rows = []
    offset = 0
    filters = f'subject=eq.{subject}'

    while True:
        rows = fetch_page(filters=filters, limit=1000, offset=offset)
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < 1000:
            break
        offset += 1000
        time.sleep(delay)

    return all_rows


class Command(BaseCommand):
    help = 'Скачивает все вопросы entprep.org в локальные JSON файлы'

    def add_arguments(self, parser):
        parser.add_argument(
            '--subject', type=str, default=None,
            help='Slug конкретного предмета (physics, math, ...)',
        )
        parser.add_argument(
            '--output-dir', type=str, default='data/entprep',
            help='Директория для сохранения JSON (по умолчанию: data/entprep)',
        )
        parser.add_argument(
            '--delay', type=float, default=0.35,
            help='Пауза между запросами (сек)',
        )

    def handle(self, *args, **options):
        subjects = [options['subject']] if options['subject'] else SUBJECTS
        out_dir = Path(options['output_dir'])
        delay = options['delay']

        out_dir.mkdir(parents=True, exist_ok=True)

        self.stdout.write(self.style.WARNING(
            f'\n  Скачать entprep.org → {out_dir}\n'
        ))

        total_questions = 0

        for subject in subjects:
            self.stdout.write(f'  ⬇ {subject}...', ending='')
            self.stdout.flush()

            rows = fetch_subject(subject, delay=delay)
            filepath = out_dir / f'{subject}.json'

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(rows, f, ensure_ascii=False, indent=2)

            self.stdout.write(f'  {len(rows)} вопросов → {filepath}')
            total_questions += len(rows)

            time.sleep(0.2)

        self.stdout.write(self.style.SUCCESS(
            f'\n  ✅ Готово: {len(subjects)} предметов, '
            f'{total_questions:,} вопросов в {out_dir}\n'
        ))
