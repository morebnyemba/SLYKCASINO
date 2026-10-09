from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import AdminAffiliateViewSet, AdminPayoutViewSet, AdminProgrammeView, MyPayoutsView, AdminCommissionViewSet, ClickView, MyAffiliateAnalyticsView, MyAffiliateView, TermsView

router = SimpleRouter()
router.register('admin/affiliates', AdminAffiliateViewSet, basename='admin-affiliate')
router.register('admin/affiliate-payouts', AdminPayoutViewSet, basename='admin-affiliate-payout')
router.register('admin/affiliate-commissions', AdminCommissionViewSet, basename='admin-affiliate-commission')

urlpatterns = [
    path('affiliates/me/', MyAffiliateView.as_view(), name='affiliate-me'),
    path('affiliates/me/payouts/', MyPayoutsView.as_view(), name='affiliate-payouts'),
    path('affiliates/me/analytics/', MyAffiliateAnalyticsView.as_view(), name='affiliate-analytics'),
    path('affiliates/terms/', TermsView.as_view(), name='affiliate-terms'),
    path('affiliates/click/', ClickView.as_view(), name='affiliate-click'),
    path('admin/affiliate-programme/', AdminProgrammeView.as_view(), name='admin-affiliate-programme'),
    *router.urls,
]
