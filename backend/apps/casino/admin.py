from django.contrib import admin

from .models import Game, GameRound


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'provider', 'rtp', 'is_active')
    list_filter = ('provider', 'is_active')
    search_fields = ('name', 'slug')


@admin.register(GameRound)
class GameRoundAdmin(admin.ModelAdmin):
    list_display = ('id', 'game', 'player_id', 'stake', 'win', 'status', 'debit_confirmed', 'created_at')
    list_filter = ('status', 'debit_confirmed')
    search_fields = ('player_id', 'provider_round_ref')
