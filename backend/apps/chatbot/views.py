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
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import services as accounts_services

from . import config, engine, services, whatsapp
from .models import WHATSAPP, ChatbotSettings, ChatLink, ChatTicket, InboundMessage, OutboundMessage

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
    for st in whatsapp.parse_statuses(payload):
        services.apply_status(st)                        # sent / delivered / read / failed (with Meta's reason)
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
                                                    address=msg.address, text=services.redact(msg.text))
        except IntegrityError:
            return  # redelivered: already answered
        if services.over_rate(msg.address):
            return
        services.acknowledge(msg.provider_id)            # blue ticks and "typing…" while we work out the answer
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
        'require_login': cfg.require_login, 'session_minutes': cfg.session_minutes,
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
            'allow_withdrawals': cfg.allow_withdrawals, 'withdraw_daily_cap': str(cfg.withdraw_daily_cap),
            'withdraw_cooldown_hours': cfg.withdraw_cooldown_hours,
            'require_login': cfg.require_login, 'session_minutes': cfg.session_minutes,
            'can_edit_withdrawals': bool(self.request.user.is_superuser),
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
        # Money leaving through chat: only a superuser may change these (the form
        # sends every field on each save, so it's a change that is refused, not presence).
        try:
            wanted = {}
            if 'allow_withdrawals' in request.data:
                wanted['allow_withdrawals'] = bool(request.data['allow_withdrawals'])
            if 'withdraw_daily_cap' in request.data:
                cap = Decimal(str(request.data['withdraw_daily_cap'])).quantize(Decimal('0.01'))
                if cap < 0:
                    raise InvalidOperation
                wanted['withdraw_daily_cap'] = cap
            if 'withdraw_cooldown_hours' in request.data:
                hours = int(request.data['withdraw_cooldown_hours'])
                if not 0 <= hours <= 720:
                    raise ValueError
                wanted['withdraw_cooldown_hours'] = hours
            if 'require_login' in request.data:
                wanted['require_login'] = bool(request.data['require_login'])
            if 'session_minutes' in request.data:
                minutes = int(request.data['session_minutes'])
                if not 1 <= minutes <= 120:
                    raise ValueError
                wanted['session_minutes'] = minutes
        except (InvalidOperation, ValueError, TypeError):
            return Response({'detail': 'Enter a withdrawal limit of 0 or more, a waiting time of 0 to 720 hours, '
                                       'and a login time of 1 to 120 minutes.'}, status=status.HTTP_400_BAD_REQUEST)
        changed_w = {k: v for k, v in wanted.items() if getattr(cfg, k) != v}
        if changed_w and not request.user.is_superuser:
            return Response({'detail': 'Only a superuser can change WhatsApp withdrawals or login.'}, status=status.HTTP_403_FORBIDDEN)
        for k, v in changed_w.items():
            setattr(cfg, k, v)
        if changed_w:
            accounts_services.audit(None, 'chatbot_withdrawals', request, **{k: str(v) for k, v in changed_w.items()})
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


class _SuperuserOnly(APIView):
    """Connection tools touch the live Meta account: superusers only."""
    permission_classes = [IsAdminUser]

    def _guard(self, request):
        if not request.user.is_superuser:
            return Response({'detail': 'Only a superuser can use the connection tools.'}, status=status.HTTP_403_FORBIDDEN)
        return None


class AdminChatbotNumbersView(_SuperuserOnly):
    """POST /api/admin/chatbot/numbers/ {waba_id} — the numbers (and their Phone number IDs) under a WhatsApp Business Account."""

    def post(self, request):
        return self._guard(request) or Response(whatsapp.list_numbers(str(request.data.get('waba_id') or '')))


class AdminChatbotProfileView(_SuperuserOnly):
    """GET/PUT /api/admin/chatbot/profile/ — the number's WhatsApp business profile
    (about, description, address, email, websites, category). Any staff member
    can read it; only a superuser changes what players see."""

    def get(self, request):
        return Response(whatsapp.get_profile())

    def put(self, request):
        denied = self._guard(request)
        if denied:
            return denied
        result = whatsapp.update_profile(request.data if isinstance(request.data, dict) else {})
        if result['ok']:
            accounts_services.audit(None, 'chatbot_profile', request, changed=','.join(result['changed']))
        return Response(result)


class AdminChatbotProfilePhotoView(_SuperuserOnly):
    """POST /api/admin/chatbot/profile/photo/ (multipart "file") — the profile photo."""
    parser_classes = [MultiPartParser]

    def post(self, request):
        denied = self._guard(request)
        if denied:
            return denied
        upload = request.FILES.get('file')
        if upload is None:
            return Response({'ok': False, 'error': 'Choose a photo.'})
        if upload.size > whatsapp.PHOTO_MAX:
            return Response({'ok': False, 'error': 'The photo must be under 5 MB.'})
        result = whatsapp.upload_profile_photo(upload.read(), upload.content_type or '')
        if result['ok']:
            accounts_services.audit(None, 'chatbot_profile', request, changed='photo')
        return Response(result)


