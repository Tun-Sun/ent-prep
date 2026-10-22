from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = [
        ('student', 'Ученик'),
        ('teacher', 'Учитель'),
        ('admin', 'Администратор'),
    ]

    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='student')
    full_name = models.CharField(max_length=150, blank=True)
    school = models.CharField(max_length=200, blank=True)
    # Код ученика в GetCourse: по нему вход из урока находит своего человека, не
    # глядя на письмо (почту в ГК правят чаще, чем теряют аккаунт). Пустое значение
    # — норма для всех, кто в ГК не учится, поэтому уникальность только для непустых.
    gc_uid = models.CharField(max_length=64, blank=True, default='', verbose_name='Код ученика в GetCourse')
    # Вход из учебного чата: Telegram даёт свой номер, и он надёжнее почты, которую
    # человек может написать чужую. Пусто — значит человек ещё не входил по-телеграму,
    # поэтому уникальность только для непустых (иначе второй такой же ученик не влез бы).
    telegram_id = models.BigIntegerField(null=True, blank=True, unique=True,
                                         verbose_name='Идентификатор в Telegram')
    telegram_username = models.CharField(max_length=64, blank=True, default='',
                                         verbose_name='Ник в Telegram')
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True, verbose_name='Аватар')
    dashboard_subjects = models.ManyToManyField('subjects.Subject', blank=True, verbose_name='Предметы на дашборде')
    profile_subjects = models.ManyToManyField('subjects.Subject', blank=True, related_name='students',
                                               verbose_name='Профильные предметы ученика')

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'
        constraints = [
            models.UniqueConstraint(fields=['gc_uid'], condition=~models.Q(gc_uid=''),
                                    name='uniq_gc_uid_when_filled'),
        ]

    def __str__(self):
        return f'{self.username} ({self.get_role_display()})'


class StudyGroup(models.Model):
    name = models.CharField(max_length=200, verbose_name='Название')
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name='teaching_groups', verbose_name='Учитель')
    students = models.ManyToManyField(User, blank=True, related_name='student_groups', verbose_name='Ученики')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Группа'
        verbose_name_plural = 'Группы'

    def __str__(self):
        return self.name


class SystemSetting(models.Model):
    key = models.CharField(max_length=100, unique=True, verbose_name='Ключ')
    value = models.TextField(blank=True, verbose_name='Значение')
    description = models.CharField(max_length=255, blank=True, verbose_name='Описание')

    class Meta:
        verbose_name = 'Системная настройка'
        verbose_name_plural = 'Системные настройки'

    def __str__(self):
        return self.key
