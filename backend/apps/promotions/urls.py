from rest_framework.routers import SimpleRouter

from .views import PromotionViewSet

router = SimpleRouter()
router.register('promotions', PromotionViewSet, basename='promotion')

urlpatterns = router.urls
