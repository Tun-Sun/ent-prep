from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Пользователь в админке: роль, класс и трек видны в списке.

    Без трека в списке владелец платформы не может ответить на вопрос «кто из
    11-классников уже выбрал NUET», а это ровно то, что решает, какой контент
    ученику показывать.
    """
    list_display = ('username', 'full_name', 'role', 'grade', 'track', 'school',
                    'is_active', 'is_staff')
    list_filter = BaseUserAdmin.list_filter + ('role', 'grade', 'track')
    search_fields = ('username', 'first_name', 'last_name', 'email', 'full_name', 'school')
    ordering = ('full_name', 'username')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Учёба', {
            'fields': ('role', 'grade', 'track', 'full_name', 'school', 'gc_uid',
                       'telegram_id', 'telegram_username', 'avatar',
                       'dashboard_subjects', 'profile_subjects'),
        }),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Учёба', {'fields': ('role', 'grade', 'track', 'full_name', 'school')}),
    )
    filter_horizontal = ('groups', 'user_permissions', 'dashboard_subjects', 'profile_subjects')
