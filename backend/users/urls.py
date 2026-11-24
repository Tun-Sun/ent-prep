from django.urls import path
from .views import (
    RegisterView, ProfileView, UpdateProfileSubjectsView,
    ClearTestHistoryView, DeleteOwnAccountView,
    UpdateStudentSubjectsView, UpdateStudentTracksView, DeactivateStudentView,
    ReactivateStudentView, UpdateStudentNameView,
    ChangePasswordView, ResetStudentPasswordView, SetPasswordView, ResetStudentPasswordView,
    StudyGroupListCreateView, StudyGroupDetailView,
    StudyGroupAddStudentsView, CreateStudentView, StudentListView,
    AdminUserListView, AdminUserDetailView, AdminUserDeleteView,
    AdminSettingListView, AdminSettingDetailView, AdminInviteCodeView,
    TelegramAuthView, TelegramConfigView, PublicGroupListView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/change-password/', ChangePasswordView.as_view(), name='change-password'),
    path('login/set-password/', SetPasswordView.as_view(), name='set-password'),
    # Вход из учебного чата: виджет Telegram отдаёт подписанные поля, сервер сверяет
    # подпись и выдаёт ключи. Конфиг — чтобы фронт не пересобирать ради ника бота.
    path('telegram/', TelegramAuthView.as_view(), name='telegram-auth'),
    path('telegram/config/', TelegramConfigView.as_view(), name='telegram-config'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('profile/subjects/', UpdateProfileSubjectsView.as_view(), name='profile-subjects'),
    path('profile/history/', ClearTestHistoryView.as_view(), name='profile-history'),
    path('profile/account/', DeleteOwnAccountView.as_view(), name='profile-account'),
    # Groups
    path('groups/public/', PublicGroupListView.as_view(), name='public-groups'),
    path('groups/', StudyGroupListCreateView.as_view(), name='study-groups'),
    path('groups/<int:pk>/', StudyGroupDetailView.as_view(), name='study-group-detail'),
    path('groups/<int:pk>/students/', StudyGroupAddStudentsView.as_view(), name='study-group-students'),
    path('students/create/', CreateStudentView.as_view(), name='student-create'),
    path('students/search/', StudentListView.as_view(), name='student-search'),
    path('students/<int:student_id>/subjects/', UpdateStudentSubjectsView.as_view(), name='student-subjects'),
    path('students/<int:student_id>/tracks/', UpdateStudentTracksView.as_view(), name='student-tracks'),
    path('students/<int:student_id>/name/', UpdateStudentNameView.as_view(), name='student-name'),
    path('students/<int:student_id>/', DeactivateStudentView.as_view(), name='student-deactivate'),
    path('students/<int:student_id>/reactivate/', ReactivateStudentView.as_view(),
         name='student-reactivate'),
    path('students/<int:student_id>/reset-password/', ResetStudentPasswordView.as_view(), name='student-reset-password'),
    # Admin panel
    path('admin/users/', AdminUserListView.as_view(), name='admin-users'),
    path('admin/users/<int:pk>/', AdminUserDetailView.as_view(), name='admin-user-detail'),
    path('admin/users/<int:pk>/delete/', AdminUserDeleteView.as_view(), name='admin-user-delete'),
    path('admin/settings/', AdminSettingListView.as_view(), name='admin-settings'),
    path('admin/invite-code/', AdminInviteCodeView.as_view(), name='admin-invite-code'),    path('admin/settings/<int:pk>/', AdminSettingDetailView.as_view(), name='admin-setting-detail'),
]
