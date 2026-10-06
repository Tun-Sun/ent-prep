from django.urls import path

from .api import RunDetailView, RunView

urlpatterns = [
    path("runs/", RunView.as_view(), name="ingest-runs"),
    path("runs/<int:pk>/", RunDetailView.as_view(), name="ingest-run"),
]
