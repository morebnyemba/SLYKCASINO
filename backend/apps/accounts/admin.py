from django.contrib import admin

from .models import Player


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'kyc_status', 'kyc_updated_at', 'created_at')
    list_filter = ('kyc_status',)
    search_fields = ('username', 'email')
