"""Revenue-share settings need every partner's co-signature.

A save to the revenue-share settings (each wallet's share, who holds each
wallet, the founder, the start date) made by a staff login is not applied: it is held as a SettingsChange with the exact request.
Every partner (the founder and each wallet holder) approves or rejects it; the
requester's own approval is implied. When the last partner approves, the
request is replayed as the person who made it, through the same view and
validation as before. One rejection drops it; open changes expire after 7 days;
once one change to a settings page is applied, other open changes to that page
are superseded (they were made against the old values). With no other partner
to ask (a single partner, or none set up yet) a save applies at once.
"""
from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.urls import resolve
from django.utils import timezone

from apps.accounts import services as accounts_services

from .models import ChangeVote, Decision, SettingsChange

EXPIRY = timedelta(days=7)
MAX_BODY = 2 * 1024 * 1024

GOVERNED = [
    (r'^/api/admin/revenue-share/settings/$', 'Revenue share settings — shares, wallet holders, founder'),
]
_COMPILED = [(re.compile(p), label) for p, label in GOVERNED]

# Django admin: the revenue-share records can't be edited there at all (it would skip co-signing).
DJANGO_ADMIN_LOCKED = ('revenue/',)


class ChangeError(ValueError):
    """Something the co-signing rules don't allow (shown to staff)."""


def governed(path: str) -> Optional[str]:
    for pattern, label in _COMPILED:
        if pattern.match(path):
            return label
    return None


def django_admin_locked(path: str) -> bool:
    rest = path[len('/django-admin/'):] if path.startswith('/django-admin/') else ''
    return bool(rest) and rest.startswith(DJANGO_ADMIN_LOCKED)


def _signers():
    from .audit import signers
    return signers()


def _json(raw: bytes, content_type: str):
    if 'json' not in (content_type or ''):
        return {'(form data)': f'{len(raw)} bytes'}
    try:
        return json.loads(raw.decode() or '{}')
    except (ValueError, UnicodeDecodeError):
        return {}


def _replay(user, method: str, path: str, body: bytes = b'', content_type: str = 'application/json'):
    """Run a request through its view as `user`, outside the middleware."""
    from rest_framework.test import APIRequestFactory, force_authenticate

    request = APIRequestFactory().generic(method, path, data=body, content_type=content_type or 'application/json')
    force_authenticate(request, user=user)
    match = resolve(path)
    response = match.func(request, *match.args, **match.kwargs)
    if hasattr(response, 'render'):
        response.render()
    return response


def revenue_settings_now() -> dict:
    """The revenue-share settings as the settings form sends them, with names."""
    from .models import RevenueSettings, ShareWallet
    cfg = RevenueSettings.load()
    return {
        'share_percent': f'{cfg.share_percent:.2f}',
        'started_on': cfg.started_on.isoformat() if cfg.started_on else None,
        'founder_id': cfg.founder_id,
        'wallets': [{'slot': w.slot, 'label': w.label, 'holder_id': w.holder_id,
                     'holder': w.holder.get_username() if w.holder else None} for w in ShareWallet.ensure()],
    }


def _current(user, path: str):
    if path.startswith('/api/admin/revenue-share/settings/'):
        return revenue_settings_now()
    try:
        response = _replay(user, 'GET', path)
        if response.status_code == 200:
            data = json.loads(response.content or b'{}')
            text = json.dumps(data)
            return data if len(text) < 200_000 else {'(too large to show)': len(text)}
    except Exception:  # noqa: BLE001 — the "before" view is best-effort
        pass
    return {}


