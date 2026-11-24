"""Bulk bonus grants: one promotion for many players at once.

Giving: each player in the audience gets the bonus through grant_bonus, so it
lands in the Bonus wallet with a wagering requirement, the fraud engine can
refuse it (multi-accounts), the player is notified, and a player is never paid
twice for one grant (the grant is its own hidden promotion; one claim per player).

Taking back: from the Bonus wallet only, never below zero. Real money (Deposit,
Winnings) is never touched here: taking deposited or won money is not a
promotion. Undo takes back what a grant gave, as far as it is still unused.

Suspended and self-excluded players are always left out. A grant runs in the
background (Celery) and can be resumed if it stalls: every step is idempotent.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.accounts import services as accounts
from apps.wallet import services as wallet
from apps.wallet.models.wallet import Bucket

from .models import BulkGrant, PromotionClaim

logger = logging.getLogger(__name__)

MAX_PER_PLAYER = Decimal('500.00')
MAX_WAGERING = Decimal('50')
CHUNK = 200
STALLED_AFTER = timedelta(minutes=3)


class BulkError(ValueError):
    """A grant that can't be made (shown to staff)."""


def system_code(grant: BulkGrant) -> str:
    return f'bulk-{grant.pk}'


def audience_ids(audience: str) -> list[int]:
    """Player IDs in the audience: never suspended or self-excluded players."""
    from apps.accounts.models import Player
    from apps.wallet.models import LedgerEntry
    qs = Player.objects.filter(is_suspended=False, self_excluded=False)
    if audience == BulkGrant.Audience.DEPOSITORS:
        qs = qs.filter(pk__in=LedgerEntry.objects.filter(kind='deposit').values('wallet__player_id'))
    elif audience == BulkGrant.Audience.ACTIVE:
        since = timezone.now() - timedelta(days=30)
        qs = qs.filter(pk__in=LedgerEntry.objects.filter(kind__in=('bet_stake', 'casino_debit'), created_at__gte=since)
                       .values('wallet__player_id'))
    elif audience == BulkGrant.Audience.VERIFIED:
        qs = qs.filter(kyc_status=Player.Kyc.VERIFIED)
    elif audience != BulkGrant.Audience.ALL:
        raise BulkError('Choose who gets it.')
    return list(qs.order_by('pk').values_list('pk', flat=True))


def _clean(kind: str, audience: str, amount, wagering) -> tuple[Decimal, Decimal]:
    if kind not in BulkGrant.Kind.values:
        raise BulkError('Choose to give a bonus or take bonus back.')
    if audience not in BulkGrant.Audience.values:
        raise BulkError('Choose who gets it.')
    try:
        amount = Decimal(str(amount)).quantize(Decimal('0.01'))
        wagering = Decimal(str(wagering if wagering not in (None, '') else '1')).quantize(Decimal('0.01'))
    except Exception as exc:  # noqa: BLE001
        raise BulkError('Enter the amount and wagering as numbers.') from exc
    if not Decimal('0.01') <= amount <= MAX_PER_PLAYER:
        raise BulkError(f'The amount per player is between $0.01 and ${MAX_PER_PLAYER:.2f}.')
    if not Decimal('0') <= wagering <= MAX_WAGERING:
        raise BulkError(f'Wagering is between 0x and {MAX_WAGERING:.0f}x the bonus.')
    return amount, wagering


def preview(*, kind: str, audience: str, amount) -> dict:
    """How many players and how much, before anything is done."""
    amount, _ = _clean(kind, audience, amount, 1)
    ids = audience_ids(audience)
    if kind == BulkGrant.Kind.CREDIT:
        cost = amount * len(ids)
        return {'players': len(ids), 'total': f'{cost:.2f}', 'affected': len(ids)}
    taken, affected = Decimal('0'), 0
    for pid in ids:
        have = wallet.get_balances(pid)[Bucket.BONUS]
        if have > 0:
            affected += 1
            taken += min(have, amount)
    return {'players': len(ids), 'total': f'{taken:.2f}', 'affected': affected}


