from rest_framework.routers import SimpleRouter

from .views import PlayerViewSet

router = SimpleRouter()
router.register('players', PlayerViewSet, basename='player')

urlpatterns = router.urls
