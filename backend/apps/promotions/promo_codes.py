"""Promo codes: staff create them; players enter one with a deposit and get
its bonus in their Bonus wallet (so the Bonus wallet's rules apply to it).

A code is checked when the player enters it (so they know before paying) and
again when the deposit lands (it may have expired or run out meanwhile — the
deposit is then credited without the bonus and the player is told why). One
bonus per deposit: a code replaces the automatic deposit promotion. The fraud
engine can still refuse the bonus (account under review, or the same code
already used by an account sharing a payment number); the use then still
counts, so the code can't be retried.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Optional

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from . import utils
from .models import PromoCode, PromoRedemption, Promotion, PromotionClaim

CODE_RE = re.compile(r'^[A-Z0-9][A-Z0-9_-]{2,39}$')


class PromoError(ValueError):
    """The code can't be used (the message is for the player)."""


def normalise(code: str) -> str:
    return (code or '').strip().upper()


def bonus_for(promo: PromoCode, amount: Decimal) -> Decimal:
    if promo.kind == PromoCode.Kind.FIXED:
        return utils.quantize(promo.value)
    value = utils.quantize(Decimal(amount) * promo.value / Decimal('100'))
    return min(value, promo.max_bonus) if promo.max_bonus > 0 else value


def find(code: str, *, player_id: int, amount: Optional[Decimal] = None, now=None, lock: bool = False) -> PromoCode:
    """The usable PromoCode for this player (and deposit amount), or PromoError."""
    now = now or timezone.now()
    code = normalise(code)
    qs = PromoCode.objects.select_for_update() if lock else PromoCode.objects
    promo = qs.filter(code=code).first()
    if promo is None or not promo.active:
        raise PromoError('That promo code isn’t valid.')
    if promo.starts_at and now < promo.starts_at:
        raise PromoError('That promo code isn’t active yet.')
    if promo.ends_at and now >= promo.ends_at:
        raise PromoError('That promo code has expired.')
    if promo.max_uses and promo.redemptions.count() >= promo.max_uses:
        raise PromoError('That promo code has been fully used.')
    if promo.per_player_limit and promo.redemptions.filter(player_id=player_id).count() >= promo.per_player_limit:
        raise PromoError('You’ve already used that promo code.')
    if amount is not None and Decimal(amount) < promo.min_deposit:
        raise PromoError(f'That promo code needs a deposit of at least ${promo.min_deposit:.2f}.')
    return promo


def preview(code: str, *, player_id: int, amount: Optional[Decimal] = None) -> dict:
    promo = find(code, player_id=player_id, amount=amount)
    out = {'code': promo.code, 'name': promo.name, 'description': promo.description,
           'kind': promo.kind, 'value': str(promo.value), 'max_bonus': str(promo.max_bonus),
           'min_deposit': str(promo.min_deposit)}
    if amount is not None:
        out['bonus'] = str(bonus_for(promo, Decimal(amount)))
    return out


def _promotion(promo: PromoCode) -> Promotion:
    """The hidden Promotion its claims hang on — its code is what the fraud
    engine compares across linked accounts."""
    obj, _ = Promotion.objects.get_or_create(
        code=f'promo:{promo.id}', defaults={'name': f'Promo code {promo.code}', 'kind': Promotion.Kind.DEPOSIT,
                                            'active': False, 'bonus_amount': 0},
    )
    return obj


@transaction.atomic
def apply_to_deposit(*, player_id: int, code: str, amount: Decimal, deposit_entry_id: int) -> Optional[PromoRedemption]:
    """Give a deposit its promo code's bonus (into the Bonus wallet). Never
    raises for a code problem — the deposit stands and the player is told."""
    from apps.notifications import services as notif_services
    from apps.wallet import services as wallet_services
    from .services import _refused

    existing = PromoRedemption.objects.filter(deposit_entry_id=deposit_entry_id).first()
    if existing is not None:
        return existing
    try:
        promo = find(code, player_id=player_id, amount=amount, lock=True)
    except PromoError as exc:
        notif_services.notify(player_id=player_id, kind='account_alert', title='Promo code not applied',
                              body=f'Your deposit is in your wallet, but {normalise(code)} couldn’t be applied: {exc}')
        return None
    bonus = bonus_for(promo, Decimal(amount))
    try:
        with transaction.atomic():
            redemption = PromoRedemption.objects.create(promo=promo, player_id=player_id, deposit_entry_id=deposit_entry_id,
                                                        deposit_amount=amount, bonus_amount=bonus)
    except IntegrityError:
        return PromoRedemption.objects.get(deposit_entry_id=deposit_entry_id)
    if bonus <= 0:
        return redemption
    promotion = _promotion(promo)
    claim = PromotionClaim.objects.create(player_id=player_id, promotion=promotion, bonus_amount=bonus,
                                          source=f'promo:{deposit_entry_id}', wagering_required=0)
    if _refused(claim, promotion.code):
        redemption.credited = False
        redemption.save(update_fields=['credited'])
        return redemption
    from . import helpers
    wallet_services.credit(player_id=player_id, amount=bonus, kind='bonus',
                           idempotency_key=helpers.bonus_credit_key(claim.id), reference=f'claim:{claim.id}')
    claim.bonus_credited = True
    claim.status = PromotionClaim.Status.COMPLETED
    claim.completed_at = timezone.now()
    claim.save(update_fields=['bonus_credited', 'status', 'completed_at'])
    notif_services.notify(player_id=player_id, kind='bonus_credited', title=f'{promo.code}: ${bonus:.2f} bonus',
                          body=f'{promo.name} — ${bonus:.2f} is in your Bonus wallet.')
    return redemption


def stats() -> dict[int, dict]:
    from django.db.models import Count, Sum
    rows = PromoRedemption.objects.values('promo_id').annotate(
        uses=Count('id'), total=Sum('bonus_amount', filter=Q(credited=True)))
    return {r['promo_id']: {'uses': r['uses'], 'total': f"{(r['total'] or 0):.2f}"} for r in rows}
