# Пробные варианты «Пробные от INTELLECT» (ЕНТ 01–03, NUET 01–03)

Шесть отдельных предметов-вариантов: `ent-01`, `ent-02`, `ent-03`, `nuet-01`,
`nuet-02`, `nuet-03`. Отдельный `Subject` на вариант — единственная надёжная
изоляция: старт теста набирает вопросы по `topic__subject_id`, поэтому в
вариант 01 физически не попадают ни вопросы варианта 02, ни старый банк.

Все шесть создаются скрытыми (`is_visible=False`): пустая карточка не должна
появляться у ученика раньше вопросов.

## Порядок запуска

```bash
cd /opt/entprep/backend

# 1. Создать/выровнять шесть вариантов (идемпотентно)
../venv/bin/python manage.py trial_variants --hidden

# 2. Залить формы: пары «слаг=ссылка», можно повторять
../venv/bin/python manage.py trial_import \
  --form ent-01=https://docs.google.com/forms/d/<ID>/edit \
  --form ent-02=... --form ent-03=... \
  --form nuet-01=... --form nuet-02=... --form nuet-03=...

# либо из файла: {"ent-01": "https://...", ...}
../venv/bin/python manage.py trial_import --from-file links.json

# 3. Проверить, что вопросы и ключи на месте
../venv/bin/python manage.py legacy_content --status

# 4. Скрыть старый банк, оставив только варианты
../venv/bin/python manage.py legacy_content --hide
```

`trial_import` сам проставляет `question_count` и `time_limit` по факту
импортированных вопросов (минута на вопрос, не меньше 10 минут и не больше
4 часов; жёсткий регламент — `--time-limit 14400`). Формы нужно расшарить на
сервисный аккаунт (`manage.py` печатает его email в ошибке) с правом
«Просмотр», иначе правильные ответы не подтянутся и вопросы уйдут в `draft`.

## Откат

`legacy_content --hide` перед изменением пишет снимок в
`backend/var/legacy_visibility_<дата>.json` и возвращает прежнее состояние
видимости одной командой:

```bash
../venv/bin/python manage.py legacy_content --restore            # последний снимок
../venv/bin/python manage.py legacy_content --restore --snapshot backend/var/legacy_visibility_2026-11-18_15-00-00.json
```

Ничего не удаляется: скрытие — это только `is_visible=False` у `Subject`.
Вопросы, темы, сессии и ответы остаются в БД, а раздел «Мои уроки», полная
симуляция ЕНТ и каталог перестают показывать скрытые предметы.

Команда `--hide` отказывается работать, если у какого-то из шести вариантов
ноль вопросов (`--allow-empty` снимает проверку) — чтобы не оставить учеников
с пустым каталогом.
