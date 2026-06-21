from django import forms
from django.contrib import admin

from .models import Bet, BetLeg, BetSlip, Event, ProviderCredential, Team


class ProviderCredentialForm(forms.ModelForm):
    class Meta:
        model = ProviderCredential
        fields = '__all__'
        widgets = {'api_key': forms.PasswordInput(render_value=True)}


@admin.register(ProviderCredential)
class ProviderCredentialAdmin(admin.ModelAdmin):
    form = ProviderCredentialForm
    list_display = ('provider', 'base_url')
    search_fields = ('provider',)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'provider', 'external_id', 'logo_url')
    search_fields = ('name', 'external_id')


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'sport', 'home_team', 'away_team', 'odds', 'odds_draw', 'odds_away',
        'featured', 'is_open', 'starts_at', 'provider', 'external_id',
    )
    list_filter = ('sport', 'featured', 'is_open', 'provider')
    search_fields = ('name', 'external_id')
    raw_id_fields = ('home_team', 'away_team')


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