def start(*, kind: str, audience: str, amount, wagering, name: str, message: str, by: str,
          undo_of: BulkGrant | None = None) -> BulkGrant:
    amount, wagering = _clean(kind, audience, amount, wagering)
    name = (name or '').strip()
    if not name and not undo_of:
        raise BulkError('Give the promotion a name: players see it.')
    if BulkGrant.objects.filter(status=BulkGrant.Status.RUNNING).exists():
        raise BulkError('Another bulk grant is still running. Wait for it to finish.')
    grant = BulkGrant.objects.create(
        kind=kind, audience=audience, amount=amount, wagering_multiplier=wagering, name=name[:80] or 'Bonus adjustment',
        message=(message or '').strip()[:300], created_by=by[:150], undo_of=undo_of,
        players=len(audience_ids(audience)) if not undo_of else 0, heartbeat_at=timezone.now(),
    )
    accounts.audit(None, 'bulk_grant_started', None, grant=grant.pk, kind=kind, audience=audience,
                   amount=str(amount), name=grant.name, by=by, undo_of=undo_of.pk if undo_of else None)
    enqueue(grant.pk)
    return grant


def enqueue(grant_id: int) -> None:
    from .tasks import run_bulk_grant
    transaction.on_commit(lambda: run_bulk_grant.delay(grant_id))


def undo(grant: BulkGrant, *, by: str) -> BulkGrant:
    """Take back what a finished 'give' grant paid, as far as it is still in
    each player's Bonus wallet."""
    if grant.kind != BulkGrant.Kind.CREDIT or grant.status != BulkGrant.Status.DONE:
        raise BulkError('Only a finished bonus grant can be undone.')
    if BulkGrant.objects.filter(undo_of=grant).exists():
        raise BulkError('This grant has already been undone.')
    return start(kind=BulkGrant.Kind.DEBIT, audience=grant.audience, amount=grant.amount, wagering=0,
                 name=f'Undo: {grant.name}'[:80], message='', by=by, undo_of=grant)


# -- running ---------------------------------------------------------------------------

def _give(grant: BulkGrant, pid: int) -> Decimal:
    from . import services
    claim = services.grant_bonus(player_id=pid, amount=grant.amount, wagering_multiplier=grant.wagering_multiplier,
                                 system_code=system_code(grant), name=grant.name,
                                 message=grant.message or f'${grant.amount:.2f} bonus: {grant.name}.')
    return claim.bonus_amount if claim and claim.bonus_credited else Decimal('0')


def _take(grant: BulkGrant, pid: int, most: Decimal) -> Decimal:
    """Take up to `most` from the Bonus wallet (never below zero). Idempotent per grant and player."""
    from apps.wallet.bonus import reset
    from apps.wallet.models import LedgerEntry
    key = f'bulk:{grant.pk}:{pid}'
    done = LedgerEntry.objects.filter(idempotency_key=key).values_list('amount', flat=True).first()
    if done is not None:
        return -done
    for _ in range(2):                                     # once more if the balance moved under us
        have = wallet.get_balances(pid)[Bucket.BONUS]
        take = min(have, most)
        if take <= 0:
            return Decimal('0')
        try:
            wallet.post_entry(player_id=pid, amount=-take, kind='bonus_forfeit', bucket=Bucket.BONUS,
                              idempotency_key=key, reference=f'bulk:{grant.pk}', require_non_negative=True)
        except wallet.InsufficientFunds:
            continue
        if take == have:
            reset(pid, cleared=True)
        from apps.notifications import services as notes
        notes.notify(player_id=pid, kind='account_alert', title='Bonus adjusted',
                     body=grant.message or f'${take:.2f} was removed from your Bonus wallet ({grant.name}).')
        return take
    return Decimal('0')


def _targets(grant: BulkGrant) -> list[tuple[int, Decimal]]:
    """[(player, most to give or take)] for this grant."""
    if grant.undo_of_id:
        claims = PromotionClaim.objects.filter(promotion__code=system_code(grant.undo_of), bonus_credited=True)
        return list(claims.order_by('player_id').values_list('player_id', 'bonus_amount'))
    return [(pid, grant.amount) for pid in audience_ids(grant.audience)]


