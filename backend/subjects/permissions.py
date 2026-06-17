from rest_framework.permissions import IsAdminUser


class IsTeacherOrAdmin(IsAdminUser):
    """Доступ только учителям и админам"""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role in ('teacher', 'admin')
        )
