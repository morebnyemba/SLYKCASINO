"""/api/admin/revenue-share/ — the house revenue share. Superusers see and run
everything; a wallet holder sees only their own wallet and asks for its
withdrawal; other staff see nothing."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import PoolExpense, RevenueDay, RevenueSettings, ShareWallet, ShareWithdrawal


def _forbidden(text='Only a superuser can do this.'):
    return Response({'detail': text}, status=status.HTTP_403_FORBIDDEN)


def _day(d: RevenueDay) -> dict:
    return {'day': d.day.isoformat(), 'ggr': str(d.ggr), 'bonus_conversions': str(d.bonus_conversions), 'carried_in': str(d.carried_in), 'base': str(d.base),
            'carry_out': str(d.carry_out), 'share_percent': str(d.share_percent), 'share_each': str(d.share_each),
            'pool': str(d.pool), 'affiliate_costs': str(d.affiliate_costs)}


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
            return Response({'role': 'holder', 'wallet': services.wallet_summary(own),
                             'withdrawals': [services.withdrawal_row(w) for w in own.withdrawals.all()[:20]],
                             'methods': [{'id': m.value, 'label': m.label} for m in ShareWithdrawal.Method]})
        cfg = RevenueSettings.load()
        staff = get_user_model().objects.filter(is_staff=True, is_active=True).order_by('username')
        return Response({
            'role': 'superuser',
            'own_slot': own.slot if own else None,
            'settings': {'share_percent': str(cfg.share_percent), 'started_on': cfg.started_on.isoformat() if cfg.started_on else None,
                         'locked_start': RevenueDay.objects.exists()},
            'wallets': [services.wallet_summary(w, entries=5) for w in ShareWallet.ensure()],
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
            return Response({'detail': str(exc)}, status=status.HTTP_404_NOT_FOUND)
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
            services.update_settings(share_percent=request.data.get('share_percent'),
                                     started_on=request.data.get('started_on'), wallets=wallets,
                                     by=request.user.get_username(), request=request)
        except services.RevenueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return OverviewView().get(request)
