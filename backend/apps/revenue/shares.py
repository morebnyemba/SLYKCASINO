"""Shares of the partner pool (30% of each day's GGR by default).

Each wallet holds its own `percent`; whatever no wallet holds goes to the
operating pool until it's sold. Rules:

* Selling (out of the unheld part) and raising a share: a superuser, at once.
  An approved buyer can ask to buy; it counts once an admin confirms the
  payment (payment happens outside the site).
* Cutting someone's share, or handing their wallet to someone else: only with
  that holder's consent — applied at once when they ask for it themselves or
  the wallet has no holder, otherwise held until they approve.
* Price: `price_per_percent` below, from the last 30 closed days.

Every step is written to the audit log.
"""
from __future__ import annotations

import statistics
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.accounts import services as accounts_services

from .models import RevenueDay, RevenueSettings, ShareBuyer, ShareChange, ShareSale, ShareWallet
from .services import RevenueError

CENT = Decimal('0.01')
ZERO = Decimal('0')
WINDOW_DAYS = 30
MIN_DAYS = 14                      # fewer closed days than this: no formula price yet
MIN_FACTOR = Decimal('0.60')       # the steadiness adjustment never takes off more than 40%
REQUEST_DAYS = 7                   # a buyer's request (and its price) holds this long


def _pct(value, field='share') -> Decimal:
    try:
        pct = Decimal(str(value)).quantize(CENT)
    except (ArithmeticError, ValueError) as exc:
        raise RevenueError(f'Enter the {field} as a percentage, e.g. 2.5.') from exc
    if pct < 0 or pct > 100:
        raise RevenueError(f'The {field} must be between 0% and 100%.')
    return pct


def held_percent(*, exclude: Optional[ShareWallet] = None) -> Decimal:
    qs = ShareWallet.objects.all()
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return sum((w.percent for w in qs), ZERO)


def unsold_percent() -> Decimal:
    return max(RevenueSettings.load().partner_pool_percent - held_percent(), ZERO)


# -- price -------------------------------------------------------------------------

def price_per_percent(*, months: Optional[int] = None, today=None) -> dict:
    """What 1% of the partner pool costs, from the last 30 closed days:

        monthly earnings of 1%  = (sum of the days' shared base ÷ days × 30) × 1%
        steadiness factor       = 1 − ¼ × min(volatility, 1) − ½ × losing-day share,
                                  never below 0.60
        price of 1%             = monthly earnings × months (12) × steadiness factor

    `base` is the real-money GGR each day actually shared (after carried losses),
    volatility is the days' standard deviation ÷ their mean, and a losing day is
    one whose GGR was zero or below. Steady, always-winning days price at the
    full 12 months; jumpy or losing stretches cost less, because the buyer's
    income is less certain. No price with fewer than 14 days or no earnings —
    an admin then sets the price when recording a sale."""
    cfg = RevenueSettings.load()
    months = months or cfg.price_months
    days = list(RevenueDay.objects.order_by('-day')[:WINDOW_DAYS])
    out = {'days': len(days), 'months': months, 'window': WINDOW_DAYS, 'price_per_percent': None,
           'monthly_per_percent': None, 'factor': None, 'volatility': None, 'losing_days': None,
           'base_total': None, 'from': days[-1].day.isoformat() if days else None,
           'to': days[0].day.isoformat() if days else None, 'reason': ''}
    if len(days) < MIN_DAYS:
        out['reason'] = f'Needs at least {MIN_DAYS} closed days ({len(days)} so far) — set the price yourself.'
        return out
    bases = [d.base for d in days]
    total = sum(bases, ZERO)
    mean = total / len(days)
    losing = sum(1 for d in days if d.ggr <= 0)
    out.update(base_total=str(total.quantize(CENT)), losing_days=losing)
    if mean <= 0:
        out['reason'] = 'The last 30 days earned nothing to share — set the price yourself.'
        return out
    volatility = Decimal(str(statistics.pstdev([float(b) for b in bases]))) / mean
    factor = max(MIN_FACTOR, Decimal('1') - Decimal('0.25') * min(volatility, Decimal('1'))
                 - Decimal('0.5') * Decimal(losing) / Decimal(len(days)))
    monthly = mean * Decimal(WINDOW_DAYS) / Decimal('100')
    price = (monthly * Decimal(months) * factor).quantize(CENT, rounding=ROUND_HALF_UP)
    out.update(price_per_percent=str(price), monthly_per_percent=str(monthly.quantize(CENT)),
               factor=str(factor.quantize(Decimal('0.001'))), volatility=str(volatility.quantize(Decimal('0.001'))))
    return out


