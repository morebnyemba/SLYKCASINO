"""risk domain logic — the fraud engine.

Detectors (`on_*`, called from the money paths, and `sweep`, run hourly)
record RiskSignals. Each signal carries points by severity; a player's score is
the sum of their signals inside the window since their last review. Then:

- score >= review_score: the player is put **under review** — new withdrawal
  requests are held for staff and no new bonuses are credited. A case opens.
- score >= suspend_score, or any critical signal: the account is **suspended
  automatically**, withdrawals are frozen (and pending ones held), bonuses
  stop. A case opens.

Every case alerts staff (audit log, the console's queue badge, and email to
RISK_ALERT_EMAILS when set) and keeps every record. Only a superuser closes a
case; dismissing it lifts the restrictions, confirming keeps them.

Signals never block a player on their own except through these thresholds, and
an IP match alone is only ever a low signal (mobile carriers share IPs).
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Iterable, Optional

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from . import linking
from .models import RiskCase, RiskProfile, RiskSettings, RiskSignal

logger = logging.getLogger(__name__)
Severity = RiskSignal.Severity


# -- state ----------------------------------------------------------------------

def profile(player_id: int) -> RiskProfile:
    obj, _ = RiskProfile.objects.get_or_create(player_id=player_id)
    return obj


def withdrawals_blocked(player) -> Optional[str]:
    """Why this player can't withdraw at all right now (None = they can)."""
    if player.is_suspended:
        return 'Your account is suspended. Contact support.'
    if RiskProfile.objects.filter(player_id=player.id, withdrawals_frozen=True).exists():
        return 'Withdrawals are on hold while we review your account. Contact support.'
    return None


def needs_review(player_id: int) -> bool:
    return RiskProfile.objects.filter(player_id=player_id, under_review=True).exists()


def _score(prof: RiskProfile, cfg: RiskSettings) -> int:
    since = timezone.now() - timedelta(days=cfg.window_days)
    if prof.cleared_at and prof.cleared_at > since:
        since = prof.cleared_at
    return RiskSignal.objects.filter(player_id=prof.player_id, created_at__gt=since).aggregate(
        s=Sum('points'))['s'] or 0


# -- recording and acting ----------------------------------------------------------

@transaction.atomic
def flag(player_id: int, code: str, severity: str, detail: str, *, dedupe: str,
         data: Optional[dict] = None, linked: Iterable[int] = ()) -> Optional[RiskSignal]:
    """Record a finding (once per `dedupe`) and act on the player's new score.
    Returns the signal, or None if it was already recorded."""
    try:
        with transaction.atomic():
            signal = RiskSignal.objects.create(
                player_id=player_id, code=code, severity=severity, points=RiskSignal.POINTS[severity],
                detail=detail[:300], data=data or {}, linked_player_ids=sorted(set(linked)),
                dedupe_key=f'{code}:{player_id}:{dedupe}'[:200],
            )
    except IntegrityError:
        return None
    _act(player_id, signal)
    return signal


def _act(player_id: int, signal: RiskSignal) -> None:
    from apps.accounts.models import Player
    from apps.accounts import services as accounts_services

    cfg = RiskSettings.load()
    prof = RiskProfile.objects.select_for_update().get_or_create(player_id=player_id)[0]
    prof.score = _score(prof, cfg)
    suspend = signal.severity == Severity.CRITICAL or prof.score >= cfg.suspend_score
    review = suspend or prof.score >= cfg.review_score
    if not review:
        prof.save(update_fields=['score', 'updated_at'])
        return
    prof.under_review = True
    prof.bonus_blocked = True
    if suspend:
        prof.withdrawals_frozen = True
    prof.save()

    player = Player.objects.filter(pk=player_id).first()
    if player is None:
        return
    reason = f'{signal.get_severity_display()}: {signal.detail}'
    if suspend and not player.is_suspended:
        accounts_services.suspend_player(player_id, reason=f'Automatic fraud check — {reason}'[:255])
        accounts_services.audit(player_id, 'player_suspended', None, reason='automatic', signal=signal.code)
    if suspend:
        _hold_pending_withdrawals(player_id, reason)
    action = RiskCase.Action.SUSPENDED if suspend else RiskCase.Action.REVIEW
    case = RiskCase.objects.filter(player_id=player_id, status=RiskCase.Status.OPEN).first()
    if case is None:
        case = RiskCase.objects.create(player_id=player_id, action=action, reason=reason[:300], score=prof.score)
        accounts_services.audit(player_id, 'risk_case_opened', None, case_id=case.id, action=action,
                                score=prof.score, signal=signal.code)
        transaction.on_commit(lambda: _alert_staff(case.id))
    else:
        changed = case.score != prof.score or (suspend and case.action != action)
        case.score = prof.score
        if suspend:
            case.action = action
            case.reason = reason[:300]
        if changed:
            case.save(update_fields=['score', 'action', 'reason', 'updated_at'])


