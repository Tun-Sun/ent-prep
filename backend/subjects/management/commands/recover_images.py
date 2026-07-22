from __future__ import annotations

import requests as _requests

from django.core.management.base import BaseCommand, CommandError

from subjects.google_forms.fetcher import fetch_form
from subjects.google_forms.answers import _get_forms_service
from subjects.google_forms.images import _save_image_to_question
from subjects.models import Question


class Command(BaseCommand):
    help = 'Восстанавливает картинки для вопросов, импортированных из Google Form'

    def add_arguments(self, parser):
        parser.add_argument('form_url', type=str, help='URL Google Form')
        parser.add_argument('--dry-run', action='store_true', help='Только показать, какие картинки будут скачаны')

    def handle(self, *args, **options):
        form_url = options['form_url']
        dry_run = options['dry_run']

        # 1. Скрапинг — получаем вопросы с external_id
        self.stdout.write(f'Скрапинг формы: {form_url}')
        scrape = fetch_form(form_url)
        if not scrape.questions:
            raise CommandError('Не удалось получить вопросы из формы')

        # 2. Forms API — получаем contentUri картинок
        form_id = scrape.form_id
        if not form_id:
            self.stdout.write(self.style.WARNING('Не удалось определить form_id'))
            return

        service = _get_forms_service()
        if not service:
            self.stdout.write(self.style.ERROR('Forms API недоступен (нет Service Account)'))
            return

        self.stdout.write(f'  Вопросов: {len(scrape.questions)}')
        self.stdout.write('Получение картинок через Forms API...')

        try:
            form = service.forms().get(formId=form_id).execute()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Forms API error: {e}'))
            return

        # Собираем URI только для choice-вопросов (в порядке scraper-индекса)
        api_uris: list[str] = []
        for item in form.get('items', []):
            qi = item.get('questionItem', {})
            if not qi:
                continue
            q = qi.get('question', {})
            if not q.get('choiceQuestion'):
                continue
            uri = qi.get('image', {}).get('contentUri', '') or q.get('image', {}).get('contentUri', '')
            api_uris.append(uri)

        self.stdout.write(f'  Найдено {len(api_uris)} choice-вопросов в Forms API, '
                          f'из них с картинками: {sum(1 for u in api_uris if u)}')

        matched = 0
        downloaded = 0
        errors = 0
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

        for idx, sq in enumerate(scrape.questions):
            ext_id = sq['external_id'] if isinstance(sq, dict) else sq.external_id
            question = Question.objects.filter(
                source_type='authorial', external_id=ext_id
            ).first()

            if not question:
                self.stdout.write(f'  [{idx}] Вопрос {ext_id} не найден в БД')
                continue

            matched += 1

            # Берём URI из Forms API по тому же индексу
            if idx >= len(api_uris) or not api_uris[idx]:
                self.stdout.write(f'  [{idx}] Q{question.id}: нет URI в Forms API')
                continue

            uri = api_uris[idx]
            if dry_run:
                self.stdout.write(f'  [{idx}] Q{question.id}: будет скачан {uri[:60]}...')
                continue

            try:
                resp = _requests.get(uri, headers=headers, timeout=15)
                if resp.status_code == 200 and len(resp.content) > 100:
                    _save_image_to_question(question, resp.content, f'api_{idx}')
                    downloaded += 1
                    self.stdout.write(self.style.SUCCESS(
                        f'  [{idx}] Q{question.id}: {len(resp.content)} bytes'
                    ))
                else:
                    errors += 1
                    self.stdout.write(self.style.ERROR(
                        f'  [{idx}] Q{question.id}: статус {resp.status_code}'
                    ))
            except Exception as e:
                errors += 1
                self.stdout.write(self.style.ERROR(
                    f'  [{idx}] Q{question.id}: {e}'
                ))

        self.stdout.write()
        if dry_run:
            self.stdout.write(self.style.NOTICE(
                f'Сухой прогон. Совпало вопросов: {matched}'
            ))
            return

        self.stdout.write(self.style.SUCCESS(
            f'Скачано: {downloaded}, ошибок: {errors}'
        ))
