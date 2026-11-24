"""Aviator free spins: staff give players free bets; players claim them.

A grant offers each chosen player `count` free bets of `amount` (status OFFERED).
The player is notified and claims them on the Aviator page (OFFERED -> AVAILABLE);
from then on they work like any free bet (services.place_bet with free_bet_id):
the stake costs nothing and a win pays the winnings only, as a bonus credit.
Unclaimed offers lapse at the grant's expiry. Suspended and self-excluded
players are never offered spins.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from .models import JetFreeBet, JetFreeSpinGrant

MAX_AMOUNT = Decimal('100.00')
MAX_COUNT = 50
MAX_DAYS = 90


class FreeSpinError(ValueError):
    """Why a grant can't be made (shown to staff)."""


def _audience_ids(audience: str, usernames: str) -> tuple[list[int], list[str]]:
    from apps.accounts.models import Player
    from apps.wallet.models import LedgerEntry
    qs = Player.objects.filter(is_suspended=False, self_excluded=False)
    missing: list[str] = []
    if audience == JetFreeSpinGrant.Audience.DEPOSITORS:
        qs = qs.filter(pk__in=LedgerEntry.objects.filter(kind='deposit').values('wallet__player_id'))
    elif audience == JetFreeSpinGrant.Audience.USERNAMES:
        names = {n.strip().lstrip('@').lower() for n in usernames.replace(',', '\n').split() if n.strip()}
        if not names:
            raise FreeSpinError('List the usernames to give spins to.')
        found = dict(qs.filter(username__in=names).values_list('username', 'pk'))
        missing = sorted(names - set(found))
        return list(found.values()), missing
    elif audience != JetFreeSpinGrant.Audience.ALL:
        raise FreeSpinError('Choose who gets the spins.')
    return list(qs.values_list('pk', flat=True)), missing


@transaction.atomic
def grant(*, audience: str, usernames: str = '', amount, count, days, message: str = '', by: str) -> tuple[JetFreeSpinGrant, list[str]]:
    try:
        amount = Decimal(str(amount)).quantize(Decimal('0.01'))
        count, days = int(count), int(days)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise FreeSpinError('Enter the spin value, how many spins and how many days.') from exc
    if not Decimal('0.10') <= amount <= MAX_AMOUNT:
        raise FreeSpinError(f'Each spin is worth $0.10 to ${MAX_AMOUNT:.2f}.')
    if not 1 <= count <= MAX_COUNT:
        raise FreeSpinError(f'Give 1 to {MAX_COUNT} spins.')
    if not 1 <= days <= MAX_DAYS:
        raise FreeSpinError(f'Players have 1 to {MAX_DAYS} days to use them.')
    ids, missing = _audience_ids(audience, usernames)
    if not ids:
        raise FreeSpinError('No players match.' + (f' Not found: {", ".join(missing)}.' if missing else ''))
    expires = timezone.now() + timedelta(days=days)
    g = JetFreeSpinGrant.objects.create(audience=audience, usernames=usernames[:5000], amount=amount, count=count,
                                        message=message.strip()[:200], expires_at=expires, players=len(ids), created_by=by[:150])
    JetFreeBet.objects.bulk_create(
        [JetFreeBet(player_id=pid, amount=amount, expires_at=expires, source='free_spins', grant=g,
                    status=JetFreeBet.Status.OFFERED) for pid in ids for _ in range(count)], batch_size=2000)
    from apps.notifications.models import Notification
    body = message.strip() or f'{count} free spin{"" if count == 1 else "s"} of ${amount:.2f} in Aviator. Claim them before {expires:%d %b}.'
    Notification.objects.bulk_create(
        [Notification(player_id=pid, kind='bonus_credited', title='🎁 Free Aviator spins', body=body) for pid in ids], batch_size=2000)
    from apps.accounts import services as accounts
    accounts.audit(None, 'free_spins_granted', None, grant=g.pk, audience=audience, players=len(ids), count=count,
                   amount=str(amount), by=by)
    return g, missing


def offers_for(player_id: int, now=None) -> list[dict]:
    """Unclaimed spins, one row per grant."""
    now = now or timezone.now()
    rows = (JetFreeBet.objects.filter(player_id=player_id, status=JetFreeBet.Status.OFFERED, expires_at__gt=now)
            .values('grant_id', 'amount', 'expires_at', 'grant__message').annotate(n=Count('id')).order_by('expires_at'))
    return [{'grant': r['grant_id'], 'count': r['n'], 'amount': str(r['amount']), 'expires_at': r['expires_at'].isoformat(),
             'message': r['grant__message'] or ''} for r in rows]


@transaction.atomic
def claim(player_id: int, grant_id=None, now=None) -> int:
    """Claim the player's offered spins (all of them, or one grant's). Returns how many."""
    now = now or timezone.now()
    qs = JetFreeBet.objects.select_for_update().filter(player_id=player_id, status=JetFreeBet.Status.OFFERED, expires_at__gt=now)
    if grant_id:
        qs = qs.filter(grant_id=grant_id)
    return JetFreeBet.objects.filter(pk__in=list(qs.values_list('pk', flat=True))).update(status=JetFreeBet.Status.AVAILABLE)


def payload(g: JetFreeSpinGrant) -> dict:
    stats = g.free_bets.aggregate(claimed=Count('id', filter=~Q(status__in=('offered', 'expired'))),
                                  used=Count('id', filter=Q(status='used')), total=Count('id'))
    return {'id': g.pk, 'audience': g.audience, 'audience_label': g.get_audience_display(), 'amount': f'{g.amount:.2f}',
            'count': g.count, 'message': g.message, 'players': g.players, 'expires_at': g.expires_at.isoformat(),
            'created_by': g.created_by, 'created_at': g.created_at.isoformat(), 'spins': stats['total'],
            'claimed': stats['claimed'], 'used': stats['used'], 'cost_if_all_used': f'{g.amount * stats["total"]:.2f}'}