def _hold_pending_withdrawals(player_id: int, reason: str) -> None:
    from apps.wallet.models import WithdrawalRequest
    WithdrawalRequest.objects.filter(player_id=player_id, status=WithdrawalRequest.Status.REQUESTED,
                                     risk_hold=False).update(risk_hold=True, risk_note=reason[:300])


def _alert_staff(case_id: int) -> None:
    """Email the case to RISK_ALERT_EMAILS (best effort: the console's queue
    shows it either way)."""
    recipients = [e for e in getattr(settings, 'RISK_ALERT_EMAILS', []) if e]
    if not recipients:
        return
    from django.core.mail import send_mail

    from apps.accounts.models import Player
    case = RiskCase.objects.filter(pk=case_id).first()
    if case is None:
        return
    player = Player.objects.filter(pk=case.player_id).first()
    name = player.username if player else f'#{case.player_id}'
    try:
        send_mail(
            subject=f'[Fraud alert] {name}: {case.get_action_display()}',
            message=(f'Player {name} (#{case.player_id}) — {case.get_action_display()}.\n'
                     f'Score {case.score}. Reason: {case.reason}\n\n'
                     f'Review it in the console: Fraud & risk → case #{case.id}.'),
            from_email=None, recipient_list=recipients, fail_silently=False,
        )
    except Exception:  # noqa: BLE001 — never let an email failure undo the case
        logger.exception('could not email fraud alert for case %s', case_id)


@transaction.atomic
def decide(case_id: int, *, decision: str, note: str, by: str) -> RiskCase:
    """A superuser closes a case. `dismiss`: the findings were innocent — lift
    the review, freeze and bonus block, reinstate an automatic suspension and
    release held withdrawals. `confirm`: fraud — restrictions stay."""
    from apps.accounts import services as accounts_services
    from apps.wallet.models import WithdrawalRequest

    case = RiskCase.objects.select_for_update().get(pk=case_id)
    if case.status != RiskCase.Status.OPEN:
        raise ValueError('This case is already closed.')
    if decision not in ('dismiss', 'confirm'):
        raise ValueError('Choose dismiss or confirm.')
    if len((note or '').strip()) < 3:
        raise ValueError('Say why — it goes on the record.')
    now = timezone.now()
    if decision == 'dismiss':
        RiskProfile.objects.filter(player_id=case.player_id).update(
            under_review=False, withdrawals_frozen=False, bonus_blocked=False, score=0, cleared_at=now)
        if case.action == RiskCase.Action.SUSPENDED:
            accounts_services.unsuspend_player(case.player_id)
        WithdrawalRequest.objects.filter(player_id=case.player_id, risk_hold=True).update(risk_hold=False)
    case.status = RiskCase.Status.DISMISSED if decision == 'dismiss' else RiskCase.Status.CONFIRMED
    case.decided_at, case.decided_by, case.decision_note = now, by[:150], note.strip()[:500]
    case.save()
    return case


MAX_PURGE = 100


