from django.apps import AppConfig


class SportsbookConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.sportsbook'
    label = 'sportsbook'

    def ready(self):
        from . import signals  # noqa: F401  — register post_save odds publisher
