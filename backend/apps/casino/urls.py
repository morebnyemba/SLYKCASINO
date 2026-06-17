from rest_framework.routers import SimpleRouter

from .views import GameRoundViewSet, GameViewSet

router = SimpleRouter()
router.register('casino/games', GameViewSet, basename='casino-game')
router.register('casino/rounds', GameRoundViewSet, basename='casino-round')

urlpatterns = router.urls
