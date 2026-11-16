"""/api/admin/revenue-share/ — the house revenue share. Superusers see and run
everything; a wallet holder sees only their own wallet and asks for its
withdrawal; other staff see nothing."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from . import audit, services
from .models import PoolAudit, PoolExpense, PoolProposal, RevenueDay, RevenueSettings, ShareWallet, ShareWithdrawal


def _forbidden(text='Only a superuser can do this.'):
    return Response({'detail': text}, status=status.HTTP_403_FORBIDDEN)


def _day(d: RevenueDay) -> dict:
    return {'day': d.day.isoformat(), 'ggr': str(d.ggr), 'bonus_conversions': str(d.bonus_conversions), 'carried_in': str(d.carried_in), 'base': str(d.base),
            'carry_out': str(d.carry_out), 'share_percent': str(d.share_percent), 'share_each': str(d.share_each),
            'shared': str(d.shared),
            'pool': str(d.pool), 'affiliate_costs': str(d.affiliate_costs - d.affiliate_reversals),
            'affiliate_reversals': str(d.affiliate_reversals)}


class OverviewView(APIView):
    """GET — superuser: wallets, pool, today so far, closed days, withdrawals,
    expenses, settings and the staff who can hold a wallet. Holder: own wallet."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        services.close_days()
        own = ShareWallet.objects.filter(holder=request.user).first()
        if not request.user.is_superuser:
            if own is None:
                return _forbidden('Revenue share is visible to superusers and wallet holders only.')
            return Response({'role': 'holder', 'wallet': services.wallet_summary(own), 'pool': services.pool_summary(),
                             'governance': audit.governance(),
                             'is_founder': audit.is_founder(request.user),
                             'withdrawals': [services.withdrawal_row(w) for w in own.withdrawals.all()[:20]],
                             'methods': [{'id': m.value, 'label': m.label} for m in ShareWithdrawal.Method]})
        cfg = RevenueSettings.load()
        staff = get_user_model().objects.filter(is_staff=True, is_active=True).order_by('username')
        return Response({
            'role': 'superuser',
            'own_slot': own.slot if own else None,
            'is_founder': audit.is_founder(request.user),
            'governance': audit.governance(),
            'founder': (lambda f: {'id': f.id, 'username': f.get_username()} if f else None)(audit.founder()),
            'founder_set': cfg.founder_id is not None,
            'superusers': [{'id': u.id, 'username': u.get_username()} for u in staff if u.is_superuser],
            'settings': {'share_percent': str(cfg.share_percent), 'started_on': cfg.started_on.isoformat() if cfg.started_on else None,
                         'locked_start': RevenueDay.objects.exists(),
                         'partner_pool_percent': str(cfg.partner_pool_percent)},
            'wallets': [services.wallet_summary(w, entries=5) for w in ShareWallet.all_wallets()],
            'pool': services.pool_summary(),
            'today': services.today_so_far(),
            'days': [_day(d) for d in RevenueDay.objects.all()[:90]],
            'withdrawals': [services.withdrawal_row(w) for w in ShareWithdrawal.objects.select_related('wallet')[:50]],
            'expenses': [{'id': e.id, 'day': e.day.isoformat(), 'category': e.category, 'category_label': e.get_category_display(),
                          'amount': str(e.amount), 'note': e.note, 'recorded_by': e.recorded_by} for e in PoolExpense.objects.all()[:100]],
            'categories': [{'id': c.value, 'label': c.label} for c in PoolExpense.Category],
            'methods': [{'id': m.value, 'label': m.label} for m in ShareWithdrawal.Method],
            'staff': [{'id': u.id, 'username': u.get_username()} for u in staff],
        })


class WithdrawView(APIView):
    """POST {method, account} — the holder takes their whole balance; it resets to zero."""
    permission_classes = [IsAdminUser]

    def post(self, request):
        try:
            w = services.request_withdrawal(user=request.user, method=str(request.data.get('method') or ''),
                                            account=str(request.data.get('account') or ''), request=request)
        except services.RevenueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(services.withdrawal_row(w), status=status.HTTP_201_CREATED)


