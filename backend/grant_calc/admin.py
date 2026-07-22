from django.contrib import admin
from .models import University


@admin.register(University)
class UniversityAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'uni_type', 'min_score', 'sort_order')
    list_filter = ('uni_type', 'city')
    search_fields = ('name', 'city', 'specializations')
