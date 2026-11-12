"""The pool, open to inspection: a ledger with a running balance, and a weekly
audit where the founder's outside reports are matched line by line against
what the platform recorded.

Deposits — Paynow's report of money received vs. Paynow payments the platform
credited that week:
  matched · amount_mismatch · other_week (timing: the platform recorded it in
  a neighbouring week) · not_credited (Paynow says paid, the player was never
  credited) · unknown (no such payment on the platform) · missing_from_report
  (the platform credited money Paynow doesn't report — investigate first).
Payouts — the founder's report of money sent to players vs. withdrawals marked
paid that week: the same, with missing_from_report meaning "marked paid but
not in the founder's report".
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.accounts import services as accounts_services

from . import reports
from .models import (
    AuditSignature, Decision, PoolAudit, PoolExpense, PoolProposal, ProposalVote, RevenueDay, RevenueSettings, ShareEntry,
    ShareWallet, ShareWithdrawal,
)

CENT = Decimal('0.01')
ZERO = Decimal('0.00')
PROBLEM_ROWS = 300
KINDS = ('paynow', 'payouts')


class AuditError(ValueError):
    """Something the audit rules don't allow (shown to staff)."""


def _aware(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.min))


def _money(v) -> str:
    return str((v or ZERO).quantize(CENT))


def week_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def window(week_start: date) -> tuple[datetime, datetime]:
    return _aware(week_start), _aware(week_start + timedelta(days=7))


# -- who -------------------------------------------------------------------------

def founder():
    cfg = RevenueSettings.load()
    if cfg.founder_id:
        return cfg.founder
    first = ShareWallet.objects.filter(slot=1).select_related('holder').first()
    return first.holder if first else None


def is_founder(user) -> bool:
    f = founder()
    return bool(f and user and f.pk == user.pk)


def can_view(user) -> bool:
    return bool(user and (user.is_superuser or ShareWallet.objects.filter(holder=user).exists()))


# -- the pool ledger ---------------------------------------------------------------

def pool_ledger(*, start: Optional[date] = None, end: Optional[date] = None) -> dict:
    """Every movement of the operating pool in [start, end] with a running
    balance: each closed day's share in, that day's affiliate commissions out,
    and each recorded cost out. Opening balance = everything before `start`."""
    moves = []
    for d in RevenueDay.objects.order_by('day'):
        moves.append((d.day, 0, 'day', f'Day closed · GGR {_money(d.ggr)}', d.pool, None))
        if d.affiliate_costs:
            moves.append((d.day, 1, 'affiliates', 'Affiliate commissions', -d.affiliate_costs, None))
    for e in PoolExpense.objects.order_by('day', 'id'):
        moves.append((e.day, 2, 'expense', f'{e.get_category_display()}{" · " + e.note if e.note else ""} (by {e.recorded_by})',
                      -e.amount, e.id))
    moves.sort(key=lambda m: (m[0], m[1]))
    balance, opening, rows = ZERO, ZERO, []
    total_in, total_out = ZERO, ZERO
    for day, _, kind, label, amount, ref in moves:
        balance += amount
        if start and day < start:
            opening = balance
            continue
        if end and day > end:
            continue
        total_in += max(amount, ZERO)
        total_out += -min(amount, ZERO)
        rows.append({'day': day.isoformat(), 'kind': kind, 'label': label, 'amount': _money(amount),
                     'balance': _money(balance), 'expense_id': ref})
    return {'opening': _money(opening), 'in': _money(total_in), 'out': _money(total_out),
            'closing': rows[-1]['balance'] if rows else _money(opening), 'rows': rows}


