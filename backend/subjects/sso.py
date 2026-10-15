"""Подпись безпарольного перехода из урока GetCourse (Шаг 6.1).

Ссылка, по которой ученик приходит в платформу, обязана быть подписана: без этого
любой, кто получил чужой URL, вошёл бы под чужим письмом и получил бы чужую
авторизованную сессию. Держатся три правила:

1. Подпись покрывает **все** поля перехода, а не только `gc_uid` и урок. Иначе
   достаточно было бы вырезать из готовой ссылки `email=` и подставить своё —
   подпись бы этого не заметила, а аккаунт по новому письму платформа создала бы.
2. Срок жизни у ссылки короткий (`GC_SSO_MAX_AGE`): украденную или пересланную
   ссылку нельзя превратить в вечный ключ.
3. Секрет живёт в `.env` и наружу не отдаётся ни при каком раскладе — по ссылке
   восстанавливать секрет нельзя, только проверять подпись.
"""
import hashlib
import hmac
from datetime import datetime, timezone as dt_timezone

# Порядок полей зафиксирован: менять его — значит молча сломать все ссылки,
# которые методист уже вложил в уроки.
SIGNED_FIELDS = ('gc_uid', 'email', 'first_name', 'last_name', 'assignment_id', 'ts')


def normalize(values):
    """Поля перехода к единому виду: подпись считают по одним и тем же строкам."""
    out = {}
    for field in SIGNED_FIELDS:
        raw = values.get(field)
        out[field] = ('' if raw is None else str(raw)).strip()
    out['email'] = out['email'].lower()
    return out


def canonical_string(values):
    v = normalize(values)
    return '|'.join(v[field] for field in SIGNED_FIELDS)


def make_sign(secret, values):
    return hmac.new(secret.encode('utf-8'), canonical_string(values).encode('utf-8'),
                    hashlib.sha256).hexdigest()


def sign_is_valid(secret, values, sign):
    if not secret:
        return False
    provided = (sign or '').strip()
    if not provided:
        return False
    return hmac.compare_digest(make_sign(secret, values), provided.lower())


def parse_ts(ts):
    """Unix-время секундами; ничего не разбираем — None."""
    try:
        return int(float(str(ts).strip()))
    except (TypeError, ValueError):
        return None


def ts_is_fresh(ts, now=None, max_age=300):
    """Ссылка живёт `max_age` секунд. Будущее `ts` тоже отказ: так подпись
    не превращают в заготовку, которая «оживёт» позже."""
    moment = parse_ts(ts)
    if moment is None:
        return False
    now = now or datetime.now(dt_timezone.utc)
    delta = abs((now - datetime.fromtimestamp(moment, tz=dt_timezone.utc)).total_seconds())
    return delta <= max_age


def link_query(secret, base_url, values):
    """Собрать готовый переход: поле `sign` дописано по тем же полям, что проверят."""
    from urllib.parse import urlencode
    v = normalize(values)
    v['sign'] = make_sign(secret, v)
    return '%s?%s' % (base_url, urlencode(v))
