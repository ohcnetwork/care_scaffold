---
name: care-plugin-architecture
description: Load FIRST for any CARE plugin work. Decides what belongs in the plugin vs. core care/care_fe, explains the two-sided plugin model (Django app + Module Federation micro-frontend), and gives the decision tree for extending core data models without modifying them. Use when starting a plugin, reviewing whether a core change is justified, or when unsure where code should live.
---

# CARE Plugin Architecture

## The prime directive

> A plugin owns a **complete vertical feature** — models, migrations, API, UI, i18n, background
> jobs — while adding **as close to zero lines as possible** to `care` and `care_fe`.

Every line in core is a merge conflict against upstream and a reviewer's objection. The measure of a
good CARE plugin is the size of its core diff, not the size of its feature.

## Two sides, two mechanisms

| | Backend | Frontend |
| --- | --- | --- |
| Repo | `care_<name>` | `care_<name>_fe` |
| Unit | Django app (pip package) | Vite app (Module Federation remote) |
| Registered in | `care/plug_config.py` → `Plug(...)` | `care_fe/.env.local` → `REACT_ENABLED_APPS`, or `GET /api/v1/plug_config/` |
| Loaded by | `PlugManager` → `INSTALLED_APPS` + `config/urls.py` loop | `src/PluginEngine.tsx` → `setFederationRemote()` → `./manifest` |
| Namespace | `/api/care_<name>/…` | `manifest.components` / `manifest.routes` |
| Isolation | Own models, own migrations dir | Own bundle, own i18n namespace, own Tailwind scope |

Both sides are **optional and independent**. A UI-only plugin needs no Django app; a
webhook-only integration needs no frontend.

## Where does this code go? — decision tree

```
Need to store new data?
├─ Is it a new domain concept (a call session, a lab order, a transcript)?
│  └─ YES → new model in the plugin. Reference core models by FK; core never references you.
└─ Is it an attribute of an existing core record (a flag on an availability, a tag)?
   └─ YES → write into the core model's `meta` JSONField. NO core migration. NO new column.

Need to react to something happening in core?
├─ Django `post_save` / `pre_delete` signal on the core model, registered in your AppConfig.ready()
└─ NEVER add a call to your plugin from inside a core viewset.

Need to show UI somewhere in care_fe?
├─ Does a `SupportedPluginComponents` extension point already exist there?
│  ├─ YES → implement it in your manifest. Zero core changes.  ← 90% of cases
│  └─ NO  → is there a `PluginOverride` that can replace a registered component? Use that.
│           Otherwise add ONE generic extension point to core (see care-extension-points).
└─ Need a whole page? → `manifest.routes` — zero core changes, ever.

Need a new setting / credential?
└─ `PluginSettings` in your plugin's settings.py, defaults + env fallback, values supplied
   through `Plug(configs={...})`. NEVER add to core's settings/base.py.

Need a background job?
└─ Celery task inside your plugin; register beat schedules from your own settings.

Need to talk to a third-party service (video, LLM, SMS, payments)?
└─ The plugin backend brokers it. It holds the API secret, authorises the CARE user, and
   mints a short-lived scoped token for the browser. The credential NEVER reaches the client.
   Inbound webhooks are signature-verified, not CARE-JWT authenticated.
   → care-third-party-services
```

## The `meta` JSONField pattern

Core models (`Availability`, `Device`, `Facility`, …) carry a `meta` JSONField precisely so plugins
can annotate them. This is the single highest-leverage technique for keeping the core diff at zero.

```python
# Read
enabled = availability.meta.get("teleconsultation", {}).get("enabled", False)

# Write (serializer field MUST be write_only — see care-backend-plugin for why)
availability.meta.setdefault("teleconsultation", {})["enabled"] = True
availability.save(update_fields=["meta"])
```

Namespace your keys under a single top-level dict named after your plugin, so two plugins never
collide.

## The signal pattern

Auto-create your plugin's records when a core record appears, without core knowing you exist:

```python
# care_<name>/signals.py
@receiver(post_save, sender=TokenBooking)
def on_booking_created(sender, instance, created, **kwargs):
    if not created:
        return
    if not availability_is_enabled(instance):
        return
    TeleSession.objects.create(booking=instance, ...)
```

Registered from `AppConfig.ready()`. Core ships unchanged.

## What a *justified* core change looks like

Acceptable:

- Adding a new key to `SupportedPluginComponents` in `care_fe/src/pluginTypes.ts` plus a single
  `<PLUGIN_Component __name="…" />` render site — **generic**, named after the *location*
  (`AppointmentActions`, `AppShellOverlay`), never after your plugin.
- Adding a missing field to a core TypeScript type that the core API already returns
  (e.g. `TokenSlot.availability.id`) — a bug fix, not a feature.
- Adding `meta` to a core model that lacks it.

Unacceptable:

- `if settings.CONNECT_ENABLED:` anywhere in core.
- Importing your plugin from core.
- A new column on a core model for your feature.
- Plugin-specific strings in `care_fe/public/locale/en.json`.

## Directory shape to aim for

```
care_<name>/                      # backend repo
├── setup.py                      # name=care_<name>, install_requires
├── MANIFEST.in
└── care_<name>/
    ├── apps.py                   # PLUGIN_NAME + AppConfig.ready() → signals
    ├── settings.py               # PluginSettings, DEFAULTS, REQUIRED_SETTINGS
    ├── urls.py                   # DefaultRouter; mounted at /api/care_<name>/
    ├── signals.py
    ├── models/  serializers/  viewsets/  tasks/  utils/  integrations/  tests/
    └── migrations/

care_<name>_fe/                   # frontend repo
├── vite.config.ts                # federation({ name, exposes: {"./manifest"} })
├── public/locale/en.json         # keys prefixed <name>__
└── src/
    ├── manifest.tsx              # THE entrypoint — only thing federation exposes
    ├── types.ts
    ├── utils/api.ts              # window.CARE_API_URL + localStorage token
    ├── components/               # one file per extension point + shared UI
    ├── pages/                    # for manifest.routes
    └── hooks/
```

## Order of work

1. Model + migrations.
2. Serializers + viewsets + urls.
3. **Verify with curl.** Do not write React against an unverified API.
4. Frontend types + API client.
5. Components → manifest.
6. i18n keys.
7. Celery/webhooks.

## Related skills

- `care-backend-plugin` — Django app mechanics.
- `care-frontend-plugin` — federation, manifest, styling, i18n.
- `care-design-system` — Tailwind theme, CARE palette, shadcn/ui, making UI look native.
- `care-extension-points` — the catalog, and how to add one.
- `care-auth-contexts` — staff JWT vs. patient OTP.
- `care-third-party-services` — brokering an external service, token minting, webhooks.
- `care-plugin-interop` — cross-plugin integration.
- `care-plugin-verification` — running and debugging.