def affiliate_costs_on(day: date) -> list[dict]:
    """The commissions behind a closed day's 'Affiliate commissions' line."""
    from apps.affiliates.models import Commission

    start, end = _aware(day), _aware(day + timedelta(days=1))
    qs = (Commission.objects.filter(status__in=(Commission.Status.APPROVED, Commission.Status.PAID),
                                    decided_at__gte=start, decided_at__lt=end)
          .select_related('affiliate').order_by('affiliate__code', 'id'))
    return [{'agent': c.affiliate.code, 'kind': c.get_kind_display(), 'period': c.period.isoformat() if c.period else '',
             'ticket': c.ticket, 'base': _money(c.base_amount), 'rate': str(c.rate), 'amount': _money(c.amount)} for c in qs]


# -- the platform's figures for a week ------------------------------------------------

def _paid_deposits(start, end):
    from apps.wallet.models import PaymentTransaction
    return PaymentTransaction.objects.filter(status=PaymentTransaction.Status.PAID).filter(
        Q(completed_at__gte=start, completed_at__lt=end) | Q(completed_at__isnull=True, updated_at__gte=start, updated_at__lt=end))


def _paid_withdrawals(start, end):
    from apps.wallet.models import WithdrawalRequest
    return WithdrawalRequest.objects.filter(status=WithdrawalRequest.Status.PAID, decided_at__gte=start, decided_at__lt=end)


def snapshot(week_start: date) -> dict:
    start, end = window(week_start)
    last = week_start + timedelta(days=6)
    deposits = _paid_deposits(start, end)
    withdrawals = list(_paid_withdrawals(start, end).values_list('amount', 'fee'))
    days = RevenueDay.objects.filter(day__gte=week_start, day__lte=last)
    agg = days.aggregate(ggr=Sum('ggr'), pool=Sum('pool'), aff=Sum('affiliate_costs'), share=Sum('share_each'))
    expenses = PoolExpense.objects.filter(day__gte=week_start, day__lte=last).aggregate(t=Sum('amount'))['t'] or ZERO
    partners = (ShareWithdrawal.objects.filter(status=ShareWithdrawal.Status.PAID, decided_at__gte=start, decided_at__lt=end)
                .aggregate(t=Sum('amount'))['t'] or ZERO)
    return {
        'deposits': {'count': deposits.count(), 'total': _money(deposits.aggregate(t=Sum('amount'))['t'])},
        'payouts': {'count': len(withdrawals), 'requested': _money(sum((a for a, _ in withdrawals), ZERO)),
                    'fees': _money(sum((f for _, f in withdrawals), ZERO)),
                    'sent': _money(sum((a - f for a, f in withdrawals), ZERO))},
        'ggr': _money(agg['ggr']), 'days_closed': days.count(),
        'pool_in': _money(agg['pool']), 'affiliate_costs': _money(agg['aff']), 'expenses': _money(expenses),
        'partner_shares': _money((agg['share'] or ZERO) * 3), 'partner_withdrawals': _money(partners),
        'pool_balance_end': pool_ledger(end=last)['closing'],
    }


# -- matching ------------------------------------------------------------------------

def _result(rows, problems, matched, system_total, report_total, extra) -> dict:
    counts = defaultdict(int)
    for p in problems:
        counts[p['issue']] += 1
    counts['matched'] = matched
    return {'counts': dict(counts), 'report_total': _money(report_total), 'system_total': _money(system_total),
            'difference': _money(report_total - system_total), 'rows': len(rows),
            'balanced': not any(p['issue'] != 'other_week' for p in problems) and report_total == system_total,
            'problems': problems[:PROBLEM_ROWS], **extra}


