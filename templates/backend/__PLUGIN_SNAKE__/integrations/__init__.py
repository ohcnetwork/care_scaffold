"""Integrations with *optional* companion plugins.

Never import another plugin at module top level — it crashes the app when that plugin is
not installed. Guard with apps.is_installed() and import inside the function.
See the care-plugin-interop skill.

    from django.apps import apps

    def is_enabled() -> bool:
        return bool(plugin_settings.__PLUGIN_PREFIX___NOTIFY_ENABLED) and apps.is_installed(
            "care_notifications"
        )
"""
