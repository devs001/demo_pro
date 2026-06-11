from django.apps import AppConfig


class MyappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'myapp'

    def ready(self):
        # Skip during migrations / management commands that don't need live broker API
        import sys
        if any(cmd in sys.argv for cmd in ('migrate', 'makemigrations', 'test', 'shell')):
            return
        try:
            from .broker import startup_check
            startup_check()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Broker startup check skipped or failed: %s", exc
            )