def match_deposits(week_start: date, rows: list[reports.ReportRow]) -> dict:
    from apps.wallet.models import PaymentTransaction

    start, end = window(week_start)
    week = {tx.pk: tx for tx in _paid_deposits(start, end)}
    refs = {reports.norm_ref(r.reference) for r in rows if r.reference} | {reports.norm_ref(r.provider_ref) for r in rows if r.provider_ref}
    known = list(week.values()) + list(PaymentTransaction.objects.filter(
        Q(reference__in=refs) | Q(provider_ref__in=refs)).exclude(pk__in=list(week)))
    by_ref = {}
    for tx in known:
        for key in (tx.reference, tx.provider_ref):
            if key:
                by_ref.setdefault(reports.norm_ref(key), tx)
    problems, matched, seen, report_total = [], 0, set(), ZERO
    for r in rows:
        report_total += r.amount
        tx = by_ref.get(reports.norm_ref(r.reference)) or by_ref.get(reports.norm_ref(r.provider_ref))
        base = {'line': r.line, 'reference': r.reference or r.provider_ref, 'amount': _money(r.amount), 'when': r.when}
        if tx is None:
            problems.append({**base, 'issue': 'unknown', 'detail': 'No such payment on the platform.'})
            continue
        seen.add(tx.pk)
        base.update({'system_amount': _money(tx.amount), 'player_id': tx.player_id})
        if tx.status != PaymentTransaction.Status.PAID:
            problems.append({**base, 'issue': 'not_credited', 'detail': f'Paynow says paid; the platform has it as {tx.status} — the player was never credited.'})
        elif tx.amount != r.amount:
            problems.append({**base, 'issue': 'amount_mismatch', 'detail': f'Platform credited {_money(tx.amount)}.'})
        elif tx.pk not in week:
            problems.append({**base, 'issue': 'other_week', 'detail': 'The platform recorded it in a neighbouring week (timing).'})
        else:
            matched += 1
    for tx in week.values():
        if tx.pk not in seen:
            problems.append({'line': None, 'reference': tx.reference, 'amount': None, 'system_amount': _money(tx.amount),
                             'player_id': tx.player_id, 'when': (tx.completed_at or tx.updated_at).isoformat(),
                             'issue': 'missing_from_report', 'detail': 'Credited on the platform but not in Paynow’s report.'})
    system_total = sum((tx.amount for tx in week.values()), ZERO)
    return _result(rows, problems, matched, system_total, report_total, {})


def match_payouts(week_start: date, rows: list[reports.ReportRow]) -> dict:
    from apps.risk.linking import normalize_number
    from apps.wallet.models import WithdrawalRequest

    start, end = window(week_start)
    week = list(_paid_withdrawals(start, end).order_by('decided_at', 'id'))
    week_ids = {w.pk for w in week}
    refs = {reports.norm_ref(r.reference) for r in rows if r.reference}
    ids = {int(r.request_id) for r in rows if r.request_id.isdigit()}
    others = list(WithdrawalRequest.objects.filter(status=WithdrawalRequest.Status.PAID)
                  .filter(Q(reference__in=refs) | Q(pk__in=ids)).exclude(pk__in=week_ids)) if (refs or ids) else []
    pool = week + others
    by_ref = {reports.norm_ref(w.reference): w for w in pool if w.reference}
    by_id = {w.pk: w for w in pool}
    problems, matched, used, report_total = [], 0, set(), ZERO
    for r in rows:
        report_total += r.amount
        w = by_ref.get(reports.norm_ref(r.reference)) if r.reference else None
        if w is None and r.request_id.isdigit():
            w = by_id.get(int(r.request_id))
        if w is None and r.account:
            number = normalize_number(r.account)
            candidates = [x for x in week if x.pk not in used and number and normalize_number(x.account_number) == number]
            w = next((x for x in candidates if r.amount in (x.payout_amount, x.amount)), candidates[0] if candidates else None)
        base = {'line': r.line, 'reference': r.reference or r.request_id, 'account': r.account, 'amount': _money(r.amount), 'when': r.when}
        if w is None or w.pk in used:
            problems.append({**base, 'issue': 'unknown', 'detail': 'No withdrawal on the platform matches this payment.'})
            continue
        used.add(w.pk)
        base.update({'system_amount': _money(w.payout_amount), 'player_id': w.player_id, 'request_id': w.pk})
        if r.amount not in (w.payout_amount, w.amount):
            problems.append({**base, 'issue': 'amount_mismatch',
                             'detail': f'Platform: {_money(w.amount)} requested, {_money(w.payout_amount)} to send after the fee.'})
        elif w.pk not in week_ids:
            problems.append({**base, 'issue': 'other_week', 'detail': 'Marked paid on the platform in a neighbouring week (timing).'})
        else:
            matched += 1
    for w in week:
        if w.pk not in used:
            problems.append({'line': None, 'reference': w.reference, 'account': w.account_number, 'amount': None,
                             'system_amount': _money(w.payout_amount), 'player_id': w.player_id, 'request_id': w.pk,
                             'when': w.decided_at.isoformat(), 'issue': 'missing_from_report',
                             'detail': f'Marked paid on the platform (by {w.decided_by or "?"}) but not in the payouts report.'})
    system_total = sum((w.payout_amount for w in week), ZERO)
    return _result(rows, problems, matched, system_total, report_total, {})


