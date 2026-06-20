from rest_framework.routers import SimpleRouter

from .views import CrashViewSet, GameRoundViewSet, GameViewSet

router = SimpleRouter()
router.register('casino/games', GameViewSet, basename='casino-game')
router.register('casino/rounds', GameRoundViewSet, basename='casino-round')
router.register('casino/crash', CrashViewSet, basename='casino-crash')

urlpatterns = router.urls
