from django.urls import path
from rest_framework.routers import SimpleRouter

from .admin_api import AdminEventViewSet, AdminLeagueViewSet, FeedSettingsView, FeedSyncView, FeedTestView
from .views import (
    AdminBetViewSet, AdminCashoutSettingsView, AdminTicketsView, BetSlipViewSet, BetViewSet, BookingCodeCreateView,
    BookingCodeDetailView, CashoutOffersView, EventViewSet, MultiBetBonusView,
)

router = SimpleRouter()
router.register('events', EventViewSet, basename='event')
router.register('bets', BetViewSet, basename='bet')
router.register('betslips', BetSlipViewSet, basename='betslip')
router.register('admin/bets', AdminBetViewSet, basename='admin-bet')
router.register('admin/sportsbook/events', AdminEventViewSet, basename='admin-sb-event')
router.register('admin/sportsbook/leagues', AdminLeagueViewSet, basename='admin-sb-league')

urlpatterns = [
    path('booking-codes/', BookingCodeCreateView.as_view(), name='booking-code-create'),
    path('booking-codes/<str:code>/', BookingCodeDetailView.as_view(), name='booking-code-detail'),
    path('multibet-bonus/', MultiBetBonusView.as_view(), name='multibet-bonus'),
    path('cashout/offers/', CashoutOffersView.as_view(), name='cashout-offers'),
    path('admin/tickets/', AdminTicketsView.as_view(), name='admin-tickets'),
    path('admin/sportsbook/cashout/', AdminCashoutSettingsView.as_view(), name='admin-sb-cashout'),
    path('admin/sportsbook/feed/', FeedSettingsView.as_view(), name='admin-sb-feed'),
    path('admin/sportsbook/feed/test/', FeedTestView.as_view(), name='admin-sb-feed-test'),
    path('admin/sportsbook/feed/sync/', FeedSyncView.as_view(), name='admin-sb-feed-sync'),
    *router.urls,
]
