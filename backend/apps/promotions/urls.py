from rest_framework.routers import SimpleRouter

from .views import MyClaimsViewSet, PromotionViewSet

router = SimpleRouter()
router.register('promotions', PromotionViewSet, basename='promotion')
router.register('promotions/my-claims', MyClaimsViewSet, basename='my-claims')

urlpatterns = router.urls
