from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import AdminAffiliateViewSet, AdminCommissionViewSet, ClickView, MyAffiliateView, TermsView

router = SimpleRouter()
router.register('admin/affiliates', AdminAffiliateViewSet, basename='admin-affiliate')
router.register('admin/affiliate-commissions', AdminCommissionViewSet, basename='admin-affiliate-commission')

urlpatterns = [
    path('affiliates/me/', MyAffiliateView.as_view(), name='affiliate-me'),
    path('affiliates/terms/', TermsView.as_view(), name='affiliate-terms'),
    path('affiliates/click/', ClickView.as_view(), name='affiliate-click'),
    *router.urls,
]
