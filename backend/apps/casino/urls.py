from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import AdminGameDetailView, AdminGamesView, CrashViewSet, GameRoundViewSet, GameViewSet, MyWaitlistView

router = SimpleRouter()
router.register('casino/games', GameViewSet, basename='casino-game')
router.register('casino/rounds', GameRoundViewSet, basename='casino-round')
router.register('casino/crash', CrashViewSet, basename='casino-crash')

urlpatterns = [
    path('casino/waitlist/', MyWaitlistView.as_view(), name='casino-waitlist'),
    path('admin/casino/games/', AdminGamesView.as_view(), name='admin-casino-games'),
    path('admin/casino/games/<int:pk>/', AdminGameDetailView.as_view(), name='admin-casino-game'),
] + router.urls
