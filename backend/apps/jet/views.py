from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import services as accounts_services
from apps.wallet.services import InsufficientFunds, get_balance_dto

from . import bot_chat, bots, engine, services, social
from .models import JetBet, JetChatMessage, JetRound, JetSettings


def _player(request):
    return accounts_services.get_current_player(request) if request.user and request.user.is_authenticated else None


def _balance(player_id: int) -> str:
    return str(get_balance_dto(player_id).balance)


class StateView(APIView):
    """GET /api/jet/state/ — everything the game screen needs to draw itself:
    rules and limits, the current (or last) round, its bets, recent crash
    points, the server time (to sync the client clock) and the player's own bets."""
    permission_classes = [AllowAny]

    def get(self, request):
        cfg = JetSettings.load()
        rnd = services.current_round() or JetRound.objects.order_by('-id').first()
        bets = list(JetBet.objects.filter(round=rnd).exclude(status=JetBet.Status.REFUNDED)) if rnd else []
        player = _player(request)
        listed = [services.bet_payload(b) for b in bets]
        if rnd:
            # Simulated players are added for display only — never stored or counted.
            listed += bots.snapshot(rnd, timezone.now(), cfg)
        return Response({
            'settings': services.settings_payload(cfg),
            'round': services.round_payload(rnd) if rnd else None,
            'server_time': services.iso(timezone.now()),
            'history': services.history(),
            'bets': sorted(listed, key=lambda b: -Decimal(b['stake'])),
            'my_bets': [services.bet_payload(b, mine=True) for b in bets if player and b.player_id == player.id],
            'balance': _balance(player.id) if player else None,
            'free_bets': social.free_bets_for(player.id) if player else [],
        })


def _error(exc) -> Response:
    if isinstance(exc, InsufficientFunds):
        return Response({'detail': 'Not enough balance — deposit to keep playing.'}, status=status.HTTP_402_PAYMENT_REQUIRED)
    return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)


class BetView(APIView):
    """POST /api/jet/bets/ {stake, slot, auto_cashout?} — bet on the round that's taking bets."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        player = _player(request)
        if player is None:
            return Response({'detail': 'Player not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            slot = int(request.data.get('slot') or 1)
        except (TypeError, ValueError):
            slot = 0
        try:
            bet = services.place_bet(player=player, stake=request.data.get('stake'), slot=slot,
                                     auto_cashout=request.data.get('auto_cashout'),
                                     free_bet_id=request.data.get('free_bet_id'))
        except (services.JetError, InsufficientFunds) as exc:
            return _error(exc)
        return Response({'bet': services.bet_payload(bet, mine=True), 'balance': _balance(player.id),
                         'free_bets': social.free_bets_for(player.id)},
                        status=status.HTTP_201_CREATED)


class BetActionView(APIView):
    """POST /api/jet/bets/<id>/cashout/ and /api/jet/bets/<id>/cancel/"""
    permission_classes = [IsAuthenticated]
    action = 'cashout'

    def post(self, request, pk: int):
        player = _player(request)
        if player is None:
            return Response({'detail': 'Player not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            fn = services.cash_out if self.action == 'cashout' else services.cancel_bet
            bet = fn(player_id=player.id, bet_id=int(pk))
        except services.JetError as exc:
            return _error(exc)
        return Response({'bet': services.bet_payload(bet, mine=True), 'balance': _balance(player.id),
                         'free_bets': social.free_bets_for(player.id)})


class ChatView(APIView):
    """GET /api/jet/chat/ — the latest messages; POST {body} — say something."""

    def get_permissions(self):
        return [AllowAny()] if self.request.method == 'GET' else [IsAuthenticated()]

    def get(self, request):
        cfg = JetSettings.load()
        return Response({'enabled': cfg.chat_enabled, 'messages': social.recent() if cfg.chat_enabled else []})

    def post(self, request):
        player = _player(request)
        if player is None:
            return Response({'detail': 'Player not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            msg = social.post(player=player, body=request.data.get('body', ''))
        except social.ChatError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response({'message': social.message_payload(msg)}, status=status.HTTP_201_CREATED)


class MyBetsView(APIView):
    """GET /api/jet/my-bets/ — the player's last 50 Jet bets."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        player = _player(request)
        if player is None:
            return Response({'results': []})
        bets = JetBet.objects.filter(player_id=player.id).select_related('round')[:50]
        return Response({'results': [
            {**services.bet_payload(b, mine=True), 'created_at': services.iso(b.created_at),
             'crash_point': str(b.round.crash_point) if b.round.status == JetRound.Status.CRASHED else None}
            for b in bets
        ]})


