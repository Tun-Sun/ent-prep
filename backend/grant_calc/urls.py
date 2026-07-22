from django.urls import path
from .views import GrantCalcView, UniversityTypeListView

urlpatterns = [
    path('', GrantCalcView.as_view(), name='grant-calc'),
    path('types/', UniversityTypeListView.as_view(), name='grant-calc-types'),
]
