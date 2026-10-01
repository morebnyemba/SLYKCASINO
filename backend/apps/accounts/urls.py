from django.urls import path
from rest_framework.routers import SimpleRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import (
    AdminAuditLogViewSet,
    AdminKYCViewSet,
    DataExportView,
    DeleteAccountView,
    KYCSubmitView,
    LogoutView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PlayerViewSet,
    RegisterView,
    RequestVerificationView,
    ResponsibleGamblingView,
    SelfExcludeView,
    VerifyEmailView,
)

router = SimpleRouter()
router.register('players', PlayerViewSet, basename='player')
router.register('admin/kyc', AdminKYCViewSet, basename='admin-kyc')
router.register('admin/audit-log', AdminAuditLogViewSet, basename='admin-audit-log')

rg_urlpatterns = [
    path('players/me/rg/', ResponsibleGamblingView.as_view(), name='player-rg'),
    path('players/me/self-exclude/', SelfExcludeView.as_view(), name='player-self-exclude'),
    path('players/me/export/', DataExportView.as_view(), name='player-export'),
    path('players/me/delete/', DeleteAccountView.as_view(), name='player-delete'),
    path('players/me/kyc/', KYCSubmitView.as_view(), name='player-kyc'),
]

auth_urlpatterns = [
    path('auth/register/', RegisterView.as_view(), name='auth-register'),
    path('auth/login/',    TokenObtainPairView.as_view(), name='auth-login'),
    path('auth/refresh/',  TokenRefreshView.as_view(), name='auth-refresh'),
    path('auth/logout/',   LogoutView.as_view(), name='auth-logout'),
    path('auth/verify-email/request/', RequestVerificationView.as_view(), name='verify-email-request'),
    path('auth/verify-email/confirm/', VerifyEmailView.as_view(), name='verify-email-confirm'),
    path('auth/password-reset/', PasswordResetRequestView.as_view(), name='password-reset'),
    path('auth/password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
]

urlpatterns = router.urls + auth_urlpatterns + rg_urlpatterns
