# -*- coding: utf-8 -*-
"""Проверка подписи Telegram Login Widget (вход из учебного чата).

Telegram отдаёт набор полей и `hash`, посчитанный так: строка `key=value` по полям
в алфавитном порядке без `hash`, ключ HMAC — `SHA256(bot_token)`, сам HMAC — SHA256.
Секрет бота знает только сервер, поэтому подделать чужой `id` нельзя, не зная его.

Пустой токен бота = вход через Telegram закрыт, а не «подпись не проверяется» —
ровно как с секретом перехода GetCourse.
"""
import hashlib
import hmac
import time

# Поля, которые виджет подписывает; `hash` в строку проверки не входит по определению.
SIGNED_FIELDS = ('id', 'first_name', 'last_name', 'username', 'photo_url', 'auth_date')
HASH_FIELDS = ('hash', 'web_app_hash')


def normalize(payload):
    """Только непустые строки: Telegram не подписывает поле, которого нет."""
    out = {}
    for field in SIGNED_FIELDS:
        value = (payload.get(field) or '').strip()
        if value:
            out[field] = value
    return out


def data_check_string(data):
    """Строка проверки: поля по алфавиту, самой подписи в ней нет."""
    return '\n'.join('%s=%s' % (k, data[k]) for k in sorted(data) if k not in HASH_FIELDS)


def secret_key(bot_token):
    return hashlib.sha256(bot_token.encode('utf-8')).digest()


def make_hash(bot_token, data):
    return hmac.new(secret_key(bot_token), data_check_string(data).encode('utf-8'),
                    hashlib.sha256).hexdigest()


def is_fresh(auth_date, now=None, max_age=86400):
    """Свежесть ответа: без неё перехваченную связку полей можно подавать вечно.

    Telegram сам рекомендует окно в сутки; `auth_date` — целое число секунд с эпохи.
    """
    try:
        stamp = int(str(auth_date).strip())
    except (TypeError, ValueError):
        return False
    return (now if now is not None else int(time.time())) - stamp <= max_age


def verify(bot_token, payload, now=None, max_age=86400):
    """Возвращает (данные, ошибка). Пустой набор — значит подпись не сошлась.

    `id` обязано быть: без него неотличим «ученик без имени» от пустого запроса,
    а по `id` потом ищется аккаунт.
    """
    if not bot_token:
        return None, 'Вход через Telegram на сервере не настроен'
    data = normalize(payload)
    if 'id' not in data or 'auth_date' not in data:
        return None, 'Telegram не прислал идентификатор или дату входа'
    provided = str(payload.get('hash') or '').strip().lower()
    if not provided:
        return None, 'В ответе Telegram нет подписи'
    if not hmac.compare_digest(make_hash(bot_token, data), provided):
        return None, 'Подпись Telegram не совпала'
    if not is_fresh(data['auth_date'], now=now, max_age=max_age):
        return None, 'Ответ Telegram слишком старый, войдите заново'
    return data, ''
