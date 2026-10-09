from django.contrib import admin

from .models import JetBet, JetRound, JetSettings


@admin.register(JetRound)
class JetRoundAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'bet_count', 'total_stake', 'total_payout', 'crashed_at')
    list_filter = ('status',)
    # Read-only: rounds are only ever created and settled by the runner.
    readonly_fields = [f.name for f in JetRound._meta.fields]
    exclude = ('server_seed', 'crash_point')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(JetBet)
class JetBetAdmin(admin.ModelAdmin):
    list_display = ('id', 'round', 'display_name', 'stake', 'status', 'cashout_multiplier', 'payout')
    list_filter = ('status',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


admin.site.register(JetSettings)