def quote(percent) -> dict:
    pct = _pct(percent)
    q = price_per_percent()
    total = (Decimal(q['price_per_percent']) * pct).quantize(CENT) if q['price_per_percent'] else None
    return {**q, 'percent': str(pct), 'total': str(total) if total is not None else None,
            'unsold_percent': str(unsold_percent())}


# -- wallets -----------------------------------------------------------------------

def _wallet_for(user) -> ShareWallet:
    """The buyer's wallet, or a new one in the next free slot."""
    wallet = ShareWallet.objects.select_for_update().filter(holder=user).first()
    if wallet is not None:
        return wallet
    ShareWallet.ensure()
    empty = ShareWallet.objects.select_for_update().filter(holder__isnull=True, percent=0).order_by('slot').first()
    if empty is not None:
        empty.holder = user
        empty.label = empty.label if empty.slot > 3 and empty.label else user.get_username()
        empty.save(update_fields=['holder', 'label'])
        return empty
    slot = (ShareWallet.objects.order_by('-slot').values_list('slot', flat=True).first() or 0) + 1
    return ShareWallet.objects.create(slot=slot, holder=user, label=user.get_username())


def _staff(user_id):
    user = get_user_model().objects.filter(pk=user_id, is_staff=True, is_active=True).first()
    if user is None:
        raise RevenueError('Shares can only be held by an active staff login.')
    return user


def _room_for(pct: Decimal, *, wallet: Optional[ShareWallet] = None) -> None:
    cap = RevenueSettings.load().partner_pool_percent
    others = held_percent(exclude=wallet)
    current = wallet.percent if wallet is not None else ZERO
    if others + current + pct > cap:
        raise RevenueError(f'Only {max(cap - others - current, ZERO):.2f}% of the {cap:.2f}% partner pool is unsold.')


def set_share(*, slot: int, percent, by_user, reason: str = '', request=None) -> dict:
    """Set one wallet's share. A raise comes out of the unsold part (superuser);
    a cut needs the holder's consent (see module docstring)."""
    from .audit import assert_unlocked
    assert_unlocked()
    new = _pct(percent)
    with transaction.atomic():
        RevenueSettings.objects.select_for_update().get(pk=RevenueSettings.load().pk)
        wallet = ShareWallet.objects.select_for_update(of=('self',)).select_related('holder').filter(slot=slot).first()
        if wallet is None:
            raise RevenueError('Unknown wallet.')
        old = wallet.percent
        if new == old:
            return {'applied': True, 'change': None}
        if new > old:
            if not by_user.is_superuser:
                raise RevenueError('Only a superuser can raise a share.')
            _room_for(new - old, wallet=wallet)
            wallet.percent = new
            wallet.save(update_fields=['percent'])
            accounts_services.audit(None, 'share_raised', request, slot=slot, holder=_name(wallet.holder),
                                    from_percent=str(old), to_percent=str(new), by=by_user.get_username(), reason=reason)
            return {'applied': True, 'change': None}
        return _cut(wallet, to_percent=new, new_holder=None, by_user=by_user, reason=reason, request=request)


def transfer_wallet(*, slot: int, new_holder_id, by_user, reason: str = '', request=None) -> dict:
    """Hand a wallet (its share and future earnings) to another staff login —
    the current holder's consent is needed, as for a cut."""
    from .audit import assert_unlocked
    assert_unlocked()
    with transaction.atomic():
        wallet = ShareWallet.objects.select_for_update(of=('self',)).select_related('holder').filter(slot=slot).first()
        if wallet is None:
            raise RevenueError('Unknown wallet.')
        user = _staff(new_holder_id)
        if wallet.holder_id == user.pk:
            return {'applied': True, 'change': None}
        clash = ShareWallet.objects.filter(holder=user).exclude(pk=wallet.pk).first()
        if clash is not None:
            raise RevenueError(f'{user.get_username()} already holds wallet {clash.slot} — change its share instead.')
        return _cut(wallet, to_percent=wallet.percent, new_holder=user, by_user=by_user, reason=reason, request=request)


def _name(user) -> Optional[str]:
    return user.get_username() if user else None


