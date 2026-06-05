from django.db import models


class ChatMessage(models.Model):
    """A chat message. `player_id` references accounts.Player by ID. `delivered`
    records whether it was published to the realtime engine — the hook recovery
    uses to re-publish undelivered messages idempotently."""

    channel = models.CharField(max_length=120, default='lobby', db_index=True)
    player_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    body = models.TextField()
    delivered = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'livechat_message'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['channel', 'created_at'])]

    def __str__(self) -> str:
        return f'[{self.channel}] {self.body[:40]}'
