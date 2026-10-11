from django.urls import path

from .views import AdminSupportInboxView, AdminSupportThreadView, RealtimeTicketView, SupportChatView

# The old public chat lobby (/api/chat/) is gone: support is private, one
# conversation per player, readable only by that player and staff.
urlpatterns = [
    path('support/messages/', SupportChatView.as_view(), name='support-messages'),
    path('admin/support/', AdminSupportInboxView.as_view(), name='admin-support-inbox'),
    path('admin/support/<int:player_id>/', AdminSupportThreadView.as_view(), name='admin-support-thread'),
    path('realtime/ticket/', RealtimeTicketView.as_view(), name='realtime-ticket'),
]
