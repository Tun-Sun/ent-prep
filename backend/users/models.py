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
    dashboard_subjects = models.ManyToManyField('subjects.Subject', blank=True, verbose_name='Предметы на дашборде')
    profile_subjects = models.ManyToManyField('subjects.Subject', blank=True, related_name='students',
                                               verbose_name='Профильные предметы ученика')

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

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