class RoundsView(APIView):
    """GET /api/jet/rounds/[<id>/] — finished rounds with their revealed seeds,
    so anyone can check the crash points."""
    permission_classes = [AllowAny]

    def get(self, request, pk: int | None = None):
        qs = JetRound.objects.filter(status=JetRound.Status.CRASHED)
        if pk is not None:
            rnd = qs.filter(pk=pk).first()
            if rnd is None:
                return Response({'detail': 'Round not found or still in play.'}, status=status.HTTP_404_NOT_FOUND)
            bets = rnd.bets.exclude(status=JetBet.Status.REFUNDED).order_by('-stake')[:200]
            return Response({**services.round_payload(rnd), 'house_edge_percent': str(rnd.house_edge_percent),
                             'bets': [services.bet_payload(b) for b in bets]})
        return Response({'results': [
            {**services.round_payload(r), 'house_edge_percent': str(r.house_edge_percent)} for r in qs.order_by('-id')[:50]
        ]})


# -- operator console -----------------------------------------------------------

SETTING_FIELDS = ('house_edge_percent', 'min_bet', 'max_bet', 'max_win', 'max_multiplier', 'round_stake_limit',
                  'rain_amount', 'rain_daily_budget')
INT_FIELDS = ('betting_seconds', 'bot_count', 'rain_players', 'rain_every_minutes', 'bot_chat_per_minute')
BOOL_FIELDS = ('enabled', 'bots_enabled', 'chat_enabled', 'rain_enabled', 'bot_chat_enabled')


