"""livechat transport (DRF)."""
from __future__ import annotations

from rest_framework import serializers

from apps.accounts.models import Player

from .models import ChatMessage


class ChatMessageSerializer(serializers.ModelSerializer):
    sender = serializers.SerializerMethodField()

    class Meta:
        model = ChatMessage
        fields = ['id', 'channel', 'body', 'sender', 'player_id', 'created_at']

    def get_sender(self, obj: ChatMessage) -> str:
        if obj.player_id:
            player = Player.objects.filter(pk=obj.player_id).only('username').first()
            if player:
                return player.username
        return 'Guest'
