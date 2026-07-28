from django.apps import AppConfig


class AnalysisapiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'AnalysisAPI'

    def ready(self):
        import AnalysisAPI.signals
