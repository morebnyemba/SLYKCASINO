from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAdminUser

from apps.accounts.models import AuditLog
from apps.accounts.services import audit

from .models import SiteIdentity, SiteTheme
from .serializers import SiteIdentitySerializer, SiteThemeSerializer


class SiteThemeView(generics.RetrieveUpdateAPIView):
    """GET /api/branding/theme/ — public, used by the site to render.

    PATCH /api/branding/theme/ — admin-only, edits the live sitewide theme.
    """
    serializer_class = SiteThemeSerializer

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH'):
            return [IsAdminUser()]
        return [AllowAny()]

    def get_object(self):
        return SiteTheme.load()

    def perform_update(self, serializer):
        serializer.save(updated_by_username=self.request.user.username)
        audit(
            None,
            AuditLog.EventType.THEME_UPDATED,
            request=self.request,
            actor=self.request.user.username,
        )


class SiteIdentityView(generics.RetrieveUpdateAPIView):
    """GET /api/branding/identity/ — public, used by the site to render.

    PATCH /api/branding/identity/ — admin-only, edits the live site name/logo/license.
    """
    serializer_class = SiteIdentitySerializer

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH'):
            return [IsAdminUser()]
        return [AllowAny()]

    def get_object(self):
        return SiteIdentity.load()

    def perform_update(self, serializer):
        serializer.save(updated_by_username=self.request.user.username)
        audit(
            None,
            AuditLog.EventType.IDENTITY_UPDATED,
            request=self.request,
            actor=self.request.user.username,
        )
