from django.urls import path
from rest_framework.routers import SimpleRouter

from .bulk_views import AdminBulkGrantView, AdminBulkGrantsView
from .cashback_views import AdminCashbackView

from .views import (
    AdminAnnouncementView, AdminDepositBonusViewSet, AdminPromoCodeViewSet, PromoCodeCheckView, AnnouncementView, DepositBonusListView, BannerImageUploadView, BannerImageView, BannerViewSet, MyClaimsViewSet, PromotionViewSet, TournamentViewSet,
)

router = SimpleRouter()
router.register('admin/deposit-bonuses', AdminDepositBonusViewSet, basename='admin-deposit-bonus')
router.register('admin/promo-codes', AdminPromoCodeViewSet, basename='admin-promo-code')
router.register('promotions/banners', BannerViewSet, basename='banner')
router.register('promotions/tournaments', TournamentViewSet, basename='tournament')
router.register('promotions/my-claims', MyClaimsViewSet, basename='my-claims')
router.register('promotions', PromotionViewSet, basename='promotion')

# Before the router, whose promotions/<pk>/ route would otherwise swallow these.
urlpatterns = [
    path('announcement/', AnnouncementView.as_view(), name='announcement'),
    path('promo-codes/check/', PromoCodeCheckView.as_view(), name='promo-code-check'),
    path('admin/announcement/', AdminAnnouncementView.as_view(), name='admin-announcement'),
    path('admin/cashback/', AdminCashbackView.as_view(), name='admin-cashback'),
    path('admin/bulk-grants/', AdminBulkGrantsView.as_view(), name='admin-bulk-grants'),
    path('admin/bulk-grants/<int:pk>/', AdminBulkGrantView.as_view(), name='admin-bulk-grant'),
    path('promotions/deposit-bonuses/', DepositBonusListView.as_view(), name='deposit-bonuses'),
    path('promotions/banner-images/', BannerImageUploadView.as_view(), name='banner-image-upload'),
    path('promotions/banner-images/<int:pk>/', BannerImageView.as_view(), name='banner-image'),
    *router.urls,
]
