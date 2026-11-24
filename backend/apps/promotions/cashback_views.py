"""Admin API: lost-by-one refunds and cashback (promotions.refunds, promotions.cashback).
Anyone on staff can look; only a superuser changes the rules (they pay real money)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, Sum
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import services as accounts

from .models import CashbackPayout, CashbackSettings, CashbackTier, LossRefundSettings


def _money(v, *, field: str, allow_blank: bool = False):
    if allow_blank and (v is None or str(v).strip() == ''):
        return None
    try:
        d = Decimal(str(v)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f'{field}: enter a number.') from exc
    if d < 0:
        raise ValueError(f'{field}: must be 0 or more.')
    return d


def _payload(request) -> dict:
    from apps.wallet.models import LedgerEntry
    r, c = LossRefundSettings.load(), CashbackSettings.load()
    refunds = LedgerEntry.objects.filter(kind='loss_refund').aggregate(n=Count('id'), t=Sum('amount'))
    cash = CashbackPayout.objects.aggregate(n=Count('id'), t=Sum('amount'))
    names = accounts.usernames_for(list(CashbackPayout.objects.values_list('player_id', flat=True)[:20]))
    return {
        'can_edit': bool(request.user.is_superuser),
        'refund': {'enabled': r.enabled, 'min_odds': f'{r.min_odds:.2f}', 'divisor': f'{r.divisor:.2f}',
                   'max_refund': f'{r.max_refund:.2f}' if r.max_refund is not None else '',
                   'paid_count': refunds['n'] or 0, 'paid_total': f'{refunds["t"] or 0:.2f}'},
        'cashback': {'enabled': c.enabled, 'period_days': c.period_days,
                     'starts_on': c.starts_on.isoformat() if c.starts_on else '',
                     'last_period_start': c.last_period_start.isoformat() if c.last_period_start else None,
                     'paid_count': cash['n'] or 0, 'paid_total': f'{cash["t"] or 0:.2f}'},
        'tiers': [{'id': t.id, 'name': t.name, 'min_loss': f'{t.min_loss:.2f}', 'percent': f'{t.percent:.2f}',
                   'max_amount': f'{t.max_amount:.2f}' if t.max_amount is not None else '', 'min_tickets': t.min_tickets,
                   'min_active_days': t.min_active_days, 'active': t.active} for t in CashbackTier.objects.all()],
        'recent': [{'player': names.get(p.player_id, f'#{p.player_id}'), 'period': f'{p.period_start}..{p.period_end}',
                    'loss': f'{p.loss:.2f}', 'percent': f'{p.percent:.2f}', 'amount': f'{p.amount:.2f}',
                    'created_at': p.created_at.isoformat()} for p in CashbackPayout.objects.all()[:20]],
    }


class AdminCashbackView(APIView):
    """GET — refund and cashback rules, totals, recent payouts. PUT {refund?, cashback?, tiers?} — superusers only."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        return Response(_payload(request))

    def put(self, request):
        if not request.user.is_superuser:
            return Response({'detail': 'Only a superuser can change refunds and cashback.'}, status=status.HTTP_403_FORBIDDEN)
        d = request.data
        try:
            with transaction.atomic():
                if isinstance(d.get('refund'), dict):
                    x, r = d['refund'], LossRefundSettings.load()
                    r.enabled = bool(x.get('enabled', r.enabled))
                    r.min_odds = _money(x.get('min_odds', r.min_odds), field='Minimum ticket odds')
                    r.divisor = _money(x.get('divisor', r.divisor), field='Divide by')
                    if r.divisor <= 0:
                        raise ValueError('Divide by: must be more than 0.')
                    r.max_refund = _money(x.get('max_refund'), field='Most per refund', allow_blank=True)
                    r.save()
                if isinstance(d.get('cashback'), dict):
                    x, c = d['cashback'], CashbackSettings.load()
                    c.enabled = bool(x.get('enabled', c.enabled))
                    days = int(x.get('period_days', c.period_days))
                    if not 1 <= days <= 90:
                        raise ValueError('Period: 1 to 90 days.')
                    starts = (x.get('starts_on') or '').strip() if isinstance(x.get('starts_on'), str) else ''
                    new_start = date.fromisoformat(starts) if starts else c.starts_on
                    if days != c.period_days or new_start != c.starts_on:
                        c.last_period_start = None                 # periods counted afresh from the new start
                    c.period_days, c.starts_on = days, new_start
                    if c.enabled and not c.starts_on:
                        raise ValueError('Choose the date the first cashback period starts.')
                    c.save()
                if isinstance(d.get('tiers'), list):
                    keep = []
                    for x in d['tiers']:
                        pct = _money(x.get('percent'), field='Cashback %')
                        if not Decimal('0.01') <= pct <= Decimal('100'):
                            raise ValueError('Cashback %: 0.01 to 100.')
                        values = dict(name=str(x.get('name') or '')[:60], min_loss=_money(x.get('min_loss'), field='Minimum loss'),
                                      percent=pct, max_amount=_money(x.get('max_amount'), field='Most per player', allow_blank=True),
                                      min_tickets=int(x.get('min_tickets') or 0), min_active_days=int(x.get('min_active_days') or 0),
                                      active=bool(x.get('active', True)))
                        if x.get('id'):
                            CashbackTier.objects.filter(pk=x['id']).update(**values)
                            keep.append(int(x['id']))
                        else:
                            keep.append(CashbackTier.objects.create(**values).pk)
                    CashbackTier.objects.exclude(pk__in=keep).delete()
        except (ValueError, TypeError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        accounts.audit(None, 'cashback_rules', request, **{k: str(d.get(k))[:500] for k in ('refund', 'cashback', 'tiers') if k in d})
        return Response(_payload(request))
