from django.apps import AppConfig


class PlanejamentoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'planejamento'
    verbose_name = 'Planejamento'

    def ready(self):
        import planejamento.signals  # noqa: F401
