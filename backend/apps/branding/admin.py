from django.contrib import admin

from .models import SiteIdentity, SiteTheme


class _SingletonAdmin(admin.ModelAdmin):
    readonly_fields = ['updated_at', 'updated_by_username']
    list_display = ['__str__', 'updated_at', 'updated_by_username']

    def has_add_permission(self, request):
        return not self.model.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SiteTheme)
class SiteThemeAdmin(_SingletonAdmin):
    pass


@admin.register(SiteIdentity)
class SiteIdentityAdmin(_SingletonAdmin):
    pass
