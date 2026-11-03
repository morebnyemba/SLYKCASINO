"""wallet domain logic — the ONLY place wallet mutations happen.

The ledger is append-only and every movement is keyed by a unique
`idempotency_key`. `post_entry` is the single write primitive; debit/credit are
thin wrappers. Re-posting the same key is a guaranteed no-op (get_or_create on a
UNIQUE column), which is what makes both live retries and recovery idempotent.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.db import transaction

from . import helpers, utils
from .dtos import BalanceDTO, LedgerEntryDTO
from .models import BALANCE_FIELD, Bucket, LedgerEntry, Wallet, WalletRules
from .models.ledger import FIXED_BUCKET, WITHDRAWAL_BUCKETS, WITHDRAWAL_KINDS
from .reporting import (  # noqa: F401  (read-only analytics, re-exported)
    deposit_count, earliest_entry, empty_kpis, first_deposit_amounts, first_deposits, ledger_kpis, ledger_series, player_breakdown, recent_activity,
)


class InsufficientFunds(Exception):
    """Raised when a debit would overdraw a wallet."""


class WalletRuleError(ValueError):
    """A bet or movement the wallet rules don't allow (shown to the player)."""


BETTING_BUCKETS = (Bucket.DEPOSIT, Bucket.BONUS, Bucket.WINNINGS)


def betting_bucket(value) -> str:
    """The wallet a player chose to pay a stake from. Required — money is never
    taken from a balance the player didn't pick."""
    if value not in BETTING_BUCKETS:
        raise WalletRuleError('Choose which wallet to bet from: Deposit, Bonus or Winnings.')
    return value


def check_min_odds(bucket: str, odds) -> None:
    """Refuse a ticket whose combined odds are below the wallet's minimum."""
    minimum = WalletRules.load().min_odds(bucket)
    if Decimal(str(odds)) < minimum:
        raise WalletRuleError(
            f'Bets from your {Bucket(bucket).label} wallet need combined odds of at least {minimum:.2f}.')


def check_ticket_limits(*, stake, selections: int, bucket: Optional[str] = None) -> None:
    """Refuse a sportsbook ticket outside the operator's limits: the stake
    (min_stake..max_stake, except a Bonus ticket, which must stake the whole
    Bonus wallet) and the number of selections (max_selections)."""
    rules = WalletRules.load()
    if selections > rules.max_selections:
        raise WalletRuleError(f'A ticket can have at most {rules.max_selections} selections.')
    if bucket == Bucket.BONUS:
        return
    stake = Decimal(str(stake))
    if stake < rules.min_stake:
        raise WalletRuleError(f'The minimum stake is ${rules.min_stake:.2f}.')
    if stake > rules.max_stake:
        raise WalletRuleError(f'The maximum stake is ${rules.max_stake:.2f}.')


def betting_limits() -> dict:
    """The limits every ticket must meet, for the bet slip (public)."""
    rules = WalletRules.load()
    return {'min_stake': f'{rules.min_stake:.2f}', 'max_stake': f'{rules.max_stake:.2f}',
            'max_selections': rules.max_selections}


# -- provisioning / reads ----------------------------------------------------

def ensure_wallet(player_id: int, *, currency: str = 'USD') -> Wallet:
    wallet, _ = Wallet.objects.get_or_create(
        player_id=player_id, defaults={'currency': currency},
    )
    return wallet


def get_balance(player_id: int) -> Decimal:
    wallet = Wallet.objects.filter(player_id=player_id).first()
    return utils.quantize(wallet.balance) if wallet else Decimal('0.00')


def get_currency(player_id: int) -> str:
    wallet = Wallet.objects.filter(player_id=player_id).first()
    return wallet.currency if wallet else 'USD'


def get_balance_dto(player_id: int) -> BalanceDTO:
    wallet = ensure_wallet(player_id)
    return BalanceDTO(
        player_id=player_id, balance=utils.quantize(wallet.balance), currency=wallet.currency,
        deposit=utils.quantize(wallet.deposit_balance), bonus=utils.quantize(wallet.bonus_balance),
        winnings=utils.quantize(wallet.winnings_balance),
    )


