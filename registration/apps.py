from django.apps import AppConfig


class App1Config(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'registration'

    def ready(self):
        import registration.signals  # noqa