class AdminChatbotRegisterView(_SuperuserOnly):
    """POST /api/admin/chatbot/register/ {pin} — register the configured number with the Cloud API."""

    def post(self, request):
        denied = self._guard(request)
        if denied:
            return denied
        result = whatsapp.register_number(str(request.data.get('pin') or ''))
        # The PIN is never logged or audited: only that a registration was tried.
        accounts_services.audit(None, 'chatbot_register', request, ok=result['ok'], code=result.get('code', ''))
        return Response(result)


# -- inbox ---------------------------------------------------------------------------

WINDOW = timedelta(hours=24)


def _last_in(address: str):
    row = InboundMessage.objects.filter(address=address).order_by('-received_at').first()
    return row.received_at if row else None


def _who(addresses: list[str]) -> dict:
    from apps.accounts.models import Player
    links = {link.address: link.player_id for link in ChatLink.objects.filter(address__in=addresses)}
    names = dict(Player.objects.filter(pk__in=set(links.values())).values_list('pk', 'username'))
    return {a: names.get(pid) for a, pid in links.items()}


class AdminInboxView(APIView):
    """GET /api/admin/chatbot/inbox/?q= — every conversation, most recent first,
    with who it is (when the number is linked), the last message and whether it
    needs a person: unanswered, or a reply that failed to send."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        from django.db.models import Max
        q = ''.join(ch for ch in request.query_params.get('q', '') if ch.isdigit())
        ins = {r['address']: r for r in InboundMessage.objects.values('address').annotate(last=Max('received_at'), n=Count('id'))}
        outs = {r['address']: r for r in OutboundMessage.objects.values('address').annotate(last=Max('created_at'), n=Count('id'))}
        addresses = sorted(set(ins) | set(outs), key=lambda a: max(filter(None, [ins.get(a, {}).get('last'), outs.get(a, {}).get('last')])),
                           reverse=True)
        if q:
            addresses = [a for a in addresses if q in a]
        addresses = addresses[:200]
        who = _who(addresses)
        since = timezone.now() - WINDOW
        failed = {r['address']: r['n'] for r in OutboundMessage.objects.filter(address__in=addresses, created_at__gte=since,
                                                                            status='failed').values('address').annotate(n=Count('id'))}
        rows = []
        for a in addresses:
            last_in, last_out = ins.get(a, {}).get('last'), outs.get(a, {}).get('last')
            latest_in = InboundMessage.objects.filter(address=a).order_by('-received_at').first()
            latest_out = OutboundMessage.objects.filter(address=a).order_by('-created_at').first()
            last = latest_in if (last_in and (not last_out or last_in >= last_out)) else latest_out
            rows.append({
                'address': a, 'player': who.get(a), 'incoming': ins.get(a, {}).get('n', 0), 'outgoing': outs.get(a, {}).get('n', 0),
                'last_at': (last_in if last is latest_in else last_out).isoformat(),
                'last_text': (last.text if last else '')[:120], 'last_direction': 'in' if last is latest_in else 'out',
                'unanswered': bool(last_in and (not last_out or last_in > last_out + timedelta(seconds=1))),
                'failed': failed.get(a, 0), 'can_reply': bool(last_in and last_in >= since),
            })
        return Response({'conversations': rows})


def _thread(address: str) -> dict:
    ins = list(InboundMessage.objects.filter(address=address).order_by('-received_at')[:100])
    outs = list(OutboundMessage.objects.filter(address=address).order_by('-created_at')[:100])
    messages = ([{'id': f'i{m.id}', 'direction': 'in', 'text': m.text, 'at': m.received_at.isoformat()} for m in ins]
                + [{'id': f'o{m.id}', 'direction': 'out', 'text': m.text, 'buttons': m.buttons, 'at': m.created_at.isoformat(),
                    'media': ({'kind': m.media_kind, 'url': f'/api/admin/chatbot/media/{m.id}/'} if m.media else None),
                    'status': m.status, 'status_label': m.get_status_display(), 'error': m.error, 'error_code': m.error_code,
                    'source': m.source, 'sent_by': m.sent_by} for m in outs])
    messages.sort(key=lambda m: m['at'])
    last_in = _last_in(address)
    return {'address': address, 'player': _who([address]).get(address), 'messages': messages[-120:],
            'can_reply': bool(last_in and last_in >= timezone.now() - WINDOW),
            'window_ends': (last_in + WINDOW).isoformat() if last_in else None}


class AdminInboxThreadView(APIView):
    """GET — one conversation. POST {text} — a staff reply (free text; WhatsApp allows it
    only within 24 hours of the customer's last message), or multipart {file, text}: a
    photo or video with an optional caption."""
    permission_classes = [IsAdminUser]
    parser_classes = [JSONParser, MultiPartParser]

    def get(self, request, address: str):
        return Response(_thread(''.join(ch for ch in address if ch.isdigit())))

    def post(self, request, address: str):
        address = ''.join(ch for ch in address if ch.isdigit())
        text = str(request.data.get('text') or '').strip()
        upload = request.FILES.get('file')
        if (not text and not upload) or len(text) > 1000:
            return Response({'detail': 'Write a message (or caption) of up to 1,000 characters, or attach a photo or video.'},
                            status=status.HTTP_400_BAD_REQUEST)
        last_in = _last_in(address)
        if not last_in or last_in < timezone.now() - WINDOW:
            return Response({'detail': 'WhatsApp only allows a free-text reply within 24 hours of the customer’s last message. '
                                       'They need to message us first.'}, status=status.HTTP_400_BAD_REQUEST)
        if upload:
            from common.attachments import AttachmentError, inspect
            try:
                found = inspect(upload)
            except AttachmentError as exc:
                return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            services.send_media(WHATSAPP, address, upload, found, text, by=request.user.get_username())
            accounts_services.audit(None, 'chat_staff_media', request, number=f'…{address[-4:]}', kind=found.kind, size=upload.size)
            return Response(_thread(address), status=status.HTTP_201_CREATED)
        services.send_now(WHATSAPP, address, [{'text': text}], source='staff', by=request.user.get_username())
        accounts_services.audit(None, 'chat_staff_message', request, number=f'…{address[-4:]}', length=len(text))
        return Response(_thread(address), status=status.HTTP_201_CREATED)


class AdminChatbotMediaView(APIView):
    """GET /api/admin/chatbot/media/<id>/ — a photo or video staff sent (staff only)."""
    permission_classes = [IsAdminUser]

    def get(self, request, pk: int):
        from django.http import FileResponse, Http404
        row = OutboundMessage.objects.filter(pk=pk).exclude(media='').first()
        if row is None:
            raise Http404
        return FileResponse(row.media.open('rb'), content_type=row.media_mime or 'application/octet-stream')


class AdminChatbotHealthView(APIView):
    """GET — is it working? Counts, the last message each way, and the reasons replies failed,
    with the likely fix. POST {to} — send a test message and say exactly what Meta answered."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        from django.db.models import Max
        since = timezone.now() - timedelta(hours=24)
        out24 = OutboundMessage.objects.filter(created_at__gte=since)
        by_status = {r['status']: r['n'] for r in out24.values('status').annotate(n=Count('id'))}
        reasons = [{'error': r['error'], 'code': r['error_code'], 'count': r['n'], 'last_at': r['last'].isoformat()}
                   for r in out24.filter(status='failed').exclude(error='').values('error', 'error_code')
                   .annotate(n=Count('id'), last=Max('created_at')).order_by('-n')[:5]]
        last_in = InboundMessage.objects.order_by('-received_at').first()
        last_out = OutboundMessage.objects.order_by('-created_at').first()
        problem = ''
        if not whatsapp.configured():
            problem = ('Replies cannot be sent: the access token or phone number ID is missing. '
                       'Fill in the Connection section of the WhatsApp bot page, then press Test connection.')
        elif last_in and not OutboundMessage.objects.filter(created_at__gte=last_in.received_at - timedelta(seconds=5)).exists() \
                and last_in.received_at < timezone.now() - timedelta(minutes=2):
            problem = 'Messages are arriving but no replies are being sent or logged. Restart the Django service and check its logs.'
        elif reasons and (last_out and last_out.status == 'failed'):
            problem = f'The latest reply failed: {reasons[0]["error"]}'
        return Response({
            'configured': whatsapp.configured(), 'problem': problem,
            'incoming_24h': InboundMessage.objects.filter(received_at__gte=since).count(),
            'outgoing_24h': out24.count(), 'by_status': by_status, 'failures': reasons,
            'last_incoming_at': last_in.received_at.isoformat() if last_in else None,
            'last_outgoing_at': last_out.created_at.isoformat() if last_out else None,
        })

    def post(self, request):
        to = ''.join(ch for ch in str(request.data.get('to') or '') if ch.isdigit())
        if not 8 <= len(to) <= 15:
            return Response({'detail': 'Enter the number with its country code, e.g. 263771234567.'}, status=status.HTTP_400_BAD_REQUEST)
        last_in = _last_in(to)
        in_window = bool(last_in and last_in >= timezone.now() - WINDOW)
        reply = {'text': f'✅ Test message from {engine._site()}. If you can read this, sending works.'}
        row = services.record(to, reply if in_window else {'text': 'Template “hello_world” (connection test)'}, source='test',
                              by=request.user.get_username())
        if in_window:
            services.transmit(row, reply)
        else:                                            # outside 24 hours only a template can be sent
            result = whatsapp.send_template(to)
            row.provider_id, row.error_code, row.error = result.provider_id, result.code, result.error
            row.status = row.Status.SENT if result.ok else row.Status.FAILED
            row.save(update_fields=['provider_id', 'status', 'error_code', 'error', 'updated_at'])
        return Response({'ok': row.status != 'failed', 'status': row.status, 'error': row.error, 'error_code': row.error_code,
                         'via': 'text' if in_window else 'template'})