class DecideWithdrawalView(APIView):
    """POST {decision: paid|rejected, reference?, note?} — superuser."""
    permission_classes = [IsAdminUser]

    def post(self, request, pk: int):
        if not request.user.is_superuser:
            return _forbidden()
        try:
            w = services.decide_withdrawal(pk, decision=str(request.data.get('decision') or ''), by=request.user.get_username(),
                                           reference=str(request.data.get('reference') or ''),
                                           note=str(request.data.get('note') or ''), request=request)
        except services.RevenueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(services.withdrawal_row(w))


class ExpensesView(APIView):
    """POST {day, category, amount, note?} — superuser records a pool cost."""
    permission_classes = [IsAdminUser]

    def post(self, request):
        if not request.user.is_superuser:
            return _forbidden()
        try:
            e = services.record_expense(day=request.data.get('day'), category=str(request.data.get('category') or ''),
                                        amount=request.data.get('amount'), note=str(request.data.get('note') or ''),
                                        by=request.user.get_username(), request=request)
        except services.RevenueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'id': e.id, 'pool': services.pool_summary()}, status=status.HTTP_201_CREATED)


class ExpenseView(APIView):
    """DELETE — superuser removes a cost entered by mistake."""
    permission_classes = [IsAdminUser]

    def delete(self, request, pk: int):
        if not request.user.is_superuser:
            return _forbidden()
        try:
            services.delete_expense(pk, by=request.user.get_username(), request=request)
        except services.RevenueError as exc:
            code = status.HTTP_404_NOT_FOUND if 'not found' in str(exc) else status.HTTP_400_BAD_REQUEST
            return Response({'detail': str(exc)}, status=code)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SettingsView(APIView):
    """PUT {share_percent?, started_on?, wallets?: [{slot, holder_id, label}]} — superuser."""
    permission_classes = [IsAdminUser]

    def put(self, request):
        if not request.user.is_superuser:
            return _forbidden()
        wallets = request.data.get('wallets')
        if wallets is not None and not isinstance(wallets, list):
            return Response({'detail': 'wallets must be a list.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            extra = {'founder_id': request.data.get('founder_id')} if 'founder_id' in request.data else {}
            services.update_settings(share_percent=request.data.get('share_percent'),
                                     started_on=request.data.get('started_on'), wallets=wallets, **extra,
                                     by=request.user.get_username(), request=request)
        except services.RevenueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return OverviewView().get(request)


def _week(value: str):
    from datetime import date
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


class PoolLedgerView(APIView):
    """GET ?from=&to= — the operating pool's movements with a running balance.
    Superusers and wallet holders (read-only for holders)."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        if not audit.can_view(request.user):
            return _forbidden('The pool is visible to superusers and wallet holders only.')
        services.close_days()
        start, end = _week(request.query_params.get('from') or ''), _week(request.query_params.get('to') or '')
        return Response({'summary': services.pool_summary(), **audit.pool_ledger(start=start, end=end)})


class PoolDayView(APIView):
    """GET — the affiliate commissions behind one closed day's pool cost."""
    permission_classes = [IsAdminUser]

    def get(self, request, day: str):
        if not audit.can_view(request.user):
            return _forbidden('The pool is visible to superusers and wallet holders only.')
        d = _week(day)
        if d is None:
            return Response({'detail': 'Use YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'day': day, 'commissions': audit.affiliate_costs_on(d)})


class AuditsView(APIView):
    """GET — every weekly pool audit (newest first), the deadlines and the lock."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        if not audit.can_view(request.user):
            return _forbidden('Pool audits are visible to superusers and wallet holders only.')
        audit.ensure_weeks()
        f = audit.founder()
        return Response({
            'is_founder': audit.is_founder(request.user), 'is_signer': audit.is_signer(request.user),
            'founder': f.get_username() if f else None, 'signers': [u.get_username() for u in audit.signers()],
            'sources': [{'id': c.value, 'label': c.label} for c in PoolAudit.Source],
            'governance': audit.governance(),
            'audits': [audit.audit_row(a, user=request.user) for a in PoolAudit.objects.all()[:26]],
        })


class GovernanceView(APIView):
    """GET — the dashboard warning: weeks due or missed, who is late, and the lock."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        if not audit.can_view(request.user):
            return _forbidden('Pool audits are visible to superusers and wallet holders only.')
        return Response(audit.governance())


def _audit_action(request, week, fn, **kwargs):
    w = _week(week)
    if w is None:
        return Response({'detail': 'Use YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        a = fn(w, user=request.user, request=request, **kwargs)
    except audit.AuditError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(audit.audit_row(a, user=request.user))


class AuditUploadView(APIView):
    """POST multipart {kind: paynow|payouts, file} or {kind, total} — the founder."""
    permission_classes = [IsAdminUser]

    def post(self, request, week: str):
        return _audit_action(request, week, lambda w, **kw: audit.upload(w, str(request.data.get('kind') or ''),
                                                                        file=request.FILES.get('file'),
                                                                        total=request.data.get('total'), **kw))


class AuditSubmitView(APIView):
    """POST {declared_balance, payouts_source, note?} — the founder submits the week."""
    permission_classes = [IsAdminUser]

    def post(self, request, week: str):
        return _audit_action(request, week, audit.submit, declared_balance=request.data.get('declared_balance'),
                             payouts_source=str(request.data.get('payouts_source') or ''),
                             note=str(request.data.get('note') or ''))


class AuditCosignView(APIView):
    """POST {decision: approve|reject, note?} — each partner co-signs or disputes."""
    permission_classes = [IsAdminUser]

    def post(self, request, week: str):
        return _audit_action(request, week, audit.cosign, decision=str(request.data.get('decision') or ''),
                             note=str(request.data.get('note') or ''))


class ProposalsView(APIView):
    """GET — uses of the pool; POST {kind: promotion|disburse, amount, note} — propose one."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        if not audit.can_view(request.user):
            return _forbidden('The pool is visible to superusers and wallet holders only.')
        return Response({'available': str(audit.pool_available()), 'is_signer': audit.is_signer(request.user),
                         'kinds': [{'id': k.value, 'label': k.label} for k in PoolProposal.Kind],
                         'proposals': [audit.proposal_row(p, user=request.user) for p in PoolProposal.objects.all()[:50]]})

    def post(self, request):
        try:
            p = audit.propose(user=request.user, kind=str(request.data.get('kind') or ''), amount=request.data.get('amount'),
                              note=str(request.data.get('note') or ''), request=request)
        except services.RevenueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(audit.proposal_row(p, user=request.user), status=status.HTTP_201_CREATED)


class ProposalVoteView(APIView):
    """POST {decision: approve|reject, note?} — or {cancel: true} by the proposer."""
    permission_classes = [IsAdminUser]

    def post(self, request, pk: int):
        try:
            if request.data.get('cancel'):
                p = audit.cancel(pk, user=request.user, request=request)
            else:
                p = audit.vote(pk, user=request.user, decision=str(request.data.get('decision') or ''),
                               note=str(request.data.get('note') or ''), request=request)
        except services.RevenueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(audit.proposal_row(p, user=request.user))


class AuditFileView(APIView):
    """GET — download an uploaded report (it holds players' numbers: staff with pool access only)."""
    permission_classes = [IsAdminUser]

    def get(self, request, week: str, kind: str):
        from django.http import FileResponse
        if not audit.can_view(request.user):
            return _forbidden('Pool audits are visible to superusers and wallet holders only.')
        a = PoolAudit.objects.filter(week_start=_week(week)).first() if _week(week) else None
        f = getattr(a, f'{kind}_file', None) if a and kind in audit.KINDS else None
        if not f:
            return Response({'detail': 'No such report.'}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(f.open('rb'), as_attachment=True, filename=f.name.rsplit('/', 1)[-1])


class SettingsChangesView(APIView):
    """GET — settings changes waiting for (or decided by) the partners."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        from . import changes
        from .models import SettingsChange
        changes._expire()
        qs = SettingsChange.objects.select_related('requested_by')
        if not audit.can_view(request.user):
            qs = qs.filter(requested_by=request.user)
        return Response({'pending_for_me': changes.pending_for(request.user),
                         'changes': [changes.change_row(c, user=request.user) for c in qs[:50]]})


class SettingsChangeView(APIView):
    """POST {decision: approve|reject, note?} — or {cancel: true} by the requester."""
    permission_classes = [IsAdminUser]

    def post(self, request, pk: int):
        from . import changes
        try:
            if request.data.get('cancel'):
                c = changes.cancel(pk, user=request.user)
            else:
                c = changes.vote(pk, user=request.user, decision=str(request.data.get('decision') or ''),
                                 note=str(request.data.get('note') or ''), request=request)
        except changes.ChangeError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(changes.change_row(c, user=request.user))


# -- shares ---------------------------------------------------------------------------

def _shares_payload(user) -> dict:
    from . import shares
    from .models import ShareBuyer, ShareChange, ShareRelease, ShareSale
    cfg = RevenueSettings.load()
    superuser = user.is_superuser
    controller = shares.is_controller(user)
    sees_all = superuser or controller
    own = ShareWallet.objects.filter(holder=user).first()
    sales = ShareSale.objects.select_related('buyer', 'wallet')
    changes = ShareChange.objects.select_related('wallet', 'holder', 'new_holder')
    if not superuser:
        sales = sales.filter(buyer=user)
    if not sees_all:
        changes = changes.filter(holder=user)
    staff = get_user_model().objects.filter(is_staff=True, is_active=True).order_by('username')
    return {
        'can_admin': superuser,
        'is_controller': controller,
        'controllers': shares.controller_names(),
        'is_buyer': shares.is_buyer(user),
        'own_slot': own.slot if own else None,
        'settings': {'partner_pool_percent': str(cfg.partner_pool_percent), 'price_months': cfg.price_months,
                     'signer_min_percent': str(cfg.signer_min_percent), 'seller_percent': str(cfg.seller_percent)},
        'agreement': shares.agreement.payload(),
        'released_percent': str(shares.released_percent()),
        'releases': [shares.release_row(r) for r in ShareRelease.objects.select_related('wallet', 'holder')
                     .filter(remaining__gt=0) if sees_all or r.holder_id == user.pk],
        'held_percent': str(shares.held_percent()),
        'unsold_percent': str(shares.unsold_percent()),
        'price': shares.price_per_percent(),
        'wallets': [{'slot': w.slot, 'label': w.label or f'Partner {w.slot}', 'holder': w.holder.get_username() if w.holder else None,
                     'holder_id': w.holder_id, 'percent': str(w.percent),
                     # Another controller's share: even a controller needs its holder's consent.
                     'protected': bool(w.holder and shares.is_controller(w.holder))}
                    for w in ShareWallet.all_wallets() if sees_all or w.percent > 0],
        'sales': [shares.sale_row(s) for s in sales[:50]],
        'changes': [shares.change_row(c) for c in changes[:50]],
        'pending_for_me': [shares.change_row(c) for c in ShareChange.objects.select_related('wallet', 'holder', 'new_holder')
                           .filter(holder=user, status=ShareChange.Status.PENDING)],
        'buyers': ([{'user_id': b.user_id, 'username': b.user.get_username(), 'approved_by': b.approved_by}
                    for b in ShareBuyer.objects.select_related('user')] if superuser else []),
        'staff': [{'id': u.id, 'username': u.get_username()} for u in staff] if sees_all else [],
    }


def _can_see_shares(user) -> bool:
    from . import shares
    return (user.is_superuser or ShareWallet.objects.filter(holder=user).exists() or shares.is_buyer(user)
            or shares.is_controller(user))


def _run(fn):
    from .services import RevenueError
    try:
        fn()
    except RevenueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return None


class SharesView(APIView):
    """GET — shares: who holds what, unsold %, today's price, sales and changes.
    Superusers see everything; holders and approved buyers see their own."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        if not _can_see_shares(request.user):
            return _forbidden('Shares are visible to superusers, shareholders and approved buyers.')
        return Response(_shares_payload(request.user))


class ShareQuoteView(APIView):
    """GET ?percent= — the formula price for that share today."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        from . import shares
        if not _can_see_shares(request.user):
            return _forbidden('Shares are visible to superusers, shareholders and approved buyers.')
        out = {}
        err = _run(lambda: out.update(shares.quote(request.query_params.get('percent', '1'))))
        return err or Response(out)


class ShareActionView(APIView):
    """POST /shares/<action>/ — set, transfer, buy, sale (record), settings,
    buyer-add, buyer-remove. Rules live in revenue.shares."""
    permission_classes = [IsAdminUser]

    def post(self, request, action: str):
        from . import shares
        d, u = request.data, request.user
        actions = {
            'set': lambda: shares.set_share(slot=int(d.get('slot') or 0), percent=d.get('percent'), by_user=u,
                                            reason=d.get('reason', ''), for_sale=d.get('for_sale', True) not in (False, 'false', 0, '0'),
                                            request=request),
            'reclaim': lambda: shares.reclaim_release(int(d.get('release_id') or 0), by_user=u, request=request),
            'transfer': lambda: shares.transfer_wallet(slot=int(d.get('slot') or 0), new_holder_id=d.get('new_holder_id'),
                                                       by_user=u, reason=d.get('reason', ''), request=request),
            'buy': lambda: shares.request_purchase(by_user=u, percent=d.get('percent'),
                                                  accepted_agreement=d.get('accepted_agreement', False), request=request),
            'sale': lambda: shares.record_sale(buyer_id=d.get('buyer_id'), percent=d.get('percent'), price=d.get('price'),
                                               payment_method=d.get('payment_method', ''),
                                               payment_reference=d.get('payment_reference', ''), note=d.get('note', ''),
                                               accepted_agreement=d.get('accepted_agreement', False),
                                               by_user=u, request=request),
            'settings': lambda: shares.update_share_settings(partner_pool_percent=d.get('partner_pool_percent'),
                                                             price_months=d.get('price_months'),
                                                             signer_min_percent=d.get('signer_min_percent'),
                                                             seller_percent=d.get('seller_percent'), by_user=u, request=request),
            'buyer-add': lambda: shares.approve_buyer(user_id=d.get('user_id'), by_user=u, request=request),
            'buyer-remove': lambda: shares.remove_buyer(user_id=d.get('user_id'), by_user=u, request=request),
        }
        if action not in actions:
            return Response({'detail': 'Unknown action.'}, status=status.HTTP_404_NOT_FOUND)
        result = {}
        err = _run(lambda: result.update(r=actions[action]()))
        if err:
            return err
        r = result.get('r')
        body = _shares_payload(u)
        if isinstance(r, dict) and 'applied' in r:
            body['result'] = r
        return Response(body)


class ShareSaleDecideView(APIView):
    """POST {action: confirm|reject, payment_method?, payment_reference?, note?}."""
    permission_classes = [IsAdminUser]

    def post(self, request, pk: int):
        from . import shares
        d, u = request.data, request.user
        if d.get('action') == 'confirm':
            err = _run(lambda: shares.confirm_sale(pk, by_user=u, payment_method=d.get('payment_method', ''),
                                                   payment_reference=d.get('payment_reference', ''), request=request))
        else:
            err = _run(lambda: shares.reject_sale(pk, by_user=u, note=d.get('note', ''), request=request))
        return err or Response(_shares_payload(u))


class ShareChangeDecideView(APIView):
    """POST {approve: bool, note?} — the holder answers a cut/transfer of their wallet."""
    permission_classes = [IsAdminUser]

    def post(self, request, pk: int):
        from . import shares
        err = _run(lambda: shares.decide_change(pk, by_user=request.user, approve=bool(request.data.get('approve')),
                                                note=request.data.get('note', ''), request=request))
        return err or Response(_shares_payload(request.user))
