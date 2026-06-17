"""notifications domain logic."""
from __future__ import annotations

from .models import Notification


def notify(player_id: int, kind: str, title: str, body: str = '') -> Notification:
    """Create a notification for the given player."""
    return Notification.objects.create(
        player_id=player_id,
        kind=kind,
        title=title,
        body=body,
    )


def mark_read(player_id: int, notification_id: int) -> bool:
    """Mark a single notification as read. Returns True if found and updated."""
    updated = Notification.objects.filter(pk=notification_id, player_id=player_id).update(read=True)
    return bool(updated)


def mark_all_read(player_id: int) -> int:
    """Bulk-mark all unread notifications for a player as read. Returns count updated."""
    return Notification.objects.filter(player_id=player_id, read=False).update(read=True)
