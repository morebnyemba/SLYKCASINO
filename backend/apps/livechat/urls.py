from django.urls import path

from .room_views import (
    AdminModerateView, AdminMutesView, AdminMuteView, AdminRoomMessagesView, AdminRoomsView, AdminRoomView,
    ReportMessageView, RoomMessagesView, RoomsView,
)
from .views import AdminSupportInboxView, AdminSupportThreadView, RealtimeTicketView, SupportChatView

# The old public chat lobby (/api/chat/) is gone: support is private, one
# conversation per player, readable only by that player and staff.
urlpatterns = [
    path('support/messages/', SupportChatView.as_view(), name='support-messages'),
    path('admin/support/', AdminSupportInboxView.as_view(), name='admin-support-inbox'),
    path('admin/support/<int:player_id>/', AdminSupportThreadView.as_view(), name='admin-support-thread'),
    path('realtime/ticket/', RealtimeTicketView.as_view(), name='realtime-ticket'),
    # Group chat rooms (players, agents, staff) and their moderation.
    path('chat/rooms/', RoomsView.as_view(), name='chat-rooms'),
    path('chat/rooms/<slug:slug>/messages/', RoomMessagesView.as_view(), name='chat-room-messages'),
    path('chat/messages/<int:pk>/report/', ReportMessageView.as_view(), name='chat-report'),
    path('admin/chat/rooms/', AdminRoomsView.as_view(), name='admin-chat-rooms'),
    path('admin/chat/rooms/<int:pk>/', AdminRoomView.as_view(), name='admin-chat-room'),
    path('admin/chat/rooms/<int:pk>/messages/', AdminRoomMessagesView.as_view(), name='admin-chat-room-messages'),
    path('admin/chat/moderate/', AdminModerateView.as_view(), name='admin-chat-moderate'),
    path('admin/chat/mutes/', AdminMutesView.as_view(), name='admin-chat-mutes'),
    path('admin/chat/mutes/<int:player_id>/', AdminMuteView.as_view(), name='admin-chat-mute'),
]