# -- who signs --------------------------------------------------------------------

def signers() -> list:
    """Everyone whose approval a week or a use of the pool needs: the founder
    and every partner holding a wallet."""
    people = {}
    f = founder()
    if f is not None:
        people[f.pk] = f
    for w in ShareWallet.objects.filter(holder__isnull=False, holder__is_active=True).select_related('holder'):
        people.setdefault(w.holder_id, w.holder)
    return list(people.values())


def is_signer(user) -> bool:
    return bool(user and any(u.pk == user.pk for u in signers()))


# -- the weekly audit ------------------------------------------------------------------

def deadline(week_start: date) -> datetime:
    """Due by the end of the Tuesday after the week."""
    return _aware(week_start + timedelta(days=9))


def counted(week_start: date) -> bool:
    cfg = RevenueSettings.load()
    return bool(cfg.audits_from and week_start >= cfg.audits_from)


def ensure_weeks(*, today: Optional[date] = None) -> int:
    """One audit per completed week since revenue sharing started. Idempotent."""
    today = today or timezone.localdate()
    cfg = RevenueSettings.load()
    if not cfg.started_on:
        return 0
    created, week = 0, week_of(cfg.started_on)
    if cfg.audits_from:
        week = max(week, cfg.audits_from)
    while week + timedelta(days=7) <= today:
        _, made = PoolAudit.objects.get_or_create(week_start=week)
        created += made
        week += timedelta(days=7)
    return created


def outstanding(a: PoolAudit) -> list[str]:
    """Who still has to act on this week."""
    if a.status == PoolAudit.Status.APPROVED:
        return []
    f = founder()
    if a.status in (PoolAudit.Status.OPEN, PoolAudit.Status.DISPUTED):
        return [f'{f.get_username() if f else "The founder"} (submit)']
    signed = set(a.signatures.filter(decision=Decision.APPROVE).values_list('user_id', flat=True))
    return [u.get_username() for u in signers() if u.pk not in signed]


def audit_row(a: PoolAudit, *, user=None) -> dict:
    sigs = [{'user': s.user.get_username(), 'decision': s.decision, 'note': s.note, 'at': s.created_at.isoformat()}
            for s in a.signatures.select_related('user').order_by('created_at')]
    live = a.status != PoolAudit.Status.APPROVED
    system = snapshot(a.week_start) if live else a.snapshot
    expected = a.expected_balance if a.expected_balance is not None else Decimal(system['pool_balance_end'])
    mine = a.signatures.filter(user=user).first() if user else None
    return {
        'week_start': a.week_start.isoformat(), 'week_end': (a.week_start + timedelta(days=6)).isoformat(),
        'due': deadline(a.week_start).isoformat(), 'counted': counted(a.week_start),
        'overdue': live and counted(a.week_start) and timezone.now() >= deadline(a.week_start),
        'status': a.status, 'status_label': a.get_status_display(), 'system': system,
        'paynow': a.paynow_result or None, 'payouts': a.payouts_result or None,
        'paynow_file': bool(a.paynow_file), 'payouts_file': bool(a.payouts_file),
        'payouts_source': a.payouts_source, 'payouts_source_label': a.get_payouts_source_display() if a.payouts_source else '',
        'declared_balance': _money(a.declared_balance) if a.declared_balance is not None else None,
        'expected_balance': _money(expected),
        'balance_difference': _money(a.declared_balance - expected) if a.declared_balance is not None else None,
        'note': a.note, 'uploaded_by': a.uploaded_by, 'submitted_by': a.submitted_by,
        'submitted_at': a.submitted_at.isoformat() if a.submitted_at else None,
        'approved_at': a.approved_at.isoformat() if a.approved_at else None,
        'signatures': sigs, 'outstanding': outstanding(a),
        'can_sign': bool(user and a.status == PoolAudit.Status.SUBMITTED and is_signer(user)
                         and not (mine and mine.decision == Decision.APPROVE)),
    }


