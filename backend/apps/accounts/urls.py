from django.urls import path
from rest_framework.routers import SimpleRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import LogoutView, PlayerViewSet, RegisterView

router = SimpleRouter()
router.register('players', PlayerViewSet, basename='player')

auth_urlpatterns = [
    path('auth/register/', RegisterView.as_view(), name='auth-register'),
    path('auth/login/',    TokenObtainPairView.as_view(), name='auth-login'),
    path('auth/refresh/',  TokenRefreshView.as_view(), name='auth-refresh'),
    path('auth/logout/',   LogoutView.as_view(), name='auth-logout'),
]

urlpatterns = router.urls + auth_urlpatterns