def purge_review(case_ids) -> dict:
    """Dry run for confirm-and-delete: which open cases' players would be
    permanently deleted, who can't be (and why), and what they hold. Nothing
    changes."""
    from decimal import Decimal

    from apps.accounts import services as accounts_services
    from apps.accounts.models import Player

    cases = list(RiskCase.objects.filter(pk__in=list(case_ids)[:MAX_PURGE + 1]).order_by('id'))
    if len(cases) > MAX_PURGE:
        raise ValueError(f'Permanent deletion is limited to {MAX_PURGE} cases at a time. Select fewer.')
    people = {p.id: p for p in Player.objects.filter(pk__in={c.player_id for c in cases}).select_related('user')}
    deletable, skipped, forfeited, open_bets = [], [], Decimal('0'), 0
    for case in cases:
        player = people.get(case.player_id)
        reason = ''
        if case.status != RiskCase.Status.OPEN:
            reason = 'Case already closed'
        elif player is None:
            reason = 'Player already deleted'
        else:
            check = accounts_services.deletion_check(player.id)
            if check['is_staff']:
                reason = 'Staff account'
        if reason:
            skipped.append({'case_id': case.id, 'player_id': case.player_id,
                            'username': player.username if player else None, 'reason': reason})
            continue
        deletable.append((case, player))
        forfeited += Decimal(check['balance'])
        open_bets += check['open_bets']
    return {'requested': len(cases), 'deletable': len(deletable), 'skipped': skipped, 'skipped_count': len(skipped),
            'balance_forfeited': str(forfeited), 'open_bets_discarded': open_bets,
            'confirm_phrase': f'DELETE {len(deletable)}', '_deletable': deletable}


def confirm_and_delete(case_ids, *, note: str, by: str, request=None, confirm: str, single: bool = False) -> dict:
    """Confirm these open cases as fraud and permanently delete each player —
    the way fraud accounts leave the platform. Their money is forfeited. The
    case stays on record as confirmed (with the username and what was
    forfeited, since the account is gone), and so do the fraud signals and
    identity links, so repeat signups from the same ring are still caught.
    `confirm` must be "DELETE <n>" for the number deletable right now, unless
    `single` (the caller has checked the username)."""
    from apps.accounts import services as accounts_services

    review = purge_review(case_ids)
    deletable = review.pop('_deletable')
    if not deletable:
        raise ValueError('None of these cases can be deleted.')
    if not single and (confirm or '').strip() != f'DELETE {len(deletable)}':
        raise ValueError(f'Type DELETE {len(deletable)} to confirm. The list may have changed — review it again.')
    if len((note or '').strip()) < 3:
        raise ValueError('Say why — it goes on the record.')
    done, failed = [], []
    for case, player in deletable:
        username, check = player.username, accounts_services.deletion_check(player.id)
        try:
            with transaction.atomic():
                decide(case.id, decision='confirm', note=note, by=by)
                accounts_services.delete_player(player.id, confirm_username=username, force=True, deleted_by=by,
                                                request=request)
                closed = RiskCase.objects.get(pk=case.id)
                closed.decision_note = (f'{note.strip()[:300]} — account {username} deleted'
                                        f' (${check["balance"]} forfeited)')[:500]
                closed.save(update_fields=['decision_note'])
        except Exception as exc:  # noqa: BLE001 — one case must never stop the rest
            failed.append({'case_id': case.id, 'username': username, 'error': str(exc)[:200]})
            continue
        done.append(case.id)
    accounts_services.audit(None, 'risk_cases_confirmed_deleted', request, by=by, requested=review['requested'],
                            done=len(done), skipped=review['skipped_count'], failed=len(failed))
    return {'requested': review['requested'], 'done': len(done), 'skipped': review['skipped'],
            'skipped_count': review['skipped_count'], 'failed': failed, 'failed_count': len(failed)}


@transaction.atomic
def set_restrictions(player_id: int, *, withdrawals_frozen: Optional[bool] = None,
                     bonus_blocked: Optional[bool] = None) -> RiskProfile:
    prof = RiskProfile.objects.select_for_update().get_or_create(player_id=player_id)[0]
    if withdrawals_frozen is not None:
        prof.withdrawals_frozen = withdrawals_frozen
        if withdrawals_frozen:
            _hold_pending_withdrawals(player_id, 'Withdrawals frozen by staff')
    if bonus_blocked is not None:
        prof.bonus_blocked = bonus_blocked
    prof.save()
    return prof


