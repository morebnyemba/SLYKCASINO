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
from .models import LedgerEntry, Wallet
from .reporting import (  # noqa: F401  (read-only analytics, re-exported)
    deposit_count, earliest_entry, empty_kpis, first_deposit_amounts, first_deposits, ledger_kpis, ledger_series, player_breakdown, recent_activity,
)


class InsufficientFunds(Exception):
    """Raised when a debit would overdraw a wallet."""


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
    return BalanceDTO(player_id=player_id, balance=utils.quantize(wallet.balance), currency=wallet.currency)


# -- the single write primitive ---------------------------------------------

@transaction.atomic
def post_entry(
    *, player_id: int, amount: Decimal, kind: str,
    idempotency_key: str, reference: str = '', require_non_negative: bool = False,
) -> LedgerEntry:
    """Append one signed movement and update the cached balance — idempotently.

    If `idempotency_key` already exists, the existing entry is returned and the
    balance is NOT touched (no double-spend / no duplicate ledger row).

    The wallet row is locked with `select_for_update()` for the lifetime of this
    transaction, so concurrent calls for the same player fully serialize. The
    funds check (when `require_non_negative`) happens *after* acquiring that
    lock and *before* writing the entry, which is what makes it race-free: two
    concurrent debits against the same balance can no longer both pass the
    check (previously the check ran outside the lock — see InsufficientFunds).

    Checked once before the lock (cheap bail-out for the common idempotent
    retry) and again after acquiring it (correctness for two requests racing
    on the same key), so a retry storm doesn't serialize on row locks it
    doesn't need.
    """
    existing = LedgerEntry.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        return existing
    wallet = Wallet.objects.select_for_update().get(player_id=player_id)
    existing = LedgerEntry.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        return existing  # idempotent replay: no balance change, no funds re-check
    quantized_amount = utils.quantize(amount)
    if require_non_negative:
        projected = utils.quantize(Decimal(wallet.balance) + quantized_amount)
        if projected < 0:
            raise InsufficientFunds(f'player {player_id} cannot be debited {abs(quantized_amount)}')
    entry = LedgerEntry.objects.create(
        wallet=wallet, idempotency_key=idempotency_key,
        amount=quantized_amount, kind=kind, reference=reference,
    )
    wallet.balance = utils.quantize(Decimal(wallet.balance) + quantized_amount)
    wallet.save(update_fields=['balance', 'updated_at'])
    _after_new_entry(player_id, entry)
    return entry


def _after_new_entry(player_id: int, entry: LedgerEntry) -> None:
    """Side effects of a NEW ledger entry (never of an idempotent replay), in
    the same transaction: stakes count towards bonus wagering, and a deposit
    may earn a referred player their welcome bonus. Lazy imports keep wallet
    free of import-time dependencies on other apps."""
    if entry.kind in ('bet_stake', 'casino_debit'):
        from apps.promotions import services as promotions_services
        promotions_services.record_wagering(player_id=player_id, amount=abs(entry.amount))
    elif entry.kind == 'deposit':
        from apps.affiliates import services as affiliate_services
        affiliate_services.on_deposit(player_id=player_id, amount=entry.amount)


def debit(
    *, player_id: int, amount: Decimal, kind: str,
    idempotency_key: str, reference: str = '', allow_negative: bool = False,
) -> LedgerEntry:
    """Debit a positive magnitude. Funds are checked unless `allow_negative`."""
    magnitude = utils.quantize(abs(amount))
    return post_entry(
        player_id=player_id, amount=utils.to_debit(magnitude), kind=kind,
        idempotency_key=idempotency_key, reference=reference,
        require_non_negative=not allow_negative,
    )


def credit(
    *, player_id: int, amount: Decimal, kind: str,
    idempotency_key: str, reference: str = '',
) -> LedgerEntry:
    return post_entry(
        player_id=player_id, amount=utils.to_credit(amount), kind=kind,
        idempotency_key=idempotency_key, reference=reference,
    )


def recompute_balance(player_id: int) -> Decimal:
    """Authoritative balance from the ledger (used by recovery & audits)."""
    amounts = LedgerEntry.objects.filter(wallet__player_id=player_id).values_list('amount', flat=True)
    return utils.sum_entries(amounts)


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
        player_id=player_id, amount=amount, kind='withdrawal',
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


def erase_player_data(player_id: int) -> int:
    """Permanently delete a player's wallet, every ledger entry and payment
    record (account deletion). Returns rows deleted."""
    from .models import PaymentTransaction
    deleted = PaymentTransaction.objects.filter(player_id=player_id).delete()[0]
    deleted += Wallet.objects.filter(player_id=player_id).delete()[0]  # cascades to ledger entries
    return deleted
