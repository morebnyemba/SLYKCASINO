"""WhatsApp Business Cloud API (Meta): webhook signature check, inbound
message parsing and sending replies.

Settings: Admin → WhatsApp bot (stored encrypted), falling back to the environment:
  WHATSAPP_TOKEN            — a permanent system-user access token
  WHATSAPP_PHONE_NUMBER_ID  — the sending number's id (not the number itself)
  WHATSAPP_APP_SECRET       — the Meta app secret; signs every webhook (X-Hub-Signature-256)
  WHATSAPP_VERIFY_TOKEN     — any string; Meta echoes it when you subscribe the webhook
  WHATSAPP_GRAPH_VERSION    — e.g. v21.0

Replies are free-form text (with up to three reply buttons), which WhatsApp
allows within 24 hours of the player's last message: the bot only ever answers.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from typing import Optional


logger = logging.getLogger(__name__)

MAX_TEXT = 4000          # WhatsApp allows 4096 characters
MAX_BUTTONS = 3
MAX_BUTTON_TITLE = 20


@dataclass(frozen=True)
class Inbound:
    provider_id: str
    address: str          # the sender's number, digits with country code
    text: str


def _setting(name: str) -> str:
    """A connection setting in force: the admin's (Admin → WhatsApp bot), else .env.prod's."""
    from . import config
    return config.value(name)


def configured() -> bool:
    return bool(_setting('token') and _setting('phone_number_id'))


def verify_token() -> str:
    return _setting('verify_token')


def display_number() -> str:
    return _setting('display_number')


def verify_signature(body: bytes, header: Optional[str]) -> bool:
    """Meta signs the raw body with the app secret. No secret configured means
    no webhook is trusted (fail closed)."""
    secret = _setting('app_secret')
    if not secret or not header or not header.startswith('sha256='):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header[len('sha256='):], expected)


def parse(payload: dict) -> list[Inbound]:
    """The messages in a webhook delivery (status updates and anything that
    isn't text or a button tap are ignored)."""
    out: list[Inbound] = []
    for entry in payload.get('entry') or []:
        for change in entry.get('changes') or []:
            value = change.get('value') or {}
            for m in value.get('messages') or []:
                kind, text = m.get('type'), ''
                if kind == 'text':
                    text = (m.get('text') or {}).get('body', '')
                elif kind == 'interactive':
                    i = m.get('interactive') or {}
                    reply = i.get('button_reply') or i.get('list_reply') or {}
                    text = reply.get('id') or reply.get('title') or ''
                elif kind == 'button':
                    text = (m.get('button') or {}).get('payload') or (m.get('button') or {}).get('text') or ''
                sender = ''.join(ch for ch in str(m.get('from', '')) if ch.isdigit())
                if m.get('id') and sender:
                    out.append(Inbound(provider_id=str(m['id'])[:128], address=sender[:32], text=str(text)[:500]))
    return out


MAX_LIST_ROWS = 10
MAX_ROW_TITLE = 24
MAX_ROW_DESCRIPTION = 72


def _button(b) -> tuple[str, str]:
    """A button is a command string (shown as is) or [command, label]."""
    if isinstance(b, (list, tuple)):
        return str(b[0]), str(b[1])
    return str(b), str(b)


def payload_for(to: str, reply: dict) -> dict:
    """The Graph API body for one reply:
    {'text': str, 'buttons': [cmd | [cmd, label], ...]}  → up to three reply buttons, or
    {'text': str, 'list': {'button': label, 'rows': [[cmd, title, description], ...]}} → a pick list.
    A button's or row's id is the command it sends, so a tap reads like typing it."""
    text = reply['text'][:MAX_TEXT]
    base = {'messaging_product': 'whatsapp', 'recipient_type': 'individual', 'to': to}
    pick_list = reply.get('list')
    if pick_list and pick_list.get('rows'):
        rows = [{'id': str(r[0])[:200], 'title': str(r[1])[:MAX_ROW_TITLE],
                 **({'description': str(r[2])[:MAX_ROW_DESCRIPTION]} if len(r) > 2 and r[2] else {})}
                for r in pick_list['rows'][:MAX_LIST_ROWS]]
        return {**base, 'type': 'interactive', 'interactive': {
            'type': 'list', 'body': {'text': text[:1024]},
            'action': {'button': str(pick_list.get('button') or 'Choose')[:MAX_BUTTON_TITLE],
                       'sections': [{'title': str(pick_list.get('title') or 'Picks')[:MAX_ROW_TITLE], 'rows': rows}]},
        }}
    buttons = [_button(b) for b in reply.get('buttons') or [] if b][:MAX_BUTTONS]
    if not buttons:
        return {**base, 'type': 'text', 'text': {'body': text, 'preview_url': False}}
    return {**base, 'type': 'interactive', 'interactive': {
        'type': 'button', 'body': {'text': text[:1024]},
        'action': {'buttons': [{'type': 'reply', 'reply': {'id': cmd[:256], 'title': label[:MAX_BUTTON_TITLE]}}
                               for cmd, label in buttons]},
    }}


def check_connection() -> dict:
    """Ask Meta about the configured number with the configured token: the
    business name and number it's registered as, or why it failed."""
    if not configured():
        return {'ok': False, 'error': 'Add the phone number ID and access token first.'}
    import requests
    url = f'https://graph.facebook.com/{_setting("graph_version")}/{_setting("phone_number_id")}'
    try:
        res = requests.get(url, timeout=10, headers={'Authorization': f'Bearer {_setting("token")}'},
                           params={'fields': 'display_phone_number,verified_name,quality_rating'})
    except requests.RequestException as exc:
        return {'ok': False, 'error': f'Could not reach Meta: {exc.__class__.__name__}.'}
    try:
        body = res.json()
    except ValueError:
        body = {}
    if res.status_code >= 300:
        err = (body.get('error') or {}).get('message') or f'Meta answered {res.status_code}.'
        return {'ok': False, 'error': str(err)[:300]}
    return {'ok': True, 'verified_name': body.get('verified_name', ''),
            'display_phone_number': body.get('display_phone_number', ''),
            'quality_rating': body.get('quality_rating', '')}


def send(to: str, reply: dict) -> bool:
    """Send one reply. False (logged) when not configured or Meta refuses."""
    if not configured():
        logger.info('whatsapp not configured; reply to %s dropped', to[-4:])
        return False
    import requests
    url = f'https://graph.facebook.com/{_setting("graph_version")}/{_setting("phone_number_id")}/messages'
    try:
        res = requests.post(url, json=payload_for(to, reply), timeout=10,
                            headers={'Authorization': f'Bearer {_setting("token")}'})
    except requests.RequestException:
        logger.warning('whatsapp send to %s failed', to[-4:], exc_info=True)
        return False
    if res.status_code >= 300:
        logger.warning('whatsapp send to %s refused: %s %s', to[-4:], res.status_code, res.text[:300])
        return False
    return True
