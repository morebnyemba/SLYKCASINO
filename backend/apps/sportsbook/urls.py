from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    AdminBetViewSet, BetSlipViewSet, BetViewSet, BookingCodeCreateView, BookingCodeDetailView, EventViewSet,
    MultiBetBonusView,
)

router = SimpleRouter()
router.register('events', EventViewSet, basename='event')
router.register('bets', BetViewSet, basename='bet')
router.register('betslips', BetSlipViewSet, basename='betslip')
router.register('admin/bets', AdminBetViewSet, basename='admin-bet')

urlpatterns = [
    path('booking-codes/', BookingCodeCreateView.as_view(), name='booking-code-create'),
    path('booking-codes/<str:code>/', BookingCodeDetailView.as_view(), name='booking-code-detail'),
    path('multibet-bonus/', MultiBetBonusView.as_view(), name='multibet-bonus'),
    *router.urls,
]
