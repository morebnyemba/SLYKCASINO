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
from .models import DepositBonus, Promotion, PromotionClaim, Tournament, TournamentEntry


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


def _system_promotion(code: str, name: str) -> Promotion:
    """A hidden, never-claimable promotion that system-granted bonuses hang
    their claims (and wagering) on."""
    promo, _ = Promotion.objects.get_or_create(
        code=code, defaults={'name': name, 'kind': Promotion.Kind.DEPOSIT, 'active': False, 'bonus_amount': 0},
    )
    return promo


@transaction.atomic
def grant_bonus(
    *, player_id: int, amount: Decimal, wagering_multiplier: Decimal, system_code: str, name: str,
    message: str = '',
) -> PromotionClaim | None:
    """Credit a system bonus of any amount (e.g. a % of a deposit) once per
    player per programme, with a wagering requirement that keeps it from being
    withdrawn until met. Idempotent: a second call returns the same claim."""
    amount = utils.quantize(Decimal(amount))
    if amount <= 0:
        return None
    promo = _system_promotion(system_code, name)
    required = utils.wagering_requirement(amount, Decimal(wagering_multiplier))
    claim, created = PromotionClaim.objects.get_or_create(
        player_id=player_id, promotion=promo,
        defaults={'bonus_amount': amount, 'wagering_required': required},
    )
    if not created:
        return claim
    wallet_services.credit(
        player_id=player_id, amount=amount, kind='bonus',
        idempotency_key=helpers.bonus_credit_key(claim.id), reference=f'claim:{claim.id}',
    )
    claim.bonus_credited = True
    if required <= 0:
        claim.status = PromotionClaim.Status.COMPLETED
        claim.completed_at = timezone.now()
    claim.save(update_fields=['bonus_credited', 'status', 'completed_at'])
    from apps.notifications import services as notif_services
    notif_services.notify(
        player_id=player_id, kind='bonus_credited', title=f'{name} credited',
        body=message or f'{amount} bonus has been added to your wallet.',
    )
    return claim


# -- deposit promotions --------------------------------------------------------

def _live_tiers(now=None):
    from django.db.models import Q

    now = now or timezone.now()
    return (DepositBonus.objects.filter(active=True)
            .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
            .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now)))


def live_deposit_bonuses():
    """The deposit promotions running right now, smallest deposit first."""
    return list(_live_tiers())


def deposit_bonus_for(amount: Decimal, tiers) -> tuple[DepositBonus | None, Decimal]:
    """The tier that gives this deposit the biggest bonus, and that bonus."""
    best, bonus = None, Decimal('0')
    for tier in tiers:
        if amount < tier.min_deposit or (tier.max_deposit is not None and amount > tier.max_deposit):
            continue
        value = utils.quantize(amount * tier.percent / Decimal('100'))
        if tier.max_bonus > 0:
            value = min(value, tier.max_bonus)
        if value > bonus:
            best, bonus = tier, value
    return best, bonus


def _tier_promotion(tier: DepositBonus) -> Promotion:
    promo, _ = Promotion.objects.get_or_create(
        code=f'deposit-bonus:{tier.pk}',
        defaults={'name': tier.name, 'kind': Promotion.Kind.DEPOSIT, 'active': False, 'bonus_amount': 0},
    )
    return promo


def _used_up(tier: DepositBonus, promo: Promotion, player_id: int) -> bool:
    claims = PromotionClaim.objects.filter(player_id=player_id, promotion=promo)
    if tier.limit == DepositBonus.Limit.ONCE:
        return claims.exists()
    if tier.limit == DepositBonus.Limit.DAILY:
        return claims.filter(created_at__date=timezone.localdate()).exists()
    return False


@transaction.atomic
def on_deposit(*, player_id: int, amount: Decimal, deposit_id: int) -> PromotionClaim | None:
    """Called by the wallet for every new deposit: credit the best running
    deposit promotion for its amount (if the player hasn't used it up), as
    bonus money locked until wagered. At most once per deposit."""
    amount = Decimal(amount)
    # Skip tiers this player has used up, then pick the best of the rest.
    usable = [t for t in _live_tiers()
              if t.limit == DepositBonus.Limit.EVERY or not _used_up(t, _tier_promotion(t), player_id)]
    tier, bonus = deposit_bonus_for(amount, usable)
    if tier is None or bonus <= 0:
        return None
    promo = _tier_promotion(tier)
    required = utils.wagering_requirement(bonus, tier.wagering_multiplier)
    claim, created = PromotionClaim.objects.get_or_create(
        source=f'deposit:{deposit_id}',
        defaults={'player_id': player_id, 'promotion': promo, 'bonus_amount': bonus, 'wagering_required': required},
    )
    if not created:
        return claim
    wallet_services.credit(
        player_id=player_id, amount=bonus, kind='bonus',
        idempotency_key=helpers.bonus_credit_key(claim.id), reference=f'claim:{claim.id}',
    )
    claim.bonus_credited = True
    if required <= 0:
        claim.status = PromotionClaim.Status.COMPLETED
        claim.completed_at = timezone.now()
    claim.save(update_fields=['bonus_credited', 'status', 'completed_at'])
    from apps.notifications import services as notif_services
    notif_services.notify(
        player_id=player_id, kind='bonus_credited', title=f'{tier.name}: {bonus} bonus',
        body=(f'You got {bonus} ({tier.percent.normalize():f}% of your {utils.quantize(amount)} deposit). '
              + (f'Bet {required} in total to make it withdrawable.' if required > 0 else 'It’s yours to use now.')),
    )
    return claim


def used_deposit_bonuses(player_id: int, tiers) -> set[int]:
    """Which of these limited tiers the player can't get again right now."""
    return {t.pk for t in tiers
            if t.limit != DepositBonus.Limit.EVERY and _used_up(t, _tier_promotion(t), player_id)}


def deposit_bonus_stats() -> dict[int, dict]:
    """Per tier: how many bonuses it has given and their total."""
    from django.db.models import Sum

    rows = (PromotionClaim.objects.filter(promotion__code__startswith='deposit-bonus:', bonus_credited=True)
            .values('promotion__code').annotate(n=Count('id'), total=Sum('bonus_amount')))
    return {int(r['promotion__code'].split(':')[1]): {'given': r['n'], 'total': r['total'] or Decimal('0')} for r in rows}


def bonus_status(player_id: int) -> dict:
    """Bonus money still locked by unmet wagering, and how much wagering is
    left to unlock it all. Locked bonus can be played but not withdrawn."""
    locked = remaining = Decimal('0')
    for claim in PromotionClaim.objects.filter(
        player_id=player_id, status=PromotionClaim.Status.ACTIVE, bonus_credited=True,
    ):
        left = claim.wagering_required - claim.wagering_progress
        if left > 0:
            locked += claim.bonus_amount
            remaining += left
    return {'locked': utils.quantize(locked), 'wagering_remaining': utils.quantize(remaining)}


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


def erase_player_data(player_id: int) -> int:
    return (PromotionClaim.objects.filter(player_id=player_id).delete()[0]
            + TournamentEntry.objects.filter(player_id=player_id).delete()[0])
