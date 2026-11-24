"""WhatsApp Business Cloud API (Meta): webhook signature check, inbound
message parsing and sending replies.

Settings: Admin → WhatsApp bot (stored encrypted), falling back to the environment:
  WHATSAPP_TOKEN            — a permanent system-user access token
  WHATSAPP_PHONE_NUMBER_ID  — the sending number's id (not the number itself); the only ID sending uses
  WHATSAPP_BUSINESS_ACCOUNT_ID — the account the number belongs to (optional: checks, number lookup)
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


def _graph(method: str, path: str, **kw):
    """One Graph API call with the configured token. Returns (response, error_text);
    exactly one of them is None."""
    import requests
    url = f'https://graph.facebook.com/{_setting("graph_version")}/{path}'
    try:
        res = requests.request(method, url, timeout=10, headers={'Authorization': f'Bearer {_setting("token")}'}, **kw)
    except requests.RequestException as exc:
        return None, f'Could not reach Meta: {exc.__class__.__name__}.'
    return res, None


def _json(res) -> dict:
    try:
        body = res.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def check_connection() -> dict:
    """Ask Meta about the configured number with the configured token: the
    business name and number it's registered as, or why it failed. With the
    WhatsApp Business Account ID also set, it can tell a wrong ID from a token
    without access, and checks the number belongs to that account."""
    if not configured():
        return {'ok': False, 'error': 'Add the phone number ID and access token first.'}
    pid, waba = _setting('phone_number_id'), _setting('waba_id')
    if waba and pid == waba:
        return {'ok': False, 'code': 'same_id',
                'error': 'The phone number ID box holds the WhatsApp Business Account ID. Use "Find my numbers" to get the phone number ID.'}
    res, err = _graph('GET', pid, params={'fields': 'display_phone_number,verified_name,quality_rating'})
    if err:
        return {'ok': False, 'error': err}
    if res.status_code >= 300:
        code, text = _meta_error(res)
        out = {'ok': False, 'error': text, 'code': code}
        if code == '100' and waba:
            out.update(_diagnose_id(pid, waba))
        return out
    body = _json(res)
    out = {'ok': True, 'verified_name': body.get('verified_name', ''),
           'display_phone_number': body.get('display_phone_number', ''),
           'quality_rating': body.get('quality_rating', '')}
    warnings = []
    # Registration state is a second, tolerant request: if Meta rejects these
    # fields the connection is still good, we just can't say if it is registered.
    res2, _ = _graph('GET', pid, params={'fields': 'platform_type,status,code_verification_status'})
    if res2 is not None and res2.status_code < 300:
        extra = _json(res2)
        out.update(platform_type=extra.get('platform_type', ''), status=extra.get('status', ''),
                   code_verification_status=extra.get('code_verification_status', ''))
        if extra.get('platform_type') and extra['platform_type'] != 'CLOUD_API':
            warnings.append('This number is not registered with the Cloud API, so it cannot send yet. '
                            'Use "Register number" with a 6-digit PIN.')
    if waba:
        listed = list_numbers(waba)
        if listed['ok'] and pid not in {n['id'] for n in listed['numbers']}:
            warnings.append('This number is not under the WhatsApp Business Account ID you entered: one of the two IDs is wrong.')
        subs, _ = _graph('GET', f'{waba}/subscribed_apps')
        if subs is not None and subs.status_code < 300 and not (_json(subs).get('data') or []):
            warnings.append('No app is subscribed to this WhatsApp Business Account, so incoming messages will not reach the bot.')
    if warnings:
        out['warning'] = ' '.join(warnings)
    return out


def _diagnose_id(pid: str, waba: str) -> dict:
    """Meta's error 100 means "no such ID" or "no access", without saying which.
    Asking for the account's numbers tells them apart."""
    listed = list_numbers(waba)
    if listed['ok']:
        numbers = listed['numbers']
        if pid in {n['id'] for n in numbers}:
            return {'diagnosis': 'The token can see the account but not this number: give the system user full control of the WhatsApp account.'}
        names = ', '.join(f'{n["display_phone_number"]} (ID {n["id"]})' for n in numbers[:5]) or 'none'
        return {'diagnosis': f'The phone number ID is wrong. This account\'s numbers: {names}. Pick one under "Find my numbers".',
                'numbers': numbers}
    if listed.get('code') == '100':
        return {'diagnosis': 'The token cannot see this WhatsApp Business Account either: it is a token problem, not the ID. '
                             'Assign the account to the token\'s system user (full control) and give it whatsapp_business_messaging.'}
    return {}


