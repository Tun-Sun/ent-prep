"""Логика геймификации: достижения, серии дней, разрешение дуэлей."""

from datetime import timedelta

from django.db.models import Avg, Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from .models import UserAchievement

# ── Достижения ──────────────────────────────────────────────────────────────
# Условия проверяются в check_achievements(). Добавление нового достижения —
# одна строка здесь + ветка в _earned_codes().

ACHIEVEMENTS = [
    {'code': 'first_test',    'icon': '🎯', 'title': 'Первый шаг',      'description': 'Пройдите первый тест'},
    {'code': 'tests_10',      'icon': '📚', 'title': 'Разогрев',        'description': 'Пройдите 10 тестов'},
    {'code': 'tests_50',      'icon': '🎓', 'title': 'Марафонец',       'description': 'Пройдите 50 тестов'},
    {'code': 'perfect_run',   'icon': '🏅', 'title': 'Идеально!',       'description': '100% за тест (от 5 вопросов)'},
    {'code': 'streak_7',      'icon': '🔥', 'title': 'Неделя огня',     'description': '7 дней подряд с тестами'},
    {'code': 'ent_warrior',   'icon': '⚔️', 'title': 'Воин ЕНТ',        'description': 'Полная симуляция ЕНТ пройдена'},
    {'code': 'rush_master',   'icon': '⚡', 'title': 'Молния',          'description': '25+ верных из 30 в Question Rush'},
    {'code': 'duel_winner',   'icon': '🏆', 'title': 'Победитель дуэли', 'description': 'Выиграйте дуэль у соперника'},
    {'code': 'subject_master', 'icon': '👑', 'title': 'Мастер предмета', 'description': 'Средний балл 90%+ по предмету (5+ тестов)'},
]

ACHIEVEMENTS_BY_CODE = {a['code']: a for a in ACHIEVEMENTS}

DUEL_EXPIRE_DAYS = 7


def get_streak(user):
    """Текущая и лучшая серии дней с завершёнными тестами."""
    from tests.models import TestSession

    dates = list(
        TestSession.objects
        .filter(student=user, is_completed=True, completed_at__isnull=False)
        .annotate(d=TruncDate('completed_at'))
        .values_list('d', flat=True)
        .distinct()
        .order_by('-d')
    )
    if not dates:
        return {'current': 0, 'best': 0}

    # Текущая серия: отсчитываем назад от сегодня/вчера
    current = 0
    today = timezone.localdate()
    expected = today
    if dates[0] < today - timedelta(days=1):
        current = 0
    else:
        expected = dates[0]
        for d in dates:
            if d == expected:
                current += 1
                expected -= timedelta(days=1)
            else:
                break

    # Лучшая серия за всё время
    best = 0
    run = 0
    prev = None
    for d in sorted(dates):
        if prev is not None and d == prev + timedelta(days=1):
            run += 1
        else:
            run = 1
        if run > best:
            best = run
        prev = d

    return {'current': current, 'best': best}


def _earned_codes(user):
    """Список кодов достижений, заслуженных пользователем сейчас."""
    from tests.models import TestSession

    completed = TestSession.objects.filter(student=user, is_completed=True)

    codes = []
    total = completed.count()
    if total >= 1:
        codes.append('first_test')
    if total >= 10:
        codes.append('tests_10')
    if total >= 50:
        codes.append('tests_50')
    if completed.filter(total_questions__gte=5, score_percent=100).exists():
        codes.append('perfect_run')
    if completed.filter(is_ent=True).exists():
        codes.append('ent_warrior')
    if completed.filter(mode='rush', correct_answers__gte=25).exists():
        codes.append('rush_master')
    if user.duels_won.exists():
        codes.append('duel_winner')
    if get_streak(user)['best'] >= 7:
        codes.append('streak_7')

    # Мастер предмета: avg ≥ 90% при 5+ тестах
    subj = (
        completed.values('subject')
        .annotate(c=Count('id'), avg=Avg('score_percent'))
        .filter(c__gte=5, avg__gte=90)
    )
    if subj.exists():
        codes.append('subject_master')

    return codes


def check_achievements(user):
    """Начисляет заслуженные достижения. Возвращает список новых кодов."""
    newly = []
    for code in _earned_codes(user):
        _, created = UserAchievement.objects.get_or_create(user=user, code=code)
        if created:
            newly.append(code)
    return newly


def achievements_payload(user):
    """Данные для эндпоинта: все достижения + серия дней."""
    unlocked = {ua.code: ua.unlocked_at for ua in user.achievements.all()}
    items = []
    for a in ACHIEVEMENTS:
        at = unlocked.get(a['code'])
        items.append({
            'code': a['code'],
            'icon': a['icon'],
            'title': a['title'],
            'description': a['description'],
            'unlocked': at is not None,
            'unlocked_at': at.strftime('%d.%m.%Y') if at else None,
        })
    items.sort(key=lambda x: (not x['unlocked'],))
    streak = get_streak(user)
    return {
        'achievements': items,
        'unlocked_count': sum(1 for i in items if i['unlocked']),
        'total_count': len(items),
        'streak': streak,
    }


def resolve_duel(duel):
    """Определяет победителя, если обе сессии дуэли завершены."""
    from .models import Duel

    if duel.status != 'active':
        return False
    cs, os_ = duel.challenger_session, duel.opponent_session
    if not cs or not os_ or not cs.is_completed or not os_.is_completed:
        return False

    if cs.earned_points > os_.earned_points:
        duel.winner = duel.challenger
    elif os_.earned_points > cs.earned_points:
        duel.winner = duel.opponent
    else:
        duel.is_draw = True
    duel.status = 'completed'
    duel.completed_at = timezone.now()
    duel.save()

    if duel.winner:
        check_achievements(duel.winner)
    return True


def resolve_user_duels(user):
    """Лениво завершает активные дуэли пользователя (вызов после финиша теста)."""
    from .models import Duel

    duels = Duel.objects.filter(status='active') & (
        Duel.objects.filter(challenger=user) | Duel.objects.filter(opponent=user)
    )
    for duel in duels:
        resolve_duel(duel)


def expire_stale_duels():
    """Помечает истёкшие ожидающие дуэли (старше DUEL_EXPIRE_DAYS дней)."""
    from .models import Duel

    deadline = timezone.now() - timedelta(days=DUEL_EXPIRE_DAYS)
    Duel.objects.filter(status='pending', created_at__lt=deadline).update(status='expired')
