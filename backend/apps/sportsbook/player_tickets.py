"""Tickets for players: their own list (paged, filtered, with totals) and the
public "check a ticket" lookup by ticket code.

The list pages singles and multiples together exactly like the staff explorer
(admin_tickets): newest first, cursor-paged so pages never skip or repeat.
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts import services as accounts_services

from . import ticket_codes
from .admin_tickets import KINDS, RANK, _after, _decode_cursor, _encode_cursor, _querysets
from .services import LIVE_STATUSES, match_over_by

OPEN = ('open', 'pending', 'accepting')
SETTLED = ('won', 'lost', 'void', 'rejected', 'cashed_out')
ZERO = Decimal('0')


def _live(kind: str) -> Q:
    """Tickets with a match being played right now (live status, not past the longest a match lasts)."""
    prefix = 'event_ref__' if kind == 'single' else 'legs__event_ref__'
    return Q(status__in=OPEN) & Q(**{f'{prefix}status__in': LIVE_STATUSES, f'{prefix}starts_at__gt': match_over_by()})


def _row(obj, kind: str, prefix: str, serializer, ctx) -> dict:
    return {**serializer(obj, context=ctx).data, 'kind': kind, 'ticket': f'{prefix}{obj.pk}'}


class MyTicketsView(APIView):
    """GET /api/my-tickets/?tab=all|open|live|settled&date_from=&date_to=&cursor=&limit=

    The player's singles and multiples, newest first, a page at a time
    (`next_cursor`), plus `counts` per tab and `stats` (staked, returned,
    win rate) for the date range, so the app never downloads every bet."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        player = accounts_services.get_current_player(request)
        if player is None:
            return Response({'results': [], 'next_cursor': None, 'counts': {}, 'stats': None})
        params = request.query_params
        base = {k: v.filter(player_id=player.id) for k, v in _querysets().items()}
        for param, lookup in (('date_from', 'placed_at__date__gte'), ('date_to', 'placed_at__date__lte')):
            if params.get(param):
                day = parse_date(params[param])
                if day is None:
                    return Response({'detail': f'{param} must be a date (YYYY-MM-DD).'}, status=status.HTTP_400_BAD_REQUEST)
                base = {k: v.filter(**{lookup: day}) for k, v in base.items()}

        tabs = {
            'all': lambda kind, v: v,
            'open': lambda kind, v: v.filter(status__in=OPEN),
            'live': lambda kind, v: v.filter(_live(kind)).distinct(),
            'settled': lambda kind, v: v.filter(status__in=SETTLED),
        }
        tab = params.get('tab') if params.get('tab') in tabs else 'all'
        counts = {name: sum(f(k, v).order_by().count() for k, v in base.items()) for name, f in tabs.items()}

        staked = returned = ZERO
        won = decided = 0
        for v in base.values():
            a = v.aggregate(staked=Sum('stake'), cashed_stake=Sum('stake_cashed_out'), paid=Sum('payout'),
                            cashed=Sum('cashout_paid'), won=Count('id', filter=Q(status='won')),
                            decided=Count('id', filter=Q(status__in=('won', 'lost'))))
            staked += (a['staked'] or ZERO) + (a['cashed_stake'] or ZERO)
            returned += (a['paid'] or ZERO) + (a['cashed'] or ZERO)
            won += a['won']
            decided += a['decided']
        # A multiple's bonus is paid on top of its payout.
        returned += base['multiple'].filter(status='won').aggregate(b=Sum('bonus'))['b'] or ZERO

        try:
            limit = max(1, min(int(params.get('limit') or 20), 50))
        except ValueError:
            limit = 20
        cursor = _decode_cursor(params['cursor']) if params.get('cursor') else None
        if params.get('cursor') and cursor is None:
            return Response({'detail': 'Invalid cursor.'}, status=status.HTTP_400_BAD_REQUEST)
        candidates = []
        for kind, v in base.items():
            v = tabs[tab](kind, v)
            if cursor:
                v = v.filter(_after(kind, cursor))
            candidates += [(obj, kind) for obj in v.order_by('-placed_at', '-pk')[:limit + 1]]
        candidates.sort(key=lambda c: (c[0].placed_at, -RANK[c[1]], c[0].pk), reverse=True)
        page, more = candidates[:limit], len(candidates) > limit

        meta = {kind: (prefix, ser) for kind, prefix, _, ser in KINDS}
        ctx = {'request': request}
        return Response({
            'results': [_row(obj, kind, *meta[kind], ctx) for obj, kind in page],
            'next_cursor': _encode_cursor(*page[-1]) if more and page else None,
            'counts': counts,
            'stats': {'staked': f'{staked:.2f}', 'returned': f'{returned:.2f}', 'net': f'{returned - staked:.2f}',
                      'won': won, 'decided': decided},
        })


class PublicTicketView(APIView):
    """GET /api/tickets/<code>/ — "check a ticket": anyone with the ticket code
    (printed under its barcode) sees the ticket, its selections, live scores and
    result. Who placed it is never shown. `mine` is true for its own player.
    Rate-limited, and codes are random, so tickets can't be trawled."""
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'ticket_lookup'

    def get(self, request, code: str):
        code = ticket_codes.normalise(code)
        if len(code) != ticket_codes.LENGTH:
            return Response({'detail': 'Ticket codes are 10 letters and numbers, under the barcode.'},
                            status=status.HTTP_400_BAD_REQUEST)
        for kind, prefix, _, serializer in KINDS:
            obj = _querysets()[kind].filter(code=code).first()
            if obj is not None:
                break
        else:
            return Response({'detail': 'No ticket with that code. Check it and try again.'}, status=status.HTTP_404_NOT_FOUND)
        player = accounts_services.get_current_player(request) if request.user.is_authenticated else None
        mine = bool(player and player.id == obj.player_id)
        # Only the ticket's own player sees a live cash-out offer.
        row = _row(obj, kind, prefix, serializer, {'request': request, 'skip_cashout': not mine})
        row['mine'] = mine
        return Response(row)
