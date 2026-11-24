from django.db import models


class ChatMessage(models.Model):
    """A chat message. `player_id` references accounts.Player by ID. `delivered`
    records whether it was published to the realtime engine — the hook recovery
    uses to re-publish undelivered messages idempotently."""

    channel = models.CharField(max_length=120, default='lobby', db_index=True)
    player_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    body = models.TextField()
    delivered = models.BooleanField(default=False)
    # Private support conversations (channel "support:<player id>"): replies
    # from staff, who wrote them, and when the other side read the message.
    from_staff = models.BooleanField(default=False)
    staff_name = models.CharField(max_length=150, blank=True)
    # A photo or video staff sent (support.staff_reply); served only to staff and this player.
    attachment = models.FileField(upload_to='support/%Y/%m/', blank=True, default='')
    attachment_kind = models.CharField(max_length=8, blank=True, default='')
    attachment_mime = models.CharField(max_length=20, blank=True, default='')
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'livechat_message'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['channel', 'created_at'])]

    def __str__(self) -> str:
        return f'[{self.channel}] {self.body[:40]}'