def hold(request, user) -> Optional[SettingsChange]:
    """Called by the middleware for a governed save. Returns the held change,
    or None when there is no other partner to ask (the save goes ahead)."""
    others = [u for u in _signers() if u.pk != user.pk]
    if not others:
        return None
    raw = request.body
    if len(raw) > MAX_BODY:
        raise ChangeError('That change is too large to hold for co-signing.')
    change = SettingsChange.objects.create(
        label=governed(request.path) or request.path, method=request.method, path=request.path,
        content_type=request.META.get('CONTENT_TYPE', ''), body=raw, before=_current(user, request.path),
        requested=_json(raw, request.META.get('CONTENT_TYPE', '')), requested_by=user,
    )
    if any(u.pk == user.pk for u in _signers()):
        ChangeVote.objects.create(change=change, user=user, decision=Decision.APPROVE, note='Requested')
    accounts_services.audit(None, 'settings_change_requested', request, id=change.id, label=change.label,
                            path=change.path, by=user.get_username())
    return change


def _expire() -> None:
    SettingsChange.objects.filter(status=SettingsChange.Status.OPEN, created_at__lt=timezone.now() - EXPIRY).update(
        status=SettingsChange.Status.EXPIRED, decided_at=timezone.now())


def waiting_for(change: SettingsChange) -> list[str]:
    if change.status != SettingsChange.Status.OPEN:
        return []
    voted = set(change.votes.values_list('user_id', flat=True))
    return [u.get_username() for u in _signers() if u.pk not in voted]


def _username(user_id) -> Optional[str]:
    from django.contrib.auth import get_user_model
    if user_id in (None, ''):
        return None
    u = get_user_model().objects.filter(pk=user_id).first()
    return u.get_username() if u else f'#{user_id}'


def diff(change: SettingsChange) -> list[dict]:
    """The fields the change would alter: field, before, after (people by name)."""
    before, after = change.before, change.requested
    if not isinstance(after, dict):
        return [{'field': '(change)', 'before': before, 'after': after}]
    rows = []
    if isinstance(before, dict) and 'wallets' in before:
        old_wallets = {w['slot']: w for w in before.get('wallets') or []}
        for w in after.get('wallets') or []:
            old = old_wallets.get(w.get('slot'), {})
            if 'holder_id' in w and str(w.get('holder_id') or '') != str(old.get('holder_id') or ''):
                rows.append({'field': f'Wallet {w.get("slot")} holder', 'before': old.get('holder'),
                             'after': _username(w.get('holder_id'))})
            if 'label' in w and (w.get('label') or '') != (old.get('label') or ''):
                rows.append({'field': f'Wallet {w.get("slot")} name', 'before': old.get('label'), 'after': w.get('label')})
        if 'founder_id' in after and str(after.get('founder_id') or '') != str(before.get('founder_id') or ''):
            rows.append({'field': 'Founder', 'before': _username(before.get('founder_id')) or 'Wallet 1’s holder',
                         'after': _username(after.get('founder_id')) or 'Wallet 1’s holder'})
        for key in ('share_percent', 'started_on'):
            if after.get(key) not in (None, '') and str(after.get(key)) != str(before.get(key)):
                try:
                    if key == 'share_percent' and float(after[key]) == float(before.get(key) or 0):
                        continue
                except (TypeError, ValueError):
                    pass
                rows.append({'field': key, 'before': before.get(key), 'after': after.get(key)})
        return rows
    for key, value in after.items():
        old = before.get(key) if isinstance(before, dict) else None
        if str(old) != str(value):
            rows.append({'field': key, 'before': old, 'after': value})
    return rows


def change_row(change: SettingsChange, *, user=None) -> dict:
    voted = {v.user_id: v for v in change.votes.select_related('user')}
    return {
        'id': change.id, 'label': change.label, 'method': change.method, 'path': change.path,
        'requested_by': change.requested_by.get_username(), 'status': change.status,
        'status_label': change.get_status_display(), 'created_at': change.created_at.isoformat(),
        'decided_at': change.decided_at.isoformat() if change.decided_at else None,
        'expires_at': (change.created_at + EXPIRY).isoformat(), 'diff': diff(change),
        'votes': [{'user': v.user.get_username(), 'decision': v.decision, 'note': v.note} for v in voted.values()],
        'waiting_for': waiting_for(change), 'result_detail': change.result_detail,
        'can_vote': bool(user and change.status == SettingsChange.Status.OPEN and user.pk not in voted
                         and any(u.pk == user.pk for u in _signers())),
        'can_cancel': bool(user and change.status == SettingsChange.Status.OPEN and change.requested_by_id == user.pk),
    }


