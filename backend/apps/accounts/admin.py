from django.contrib import admin

from .models import KYCSubmission, Player


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'kyc_status', 'is_suspended', 'kyc_updated_at', 'created_at')
    list_filter = ('kyc_status', 'is_suspended')
    search_fields = ('username', 'email')


@admin.register(KYCSubmission)
class KYCSubmissionAdmin(admin.ModelAdmin):
    list_display = ('player', 'document_type', 'status', 'submitted_at', 'reviewed_at', 'reviewed_by_username')
    list_filter = ('status', 'document_type')
    search_fields = ('player__username',)
    readonly_fields = ('player', 'document_type', 'file', 'submitted_at')
