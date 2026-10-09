from django.apps import AppConfig


class JetConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.jet'
    label = 'jet'
    verbose_name = 'Jet (crash game)'
