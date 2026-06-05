from rest_framework.routers import SimpleRouter

from .views import GameViewSet

router = SimpleRouter()
router.register('casino/games', GameViewSet, basename='casino-game')

urlpatterns = router.urls
