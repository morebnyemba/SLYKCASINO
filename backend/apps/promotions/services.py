"""promotions domain logic — the ONLY place promotions mutations happen.

Claiming credits a bonus to the wallet (idempotency-keyed per claim) and sets a
wagering requirement. Wagering from other domains is recorded against active
claims; once met, the claim completes.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.wallet import services as wallet_services

from . import helpers, utils
from .clients import CampaignProviderClient
from .models import Promotion, PromotionClaim


def list_promotions():
    return Promotion.objects.annotate(claim_count=Count('claims'))


@transaction.atomic
def claim_promotion(*, player_id: int, promotion_id: int) -> PromotionClaim:
    """Claim a promotion: credit the bonus once and set the wagering target."""
    errors = helpers.validate_claim_request_structure({'player_id': player_id, 'promotion_id': promotion_id})
    if errors:
        raise ValueError('; '.join(errors))

    eligibility = CampaignProviderClient().check_eligibility(player_id, promotion_id)
    if not eligibility.eligible:
        raise ValueError(f'player not eligible: {eligibility.reason or "ineligible"}')

    promo = Promotion.objects.get(pk=promotion_id, active=True)
    required = utils.wagering_requirement(promo.bonus_amount, promo.wagering_multiplier)

    claim, created = PromotionClaim.objects.get_or_create(
        player_id=player_id, promotion=promo,
        defaults={'bonus_amount': promo.bonus_amount, 'wagering_required': required},
    )
    if not created:
        return claim  # idempotent — one claim per (player, promotion)

    if promo.bonus_amount > 0:
        wallet_services.credit(
            player_id=player_id, amount=promo.bonus_amount, kind='bonus',
            idempotency_key=helpers.bonus_credit_key(claim.id), reference=f'claim:{claim.id}',
        )
        claim.bonus_credited = True
        claim.save(update_fields=['bonus_credited'])
        # Notify player that bonus was credited (lazy import avoids circular).
        from apps.notifications import services as notif_services
        promo_name = getattr(promo, 'name', f'Promotion #{promo.pk}')
        notif_services.notify(
            player_id=player_id,
            kind='bonus_credited',
            title='Bonus credited',
            body=f'{promo.bonus_amount} bonus from "{promo_name}" has been credited to your wallet.',
        )
    return claim


@transaction.atomic
def record_wagering(*, player_id: int, amount: Decimal) -> int:
    """Add wagering to all active claims for a player; complete those that meet
    their requirement. Returns the number of claims completed."""
    completed = 0
    claims = PromotionClaim.objects.select_for_update().filter(
        player_id=player_id, status=PromotionClaim.Status.ACTIVE,
    )
    for claim in claims:
        claim.wagering_progress = utils.quantize(claim.wagering_progress + amount)
        if utils.is_wagering_complete(claim.wagering_progress, claim.wagering_required):
            claim.status = PromotionClaim.Status.COMPLETED
            claim.completed_at = timezone.now()
            completed += 1
        claim.save(update_fields=['wagering_progress', 'status', 'completed_at'])
    return completed
