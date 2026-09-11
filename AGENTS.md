# AGENTS.md

You are looking at **care_scaffold**, a knowledge + template repo for building plugins for
[CARE](https://github.com/ohcnetwork/care) (Django backend) and
[care_fe](https://github.com/ohcnetwork/care_fe) (React frontend).

This repo contains **no application code**. Do not treat it as the project you are building.
Its job is to teach you how to build a *separate* plugin repo pair.

## If the user asks you to set up an environment or start a new plugin

Execute [`bootstrap.prompt.md`](bootstrap.prompt.md). It is self-contained and idempotent.

## If the user is already mid-build

Load the relevant skill(s) from `skills/` on demand:

| Skill | Load it when… |
| --- | --- |
| `care-plugin-architecture` | **Always load first.** Decides what goes in the plugin vs. core. |
| `care-backend-plugin` | Creating/altering the Django app, models, viewsets, settings, celery tasks. |
| `care-frontend-plugin` | Creating/altering the federated Vite app, manifest, API client, i18n, styling. |
| `care-design-system` | Writing ANY UI. Tailwind theme, CARE palette, shadcn/ui, icons, scoping, portals. |
| `care-extension-points` | Deciding *where* plugin UI attaches, or adding a new extension point to core. |
| `care-auth-contexts` | Anything touching staff JWT vs. patient OTP auth, or permissions. |
| `care-third-party-services` | Integrating an external service (LiveKit, LLM, SMS, payments) or webhooks. |
| `care-plugin-interop` | Talking to another plugin (notifications, scribe, devices). |
| `care-plugin-verification` | Running, debugging or testing the plugin end to end. |

## The one rule that matters

**Minimal overlap with core.** Every line you add to `care` or `care_fe` is a merge conflict and a
review blocker. Before editing core, prove that no existing extension point, `meta` JSON field, or
Django signal can do the job. If you must edit core, the change must be *generic* — usable by any
plugin, naming no plugin.

## Conventions in `templates/`

Template files use literal placeholder tokens, substituted by `scripts/new-plugin.sh`:

| Token | Example | Meaning |
| --- | --- | --- |
| `__PLUGIN_SNAKE__` | `care_connect` | Backend Django app + pip package name |
| `__PLUGIN_FE__` | `care_connect_fe` | Frontend repo / federation slug |
| `__PLUGIN_FED_NAME__` | `care_connect` | Federation `name` in vite config |
| `__PLUGIN_TITLE__` | `Care Connect` | Human-readable title |
| `__PLUGIN_PREFIX__` | `CONNECT` | Settings-key prefix (`CONNECT_LIVEKIT_URL`) |
| `__I18N_PREFIX__` | `connect__` | i18n key prefix |
| `__PLUGIN_ROUTE__` | `connect` | URL segment for plugin routes |
| `__PLUGIN_CONTAINER__` | `care-connect-container` | Tailwind scoping class |
| `__PLUGIN_PORT__` | `4173` | Vite preview port for the remote |

Never ship a file with an unsubstituted `__…__` token.
