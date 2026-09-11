from django.apps import AppConfig

PLUGIN_NAME = "__PLUGIN_SNAKE__"


class __PLUGIN_CLASS__Config(AppConfig):
    name = PLUGIN_NAME
    verbose_name = "__PLUGIN_TITLE__"

    def ready(self):
        from __PLUGIN_SNAKE__ import signals  # noqa: F401