def run(grant_id: int) -> BulkGrant:
    """Work through the audience. Safe to run again (resume): nobody is paid twice."""
    grant = BulkGrant.objects.get(pk=grant_id)
    if grant.status != BulkGrant.Status.RUNNING:
        return grant
    try:
        targets = _targets(grant)
        BulkGrant.objects.filter(pk=grant.pk).update(players=len(targets), processed=0, heartbeat_at=timezone.now())
        for i in range(0, len(targets), CHUNK):
            for pid, most in targets[i:i + CHUNK]:
                try:
                    with transaction.atomic():
                        if grant.kind == BulkGrant.Kind.CREDIT:
                            _give(grant, pid)
                        else:
                            _take(grant, pid, most)
                except Exception:  # noqa: BLE001 — one bad account must not stop the rest
                    logger.exception('bulk grant %s failed for player %s', grant.pk, pid)
            BulkGrant.objects.filter(pk=grant.pk).update(processed=F('processed') + len(targets[i:i + CHUNK]),
                                                         heartbeat_at=timezone.now())
        if grant.undo_of_id:
            PromotionClaim.objects.filter(promotion__code=system_code(grant.undo_of),
                                          status=PromotionClaim.Status.ACTIVE).update(status=PromotionClaim.Status.FORFEITED)
        _finish(grant, BulkGrant.Status.DONE)
    except Exception as exc:  # noqa: BLE001
        logger.exception('bulk grant %s failed', grant.pk)
        BulkGrant.objects.filter(pk=grant.pk).update(error=f'{exc.__class__.__name__}: {exc}'[:300])
        _finish(grant, BulkGrant.Status.FAILED)
    return BulkGrant.objects.get(pk=grant.pk)


def _finish(grant: BulkGrant, status: str) -> None:
    """Final numbers come from the ledger and claims, not from counters, so a
    resumed or retried run still reports the truth."""
    from django.db.models import Count, Sum
    from apps.wallet.models import LedgerEntry
    if grant.kind == BulkGrant.Kind.CREDIT:
        agg = PromotionClaim.objects.filter(promotion__code=system_code(grant), bonus_credited=True).aggregate(
            n=Count('id'), t=Sum('bonus_amount'))
        affected, total = agg['n'] or 0, agg['t'] or Decimal('0')
    else:
        agg = LedgerEntry.objects.filter(reference=f'bulk:{grant.pk}', kind='bonus_forfeit').aggregate(n=Count('id'), t=Sum('amount'))
        affected, total = agg['n'] or 0, -(agg['t'] or Decimal('0'))
    fresh = BulkGrant.objects.get(pk=grant.pk)
    BulkGrant.objects.filter(pk=grant.pk).update(
        status=status, affected=affected, total=total, skipped=max(fresh.players - affected, 0),
        finished_at=timezone.now(), heartbeat_at=timezone.now())
    accounts.audit(None, 'bulk_grant_finished', None, grant=grant.pk, status=status, affected=affected, total=str(total))


def stalled(grant: BulkGrant) -> bool:
    return (grant.status == BulkGrant.Status.RUNNING and grant.heartbeat_at is not None
            and grant.heartbeat_at < timezone.now() - STALLED_AFTER)


def payload(grant: BulkGrant) -> dict:
    return {
        'id': grant.pk, 'kind': grant.kind, 'kind_label': grant.get_kind_display(), 'audience': grant.audience,
        'audience_label': grant.get_audience_display(), 'amount': f'{grant.amount:.2f}',
        'wagering_multiplier': f'{grant.wagering_multiplier:.2f}', 'name': grant.name, 'message': grant.message,
        'status': grant.status, 'stalled': stalled(grant), 'players': grant.players, 'processed': grant.processed,
        'affected': grant.affected, 'skipped': grant.skipped, 'total': f'{grant.total:.2f}', 'error': grant.error,
        'created_by': grant.created_by, 'created_at': grant.created_at.isoformat(),
        'finished_at': grant.finished_at.isoformat() if grant.finished_at else None,
        'undo_of': grant.undo_of_id, 'undone_by': getattr(getattr(grant, 'undone_by', None), 'pk', None),
        'can_undo': (grant.kind == BulkGrant.Kind.CREDIT and grant.status == BulkGrant.Status.DONE
                     and not BulkGrant.objects.filter(undo_of=grant).exists()),
    }
