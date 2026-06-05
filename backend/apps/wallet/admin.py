from django.contrib import admin

from .models import LedgerEntry, Wallet


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('player_id', 'balance', 'currency', 'updated_at')
    search_fields = ('player_id',)


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ('idempotency_key', 'wallet', 'amount', 'kind', 'reference', 'created_at')
    list_filter = ('kind',)
    search_fields = ('idempotency_key', 'reference')
    # Ledger is append-only — never editable from the admin.
    readonly_fields = [f.name for f in LedgerEntry._meta.fields]

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