def _founder_audit(week_start: date, user) -> PoolAudit:
    if not is_founder(user):
        raise AuditError('Only the founder uploads the weekly reports and submits the week.')
    audit = PoolAudit.objects.select_for_update().filter(week_start=week_start).first()
    if audit is None and week_start == week_of(week_start):
        ensure_weeks()                      # the hourly job may not have opened it yet
        audit = PoolAudit.objects.select_for_update().filter(week_start=week_start).first()
    if audit is None:
        raise AuditError('No audit for that week yet — weeks open once they have ended.')
    if audit.status == PoolAudit.Status.APPROVED:
        raise AuditError('That week is approved by every partner and can’t change.')
    if audit.status == PoolAudit.Status.SUBMITTED:
        raise AuditError('That week is submitted and waiting for co-signatures. A partner must dispute it before it can change.')
    return audit


@transaction.atomic
def upload(week_start: date, kind: str, *, user, file=None, total=None, request=None) -> PoolAudit:
    """The founder's report for one side of the week: a CSV/Excel file (matched
    line by line) or, for a PDF statement, its total typed in."""
    if kind not in KINDS:
        raise AuditError('Unknown report.')
    audit = _founder_audit(week_start, user)
    if file is not None:
        data = file.read()
        try:
            parsed = reports.read_report(file.name, data)
        except reports.ReportError as exc:
            raise AuditError(str(exc)) from exc
        result = (match_deposits if kind == 'paynow' else match_payouts)(week_start, parsed['rows'])
        result.update({'file_name': file.name[:120], 'skipped': parsed['skipped'], 'columns': parsed['columns'], 'manual': False})
        file.seek(0)
        getattr(audit, f'{kind}_file').save(f'{week_start.isoformat()}-{kind}-{file.name[-60:]}', file, save=False)
    else:
        amount = reports.parse_amount(total)
        if amount is None or amount < 0:
            raise AuditError('Upload the report, or enter its total.')
        snap = snapshot(week_start)
        system = Decimal(snap['deposits']['total'] if kind == 'paynow' else snap['payouts']['sent'])
        result = {'manual': True, 'report_total': _money(amount), 'system_total': _money(system),
                  'difference': _money(amount - system), 'balanced': amount == system, 'counts': {}, 'problems': [], 'rows': 0}
    setattr(audit, f'{kind}_result', result)
    audit.uploaded_by = user.get_username()[:150]
    audit.save()
    _clear_lock_cache()
    accounts_services.audit(None, 'pool_audit_report', request, week=week_start.isoformat(), report=kind,
                            report_total=result['report_total'], system_total=result['system_total'],
                            balanced=result['balanced'], by=user.get_username())
    return audit


