from django.contrib import admin

from .models import Bet, Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('name', 'sport', 'odds', 'odds_draw', 'odds_away', 'featured', 'is_open', 'starts_at')
    list_filter = ('sport', 'featured', 'is_open')
    search_fields = ('name',)


@admin.register(Bet)
class BetAdmin(admin.ModelAdmin):
    list_display = ('event', 'player_id', 'stake', 'odds', 'status', 'payout', 'placed_at')
    list_filter = ('status',)
    search_fields = ('event', 'player_id')
