"""Staff ticket explorer: every player's singles (S12) and multiples (M5) as
one newest-first list, plus one ticket in full.

The list is cursor-paged across both tables. Rows are ordered by
(placed_at desc, singles before multiples, id desc); the cursor is the last
row's position in that order, so pages never skip or repeat a ticket even
when several were placed in the same instant.
"""
from __future__ import annotations

import base64
import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Prefetch, Q, Sum
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from . import ticket_codes
from .models import Bet, BetLeg, BetSlip
from .serializers import BetSerializer, BetSlipSerializer

logger = logging.getLogger(__name__)

TICKET_RE = re.compile(r'#?([SsMm])(\d+)')
KINDS = (('single', 'S', Bet, BetSerializer), ('multiple', 'M', BetSlip, BetSlipSerializer))
RANK = {'single': 0, 'multiple': 1}
MAX_LIMIT = 100
ZERO = Decimal('0')


# Everything a ticket shows: the match with both teams, and the market picked.
TICKET_JOINS = ('event_ref__home_team', 'event_ref__away_team', 'event_ref__league', 'outcome_ref__market')


def _querysets():
    legs = Prefetch('legs', queryset=BetLeg.objects.select_related(*TICKET_JOINS))
    return {
        'single': Bet.objects.select_related(*TICKET_JOINS),
        'multiple': BetSlip.objects.prefetch_related(legs),
    }


def _encode_cursor(obj, kind: str) -> str:
    raw = f'{obj.placed_at.isoformat()}|{kind}|{obj.pk}'
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip('=')


def _decode_cursor(value: str):
    try:
        raw = base64.urlsafe_b64decode(value + '=' * (-len(value) % 4)).decode()
        stamp, kind, pk = raw.split('|')
        if kind not in RANK:
            return None
        return datetime.fromisoformat(stamp), kind, int(pk)
    except (ValueError, UnicodeDecodeError):
        return None


def _after(kind: str, cursor) -> Q:
    """Rows of `kind` that come after the cursor in the list's order."""
    stamp, c_kind, c_pk = cursor
    if RANK[kind] < RANK[c_kind]:   # same instant: these came before the cursor
        return Q(placed_at__lt=stamp)
    if RANK[kind] > RANK[c_kind]:   # same instant: these all come after it
        return Q(placed_at__lte=stamp)
    return Q(placed_at__lt=stamp) | Q(placed_at=stamp, pk__lt=c_pk)


def _filtered(params):
    """Both querysets with every filter but `status` applied, or a 400 message."""
    from apps.accounts.models import Player

    qs = _querysets()
    if params.get('player_id'):
        qs = {k: v.filter(player_id=params['player_id']) for k, v in qs.items()}
    q = (params.get('q') or '').strip()
    ticket = TICKET_RE.fullmatch(q)
    code = ticket_codes.normalise(q)
    if not ticket and len(code) == ticket_codes.LENGTH and set(code) <= set(ticket_codes.ALPHABET):
        # A ticket code (from the barcode); fall through to a name search if it isn't one.
        by_code = {k: v.filter(code=code) for k, v in qs.items()}
        if any(v.exists() for v in by_code.values()):
            qs, q = by_code, ''
    if ticket:
        wanted = 'single' if ticket.group(1).lower() == 's' else 'multiple'
        qs = {k: (v.filter(pk=int(ticket.group(2))) if k == wanted else v.none()) for k, v in qs.items()}
    elif q:
        ids = list(Player.objects.filter(Q(username__icontains=q) | Q(email__icontains=q) | Q(full_name__icontains=q))
                   .values_list('id', flat=True)[:500])
        qs = {k: v.filter(player_id__in=ids) for k, v in qs.items()}
    kind = params.get('kind')
    if kind in RANK:
        qs = {k: (v if k == kind else v.none()) for k, v in qs.items()}
    for param, lookup in (('date_from', 'placed_at__date__gte'), ('date_to', 'placed_at__date__lte')):
        if params.get(param):
            day = parse_date(params[param])
            if day is None:
                return None, f'{param} must be a date (YYYY-MM-DD).'
            qs = {k: v.filter(**{lookup: day}) for k, v in qs.items()}
    if params.get('min_stake'):
        try:
            minimum = Decimal(params['min_stake'])
        except InvalidOperation:
            return None, 'min_stake must be a number.'
        qs = {k: v.filter(stake__gte=minimum) for k, v in qs.items()}
    return qs, None


def _summary(qs: dict, by_status: dict) -> dict:
    """Totals over the filtered tickets, and what's riding on the open ones."""
    money = DecimalField(max_digits=20, decimal_places=2)
    potential = {
        'single': ExpressionWrapper(F('stake') * F('odds'), output_field=money),
        'multiple': ExpressionWrapper(F('stake') * F('combined_odds') * (1 + F('bonus_percent') / 100), output_field=money),
    }
    n, staked, returned, open_n, liability = 0, ZERO, ZERO, 0, ZERO
    for kind, v in qs.items():
        a = v.aggregate(n=Count('id'), staked=Sum('stake'), paid=Sum('payout'), cashed=Sum('cashout_paid'),
                        cashed_stake=Sum('stake_cashed_out'))
        o = v.filter(status='open').aggregate(n=Count('id'), riding=Sum(potential[kind]))
        n += a['n'] or 0
        # Stake that bought a partial cash-out was still staked.
        staked += (a['staked'] or ZERO) + (a['cashed_stake'] or ZERO)
        returned += (a['paid'] or ZERO) + (a['cashed'] or ZERO)
        open_n += o['n'] or 0
        liability += o['riding'] or ZERO
    return {
        'tickets': n, 'staked': f'{staked:.2f}', 'returned': f'{returned:.2f}', 'net': f'{staked - returned:.2f}',
        'open': open_n, 'open_liability': f'{liability:.2f}', 'by_status': by_status,
    }