@transaction.atomic
def submit(week_start: date, *, user, declared_balance, payouts_source: str, note: str = '', request=None) -> PoolAudit:
    """The founder submits the week: both reports, where the payouts report came
    from (a statement, not a hand-made sheet), and what the pool actually holds
    at the week's end after the costs they claim. Partners then co-sign."""
    audit = _founder_audit(week_start, user)
    if not (audit.paynow_result and audit.payouts_result):
        raise AuditError('Upload both reports (Paynow and the payouts statement) first.')
    if payouts_source not in PoolAudit.Source.values:
        raise AuditError('The payouts report must be an EcoCash, OneMoney, InnBucks or bank statement — say which.')
    declared = reports.parse_amount(declared_balance)
    if declared is None:
        raise AuditError('Enter the balance the pool actually holds at the end of the week.')
    expected = Decimal(snapshot(week_start)['pool_balance_end'])
    issues = [k for k in KINDS if not getattr(audit, f'{k}_result').get('balanced')]
    if declared != expected:
        issues.append('balance')
    note = (note or '').strip()
    if issues and len(note) < 10:
        raise AuditError('The figures don’t all agree — explain every difference in the note before submitting.')
    audit.signatures.all().delete()                    # a resubmission needs fresh co-signatures
    audit.payouts_source, audit.declared_balance, audit.expected_balance = payouts_source, declared, expected
    audit.note, audit.status = note[:1000], PoolAudit.Status.SUBMITTED
    audit.submitted_by, audit.submitted_at = user.get_username()[:150], timezone.now()
    audit.save()
    AuditSignature.objects.create(audit=audit, user=user, decision=Decision.APPROVE, note='Submitted')
    transaction.on_commit(_clear_lock_cache)
    accounts_services.audit(None, 'pool_audit_submitted', request, week=week_start.isoformat(), by=user.get_username(),
                            declared=_money(declared), expected=_money(expected), issues=issues, note=audit.note)
    _maybe_approve(audit)
    return audit


@transaction.atomic
def cosign(week_start: date, *, user, decision: str, note: str = '', request=None) -> PoolAudit:
    """A partner approves the submitted week, or disputes it (with a reason),
    which sends it back to the founder."""
    if not is_signer(user):
        raise AuditError('Only the founder and the partners holding a wallet co-sign weeks.')
    audit = PoolAudit.objects.select_for_update().filter(week_start=week_start).first()
    if audit is None or audit.status != PoolAudit.Status.SUBMITTED:
        raise AuditError('That week isn’t waiting for co-signatures.')
    if decision not in Decision.values:
        raise AuditError('Approve or dispute.')
    note = (note or '').strip()
    if decision == Decision.REJECT and len(note) < 10:
        raise AuditError('Say what you dispute, so the founder can answer it.')
    AuditSignature.objects.update_or_create(audit=audit, user=user, defaults={'decision': decision, 'note': note[:1000]})
    if decision == Decision.REJECT:
        audit.status = PoolAudit.Status.DISPUTED
        audit.save(update_fields=['status', 'updated_at'])
    accounts_services.audit(None, 'pool_audit_cosigned', request, week=week_start.isoformat(), by=user.get_username(),
                            decision=decision, note=note)
    _maybe_approve(audit)
    return audit


def _maybe_approve(audit: PoolAudit) -> None:
    if audit.status != PoolAudit.Status.SUBMITTED:
        return
    approved = set(audit.signatures.filter(decision=Decision.APPROVE).values_list('user_id', flat=True))
    if all(u.pk in approved for u in signers()):
        audit.snapshot = snapshot(audit.week_start)
        audit.status, audit.approved_at = PoolAudit.Status.APPROVED, timezone.now()
        audit.save()
        transaction.on_commit(_clear_lock_cache)


def locked(day: date) -> bool:
    """A pool cost on a day in an approved week can't be added or removed."""
    return PoolAudit.objects.filter(week_start=week_of(day), status=PoolAudit.Status.APPROVED).exists()


# -- governance: deadlines, warnings, the lock ----------------------------------------------

