from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'
    label = 'accounts'

    def ready(self):
        # Import KYC registry so all providers are registered at startup.
        import apps.accounts.kyc  # noqa: F401
