"""A password lock on the whole revenue share, set by the founder (wallet 1's holder).

While it's set, the founder who set it opens the revenue share as usual; every
other admin — superusers included — is refused (HTTP 423) on every revenue-share
page and API, and in the Django admin, until they enter the password the
founder gives them. Entering it opens the revenue share for that login for
UNLOCK_HOURS. Changing or removing the password closes every opened session.

It guards the application, not the server: whoever can reach the database or
run commands on the server can still read the data, and can clear a forgotten
password with `manage.py revenue_lock --clear`.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.utils import timezone

from apps.accounts import services as accounts_services

from .models import RevenueSettings
from .services import RevenueError

UNLOCK_HOURS = 8
MIN_LENGTH = 8
TRIES = 5
TRY_WINDOW = timedelta(minutes=15)
# Paths the lock covers (the lock's own endpoints excepted).
GUARDED = ('/api/admin/revenue-share/', '/api/admin/settings-changes/', '/api/admin/liabilities/partners/',
           '/django-admin/revenue/')
OPEN = ('/api/admin/revenue-share/lock/',)


def _cfg() -> RevenueSettings:
    return RevenueSettings.load()


def is_locked(cfg: Optional[RevenueSettings] = None) -> bool:
    return bool((cfg or _cfg()).lock_hash)


def _version(cfg: RevenueSettings) -> str:
    return str(int(cfg.lock_set_at.timestamp() * 1000)) if cfg.lock_set_at else '0'


def _grant_key(user, cfg: RevenueSettings) -> str:
    return f'revenue:unlock:{user.pk}:{_version(cfg)}'


def can_manage(user, cfg: Optional[RevenueSettings] = None) -> bool:
    """Who may set, change or remove the password: whoever set it; with no lock, the founder."""
    from .audit import is_founder
    cfg = cfg or _cfg()
    if not (user and user.is_authenticated):
        return False
    if is_locked(cfg):
        return cfg.lock_owner_id == user.pk
    return is_founder(user)


def has_access(user, cfg: Optional[RevenueSettings] = None) -> bool:
    cfg = cfg or _cfg()
    if not is_locked(cfg):
        return True
    if user is None or not user.is_authenticated:
        return False
    if cfg.lock_owner_id == user.pk:
        return True
    try:
        return bool(cache.get(_grant_key(user, cfg)))
    except Exception:  # noqa: BLE001 — no cache: nobody but the owner gets in
        return False


def guarded(path: str) -> bool:
    return path.startswith(GUARDED) and not path.startswith(OPEN)


def status_for(user) -> dict:
    cfg = _cfg()
    return {'locked': is_locked(cfg), 'owner': cfg.lock_owner.get_username() if cfg.lock_owner_id else None,
            'set_at': cfg.lock_set_at, 'can_manage': can_manage(user, cfg), 'has_access': has_access(user, cfg),
            'unlock_hours': UNLOCK_HOURS}


def set_password(user, password: str, *, current: str = '', request=None) -> None:
    cfg = _cfg()
    if not can_manage(user, cfg):
        raise RevenueError('Only the founder can lock the revenue share.' if not is_locked(cfg)
                           else 'Only the person who set the lock can change it.')
    if is_locked(cfg) and not check_password(current or '', cfg.lock_hash):
        raise RevenueError('The current password is wrong.')
    password = password or ''
    if len(password) < MIN_LENGTH:
        raise RevenueError(f'Use a password of at least {MIN_LENGTH} characters.')
    changed = is_locked(cfg)
    cfg.lock_hash, cfg.lock_owner, cfg.lock_set_at = make_password(password), user, timezone.now()
    cfg.save(update_fields=['lock_hash', 'lock_owner', 'lock_set_at', 'updated_at'])
    accounts_services.audit(None, 'revenue_lock_changed' if changed else 'revenue_locked', request, by=user.get_username())


def remove(user, password: str, *, request=None) -> None:
    cfg = _cfg()
    if not is_locked(cfg):
        return
    if not can_manage(user, cfg):
        raise RevenueError('Only the person who set the lock can remove it.')
    if not check_password(password or '', cfg.lock_hash):
        raise RevenueError('The password is wrong.')
    clear(by=user.get_username(), request=request)


def clear(*, by: str, request=None) -> None:
    """Remove the lock (also the server's recovery command)."""
    cfg = _cfg()
    cfg.lock_hash, cfg.lock_owner, cfg.lock_set_at = '', None, None
    cfg.save(update_fields=['lock_hash', 'lock_owner', 'lock_set_at', 'updated_at'])
    accounts_services.audit(None, 'revenue_unlocked_for_all', request, by=by)


def unlock(user, password: str, *, request=None) -> None:
    """Open the revenue share for this login for UNLOCK_HOURS. Five wrong tries
    in 15 minutes and the login waits."""
    cfg = _cfg()
    if not is_locked(cfg) or has_access(user, cfg):
        return
    key = f'revenue:unlock-tries:{user.pk}'
    tries = cache.get(key, 0)
    if tries >= TRIES:
        raise RevenueError('Too many wrong passwords. Try again in 15 minutes.')
    if not check_password(password or '', cfg.lock_hash):
        cache.set(key, tries + 1, int(TRY_WINDOW.total_seconds()))
        accounts_services.audit(None, 'revenue_unlock_failed', request, by=user.get_username())
        raise RevenueError('That password is wrong.')
    cache.delete(key)
    cache.set(_grant_key(user, cfg), True, UNLOCK_HOURS * 3600)
    accounts_services.audit(None, 'revenue_opened', request, by=user.get_username(), hours=UNLOCK_HOURS)


def close(user) -> None:
    """Lock it again for this login now (they'll need the password next time)."""
    cfg = _cfg()
    if is_locked(cfg):
        cache.delete(_grant_key(user, cfg))
