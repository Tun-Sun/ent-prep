"""Правила доступа к пробным тестам.

Окно доступности предмета задаётся датами `available_from`/`available_until`
и закрывается автоматически. Тренер может открыть доступ конкретному ученику
вручную — записью `TrialAccess`. Оба пути проверяются одной функцией, чтобы
каталог, старт и сдача отвечали одинаково.
"""
from .models import TrialAccess


def manual_access_open(user, subject) -> bool:
    """Открыл ли тренер этот пробник лично этому ученику."""
    if getattr(user, 'role', '') != 'student' or subject is None:
        return False
    return TrialAccess.objects.filter(student=user, subject=subject).exists()


def can_take_subject(user, subject) -> bool:
    """Можно ли сейчас начать/продолжить тест по предмету."""
    if subject is None:
        return True
    if subject.is_available_now():
        return True
    return manual_access_open(user, subject)