def pending_for(user) -> int:
    _expire()
    if not any(u.pk == user.pk for u in _signers()):
        return 0
    return sum(1 for c in SettingsChange.objects.filter(status=SettingsChange.Status.OPEN) if user.get_username() in waiting_for(c))


def vote(change_id: int, *, user, decision: str, note: str = '', request=None) -> SettingsChange:
    _expire()                       # outside the vote's transaction, so a refused vote keeps the expiry
    return _vote(change_id, user=user, decision=decision, note=note, request=request)


@transaction.atomic
def _vote(change_id: int, *, user, decision: str, note: str = '', request=None) -> SettingsChange:
    change = SettingsChange.objects.select_for_update().filter(pk=change_id).first()
    if change is None or change.status != SettingsChange.Status.OPEN:
        raise ChangeError('That change isn’t waiting for co-signatures.')
    if not any(u.pk == user.pk for u in _signers()):
        raise ChangeError('Only the founder and the partners holding a wallet co-sign settings changes.')
    if decision not in Decision.values:
        raise ChangeError('Approve or reject.')
    note = (note or '').strip()
    if decision == Decision.REJECT and len(note) < 5:
        raise ChangeError('Say why you reject it.')
    ChangeVote.objects.update_or_create(change=change, user=user, defaults={'decision': decision, 'note': note[:500]})
    accounts_services.audit(None, 'settings_change_vote', request, id=change.id, label=change.label,
                            decision=decision, note=note, by=user.get_username())
    if decision == Decision.REJECT:
        change.status, change.decided_at = SettingsChange.Status.REJECTED, timezone.now()
        change.save(update_fields=['status', 'decided_at'])
        return change
    if not waiting_for(change):
        _apply(change)
    return change


def _apply(change: SettingsChange) -> None:
    user = change.requested_by
    if not (user.is_active and user.is_staff):
        change.status, change.result_detail = SettingsChange.Status.FAILED, 'The person who asked for it no longer has a staff login.'
    else:
        try:
            response = _replay(user, change.method, change.path, bytes(change.body), change.content_type)
            change.result_status = response.status_code
            ok = response.status_code < 400
            detail = ''
            if not ok:
                try:
                    detail = str(json.loads(response.content).get('detail') or response.content[:500].decode())
                except (ValueError, AttributeError, UnicodeDecodeError):
                    detail = f'HTTP {response.status_code}'
            change.status = SettingsChange.Status.APPLIED if ok else SettingsChange.Status.FAILED
            change.result_detail = detail[:1000]
        except Exception as exc:  # noqa: BLE001 — record why, never half-apply silently
            change.status, change.result_detail = SettingsChange.Status.FAILED, str(exc)[:1000]
    change.decided_at = timezone.now()
    change.save(update_fields=['status', 'result_status', 'result_detail', 'decided_at'])
    if change.status == SettingsChange.Status.APPLIED:
        SettingsChange.objects.filter(status=SettingsChange.Status.OPEN, path=change.path).exclude(pk=change.pk).update(
            status=SettingsChange.Status.SUPERSEDED, decided_at=timezone.now())
    accounts_services.audit(None, 'settings_change_applied', None, id=change.id, label=change.label,
                            status=change.status, detail=change.result_detail)


@transaction.atomic
def cancel(change_id: int, *, user) -> SettingsChange:
    change = SettingsChange.objects.select_for_update().filter(pk=change_id, requested_by=user,
                                                               status=SettingsChange.Status.OPEN).first()
    if change is None:
        raise ChangeError('Only an open change of your own can be withdrawn.')
    change.status, change.decided_at = SettingsChange.Status.CANCELLED, timezone.now()
    change.save(update_fields=['status', 'decided_at'])
    return change