def get_balances(player_id: int) -> dict[str, Decimal]:
    """The three bucket balances (zeros when the player has no wallet yet)."""
    wallet = Wallet.objects.filter(player_id=player_id).first()
    return {b: utils.quantize(wallet.bucket_balance(b)) if wallet else Decimal('0.00') for b in Bucket.values}


# -- the single write primitive ---------------------------------------------

@transaction.atomic
def post_entry(
    *, player_id: int, amount: Decimal, kind: str,
    idempotency_key: str, reference: str = '', require_non_negative: bool = False,
    bucket: Optional[str] = None,
) -> LedgerEntry:
    """Append one signed movement on one bucket and update the cached balances —
    idempotently.

    `bucket` is required except for kinds whose bucket is fixed (deposits,
    bonuses, withdrawals, affiliate commission — see FIXED_BUCKET), and must
    match it for those; the database enforces the same rule.

    If `idempotency_key` already exists, the existing entry is returned and the
    balance is NOT touched (no double-spend / no duplicate ledger row).

    The wallet row is locked with `select_for_update()` for the lifetime of this
    transaction, so concurrent calls for the same player fully serialize. The
    funds check (when `require_non_negative`) runs on the chosen bucket alone,
    *after* acquiring that lock and *before* writing the entry, which is what
    makes it race-free and keeps one balance from ever paying for another.

    Checked once before the lock (cheap bail-out for the common idempotent
    retry) and again after acquiring it (correctness for two requests racing
    on the same key), so a retry storm doesn't serialize on row locks it
    doesn't need.
    """
    fixed = FIXED_BUCKET.get(kind)
    if bucket is None:
        bucket = fixed
    if bucket not in Bucket.values:
        raise ValueError(f'ledger entry {kind!r} needs a wallet bucket')
    if fixed is not None and bucket != fixed:
        raise ValueError(f'{kind} entries belong to the {fixed} wallet, not {bucket}')
    if kind in WITHDRAWAL_KINDS and bucket not in WITHDRAWAL_BUCKETS:
        raise ValueError(f'{kind} entries can only touch the Winnings or Deposit wallet, not {bucket}')
    existing = LedgerEntry.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        return existing
    wallet = Wallet.objects.select_for_update().get(player_id=player_id)
    existing = LedgerEntry.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        return existing  # idempotent replay: no balance change, no funds re-check
    quantized_amount = utils.quantize(amount)
    field = BALANCE_FIELD[bucket]
    projected = utils.quantize(Decimal(getattr(wallet, field)) + quantized_amount)
    if require_non_negative and projected < 0:
        raise InsufficientFunds(
            f'Not enough in your {Bucket(bucket).label} wallet — it has {getattr(wallet, field):.2f}.')
    entry = LedgerEntry.objects.create(
        wallet=wallet, idempotency_key=idempotency_key,
        amount=quantized_amount, kind=kind, bucket=bucket, reference=reference,
    )
    setattr(wallet, field, projected)
    wallet.balance = utils.quantize(Decimal(wallet.balance) + quantized_amount)
    wallet.save(update_fields=[field, 'balance', 'updated_at'])
    _after_new_entry(player_id, entry)
    return entry


def _after_new_entry(player_id: int, entry: LedgerEntry) -> None:
    """Side effects of a NEW ledger entry (never of an idempotent replay), in
    the same transaction: stakes count towards bonus wagering, and a deposit
    may earn a referred player their welcome bonus or, failing that, a running
    deposit promotion (never both on one deposit). Lazy imports keep wallet
    free of import-time dependencies on other apps."""
    if entry.kind in ('bet_stake', 'casino_debit'):
        from apps.promotions import services as promotions_services
        from apps.risk import services as risk
        promotions_services.record_wagering(player_id=player_id, amount=abs(entry.amount))
        risk.safely(risk.on_stake, player_id, amount=abs(entry.amount))
    elif entry.kind == 'bonus':
        # New bonus money starts the rollover count again (wallet.bonus).
        from . import bonus
        bonus.reset(player_id)
    elif entry.kind == 'deposit':
        from apps.affiliates import services as affiliate_services
        from apps.promotions import services as promotions_services
        from apps.risk import services as risk
        payment = _deposit_payment(entry.reference)
        # Checked first, so a deposit from another account's number blocks its bonus.
        risk.safely(risk.on_deposit, player_id, amount=entry.amount, phone=payment.phone if payment else '')
        welcomed = affiliate_services.on_deposit(player_id=player_id, amount=entry.amount)
        if payment is not None and payment.promo_code:
            # A promo code replaces the automatic deposit promotion (one bonus per deposit).
            from apps.promotions import promo_codes
            promo_codes.apply_to_deposit(player_id=player_id, code=payment.promo_code, amount=entry.amount,
                                         deposit_entry_id=entry.id)
        elif not welcomed:
            promotions_services.on_deposit(player_id=player_id, amount=entry.amount, deposit_id=entry.id)


