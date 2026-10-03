from django.contrib import admin

from .models import LedgerEntry, PaymentTransaction, Wallet


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


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    # Gateway deposits; the wallet credit is in the ledger (reference psp:paynow:<reference>).
    list_display = ('reference', 'player_id', 'method', 'amount', 'currency', 'status', 'provider_status', 'created_at')
    list_filter = ('status', 'method', 'provider')
    search_fields = ('reference', 'provider_ref', 'phone', 'player_id')
    readonly_fields = [f.name for f in PaymentTransaction._meta.fields]

    def has_add_permission(self, request):
        return False