def list_numbers(waba_id: str = '') -> dict:
    """The phone numbers (with their IDs) under a WhatsApp Business Account, so
    staff can copy the right Phone number ID instead of guessing. Without an ID,
    the configured one."""
    waba_id = (waba_id or _setting('waba_id') or '').strip()
    if not waba_id:
        return {'ok': False, 'error': 'Enter the WhatsApp Business Account ID.'}
    if not waba_id.isdigit():
        return {'ok': False, 'error': 'The WhatsApp Business Account ID is digits only.'}
    if not _setting('token'):
        return {'ok': False, 'error': 'Add the access token first.'}
    fields = 'id,display_phone_number,verified_name,quality_rating,code_verification_status'
    res, err = _graph('GET', f'{waba_id}/phone_numbers', params={'fields': fields})
    if err:
        return {'ok': False, 'error': err}
    if res.status_code >= 300:
        code, text = _meta_error(res)
        if code == '100':
            text = ('Meta cannot find that WhatsApp Business Account with this token. Check the ID, and that the token\'s system user '
                    f'has been assigned this account. ({text[-160:]})')
        return {'ok': False, 'error': text[:400], 'code': code}
    rows = [{'id': str(r.get('id', '')), 'display_phone_number': r.get('display_phone_number', ''),
             'verified_name': r.get('verified_name', ''), 'quality_rating': r.get('quality_rating', ''),
             'code_verification_status': r.get('code_verification_status', '')}
            for r in _json(res).get('data') or []]
    return {'ok': True, 'numbers': rows, 'current': _setting('phone_number_id')}


def register_number(pin: str) -> dict:
    """Register the configured number with the Cloud API using a 6-digit PIN
    (the two-step verification PIN; it is set the first time)."""
    pin = (pin or '').strip()
    if not (pin.isdigit() and len(pin) == 6):
        return {'ok': False, 'error': 'The PIN is exactly 6 digits.'}
    if not configured():
        return {'ok': False, 'error': 'Add the phone number ID and access token first.'}
    res, err = _graph('POST', f'{_setting("phone_number_id")}/register', json={'messaging_product': 'whatsapp', 'pin': pin})
    if err:
        return {'ok': False, 'error': err}
    if res.status_code >= 300:
        code, text = _meta_error(res)
        return {'ok': False, 'error': text, 'code': code}
    return {'ok': True}


@dataclass(frozen=True)
class SendResult:
    ok: bool
    provider_id: str = ''
    error: str = ''
    code: str = ''


def _meta_error(res) -> tuple[str, str]:
    """(code, text) from a failed Graph API response, in words staff can act on."""
    try:
        err = (res.json() or {}).get('error') or {}
    except ValueError:
        err = {}
    code = str(err.get('code') or res.status_code)
    detail = ((err.get('error_data') or {}).get('details') or err.get('message') or res.text[:200] or '').strip()
    hint = {
        '190': 'The access token is invalid or has expired (a temporary token lasts 24 hours: create a permanent system-user token).',
        '100': 'Meta cannot find this phone number ID with this token. Either it is not the Phone number ID (a WhatsApp Business Account ID '
               'looks the same), or the token\'s system user has not been given the WhatsApp account. '
               'Use "Find my numbers" to look the ID up.',
        '200': 'This token is not allowed to use this WhatsApp account: assign the account to its system user with full control, '
               'and give the token whatsapp_business_messaging.',
        '10': 'This token lacks permission: it needs whatsapp_business_management and whatsapp_business_messaging.',
        '133010': 'This number is not registered with the Cloud API yet: use "Register number" with a 6-digit PIN.',
        '133005': 'The registration PIN is wrong.',
        '133016': 'Too many registration attempts: Meta blocks this number from registering for a while.',
        '131030': 'This recipient is not on the allowed list (a number in test mode can only message numbers added in Meta).',
        '131047': 'More than 24 hours since this person last wrote: free-text replies are blocked until they message again.',
        '131026': 'The message could not be delivered: this number may not be on WhatsApp, or has blocked the business.',
        '131031': 'The business account is locked or restricted by Meta.',
        '130429': 'Meta is rate-limiting this number: too many messages too fast.',
    }.get(code, '')
    return code, (f'{hint} ({detail})' if hint and detail else hint or detail or f'Meta answered {res.status_code}.')[:400]


