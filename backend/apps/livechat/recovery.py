"""livechat fault-tolerance — re-publish undelivered messages.

Recovery strategy
-----------------
If the realtime publish fails (engine restart, transient network error) the
message persists with `delivered=False`. This manager re-publishes such messages
and flips the flag on success.

Idempotency
-----------
Re-running only targets `delivered=False`; once delivered, a message is skipped.
Re-publishing the same persisted message is harmless (the engine broadcasts a
de-duplicable, content-identical frame). The flag transition is one-way.
"""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from common.recovery import BaseRecoveryManager, RecoveryReport

from .clients import RealtimePublisherClient
from .models import ChatMessage

GRACE = timedelta(seconds=30)


class RecoveryManager(BaseRecoveryManager):
    domain = 'livechat'

    def reconcile(self) -> None:
        cutoff = timezone.now() - GRACE
        undelivered = ChatMessage.objects.filter(delivered=False, created_at__lt=cutoff)
        publisher = RealtimePublisherClient()
        for message in undelivered.iterator():
            self.mark_scanned()
            if self.dry_run:
                self.mark_skipped(f'would re-publish message {message.id}')
                continue
            try:
                if publisher.publish(message.channel, message.body):
                    ChatMessage.objects.filter(pk=message.id, delivered=False).update(delivered=True)
                    self.mark_repaired(f'message {message.id}: re-published')
                else:
                    self.mark_skipped(f'message {message.id}: still undeliverable')
            except Exception as exc:  # noqa: BLE001
                self.mark_failed(f'message {message.id}: {exc!r}')


def reconcile_undelivered_messages(*, dry_run: bool = False) -> RecoveryReport:
    """Module-level entry point (matches the domain's named recovery routine)."""
    return RecoveryManager(dry_run=dry_run).run()