def _row(obj, kind: str, prefix: str, serializer, ctx) -> dict:
    return {**serializer(obj, context=ctx).data, 'kind': kind, 'ticket': f'{prefix}{obj.pk}',
            'player_id': obj.player_id, 'settled_at': obj.settled_at}


def _usernames(rows) -> None:
    from apps.accounts.models import Player
    names = dict(Player.objects.filter(id__in={r['player_id'] for r in rows}).values_list('id', 'username'))
    for r in rows:
        r['username'] = names.get(r['player_id'], '(deleted)')


class AdminTicketsView(APIView):
    """GET /api/admin/tickets/?q=&status=&kind=single|multiple&player_id=
    &date_from=&date_to=&min_stake=&limit=&cursor=

    `q` takes a ticket number as players see it (S12 / M5), a ticket code (the
    barcode), or part of a username, email or name. Returns a page of tickets, `next_cursor` (null on
    the last page) and a summary of everything that matches (with
    `by_status` counts ignoring the status filter, for the status tabs)."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        params = request.query_params
        qs, error = _filtered(params)
        if error:
            return Response({'detail': error}, status=status.HTTP_400_BAD_REQUEST)

        by_status: dict[str, int] = {}
        for v in qs.values():
            for row in v.order_by().values('status').annotate(n=Count('id')):
                by_status[row['status']] = by_status.get(row['status'], 0) + row['n']
        if params.get('status'):
            qs = {k: v.filter(status=params['status']) for k, v in qs.items()}
        summary = _summary(qs, by_status)

        try:
            limit = max(1, min(int(params.get('limit') or 50), MAX_LIMIT))
        except ValueError:
            limit = 50
        cursor = _decode_cursor(params['cursor']) if params.get('cursor') else None
        if params.get('cursor') and cursor is None:
            return Response({'detail': 'Invalid cursor.'}, status=status.HTTP_400_BAD_REQUEST)

        # Up to limit+1 from each table, merged in list order: the extra row
        # says whether there's another page.
        candidates = []
        for kind, v in qs.items():
            if cursor:
                v = v.filter(_after(kind, cursor))
            candidates += [(obj, kind) for obj in v.order_by('-placed_at', '-pk')[:limit + 1]]
        candidates.sort(key=lambda c: (c[0].placed_at, -RANK[c[1]], c[0].pk), reverse=True)
        page, more = candidates[:limit], len(candidates) > limit

        ctx = {'request': request, 'skip_cashout': True}
        meta = {kind: (prefix, ser) for kind, prefix, _, ser in KINDS}
        rows = []
        for obj, kind in page:
            prefix, ser = meta[kind]
            try:
                rows.append(_row(obj, kind, prefix, ser, ctx))
            except Exception:  # noqa: BLE001 — one odd old ticket must never take the list down
                logger.exception('admin tickets: could not show %s%s', prefix, obj.pk)
        _usernames(rows)
        return Response({
            'results': rows,
            'next_cursor': _encode_cursor(*page[-1]) if more and page else None,
            'summary': summary,
        })


class AdminTicketDetailView(APIView):
    """GET /api/admin/tickets/<S12|M5>/ — one ticket in full: legs, the live
    cash-out offer if it's open, and who placed it."""
    permission_classes = [IsAdminUser]

    def get(self, request, ticket: str):
        from apps.accounts.models import Player
        from apps.wallet import services as wallet_services

        match = TICKET_RE.fullmatch(ticket.strip())
        if not match:
            return Response({'detail': 'Ticket numbers look like S12 or M5.'}, status=status.HTTP_400_BAD_REQUEST)
        kind = 'single' if match.group(1).lower() == 's' else 'multiple'
        obj = _querysets()[kind].filter(pk=int(match.group(2))).first()
        if obj is None:
            return Response({'detail': 'No such ticket.'}, status=status.HTTP_404_NOT_FOUND)
        prefix, ser = ('S', BetSerializer) if kind == 'single' else ('M', BetSlipSerializer)
        row = _row(obj, kind, prefix, ser, {'request': request})
        row['cashed_out_at'] = obj.cashed_out_at
        player = Player.objects.filter(pk=obj.player_id).first() if obj.player_id else None
        row['username'] = player.username if player else '(deleted)'
        row['player'] = player and {
            'id': player.id, 'username': player.username, 'email': player.email, 'full_name': player.full_name,
            'is_suspended': player.is_suspended, 'kyc_status': player.kyc_status,
            'balance': str(wallet_services.get_balance(player.id)),
        }
        return Response(row)
