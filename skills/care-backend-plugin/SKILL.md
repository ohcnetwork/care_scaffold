---
name: care-backend-plugin
description: How to build the Django side of a CARE plugin — package layout, AppConfig, PluginSettings, external ADDITIONAL_PLUGS registration, URL mounting under /api/care_<name>/, migrations, signals, celery tasks, and the editable-install gotchas that silently break celery. Use when creating or modifying a care_<name> backend plugin.
---

# CARE Backend Plugin (Django)

A backend plugin is an ordinary pip-installable Django app in its own Git repository. Core is
a read-only checkout. Register the plugin through the existing `ADDITIONAL_PLUGS` environment
variable, supplied to both backend and Celery by `.agent/plugin.compose.yaml`.

## How core loads plugins

`PlugManager` combines the core's existing plugins with this external JSON array:

```json
[{
  "name": "care_connect",
  "package_name": "/plugins/care_connect",
  "version": "",
  "configs": {"CONNECT_LIVEKIT_URL": "ws://localhost:7880"}
}]
```

The `name` is the Django app label; `package_name` is a pip target. An empty version is required
for a local path. Editable installation is a separate `python -m pip install -e` step; the core
installer does not add `-e`. Do not edit `care/plug_config.py`.

Core then does, in `config/settings/base.py`:

```python
PLUGIN_APPS    = manager.get_apps()
PLUGIN_CONFIGS = manager.get_config()
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS + PLUGIN_APPS
```

and in `config/urls.py`:

```python
for plug in settings.PLUGIN_APPS:
    urlpatterns += [path(f"api/{plug}/", include(f"{plug}.urls"))]
```

**Consequence:** your `urls.py` is automatically mounted at `/api/care_<name>/`. Never hardcode
that prefix in your route definitions.

For deployments, supply a published package or Git URL through the same external registration
mechanism; never encode a developer's local filesystem path in deployment configuration.

## Package layout

```
care_connect/                      # repo root
├── setup.py
├── MANIFEST.in
├── README.md
└── care_connect/                  # the importable package
    ├── __init__.py
    ├── apps.py
    ├── settings.py
    ├── urls.py
    ├── signals.py
    ├── models/__init__.py
    ├── serializers/__init__.py
    ├── viewsets/__init__.py
    ├── tasks/__init__.py
    ├── utils/__init__.py
    ├── integrations/__init__.py
    ├── migrations/__init__.py
    └── tests/__init__.py
```

`setup.py` must use `packages=find_packages(include=["care_connect", "care_connect.*"])` and
`include_package_data=True`, with `python_requires=">=3.13"`.

## apps.py

```python
from django.apps import AppConfig

PLUGIN_NAME = "care_connect"

class CareConnectConfig(AppConfig):
    name = PLUGIN_NAME
    verbose_name = "Care Connect"

    def ready(self):
        from care_connect import signals  # noqa: F401
```

`ready()` is the only safe place to register signal receivers.

## settings.py — the PluginSettings pattern

Copy this verbatim (it is the shared CARE plugin idiom) and change only `DEFAULTS`,
`REQUIRED_SETTINGS`, and the `validate()` body.

Resolution order for each key: `settings.PLUGIN_CONFIGS[plugin][key]` → environment variable →
`DEFAULTS[key]`. The env cast is inferred from the type of the default, so **give every default a
correctly-typed value** (`0` not `None`, `False` not `None`, `""` for strings).

```python
from care_connect.settings import plugin_settings
plugin_settings.CONNECT_LIVEKIT_URL
```

Put required credentials in `REQUIRED_SETTINGS` so a misconfigured deploy fails loudly at boot,
and validate ranges in `validate()`.

Never add your keys to core's `config/settings/base.py`.

## urls.py

```python
from rest_framework.routers import DefaultRouter
from django.urls import path

router = DefaultRouter()
router.register("sessions", TeleSessionViewSet, basename="tele-session")
router.register("otp/sessions", OTPTeleSessionViewSet, basename="otp-tele-session")

urlpatterns = [
    *router.urls,
    path("config/", ConfigView.as_view(), name="care-connect-config"),
    path("webhook/", WebhookView.as_view(), name="care-connect-webhook"),
]
```

Expose a `config/` endpoint returning the client-safe subset of your settings (feature flags,
public URLs). The frontend reads it instead of hardcoding anything.

## Models

- Inherit CARE's `EMRBaseModel` (or `BaseModel`) so you get `external_id`, `created_date`,
  `modified_date`, `deleted` for free. `external_id` is the UUID the API exposes; never leak `id`.
- FK **into** core models is fine (`models.ForeignKey("emr.TokenBooking", ...)`).
  FK **from** core into your model is forbidden.
- Use `on_delete=models.CASCADE` toward core so deleting a booking cleans up your rows.
- Your migrations live in your package. `makemigrations care_connect` — never touch core migrations.
- **Soft delete does not cascade.** CARE's `deleted=True` is a plain flag, so marking a parent
  deleted leaves children visible. Filter `deleted=False` in every queryset, and mark related rows
  yourself when soft-deleting a parent.

