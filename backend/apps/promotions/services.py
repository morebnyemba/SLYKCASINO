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
from .models import Promotion, PromotionClaim, Tournament, TournamentEntry


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


# -- tournaments / leaderboards ----------------------------------------------

def list_tournaments():
    return Tournament.objects.all()


def leaderboard(tournament_id: int, *, limit: int = 50):
    return TournamentEntry.objects.filter(tournament_id=tournament_id).order_by('-score', 'updated_at')[:limit]


@transaction.atomic
def join_tournament(*, player_id: int, player_name: str, tournament_id: int) -> TournamentEntry:
    """Opt a player into a tournament. Idempotent — one entry per (tournament, player)."""
    tournament = Tournament.objects.get(pk=tournament_id)
    if not tournament.is_live:
        raise ValueError('tournament is not currently open')
    entry, _ = TournamentEntry.objects.get_or_create(
        tournament=tournament, player_id=player_id,
        defaults={'player_name': player_name},
    )
    return entry


@transaction.atomic
def record_tournament_play(*, player_id: int, wagered: Decimal) -> int:
    """Add a player's wager to their entries in every live, wagered-metric
    tournament. Returns the number of entries updated. Players who have not opted
    in are not scored."""
    if wagered is None or wagered <= 0:
        return 0
    entries = TournamentEntry.objects.select_for_update().filter(
        player_id=player_id,
        tournament__active=True,
        tournament__metric=Tournament.Metric.WAGERED,
    ).select_related('tournament')
    updated = 0
    for entry in entries:
        if not entry.tournament.is_live:
            continue
        entry.score = utils.quantize(entry.score + wagered)
        entry.save(update_fields=['score', 'updated_at'])
        updated += 1
    return updated
