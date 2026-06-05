"""livechat domain logic — the ONLY place livechat mutations happen."""
from __future__ import annotations

from typing import Optional

from django.db import transaction

from . import helpers, utils
from .clients import RealtimePublisherClient
from .models import ChatMessage


def list_messages(channel: Optional[str] = None, limit: int = 50):
    qs = ChatMessage.objects.all()
    if channel:
        qs = qs.filter(channel=channel)
    return qs[:limit]


@transaction.atomic
def post_message(*, body: str, channel: str = 'lobby', player_id: Optional[int] = None) -> ChatMessage:
    """Persist a message, then attempt realtime publish (delivery tracked)."""
    errors = helpers.validate_message_structure({'body': body})
    if errors:
        raise ValueError('; '.join(errors))
    if not utils.is_valid_channel(channel):
        channel = 'lobby'

    message = ChatMessage.objects.create(
        channel=channel, player_id=player_id, body=utils.sanitize_message(body),
    )
    delivered = RealtimePublisherClient().publish(channel, message.body)
    if delivered:
        message.delivered = True
        message.save(update_fields=['delivered'])
    return message
