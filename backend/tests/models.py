from django.db import models
from django.conf import settings


class TestSession(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='test_sessions')
    subject = models.ForeignKey('subjects.Subject', on_delete=models.CASCADE, related_name='test_sessions')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    total_questions = models.IntegerField(default=0)
    correct_answers = models.IntegerField(default=0)
    score_percent = models.FloatField(default=0)
    is_completed = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Тестовая сессия'
        verbose_name_plural = 'Тестовые сессии'
        ordering = ['-started_at']

    def __str__(self):
        status = 'Завершён' if self.is_completed else 'В процессе'
        return f'{self.student.username} — {self.subject.name} ({status})'

    def calculate_score(self):
        if self.total_questions > 0:
            self.score_percent = round((self.correct_answers / self.total_questions) * 100, 1)
        self.save()


class AnswerRecord(models.Model):
    session = models.ForeignKey(TestSession, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey('subjects.Question', on_delete=models.CASCADE)
    selected_answer = models.ForeignKey('subjects.Answer', on_delete=models.CASCADE, null=True)
    is_correct = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Запись ответа'
        verbose_name_plural = 'Записи ответов'
        unique_together = ['session', 'question']

    def __str__(self):
        return f'{self.question.text[:40]} → {"✓" if self.is_correct else "✗"}'
