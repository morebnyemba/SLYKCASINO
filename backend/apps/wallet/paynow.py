"""Paynow (paynow.co.zw) — Zimbabwe's payment gateway, for EcoCash, OneMoney
and InnBucks (express checkout: the player approves a prompt on their phone)
and cards (web checkout: the player is redirected to Paynow's page).

Every message to and from Paynow is url-encoded and signed: the hash is the
upper-case SHA-512 of all field values in order (hash excluded) followed by the
integration key. Inbound messages without a valid hash are rejected.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import parse_qsl, urlencode

import requests
from django.conf import settings

INITIATE_URL = 'https://www.paynow.co.zw/interface/initiatetransaction'
REMOTE_URL = 'https://www.paynow.co.zw/interface/remotetransaction'

MOBILE_METHODS = ('ecocash', 'onemoney', 'innbucks')
METHODS = (*MOBILE_METHODS, 'card')

# Paynow transaction statuses, as they arrive (compared case-insensitively).
PAID_STATUSES = {'paid', 'awaiting delivery', 'delivered'}
CANCELLED_STATUSES = {'cancelled'}
FAILED_STATUSES = {'failed', 'disputed', 'refunded'}

TIMEOUT = 20


class PaynowError(Exception):
    """Paynow refused the request, or answered with something we can't trust."""


@dataclass(frozen=True)
class PaynowConfig:
    integration_id: str
    integration_key: str
    result_url: str
    return_url: str
    auth_email: str


def get_config() -> PaynowConfig:
    """Credentials saved in the admin console win; the server environment
    (PAYNOW_*) fills anything left blank there."""
    from .models import PaymentGateway
    saved = PaymentGateway.current()
    frontend = getattr(settings, 'FRONTEND_URL', '').rstrip('/')
    return PaynowConfig(
        integration_id=(saved and saved.paynow_integration_id) or getattr(settings, 'PAYNOW_INTEGRATION_ID', ''),
        integration_key=(saved and saved.paynow_integration_key) or getattr(settings, 'PAYNOW_INTEGRATION_KEY', ''),
        result_url=getattr(settings, 'PAYNOW_RESULT_URL', '') or f'{frontend}/api/wallet/paynow/result/',
        return_url=getattr(settings, 'PAYNOW_RETURN_URL', '') or f'{frontend}/deposit/return',
        auth_email=(saved and saved.paynow_auth_email) or getattr(settings, 'PAYNOW_AUTH_EMAIL', ''),
    )


def is_configured() -> bool:
    cfg = get_config()
    return bool(cfg.integration_id and cfg.integration_key)


def make_hash(values, key: str) -> str:
    joined = ''.join(str(v) for v in values) + key
    return hashlib.sha512(joined.encode('utf-8')).hexdigest().upper()


def sign(fields: list[tuple[str, str]], key: str) -> list[tuple[str, str]]:
    return [*fields, ('hash', make_hash((v for _, v in fields), key))]


def parse_signed(body: str | bytes, key: str) -> dict[str, str]:
    """Parse a url-encoded Paynow message and verify its hash. Error replies
    are unsigned; they raise PaynowError with Paynow's message."""
    if isinstance(body, bytes):
        body = body.decode('utf-8', errors='replace')
    pairs = parse_qsl(body, keep_blank_values=True)
    fields = {k.lower(): v for k, v in pairs}
    if fields.get('status', '').lower() == 'error':
        raise PaynowError(fields.get('error') or 'Paynow rejected the request')
    received = fields.get('hash', '')
    expected = make_hash((v for k, v in pairs if k.lower() != 'hash'), key)
    if not received or not hmac.compare_digest(received.upper(), expected):
        raise PaynowError('Paynow message failed hash verification')
    return fields


def normalise_phone(raw: str) -> str:
    """Zimbabwe mobile numbers as Paynow wants them: 07XXXXXXXX."""
    digits = ''.join(ch for ch in raw or '' if ch.isdigit())
    if digits.startswith('263'):
        digits = '0' + digits[3:]
    elif len(digits) == 9 and digits.startswith('7'):
        digits = '0' + digits
    if len(digits) != 10 or not digits.startswith('07'):
        raise ValueError('Enter a valid Zimbabwe mobile number, e.g. 0771234567.')
    return digits


@dataclass(frozen=True)
class Initiated:
    poll_url: str
    provider_ref: str
    redirect_url: str
    instructions: str


def _post(url: str, data: list[tuple[str, str]] | None = None) -> str:
    try:
        res = requests.post(url, data=urlencode(data or []), timeout=TIMEOUT,
                            headers={'Content-Type': 'application/x-www-form-urlencoded'})
    except requests.RequestException as exc:
        raise PaynowError(f'Could not reach Paynow: {exc.__class__.__name__}') from exc
    if res.status_code >= 400:
        raise PaynowError(f'Paynow answered HTTP {res.status_code}')
    return res.text


def initiate(*, reference: str, amount: Decimal, method: str, phone: str = '', info: str = '') -> Initiated:
    """Start a payment. Mobile methods push an approval prompt to `phone`;
    `card` returns a Paynow page to redirect the player to."""
    cfg = get_config()
    if not is_configured():
        raise PaynowError('Paynow is not configured')
    fields = [
        ('id', cfg.integration_id),
        ('reference', reference),
        ('amount', f'{Decimal(amount):.2f}'),
        ('additionalinfo', info or f'Deposit {reference}'),
        ('returnurl', f'{cfg.return_url}?ref={reference}'),
        ('resulturl', cfg.result_url),
    ]
    if method in MOBILE_METHODS:
        fields += [('authemail', cfg.auth_email), ('phone', phone), ('method', method)]
        url = REMOTE_URL
    elif method == 'card':
        if cfg.auth_email:
            fields.append(('authemail', cfg.auth_email))
        url = INITIATE_URL
    else:
        raise ValueError(f'Unsupported payment method: {method}')
    fields.append(('status', 'Message'))

    reply = parse_signed(_post(url, sign(fields, cfg.integration_key)), cfg.integration_key)
    if reply.get('status', '').lower() != 'ok':
        raise PaynowError(reply.get('error') or 'Paynow did not accept the payment')

    instructions = reply.get('instructions', '')
    code = reply.get('authorizationcode')
    if method == 'innbucks' and code:
        instructions = f'Approve the payment in your InnBucks app with code {code}.'
    return Initiated(
        poll_url=reply.get('pollurl', ''),
        provider_ref=reply.get('paynowreference', ''),
        redirect_url=reply.get('browserurl', ''),
        instructions=instructions,
    )


def check_credentials() -> str:
    """Prove the saved Integration ID and key work: start a $1 card checkout
    that nobody pays (it simply expires — no money moves). Returns Paynow's
    reference; raises PaynowError with Paynow's reason otherwise."""
    import uuid
    started = initiate(
        reference=f'TEST{uuid.uuid4().hex[:12].upper()}', amount=Decimal('1.00'), method='card',
        info='Connection test from the BetBlits admin console',
    )
    return started.provider_ref


def poll(poll_url: str) -> dict[str, str]:
    """Current status of a payment, straight from Paynow (hash-verified)."""
    return parse_signed(_post(poll_url), get_config().integration_key)


def outcome(paynow_status: str) -> str:
    """Map a Paynow status onto PaymentTransaction.Status values."""
    s = (paynow_status or '').strip().lower()
    if s in PAID_STATUSES:
        return 'paid'
    if s in CANCELLED_STATUSES:
        return 'cancelled'
    if s in FAILED_STATUSES:
        return 'failed'
    return 'pending'