def _cut(wallet: ShareWallet, *, to_percent: Decimal, new_holder, by_user, reason: str, request) -> dict:
    holder = wallet.holder
    own = holder is not None and holder.pk == by_user.pk
    if not (own or by_user.is_superuser):
        raise RevenueError('Only the holder or a superuser can change this share.')
    if new_holder is not None and not by_user.is_superuser:
        raise RevenueError('Only a superuser can hand a wallet to someone else.')
    change = ShareChange.objects.create(
        wallet=wallet, holder=holder, from_percent=wallet.percent, to_percent=to_percent, new_holder=new_holder,
        reason=(reason or '').strip()[:500], requested_by=by_user.get_username(),
    )
    accounts_services.audit(None, 'share_change_requested', request, id=change.id, slot=wallet.slot, holder=_name(holder),
                            from_percent=str(change.from_percent), to_percent=str(to_percent),
                            new_holder=_name(new_holder), by=by_user.get_username(), reason=change.reason)
    if own or holder is None:
        _apply(change, note='Asked for by the holder' if own else 'Wallet had no holder')
        return {'applied': True, 'change': change_row(change)}
    return {'applied': False, 'change': change_row(change)}


def _apply(change: ShareChange, *, note: str = '') -> None:
    wallet = ShareWallet.objects.select_for_update().get(pk=change.wallet_id)
    wallet.percent = change.to_percent
    fields = ['percent']
    if change.new_holder_id:
        wallet.holder_id = change.new_holder_id
        fields.append('holder')
    wallet.save(update_fields=fields)
    change.status, change.decided_at, change.decided_note = ShareChange.Status.APPLIED, timezone.now(), note[:500]
    change.save(update_fields=['status', 'decided_at', 'decided_note'])
    accounts_services.audit(None, 'share_change_applied', None, id=change.id, slot=wallet.slot,
                            to_percent=str(change.to_percent), new_holder=_name(change.new_holder), note=note)


def decide_change(change_id: int, *, by_user, approve: bool, note: str = '', request=None) -> ShareChange:
    """The holder approves or rejects a cut/transfer of their own wallet; the
    person who asked can withdraw it (approve=False by them = cancel)."""
    with transaction.atomic():
        change = ShareChange.objects.select_for_update(of=('self',)).select_related('wallet').filter(pk=change_id).first()
        if change is None or change.status != ShareChange.Status.PENDING:
            raise RevenueError('That change isn’t waiting for an answer.')
        if change.holder_id == by_user.pk:
            if approve:
                if change.wallet.percent != change.from_percent or change.wallet.holder_id != change.holder_id:
                    raise RevenueError('This wallet changed since that was asked — ask again.')
                _apply(change, note=(note or 'Approved by the holder'))
            else:
                change.status, change.decided_at, change.decided_note = ShareChange.Status.REJECTED, timezone.now(), (note or '')[:500]
                change.save(update_fields=['status', 'decided_at', 'decided_note'])
        elif change.requested_by == by_user.get_username() and not approve:
            change.status, change.decided_at = ShareChange.Status.CANCELLED, timezone.now()
            change.save(update_fields=['status', 'decided_at'])
        else:
            raise RevenueError('Only the holder of that wallet can answer.')
    accounts_services.audit(None, 'share_change_decided', request, id=change.id, status=change.status,
                            by=by_user.get_username(), note=note)
    return change


def change_row(c: ShareChange) -> dict:
    return {'id': c.id, 'slot': c.wallet.slot, 'holder': _name(c.holder), 'holder_id': c.holder_id,
            'from_percent': str(c.from_percent), 'to_percent': str(c.to_percent),
            'new_holder': _name(c.new_holder), 'reason': c.reason, 'status': c.status,
            'status_label': c.get_status_display(), 'requested_by': c.requested_by,
            'decided_note': c.decided_note, 'created_at': c.created_at.isoformat(),
            'decided_at': c.decided_at.isoformat() if c.decided_at else None}


# -- buyers and sales --------------------------------------------------------------

def approve_buyer(*, user_id, by_user, request=None) -> ShareBuyer:
    if not by_user.is_superuser:
        raise RevenueError('Only a superuser can approve buyers.')
    user = _staff(user_id)
    buyer, _ = ShareBuyer.objects.get_or_create(user=user, defaults={'approved_by': by_user.get_username()})
    accounts_services.audit(None, 'share_buyer_approved', request, buyer=user.get_username(), by=by_user.get_username())
    return buyer


def remove_buyer(*, user_id, by_user, request=None) -> None:
    if not by_user.is_superuser:
        raise RevenueError('Only a superuser can remove buyers.')
    ShareBuyer.objects.filter(user_id=user_id).delete()
    accounts_services.audit(None, 'share_buyer_removed', request, user_id=user_id, by=by_user.get_username())


