"""
Создаёт суперпользователя если его ещё нет.
Безопасно запускать多次 — если админ есть, ничего не делает.

Использование:
    python manage.py ensure_admin

Переменные окружения (необязательно, для продакшена):
    ADMIN_USERNAME=admin
    ADMIN_PASSWORD=...
    ADMIN_EMAIL=...
"""

import os
import sys

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = 'Создаёт суперпользователя если его ещё нет'

    def add_arguments(self, parser):
        parser.add_argument('--username', default=os.environ.get('ADMIN_USERNAME', 'admin'))
        parser.add_argument('--email', default=os.environ.get('ADMIN_EMAIL', 'admin@example.com'))
        parser.add_argument('--password', default=os.environ.get('ADMIN_PASSWORD', 'admin12345'))

    def handle(self, *args, **options):
        username = options['username']
        email = options['email']
        password = options['password']

        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(
                f'  Пользователь "{username}" уже существует — пропуск'
            ))
            return

        User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
        )
        self.stdout.write(self.style.SUCCESS(
            f'  ✓ Создан суперпользователь: {username}'
        ))

        # Подсказку не выводим в лог (безопасность), но показываем локально
        if 'test' not in sys.argv:
            self.stdout.write(self.style.WARNING(
                f'  ⚠ Пароль: {password}  (измени в админке после первого входа!)'
            ))
