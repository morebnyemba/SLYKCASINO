"""Staff API for the fraud engine — /api/admin/risk/…

Any staff member can look; only a superuser can close a case or lift a
restriction (reinstating an account is the decision the spec reserves for
authorised administrators)."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import services as accounts_services

from . import linking, services
from .models import RiskCase, RiskProfile, RiskSettings, RiskSignal


def _superuser_only(request):
    if not request.user.is_superuser:
        return Response({'detail': 'Only a superuser can do this.'}, status=status.HTTP_403_FORBIDDEN)
    return None


def _players(ids):
    from apps.accounts.models import Player
    return {p.id: p for p in Player.objects.filter(pk__in=list(ids))}


def _signal(s: RiskSignal) -> dict:
    return {'id': s.id, 'code': s.code, 'severity': s.severity, 'points': s.points, 'detail': s.detail,
            'data': s.data, 'linked_player_ids': s.linked_player_ids, 'created_at': s.created_at.isoformat()}


def _case(c: RiskCase, player=None) -> dict:
    return {'id': c.id, 'player_id': c.player_id, 'username': player.username if player else None,
            'status': c.status, 'status_label': c.get_status_display(), 'action': c.action,
            'action_label': c.get_action_display(), 'reason': c.reason, 'score': c.score,
            'created_at': c.created_at.isoformat(), 'updated_at': c.updated_at.isoformat(),
            'decided_at': c.decided_at.isoformat() if c.decided_at else None,
            'decided_by': c.decided_by, 'decision_note': c.decision_note}


def _profile(p: RiskProfile) -> dict:
    return {'score': p.score, 'under_review': p.under_review, 'withdrawals_frozen': p.withdrawals_frozen,
            'bonus_blocked': p.bonus_blocked, 'cleared_at': p.cleared_at.isoformat() if p.cleared_at else None}


def player_report(player_id: int) -> dict:
    """Everything staff need to judge a player: risk state, every signal,
    linked accounts and why, wallets, withdrawals and cases. Also the
    downloadable fraud report."""
    from django.utils import timezone

    from apps.wallet import services as wallet_services
    from apps.wallet.models import LedgerEntry, WithdrawalRequest
    from apps.wallet.withdrawals import payload
    links = linking.linked_accounts(player_id)
    people = _players([player_id, *links])
    me = people.get(player_id)
    entries = LedgerEntry.objects.filter(wallet__player_id=player_id).order_by('-created_at')[:100]
    return {
        'generated_at': timezone.now().isoformat(),
        'player': {
            'id': player_id, 'username': me.username if me else None, 'email': me.email if me else None,
            'created_at': me.created_at.isoformat() if me else None, 'kyc_status': me.kyc_status if me else None,
            'is_suspended': me.is_suspended if me else None, 'suspended_reason': me.suspended_reason if me else '',
        },
        'profile': _profile(services.profile(player_id)),
        'wallets': {k: str(v) for k, v in wallet_services.get_balances(player_id).items()},
        'signals': [_signal(s) for s in RiskSignal.objects.filter(player_id=player_id)[:200]],
        'cases': [_case(c, me) for c in RiskCase.objects.filter(player_id=player_id)],
        'linked_accounts': sorted([
            {'player_id': pid, 'username': people[pid].username if pid in people else None,
             'is_suspended': people[pid].is_suspended if pid in people else None,
             'how': sorted(how), 'strong': bool(how & set(linking.STRONG))}
            for pid, how in links.items()
        ], key=lambda r: (not r['strong'], r['player_id'])),
        'numbers': {k: sorted(f'••{n[-4:]}' for n in v) for k, v in linking.numbers_of(player_id).items()},
        'ips': sorted(linking.ips_of(player_id)),
        'withdrawals': [payload(r, staff=True) for r in WithdrawalRequest.objects.filter(player_id=player_id)[:50]],
        'transactions': [{'transaction_ref': e.transaction_ref, 'kind': e.kind, 'wallet': e.bucket,
                          'amount': str(e.amount), 'reference': e.reference, 'created_at': e.created_at.isoformat()}
                         for e in entries],
    }


class CasesView(APIView):
    """GET /api/admin/risk/cases/?status=open|confirmed|dismissed|all"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        state = request.query_params.get('status') or 'open'
        qs = RiskCase.objects.all() if state == 'all' else RiskCase.objects.filter(status=state)
        rows = list(qs.order_by('-score', '-created_at')[:200] if state == 'open' else qs[:200])
        people = _players({c.player_id for c in rows})
        return Response({
            'results': [_case(c, people.get(c.player_id)) for c in rows],
            'open': RiskCase.objects.filter(status=RiskCase.Status.OPEN).count(),
            'held_withdrawals': _held_withdrawals(),
        })


