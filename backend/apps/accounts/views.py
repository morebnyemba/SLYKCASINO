"""accounts transport — views move data; all logic is in services."""
from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from . import services
from .emails import send_password_reset_email, send_verification_email, send_welcome_email
from .models import Player
from .serializers import PlayerSerializer, RegisterSerializer

User = get_user_model()


class AuthRateThrottle(AnonRateThrottle):
    rate = '10/minute'
    scope = 'auth'


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        ser = RegisterSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        d = ser.validated_data
        try:
            player = services.register_player(
                username=d['username'],
                email=d['email'],
                password=d['password'],
                currency=d.get('currency', 'USD'),
            )
            services.audit(player.id, 'register', request)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        token = services.generate_verify_token(player.id)
        send_verification_email(player, token)
        return Response(PlayerSerializer(player).data, status=status.HTTP_201_CREATED)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        player = services.get_current_player(request)
        if player:
            services.audit(player.id, 'logout', request)
        try:
            token = RefreshToken(request.data['refresh'])
            token.blacklist()
        except (KeyError, TokenError):
            return Response({'detail': 'invalid or missing refresh token'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ResponsibleGamblingView(APIView):
    """GET/PATCH /api/players/me/rg/ — deposit limits and self-exclusion."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        player = services.get_current_player(request)
        if player is None:
            return Response({'detail': 'player not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            'deposit_limit_daily': str(player.deposit_limit_daily) if player.deposit_limit_daily is not None else None,
            'self_excluded': player.self_excluded,
            'exclusion_ends_at': player.exclusion_ends_at,
        })

    def patch(self, request):
        player = services.get_current_player(request)
        if player is None:
            return Response({'detail': 'player not found'}, status=status.HTTP_404_NOT_FOUND)
        if 'deposit_limit_daily' in request.data:
            try:
                player = services.set_deposit_limit(player.id, request.data['deposit_limit_daily'])
            except ValueError as exc:
                return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'deposit_limit_daily': str(player.deposit_limit_daily) if player.deposit_limit_daily is not None else None,
            'self_excluded': player.self_excluded,
            'exclusion_ends_at': player.exclusion_ends_at,
        })


class SelfExcludeView(APIView):
    """POST /api/players/me/self-exclude/ — initiate a cooling-off period."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        player = services.get_current_player(request)
        if player is None:
            return Response({'detail': 'player not found'}, status=status.HTTP_404_NOT_FOUND)
        days = request.data.get('days')
        try:
            days_int = int(days) if days is not None else None
        except (ValueError, TypeError):
            return Response({'detail': 'days must be an integer'}, status=status.HTTP_400_BAD_REQUEST)
        player = services.self_exclude(player.id, days=days_int)
        services.audit(player.id, 'self_exclude', request)
        return Response({
            'self_excluded': player.self_excluded,
            'exclusion_ends_at': player.exclusion_ends_at,
            'detail': 'Self-exclusion applied. You can contact support to review this.',
        })


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------

class RequestVerificationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        player = services.get_current_player(request)
        if player is None:
            return Response({'detail': 'player not found'}, status=status.HTTP_404_NOT_FOUND)
        if not player.email:
            return Response({'detail': 'no email on file'}, status=status.HTTP_400_BAD_REQUEST)
        token = services.generate_verify_token(player.id)
        send_verification_email(player, token)
        return Response({'detail': 'verification email sent'})


class VerifyEmailView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        token = request.data.get('token', '')
        if not token:
            return Response({'detail': 'token is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            player = services.verify_email(token)
            services.audit(player.id, 'email_verified', request)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        send_welcome_email(player)
        return Response({'detail': 'Email verified successfully'})


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------

class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email', '')
        if not email:
            return Response({'detail': 'if that email is registered, a reset link has been sent'})
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'detail': 'if that email is registered, a reset link has been sent'})
        generator = PasswordResetTokenGenerator()
        token = generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        send_password_reset_email(user, uid, token)
        resp_data: dict = {'detail': 'if that email is registered, a reset link has been sent'}
        if settings.DEBUG:
            resp_data['uid'] = uid
            resp_data['token'] = token
        return Response(resp_data)


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        uid = request.data.get('uid', '')
        token = request.data.get('token', '')
        password = request.data.get('password', '')
        if not uid or not token or not password:
            return Response({'detail': 'uid, token, and password are required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            pk = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=pk)
        except (User.DoesNotExist, Exception):
            return Response({'detail': 'Invalid uid'}, status=status.HTTP_400_BAD_REQUEST)
        generator = PasswordResetTokenGenerator()
        if not generator.check_token(user, token):
            return Response({'detail': 'Invalid or expired token'}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(password)
        user.save()
        try:
            player = Player.objects.get(user=user)
            services.audit(player.id, 'password_reset', request)
        except Player.DoesNotExist:
            pass
        return Response({'detail': 'Password reset successful'})


# ---------------------------------------------------------------------------
# GDPR — data export and account deletion
# ---------------------------------------------------------------------------

class DataExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        import json
        from django.http import HttpResponse
        from django.utils import timezone as tz

        player = services.get_current_player(request)
        if player is None:
            return Response({'detail': 'Player not found'}, status=status.HTTP_404_NOT_FOUND)

        from apps.wallet.models import LedgerEntry, Wallet
        from apps.sportsbook.models import Bet
        from apps.casino.models import GameRound
        from apps.promotions.models import PromotionClaim
        from apps.livechat.models import ChatMessage

        wallet = Wallet.objects.filter(player_id=player.id).first()
        ledger_entries = []
        balance = '0'
        currency = 'USD'
        if wallet:
            balance = str(wallet.balance)
            currency = wallet.currency
            for entry in LedgerEntry.objects.filter(wallet=wallet):
                ledger_entries.append({
                    'id': entry.id,
                    'amount': str(entry.amount),
                    'kind': entry.kind,
                    'reference': entry.reference,
                    'created_at': entry.created_at.isoformat(),
                })

        bets = list(Bet.objects.filter(player_id=player.id).values(
            'id', 'event', 'stake', 'odds', 'status', 'payout', 'placed_at', 'settled_at'
        ))
        for b in bets:
            b['stake'] = str(b['stake'])
            b['odds'] = str(b['odds'])
            b['payout'] = str(b['payout'])
            if b['placed_at']:
                b['placed_at'] = b['placed_at'].isoformat()
            if b['settled_at']:
                b['settled_at'] = b['settled_at'].isoformat()

        rounds = list(GameRound.objects.filter(player_id=player.id).values(
            'id', 'game_id', 'stake', 'win', 'status', 'created_at', 'settled_at'
        ))
        for r in rounds:
            r['stake'] = str(r['stake'])
            r['win'] = str(r['win'])
            if r['created_at']:
                r['created_at'] = r['created_at'].isoformat()
            if r['settled_at']:
                r['settled_at'] = r['settled_at'].isoformat()

        claims = list(PromotionClaim.objects.filter(player_id=player.id).values(
            'id', 'promotion_id', 'bonus_amount', 'wagering_required',
            'wagering_progress', 'status', 'created_at', 'completed_at'
        ))
        for c in claims:
            c['bonus_amount'] = str(c['bonus_amount'])
            c['wagering_required'] = str(c['wagering_required'])
            c['wagering_progress'] = str(c['wagering_progress'])
            if c['created_at']:
                c['created_at'] = c['created_at'].isoformat()
            if c['completed_at']:
                c['completed_at'] = c['completed_at'].isoformat()

        messages = list(ChatMessage.objects.filter(player_id=player.id).values(
            'id', 'channel', 'body', 'created_at'
        ))
        for m in messages:
            if m['created_at']:
                m['created_at'] = m['created_at'].isoformat()

        data = {
            'player': {
                'id': player.id,
                'username': player.username,
                'email': player.email,
                'kyc_status': player.kyc_status,
                'created_at': player.created_at.isoformat(),
                'self_excluded': player.self_excluded,
                'exclusion_ends_at': player.exclusion_ends_at.isoformat() if player.exclusion_ends_at else None,
                'deposit_limit_daily': str(player.deposit_limit_daily) if player.deposit_limit_daily else None,
                'email_verified': player.email_verified,
            },
            'wallet': {'balance': balance, 'currency': currency},
            'ledger': ledger_entries,
            'bets': bets,
            'casino_rounds': rounds,
            'promotion_claims': claims,
            'chat_messages': messages,
            'exported_at': tz.now().isoformat(),
        }

        services.audit(player.id, 'data_export', request)

        response = HttpResponse(
            json.dumps(data, indent=2),
            content_type='application/json',
        )
        response['Content-Disposition'] = f'attachment; filename="slyk_data_export_{player.id}.json"'
        return response


class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        player = services.get_current_player(request)
        if player is None:
            return Response({'detail': 'Player not found'}, status=status.HTTP_404_NOT_FOUND)

        player_id = player.id
        services.audit(player_id, 'account_deleted', request)

        player.username = f'deleted_{player.id}'
        player.email = ''
        player.email_verify_token = ''
        player.save(update_fields=['username', 'email', 'email_verify_token'])

        if player.user:
            player.user.email = ''
            player.user.is_active = False
            player.user.save(update_fields=['email', 'is_active'])

        return Response(status=status.HTTP_204_NO_CONTENT)


class PlayerViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Player directory. `list`/`retrieve` expose other players' PII (email, KYC
    status, etc.) so they are admin-only; `me`/`stats` are self-service and
    override this with their own `permission_classes` below."""
    queryset = Player.objects.all()
    serializer_class = PlayerSerializer
    permission_classes = [IsAdminUser]

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        player = services.get_current_player(request)
        if player is None:
            return Response({'detail': 'player profile not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer(player).data)

    @action(detail=False, methods=['get'], url_path='me/stats', permission_classes=[IsAuthenticated])
    def stats(self, request):
        from django.db.models import Count, Sum
        from apps.sportsbook.models import Bet
        from apps.casino.models import GameRound

        player = services.get_current_player(request)
        if player is None:
            return Response({'detail': 'player profile not found'}, status=status.HTTP_404_NOT_FOUND)

        bet_agg = Bet.objects.filter(player_id=player.id).aggregate(
            total_staked=Sum('stake'), total_payout=Sum('payout'), count=Count('id'),
        )
        bets_won = Bet.objects.filter(player_id=player.id, status='won').count()
        round_agg = GameRound.objects.filter(player_id=player.id).aggregate(
            total_staked=Sum('stake'), total_win=Sum('win'), count=Count('id'),
        )

        return Response({
            'bets': {
                'count': bet_agg['count'] or 0,
                'won': bets_won,
                'total_staked': str(bet_agg['total_staked'] or 0),
                'total_payout': str(bet_agg['total_payout'] or 0),
            },
            'casino': {
                'count': round_agg['count'] or 0,
                'total_staked': str(round_agg['total_staked'] or 0),
                'total_win': str(round_agg['total_win'] or 0),
            },
        })
