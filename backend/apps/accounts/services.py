"""accounts domain logic — the ONLY place accounts mutations happen.

Imports allowed: models, dtos, utils, helpers, clients, and *other apps' services*
(cross-context integration). Never imports another app's models.
"""
from __future__ import annotations

import secrets
import uuid
from decimal import Decimal
from typing import Optional

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.wallet import services as wallet_services

from . import helpers, utils
from .clients import KycProviderClient
from .dtos import PlayerDTO
from .models import KYCSubmission, Player

User = get_user_model()


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
    if player.is_suspended:
        raise ValueError('Account is suspended')
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


# ---------------------------------------------------------------------------
# Internal KYC document review (manual staff decision, no external provider)
# ---------------------------------------------------------------------------

@transaction.atomic
def submit_kyc_document(player_id: int, *, document_type: str, file) -> KYCSubmission:
    """Player submits an identity document for staff review."""
    submission = KYCSubmission.objects.create(
        player_id=player_id, document_type=document_type, file=file,
    )
    player = Player.objects.select_for_update().get(pk=player_id)
    if player.kyc_status == Player.Kyc.UNVERIFIED:
        player.kyc_status = Player.Kyc.PENDING
        player.kyc_updated_at = timezone.now()
        player.save(update_fields=['kyc_status', 'kyc_updated_at'])
    return submission


@transaction.atomic
def approve_kyc(submission_id: int, *, reviewer_username: str) -> KYCSubmission:
    """Staff approves a document; player's KYC status moves to verified."""
    submission = KYCSubmission.objects.select_for_update().get(pk=submission_id)
    submission.status = KYCSubmission.Status.APPROVED
    submission.reviewed_at = timezone.now()
    submission.reviewed_by_username = reviewer_username
    submission.save(update_fields=['status', 'reviewed_at', 'reviewed_by_username'])
    set_kyc_status(submission.player_id, Player.Kyc.VERIFIED)
    return submission


@transaction.atomic
def reject_kyc(submission_id: int, *, reviewer_username: str, reason: str) -> KYCSubmission:
    """Staff rejects a document. Resets the player back to unverified so they
    can resubmit — an explicit admin override of the normally forward-only
    KYC transition rule (is_valid_kyc_transition), since only a human review
    decision should ever move KYC status backwards."""
    submission = KYCSubmission.objects.select_for_update().get(pk=submission_id)
    submission.status = KYCSubmission.Status.REJECTED
    submission.rejection_reason = reason
    submission.reviewed_at = timezone.now()
    submission.reviewed_by_username = reviewer_username
    submission.save(update_fields=['status', 'rejection_reason', 'reviewed_at', 'reviewed_by_username'])
    player = Player.objects.select_for_update().get(pk=submission.player_id)
    player.kyc_status = Player.Kyc.UNVERIFIED
    player.kyc_updated_at = timezone.now()
    player.save(update_fields=['kyc_status', 'kyc_updated_at'])
    return submission


# ---------------------------------------------------------------------------
# Player suspension (admin override, hard freeze)
# ---------------------------------------------------------------------------

@transaction.atomic
def suspend_player(player_id: int, *, reason: str) -> Player:
    player = Player.objects.select_for_update().get(pk=player_id)
    player.is_suspended = True
    player.suspended_reason = reason
    player.suspended_at = timezone.now()
    player.save(update_fields=['is_suspended', 'suspended_reason', 'suspended_at'])
    return player


@transaction.atomic
def unsuspend_player(player_id: int) -> Player:
    player = Player.objects.select_for_update().get(pk=player_id)
    player.is_suspended = False
    player.suspended_reason = ''
    player.suspended_at = None
    player.save(update_fields=['is_suspended', 'suspended_reason', 'suspended_at'])
    return player


# ---------------------------------------------------------------------------
# Manual balance adjustment (staff override on the wallet ledger)
# ---------------------------------------------------------------------------

def adjust_balance(player_id: int, *, amount: Decimal, reason: str):
    """Post a signed manual adjustment to the player's wallet ledger.

    Positive amount credits, negative amount debits. Uses the same
    append-only ledger primitive as every other money movement.
    """
    amount = Decimal(str(amount))
    idempotency_key = f'adjustment:{uuid.uuid4()}'
    if amount >= 0:
        return wallet_services.credit(
            player_id=player_id, amount=amount, kind='adjustment',
            idempotency_key=idempotency_key, reference=reason,
        )
    return wallet_services.debit(
        player_id=player_id, amount=amount, kind='adjustment',
        idempotency_key=idempotency_key, reference=reason, allow_negative=True,
    )


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------

def generate_verify_token(player_id: int) -> str:
    """Generate and store an email verification token for the player."""
    player = Player.objects.get(pk=player_id)
    token = secrets.token_urlsafe(32)
    player.email_verify_token = token
    player.save(update_fields=['email_verify_token'])
    return token


def verify_email(token: str) -> Player:
    """Find player by verification token, mark email as verified, clear token."""
    try:
        player = Player.objects.get(email_verify_token=token)
    except Player.DoesNotExist:
        raise ValueError('Invalid or expired verification token.')
    player.email_verified = True
    player.email_verify_token = ''
    player.save(update_fields=['email_verified', 'email_verify_token'])
    return player


def generate_password_reset_token(email: str):
    """Generate uid+token for password reset. Returns (user, uid, token) or None."""
    user = User.objects.filter(email=email).first()
    if user is None:
        return None
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return user, uid, token


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def audit(player_id, event_type, request=None, **metadata):
    from .models import AuditLog
    ip = None
    if request:
        ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR')
    AuditLog.objects.create(
        player_id=player_id,
        event_type=event_type,
        ip_address=ip or None,
        metadata=metadata,
    )
