"""Staff "view as player": a player session minted for a staff member.

The tokens are ordinary SimpleJWT tokens for the player's user with extra
claims, copied onto every access token and every rotated refresh token:

- `imp`       id of the staff user who started it (who is accountable)
- `imp_by`    their username (shown on the player site's banner)
- `imp_mode`  'view' (read-only, any staff) or 'full' (superusers only)
- `imp_exp`   hard end of the session (unix time). Refresh rotation resets a
              token's own `exp`, so this claim is what actually caps it.

Enforcement lives in the authentication class and the refresh serializer
(both wired up in settings), so every endpoint gets it without opting in.
"""
from __future__ import annotations

import logging
import time
from datetime import timedelta

from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import SAFE_METHODS
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

logger = logging.getLogger(__name__)

SESSION_LENGTH = timedelta(hours=1)
MODES = ('view', 'full')
# Writes a read-only session may still make: ending itself.
READ_ONLY_ALLOWED = ('/auth/logout/',)


class ImpersonationRefused(ValueError):
    """The player can't be impersonated (shown to the operator)."""


def start(staff_user, player, *, mode: str = 'view') -> dict:
    """Mint a refresh token that signs `staff_user` in as `player`. The caller
    audits it; the player site swaps the token for a fresh pair straight away
    (rotation blacklists it), so it is single-use."""
    if mode not in MODES:
        raise ImpersonationRefused('Choose "view" or "full".')
    if mode == 'full' and not staff_user.is_superuser:
        raise ImpersonationRefused('Only a superuser can act as a player. Use view-only instead.')
    user = player.user
    if user is None or not user.is_active:
        raise ImpersonationRefused('This player has no active login.')
    if user.is_staff or user.is_superuser:
        raise ImpersonationRefused('Staff accounts can’t be impersonated.')
    if user.pk == staff_user.pk:
        raise ImpersonationRefused('That’s your own account.')

    ends_at = int(time.time() + SESSION_LENGTH.total_seconds())
    refresh = RefreshToken.for_user(user)
    refresh.set_exp(lifetime=SESSION_LENGTH)
    refresh['is_staff'] = False
    refresh['is_superuser'] = False
    refresh['username'] = player.username
    refresh['imp'] = staff_user.pk
    refresh['imp_by'] = staff_user.get_username()
    refresh['imp_mode'] = mode
    refresh['imp_exp'] = ends_at
    return {'refresh': str(refresh), 'mode': mode, 'expires_at': ends_at, 'username': player.username}


def claims(token) -> dict | None:
    """The impersonation claims on a validated token, or None for a normal session."""
    if token is None or not token.get('imp'):
        return None
    return {'by': token.get('imp'), 'by_username': token.get('imp_by'),
            'mode': token.get('imp_mode') or 'view', 'expires_at': token.get('imp_exp') or 0}


def is_impersonated(request) -> bool:
    return claims(getattr(request, 'auth', None)) is not None


class ImpersonationAwareJWTAuthentication(JWTAuthentication):
    """JWT auth that ends staff sessions on time, keeps 'view' sessions
    read-only and attributes every write made in a 'full' session."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        imp = claims(result[1])
        if imp is None:
            return result
        if imp['expires_at'] < time.time():
            raise AuthenticationFailed('The staff session has ended.', code='impersonation_expired')
        if request.method not in SAFE_METHODS:
            if imp['mode'] != 'full' and not request.path.endswith(READ_ONLY_ALLOWED):
                raise PermissionDenied('View-only staff session: changes are switched off.')
            if imp['mode'] == 'full':
                _audit_write(request, result[0], imp)
        return result


def _audit_write(request, user, imp) -> None:
    from . import services
    player = getattr(user, 'player', None)
    try:
        services.audit(player.id if player else None, 'impersonated_action', request,
                       method=request.method, path=request.path, by=imp['by_username'], by_id=imp['by'])
    except Exception:  # noqa: BLE001 — never block the request on the audit row
        logger.exception('impersonation: could not audit %s %s', request.method, request.path)


class ImpersonationAwareTokenRefreshSerializer(TokenRefreshSerializer):
    """Refuses to extend a staff session past its `imp_exp`."""

    def validate(self, attrs):
        try:
            ends = RefreshToken(attrs['refresh']).get('imp_exp')
        except TokenError:
            ends = None  # the parent raises the proper error
        if ends and ends < time.time():
            raise InvalidToken('The staff session has ended.')
        return super().validate(attrs)
