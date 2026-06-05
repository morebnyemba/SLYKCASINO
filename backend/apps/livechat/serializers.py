"""livechat transport (DRF)."""
from __future__ import annotations

from rest_framework import serializers

from .models import ChatMessage


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ['id', 'channel', 'body', 'created_at']