def _deposit_payment(reference: str):
    """The payment a deposit came from ('psp:<provider>:<our reference>'), for
    its mobile number and promo code; None for other deposits."""
    from .models import PaymentTransaction
    ref = reference.rsplit(':', 1)[-1] if reference.startswith('psp:') else ''
    if not ref:
        return None
    return PaymentTransaction.objects.filter(reference=ref).first()


def debit(
    *, player_id: int, amount: Decimal, kind: str,
    idempotency_key: str, reference: str = '', allow_negative: bool = False,
    bucket: Optional[str] = None,
) -> LedgerEntry:
    """Debit a positive magnitude from one bucket. Funds are checked unless
    `allow_negative` (the database still refuses a negative bucket)."""
    magnitude = utils.quantize(abs(amount))
    return post_entry(
        player_id=player_id, amount=utils.to_debit(magnitude), kind=kind,
        idempotency_key=idempotency_key, reference=reference,
        require_non_negative=not allow_negative, bucket=bucket,
    )


def credit(
    *, player_id: int, amount: Decimal, kind: str,
    idempotency_key: str, reference: str = '', bucket: Optional[str] = None,
) -> LedgerEntry:
    return post_entry(
        player_id=player_id, amount=utils.to_credit(amount), kind=kind,
        idempotency_key=idempotency_key, reference=reference, bucket=bucket,
    )


def pay_out(
    *, player_id: int, source: str, stake: Decimal, payout: Decimal, kind: str,
    idempotency_key: str, reference: str = '',
) -> None:
    """Pay a winning (or cashed-out) ticket: the stake goes back to the wallet
    it was paid from and only the profit lands in Winnings. So deposit money can
    never become withdrawable just by being staked — it has to win. Bonus
    tickets pay everything back into the Bonus wallet (wallet.bonus: it reaches
    Winnings only through the rollover). The stake part keeps
    `idempotency_key`; the profit uses `<key>:profit`."""
    payout = utils.quantize(payout)
    if source == Bucket.BONUS:
        if payout > 0:
            credit(player_id=player_id, amount=payout, kind=kind, bucket=Bucket.BONUS,
                   idempotency_key=idempotency_key, reference=reference)
        return
    back = min(payout, utils.quantize(stake))
    profit = payout - back
    if back > 0:
        credit(player_id=player_id, amount=back, kind=kind, bucket=source,
               idempotency_key=idempotency_key, reference=reference)
    if profit > 0:
        credit(player_id=player_id, amount=profit, kind=kind, bucket=Bucket.WINNINGS,
               idempotency_key=f'{idempotency_key}:profit', reference=reference)


def recompute_balance(player_id: int) -> Decimal:
    """Authoritative balance from the ledger (used by recovery & audits)."""
    amounts = LedgerEntry.objects.filter(wallet__player_id=player_id).values_list('amount', flat=True)
    return utils.sum_entries(amounts)


def recompute_balances(player_id: int) -> dict[str, Decimal]:
    """Authoritative per-bucket balances from the ledger."""
    from django.db.models import Sum

    rows = (LedgerEntry.objects.filter(wallet__player_id=player_id)
            .values('bucket').annotate(t=Sum('amount')))
    totals = {r['bucket']: r['t'] for r in rows}
    return {b: utils.quantize(totals.get(b) or 0) for b in Bucket.values}


