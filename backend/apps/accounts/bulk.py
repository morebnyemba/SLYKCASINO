"""Bulk actions on players, for the admin player list.

One action at a time on a chosen set of players (ids, or everyone matching the
list filters). Each player is handled on its own: one that can't be changed is
reported, never allowed to stop the rest. Staff accounts are never suspended,
frozen or blocked in bulk. Lifting a restriction is superuser-only, as it is
one player at a time (risk.PlayerRiskView).

Permanent deletion is here too, with more guards than any other action:
superuser only, at most MAX_DELETE players a call, a dry run that shows what
would go (and what is blocked and why) before anything is touched, and a typed
"DELETE <n>" naming the exact number. It reuses services.delete_player, so
every per-player rule still holds — staff accounts and players with an open
fraud case are never deleted, and unless "force" is set neither are players
who still hold money or open bets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from django.db import transaction

from . import services
from .models import Player

MAX_PLAYERS = 500
MAX_DELETE = 100

SUSPEND, UNSUSPEND = 'suspend', 'unsuspend'
FREEZE, UNFREEZE = 'freeze_withdrawals', 'unfreeze_withdrawals'
BLOCK_BONUS, UNBLOCK_BONUS = 'block_bonus', 'unblock_bonus'
NOTIFY = 'notify'
DELETE = 'delete'

ACTIONS = (SUSPEND, UNSUSPEND, FREEZE, UNFREEZE, BLOCK_BONUS, UNBLOCK_BONUS, NOTIFY, DELETE)
SUPERUSER_ONLY = (UNFREEZE, UNBLOCK_BONUS, DELETE)
SPARES_STAFF = (SUSPEND, FREEZE, BLOCK_BONUS)


class BulkError(Exception):
    """The request itself is wrong (nothing was changed)."""


@dataclass
class Result:
    action: str
    requested: int = 0
    done: list[int] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {'action': self.action, 'requested': self.requested, 'done': len(self.done),
                'skipped': self.skipped[:50], 'skipped_count': len(self.skipped),
                'failed': self.failed[:50], 'failed_count': len(self.failed), **self.extra}


def _is_staff(player: Player) -> bool:
    user = player.user
    return bool(user and (user.is_staff or user.is_superuser))


def _apply(action: str, player: Player, options: dict) -> Optional[str]:
    """Do `action` on one player. Returns a reason it was skipped, else None."""
    from apps.risk import services as risk
    if action == SUSPEND:
        if player.is_suspended:
            return 'Already suspended'
        services.suspend_player(player.id, reason=options['reason'])
    elif action == UNSUSPEND:
        if not player.is_suspended:
            return 'Not suspended'
        services.unsuspend_player(player.id)
    elif action in (FREEZE, UNFREEZE):
        frozen = action == FREEZE
        if risk.profile(player.id).withdrawals_frozen == frozen:
            return 'Withdrawals already frozen' if frozen else 'Withdrawals not frozen'
        risk.set_restrictions(player.id, withdrawals_frozen=frozen)
    elif action in (BLOCK_BONUS, UNBLOCK_BONUS):
        blocked = action == BLOCK_BONUS
        if risk.profile(player.id).bonus_blocked == blocked:
            return 'Bonuses already blocked' if blocked else 'Bonuses not blocked'
        risk.set_restrictions(player.id, bonus_blocked=blocked)
    elif action == NOTIFY:
        from apps.notifications import services as notifications
        notifications.notify(player.id, 'account_alert', options['title'], options['body'])
    return None


def _delete(players, options: dict, request) -> Result:
    """Permanently delete the players that can be deleted. With `dry_run`, only
    report who could be and who is blocked. Otherwise `confirm` must be exactly
    "DELETE <n>", n being how many are deletable right now."""
    force = bool(options.get('force'))
    players = list(players.select_related('user')[:MAX_DELETE + 1])
    if len(players) > MAX_DELETE:
        raise BulkError(f'Permanent deletion is limited to {MAX_DELETE} players at a time. Select fewer.')
    result = Result(action=DELETE, requested=len(players))
    deletable, discarded, open_bets = [], Decimal('0'), 0
    for player in players:
        check = services.deletion_check(player.id)
        reason = 'Staff account' if check['is_staff'] else services.deletion_blocker(player.id, check, force=force)
        if reason:
            result.skipped.append({'id': player.id, 'username': player.username, 'reason': reason[:200]})
            continue
        deletable.append(player)
        discarded += Decimal(check['balance'])
        open_bets += check['open_bets']
    result.extra = {'deletable': len(deletable), 'balance_discarded': str(discarded), 'open_bets_discarded': open_bets,
                    'confirm_phrase': f'DELETE {len(deletable)}'}
    if options.get('dry_run'):
        result.extra['dry_run'] = True
        return result
    if not deletable:
        raise BulkError('None of these players can be deleted.')
    if str(options.get('confirm') or '').strip() != f'DELETE {len(deletable)}':
        raise BulkError(f'Type DELETE {len(deletable)} to confirm. The list may have changed — review it again.')
    for player in deletable:
        try:
            services.delete_player(player.id, confirm_username=player.username, force=force,
                                   deleted_by=request.user.get_username(), request=request)
        except Exception as exc:  # noqa: BLE001 — one player must never stop the rest
            result.failed.append({'id': player.id, 'username': player.username, 'error': str(exc)[:200]})
            continue
        result.done.append(player.id)
    services.audit(None, 'players_bulk_action', request, action=DELETE, by=request.user.get_username(),
                   requested=result.requested, done=len(result.done), skipped=len(result.skipped),
                   failed=len(result.failed), forced=force)
    return result


def run(action: str, players, *, options: dict, request) -> Result:
    """Apply `action` to `players` (a queryset of Player), auditing each change."""
    if action not in ACTIONS:
        raise BulkError('Unknown action.')
    if action in SUPERUSER_ONLY and not request.user.is_superuser:
        raise BulkError('Only a superuser can delete players or lift a restriction.')
    if action == DELETE:
        return _delete(players, options, request)
    options = dict(options)
    if action == SUSPEND:
        options['reason'] = str(options.get('reason') or '').strip()[:255]
        if len(options['reason']) < 3:
            raise BulkError('Say why you are suspending these players.')
    if action == NOTIFY:
        options['title'] = str(options.get('title') or '').strip()[:120]
        options['body'] = str(options.get('body') or '').strip()[:2000]
        if len(options['title']) < 3:
            raise BulkError('Give the message a title.')

    players = list(players.select_related('user')[:MAX_PLAYERS + 1])
    if len(players) > MAX_PLAYERS:
        raise BulkError(f'That is more than {MAX_PLAYERS} players. Narrow the search and try again.')
    result = Result(action=action, requested=len(players))
    for player in players:
        if action in SPARES_STAFF and _is_staff(player):
            result.skipped.append({'id': player.id, 'username': player.username, 'reason': 'Staff account'})
            continue
        try:
            with transaction.atomic():
                skipped = _apply(action, player, options)
        except Exception as exc:  # noqa: BLE001 — one player must never stop the rest
            result.failed.append({'id': player.id, 'username': player.username, 'error': str(exc)[:200]})
            continue
        if skipped:
            result.skipped.append({'id': player.id, 'username': player.username, 'reason': skipped})
            continue
        result.done.append(player.id)
        services.audit(player.id, 'player_bulk_action', request, action=action, by=request.user.get_username(),
                       **({'reason': options['reason']} if action == SUSPEND else {}))
    services.audit(None, 'players_bulk_action', request, action=action, by=request.user.get_username(),
                   requested=result.requested, done=len(result.done), skipped=len(result.skipped),
                   failed=len(result.failed))
    return result
