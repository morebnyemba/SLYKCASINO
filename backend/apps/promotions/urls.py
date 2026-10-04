from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    BannerImageUploadView, BannerImageView, BannerViewSet, MyClaimsViewSet, PromotionViewSet, TournamentViewSet,
)

router = SimpleRouter()
router.register('promotions/banners', BannerViewSet, basename='banner')
router.register('promotions/tournaments', TournamentViewSet, basename='tournament')
router.register('promotions/my-claims', MyClaimsViewSet, basename='my-claims')
router.register('promotions', PromotionViewSet, basename='promotion')

# Before the router, whose promotions/<pk>/ route would otherwise swallow these.
urlpatterns = [
    path('promotions/banner-images/', BannerImageUploadView.as_view(), name='banner-image-upload'),
    path('promotions/banner-images/<int:pk>/', BannerImageView.as_view(), name='banner-image'),
    *router.urls,
]
