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
from .models import PoolAudit, PoolExpense, RevenueDay, RevenueSettings, ShareWallet, ShareWithdrawal

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


# -- the weekly audit ------------------------------------------------------------------

def ensure_weeks(*, today: Optional[date] = None) -> int:
    """One audit per completed week since revenue sharing started. Idempotent."""
    today = today or timezone.localdate()
    cfg = RevenueSettings.load()
    if not cfg.started_on:
        return 0
    created, week = 0, week_of(cfg.started_on)
    while week + timedelta(days=7) <= today:
        _, made = PoolAudit.objects.get_or_create(week_start=week)
        created += made
        week += timedelta(days=7)
    return created


def audit_row(a: PoolAudit) -> dict:
    return {
        'week_start': a.week_start.isoformat(), 'week_end': (a.week_start + timedelta(days=6)).isoformat(),
        'status': a.status, 'status_label': a.get_status_display(),
        'system': a.snapshot if a.status == PoolAudit.Status.SIGNED else snapshot(a.week_start),
        'paynow': a.paynow_result or None, 'payouts': a.payouts_result or None,
        'paynow_file': bool(a.paynow_file), 'payouts_file': bool(a.payouts_file),
        'note': a.note, 'uploaded_by': a.uploaded_by, 'signed_by': a.signed_by,
        'signed_at': a.signed_at.isoformat() if a.signed_at else None,
    }


def _open_audit(week_start: date, user) -> PoolAudit:
    if not is_founder(user):
        raise AuditError('Only the founder uploads the weekly reports and signs weeks off.')
    audit = PoolAudit.objects.select_for_update().filter(week_start=week_start).first()
    if audit is None and week_start == week_of(week_start):
        ensure_weeks()                      # the hourly job may not have opened it yet
        audit = PoolAudit.objects.select_for_update().filter(week_start=week_start).first()
    if audit is None:
        raise AuditError('No audit for that week yet — weeks open once they have ended.')
    if audit.status == PoolAudit.Status.SIGNED:
        raise AuditError('That week is signed off and can’t change.')
    return audit


@transaction.atomic
def upload(week_start: date, kind: str, *, user, file=None, total=None, request=None) -> PoolAudit:
    """The founder's report for one side of the week: a CSV/Excel file (matched
    line by line) or, for a PDF statement, its total typed in."""
    if kind not in KINDS:
        raise AuditError('Unknown report.')
    audit = _open_audit(week_start, user)
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
    if audit.paynow_result and audit.payouts_result:
        audit.status = PoolAudit.Status.REVIEW
    audit.save()
    accounts_services.audit(None, 'pool_audit_report', request, week=week_start.isoformat(), report=kind,
                            report_total=result['report_total'], system_total=result['system_total'],
                            balanced=result['balanced'], by=user.get_username())
    return audit


@transaction.atomic
def sign_off(week_start: date, *, user, note: str = '', request=None) -> PoolAudit:
    audit = _open_audit(week_start, user)
    if not (audit.paynow_result and audit.payouts_result):
        raise AuditError('Upload both reports (Paynow and payouts) before signing the week off.')
    unbalanced = [k for k in KINDS if not getattr(audit, f'{k}_result').get('balanced')]
    note = (note or '').strip()
    if unbalanced and len(note) < 10:
        raise AuditError('The reports don’t balance — explain the differences in the note before signing off.')
    audit.snapshot = snapshot(week_start)
    audit.status = PoolAudit.Status.SIGNED
    audit.note = note[:1000]
    audit.signed_by = user.get_username()[:150]
    audit.signed_at = timezone.now()
    audit.save()
    accounts_services.audit(None, 'pool_audit_signed', request, week=week_start.isoformat(), by=audit.signed_by,
                            unbalanced=unbalanced, note=audit.note)
    return audit


def locked(day: date) -> bool:
    """A pool cost on a day in a signed-off week can't be added or removed."""
    return PoolAudit.objects.filter(week_start=week_of(day), status=PoolAudit.Status.SIGNED).exists()