### Error responses

Raise DRF exceptions and let them serialise — the frontend's `readErrorMessage` helper reads
`detail` and `non_field_errors`:

| Situation | Raise |
| --- | --- |
| Caller lacks permission | `PermissionDenied("…")` → 403 `{"detail": "…"}` |
| Invalid input / bad state | `ValidationError("…")` → 400 |
| Not found / not visible to caller | let `get_object()` 404 — do not confirm existence |

Do not invent a custom error envelope.

## Serializers — the `meta` write_only trap

If you expose a flag that lives inside a core model's `meta` JSONField and **not** on the model,
the field **must** be `write_only=True`:

```python
class TeleAvailabilitySerializer(serializers.ModelSerializer):
    # lives in Availability.meta, not on the model
    teleconsultation_enabled = serializers.BooleanField(write_only=True)
```

Otherwise DRF's `to_representation` loop calls `getattr(instance, "teleconsultation_enabled")`,
raises `AttributeError` → **500**. And because the 500 response carries no CORS headers, the
browser reports it as a *CORS error*, sending you on a multi-hour wild goose chase.
Provide the read side with an explicit `SerializerMethodField`.

## Viewsets and querysets

Scope every queryset. The default must be "the caller sees only what they are entitled to."

```python
def get_queryset(self):
    qs = TeleSession.objects.filter(deleted=False)
    facility = self.request.query_params.get("facility")
    if facility:
        # authorize the caller against the facility, then scope
        return qs.filter(booking__token_slot__resource__facility__external_id=facility)
    # fall back to "sessions I participate in"
    return qs.filter(participants__user=self.request.user)
```

Beware the usability trap this creates: a front-desk user who is not a participant sees nothing
unless the client passes `facility=<id>`. Document required query params in the frontend client.

See `care-auth-contexts` for the OTP-scoped viewset variants.

## Signals

```python
# signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=TokenBooking)
def create_session_for_booking(sender, instance, created, **kwargs):
    if not created or not is_enabled(instance):
        return
    TeleSession.objects.create(booking=instance)
```

This is how you hook core behaviour with zero core edits.

## Celery tasks and beat

Define tasks inside your plugin. Register periodic schedules from your own module — do not edit
core's beat config:

```python
from celery import current_app
from celery.schedules import crontab

@current_app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(60.0, sweep_reminders.s(), name="care_connect: sweep reminders")
```

Put this in a module that is guaranteed to be imported — `care_<name>/tasks/__init__.py`, imported
from `AppConfig.ready()` alongside `signals`. A schedule defined in a module nobody imports never
registers, and fails silently.

## Installing during development

Follow bootstrap Phase 6.1. Keep the plugin in its independent repository at
`$WORKSPACE/care/care_connect`, locally excluded from core Git tracking and mounted at
`/plugins/care_connect` in both containers. The external `.agent/plugin.compose.yaml` supplies:

- An empty `build.args.ADDITIONAL_PLUGS`, because unpublished host paths are unavailable at image build time.
- Runtime `ADDITIONAL_PLUGS` JSON for registration in both backend and Celery.
- Entrypoints that run `python -m pip install -e /plugins/care_connect`, then execute the
  unmodified `scripts/start-dev.sh` or `scripts/celery-dev.sh` respectively.

```bash
source "$WORKSPACE/care-scaffold.env"
"$WORKSPACE/.agent/compose.sh" up -d --wait --build
```

The wrapper loads saved plugin paths and the external override. Each container installs the
plugin into its own virtualenv layer on every start, so recreation does not lose registration or
the editable install. The unmodified core Dockerfile still installs its built-in plugins during
the image build. Do not copy plugin source into core or mount over core configuration files.

Celery's watcher watches `/app`, not the external plugin mount. After plugin source changes:

```bash
"$WORKSPACE/.agent/compose.sh" restart celery
```

Restart backend as well if autoreload did not pick up a change. A metadata/dependency change
requires restarting both containers to rerun their editable installs.

### Diagnosing a stale install

```bash
"$WORKSPACE/.agent/compose.sh" exec backend python -c "import care_connect; print(care_connect.__file__)"
"$WORKSPACE/.agent/compose.sh" exec celery pip show care_connect
```

The import and editable project location must point to `/plugins/care_connect` in both containers.
Verify `compose.sh config` includes the mount, environment and installing entrypoint for both.
Do not use `install_plugins.py` as an editable-install shortcut: it performs a regular install.
Use `compose.sh down` to stop only this stack; never add `-v` without approval.

## Checklist before you call the backend done

- [ ] `curl` proves every endpoint works, with a real token, as each relevant role.
- [ ] `makemigrations --check --dry-run` is clean.
- [ ] No import of your plugin anywhere in `care/`.
- [ ] Both core checkouts have no tracked changes; all registration is external.
- [ ] Secrets come from `configs`/env, and no real key is committed.
- [ ] Plugin has its own Git root under `care/`, is locally excluded from core, and is mounted at
  `/plugins/<plugin>` in both services.
- [ ] Both services recreated through `.agent/compose.sh up -d --wait` after external registration changes.
