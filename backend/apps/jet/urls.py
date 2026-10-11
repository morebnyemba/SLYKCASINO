from django.urls import path

from .views import (
    AdminChatView, AdminPlayerBetsView, AdminRainView, AdminSettingsView, AdminStatsView, BetActionView, BetView, ChatView, MyBetsView,
    RoundsView, StateView,
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
    path('jet/chat/', ChatView.as_view(), name='jet-chat'),
    path('admin/jet/bets/', AdminPlayerBetsView.as_view(), name='admin-jet-bets'),
    path('admin/jet/rain/', AdminRainView.as_view(), name='admin-jet-rain'),
    path('admin/jet/chat/', AdminChatView.as_view(), name='admin-jet-chat'),
    path('admin/jet/chat/<int:pk>/hide/', AdminChatView.as_view(action='hide'), name='admin-jet-chat-hide'),
    path('admin/jet/chat/mute/', AdminChatView.as_view(action='mute'), name='admin-jet-chat-mute'),
]
