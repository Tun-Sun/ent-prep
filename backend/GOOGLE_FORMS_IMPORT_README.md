# Google Forms Importer для ENT Prep

## Огляд

Конвейер імпорту авторських тестів з Google Forms складається з трьох частин:

1. **Apps Script** (`ExportFormToJSON.gs`) — запускається в Google Form учителем, експортує структуру форми в JSON
2. **JSON Parser** (`subjects/google_forms/parser.py`) — валідує JSON структуру
3. **Importer** (`subjects/google_forms/importer.py`) — записує дані в БД з дедупліцірюванням

## Процес використання

### Крок 1: Підготовка Google Form (для учителя)

1. Відкрийте свою Google Form (або створіть нову)
2. Перевірте, що форма в режимі **Quiz** (Settings → "Make this a quiz")
   - Це необхідно для правильного експорту правильних відповідей
3. Перейдіть до: **Расширения (Extensions) → Apps Script**
4. Вставте вміст з `subjects/google_forms/apps_script/ExportFormToJSON.gs`
5. Нажміть кнопку **Run** → виберіть функцію `exportFormToJson`
6. При першому запуску Google попросить дозволи — дайте їх
7. У Google Drive з'явиться папка `ENT-Prep-Exports` з JSON-файлом формату:
   ```
   <назва-форми>_<дата>.json
   ```

### Крок 2: Імпорт JSON в платформу (для адміністратора)

```bash
cd ent-prep/backend

# Сухий прогін — без запису в БД, тільки валідація
python manage.py import_from_google_forms form.json --dry-run

# Реальний імпорт
python manage.py import_from_google_forms form.json

# Імпорт всіх JSON-файлів з папки
python manage.py import_from_google_forms data/google_forms/

# Імпорт з позначенням як verified (за замовчанням — draft для огляду)
python manage.py import_from_google_forms form.json --verify

# Змінити складність по замовчанню (за замовчанням — medium)
python manage.py import_from_google_forms form.json --difficulty hard
```

## Структура JSON-експорту

```json
{
  "schema_version": 1,
  "source": {
    "form_id": "1...",
    "form_title": "Physics: Newton's Laws",
    "form_url": "https://docs.google.com/forms/d/...",
    "is_quiz": true
  },
  "subject_slug": "physics",
  "subject_name": "Physics",
  "topic_name": "Newton's Laws of Motion",
  "language": "en",
  "year": 2026,
  "questions": [
    {
      "external_id": "1.../q_001",
      "title": "What is Newton's First Law?",
      "type": "multiple_choice",
      "help_text": "Інтернет",
      "image_ref": null,
      "order_index": 0,
      "answers": [
        {
          "text": "An object at rest stays at rest...",
          "is_correct": true,
          "image_ref": null
        },
        {
          "text": "Force equals mass times...",
          "is_correct": false,
          "image_ref": null
        }
      ]
    }
  ]
}
```

## Гарантії та дедупліцірування

- **external_id** = форма ID + ID питання в формі
- Вопросы з `source_type='authorial'` унікальні по `external_id`
- Повторний імпорт того ж файлу безпечний — дублікати пропускаються

## Статуси верифікації

Після імпорту вопрос отримує статус:

- **verified** — якщо має хоча б один правильний ответ (форма була в режимі Quiz)
- **draft** — якщо не має правильного ответу (учитель має вручну перевірити)

## Картинки (Крок 10 — майбутньо)

- JSON експортує `image_ref` (Drive file ID) для картинок у питаннях/ответах
- Завантаження картинок (через Drive API) реалізується в `images.py` як окремий крок
- На поточний момент картинки пропускаються, але структура готова до розширення

## Результат імпорту

Команда повертає звіт:

```
  ⬆ form1.json... создано 5, дубли 2, без правильного 1
  ⬆ form2.json... создано 10, дубли 0, без правильного 0

============================================================
  ИТОГО: создано 15, дубликатов пропущено 2, без правильного ответа 1
```

- **создано** — нові питання, додані в БД
- **дубли** — питання, які вже були в БД (пропущені)
- **без правильного** — питання без правильного ответу (помічені як draft)

## Тестування

```bash
# Виконайте тест з тестовим JSON
python manage.py import_from_google_forms test_import.json --dry-run
python manage.py import_from_google_forms test_import.json
```

Очікуваний результат: 2 питання з дедупліцірюванням по external_id.
