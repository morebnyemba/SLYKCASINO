"""Which other accounts a player is tied to, and why.

Strong links — the same mobile money / bank number used to deposit or to be
paid — mean the same person (or someone working with them) is behind both
accounts. An IP link is weak: Zimbabwean mobile carriers put many customers
behind one public IP, so on its own it only ever raises a low signal.
"""
from __future__ import annotations

import re
from collections import defaultdict

DEPOSIT_NUMBER = 'deposit number'
PAYOUT_NUMBER = 'payout number'
IP = 'IP address'
STRONG = (DEPOSIT_NUMBER, PAYOUT_NUMBER)


def normalize_number(raw: str) -> str:
    """Compare numbers by their last 9 digits: 0771 234 567, +263771234567 and
    263771234567 are the same EcoCash wallet. Bank account numbers (longer or
    shorter) are compared as their digits."""
    digits = re.sub(r'\D', '', raw or '')
    return digits[-9:] if len(digits) >= 9 else digits


def _deposit_numbers(player_ids=None):
    from apps.wallet.models import PaymentTransaction
    qs = PaymentTransaction.objects.exclude(phone='').filter(
        status__in=(PaymentTransaction.Status.PAID, PaymentTransaction.Status.PENDING))
    if player_ids is not None:
        qs = qs.filter(player_id__in=player_ids)
    return qs.values_list('player_id', 'phone')


def _payout_numbers(player_ids=None):
    from apps.wallet.models import WithdrawalRequest
    qs = WithdrawalRequest.objects.exclude(account_number='')
    if player_ids is not None:
        qs = qs.filter(player_id__in=player_ids)
    return qs.values_list('player_id', 'account_number')


def numbers_of(player_id: int) -> dict[str, set[str]]:
    return {
        DEPOSIT_NUMBER: {normalize_number(n) for _, n in _deposit_numbers([player_id])} - {''},
        PAYOUT_NUMBER: {normalize_number(n) for _, n in _payout_numbers([player_id])} - {''},
    }


def players_with_number(number: str, *, exclude: int | None = None) -> dict[int, set[str]]:
    """Every player whose deposits or payouts used this number (matched in SQL
    on the last digits, then confirmed after normalising)."""
    from apps.wallet.models import PaymentTransaction, WithdrawalRequest
    tail = normalize_number(number)
    found: dict[int, set[str]] = defaultdict(set)
    if not tail:
        return found
    deposits = PaymentTransaction.objects.filter(
        phone__endswith=tail, status__in=(PaymentTransaction.Status.PAID, PaymentTransaction.Status.PENDING))
    for pid, raw in deposits.values_list('player_id', 'phone'):
        if normalize_number(raw) == tail:
            found[pid].add(DEPOSIT_NUMBER)
    for pid, raw in WithdrawalRequest.objects.filter(account_number__endswith=tail).values_list('player_id', 'account_number'):
        if normalize_number(raw) == tail:
            found[pid].add(PAYOUT_NUMBER)
    found.pop(exclude, None)
    return found


def ips_of(player_id: int) -> set[str]:
    from apps.accounts.models import AuditLog
    return set(AuditLog.objects.filter(player_id=player_id, event_type__in=('register', 'login'))
               .exclude(ip_address=None).values_list('ip_address', flat=True).distinct())


def players_on_ips(ips, *, exclude: int | None = None, since=None) -> dict[int, set[str]]:
    from apps.accounts.models import AuditLog
    qs = AuditLog.objects.filter(ip_address__in=list(ips), event_type__in=('register', 'login')).exclude(player_id=None)
    if since is not None:
        qs = qs.filter(created_at__gte=since)
    found: dict[int, set[str]] = defaultdict(set)
    for pid in qs.values_list('player_id', flat=True).distinct():
        if pid != exclude:
            found[pid].add(IP)
    return found


def linked_accounts(player_id: int) -> dict[int, set[str]]:
    """Every other player tied to this one, with how (strongest reasons first)."""
    links: dict[int, set[str]] = defaultdict(set)
    for kind, numbers in numbers_of(player_id).items():
        for number in numbers:
            for pid, how in players_with_number(number, exclude=player_id).items():
                links[pid] |= how
    ips = ips_of(player_id)
    if ips:
        for pid, how in players_on_ips(ips, exclude=player_id).items():
            links[pid] |= how
    return dict(links)


def strongly_linked(player_id: int) -> set[int]:
    return {pid for pid, how in linked_accounts(player_id).items() if how & set(STRONG)}