def is_buyer(user) -> bool:
    return bool(user and user.is_authenticated and ShareBuyer.objects.filter(user=user).exists())


def _expire_requests() -> None:
    ShareSale.objects.filter(status=ShareSale.Status.REQUESTED,
                             created_at__lt=timezone.now() - timedelta(days=REQUEST_DAYS)).update(
        status=ShareSale.Status.CANCELLED, decided_by='expired', decided_at=timezone.now())


def request_purchase(*, by_user, percent, request=None) -> ShareSale:
    """An approved buyer asks to buy `percent` at today's formula price; they pay
    outside the site and it counts once an admin confirms the payment."""
    if not is_buyer(by_user):
        raise RevenueError('Only approved buyers can ask to buy shares.')
    pct = _pct(percent)
    if pct <= 0:
        raise RevenueError('Choose how much to buy.')
    _expire_requests()
    q = quote(pct)
    if q['total'] is None:
        raise RevenueError(f'No price can be worked out yet: {q["reason"]} Ask an admin to record the sale.')
    with transaction.atomic():
        RevenueSettings.objects.select_for_update().get(pk=RevenueSettings.load().pk)
        _room_for(pct + _requested_by_others(by_user))
        if ShareSale.objects.filter(buyer=by_user, status=ShareSale.Status.REQUESTED).exists():
            raise RevenueError('You already have a purchase waiting for payment.')
        sale = ShareSale.objects.create(buyer=by_user, percent=pct, price=Decimal(q['total']), quoted_price=Decimal(q['total']),
                                        quote=q, requested_by=by_user.get_username())
    accounts_services.audit(None, 'share_purchase_requested', request, id=sale.id, buyer=by_user.get_username(),
                            percent=str(pct), price=str(sale.price))
    return sale


def _requested_by_others(user) -> Decimal:
    return sum((s.percent for s in ShareSale.objects.filter(status=ShareSale.Status.REQUESTED).exclude(buyer=user)), ZERO)


def record_sale(*, buyer_id, percent, price=None, payment_method: str = '', payment_reference: str = '', note: str = '',
                by_user, request=None) -> ShareSale:
    """A superuser records a sale that has been paid: it counts at once. The price
    defaults to the formula's; a different agreed price is kept next to the quote."""
    if not by_user.is_superuser:
        raise RevenueError('Only a superuser can record a sale.')
    from .audit import assert_unlocked
    assert_unlocked()
    pct = _pct(percent)
    if pct <= 0:
        raise RevenueError('Choose how much is sold.')
    buyer = _staff(buyer_id)
    q = quote(pct)
    agreed = _money(price) if price not in (None, '') else (Decimal(q['total']) if q['total'] else None)
    if agreed is None:
        raise RevenueError(f'Enter the price: {q["reason"]}')
    if not (payment_reference or '').strip():
        raise RevenueError('Enter the payment reference (EcoCash/bank/receipt number).')
    with transaction.atomic():
        RevenueSettings.objects.select_for_update().get(pk=RevenueSettings.load().pk)
        _expire_requests()
        _room_for(pct + _requested_by_others(buyer))
        sale = ShareSale.objects.create(
            buyer=buyer, percent=pct, price=agreed, quoted_price=Decimal(q['total']) if q['total'] else None, quote=q,
            payment_method=(payment_method or '')[:40], payment_reference=payment_reference.strip()[:120],
            note=(note or '')[:500], requested_by=by_user.get_username(),
        )
        _confirm(sale, by_user=by_user)
    accounts_services.audit(None, 'share_sale_recorded', request, id=sale.id, buyer=buyer.get_username(), percent=str(pct),
                            price=str(agreed), quoted=q['total'], reference=sale.payment_reference, by=by_user.get_username())
    return sale


def confirm_sale(sale_id: int, *, by_user, payment_method: str = '', payment_reference: str = '', request=None) -> ShareSale:
    """A superuser confirms a buyer's payment arrived: the share is added."""
    if not by_user.is_superuser:
        raise RevenueError('Only a superuser can confirm a payment.')
    from .audit import assert_unlocked
    assert_unlocked()
    if not (payment_reference or '').strip():
        raise RevenueError('Enter the payment reference (EcoCash/bank/receipt number).')
    with transaction.atomic():
        RevenueSettings.objects.select_for_update().get(pk=RevenueSettings.load().pk)
        _expire_requests()
        sale = ShareSale.objects.select_for_update().filter(pk=sale_id).first()
        if sale is None or sale.status != ShareSale.Status.REQUESTED:
            raise RevenueError('That purchase isn’t waiting for payment.')
        sale.payment_method = (payment_method or sale.payment_method)[:40]
        sale.payment_reference = payment_reference.strip()[:120]
        _confirm(sale, by_user=by_user)
    accounts_services.audit(None, 'share_sale_confirmed', request, id=sale.id, buyer=sale.buyer.get_username(),
                            percent=str(sale.percent), price=str(sale.price), reference=sale.payment_reference,
                            by=by_user.get_username())
    return sale


