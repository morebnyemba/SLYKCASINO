"""The WhatsApp connection settings, from the admin first and .env.prod second.

Every part of the bot reads them through value(), so a change in the admin
takes effect on the next message, with no redeploy. Secrets are stored
encrypted (secrets.py) and never leave the server: the admin page only learns
whether one is set and its last four characters.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.utils import timezone

from . import secrets
from .models import ChatbotSettings


@dataclass(frozen=True)
class Field:
    column: str
    env: str
    secret: bool = False
    default: str = ''
    label: str = ''


FIELDS: dict[str, Field] = {
    'phone_number_id': Field('phone_number_id', 'WHATSAPP_PHONE_NUMBER_ID', label='Phone number ID'),
    'waba_id': Field('waba_id', 'WHATSAPP_BUSINESS_ACCOUNT_ID', label='WhatsApp Business Account ID'),
    'display_number': Field('display_number', 'WHATSAPP_DISPLAY_NUMBER', label='Number shown to players'),
    'token': Field('token_enc', 'WHATSAPP_TOKEN', secret=True, label='Access token'),
    'app_secret': Field('app_secret_enc', 'WHATSAPP_APP_SECRET', secret=True, label='App secret'),
    'verify_token': Field('verify_token_enc', 'WHATSAPP_VERIFY_TOKEN', secret=True, label='Webhook verify token'),
    'graph_version': Field('graph_version', 'WHATSAPP_GRAPH_VERSION', default='v21.0', label='Graph API version'),
    'time_zone': Field('time_zone', 'CHATBOT_TIME_ZONE', default='Africa/Harare', label='Players’ time zone'),
}


class ConfigError(ValueError):
    """A setting that can't be saved (shown to staff)."""


def _stored(f: Field, cfg: ChatbotSettings) -> Optional[str]:
    raw = getattr(cfg, f.column) or ''
    return secrets.decrypt(raw) if f.secret else raw


def value(name: str, cfg: Optional[ChatbotSettings] = None) -> str:
    """The setting in force: the admin's, else .env.prod's, else the default."""
    f = FIELDS[name]
    cfg = cfg or ChatbotSettings.load()
    stored = _stored(f, cfg)
    if stored:
        return stored
    return str(getattr(settings, f.env, '') or '') or f.default


def source(name: str, cfg: ChatbotSettings) -> str:
    """Where the value in force comes from: admin · env · default · unset ·
    unreadable (stored encrypted under a key that has since changed)."""
    f = FIELDS[name]
    stored = _stored(f, cfg)
    if stored is None:
        return 'unreadable'
    if stored:
        return 'admin'
    if getattr(settings, f.env, ''):
        return 'env'
    return 'default' if f.default else 'unset'


def describe(cfg: Optional[ChatbotSettings] = None) -> dict:
    """What the admin page may see: plain settings in full, secrets as set/hint only."""
    cfg = cfg or ChatbotSettings.load()
    out = {}
    for name, f in FIELDS.items():
        v = value(name, cfg)
        out[name] = {'label': f.label, 'source': source(name, cfg), 'env': f.env, 'secret': f.secret,
                     **({'set': bool(v), 'hint': secrets.hint(v)} if f.secret else {'value': v})}
    out['updated_by'] = cfg.connection_updated_by
    out['updated_at'] = cfg.connection_updated_at
    return out


def _validate(name: str, v: str) -> str:
    v = v.strip()
    if name == 'phone_number_id' and v and not v.isdigit():
        raise ConfigError('The phone number ID is the long number from Meta (WhatsApp → API setup), digits only.')
    if name == 'waba_id' and v and not v.isdigit():
        raise ConfigError('The WhatsApp Business Account ID is the long number from Meta, digits only.')
    if name == 'graph_version' and v and not re.fullmatch(r'v\d{1,2}\.\d', v):
        raise ConfigError('The Graph API version looks like v21.0.')
    if name == 'time_zone' and v:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ConfigError(f'“{v}” is not a time zone. Use a name like Africa/Harare.') from exc
    if name == 'display_number' and len(v) > 32:
        raise ConfigError('The number shown to players is at most 32 characters.')
    if name in ('token', 'app_secret', 'verify_token'):
        if len(v) > 1000 or any(ch.isspace() for ch in v):
            raise ConfigError(f'The {FIELDS[name].label.lower()} has no spaces. Paste it again.')
        if name == 'verify_token' and len(v) < 12:
            raise ConfigError('Use a verify token of at least 12 characters.')
    return v


def update(data: dict, *, by: str) -> list[str]:
    """Apply the admin's changes. A field left out (or a blank secret) stays as
    it is; `clear` lists fields to empty so .env.prod's value applies again.
    Returns the names of the fields that changed (never their values)."""
    cfg = ChatbotSettings.load()
    changed: list[str] = []
    clear = set(data.get('clear') or [])
    unknown = clear - set(FIELDS)
    if unknown:
        raise ConfigError(f'Unknown setting: {", ".join(sorted(unknown))}.')
    for name, f in FIELDS.items():
        if name in clear:
            if getattr(cfg, f.column):
                setattr(cfg, f.column, '')
                changed.append(name)
            continue
        if name not in data or data[name] is None:
            continue
        v = _validate(name, str(data[name]))
        if f.secret:
            if not v:
                continue                     # a blank secret box means "keep it"
            setattr(cfg, f.column, secrets.encrypt(v))
            changed.append(name)
        elif v != getattr(cfg, f.column):
            setattr(cfg, f.column, v)
            changed.append(name)
    if cfg.phone_number_id and cfg.phone_number_id == cfg.waba_id:
        raise ConfigError('The phone number ID and the WhatsApp Business Account ID are different numbers: '
                          'the same ID is in both boxes. Use "Find my numbers" to get the phone number ID.')
    if changed:
        cfg.connection_updated_by = by[:150]
        cfg.connection_updated_at = timezone.now()
        cfg.save()
    return changed
