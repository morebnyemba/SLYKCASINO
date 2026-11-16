"""The Bonus wallet's rules, enforced here for every bet and settlement.

- Sportsbook, plus Aviator as fixed `bonus_aviator_stake` ($0.10) bets that pay
  the profit only into a claimable pot (claimed to Deposit, or to Winnings
  within the unlock limit). Never other casino games.
- A bonus ticket stakes the whole Bonus wallet (100% of it) on one multiple of
  at least `bonus_min_legs` selections (10), each priced at least
  `bonus_min_leg_odds` (1.50). No singles, no cash-out.
- A winning bonus ticket pays back into the Bonus wallet, not Winnings.
- After `bonus_wins_to_convert` (2) full-stake bonus tickets win in a row, the
  Bonus wallet moves to Winnings — up to the lower of `bonus_max_conversion`
  ($500) and `bonus_conversion_multiple` (5×) the bonus given in this cycle;
  the rest is forfeited. A losing bonus ticket, or a new bonus credit, starts
  the count again.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Iterable

from django.db import transaction
from django.utils import timezone

from . import services, utils
from .models import BonusRollover, Bucket, WalletRules


def check_ticket(player_id: int, *, stake, leg_odds: Iterable, is_multiple: bool) -> None:
    """Refuse a bonus ticket that breaks the rules (WalletRuleError, shown to the player)."""
    rules = WalletRules.load()
    odds = [Decimal(str(o)) for o in leg_odds]
    if not is_multiple or len(odds) < rules.bonus_min_legs:
        raise services.WalletRuleError(
            f'Bonus bets must be one multiple of at least {rules.bonus_min_legs} selections.')
    low = [o for o in odds if o < rules.bonus_min_leg_odds]
    if low:
        raise services.WalletRuleError(
            f'Every selection on a bonus bet needs odds of at least {rules.bonus_min_leg_odds:.2f} '
            f'({len(low)} on this ticket don’t).')
    balance = services.get_balances(player_id)[Bucket.BONUS]
    if balance <= 0:
        raise services.WalletRuleError('Your Bonus wallet is empty.')
    if utils.quantize(stake) != balance:
        raise services.WalletRuleError(
            f'A bonus bet stakes your whole Bonus wallet: ${balance:.2f}.')


def not_for_games(wallet) -> None:
    """Casino games can't be played with bonus money (Aviator has its own
    bonus bets: see aviator_stake)."""
    if wallet == Bucket.BONUS:
        raise services.WalletRuleError('Bonus money can only be used on sports bets and Aviator bonus bets.')


# -- Aviator bonus bets ---------------------------------------------------------

def aviator_stake(rules: WalletRules | None = None) -> Decimal:
    """What one Aviator bonus bet stakes from the Bonus wallet (0 = not allowed)."""
    return (rules or WalletRules.load()).bonus_aviator_stake


def add_aviator_profit(player_id: int, amount) -> None:
    """A cashed-out Aviator bonus bet's profit goes into the player's claimable pot."""
    from django.db.models import F
    amount = utils.quantize(amount)
    if amount <= 0:
        return
    BonusRollover.objects.get_or_create(player_id=player_id)
    BonusRollover.objects.filter(player_id=player_id).update(aviator_profit=F('aviator_profit') + amount)


def winnings_room(player_id: int, rules: WalletRules | None = None) -> Decimal | None:
    """How much more bonus profit may go to Winnings: the unlock multiple times
    all the bonus ever given, less everything bonus play ever moved to Winnings
    (conversions and earlier claims). None = no multiple set (no limit beyond
    the per-claim cap)."""
    from django.db.models import Sum
    from .models import LedgerEntry
    rules = rules or WalletRules.load()
    if rules.bonus_conversion_multiple <= 0:
        return None
    entries = LedgerEntry.objects.filter(wallet__player_id=player_id)
    given = entries.filter(kind='bonus', bucket=Bucket.BONUS, amount__gt=0).aggregate(t=Sum('amount'))['t'] or Decimal('0')
    moved = (entries.filter(kind__in=('bonus_conversion', 'bonus_profit'), bucket=Bucket.WINNINGS)
             .aggregate(t=Sum('amount'))['t'] or Decimal('0'))
    return max(utils.quantize(given * rules.bonus_conversion_multiple) - moved, Decimal('0.00'))


def aviator_status(player_id: int) -> dict:
    rules = WalletRules.load()
    profit = BonusRollover.objects.filter(player_id=player_id).values_list('aviator_profit', flat=True).first() or Decimal('0')
    room = winnings_room(player_id, rules)
    to_winnings = min(profit, rules.bonus_max_conversion, room if room is not None else profit)
    return {'stake': str(rules.bonus_aviator_stake), 'profit': str(utils.quantize(profit)),
            'max_to_winnings': str(utils.quantize(max(to_winnings, Decimal('0'))))}


@transaction.atomic
def claim_aviator_profit(player_id: int, *, amount=None, to: str) -> dict:
    """Move Aviator bonus profit from the pot into Deposit (any amount) or
    Winnings (at most the per-claim cap and what's left of the unlock limit).
    `amount` None = as much as allowed. Raises WalletRuleError."""
    import uuid
    if to not in (Bucket.DEPOSIT, Bucket.WINNINGS):
        raise services.WalletRuleError('Claim to your Deposit or Winnings wallet.')
    rules = WalletRules.load()
    row = BonusRollover.objects.select_for_update().filter(player_id=player_id).first()
    pot = row.aviator_profit if row else Decimal('0')
    if pot <= 0:
        raise services.WalletRuleError('You have no Aviator bonus profit to claim.')
    limit = pot
    if to == Bucket.WINNINGS:
        room = winnings_room(player_id, rules)
        limit = min(pot, rules.bonus_max_conversion, room if room is not None else pot)
        if limit <= 0:
            raise services.WalletRuleError('You’ve reached the bonus limit for Winnings — claim to your Deposit wallet instead.')
    want = limit if amount in (None, '') else utils.quantize(amount)
    if want <= 0:
        raise services.WalletRuleError('Enter an amount to claim.')
    if want > limit:
        raise services.WalletRuleError(f'You can claim up to ${limit:.2f} to your {Bucket(to).label} wallet.')
    row.aviator_profit = pot - want
    row.save(update_fields=['aviator_profit', 'updated_at'])
    services.post_entry(player_id=player_id, amount=want, kind='bonus_profit', bucket=to,
                        idempotency_key=f'bonus-profit:{player_id}:{uuid.uuid4().hex}', reference='aviator-bonus-profit')
    return {'claimed': str(want), 'to': to, **aviator_status(player_id)}


def conversion_cap(rules: WalletRules, credited) -> Decimal:
    """The most that can move to Winnings: the fixed cap, and — when a multiple
    is set and the bonus given is known — that many times the bonus given."""
    cap = rules.bonus_max_conversion
    credited = Decimal(str(credited or 0))
    if rules.bonus_conversion_multiple > 0 and credited > 0:
        cap = min(cap, utils.quantize(credited * rules.bonus_conversion_multiple))
    return cap


def progress(player_id: int) -> dict:
    rules = WalletRules.load()
    row = BonusRollover.objects.filter(player_id=player_id).values('wins', 'credited').first() or {}
    return {'wins': row.get('wins', 0), 'wins_needed': rules.bonus_wins_to_convert,
            # This player's own limit (the fixed cap, or N× the bonus they were given if lower).
            'max_conversion': str(conversion_cap(rules, row.get('credited'))),
            'conversion_multiple': str(rules.bonus_conversion_multiple),
            'aviator': aviator_status(player_id),
            'min_legs': rules.bonus_min_legs, 'min_leg_odds': str(rules.bonus_min_leg_odds)}


# -- expiry -------------------------------------------------------------------------

BONUS_USE_KINDS = ('bonus', 'bet_stake', 'bet_payout', 'bonus_conversion', 'casino_debit', 'casino_credit')
EXPIRY_WARNING = timedelta(hours=24)
MIN_EXPIRY_HOURS, MAX_EXPIRY_HOURS = 24, 15 * 24


def last_use(player_id: int):
    """When the Bonus wallet was last used: a bonus credited, or a bet from or win into it."""
    from .models import LedgerEntry
    return (LedgerEntry.objects.filter(wallet__player_id=player_id, bucket=Bucket.BONUS, kind__in=BONUS_USE_KINDS)
            .order_by('-created_at').values_list('created_at', flat=True).first())


def _open_bonus_ticket(player_id: int) -> bool:
    from apps.sportsbook.models import Bet, BetSlip
    live = ('pending', 'open', 'accepting')
    return (Bet.objects.filter(player_id=player_id, wallet='bonus', status__in=live).exists()
            or BetSlip.objects.filter(player_id=player_id, wallet='bonus', status__in=live).exists())


def _countdown_start(player_id: int, rules: WalletRules):
    """The later of the last use and the day expiry was introduced (None: never used)."""
    used = last_use(player_id)
    if used is None:
        return None
    return max(used, rules.bonus_expiry_from) if rules.bonus_expiry_from else used


def expiry_period(hours: int) -> str:
    """"72 hours", "5 days" — for messages."""
    return f'{hours // 24} days' if hours > 72 and hours % 24 == 0 else f'{hours} hours'


def expires_at(player_id: int):
    """When an unused Bonus balance will expire (ISO), or None (empty, or a bonus ticket is open)."""
    rules = WalletRules.load()
    if services.get_balances(player_id)[Bucket.BONUS] <= 0 or _open_bonus_ticket(player_id):
        return None
    start = _countdown_start(player_id, rules)
    return (start + timedelta(hours=rules.bonus_expiry_hours)).isoformat() if start else None


def expire_idle(*, now=None) -> dict:
    """Hourly: forfeit every Bonus wallet unused for `bonus_expiry_hours` (72 by
    default, 15 days at most), and warn players 24 hours before. A bonus ticket
    still open keeps the wallet alive. Keyed per idle stretch, so a run that
    overlaps another never forfeits twice and a player who uses the bonus again
    starts a fresh countdown."""
    from apps.notifications import services as notif_services
    from apps.notifications.models import Notification

    from .models import Wallet
    now = now or timezone.now()
    rules = WalletRules.load()
    hours = rules.bonus_expiry_hours
    window = timedelta(hours=hours)
    report = {'expired': 0, 'amount': Decimal('0.00'), 'warned': 0}
    for player_id, balance in Wallet.objects.filter(bonus_balance__gt=0).values_list('player_id', 'bonus_balance'):
        start = _countdown_start(player_id, rules)
        if start is None or _open_bonus_ticket(player_id):
            continue
        expiry = start + window
        if now >= expiry:
            try:
                with transaction.atomic():
                    amount = services.get_balances(player_id)[Bucket.BONUS]
                    if amount <= 0:
                        continue
                    services.post_entry(player_id=player_id, amount=-amount, kind='bonus_forfeit', bucket=Bucket.BONUS,
                                        idempotency_key=f'bonus-expiry:{player_id}:{int(start.timestamp())}',
                                        reference='bonus-expired', require_non_negative=True)
                    reset(player_id, cleared=True)
            except services.InsufficientFunds:
                continue
            notif_services.notify(player_id=player_id, kind='account_alert', title='Bonus expired',
                                  body=f'Your ${amount:.2f} bonus expired after {expiry_period(hours)} without use.')
            report['expired'] += 1
            report['amount'] += amount
        elif hours >= 48 and now >= expiry - EXPIRY_WARNING:
            if Notification.objects.filter(player_id=player_id, title='Bonus expiring soon', created_at__gte=start).exists():
                continue
            notif_services.notify(player_id=player_id, kind='promo_expiring', title='Bonus expiring soon',
                                  body=f'Your ${balance:.2f} bonus expires {timezone.localtime(expiry):%d %b at %H:%M} if you don’t use it. '
                                       'Bet it on the sportsbook to keep it.')
            report['warned'] += 1
    return report


def reset(player_id: int, *, cleared: bool = False) -> None:
    """Start the win count again; `cleared` = the Bonus wallet was emptied
    (expired), so no bonus is left in this cycle either."""
    if cleared:
        BonusRollover.objects.filter(player_id=player_id).update(wins=0, credited=Decimal('0.00'))
    else:
        BonusRollover.objects.filter(player_id=player_id).update(wins=0)


@transaction.atomic
def credited(player_id: int, amount) -> None:
    """New bonus money: it starts the win count again and adds to the bonus
    given in this cycle (the base for the conversion cap)."""
    row, _ = BonusRollover.objects.select_for_update().get_or_create(player_id=player_id)
    row.wins = 0
    row.credited = max(row.credited + utils.quantize(amount), Decimal('0.00'))
    row.save(update_fields=['wins', 'credited', 'updated_at'])


@transaction.atomic
def ticket_settled(player_id: int, *, won: bool, ticket: str) -> None:
    """Count a settled bonus ticket. A win towards the rollover; a loss starts
    it again. Enough wins in a row convert the Bonus wallet to Winnings."""
    row, _ = BonusRollover.objects.select_for_update().get_or_create(player_id=player_id)
    if not won:
        # The ticket staked the whole Bonus wallet, so whatever is in it now was
        # credited after the bet — that's all the bonus left in this cycle.
        row.wins = 0
        row.credited = services.get_balances(player_id)[Bucket.BONUS]
        row.save(update_fields=['wins', 'credited', 'updated_at'])
        return
    row.wins += 1
    rules = WalletRules.load()
    if row.wins < rules.bonus_wins_to_convert:
        row.save(update_fields=['wins', 'updated_at'])
        return
    cap = conversion_cap(rules, row.credited)
    row.wins = 0
    row.credited = Decimal('0.00')          # the whole Bonus wallet converts or is forfeited
    row.save(update_fields=['wins', 'credited', 'updated_at'])
    _convert(player_id, rules, ticket=ticket, cap=cap)


def _convert(player_id: int, rules: WalletRules, *, ticket: str, cap: Decimal) -> None:
    balance = services.get_balances(player_id)[Bucket.BONUS]
    if balance <= 0:
        return
    converted = min(balance, cap)
    forfeited = balance - converted
    key = f'bonus-conversion:{ticket}'
    services.post_entry(player_id=player_id, amount=-converted, kind='bonus_conversion', bucket=Bucket.BONUS,
                        idempotency_key=f'{key}:out', reference=ticket, require_non_negative=True)
    services.post_entry(player_id=player_id, amount=converted, kind='bonus_conversion', bucket=Bucket.WINNINGS,
                        idempotency_key=f'{key}:in', reference=ticket)
    if forfeited > 0:
        services.post_entry(player_id=player_id, amount=-forfeited, kind='bonus_forfeit', bucket=Bucket.BONUS,
                            idempotency_key=f'{key}:forfeit', reference=ticket, require_non_negative=True)
    from apps.notifications import services as notif_services
    notif_services.notify(
        player_id=player_id, kind='bonus_credited', title='Bonus unlocked',
        body=(f'${converted:.2f} of bonus winnings moved to your Winnings wallet — it’s yours to withdraw.'
              + (f' ${forfeited:.2f} above your ${cap:.2f} limit was forfeited.' if forfeited else '')),
    )
