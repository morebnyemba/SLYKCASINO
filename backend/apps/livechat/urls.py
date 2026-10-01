from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import ChatMessageViewSet, RealtimeTicketView

router = SimpleRouter()
router.register('chat', ChatMessageViewSet, basename='chat')

urlpatterns = router.urls + [
    path('realtime/ticket/', RealtimeTicketView.as_view(), name='realtime-ticket'),
]
