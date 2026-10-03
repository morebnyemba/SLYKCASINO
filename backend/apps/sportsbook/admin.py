from django import forms
from django.contrib import admin

from .models import (
    Bet, BetLeg, BetSlip, BookingCode, Event, LeagueSetting, Market, MarketOutcome, MultiBetBonusTier,
    ProviderCredential, Team,
)


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


@admin.register(LeagueSetting)
class LeagueSettingAdmin(admin.ModelAdmin):
    # Leagues are auto-populated here as import_all_current_leagues discovers
    # them; toggle `enabled` off (list_editable, no need to open the row) for
    # any league you don't want synced — saves the API call too, not just
    # hides it from the sportsbook.
    # `sort_order` sets where the league appears in the sportsbook (lower = higher).
    list_display = ('name', 'country', 'league_id', 'provider', 'enabled', 'sort_order')
    list_editable = ('enabled', 'sort_order')
    list_filter = ('provider', 'enabled', 'country')
    search_fields = ('name', 'country', 'league_id')


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


class MarketOutcomeInline(admin.TabularInline):
    model = MarketOutcome
    extra = 0
    fields = ('key', 'label', 'odds', 'previous_odds', 'is_open', 'result', 'sort_order')


@admin.register(Market)
class MarketAdmin(admin.ModelAdmin):
    # Markets are imported from the odds feed; operators suspend (is_open) or
    # fix prices here. Settle through the API (settle-score / markets/<id>/settle)
    # so bets are paid out — editing `result` here does not move money.
    list_display = ('name', 'event', 'group', 'kind', 'metric', 'period', 'line', 'is_open', 'settled', 'needs_review')
    list_filter = ('needs_review', 'settled', 'group', 'kind', 'metric', 'is_open')
    search_fields = ('name', 'event__name', 'key')
    raw_id_fields = ('event',)
    inlines = [MarketOutcomeInline]


@admin.register(Bet)
class BetAdmin(admin.ModelAdmin):
    list_display = ('event', 'selection', 'player_id', 'stake', 'odds', 'status', 'payout', 'placed_at')
    list_filter = ('status', 'selection')
    search_fields = ('event', 'player_id')
    raw_id_fields = ('event_ref', 'outcome_ref')


class BetLegInline(admin.TabularInline):
    model = BetLeg
    extra = 0
    raw_id_fields = ('event_ref', 'outcome_ref')


@admin.register(BetSlip)
class BetSlipAdmin(admin.ModelAdmin):
    list_display = ('id', 'player_id', 'stake', 'combined_odds', 'status', 'payout', 'placed_at')
    list_filter = ('status',)
    search_fields = ('player_id',)
    inlines = [BetLegInline]


@admin.register(MultiBetBonusTier)
class MultiBetBonusTierAdmin(admin.ModelAdmin):
    # Legs priced under SPORTSBOOK_ACCA_BONUS_MIN_ODDS don't count towards a tier.
    list_display = ('min_legs', 'percent', 'is_active')
    list_editable = ('percent', 'is_active')


@admin.register(BookingCode)
class BookingCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'player_id', 'loads', 'created_at')
    search_fields = ('code',)
    readonly_fields = ('code', 'selections', 'player_id', 'loads', 'created_at')
