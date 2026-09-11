---
name: care-backend-plugin
description: How to build the Django side of a CARE plugin — package layout, AppConfig, PluginSettings, plug_config.py registration, URL mounting under /api/care_<name>/, migrations, signals, celery tasks, and the editable-install gotchas that silently break celery. Use when creating or modifying a care_<name> backend plugin.
---

# CARE Backend Plugin (Django)

A backend plugin is an ordinary pip-installable Django app. Core discovers it through
`plug_config.py`; nothing else in core knows it exists.

## How core loads plugins

```python
# care/plug_config.py  — the ONLY core file you edit
from plugs.manager import PlugManager
from plugs.plug import Plug

care_connect = Plug(
    name="care_connect",          # Django app label → INSTALLED_APPS entry
    package_name="care_connect",  # pip target: local dir, or git+https://github.com/org/care_connect.git
    version="",                   # "" + local dir ⇒ pip install -e ./care_connect ; else "@main"
    configs={                     # → settings.PLUGIN_CONFIGS["care_connect"]
        "CONNECT_LIVEKIT_URL": "ws://localhost:7880",
    },
)

plugs = [care_connect, ...]
manager = PlugManager(plugs)
```

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

Plugins can also be injected at deploy time without editing `plug_config.py` at all, via the
`ADDITIONAL_PLUGS` env var (a JSON array of `Plug` kwargs). Prefer this for production.

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

The plugin must live as a **real directory inside the backend checkout**:

```bash
mv /path/to/care_connect "$CARE_BE/care_connect"    # or clone directly into $CARE_BE
```

> ⚠️ **Not a symlink.** `docker/dev.Dockerfile` does `COPY . /app`; Docker's build context cannot
> follow a symlink pointing outside it, so the plugin arrives empty in the image and
> `install_plugins.py` installs nothing. This works fine under a bind-mounted venv setup and then
> breaks the moment someone builds the image — a confusing, delayed failure.

### Docker: rebuild the image

The Dockerfile installs plugins **at build time**:

```dockerfile
COPY . $APP_HOME/
RUN python3 $APP_HOME/install_plugins.py
```

The virtualenv lives at `/.venv` **inside the image**. Compose bind-mounts only the source tree
(`.:/app`), not the venv. Therefore a newly registered plug does not exist in a running container
until the image is rebuilt:

```bash
cd "$CARE_BE"
make down      # safe stop
make build     # re-runs install_plugins.py
make up
```

`backend` and `celery` share one `care_local` image, so a single rebuild covers both.

> ⚠️ **Never `make teardown`.** That is `docker compose down -v` — it deletes the volumes and with
> them the entire database. `make down` is the safe stop.

`ADDITIONAL_PLUGS` is a Docker **build arg**, so changing it also requires a rebuild.

### Fast iteration (temporary)

While actively editing plugin code, skip the rebuild:

```bash
docker exec care_be-backend-1 python install_plugins.py
docker exec care_be-celery-1  python install_plugins.py
docker compose restart backend celery
```

`docker exec` writes to a **single container's writable layer**, not the shared image — which is
why you must run it against both containers, and why the change vanishes when a container is
recreated. Treat it as a patch; rebuild before you trust a result.

### Diagnosing a stale install

Symptom: your backend change works, but the same code behaves like an older version in celery
tasks — with **no import error**. It silently runs stale code.

```bash
docker exec <container> python -c "import care_connect; print(care_connect.__file__)"
docker exec <container> pip show care_connect     # want 0.1.0-0.editable, not a frozen version
```

### venv

```bash
.venv/bin/python install_plugins.py
```

## Checklist before you call the backend done

- [ ] `curl` proves every endpoint works, with a real token, as each relevant role.
- [ ] `makemigrations --check --dry-run` is clean.
- [ ] No import of your plugin anywhere in `care/`.
- [ ] Core diff is `plug_config.py` only.
- [ ] Secrets come from `configs`/env, and no real key is committed.
- [ ] Plugin is a real directory inside `$CARE_BE`, not a symlink.
- [ ] Image rebuilt (`make down && make build && make up`) after registering the plug.
