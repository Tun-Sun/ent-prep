from django.urls import path
from .views import (
    StartTestView, StartEntView, SubmitAnswerView,
    SubmitBulkAnswersView, FinishTestView, TestStateView,
    TestResultView, StudentTestHistoryView,
    TeacherTestHistoryView, TeacherTestResultView, TestPreviewView,
    AuthorialTestListView, AuthorialTestDetailView, AuthorialTestDeleteView,
    AIExplainView,
)

urlpatterns = [
    path('start/', StartTestView.as_view(), name='start-test'),
    path('start-ent/', StartEntView.as_view(), name='start-ent'),
    path('<int:session_id>/answer/', SubmitAnswerView.as_view(), name='submit-answer'),
    path('<int:session_id>/answers/bulk/', SubmitBulkAnswersView.as_view(), name='submit-bulk-answers'),
    path('<int:session_id>/finish/', FinishTestView.as_view(), name='finish-test'),
    path('<int:session_id>/state/', TestStateView.as_view(), name='test-state'),
    path('<int:session_id>/result/', TestResultView.as_view(), name='test-result'),
    path('history/', StudentTestHistoryView.as_view(), name='test-history'),
    path('teacher/history/', TeacherTestHistoryView.as_view(), name='teacher-test-history'),
    path('teacher/result/<int:session_id>/', TeacherTestResultView.as_view(), name='teacher-test-result'),
    path('preview/', TestPreviewView.as_view(), name='test-preview'),
    path('authorial-tests/', AuthorialTestListView.as_view(), name='authorial-test-list'),
    path('authorial-tests/<str:form_id>/', AuthorialTestDeleteView.as_view(), name='authorial-test-delete'),
    path('authorial-tests/<str:form_id>/questions/', AuthorialTestDetailView.as_view(), name='authorial-test-detail'),
    path('<int:session_id>/ai-explain/', AIExplainView.as_view(), name='ai-explain'),
]