def governance(*, now: Optional[datetime] = None) -> dict:
    """Which weeks are due or missed, who is holding them up, and whether the
    money controls are locked (two missed weeks in a row, until they're done)."""
    now = now or timezone.now()
    ensure_weeks(today=timezone.localdate(now))
    cfg = RevenueSettings.load()
    audits = list(PoolAudit.objects.filter(week_start__gte=cfg.audits_from).order_by('week_start')) if cfg.audits_from else []
    missed, due, run, lock_weeks = [], [], [], []
    for a in audits:
        pending = a.status != PoolAudit.Status.APPROVED
        late = pending and now >= deadline(a.week_start)
        if late:
            missed.append(a)
            run.append(a)
            if len(run) >= 2 and not lock_weeks:
                lock_weeks = [x.week_start.isoformat() for x in run[-2:]]
        else:
            run = []
            if pending:
                due.append(a)
    def entry(a):
        return {'week_start': a.week_start.isoformat(), 'due': deadline(a.week_start).isoformat(),
                'status': a.status, 'waiting_for': outstanding(a)}
    # Who has missed two in a row (by name), for the warning.
    streak: dict[str, int] = defaultdict(int)
    worst: dict[str, int] = defaultdict(int)
    for a in audits:
        if now < deadline(a.week_start):
            continue
        late_names = set(outstanding(a)) if a.status != PoolAudit.Status.APPROVED else set()
        for name in set(streak) | late_names:
            streak[name] = streak[name] + 1 if name in late_names else 0
            worst[name] = max(worst[name], streak[name])
    return {
        'locked': bool(lock_weeks), 'lock_weeks': lock_weeks,
        'missed': [entry(a) for a in missed], 'due': [entry(a) for a in due],
        'repeat_offenders': sorted(n for n, v in worst.items() if v >= 2),
        'warning': bool(missed or due),
    }


LOCK_CACHE_KEY = 'revenue:audit-lock'


def lock_state() -> dict:
    """Is the admin locked? Cached for 30 seconds (it's asked on every staff
    change); any audit action clears the cache so an approval unlocks at once."""
    from django.core.cache import cache
    try:
        state = cache.get(LOCK_CACHE_KEY)
    except Exception:  # noqa: BLE001
        state = None
    if state is None:
        g = governance()
        state = {'locked': g['locked'], 'lock_weeks': g['lock_weeks'],
                 'message': ('The admin is read-only: the weekly pool audits for the weeks of '
                             f'{" and ".join(g["lock_weeks"])} were both missed. Every change is blocked until the '
                             'founder submits and every partner co-signs the missed weeks (Revenue share).')
                 if g['locked'] else ''}
        try:
            cache.set(LOCK_CACHE_KEY, state, 30)
        except Exception:  # noqa: BLE001
            pass
    return state


def _clear_lock_cache() -> None:
    from django.core.cache import cache
    try:
        cache.delete(LOCK_CACHE_KEY)
    except Exception:  # noqa: BLE001
        pass


def assert_unlocked() -> None:
    from .services import RevenueError
    g = governance()
    if g['locked']:
        raise RevenueError('Locked: two weekly pool audits in a row were missed '
                           f'({", ".join(g["lock_weeks"])}). Money controls reopen once every missed week is approved.')


# -- using the pool ------------------------------------------------------------------

def pool_available() -> Decimal:
    return Decimal(pool_ledger()['closing'])


def proposal_row(p: PoolProposal, *, user=None) -> dict:
    votes = {v.user_id: v for v in p.votes.select_related('user')}
    return {
        'id': p.id, 'kind': p.kind, 'kind_label': p.get_kind_display(), 'amount': _money(p.amount), 'note': p.note,
        'proposed_by': p.proposed_by.get_username(), 'status': p.status, 'status_label': p.get_status_display(),
        'created_at': p.created_at.isoformat(), 'decided_at': p.decided_at.isoformat() if p.decided_at else None,
        'votes': [{'user': v.user.get_username(), 'decision': v.decision, 'note': v.note} for v in votes.values()],
        'waiting_for': [u.get_username() for u in signers() if u.pk not in votes] if p.status == PoolProposal.Status.OPEN else [],
        'can_vote': bool(user and p.status == PoolProposal.Status.OPEN and is_signer(user) and user.pk not in votes),
        'can_cancel': bool(user and p.status == PoolProposal.Status.OPEN and p.proposed_by_id == user.pk),
    }


