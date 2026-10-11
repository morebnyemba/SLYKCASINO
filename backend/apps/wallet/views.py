"""wallet transport — balance, ledger history, deposit, and withdrawal."""
from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q, Sum
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import services as accounts_services

from . import paynow, payments
from . import psp as psp_registry
from . import services
from .models import LedgerEntry, PaymentGateway, PaymentMethod, PaymentTransaction
from .serializers import (
    AdminLedgerEntrySerializer, AdminPaymentMethodSerializer, LedgerEntrySerializer, PaymentMethodSerializer,
)

# Header each provider signs its webhook payload with. Anything not listed
# here falls back to a generic header name (and will simply fail that PSP's
# own signature check, since no real secret will match).
_SIGNATURE_HEADERS = {
    'stripe': 'HTTP_STRIPE_SIGNATURE',
}


def _get_player_or_404(request):
    player = accounts_services.get_current_player(request)
    if player is None:
        return None, Response({'detail': 'player not found'}, status=status.HTTP_404_NOT_FOUND)
    return player, None


class WalletView(APIView):
    """GET /api/wallet/ -> current player's balance."""

    def get(self, request):
        player, err = _get_player_or_404(request)
        if err:
            return err
        dto = services.get_balance_dto(player.id)
        from apps.promotions import services as promotions_services
        bonus = promotions_services.bonus_status(player.id)
        return Response({
            'balance': str(dto.balance), 'currency': dto.currency,
            # Bonus money still being wagered can be played but not withdrawn.
            'bonus_locked': str(bonus['locked']), 'wagering_remaining': str(bonus['wagering_remaining']),
            'withdrawable': str(max(dto.balance - bonus['locked'], Decimal('0'))),
            'deposit_methods': payments.deposit_methods(),
            'payment_methods': PaymentMethodSerializer(payments.offered_methods(), many=True).data,
            'deposit_gateway': 'paynow' if payments.gateway_enabled() else 'stub',
        })


class LedgerView(APIView):
    """GET /api/wallet/ledger/ -> last 50 ledger entries."""

    def get(self, request):
        player, err = _get_player_or_404(request)
        if err:
            return err
        entries = LedgerEntry.objects.filter(wallet__player_id=player.id).order_by('-created_at')[:50]
        return Response(LedgerEntrySerializer(entries, many=True).data)