class AdminSettingsView(APIView):
    """GET/PUT /api/admin/jet/settings/ — limits, house edge, pause/resume."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        return Response(_admin_settings(JetSettings.load()))

    def put(self, request):
        cfg = JetSettings.load()
        data = request.data
        try:
            for field in SETTING_FIELDS:
                if field in data:
                    setattr(cfg, field, Decimal(str(data[field])).quantize(engine.CENT))
            for field in INT_FIELDS:
                if field in data:
                    setattr(cfg, field, int(data[field]))
        except (ArithmeticError, ValueError, TypeError):
            return Response({'detail': 'Enter numbers for every setting.'}, status=status.HTTP_400_BAD_REQUEST)
        for field in BOOL_FIELDS:
            if field in data:
                setattr(cfg, field, bool(data[field]))
        if 'display_name' in data:
            cfg.display_name = str(data['display_name'] or '').strip()[:40] or 'BetBlits Aviator'
        problems = []
        if not Decimal('0') <= cfg.house_edge_percent <= Decimal('10'):
            problems.append('House edge must be between 0% and 10%.')
        if cfg.min_bet <= 0 or cfg.max_bet < cfg.min_bet:
            problems.append('The maximum bet must be at least the minimum, and the minimum above $0.')
        if cfg.max_multiplier < Decimal('2'):
            problems.append('The highest multiplier must be at least 2x.')
        if cfg.max_win < cfg.max_bet:
            problems.append('The max win must be at least the max bet.')
        if cfg.round_stake_limit < cfg.max_bet:
            problems.append('The round limit must be at least the max bet.')
        if not 3 <= cfg.betting_seconds <= 30:
            problems.append('The countdown must be 3–30 seconds.')
        if not 0 <= cfg.bot_count <= bots.MAX_BOTS:
            problems.append(f'Simulated players must be 0–{bots.MAX_BOTS} per round.')
        if not 0 <= cfg.bot_chat_per_minute <= bot_chat.MAX_PER_MINUTE:
            problems.append(f'Bot chat can be 0–{bot_chat.MAX_PER_MINUTE} lines a minute.')
        if not (Decimal('0.10') <= cfg.rain_amount <= Decimal('100')):
            problems.append('Each rain free bet must be $0.10–$100.')
        if not 1 <= cfg.rain_players <= 100:
            problems.append('Rain can reach 1–100 players at a time.')
        if cfg.rain_daily_budget < 0:
            problems.append('The daily rain budget can’t be negative.')
        if cfg.rain_every_minutes and cfg.rain_every_minutes < 5:
            problems.append('Automatic rain can run at most every 5 minutes (0 turns it off).')
        if problems:
            return Response({'detail': ' '.join(problems)}, status=status.HTTP_400_BAD_REQUEST)
        cfg.updated_by = request.user.get_username()[:150]
        cfg.save()
        accounts_services.audit(None, 'jet_settings', request, enabled=cfg.enabled,
                                house_edge=str(cfg.house_edge_percent), max_bet=str(cfg.max_bet),
                                bots_enabled=cfg.bots_enabled, bot_count=cfg.bot_count,
                                chat_enabled=cfg.chat_enabled, rain_enabled=cfg.rain_enabled,
                                rain_amount=str(cfg.rain_amount), rain_players=cfg.rain_players,
                                rain_every_minutes=cfg.rain_every_minutes, rain_daily_budget=str(cfg.rain_daily_budget),
                                bot_chat_enabled=cfg.bot_chat_enabled, bot_chat_per_minute=cfg.bot_chat_per_minute)
        return Response(_admin_settings(cfg))


def _admin_settings(cfg: JetSettings) -> dict:
    return {
        **services.settings_payload(cfg), 'bot_count': cfg.bot_count, 'chat_enabled': cfg.chat_enabled,
        'rain_enabled': cfg.rain_enabled, 'rain_amount': str(cfg.rain_amount), 'rain_players': cfg.rain_players,
        'rain_every_minutes': cfg.rain_every_minutes, 'rain_daily_budget': str(cfg.rain_daily_budget),
        'rain_given_today': str(social.given_today()),
        'bot_chat_enabled': cfg.bot_chat_enabled, 'bot_chat_per_minute': cfg.bot_chat_per_minute,
        'last_rain_at': services.iso(cfg.last_rain_at),
    }


def _totals(qs) -> dict:
    agg = qs.aggregate(rounds=Count('id'), stake=Sum('total_stake'), payout=Sum('total_payout'),
                       bets=Sum('bet_count'))
    stake, payout = agg['stake'] or Decimal('0'), agg['payout'] or Decimal('0')
    return {
        'rounds': agg['rounds'], 'bets': agg['bets'] or 0, 'stake': str(stake), 'payout': str(payout),
        'ggr': str(stake - payout), 'rtp_percent': f'{(payout / stake * 100):.2f}' if stake else None,
    }


class AdminStatsView(APIView):
    """GET /api/admin/jet/stats/ — takings today / 7 days / all time, the live
    round (never its crash point) and the latest finished rounds."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        now = timezone.now()
        crashed = JetRound.objects.filter(status=JetRound.Status.CRASHED)
        cfg = JetSettings.load()
        live = services.current_round()
        live_bets = list(live.bets.filter(status=JetBet.Status.ACTIVE)) if live else []
        # Most the riding bets could still win: each to its auto cash-out or the cap.
        exposure = sum((engine.payout_for(b.stake, min(b.auto_cashout or cfg.max_multiplier, cfg.max_multiplier), cfg.max_win)
                        for b in live_bets), Decimal('0'))
        return Response({
            'today': _totals(crashed.filter(crashed_at__date=timezone.localdate())),
            'week': _totals(crashed.filter(crashed_at__gte=now - timedelta(days=7))),
            'all_time': _totals(crashed),
            'live': {
                'round': live.id if live else None, 'status': live.status if live else None,
                'bets': live.bet_count if live else 0, 'stake': str(live.total_stake) if live else '0',
                'riding': len(live_bets), 'max_exposure': str(exposure),
            },
            'rounds': [
                {**services.round_payload(r), 'total_payout': str(r.total_payout),
                 'ggr': str(r.total_stake - r.total_payout)}
                for r in crashed.order_by('-id')[:30]
            ],
            # Shown apart from every figure above, which are real players only.
            'bots': {
                'enabled': cfg.bots_enabled, 'per_round': cfg.bot_count,
                'live_round': len(bots.plan(live, cfg)) if live else 0,
            },
            'players_today': JetBet.objects.filter(created_at__date=timezone.localdate())
                .values('player_id').distinct().count(),
        })


