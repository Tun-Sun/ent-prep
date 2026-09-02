from django.conf import settings
from django.db import models


class UserAchievement(models.Model):
    """Достижение, разблокированное пользователем.

    Определения достижений живут в gamification.services.ACHIEVEMENTS,
    в БД хранятся только факты разблокировки.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='achievements', verbose_name='Пользователь',
    )
    code = models.CharField(max_length=40, db_index=True, verbose_name='Код достижения')
    unlocked_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата разблокировки')

    class Meta:
        verbose_name = 'Достижение пользователя'
        verbose_name_plural = 'Достижения пользователей'
        constraints = [
            models.UniqueConstraint(fields=['user', 'code'], name='unique_user_achievement'),
        ]

    def __str__(self):
        return f'{self.user} — {self.code}'


class Duel(models.Model):
    """Асинхронная дуэль между двумя учениками.

    Набор вопросов фиксируется при создании (question_ids),
    каждый игрок проходит его в своём темпе — сессии создаются
    в момент нажатия «Играть», чтобы таймер не тёк заранее.
    """
    STATUS_CHOICES = [
        ('pending', 'Ожидает соперника'),
        ('active', 'В процессе'),
        ('completed', 'Завершена'),
        ('declined', 'Отклонена'),
        ('expired', 'Истекла'),
    ]

    challenger = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='duels_challenged', verbose_name='Инициатор',
    )
    opponent = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='duels_received', verbose_name='Соперник',
        null=True, blank=True,
    )
    subject = models.ForeignKey(
        'subjects.Subject', on_delete=models.SET_NULL,
        related_name='duels', verbose_name='Предмет', null=True, blank=True,
    )
    question_ids = models.JSONField(default=list, verbose_name='ID вопросов дуэли')
    num_questions = models.PositiveIntegerField(default=10, verbose_name='Кол-во вопросов')
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default='pending', verbose_name='Статус',
    )
    challenger_session = models.ForeignKey(
        'tests.TestSession', on_delete=models.SET_NULL,
        related_name='duel_as_challenger', null=True, blank=True,
    )
    opponent_session = models.ForeignKey(
        'tests.TestSession', on_delete=models.SET_NULL,
        related_name='duel_as_opponent', null=True, blank=True,
    )
    winner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='duels_won', verbose_name='Победитель', null=True, blank=True,
    )
    is_draw = models.BooleanField(default=False, verbose_name='Ничья')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создана')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Завершена')

    class Meta:
        verbose_name = 'Дуэль'
        verbose_name_plural = 'Дуэли'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.challenger} vs {self.opponent or "?"} ({self.get_status_display()})'
