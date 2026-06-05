"""accounts domain logic — the ONLY place accounts mutations happen.

Imports allowed: models, dtos, utils, helpers, clients, and *other apps' services*
(cross-context integration). Never imports another app's models.
"""
from __future__ import annotations

from typing import Optional

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
    """Resolve the acting player. Falls back to the first player until real
    auth lands (documented stand-in, mirrors the previous behaviour)."""
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated:
        return Player.objects.filter(user=user).first()
    return Player.objects.order_by('id').first()


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


def run_kyc_verification(player_id: int) -> Player:
    """Call the external KYC provider and apply the normalized result."""
    result = KycProviderClient().verify(player_id)
    return set_kyc_status(player_id, result.status)
