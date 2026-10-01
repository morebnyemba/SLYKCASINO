from django.contrib import admin

from .models import Affiliate, AffiliateClick, Commission, Referral


@admin.register(Affiliate)
class AffiliateAdmin(admin.ModelAdmin):
    list_display = ('code', 'player_id', 'status', 'revshare_percent', 'cpa_amount', 'created_at')
    list_filter = ('status',)
    search_fields = ('code', 'website')


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ('player_id', 'affiliate', 'campaign', 'created_at')
    search_fields = ('affiliate__code', 'campaign')


@admin.register(Commission)
class CommissionAdmin(admin.ModelAdmin):
    list_display = ('affiliate', 'kind', 'period', 'amount', 'status', 'created_at')
    list_filter = ('kind', 'status')
    readonly_fields = ('amount', 'base_amount', 'rate', 'paid_at')


@admin.register(AffiliateClick)
class AffiliateClickAdmin(admin.ModelAdmin):
    list_display = ('affiliate', 'campaign', 'landing', 'created_at')
