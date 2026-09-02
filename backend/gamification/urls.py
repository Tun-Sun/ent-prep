from django.urls import path
from .views import (
    AchievementsView, OpponentsView,
    DuelListView, DuelRespondView, DuelPlayView,
)

urlpatterns = [
    path('achievements/', AchievementsView.as_view(), name='achievements'),
    path('duels/opponents/', OpponentsView.as_view(), name='duel-opponents'),
    path('duels/', DuelListView.as_view(), name='duels'),
    path('duels/<int:duel_id>/respond/', DuelRespondView.as_view(), name='duel-respond'),
    path('duels/<int:duel_id>/play/', DuelPlayView.as_view(), name='duel-play'),
]
