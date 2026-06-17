from django.urls import path
from .views import (
    StartTestView, SubmitAnswerView,
    FinishTestView, TestResultView, StudentTestHistoryView,
)

urlpatterns = [
    path('start/', StartTestView.as_view(), name='start-test'),
    path('<int:session_id>/answer/', SubmitAnswerView.as_view(), name='submit-answer'),
    path('<int:session_id>/finish/', FinishTestView.as_view(), name='finish-test'),
    path('<int:session_id>/result/', TestResultView.as_view(), name='test-result'),
    path('history/', StudentTestHistoryView.as_view(), name='test-history'),
]
