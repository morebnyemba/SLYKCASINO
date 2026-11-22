"""Chat betting endpoints.

  GET/POST /api/chatbot/whatsapp/webhook/   Meta's webhook (verify, then signed deliveries)
  GET/DELETE /api/chatbot/me/               the player's link (status / unlink)
  POST /api/chatbot/me/link-code/           a one-time code to send from WhatsApp
  POST/DELETE /api/chatbot/me/pin/          set / clear the chat PIN
  POST /api/chatbot/me/limit/               the player's own daily chat limit
  GET/PUT /api/admin/chatbot/               operator settings and usage
"""
from __future__ import annotations

import hmac
import json
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.http import HttpResponse, HttpResponseForbidden
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import services as accounts_services

from . import config, engine, services, whatsapp
from .models import WHATSAPP, ChatbotSettings, ChatLink, ChatTicket, InboundMessage

logger = logging.getLogger(__name__)


@csrf_exempt
def whatsapp_webhook(request):
    if request.method == 'GET':
        token = whatsapp.verify_token()
        if (request.GET.get('hub.mode') == 'subscribe' and token
                and hmac.compare_digest(request.GET.get('hub.verify_token', ''), token)):
            return HttpResponse(request.GET.get('hub.challenge', ''), content_type='text/plain')
        return HttpResponseForbidden('bad verify token')
    if request.method != 'POST':
        return HttpResponse(status=405)
    body = request.body
    if not whatsapp.verify_signature(body, request.headers.get('X-Hub-Signature-256')):
        logger.warning('whatsapp webhook with a bad or missing signature')
        return HttpResponseForbidden('bad signature')
    try:
        payload = json.loads(body or b'{}')
    except ValueError:
        return HttpResponse(status=400)
    for msg in whatsapp.parse(payload):
        handle_inbound(msg)
    # Always 200 once authentic: Meta retries anything else, and a retry is a duplicate.
    return HttpResponse('ok')


def handle_inbound(msg: whatsapp.Inbound) -> None:
    """Record the message once (by its WhatsApp id) and answer it."""
    with transaction.atomic():
        try:
            with transaction.atomic():
                row = InboundMessage.objects.create(channel=WHATSAPP, provider_id=msg.provider_id,
                                                    address=msg.address, text=msg.text)
        except IntegrityError:
            return  # redelivered: already answered
        if services.over_rate(msg.address):
            return
        replies = engine.handle(msg.address, msg.text, channel=WHATSAPP)
        InboundMessage.objects.filter(pk=row.pk).update(replies=len(replies))
        services.deliver(msg.address, replies, channel=WHATSAPP)


def _player(request):
    player = accounts_services.get_current_player(request)
    if player is None:
        return None, Response({'detail': 'Players only.'}, status=status.HTTP_403_FORBIDDEN)
    return player, None


def _status(player_id: int) -> dict:
    link = ChatLink.objects.filter(channel=WHATSAPP, player_id=player_id).first()
    cfg = ChatbotSettings.load()
    number = whatsapp.display_number()
    return {
        'enabled': cfg.enabled, 'bot_number': number,
        'linked': bool(link), 'number': f'+{link.address[:3]} ••• {link.address[-4:]}' if link else None,
        'linked_at': link.linked_at if link else None, 'has_pin': bool(link and link.pin_hash),
        'daily_limit': str(link.daily_cap) if link and link.daily_cap is not None else None,
        'operator_daily_limit': str(cfg.daily_cap), 'max_stake': str(cfg.max_stake), 'pin_above': str(cfg.pin_above),
        'staked_today': str(services.staked_today(player_id)),
    }


class MyChatLinkView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        player, err = _player(request)
        return err or Response(_status(player.id))

    def delete(self, request):
        player, err = _player(request)
        if err:
            return err
        services.unlink(player.id, by='website')
        return Response(_status(player.id))


class LinkCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        player, err = _player(request)
        if err:
            return err
        code = services.new_link_code(player.id)
        return Response({'code': code.code, 'expires_at': code.expires_at, 'command': f'LINK {code.code}',
                         **_status(player.id)}, status=status.HTTP_201_CREATED)


class ChatPinView(APIView):
    permission_classes = [IsAuthenticated]

    def _link(self, request):
        player, err = _player(request)
        if err:
            return None, None, err
        link = ChatLink.objects.filter(channel=WHATSAPP, player_id=player.id).first()
        if link is None:
            return player, None, Response({'detail': 'Link your WhatsApp number first.'}, status=status.HTTP_400_BAD_REQUEST)
        return player, link, None

    def post(self, request):
        player, link, err = self._link(request)
        if err:
            return err
        try:
            services.set_pin(link, str(request.data.get('pin', '')))
        except services.ChatError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        accounts_services.audit(player.id, 'chat_pin_set', request)
        return Response(_status(player.id))

    def delete(self, request):
        player, link, err = self._link(request)
        if err:
            return err
        services.clear_pin(link)
        accounts_services.audit(player.id, 'chat_pin_cleared', request)
        return Response(_status(player.id))