def _held_withdrawals() -> int:
    from apps.wallet.models import WithdrawalRequest
    return WithdrawalRequest.objects.filter(status=WithdrawalRequest.Status.REQUESTED, risk_hold=True).count()


class CaseView(APIView):
    """GET /api/admin/risk/cases/<id>/ — the case and its player's full report.
    POST /api/admin/risk/cases/<id>/decide/ {decision: dismiss|confirm, note} (superuser)."""
    permission_classes = [IsAdminUser]
    action = 'get'

    def get(self, request, pk: int):
        case = RiskCase.objects.filter(pk=pk).first()
        if case is None:
            return Response({'detail': 'Case not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'case': _case(case, _players([case.player_id]).get(case.player_id)),
                         'report': player_report(case.player_id)})

    def post(self, request, pk: int):
        denied = _superuser_only(request)
        if denied:
            return denied
        if request.data.get('decision') == 'confirm_delete':
            return self._confirm_delete(request, pk)
        try:
            case = services.decide(pk, decision=str(request.data.get('decision') or ''),
                                   note=str(request.data.get('note') or ''), by=request.user.get_username())
        except RiskCase.DoesNotExist:
            return Response({'detail': 'Case not found.'}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        accounts_services.audit(case.player_id, f'risk_case_{case.status}', request, case_id=case.id, note=case.decision_note)
        return Response(_case(case, _players([case.player_id]).get(case.player_id)))


    def _confirm_delete(self, request, pk: int):
        """Confirm fraud and permanently delete the player; the username is typed to confirm."""
        case = RiskCase.objects.filter(pk=pk).first()
        if case is None:
            return Response({'detail': 'Case not found.'}, status=status.HTTP_404_NOT_FOUND)
        player = _players([case.player_id]).get(case.player_id)
        if player is None:
            return Response({'detail': 'This player is already deleted.'}, status=status.HTTP_400_BAD_REQUEST)
        if str(request.data.get('confirm') or '').strip() != player.username:
            return Response({'detail': 'Type the player’s username exactly to confirm.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            result = services.confirm_and_delete([pk], note=str(request.data.get('note') or ''),
                                                 by=request.user.get_username(), request=request, confirm='', single=True)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if result['failed']:
            return Response({'detail': result['failed'][0]['error']}, status=status.HTTP_409_CONFLICT)
        return Response(_case(RiskCase.objects.get(pk=pk), None))


class CasesBulkView(APIView):
    """POST /api/admin/risk/cases/bulk/ (superuser) — decide many open cases at once.
    {case_ids: [..], decision: dismiss | confirm | confirm_delete, note, dry_run?, confirm?}.
    `confirm_delete` confirms the fraud and permanently deletes each player (their
    money is forfeited): a dry run first shows who goes and who is blocked, and
    then `confirm` must be "DELETE <n>". At most 100 cases for deletion, 200 otherwise."""
    permission_classes = [IsAdminUser]
    MAX_DECIDE = 200

    def post(self, request):
        denied = _superuser_only(request)
        if denied:
            return denied
        ids = request.data.get('case_ids')
        if not isinstance(ids, list) or not ids or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
            return Response({'detail': 'Choose at least one case.'}, status=status.HTTP_400_BAD_REQUEST)
        decision = str(request.data.get('decision') or '')
        note = str(request.data.get('note') or '')
        by = request.user.get_username()
        try:
            if decision == 'confirm_delete':
                if request.data.get('dry_run'):
                    review = services.purge_review(ids)
                    review.pop('_deletable')
                    return Response({**review, 'dry_run': True})
                return Response(services.confirm_and_delete(
                    ids, note=note, by=by, request=request, confirm=str(request.data.get('confirm') or '')))
            if decision not in ('dismiss', 'confirm'):
                return Response({'detail': 'Choose dismiss, confirm or confirm_delete.'}, status=status.HTTP_400_BAD_REQUEST)
            if len(note.strip()) < 3:
                return Response({'detail': 'Say why — it goes on the record.'}, status=status.HTTP_400_BAD_REQUEST)
            if len(ids) > self.MAX_DECIDE:
                return Response({'detail': f'At most {self.MAX_DECIDE} cases at a time.'}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        done, skipped = 0, []
        for case_id in ids:
            try:
                case = services.decide(case_id, decision=decision, note=note, by=by)
            except RiskCase.DoesNotExist:
                skipped.append({'case_id': case_id, 'reason': 'Case not found'})
            except ValueError as exc:
                if 'Say why' in str(exc):
                    return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
                skipped.append({'case_id': case_id, 'reason': str(exc)})
            else:
                accounts_services.audit(case.player_id, f'risk_case_{case.status}', request, case_id=case.id,
                                        note=case.decision_note)
                done += 1
        return Response({'requested': len(ids), 'done': done, 'skipped': skipped, 'skipped_count': len(skipped),
                         'failed': [], 'failed_count': 0})


class PlayerRiskView(APIView):
    """GET /api/admin/risk/players/<id>/ — the player's report (also the
    fraud report download). POST {withdrawals_frozen?, bonus_blocked?} —
    staff may add a restriction; only a superuser may lift one."""
    permission_classes = [IsAdminUser]

    def get(self, request, pk: int):
        return Response(player_report(pk))

    def post(self, request, pk: int):
        changes = {k: bool(request.data[k]) for k in ('withdrawals_frozen', 'bonus_blocked') if k in request.data}
        if not changes:
            return Response({'detail': 'Nothing to change.'}, status=status.HTTP_400_BAD_REQUEST)
        current = services.profile(pk)
        if any(getattr(current, k) and not v for k, v in changes.items()):
            denied = _superuser_only(request)
            if denied:
                return denied
        prof = services.set_restrictions(pk, **changes)
        accounts_services.audit(pk, 'risk_restrictions', request, **{k: str(v) for k, v in changes.items()})
        return Response(_profile(prof))


class SettingsView(APIView):
    """GET/PUT /api/admin/risk/settings/ — thresholds (superuser to change)."""
    permission_classes = [IsAdminUser]
    INTS = ('review_score', 'suspend_score', 'window_days', 'signup_ip_accounts', 'new_account_hours',
            'withdraw_after_bonus_hours', 'payout_numbers_7d')
    MONEY = ('big_bet_amount', 'deposit_volume_24h', 'winnings_7d')

    def _out(self, cfg):
        return {**{f: getattr(cfg, f) for f in self.INTS}, **{f: str(getattr(cfg, f)) for f in self.MONEY}}

    def get(self, request):
        return Response(self._out(RiskSettings.load()))

    def put(self, request):
        denied = _superuser_only(request)
        if denied:
            return denied
        cfg = RiskSettings.load()
        try:
            for f in self.INTS:
                if f in request.data:
                    setattr(cfg, f, int(request.data[f]))
            for f in self.MONEY:
                if f in request.data:
                    setattr(cfg, f, Decimal(str(request.data[f])).quantize(Decimal('0.01')))
        except (InvalidOperation, ValueError, TypeError):
            return Response({'detail': 'Enter whole numbers and amounts.'}, status=status.HTTP_400_BAD_REQUEST)
        if cfg.review_score < 1 or cfg.suspend_score <= cfg.review_score or cfg.window_days < 1:
            return Response({'detail': 'Review score must be at least 1 and below the suspend score; the window at least a day.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if any(getattr(cfg, f) < 0 for f in (*self.INTS, *self.MONEY)):
            return Response({'detail': 'Values can’t be negative.'}, status=status.HTTP_400_BAD_REQUEST)
        cfg.save()
        accounts_services.audit(None, 'risk_settings', request, **{k: str(v) for k, v in self._out(cfg).items()})
        return Response(self._out(cfg))
