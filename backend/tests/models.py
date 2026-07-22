import json

from django.db import models
from django.conf import settings
from django.utils import timezone
from subjects.models import Question


class TestSession(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='test_sessions')
    subject = models.ForeignKey('subjects.Subject', on_delete=models.CASCADE, related_name='test_sessions', null=True, blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    total_questions = models.IntegerField(default=0)
    correct_answers = models.IntegerField(default=0)
    score_percent = models.FloatField(default=0)
    is_completed = models.BooleanField(default=False)
    time_limit = models.IntegerField(default=14400, verbose_name='Лимит времени (сек)')
    total_points = models.FloatField(default=0, verbose_name='Всего баллов')
    earned_points = models.FloatField(default=0, verbose_name='Набрано баллов')
    is_ent = models.BooleanField(default=False, verbose_name='ЕНТ тест')
    ent_data = models.JSONField(default=dict, blank=True, verbose_name='Данные ЕНТ (секции, предметы)')

    class Meta:
        verbose_name = 'Тестовая сессия'
        verbose_name_plural = 'Тестовые сессии'
        ordering = ['-started_at']

    def __str__(self):
        status_str = 'Завершён' if self.is_completed else 'В процессе'
        if self.is_ent:
            return f'{self.student.username} — ЕНТ ({status_str})'
        subj = self.subject.name if self.subject else '—'
        return f'{self.student.username} — {subj} ({status_str})'

    def calculate_score(self):
        if self.total_questions > 0:
            self.score_percent = round((self.correct_answers / self.total_questions) * 100, 1)
        self.save()


class TestSectionResult(models.Model):
    session = models.ForeignKey(TestSession, on_delete=models.CASCADE, related_name='section_results')
    section = models.CharField(max_length=12, choices=Question.SECTION_CHOICES)
    subject = models.ForeignKey('subjects.Subject', on_delete=models.CASCADE, null=True, blank=True)
    total_questions = models.IntegerField(default=0)
    answered = models.IntegerField(default=0)
    correct_answers = models.IntegerField(default=0)
    points_earned = models.FloatField(default=0)
    points_max = models.FloatField(default=0)

    class Meta:
        verbose_name = 'Результат секции'
        verbose_name_plural = 'Результаты секций'
        unique_together = ['session', 'section']

    def __str__(self):
        return f'{self.get_section_display()}: {self.points_earned}/{self.points_max}'


class AnswerRecord(models.Model):
    session = models.ForeignKey(TestSession, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_answer = models.ForeignKey('subjects.Answer', on_delete=models.CASCADE, null=True, blank=True)
    selected_answers = models.JSONField(default=list, blank=True, verbose_name='Выбранные ответы (ID)')
    matching_pairs = models.JSONField(default=dict, blank=True, verbose_name='Пары соответствия')
    is_correct = models.BooleanField(default=False)
    points_earned = models.FloatField(default=0, verbose_name='Получено баллов')
    points_max = models.FloatField(default=0, verbose_name='Макс. баллов')

    class Meta:
        verbose_name = 'Запись ответа'
        verbose_name_plural = 'Записи ответов'
        unique_together = ['session', 'question']

    def __str__(self):
        return f'{self.question.text[:40]} → {"✓" if self.is_correct else "✗"}'
