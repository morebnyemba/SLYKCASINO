from django.contrib import admin

from .models import CrashRound, Game, GameRound


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'provider', 'category', 'rtp', 'is_active')
    list_filter = ('provider', 'category', 'is_active')
    search_fields = ('name', 'slug')


@admin.register(GameRound)
class GameRoundAdmin(admin.ModelAdmin):
    list_display = ('id', 'game', 'player_id', 'stake', 'win', 'status', 'debit_confirmed', 'created_at')
    list_filter = ('status', 'debit_confirmed')
    search_fields = ('player_id', 'provider_round_ref')


@admin.register(CrashRound)
class CrashRoundAdmin(admin.ModelAdmin):
    list_display = ('id', 'player_id', 'stake', 'crash_point', 'cashout_multiplier', 'win', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('player_id',)
