from django.apps import AppConfig


class ChatbotConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.chatbot'
    verbose_name = 'Chat betting (WhatsApp)'

    def ready(self):
        # Aviator from WhatsApp: the jet runner calls these at each stage of a round.
        from apps.jet import services as jet
        from . import aviator
        jet.register_hook('open', aviator.on_open)
        jet.register_hook('flight', aviator.on_flight)
        jet.register_hook('crash', aviator.on_crash)