def safely(detector, *args, **kwargs) -> None:
    """Run a detector without letting a bug in it break the money path that
    called it (signup, deposit, bet). Its writes are rolled back on error."""
    try:
        with transaction.atomic():
            detector(*args, **kwargs)
    except Exception:  # noqa: BLE001
        logger.exception('risk detector %s failed', getattr(detector, '__name__', detector))


# -- detectors -----------------------------------------------------------------

def _suspended(ids) -> set[int]:
    from apps.accounts.models import Player
    return set(Player.objects.filter(pk__in=list(ids), is_suspended=True).values_list('pk', flat=True))


def on_register(player_id: int, ip: Optional[str]) -> None:
    """Many accounts from one IP, or an IP a suspended account used."""
    from common.cloudflare import is_cloudflare
    if not ip or is_cloudflare(ip):
        return  # Cloudflare's address, not the player's: proves nothing
    cfg = RiskSettings.load()
    since = timezone.now() - timedelta(days=cfg.window_days)
    others = set(linking.players_on_ips([ip], exclude=player_id, since=since))
    bad = _suspended(others)
    if bad:
        flag(player_id, 'ip_of_suspended_account', Severity.MEDIUM,
             f'Signed up from an IP a suspended account used ({ip}).', dedupe=ip, linked=bad, data={'ip': ip})
    if len(others) >= cfg.signup_ip_accounts:
        flag(player_id, 'many_accounts_one_ip', Severity.LOW,
             f'{len(others) + 1} accounts from one IP ({ip}) in {cfg.window_days} days.',
             dedupe=ip, linked=others, data={'ip': ip, 'accounts': len(others) + 1})


def check_number(player_id: int, number: str, *, kind: str) -> None:
    """A deposit or payout number another account also uses."""
    others = linking.players_with_number(number, exclude=player_id)
    if not others:
        return
    tail = linking.normalize_number(number)
    bad = _suspended(others)
    severity = Severity.CRITICAL if bad else Severity.HIGH
    flag(player_id, f'shared_{kind}_number', severity,
         f'{kind.title()} number ••{tail[-4:]} is also used by {len(others)} other account(s)'
         + (' including a suspended one.' if bad else '.'),
         dedupe=tail, linked=others, data={'number_tail': tail[-4:], 'accounts': sorted(others)})


def on_deposit(player_id: int, *, amount: Decimal, phone: str = '') -> None:
    from apps.wallet.models import LedgerEntry
    if phone:
        check_number(player_id, phone, kind='deposit')
    cfg = RiskSettings.load()
    since = timezone.now() - timedelta(hours=24)
    total = LedgerEntry.objects.filter(wallet__player_id=player_id, kind='deposit', created_at__gte=since).aggregate(
        t=Sum('amount'))['t'] or Decimal('0')
    if total > cfg.deposit_volume_24h:
        flag(player_id, 'deposit_volume', Severity.MEDIUM, f'Deposited ${total:.2f} in 24 hours.',
             dedupe=timezone.localdate().isoformat(), data={'total': str(total)})


def on_stake(player_id: int, *, amount: Decimal) -> None:
    """A big bet very soon after signing up."""
    from apps.accounts.models import Player
    cfg = RiskSettings.load()
    if amount < cfg.big_bet_amount:
        return
    joined = Player.objects.filter(pk=player_id).values_list('created_at', flat=True).first()
    if joined and timezone.now() - joined < timedelta(hours=cfg.new_account_hours):
        flag(player_id, 'big_bet_new_account', Severity.MEDIUM,
             f'Staked ${amount:.2f} within {cfg.new_account_hours}h of signing up.',
             dedupe='first-day', data={'amount': str(amount)})