def totals_by_kind(
    player_ids: list[int], *, start=None, end=None,
) -> dict[int, dict[str, Decimal]]:
    """Read-only: the signed sum of each player's ledger entries per kind over
    [start, end) — e.g. for affiliate revenue reports. Players with no entries in
    the window are absent from the result."""
    from django.db.models import Sum

    if not player_ids:
        return {}
    qs = LedgerEntry.objects.filter(wallet__player_id__in=player_ids)
    if start is not None:
        qs = qs.filter(created_at__gte=start)
    if end is not None:
        qs = qs.filter(created_at__lt=end)
    totals: dict[int, dict[str, Decimal]] = {}
    for row in qs.values('wallet__player_id', 'kind').annotate(total=Sum('amount')):
        totals.setdefault(row['wallet__player_id'], {})[row['kind']] = row['total'] or Decimal('0')
    return totals


def deposits_between(player_ids: list[int], start, end, *, offset: int = 0, limit: int = 50) -> dict:
    """Read-only: these players' deposits in [start, end): the total, how
    many, how many players deposited, and one page of them newest first
    (player_id, amount, created_at)."""
    from django.db.models import Count, Sum

    qs = LedgerEntry.objects.filter(wallet__player_id__in=player_ids, kind=LedgerEntry.Kind.DEPOSIT,
                                    created_at__gte=start, created_at__lt=end)
    agg = qs.aggregate(total=Sum('amount'), n=Count('id'), players=Count('wallet__player_id', distinct=True))
    rows = list(qs.order_by('-created_at', '-pk').values('wallet__player_id', 'amount', 'created_at')[offset:offset + limit + 1])
    return {
        'total': agg['total'] or Decimal('0'), 'count': agg['n'] or 0, 'depositors': agg['players'] or 0,
        'items': [{'player_id': r['wallet__player_id'], 'amount': r['amount'], 'created_at': r['created_at']}
                  for r in rows[:limit]],
        'more': len(rows) > limit,
    }


def list_entries(player_id: int, limit: int = 50) -> list[LedgerEntryDTO]:
    rows = LedgerEntry.objects.filter(wallet__player_id=player_id)[:limit]
    return [LedgerEntryDTO.model_validate(r) for r in rows]


def deposit(
    *, player_id: int, amount: Decimal,
    idempotency_key: str, reference: str = '',
) -> LedgerEntry:
    """Credit a deposit to the wallet and notify the player."""
    entry = credit(
        player_id=player_id, amount=amount, kind='deposit',
        idempotency_key=idempotency_key, reference=reference,
    )
    # Lazy import to avoid circular dependency (notifications -> wallet is not needed).
    from apps.notifications import services as notif_services
    notif_services.notify(
        player_id=player_id,
        kind='deposit_confirmed',
        title='Deposit confirmed',
        body=f'{utils.quantize(amount)} credited to your wallet.',
    )
    return entry


def withdrawal(
    *, player_id: int, amount: Decimal,
    idempotency_key: str, reference: str = '',
) -> LedgerEntry:
    """Debit a withdrawal from the wallet and notify the player."""
    entry = debit(
        player_id=player_id, amount=amount, kind='withdrawal', bucket='winnings',
        idempotency_key=idempotency_key, reference=reference,
    )
    from apps.notifications import services as notif_services
    notif_services.notify(
        player_id=player_id,
        kind='withdrawal_processed',
        title='Withdrawal processed',
        body=f'{utils.quantize(amount)} has been withdrawn from your wallet.',
    )
    return entry


@transaction.atomic
def erase_player_data(player_id: int) -> int:
    """Permanently delete a player's wallet, every ledger entry and payment
    record (account deletion). Returns rows deleted."""
    from django.db import connection

    from .models import PaymentTransaction, WithdrawalRequest
    if connection.vendor == 'postgresql':
        # The ledger is append-only; permanent deletion is the one sanctioned
        # exception, opted into for this transaction only.
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL wallet.allow_ledger_delete = 'on'")
    deleted = PaymentTransaction.objects.filter(player_id=player_id).delete()[0]
    deleted += WithdrawalRequest.objects.filter(player_id=player_id).delete()[0]
    deleted += Wallet.objects.filter(player_id=player_id).delete()[0]  # cascades to ledger entries
    return deleted
