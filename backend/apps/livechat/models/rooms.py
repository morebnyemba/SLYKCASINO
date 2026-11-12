"""Group chat: rooms open to an audience (everyone, agents, staff), their
messages, and moderation (hidden messages, mutes, reports). No logic here."""
from django.db import models
from django.db.models import Q


class ChatRoom(models.Model):
    class Audience(models.TextChoices):
        EVERYONE = 'everyone', 'All players'
        AGENTS = 'agents', 'Agents (affiliates)'
        STAFF = 'staff', 'Staff only'

    slug = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=60)
    description = models.CharField(max_length=200, blank=True)
    # Who can read the room. Staff can read and post in every room.
    audience = models.CharField(max_length=10, choices=Audience.choices, default=Audience.EVERYONE)
    # Only staff post (announcements); everyone in the audience reads.
    staff_only_posting = models.BooleanField(default=False)
    # A closed room is hidden from players (staff still see it).
    is_open = models.BooleanField(default=True)
    # Seconds a member must wait between their own messages.
    slow_mode_seconds = models.PositiveSmallIntegerField(default=3)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'livechat_room'
        ordering = ['sort_order', 'id']

    def __str__(self) -> str:
        return self.name


class RoomMessage(models.Model):
    """One message. Hidden = staff took it out of view (reversible; only staff
    still see it). Deleting removes the row for good."""
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
    # The sender: a player (player_id) or a staff login (from_staff, staff_name).
    player_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    from_staff = models.BooleanField(default=False)
    sender_name = models.CharField(max_length=150)
    sender_role = models.CharField(max_length=10, default='player')  # player | agent | staff
    body = models.TextField()
    reply_to = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='replies')
    pinned = models.BooleanField(default=False)
    hidden_at = models.DateTimeField(null=True, blank=True)
    hidden_by = models.CharField(max_length=150, blank=True)
    hidden_reason = models.CharField(max_length=200, blank=True)
    reports = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'livechat_room_message'
        ordering = ['id']
        indexes = [models.Index(fields=['room', 'id'])]


class ChatMute(models.Model):
    """A player who may read the rooms but not post, until `until` (None = until lifted)."""
    player_id = models.BigIntegerField(unique=True)
    until = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=200, blank=True)
    muted_by = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'livechat_mute'


class MessageReport(models.Model):
    """A player flagged a message for staff. Once per player per message."""
    message = models.ForeignKey(RoomMessage, on_delete=models.CASCADE, related_name='report_rows')
    player_id = models.BigIntegerField()
    reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'livechat_message_report'
        constraints = [models.UniqueConstraint(fields=['message', 'player_id'], name='one_report_per_player_per_message')]


class RoomRead(models.Model):
    """How far a player has read a room (for unread counts)."""
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='reads')
    player_id = models.BigIntegerField()
    last_id = models.BigIntegerField(default=0)

    class Meta:
        db_table = 'livechat_room_read'
        constraints = [models.UniqueConstraint(fields=['room', 'player_id'], name='one_read_marker_per_player_per_room')]
