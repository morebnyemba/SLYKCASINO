from django.contrib import admin

from .models import Bet, BetLeg, BetSlip, Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'sport', 'odds', 'odds_draw', 'odds_away', 'featured', 'is_open',
        'starts_at', 'provider', 'external_id',
    )
    list_filter = ('sport', 'featured', 'is_open', 'provider')
    search_fields = ('name', 'external_id')


@admin.register(Bet)
class BetAdmin(admin.ModelAdmin):
    list_display = ('event', 'selection', 'player_id', 'stake', 'odds', 'status', 'payout', 'placed_at')
    list_filter = ('status', 'selection')
    search_fields = ('event', 'player_id')
    raw_id_fields = ('event_ref',)


class BetLegInline(admin.TabularInline):
    model = BetLeg
    extra = 0
    raw_id_fields = ('event_ref',)


@admin.register(BetSlip)
class BetSlipAdmin(admin.ModelAdmin):
    list_display = ('id', 'player_id', 'stake', 'combined_odds', 'status', 'payout', 'placed_at')
    list_filter = ('status',)
    search_fields = ('player_id',)
    inlines = [BetLegInline]
