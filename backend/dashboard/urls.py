from django.urls import path
from .views import (
    StudentDashboardView, TeacherDashboardView,
    TeacherStudentsView, TeacherAnalyticsView,
    LeaderboardView, DashboardSubjectsView,
    WeakTopicsView, EntForecastView, StudentReportView,
)

urlpatterns = [
    path('student/', StudentDashboardView.as_view(), name='student-dashboard'),
    path('student/weak-topics/', WeakTopicsView.as_view(), name='weak-topics'),
    path('student/ent-forecast/', EntForecastView.as_view(), name='ent-forecast'),
    path('teacher/', TeacherDashboardView.as_view(), name='teacher-dashboard'),
    path('teacher/students/', TeacherStudentsView.as_view(), name='teacher-students'),
    path('teacher/students/<int:student_id>/report.pdf/', StudentReportView.as_view(), name='student-report'),
    path('teacher/analytics/', TeacherAnalyticsView.as_view(), name='teacher-analytics'),
    path('leaderboard/', LeaderboardView.as_view(), name='leaderboard'),
    path('teacher/dashboard-subjects/', DashboardSubjectsView.as_view(), name='dashboard-subjects'),
]