class DepositView(APIView):
    """POST /api/wallet/deposit/ — credit the player's wallet (stub PSP)."""

    def post(self, request):
        player, err = _get_player_or_404(request)
        if err:
            return err

        # Responsible gambling: block excluded players.
        try:
            accounts_services.check_responsible_gambling(player)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)

        try:
            amount = Decimal(str(request.data.get('amount', '0')))
            if amount <= 0:
                raise ValueError('amount must be positive')
        except (InvalidOperation, ValueError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Enforce daily deposit limit if set.
        if player.deposit_limit_daily is not None and amount > player.deposit_limit_daily:
            return Response(
                {'detail': f'Amount exceeds your daily deposit limit of {player.deposit_limit_daily}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payments.check_deposit(str(request.data.get('method', '') or ''), amount)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if payments.gateway_enabled():
            return self._start_gateway_deposit(request, player, amount)

        idempotency_key = request.data.get('idempotency_key') or f'deposit:req:{uuid.uuid4()}'
        entry = services.credit(
            player_id=player.id,
            amount=amount,
            kind='deposit',
            idempotency_key=idempotency_key,
            reference='psp:stub',
        )
        dto = services.get_balance_dto(player.id)
        return Response({
            'balance': str(dto.balance),
            'currency': dto.currency,
            'entry': LedgerEntrySerializer(entry).data,
        }, status=status.HTTP_201_CREATED)


    def _start_gateway_deposit(self, request, player, amount):
        """Paynow: the money moves on the player's phone (or Paynow's card page),
        so this only starts the payment; the wallet is credited when Paynow
        confirms it (see payments.apply_status)."""
        dto = services.get_balance_dto(player.id)
        try:
            txn = payments.start_deposit(
                player_id=player.id, amount=amount, currency=dto.currency,
                method=str(request.data.get('method', '')), phone=str(request.data.get('phone', '')),
            )
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except paynow.PaynowError as exc:
            return Response({'detail': f'Payment could not be started: {exc}'}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(_payment_payload(txn), status=status.HTTP_202_ACCEPTED)


def _payment_payload(txn: PaymentTransaction, balance=None) -> dict:
    return {
        'reference': txn.reference, 'status': txn.status, 'method': txn.method,
        'amount': str(txn.amount), 'currency': txn.currency,
        'instructions': txn.instructions, 'redirect_url': txn.redirect_url,
        **({'balance': str(balance)} if balance is not None else {}),
    }


class PaymentStatusView(APIView):
    """GET /api/wallet/deposits/<reference>/ — a gateway deposit's status. While
    pending it re-asks Paynow, so the deposit screen can poll this."""

    def get(self, request, reference: str):
        player, err = _get_player_or_404(request)
        if err:
            return err
        txn = PaymentTransaction.objects.filter(reference=reference, player_id=player.id).first()
        if txn is None:
            return Response({'detail': 'not found'}, status=status.HTTP_404_NOT_FOUND)
        txn = payments.refresh(txn)
        balance = services.get_balance_dto(player.id).balance
        return Response(_payment_payload(txn, balance))


class PaynowResultView(APIView):
    """POST /api/wallet/paynow/result/ — Paynow's server-to-server status
    callback. Unauthenticated by design: the message is signed with our
    integration key and rejected unless the hash verifies."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def post(self, request):
        try:
            payments.handle_result(request.body)
        except paynow.PaynowError:
            return Response({'detail': 'invalid message'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'detail': 'ok'})


class PSPWebhookView(APIView):
    """POST /api/wallet/webhook/<provider>/ — PSP deposit confirmation callback.

    Unauthenticated by design: the PSP's own `verify_webhook` performs
    signature verification against the provider's signing secret, so an
    attacker without that secret cannot forge a deposit confirmation.
    Crediting is idempotent on (provider, provider_ref), so a redelivered
    webhook is a guaranteed no-op rather than a double credit.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, provider: str):
        try:
            psp = psp_registry.get_psp(provider)
        except ValueError:
            return Response({'detail': 'unknown provider'}, status=status.HTTP_404_NOT_FOUND)

        signature = request.META.get(_SIGNATURE_HEADERS.get(provider, 'HTTP_X_SIGNATURE'), '')
        try:
            result = psp.verify_webhook(request.body, signature)
        except Exception:
            # Signature mismatch, malformed payload, etc. — never trust an
            # unverified webhook body.
            return Response({'detail': 'invalid webhook'}, status=status.HTTP_400_BAD_REQUEST)

        if result.status != 'completed':
            return Response({'detail': 'ignored'}, status=status.HTTP_200_OK)

        if result.player_id is None:
            return Response({'detail': 'missing player reference'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            services.deposit(
                player_id=result.player_id,
                amount=result.amount,
                idempotency_key=f'wallet:deposit:psp:{provider}:{result.provider_ref}',
                reference=f'psp:{provider}:{result.provider_ref}',
            )
        except ObjectDoesNotExist:
            # Unknown player_id in the PSP metadata — don't 500 and trigger
            # provider retry storms for a payload that will never resolve.
            return Response({'detail': 'player wallet not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'detail': 'ok'}, status=status.HTTP_200_OK)


class AdminLedgerViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Staff-only ledger viewer — GET /api/admin/ledger/?player_id=<id>."""
    serializer_class = AdminLedgerEntrySerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = LedgerEntry.objects.select_related('wallet').order_by('-created_at')
        player_id = self.request.query_params.get('player_id')
        if player_id:
            qs = qs.filter(wallet__player_id=player_id)
        return qs[:500]


class WithdrawView(APIView):
    """POST /api/wallet/withdraw/ {amount, method, account_number, account_name?, bank_name?}
    — ask to be paid out. The amount is held at once; staff send it and mark it paid."""

    def post(self, request):
        from . import withdrawals
        player, err = _get_player_or_404(request)
        if err:
            return err
        d = request.data
        try:
            req = withdrawals.request(
                player=player, amount=d.get('amount'), method=d.get('method') or '',
                account_number=d.get('account_number') or '', account_name=d.get('account_name') or '',
                bank_name=d.get('bank_name') or '',
            )
        except withdrawals.WithdrawalError as exc:
            body = {'detail': str(exc)}
            if exc.withdrawable is not None:
                body['withdrawable'] = str(exc.withdrawable)
            return Response(body, status=exc.code)
        except services.InsufficientFunds as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_402_PAYMENT_REQUIRED)
        dto = services.get_balance_dto(player.id)
        return Response({'balance': str(dto.balance), 'currency': dto.currency,
                         'withdrawal': withdrawals.payload(req)}, status=status.HTTP_201_CREATED)


class MyWithdrawalsView(APIView):
    """GET /api/wallet/withdrawals/ — the player's requests and limits;
    POST /api/wallet/withdrawals/<id>/cancel/ — take one back before it's paid."""

    def get(self, request):
        from . import withdrawals
        from .models import WithdrawalRequest, WithdrawalSettings
        player, err = _get_player_or_404(request)
        if err:
            return err
        cfg = WithdrawalSettings.load()
        rows = WithdrawalRequest.objects.filter(player_id=player.id)[:30]
        return Response({
            'results': [withdrawals.payload(r) for r in rows],
            'limits': {'min': str(cfg.min_amount), 'max': str(cfg.max_amount), 'daily_max': str(cfg.daily_max),
                       'left_today': str(max(cfg.daily_max - withdrawals.requested_today(player.id), Decimal('0')))
                       if cfg.daily_max else None},
            'methods': [{'id': v, 'label': l} for v, l in WithdrawalRequest.Method.choices],
        })

    def post(self, request, pk: int):
        from . import withdrawals
        player, err = _get_player_or_404(request)
        if err:
            return err
        try:
            req = withdrawals.cancel(player_id=player.id, req_id=int(pk))
        except withdrawals.WithdrawalError as exc:
            return Response({'detail': str(exc)}, status=exc.code)
        return Response({'withdrawal': withdrawals.payload(req),
                         'balance': str(services.get_balance_dto(player.id).balance)})


class AdminWithdrawalsView(APIView):
    """GET /api/admin/withdrawals/?status=requested|paid|rejected|cancelled|all&q=
    — the payout queue, with what staff check before paying.
    POST /api/admin/withdrawals/<id>/mark-paid/ {reference} and .../reject/ {note}."""
    permission_classes = [IsAdminUser]
    action = 'list'

    def get(self, request):
        from apps.accounts.models import Player
        from . import withdrawals
        from .models import WithdrawalRequest
        state = request.query_params.get('status') or 'requested'
        qs = WithdrawalRequest.objects.all()
        if state != 'all':
            qs = qs.filter(status=state)
        if (request.query_params.get('player_id') or '').isdigit():
            qs = qs.filter(player_id=int(request.query_params['player_id']))
        q = (request.query_params.get('q') or '').strip()
        if q:
            ids = list(Player.objects.filter(Q(username__icontains=q) | Q(email__icontains=q)).values_list('id', flat=True)[:200])
            qs = qs.filter(Q(player_id__in=ids) | Q(account_number__icontains=q) | Q(reference__icontains=q)
                           | Q(id=int(q) if q.isdigit() else -1))
        rows = list(qs.order_by('created_at' if state == 'requested' else '-id')[:200])
        players = {p.id: p for p in Player.objects.filter(id__in={r.player_id for r in rows})}
        out = []
        for r in rows:
            p = players.get(r.player_id)
            row = withdrawals.payload(r, staff=True)
            row.update(username=p.username if p else '(deleted)', kyc_status=p.kyc_status if p else None)
            if state == 'requested':
                row['context'] = withdrawals.player_context(r.player_id)
            out.append(row)
        return Response({
            'results': out,
            'counts': {s: WithdrawalRequest.objects.filter(status=s).count() for s in ('requested',)},
            'pending_total': f"{(WithdrawalRequest.objects.filter(status='requested').aggregate(t=Sum('amount'))['t'] or Decimal('0')):.2f}",
        })

    def post(self, request, pk: int):
        from apps.accounts import services as accounts_services
        from . import withdrawals
        by = request.user.get_username()
        try:
            if self.action == 'paid':
                req = withdrawals.mark_paid(int(pk), reference=request.data.get('reference', ''), by=by)
            else:
                req = withdrawals.reject(int(pk), note=request.data.get('note', ''), by=by)
        except withdrawals.WithdrawalError as exc:
            return Response({'detail': str(exc)}, status=exc.code)
        accounts_services.audit(req.player_id, f'withdrawal_{req.status}', request, withdrawal_id=req.id,
                                amount=str(req.amount), reference=req.reference, note=req.note)
        return Response(withdrawals.payload(req, staff=True))


class AdminWithdrawalSettingsView(APIView):
    """GET/PUT /api/admin/withdrawal-settings/ — min, max and daily cap per player."""
    permission_classes = [IsAdminUser]

    @staticmethod
    def _out(cfg):
        return {'min_amount': str(cfg.min_amount), 'max_amount': str(cfg.max_amount), 'daily_max': str(cfg.daily_max)}

    def get(self, request):
        from .models import WithdrawalSettings
        return Response(self._out(WithdrawalSettings.load()))

    def put(self, request):
        from apps.accounts import services as accounts_services
        from .models import WithdrawalSettings
        cfg = WithdrawalSettings.load()
        try:
            for f in ('min_amount', 'max_amount', 'daily_max'):
                if f in request.data:
                    setattr(cfg, f, Decimal(str(request.data[f])).quantize(Decimal('0.01')))
        except (InvalidOperation, ValueError, TypeError):
            return Response({'detail': 'Enter amounts as numbers.'}, status=status.HTTP_400_BAD_REQUEST)
        if cfg.min_amount <= 0 or cfg.max_amount < cfg.min_amount or cfg.daily_max < 0:
            return Response({'detail': 'The minimum must be above $0 and at most the maximum; the daily cap can’t be negative (0 = none).'},
                            status=status.HTTP_400_BAD_REQUEST)
        cfg.save()
        accounts_services.audit(None, 'withdrawal_settings', request, **self._out(cfg))
        return Response(self._out(cfg))


class PaymentMethodsView(APIView):
    """GET /api/wallet/payment-methods/ — public: the deposit options on offer
    and the method names for the site footer."""
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            'deposit': PaymentMethodSerializer(payments.offered_methods(), many=True).data,
            'footer': list(PaymentMethod.objects.filter(show_in_footer=True).values_list('name', flat=True)),
        })


class AdminPaymentMethodViewSet(viewsets.ModelViewSet):
    """/api/admin/payment-methods/ — operators add, edit, reorder and switch
    deposit methods on or off."""
    serializer_class = AdminPaymentMethodSerializer
    permission_classes = [IsAdminUser]
    pagination_class = None
    queryset = PaymentMethod.objects.all()

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        response.data = {
            'gateway': 'paynow' if payments.gateway_enabled() else 'stub',
            'gateway_methods': list(paynow.METHODS),
            'results': response.data,
        }
        return response


def _key_hint(key: str) -> str:
    return f'••••{key[-4:]}' if len(key) >= 8 else ('••••' if key else '')


def _gateway_summary() -> dict:
    from django.conf import settings as dj
    saved = PaymentGateway.load()
    cfg = paynow.get_config()
    return {
        'provider': payments.active_provider(),
        # '' = the admin hasn't chosen; the server's PSP_PROVIDER applies.
        'provider_setting': saved.provider,
        'server_provider': getattr(dj, 'PSP_PROVIDER', 'stub'),
        'paynow': {
            'integration_id': cfg.integration_id,
            'key_hint': _key_hint(cfg.integration_key),
            'key_set': bool(cfg.integration_key),
            'auth_email': cfg.auth_email,
            'configured': paynow.is_configured(),
            # Where each value comes from: saved here, or the server environment.
            'from_server': {
                'integration_id': not saved.paynow_integration_id and bool(cfg.integration_id),
                'integration_key': not saved.paynow_integration_key and bool(cfg.integration_key),
                'auth_email': not saved.paynow_auth_email and bool(cfg.auth_email),
            },
            'result_url': cfg.result_url,
            'return_url': cfg.return_url,
        },
        'updated_at': saved.updated_at,
        'updated_by': saved.updated_by_username,
    }


class AdminPaymentGatewayView(APIView):
    """GET/PUT /api/admin/payment-gateway/ — the live gateway and the Paynow
    credentials. The key is write-only: reads show its last four characters."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        return Response(_gateway_summary())

    def put(self, request):
        from django.conf import settings as dj
        from django.core.exceptions import ValidationError
        from django.core.validators import validate_email
        saved = PaymentGateway.load()
        data = request.data

        def bad(detail):
            return Response({'detail': detail}, status=status.HTTP_400_BAD_REQUEST)

        if 'paynow_integration_id' in data:
            value = str(data.get('paynow_integration_id') or '').strip()
            if value and not value.isdigit():
                return bad('The Integration ID is a number, e.g. 12345.')
            saved.paynow_integration_id = value[:20]
        if data.get('clear_key'):
            saved.paynow_integration_key = ''
        elif (key := str(data.get('paynow_integration_key') or '').strip()):
            saved.paynow_integration_key = key[:100]
        if 'paynow_auth_email' in data:
            email = str(data.get('paynow_auth_email') or '').strip()
            if email:
                try:
                    validate_email(email)
                except ValidationError:
                    return bad('Enter a valid merchant email.')
            saved.paynow_auth_email = email
        if 'provider' in data:
            provider = str(data.get('provider') or '')
            if provider not in PaymentGateway.Provider.values:
                return bad('Unknown gateway.')
            # The test processor credits deposits without taking money: switching
            # to it on purpose must be confirmed.
            if provider == PaymentGateway.Provider.STUB and saved.provider != provider and not data.get('confirm_test_mode'):
                return bad('Switching to the test processor credits deposits without taking any money. Confirm to continue.')
            saved.provider = provider

        effective = saved.provider or getattr(dj, 'PSP_PROVIDER', 'stub')
        has_id = saved.paynow_integration_id or getattr(dj, 'PAYNOW_INTEGRATION_ID', '')
        has_key = saved.paynow_integration_key or getattr(dj, 'PAYNOW_INTEGRATION_KEY', '')
        if effective == 'paynow' and not (has_id and has_key):
            return bad('Paynow needs its Integration ID and Integration Key before it can take payments.')

        saved.updated_by_username = request.user.get_username()[:150]
        saved.save()
        accounts_services.audit(None, 'payment_settings', request, provider=payments.active_provider(),
                                key_changed=bool(data.get('paynow_integration_key') or data.get('clear_key')))
        return Response(_gateway_summary())


class AdminPaymentGatewayTestView(APIView):
    """POST /api/admin/payment-gateway/test/ — check the Paynow credentials by
    starting a $1 checkout nobody pays (no money moves)."""
    permission_classes = [IsAdminUser]

    def post(self, request):
        if not paynow.is_configured():
            return Response({'ok': False, 'error': 'Add the Integration ID and key first.'})
        try:
            ref = paynow.check_credentials()
        except paynow.PaynowError as exc:
            return Response({'ok': False, 'error': str(exc)})
        return Response({'ok': True, 'paynow_reference': ref})
