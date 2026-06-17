from django.apps import AppConfig


class WalletConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.wallet'
    label = 'wallet'

    def ready(self):
        # Import PSP registry so all providers are registered at startup.
        import apps.wallet.psp  # noqa: F401
