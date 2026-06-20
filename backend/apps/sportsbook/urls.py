from rest_framework.routers import SimpleRouter

from .views import AdminBetViewSet, BetSlipViewSet, BetViewSet, EventViewSet

router = SimpleRouter()
router.register('events', EventViewSet, basename='event')
router.register('bets', BetViewSet, basename='bet')
router.register('betslips', BetSlipViewSet, basename='betslip')
router.register('admin/bets', AdminBetViewSet, basename='admin-bet')

urlpatterns = router.urls