class ChatLimitView(APIView):
    """The player's own daily chat limit; blank removes it (the operator's applies)."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        player, err = _player(request)
        if err:
            return err
        link = ChatLink.objects.filter(channel=WHATSAPP, player_id=player.id).first()
        if link is None:
            return Response({'detail': 'Link your WhatsApp number first.'}, status=status.HTTP_400_BAD_REQUEST)
        raw = str(request.data.get('daily_limit', '') or '').strip()
        try:
            value = None if raw == '' else Decimal(raw).quantize(Decimal('0.01'))
            if value is not None and value < 0:
                raise InvalidOperation
        except InvalidOperation:
            return Response({'detail': 'Enter an amount, or leave it blank.'}, status=status.HTTP_400_BAD_REQUEST)
        link.daily_cap = value
        link.save(update_fields=['daily_cap'])
        accounts_services.audit(player.id, 'chat_limit', request, daily_limit=raw or 'none')
        return Response(_status(player.id))


def _webhook_url(request) -> str:
    """Shown to staff to paste into Meta, which only calls https: https unless
    this is a local dev host (TLS ends at the proxy, so request.scheme says http)."""
    host = request.get_host()
    local = host.split(':')[0] in ('localhost', '127.0.0.1')
    return f'{"http" if local else "https"}://{host}/api/chatbot/whatsapp/webhook/'


class AdminChatbotView(APIView):
    permission_classes = [IsAdminUser]
    MONEY = ('max_stake', 'daily_cap', 'pin_above')
    FLAGS = ('enabled', 'allow_betting', 'allow_deposits')

    def _payload(self):
        cfg = ChatbotSettings.load()
        since = timezone.now() - timedelta(days=1)
        tickets = ChatTicket.objects.filter(created_at__gte=since).aggregate(n=Count('id'), staked=Sum('stake'))
        return {
            **{f: getattr(cfg, f) for f in self.FLAGS}, **{f: str(getattr(cfg, f)) for f in self.MONEY},
            'configured': whatsapp.configured(),
            'webhook_path': '/api/chatbot/whatsapp/webhook/',
            # The address Meta must call: this API's own host (behind the proxy), not the admin's.
            'webhook_url': _webhook_url(self.request),
            'connection': config.describe(cfg),
            'can_edit_connection': bool(self.request.user.is_superuser),
            'linked_players': ChatLink.objects.count(),
            'messages_24h': InboundMessage.objects.filter(received_at__gte=since).count(),
            'tickets_24h': tickets['n'] or 0, 'staked_24h': str((tickets['staked'] or Decimal('0')).quantize(Decimal('0.01'))),
        }

    def get(self, request):
        return Response(self._payload())

    def put(self, request):
        conn = request.data.get('connection')
        if conn is not None:
            # The token and secrets let anyone send as the business: superusers only.
            if not request.user.is_superuser:
                return Response({'detail': 'Only a superuser can change the WhatsApp connection.'},
                                status=status.HTTP_403_FORBIDDEN)
            if not isinstance(conn, dict):
                return Response({'detail': 'Bad connection settings.'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                changed = config.update(conn, by=request.user.get_username())
            except config.ConfigError as exc:
                return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            if changed:
                accounts_services.audit(None, 'chatbot_connection', request, changed=','.join(changed))
        cfg = ChatbotSettings.load()
        try:
            for f in self.FLAGS:
                if f in request.data:
                    setattr(cfg, f, bool(request.data[f]))
            for f in self.MONEY:
                if f in request.data:
                    v = Decimal(str(request.data[f])).quantize(Decimal('0.01'))
                    if v < 0:
                        raise InvalidOperation
                    setattr(cfg, f, v)
        except (InvalidOperation, ValueError, TypeError):
            return Response({'detail': 'Enter amounts of 0 or more.'}, status=status.HTTP_400_BAD_REQUEST)
        cfg.save()
        if any(f in request.data for f in (*self.FLAGS, *self.MONEY)):
            accounts_services.audit(None, 'chatbot_settings', request,
                                    **{f: str(getattr(cfg, f)) for f in (*self.FLAGS, *self.MONEY)})
        return Response(self._payload())


class AdminChatbotTestView(APIView):
    """POST /api/admin/chatbot/test/ — check the connection with Meta."""
    permission_classes = [IsAdminUser]

    def post(self, request):
        return Response(whatsapp.check_connection())
