from rest_framework.routers import SimpleRouter

from .views import MyClaimsViewSet, PromotionViewSet, TournamentViewSet

router = SimpleRouter()
router.register('promotions/tournaments', TournamentViewSet, basename='tournament')
router.register('promotions/my-claims', MyClaimsViewSet, basename='my-claims')
router.register('promotions', PromotionViewSet, basename='promotion')

urlpatterns = router.urls
