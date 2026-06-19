from django.contrib import admin

from .models import Promotion, PromotionClaim, Tournament, TournamentEntry


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ('name', 'kind', 'active', 'bonus_amount', 'wagering_multiplier', 'ends_at')
    list_filter = ('kind', 'active')
    search_fields = ('name',)


@admin.register(PromotionClaim)
class PromotionClaimAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'player_id', 'promotion', 'bonus_amount',
        'wagering_progress', 'wagering_required', 'status', 'bonus_credited',
    )
    list_filter = ('status', 'bonus_credited')
    search_fields = ('player_id',)


class TournamentEntryInline(admin.TabularInline):
    model = TournamentEntry
    extra = 0
    readonly_fields = ('player_id', 'player_name', 'score', 'updated_at')


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = ('name', 'metric', 'prize_pool', 'currency', 'active', 'starts_at', 'ends_at')
    list_filter = ('active', 'metric')
    search_fields = ('name',)
    inlines = [TournamentEntryInline]


@admin.register(TournamentEntry)
class TournamentEntryAdmin(admin.ModelAdmin):
    list_display = ('id', 'tournament', 'player_id', 'player_name', 'score', 'updated_at')
    search_fields = ('player_id', 'player_name')