def send(to: str, reply: dict) -> SendResult:
    """Send one reply. Never raises; the result says what Meta answered."""
    if not configured():
        missing = [n for n, k in (('access token', 'token'), ('phone number ID', 'phone_number_id')) if not _setting(k)]
        logger.warning('whatsapp not connected (missing %s); reply to …%s not sent', ' and '.join(missing), to[-4:])
        return SendResult(False, error=f'WhatsApp is not connected: the {" and ".join(missing)} {"is" if len(missing) == 1 else "are"} not set '
                                      '(Admin → WhatsApp bot → Connection).', code='not_configured')
    import requests
    url = f'https://graph.facebook.com/{_setting("graph_version")}/{_setting("phone_number_id")}/messages'
    try:
        res = requests.post(url, json=payload_for(to, reply), timeout=10,
                            headers={'Authorization': f'Bearer {_setting("token")}'})
    except requests.RequestException as exc:
        logger.warning('whatsapp send to …%s failed: %s', to[-4:], exc.__class__.__name__)
        return SendResult(False, error=f'Could not reach Meta ({exc.__class__.__name__}). Check the server can reach graph.facebook.com.',
                          code='network')
    if res.status_code >= 300:
        code, text = _meta_error(res)
        logger.warning('whatsapp send to …%s refused: %s %s', to[-4:], code, text)
        return SendResult(False, error=text, code=code)
    try:
        wamid = ((res.json().get('messages') or [{}])[0]).get('id', '')
    except (ValueError, AttributeError, IndexError):
        wamid = ''
    return SendResult(True, provider_id=wamid)


def send_template(to: str, name: str = 'hello_world', language: str = 'en_US') -> SendResult:
    """A template message: the only kind WhatsApp lets a business send to someone
    who hasn't written in the last 24 hours (used for the connection test)."""
    if not configured():
        return send(to, {'text': ''})                    # the same "not connected" answer
    import requests
    url = f'https://graph.facebook.com/{_setting("graph_version")}/{_setting("phone_number_id")}/messages'
    body = {'messaging_product': 'whatsapp', 'to': to, 'type': 'template', 'template': {'name': name, 'language': {'code': language}}}
    try:
        res = requests.post(url, json=body, timeout=10, headers={'Authorization': f'Bearer {_setting("token")}'})
    except requests.RequestException as exc:
        return SendResult(False, error=f'Could not reach Meta ({exc.__class__.__name__}).', code='network')
    if res.status_code >= 300:
        code, text = _meta_error(res)
        return SendResult(False, error=('The “hello_world” template does not exist on this number: message the bot from that '
                                        'phone first, then send the test again.' if code == '132001' else text), code=code)
    try:
        return SendResult(True, provider_id=((res.json().get('messages') or [{}])[0]).get('id', ''))
    except (ValueError, AttributeError):
        return SendResult(True)


def mark_read(message_id: str, *, typing: bool = True) -> bool:
    """Blue ticks for the customer's message and, with `typing`, the "typing…"
    indicator (it shows until we reply or for up to 25 seconds). Best effort."""
    if not configured() or not message_id:
        return False
    import requests
    body = {'messaging_product': 'whatsapp', 'status': 'read', 'message_id': message_id}
    if typing:
        body['typing_indicator'] = {'type': 'text'}
    url = f'https://graph.facebook.com/{_setting("graph_version")}/{_setting("phone_number_id")}/messages'
    try:
        res = requests.post(url, json=body, timeout=8, headers={'Authorization': f'Bearer {_setting("token")}'})
    except requests.RequestException:
        return False
    if res.status_code >= 300:
        logger.warning('whatsapp mark-as-read refused: %s', _meta_error(res)[1])
        return False
    return True


@dataclass(frozen=True)
class Status:
    provider_id: str
    status: str          # sent | delivered | read | failed
    code: str = ''
    error: str = ''


def parse_statuses(payload: dict) -> list[Status]:
    """Meta's delivery reports for the messages we sent."""
    out: list[Status] = []
    for entry in payload.get('entry') or []:
        for change in entry.get('changes') or []:
            for st in (change.get('value') or {}).get('statuses') or []:
                if not st.get('id') or st.get('status') not in ('sent', 'delivered', 'read', 'failed'):
                    continue
                err = (st.get('errors') or [{}])[0]
                detail = ((err.get('error_data') or {}).get('details') or err.get('message') or err.get('title') or '')
                out.append(Status(provider_id=str(st['id'])[:128], status=st['status'], code=str(err.get('code') or ''),
                                  error=str(detail)[:400]))
    return out
