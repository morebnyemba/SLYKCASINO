"""Gateway deposits: start a Paynow payment, then credit the wallet exactly
once when Paynow reports it paid — from the result callback, the player's
status poll, or the background sweep, whichever sees it first."""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import paynow, services
from .models import PaymentMethod, PaymentTransaction

logger = logging.getLogger(__name__)

# Unpaid mobile prompts expire on the phone within minutes; give up after a day.
EXPIRE_AFTER = timedelta(hours=24)
# Don't hit Paynow more often than this per transaction from player polls.
POLL_EVERY = timedelta(seconds=4)


def gateway_enabled() -> bool:
    return getattr(settings, 'PSP_PROVIDER', 'stub') == 'paynow'


def gateway_supports(code: str) -> bool:
    """Whether the live gateway can take this method. The stub test processor
    takes anything; Paynow takes its own methods only."""
    return code in paynow.METHODS if gateway_enabled() else True


def offered_methods() -> list[PaymentMethod]:
    """Deposit methods to show players: switched on in the admin and
    processable by the live gateway, in the admin's order."""
    return [m for m in PaymentMethod.objects.filter(deposit_enabled=True) if gateway_supports(m.code)]


def deposit_methods() -> list[str]:
    return [m.code for m in offered_methods()]


def check_deposit(method: str, amount: Decimal) -> None:
    """Raise ValueError unless `method` is offered and `amount` is within its
    limits. A blank method is allowed on the stub processor only (older
    clients credit without choosing one)."""
    if not method and not gateway_enabled():
        return
    pm = next((m for m in offered_methods() if m.code == method), None)
    if pm is None:
        raise ValueError('That payment method is not available.')
    if amount < pm.min_deposit:
        raise ValueError(f'The minimum {pm.name} deposit is ${pm.min_deposit:.2f}.')
    if pm.max_deposit is not None and amount > pm.max_deposit:
        raise ValueError(f'The maximum {pm.name} deposit is ${pm.max_deposit:.2f}.')


def start_deposit(*, player_id: int, amount: Decimal, method: str, phone: str = '', currency: str = 'USD') -> PaymentTransaction:
    """Create a pending transaction and ask Paynow to collect it. Raises
    ValueError for bad input and paynow.PaynowError if Paynow refuses."""
    if method not in paynow.METHODS:
        raise ValueError('That payment method is not available.')
    if method in paynow.MOBILE_METHODS:
        phone = paynow.normalise_phone(phone)
    else:
        phone = ''
    txn = PaymentTransaction.objects.create(
        reference=f'DEP{uuid.uuid4().hex[:16].upper()}', player_id=player_id, provider='paynow',
        method=method, phone=phone, amount=amount, currency=currency,
    )
    try:
        started = paynow.initiate(reference=txn.reference, amount=amount, method=method, phone=phone)
    except paynow.PaynowError as exc:
        txn.status = PaymentTransaction.Status.FAILED
        txn.note = str(exc)[:255]
        txn.completed_at = timezone.now()
        txn.save(update_fields=['status', 'note', 'completed_at', 'updated_at'])
        raise
    txn.poll_url = started.poll_url
    txn.provider_ref = started.provider_ref
    txn.redirect_url = started.redirect_url
    txn.instructions = started.instructions
    txn.save(update_fields=['poll_url', 'provider_ref', 'redirect_url', 'instructions', 'updated_at'])
    return txn


@transaction.atomic
def apply_status(reference: str, fields: dict[str, str]) -> PaymentTransaction | None:
    """Apply a hash-verified Paynow status message to its transaction. Paid
    credits the wallet once (idempotency-keyed on our reference), and only if
    Paynow's amount matches what we asked for."""
    txn = PaymentTransaction.objects.select_for_update().filter(reference=reference).first()
    if txn is None:
        return None
    if txn.status != PaymentTransaction.Status.PENDING:
        return txn  # already final: a redelivered callback is a no-op

    provider_status = fields.get('status', '')
    result = paynow.outcome(provider_status)
    txn.provider_status = provider_status[:40]
    if fields.get('paynowreference'):
        txn.provider_ref = fields['paynowreference'][:64]
    if fields.get('pollurl'):
        txn.poll_url = fields['pollurl'][:500]

    if result == 'paid':
        try:
            paid = Decimal(fields.get('amount', ''))
        except Exception:  # noqa: BLE001
            paid = None
        if paid is None or paid != txn.amount:
            logger.error('paynow amount mismatch on %s: expected %s, got %r', txn.reference, txn.amount, fields.get('amount'))
            txn.status = PaymentTransaction.Status.FAILED
            txn.note = f'Amount mismatch: Paynow reported {fields.get("amount")!r}'[:255]
        else:
            services.deposit(
                player_id=txn.player_id, amount=txn.amount,
                idempotency_key=f'wallet:deposit:paynow:{txn.reference}',
                reference=f'psp:paynow:{txn.reference}',
            )
            txn.status = PaymentTransaction.Status.PAID
    elif result in ('failed', 'cancelled'):
        txn.status = result
    if txn.status != PaymentTransaction.Status.PENDING:
        txn.completed_at = timezone.now()
    txn.save()
    return txn


def handle_result(body: bytes) -> PaymentTransaction | None:
    """Paynow's result callback (raises paynow.PaynowError if unsigned/forged)."""
    fields = paynow.parse_signed(body, paynow.get_config().integration_key)
    return apply_status(fields.get('reference', ''), fields)


def refresh(txn: PaymentTransaction, *, force: bool = False) -> PaymentTransaction:
    """Ask Paynow for a pending transaction's status and apply it."""
    if txn.status != PaymentTransaction.Status.PENDING or not txn.poll_url:
        return txn
    if not force and timezone.now() - txn.updated_at < POLL_EVERY:
        return txn
    try:
        fields = paynow.poll(txn.poll_url)
    except paynow.PaynowError as exc:
        logger.warning('paynow poll failed for %s: %s', txn.reference, exc)
        PaymentTransaction.objects.filter(pk=txn.pk).update(updated_at=timezone.now())
        return txn
    # Our reference is authoritative; the poll URL belongs to this transaction.
    return apply_status(txn.reference, fields) or txn


def sweep_pending(*, now=None) -> int:
    """Background pass: poll pending payments (a closed tab or a missed
    callback must not lose a deposit) and expire abandoned ones."""
    now = now or timezone.now()
    done = 0
    for txn in PaymentTransaction.objects.filter(status=PaymentTransaction.Status.PENDING):
        if now - txn.created_at > EXPIRE_AFTER:
            txn = refresh(txn, force=True)
            if txn.status == PaymentTransaction.Status.PENDING:
                PaymentTransaction.objects.filter(pk=txn.pk, status=PaymentTransaction.Status.PENDING).update(
                    status=PaymentTransaction.Status.CANCELLED, note='Expired unpaid', completed_at=now,
                )
            done += 1
        elif refresh(txn, force=True).status != PaymentTransaction.Status.PENDING:
            done += 1
    return done
