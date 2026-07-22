# ENT Prep — платформа подготовки к ЕНТ

> **Project brief.** Веб-платформа для подготовки учащихся к ЕНТ (Единое национальное тестирование, Казахстан). Студенты проходят тесты по предметам и видят аналитику прогресса; учителя управляют базой вопросов и следят за успеваемостью.

---

## 1. Что это и для кого

Платформа решает две задачи:

- **Для ученика** — тренировка в формате, близком к ЕНТ: выбор предмета → тест на N вопросов с таймером → мгновенный результат с разбором и объяснениями → история попыток и личная статистика.
- **Для учителя** — управление контентом (CRUD вопросов + импорт из Excel), просмотр прогресса учеников и общая аналитика по предметам и баллам.

Поддерживается **3 роли**: `student` (ученик), `teacher` (учитель), `admin` (администратор). Роль задаётся при регистрации и хранится в модели пользователя.

---

## 2. Технологический стек

| Слой | Технологии |
|------|-----------|
| Frontend | React 18, Vite 5, React Router v6, axios, KaTeX (формулы), recharts (графики) |
| Backend | Django 5, Django REST Framework, SimpleJWT, django-cors-headers, WhiteNoise |
| База данных | SQLite (dev) / PostgreSQL (продакшен через `DATABASE_URL`) |
| Контент | openpyxl (импорт/экспорт Excel), BeautifulSoup4 + lxml (парсинг внешних источников), Pillow (изображения) |
| Деплой | Render.com (Blueprint `render.yaml`), gunicorn, free tier |

Аутентификация — **только JWT** (access 60 мин, refresh 7 дней, ротация refresh-токенов).

---

## 3. Архитектура

```
ent-prep/
├── backend/                  # Django-проект (один процесс раздаёт и API, и собранный SPA)
│   ├── core/                 # settings, urls, WSGI/ASGI, SPA catch-all
│   ├── users/                # модель User, регистрация, профиль, ensure_admin
│   ├── subjects/             # Subject/Topic/Question/Answer, CRUD, импорт, парсеры
│   ├── tests/                # TestSession/AnswerRecord, прохождение тестов
│   ├── dashboard/            # аналитика для ученика и учителя
│   ├── data/entprep/         # JSON-дампы вопросов по 15 предметам
│   └── staticfiles/          # собранный фронтенд (index.html + assets)
├── frontend/                 # React SPA
│   └── src/
│       ├── api/              # axios-слой
│       ├── context/          # AuthContext
│       ├── components/       # Layout, ProtectedRoute, Timer, FormattedText
│       └── pages/{auth,student,teacher}/
├── render.yaml               # Render Blueprint (БД + web-сервис + predeploy)
└── build.sh                  # сборка фронтенда и копирование в staticfiles
```

**Принцип развёртывания:** один Django-сервис раздаёт и REST API (`/api/...`), и собранный React SPA (в продакшене `spa_catch_all` отдаёт `staticfiles/index.html` для всех не-API маршрутов).

---

## 4. Доменная модель

```
Subject 1—N Topic 1—N Question 1—N Answer
   │                    │
   └─ TestSession ──────┴─ AnswerRecord ─ User
```

- **Subject** — предмет (алгебра, физика, история и т.д.), slug + иконка-эмодзи.
- **Topic** — тема внутри предмета.
- **Question** — вопрос: текст, тема, сложность (`easy/medium/hard`), объяснение, опц. изображение.
- **Answer** — вариант ответа с флагом `is_correct`, опц. изображение. Модель нативно поддерживает **только single-choice** (один правильный вариант).
- **TestSession** — попытка теста: студент, предмет, время начала/окончания, `total_questions`, `correct_answers`, `score_percent`.
- **AnswerRecord** — ответ студента в рамках сессии (один на вопрос, `unique_together`).
- **User** — расширённый `AbstractUser` с `role`, `full_name`, `school`.

---

## 5. Ключевые сценарии использования

### Ученик
1. Регистрация/вход (выбор роли при регистрации).
2. **Дашборд** — статистические карточки, график динамики, карточки предметов с прогрессом.
3. **Каталог предметов** — счётчики тем/вопросов, старт теста.
4. **Прохождение теста** — 10 вопросов, общий таймер 10 минут, мгновенная отправка каждого ответа, навигатор-сетка, поддержка картинок и формул.
5. **Результат** — итоговый балл + полный разбор по каждому вопросу с объяснениями.
6. **История** — список завершённых попыток.

### Учитель
1. **Дашборд** — общая статистика, графики по предметам и распределению, топ-ученики.
2. **Управление вопросами** — CRUD с фильтрами по предмету/теме/сложности, динамические варианты ответов.
3. **Импорт из Excel** — скачивание шаблона `.xlsx` → загрузка заполненного файла с разбором ошибок.
4. **Ученики** — список и прогресс каждого по предметам.
5. **Аналитика** — распределение баллов по диапазонам, дневная динамика.

---

## 6. Источники данных

Вопросы поступают в базу тремя путями:

1. **Парсер `parse_entprep`** — загрузка и нормализация вопросов с внешнего ресурса entprep.org (через Supabase/PostgREST API). Обрабатывает типы `single`, `multiple` (сжимается до single), `matching` (пары уходят в explanation). Большой словарь маппинга предметов и тем.
2. **Bulk-импорт `import_json`** — быстрая загрузка из локальных JSON-дампов (`backend/data/entprep/*.json`) через `bulk_create`, 15 предметов.
3. **Ручной ввод / Excel-импорт** — через UI учителя (CRUD + `import/excel/`).

Утилита `download_entprep` обновляет локальные JSON-дампы. Команда `seed_data` генерирует моковые данные для разработки.

---

## 7. API (краткая карта)

| Группа | Эндпоинты |
|--------|----------|
| Auth | `POST api/auth/register/`, `GET api/auth/profile/`, `POST api/auth/login/`, `POST api/auth/refresh/` |
| Subjects | `api/subjects/`, `api/topics/`, `api/questions/` (CRUD + фильтры), `api/subjects/{id}/topics/` |
| Импорт | `GET api/import/template/` (xlsx), `POST api/import/excel/` |
| Тесты | `POST api/tests/start/`, `POST api/tests/{id}/answer/`, `POST api/tests/{id}/finish/`, `GET api/tests/{id}/result/`, `GET api/tests/history/` |
| Дашборд | `GET api/dashboard/student/`, `GET api/dashboard/teacher/`, `GET api/dashboard/teacher/students/`, `GET api/dashboard/teacher/analytics/` |

Пермишены: чтение контента — `IsAuthenticated`; запись (CRUD, импорт) — `IsTeacherOrAdmin`; teacher-дашборд — роль `teacher` (проверяется вручную).

---

## 8. Локальный запуск

**Backend:**
```bash
cd backend
python -m venv venv && venv\Scripts\activate      # Windows
pip install -r requirements.txt
cp .env.example .env                               # при необходимости отредактировать
python manage.py migrate
python manage.py import_json --skip-existing        # загрузить вопросы из data/entprep
python manage.py ensure_admin                       # создать суперпользователя
python manage.py runserver                          # http://localhost:8000
```

**Frontend (dev-сервер с прокси на :8000):**
```bash
cd frontend
npm install
npm run dev                                         # http://localhost:5173
```

Для демо-данных: `python manage.py seed_data`.

---

## 9. Деплой (Render.com)

Развёртывание одной кнопкой через `render.yaml`:

1. Создаётся PostgreSQL `ent-prep-db` (free).
2. Веб-сервис `ent-prep` собирается по `build.sh` (установка Python-зависимостей, сборка React, копирование `dist/` → `backend/staticfiles/`).
3. **Predeploy** (в runtime-окружении, где доступен `DATABASE_URL`): `migrate` → `import_json --skip-existing` → `ensure_admin`.
4. Старт: `gunicorn core.wsgi:application`.

Переменные окружения: `PYTHON_VERSION`, `NODE_VERSION`, `SECRET_KEY` (генерируется), `DEBUG=False`, `DATABASE_URL` (из БД), `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`.

---

## 10. Известные ограничения и технический долг

Эти пункты — отправная точка для плана развития:

- **Только single-choice.** Модель `Question`/`Answer` не поддерживает множественный выбор и сопоставление — при импорте они сжимаются, теряя исходную семантику.
- **Жёсткие параметры теста.** `num_questions=10` и таймер 600 с захардкожены во фронтенде; режимов «тренировка/экзамен/марафон» нет.
- **Управление ролями.** Сменить роль пользователя можно только через Django-admin; эндпоинта управления пользователями и списка студентов для админа нет.
- **Пермишены в dashboard.** Teacher-эндпоинты проверяют роль вручную и строго `== 'teacher'` — `admin` не допускается к учительской аналитике.
- **Безопасность по умолчанию.** В `settings.py` `DEBUG=True` и `ALLOWED_HOSTS='*'`, если env не задан; `ANON_KEY` внешнего API захардкожен в парсере.
- **Нет тестов уровня продукта.** `tests.py` в приложениях пустые/макетные; end-to-end покрытия нет.
- **Один источник истины по предметам/темам.** Маппинги захардкожены в `parse_entprep` (`SUBJECT_MAP`, `TOPIC_NAMES`) — добавление предмета требует правки кода.
- **Без локализации.** Интерфейс только на русском; `LANG="ru"` зашит в `index.html`.
- **Фронтенд без TypeScript и UI-кита** — собственный CSS, ручная типизация.

---

## 11. Статус проекта

**Текущий этап:** MVP готов и разворачивается на Render. Реализован полный цикл «регистрация → тестирование → аналитика» для учеников и базовое управление контентом для учителей. База наполняется парсером entprep.org (15 предметов) и/или Excel-импортом.

**Что близко к завершению:** инфраструктура деплоя (predeploy с миграциями, импортом данных и созданием админа — идемпотентна).

**Что ожидает решения:** расширение типов вопросов, гибкие режимы тестирования, полноценное администрирование пользователей, тестовое покрытие и продакшен-настройки безопасности.