@transaction.atomic
def propose(*, user, kind: str, amount, note: str, request=None) -> PoolProposal:
    from .services import RevenueError
    if not is_signer(user):
        raise RevenueError('Only the founder and the partners holding a wallet can propose using the pool.')
    assert_unlocked()
    if kind not in PoolProposal.Kind.values:
        raise RevenueError('Choose a promotion or an equal payout to partners.')
    value = reports.parse_amount(amount)
    if value is None or value <= 0:
        raise RevenueError('Enter an amount above zero.')
    if value > pool_available():
        raise RevenueError(f'The pool only holds {_money(pool_available())}.')
    note = (note or '').strip()
    if len(note) < 5:
        raise RevenueError('Say what it is for.')
    p = PoolProposal.objects.create(kind=kind, amount=value, note=note[:500], proposed_by=user)
    ProposalVote.objects.create(proposal=p, user=user, decision=Decision.APPROVE)
    accounts_services.audit(None, 'pool_proposal', request, id=p.id, kind=kind, amount=_money(value), note=p.note,
                            by=user.get_username())
    _maybe_execute(p)
    return p


@transaction.atomic
def vote(proposal_id: int, *, user, decision: str, note: str = '', request=None) -> PoolProposal:
    from .services import RevenueError
    p = PoolProposal.objects.select_for_update().filter(pk=proposal_id).first()
    if p is None or p.status != PoolProposal.Status.OPEN:
        raise RevenueError('That proposal isn’t open.')
    if not is_signer(user):
        raise RevenueError('Only the founder and the partners holding a wallet vote on the pool.')
    if decision not in Decision.values:
        raise RevenueError('Approve or reject.')
    ProposalVote.objects.update_or_create(proposal=p, user=user, defaults={'decision': decision, 'note': (note or '')[:500]})
    accounts_services.audit(None, 'pool_proposal_vote', request, id=p.id, decision=decision, by=user.get_username())
    if decision == Decision.REJECT:
        p.status, p.decided_at = PoolProposal.Status.REJECTED, timezone.now()
        p.save(update_fields=['status', 'decided_at'])
        return p
    _maybe_execute(p)
    return p


@transaction.atomic
def cancel(proposal_id: int, *, user, request=None) -> PoolProposal:
    from .services import RevenueError
    p = PoolProposal.objects.select_for_update().filter(pk=proposal_id, proposed_by=user, status=PoolProposal.Status.OPEN).first()
    if p is None:
        raise RevenueError('Only an open proposal of your own can be withdrawn.')
    p.status, p.decided_at = PoolProposal.Status.CANCELLED, timezone.now()
    p.save(update_fields=['status', 'decided_at'])
    return p


def _maybe_execute(p: PoolProposal) -> None:
    """Carry it out once every partner has approved (and nothing is locked)."""
    from .services import RevenueError
    approved = set(p.votes.filter(decision=Decision.APPROVE).values_list('user_id', flat=True))
    if not all(u.pk in approved for u in signers()):
        return
    assert_unlocked()
    if p.amount > pool_available():
        raise RevenueError(f'The pool now holds only {_money(pool_available())} — propose a smaller amount.')
    today = timezone.localdate()
    names = ', '.join(sorted(u.get_username() for u in signers()))
    if p.kind == PoolProposal.Kind.DISBURSE:
        wallets = ShareWallet.ensure()
        each = (p.amount / len(wallets)).quantize(CENT, rounding='ROUND_DOWN')
        total = each * len(wallets)
        for w in wallets:
            ShareEntry.objects.create(wallet=w, kind=ShareEntry.Kind.POOL, amount=each)
        category, amount = PoolExpense.Category.DISBURSE, total
    else:
        category, amount = PoolExpense.Category.PROMOTION, p.amount
    p.expense = PoolExpense.objects.create(day=today, category=category, amount=amount, note=p.note[:300],
                                           recorded_by=f'agreed: {names}'[:150])
    p.status, p.decided_at = PoolProposal.Status.DONE, timezone.now()
    p.save(update_fields=['expense', 'status', 'decided_at'])
