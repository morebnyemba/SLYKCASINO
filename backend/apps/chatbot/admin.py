from django.contrib import admin

from .models import ChatbotSettings, ChatLink, ChatTicket, InboundMessage


@admin.register(ChatLink)
class ChatLinkAdmin(admin.ModelAdmin):
    list_display = ('channel', 'address', 'player_id', 'linked_at', 'last_seen_at')
    search_fields = ('address', 'player_id')
    exclude = ('pin_hash',)


@admin.register(InboundMessage)
class InboundMessageAdmin(admin.ModelAdmin):
    list_display = ('received_at', 'address', 'text', 'replies')
    search_fields = ('address', 'text')


@admin.register(ChatTicket)
class ChatTicketAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'player_id', 'kind', 'object_id', 'stake')


admin.site.register(ChatbotSettings)
