from rest_framework.routers import SimpleRouter

from .views import BetViewSet, EventViewSet

router = SimpleRouter()
router.register('events', EventViewSet, basename='event')
router.register('bets', BetViewSet, basename='bet')

urlpatterns = router.urls
