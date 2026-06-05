from django.contrib import admin

from .models import ChatMessage


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('channel', 'player_id', 'body', 'delivered', 'created_at')
    list_filter = ('channel', 'delivered')
    search_fields = ('body',)
