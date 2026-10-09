from django.urls import path

from .views import (
    AdminSettingsView, AdminStatsView, BetActionView, BetView, MyBetsView, RoundsView, StateView,
)

urlpatterns = [
    path('jet/state/', StateView.as_view(), name='jet-state'),
    path('jet/bets/', BetView.as_view(), name='jet-bet'),
    path('jet/bets/<int:pk>/cashout/', BetActionView.as_view(action='cashout'), name='jet-cashout'),
    path('jet/bets/<int:pk>/cancel/', BetActionView.as_view(action='cancel'), name='jet-cancel'),
    path('jet/my-bets/', MyBetsView.as_view(), name='jet-my-bets'),
    path('jet/rounds/', RoundsView.as_view(), name='jet-rounds'),
    path('jet/rounds/<int:pk>/', RoundsView.as_view(), name='jet-round'),
    path('admin/jet/settings/', AdminSettingsView.as_view(), name='admin-jet-settings'),
    path('admin/jet/stats/', AdminStatsView.as_view(), name='admin-jet-stats'),
]
