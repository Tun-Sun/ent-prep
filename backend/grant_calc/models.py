from django.db import models


class University(models.Model):
    TYPE_CHOICES = [
        ('national', 'Национальный'),
        ('medical', 'Медицинский'),
        ('pedagogical', 'Педагогический'),
        ('technical', 'Технический'),
        ('it', 'IT'),
        ('agro', 'Аграрный'),
        ('other', 'Другой'),
    ]

    name = models.CharField(max_length=200, verbose_name='Название')
    city = models.CharField(max_length=100, verbose_name='Город')
    uni_type = models.CharField(max_length=20, choices=TYPE_CHOICES, verbose_name='Тип')
    icon = models.CharField(max_length=10, default='🏛️', verbose_name='Иконка')
    min_score = models.IntegerField(verbose_name='Проходной балл')
    specializations = models.CharField(max_length=500, verbose_name='Специальности')
    info = models.TextField(blank=True, verbose_name='Доп. информация')
    sort_order = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'Вуз'
        verbose_name_plural = 'Вузы'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return f'{self.name} ({self.city}) — {self.min_score}'
