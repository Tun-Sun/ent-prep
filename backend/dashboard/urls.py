from django.urls import path
from .views import (
    StudentDashboardView, TeacherDashboardView,
    TeacherStudentsView, TeacherAnalyticsView,
    LeaderboardView, DashboardSubjectsView,
)

urlpatterns = [
    path('student/', StudentDashboardView.as_view(), name='student-dashboard'),
    path('teacher/', TeacherDashboardView.as_view(), name='teacher-dashboard'),
    path('teacher/students/', TeacherStudentsView.as_view(), name='teacher-students'),
    path('teacher/analytics/', TeacherAnalyticsView.as_view(), name='teacher-analytics'),
    path('leaderboard/', LeaderboardView.as_view(), name='leaderboard'),
    path('teacher/dashboard-subjects/', DashboardSubjectsView.as_view(), name='dashboard-subjects'),
]
