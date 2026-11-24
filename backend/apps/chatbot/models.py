"""Chat betting: a player's WhatsApp number linked to their account, the
conversation state, and every inbound message (so a redelivered webhook is
handled once). Channel-agnostic: `channel` is 'whatsapp' today; the same rows
serve another messenger later."""
from __future__ import annotations

from decimal import Decimal

from django.db import models

WHATSAPP = 'whatsapp'
CHANNELS = [(WHATSAPP, 'WhatsApp')]


class ChatbotSettings(models.Model):
    """One row. Operator switches and limits for betting through chat."""
    enabled = models.BooleanField(default=True)
    allow_betting = models.BooleanField(default=True)
    allow_deposits = models.BooleanField(default=True)
    # The most one ticket placed through chat may stake.
    max_stake = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('50.00'))
    # Total stakes a player may place through chat in a day (a player can set lower).
    daily_cap = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('200.00'))
    # Stakes above this need the player's chat PIN (set on the website). 0 = every bet.
    pin_above = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('20.00'))

    # -- the WhatsApp connection (Meta Cloud API), set in the admin. Blank = use
    # the WHATSAPP_* value from .env.prod. Secrets are stored encrypted (secrets.py)
    # and never sent back to the browser.
    phone_number_id = models.CharField(max_length=32, blank=True, default='')
    waba_id = models.CharField(max_length=32, blank=True, default='')
    display_number = models.CharField(max_length=32, blank=True, default='')
    graph_version = models.CharField(max_length=10, blank=True, default='')
    time_zone = models.CharField(max_length=64, blank=True, default='')
    token_enc = models.TextField(blank=True, default='')
    app_secret_enc = models.TextField(blank=True, default='')
    verify_token_enc = models.TextField(blank=True, default='')
    connection_updated_by = models.CharField(max_length=150, blank=True, default='')
    connection_updated_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'chatbot_settings'

    @classmethod
    def load(cls) -> 'ChatbotSettings':
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ChatLink(models.Model):
    """A chat address (a WhatsApp number, digits only with country code) that
    may act for one player. Made only from the player's logged-in account (a
    one-time code), never from the chat alone."""
    channel = models.CharField(max_length=16, choices=CHANNELS, default=WHATSAPP)
    address = models.CharField(max_length=32)
    player_id = models.IntegerField(db_index=True)
    linked_at = models.DateTimeField(auto_now_add=True)
    # Hashed chat PIN (django password hasher); blank = none set.
    pin_hash = models.CharField(max_length=128, blank=True, default='')
    # The player's own daily chat staking cap (None = the operator's).
    daily_cap = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'chatbot_link'
        constraints = [
            models.UniqueConstraint(fields=['channel', 'address'], name='chatbot_one_player_per_address'),
            models.UniqueConstraint(fields=['channel', 'player_id'], name='chatbot_one_address_per_player'),
        ]


class LinkCode(models.Model):
    """A short-lived one-time code a logged-in player sends from chat to link it."""
    player_id = models.IntegerField(db_index=True)
    code = models.CharField(max_length=8, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'chatbot_link_code'


class ChatSession(models.Model):
    """Where a conversation is: the slip being built and a bet waiting for YES."""
    channel = models.CharField(max_length=16, choices=CHANNELS, default=WHATSAPP)
    address = models.CharField(max_length=32)
    state = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'chatbot_session'
        constraints = [models.UniqueConstraint(fields=['channel', 'address'], name='chatbot_one_session_per_address')]


class InboundMessage(models.Model):
    """Every message received. `provider_id` is the messenger's own id, unique,
    so a webhook delivered twice is handled once."""
    channel = models.CharField(max_length=16, choices=CHANNELS, default=WHATSAPP)
    provider_id = models.CharField(max_length=128, unique=True)
    address = models.CharField(max_length=32, db_index=True)
    text = models.CharField(max_length=500, blank=True, default='')
    received_at = models.DateTimeField(auto_now_add=True)
    replies = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'chatbot_inbound'
        ordering = ['-received_at']


class ChatTicket(models.Model):
    """A ticket placed through chat (for the daily cap and reporting)."""
    class Kind(models.TextChoices):
        BET = 'bet', 'Single'
        SLIP = 'slip', 'Multiple'

    channel = models.CharField(max_length=16, choices=CHANNELS, default=WHATSAPP)
    player_id = models.IntegerField(db_index=True)
    kind = models.CharField(max_length=4, choices=Kind.choices)
    object_id = models.IntegerField()
    stake = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'chatbot_ticket'


class OutboundMessage(models.Model):
    """Every message we send, with what happened to it: the delivery log behind
    the admin inbox. `status` follows Meta's own reports (sent, delivered, read,
    failed); `error` says why when it failed or was never sent."""
    class Status(models.TextChoices):
        QUEUED = 'queued', 'Sending'
        SENT = 'sent', 'Sent'
        DELIVERED = 'delivered', 'Delivered'
        READ = 'read', 'Read'
        FAILED = 'failed', 'Failed'

    class Source(models.TextChoices):
        BOT = 'bot', 'Bot'
        STAFF = 'staff', 'Staff'
        TEST = 'test', 'Test'

    channel = models.CharField(max_length=16, choices=CHANNELS, default=WHATSAPP)
    address = models.CharField(max_length=32, db_index=True)
    text = models.TextField()
    buttons = models.JSONField(default=list, blank=True)
    source = models.CharField(max_length=8, choices=Source.choices, default=Source.BOT)
    sent_by = models.CharField(max_length=150, blank=True, default='')
    provider_id = models.CharField(max_length=128, blank=True, default='', db_index=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED, db_index=True)
    error_code = models.CharField(max_length=20, blank=True, default='')
    error = models.CharField(max_length=400, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'chatbot_outbound'
        ordering = ['-created_at']