def _confirm(sale: ShareSale, *, by_user) -> None:
    wallet = _wallet_for(sale.buyer)
    _room_for(sale.percent, wallet=wallet)
    wallet.percent += sale.percent
    wallet.save(update_fields=['percent'])
    sale.wallet = wallet
    sale.status, sale.decided_by, sale.decided_at = ShareSale.Status.CONFIRMED, by_user.get_username(), timezone.now()
    sale.save()


def reject_sale(sale_id: int, *, by_user, note: str = '', request=None) -> ShareSale:
    """A superuser rejects a request, or the buyer cancels their own."""
    with transaction.atomic():
        sale = ShareSale.objects.select_for_update().filter(pk=sale_id).first()
        if sale is None or sale.status != ShareSale.Status.REQUESTED:
            raise RevenueError('That purchase isn’t waiting for payment.')
        if by_user.is_superuser:
            sale.status = ShareSale.Status.REJECTED
        elif sale.buyer_id == by_user.pk:
            sale.status = ShareSale.Status.CANCELLED
        else:
            raise RevenueError('Only a superuser or the buyer can do this.')
        sale.decided_by, sale.decided_at, sale.note = by_user.get_username(), timezone.now(), (note or sale.note)[:500]
        sale.save()
    accounts_services.audit(None, 'share_sale_closed', request, id=sale.id, status=sale.status, by=by_user.get_username())
    return sale


def _money(value) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(CENT)
    except (ArithmeticError, ValueError) as exc:
        raise RevenueError('Enter the price as an amount.') from exc
    if amount < 0:
        raise RevenueError('The price can’t be negative.')
    return amount


def sale_row(s: ShareSale) -> dict:
    return {'id': s.id, 'buyer': s.buyer.get_username(), 'buyer_id': s.buyer_id, 'percent': str(s.percent),
            'price': str(s.price), 'quoted_price': str(s.quoted_price) if s.quoted_price is not None else None,
            'status': s.status, 'status_label': s.get_status_display(), 'payment_method': s.payment_method,
            'payment_reference': s.payment_reference, 'note': s.note, 'requested_by': s.requested_by,
            'decided_by': s.decided_by, 'slot': s.wallet.slot if s.wallet_id else None,
            'created_at': s.created_at.isoformat(), 'decided_at': s.decided_at.isoformat() if s.decided_at else None,
            'expires_at': (s.created_at + timedelta(days=REQUEST_DAYS)).isoformat() if s.status == ShareSale.Status.REQUESTED else None}


def update_share_settings(*, partner_pool_percent=None, price_months=None, signer_min_percent=None, by_user, request=None):
    """Superuser: size of the partner pool (never below what's held), the price
    multiple, and the smallest share that co-signs audits."""
    if not by_user.is_superuser:
        raise RevenueError('Only a superuser can change share settings.')
    with transaction.atomic():
        cfg = RevenueSettings.objects.select_for_update().get(pk=RevenueSettings.load().pk)
        if partner_pool_percent not in (None, ''):
            pct = _pct(partner_pool_percent, 'partner pool')
            if pct < held_percent():
                raise RevenueError(f'{held_percent():.2f}% is already held — the pool can’t be smaller than that.')
            cfg.partner_pool_percent = pct
        if price_months not in (None, ''):
            try:
                months = int(price_months)
            except (TypeError, ValueError) as exc:
                raise RevenueError('Enter the months as a whole number.') from exc
            if not 1 <= months <= 120:
                raise RevenueError('Months must be between 1 and 120.')
            cfg.price_months = months
        if signer_min_percent not in (None, ''):
            cfg.signer_min_percent = _pct(signer_min_percent, 'co-signing threshold')
        cfg.save()
    accounts_services.audit(None, 'share_settings', request, partner_pool_percent=str(cfg.partner_pool_percent),
                            price_months=cfg.price_months, signer_min_percent=str(cfg.signer_min_percent),
                            by=by_user.get_username())
    return cfg
