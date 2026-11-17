"""Правила треков: школа / ЕНТ / NUET.

Трек — не украшение профиля, а граница контента: предмет ЕНТ не должен
попадать школьнику ни в каталог, ни в запуск теста, ни в профиль, а NUET-ученик
не должен видеть ЕНТ-виджеты. Правила собраны здесь, чтобы сериализаторы, вьюхи
и тесты не расходились в том, что считать конфликтом.
"""
from django.db.models import Q

from .choices import TrackChoices

# 11-классник выбирает между двумя выпускными треками; школа сюда не входит.
GRADUATION_TRACKS = (TrackChoices.ENT, TrackChoices.NUET)
VALID_TRACKS = {choice.value for choice in TrackChoices}


def is_valid_track(value):
    return value in VALID_TRACKS


def normalize_track(grade, requested=None):
    """Каким обязан быть трек ученика при таком классе.

    5–10 — только школа: до выпускного класса ЕНТ-тренажёр не их программа.
    11 — трек выбирает сам ученик (ЕНТ или NUET); без выбора профиль не заполнен.
    Класс не указан — трек неизвестен.
    """
    if grade is None:
        return None
    if 5 <= grade <= 10:
        return TrackChoices.SCHOOL
    if grade == 11:
        return requested if requested in GRADUATION_TRACKS else None
    return None


def student_track(user):
    """Трек ученика или None. У тренера и админа трека нет."""
    if getattr(user, 'role', None) != 'student':
        return None
    return getattr(user, 'track', None) or None


def subject_track(subject):
    """Трек предмета; пустая строка в базе значит «общий»."""
    return getattr(subject, 'track', '') or None


def tracks_conflict(student_value, subject_value):
    """Конфликт только когда оба трека известны и различаются.

    Пустой трек ученика — «ещё не выбрал»: блокировать уроки и каталог раньше,
    чем человек заполнил карточку, значит наказать его за незаполненный профиль.
    """
    return bool(student_value and subject_value and student_value != subject_value)


def filter_subjects_by_track(queryset, track):
    """Предметы, доступные треку: свои плюс общие (`track=''`)."""
    if not track:
        return queryset
    return queryset.filter(Q(track='') | Q(track=track))


def can_use_subject(user, subject):
    """Может ли ученик работать с предметом. Тренеру и админу — всегда да."""
    if getattr(user, 'role', None) != 'student':
        return True
    return not tracks_conflict(student_track(user), subject_track(subject))


def requires_track(user):
    """11-классник без трека: профиль не заполнен, новые тесты не стартуют."""
    return (getattr(user, 'role', None) == 'student'
            and getattr(user, 'grade', None) == 11
            and not getattr(user, 'track', None))
