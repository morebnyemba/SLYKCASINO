from rest_framework.routers import SimpleRouter

from .views import ChatMessageViewSet

router = SimpleRouter()
router.register('chat', ChatMessageViewSet, basename='chat')

urlpatterns = router.urls
