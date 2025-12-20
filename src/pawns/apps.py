from django.apps import AppConfig

class PawnsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pawns"

    def ready(self):
        from . import signals  # noqa: F401
