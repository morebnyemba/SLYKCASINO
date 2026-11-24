"""Lost-by-one refund: a multiple that lost on exactly one match, with ticket
odds above LossRefundSettings.min_odds (25), gets back

    stake × ticket odds ÷ divisor (25) ÷ the lost match's odds

paid to the Winnings wallet once the last match has a result (a multiple is
marked lost as soon as one leg loses, so this is checked again as the others
settle). Example: $1 at 100.00 that lost on a 2.00 -> 1 × 100 ÷ 25 ÷ 2 = $2.00.

Several picks from the same match are one match here, at their one price
(BetLeg.match_odds). Bonus-wallet tickets and anonymous tickets get nothing:
a refund to Winnings would turn bonus money into cash. Idempotent per ticket.
"""
from __future__ import annotations

from decimal import ROUND_DOWN, Decimal
from typing import Optional

CENT = Decimal('0.01')


def amount_for(slip, settings=None) -> Optional[Decimal]:
    """The refund this lost ticket earns, or None."""
    from apps.sportsbook.models import BetLeg, BetSlip

    from .models import LossRefundSettings
    cfg = settings or LossRefundSettings.load()
    if not cfg.enabled or slip.status != BetSlip.Status.LOST or not slip.player_id or slip.wallet == 'bonus':
        return None
    if Decimal(slip.combined_odds) <= cfg.min_odds or cfg.divisor <= 0:
        return None
    legs = list(slip.legs.all())
    if any(leg.result == BetLeg.Result.PENDING for leg in legs):
        return None                                   # not every match has a result yet
    matches: dict = {}
    for i, leg in enumerate(legs):
        matches.setdefault(leg.event_ref_id or f'leg{i}', []).append(leg)
    if len(matches) < 2:
        return None
    lost = [group for group in matches.values() if any(leg.result == BetLeg.Result.LOST for leg in group)]
    if len(lost) != 1:
        return None
    group = lost[0]
    lost_odds = group[0].match_odds if group[0].match_odds else None
    if lost_odds is None:
        lost_odds = Decimal('1')
        for leg in group:
            lost_odds *= Decimal(leg.odds)
    if lost_odds <= 0:
        return None
    amount = (Decimal(slip.stake) * Decimal(slip.combined_odds) / cfg.divisor / Decimal(lost_odds)).quantize(CENT, rounding=ROUND_DOWN)
    if cfg.max_refund is not None:
        amount = min(amount, cfg.max_refund)
    return amount if amount >= CENT else None


def check_slip(slip) -> Optional[Decimal]:
    """Pay the refund for this ticket if it has earned one (once). Returns what was paid."""
    from apps.wallet import services as wallet
    from apps.wallet.models import LedgerEntry
    key = f'loss-refund:slip:{slip.pk}'
    if LedgerEntry.objects.filter(idempotency_key=key).exists():
        return None
    amount = amount_for(slip)
    if amount is None:
        return None
    wallet.credit(player_id=slip.player_id, amount=amount, kind='loss_refund', bucket='winnings',
                  idempotency_key=key, reference=f'slip:{slip.pk}')
    from apps.notifications import services as notes
    notes.notify(player_id=slip.player_id, kind='bonus_credited', title='Lost by one: refund paid',
                 body=f'Your ticket {slip.code or slip.pk} lost on just one match, so ${amount:.2f} is back in your Winnings.')
    return amount
