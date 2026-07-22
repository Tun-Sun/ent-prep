"""
Конвейер импорта авторских тестов из Google Forms.

Подмодули:
- ``apps_script/``  — Google Apps Script для учителя (экспорт формы в JSON).
- ``dto.py``        — структуры данных импортируемой формы.
- ``parser.py``     — разбор JSON, валидация.
- ``importer.py``   — запись в БД (Subject/Topic/Question/Answer).
- ``images.py``     — скачивание картинок из Google Drive (Drive API).
"""
