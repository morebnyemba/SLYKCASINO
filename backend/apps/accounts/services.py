"""accounts domain logic — the ONLY place accounts mutations happen.

Imports allowed: models, dtos, utils, helpers, clients, and *other apps' services*
(cross-context integration). Never imports another app's models.
"""
from __future__ import annotations

from typing import Optional

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.wallet import services as wallet_services

from . import helpers, utils
from .clients import KycProviderClient
from .dtos import PlayerDTO
from .models import Player


def to_dto(player: Player) -> PlayerDTO:
    return PlayerDTO.model_validate(player)


def get_player(player_id: int) -> Optional[Player]:
    return Player.objects.filter(pk=player_id).first()


def get_current_player(request) -> Optional[Player]:
    """Resolve the acting player from the authenticated request user."""
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated:
        return Player.objects.filter(user=user).first()
    return None


@transaction.atomic
def register_player(*, username: str, email: str, password: str, currency: str = 'USD') -> Player:
    """Create a Django User + Player atomically, then provision the wallet."""
    User = get_user_model()
    errors = helpers.validate_player_payload({'username': username, 'email': email})
    if errors:
        raise ValueError('; '.join(errors))
    normalized = utils.normalize_username(username)
    if User.objects.filter(username=normalized).exists():
        raise ValueError('username already taken')
    if User.objects.filter(email=email).exists():
        raise ValueError('email already registered')
    user = User.objects.create_user(username=normalized, email=email, password=password)
    player = Player.objects.create(user=user, username=normalized, email=email)
    wallet_services.ensure_wallet(player.id, currency=currency)
    return player


@transaction.atomic
def create_player(*, username: str, email: str = '', currency: str = 'USD') -> Player:
    """Create a player and provision its wallet atomically."""
    errors = helpers.validate_player_payload({'username': username, 'email': email})
    if errors:
        raise ValueError('; '.join(errors))
    player = Player.objects.create(
        username=utils.normalize_username(username),
        email=email,
    )
    # Cross-context: provision the ledger wallet for this identity.
    wallet_services.ensure_wallet(player.id, currency=currency)
    return player


@transaction.atomic
def set_kyc_status(player_id: int, status: str) -> Player:
    """Mutate KYC status, enforcing the forward-only transition rule."""
    player = Player.objects.select_for_update().get(pk=player_id)
    if not utils.is_valid_kyc_transition(player.kyc_status, status):
        raise ValueError(f'illegal KYC transition {player.kyc_status} -> {status}')
    player.kyc_status = status
    player.kyc_updated_at = timezone.now()
    player.save(update_fields=['kyc_status', 'kyc_updated_at'])
    return player


@transaction.atomic
def set_deposit_limit(player_id: int, daily_limit) -> Player:
    """Set or clear the player's daily deposit limit."""
    from decimal import Decimal, InvalidOperation
    player = Player.objects.select_for_update().get(pk=player_id)
    if daily_limit is None or str(daily_limit).strip() == '':
        player.deposit_limit_daily = None
    else:
        try:
            limit = Decimal(str(daily_limit))
            if limit <= 0:
                raise ValueError('limit must be positive')
            player.deposit_limit_daily = limit
        except InvalidOperation:
            raise ValueError('invalid deposit limit')
    player.save(update_fields=['deposit_limit_daily'])
    return player


@transaction.atomic
def self_exclude(player_id: int, days: Optional[int] = None) -> Player:
    """Self-exclude a player. days=None means indefinite exclusion."""
    player = Player.objects.select_for_update().get(pk=player_id)
    player.self_excluded = True
    if days is not None and days > 0:
        player.exclusion_ends_at = timezone.now() + timezone.timedelta(days=days)
    else:
        player.exclusion_ends_at = None
    player.save(update_fields=['self_excluded', 'exclusion_ends_at'])
    return player


def lift_expired_exclusions() -> int:
    """Called periodically; lifts exclusions whose end date has passed."""
    expired = Player.objects.filter(
        self_excluded=True,
        exclusion_ends_at__lte=timezone.now(),
    )
    count = expired.count()
    expired.update(self_excluded=False, exclusion_ends_at=None)
    return count


def check_responsible_gambling(player: Player) -> None:
    """Raise ValueError if the player is blocked from gambling."""
    # Re-check exclusion expiry inline (avoids race with the periodic task).
    if player.self_excluded:
        if player.exclusion_ends_at and timezone.now() >= player.exclusion_ends_at:
            # Lift inline — the periodic task may not have run yet.
            Player.objects.filter(pk=player.id).update(
                self_excluded=False, exclusion_ends_at=None,
            )
        else:
            until = (
                f' until {player.exclusion_ends_at.date()}' if player.exclusion_ends_at else ' (indefinite)'
            )
            raise ValueError(f'Account is self-excluded{until}')


def run_kyc_verification(player_id: int) -> Player:
    """Call the external KYC provider and apply the normalized result."""
    result = KycProviderClient().verify(player_id)
    return set_kyc_status(player_id, result.status)