def on_withdrawal_request(req) -> None:
    from apps.wallet.models import LedgerEntry, WithdrawalRequest
    cfg = RiskSettings.load()
    if req.account_number:
        check_number(req.player_id, req.account_number, kind='payout')
    week = timezone.now() - timedelta(days=7)
    numbers = {linking.normalize_number(n) for n in WithdrawalRequest.objects.filter(
        player_id=req.player_id, created_at__gte=week).exclude(account_number='').values_list('account_number', flat=True)}
    if len(numbers) >= cfg.payout_numbers_7d:
        flag(req.player_id, 'payout_numbers_changing', Severity.MEDIUM,
             f'{len(numbers)} different payout numbers in 7 days.', dedupe=f'week:{timezone.localdate():%G-%V}',
             data={'numbers': len(numbers)})
    bonus_since = timezone.now() - timedelta(hours=cfg.withdraw_after_bonus_hours)
    if LedgerEntry.objects.filter(wallet__player_id=req.player_id, kind='bonus', created_at__gte=bonus_since).exists():
        flag(req.player_id, 'withdraw_after_bonus', Severity.MEDIUM,
             f'Asked to withdraw within {cfg.withdraw_after_bonus_hours}h of getting a bonus.',
             dedupe=f'req:{req.id}', data={'withdrawal_id': req.id})


def on_wallet_tamper(player_id: int, *, wallet: str, amount: str = '') -> None:
    """A withdrawal from Deposit/Bonus: the app never sends this, so the request
    was hand-crafted."""
    flag(player_id, 'wallet_tamper', Severity.CRITICAL,
         f'Tried to withdraw from the {wallet} wallet with a modified request.',
         dedupe=f'{wallet}:{timezone.now():%Y%m%d%H}', data={'wallet': wallet, 'amount': amount})


def bonus_refusal(player_id: int, promotion_code: str) -> Optional[str]:
    """Why this bonus must not be credited (None = it may be). Records the
    multi-account case as a signal."""
    if RiskProfile.objects.filter(player_id=player_id, bonus_blocked=True).exists():
        return 'bonuses blocked while the account is reviewed'
    from apps.promotions.models import PromotionClaim
    linked = linking.strongly_linked(player_id)
    if not linked:
        return None
    others = set(PromotionClaim.objects.filter(
        player_id__in=linked, promotion__code=promotion_code, bonus_credited=True,
    ).values_list('player_id', flat=True))
    if others:
        flag(player_id, 'duplicate_bonus', Severity.HIGH,
             f'Claimed a bonus ({promotion_code}) another account using the same payment number already got.',
             dedupe=promotion_code, linked=others, data={'promotion': promotion_code})
        return 'this bonus was already given to an account using the same payment number'
    return None


# -- periodic sweep -------------------------------------------------------------

def sweep(*, now=None) -> dict:
    """Hourly: patterns no single event shows.
    - big winnings over 7 days;
    - strongly linked accounts backing the same selection within 24 hours."""
    from apps.sportsbook.models import Bet
    from apps.wallet.models import LedgerEntry
    now = now or timezone.now()
    cfg = RiskSettings.load()
    found = {'winnings': 0, 'coordinated': 0}
    week = now - timedelta(days=7)
    rows = (LedgerEntry.objects.filter(created_at__gte=week, bucket='winnings', kind__in=('bet_payout', 'casino_credit'))
            .values('wallet__player_id').annotate(t=Sum('amount')).filter(t__gt=cfg.winnings_7d))
    for r in rows:
        if flag(r['wallet__player_id'], 'high_winnings', Severity.MEDIUM,
                f'${r["t"]:.2f} of bet winnings credited to Winnings in 7 days.', dedupe=f'week:{now:%G-%V}', data={'total': str(r['t'])}):
            found['winnings'] += 1

    day = now - timedelta(hours=24)
    groups: dict[tuple, set[int]] = {}
    for pid, event_id, outcome_id, selection in (Bet.objects.filter(placed_at__gte=day).exclude(player_id=None)
                                                 .values_list('player_id', 'event_ref_id', 'outcome_ref_id', 'selection')):
        key = ('o', outcome_id) if outcome_id else ('e', event_id, selection)
        if key[1] is not None:
            groups.setdefault(key, set()).add(pid)
    links: dict[int, set[int]] = {}
    for key, players in groups.items():
        if len(players) < 2:
            continue
        for pid in players:
            if pid not in links:
                links[pid] = linking.strongly_linked(pid)
            mates = links[pid] & players
            if mates and flag(pid, 'coordinated_betting', Severity.MEDIUM,
                              f'Backed the same selection as {len(mates)} account(s) sharing a payment number.',
                              dedupe=f'{key}', linked=mates, data={'selection': list(map(str, key))}):
                found['coordinated'] += 1
    return found