class AdminRainView(APIView):
    """POST /api/admin/jet/rain/ {players?, amount?} — make it rain now (within the daily budget)."""
    permission_classes = [IsAdminUser]

    def post(self, request):
        try:
            result = social.rain(players=request.data.get('players'), amount=request.data.get('amount'))
        except (ArithmeticError, ValueError, TypeError):
            return Response({'detail': 'Enter a number of players and an amount.'}, status=status.HTTP_400_BAD_REQUEST)
        accounts_services.audit(None, 'jet_rain', request, **result)
        if result['reason']:
            return Response({'detail': result['reason'], **result}, status=status.HTTP_409_CONFLICT)
        return Response(result)


class AdminChatView(APIView):
    """GET /api/admin/jet/chat/ — recent messages incl. hidden ones and who sent them.
    POST /api/admin/jet/chat/<id>/hide/ and /api/admin/jet/chat/mute/ {player_id, hours}."""
    permission_classes = [IsAdminUser]
    action = 'list'

    def get(self, request):
        rows = JetChatMessage.objects.order_by('-id')[:100]
        return Response({'results': [
            {**social.message_payload(m), 'player_id': m.player_id, 'hidden': m.hidden} for m in rows
        ]})

    def post(self, request, pk: int | None = None):
        if self.action == 'hide':
            if not social.hide(int(pk)):
                return Response({'detail': 'Message not found or already hidden.'}, status=status.HTTP_404_NOT_FOUND)
            accounts_services.audit(None, 'jet_chat_hide', request, message_id=int(pk))
            return Response({'hidden': True})
        try:
            player_id, hours = int(request.data.get('player_id')), int(request.data.get('hours') or 24)
        except (TypeError, ValueError):
            return Response({'detail': 'Choose a player and how long.'}, status=status.HTTP_400_BAD_REQUEST)
        if not 1 <= hours <= 24 * 365:
            return Response({'detail': 'Mute for 1 hour to a year.'}, status=status.HTTP_400_BAD_REQUEST)
        mute = social.mute(player_id, hours, by=request.user.get_username())
        accounts_services.audit(player_id, 'jet_chat_mute', request, hours=hours)
        return Response({'player_id': player_id, 'until': services.iso(mute.until)})


class AdminPlayerBetsView(APIView):
    """GET /api/admin/jet/bets/?player_id= — a player's latest Aviator bets with each round's result."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        try:
            player_id = int(request.query_params.get('player_id') or 0)
        except ValueError:
            player_id = 0
        if not player_id:
            return Response({'detail': 'Choose a player.'}, status=status.HTTP_400_BAD_REQUEST)
        bets = JetBet.objects.filter(player_id=player_id).select_related('round')[:100]
        agg = JetBet.objects.filter(player_id=player_id, is_free=False).aggregate(
            n=Count('id'), staked=Sum('stake'), won=Sum('payout'))
        staked, won = agg['staked'] or Decimal('0'), agg['won'] or Decimal('0')
        return Response({
            'results': [
                {**services.bet_payload(b, mine=True), 'created_at': services.iso(b.created_at),
                 'crash_point': str(b.round.crash_point) if b.round.status == JetRound.Status.CRASHED else None}
                for b in bets
            ],
            'summary': {'bets': agg['n'] or 0, 'staked': f'{staked:.2f}', 'won': f'{won:.2f}',
                        'net': f'{(won - staked):.2f}'},
        })
