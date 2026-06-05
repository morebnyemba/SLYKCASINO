from django.contrib import admin

from .models import Promotion, PromotionClaim


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
