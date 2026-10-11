# AGENTS.md

You are looking at **care_scaffold**, a knowledge + template repo for building plugins for
[CARE](https://github.com/ohcnetwork/care) (Django backend) and
[care_fe](https://github.com/ohcnetwork/care_fe) (React frontend).

The tracked scaffold contains **no application code**. This checkout is the default development
workspace, with independent core and plugin repositories inside it. Work on the plugin in its own
repositories; keep reusable tooling and guidance in the scaffold.

## Repository boundaries

- `care/` and `care_fe/` are independent, ignored Git checkouts used as **read-only core
  dependencies**, not submodules. Clone them only if absent; preserve existing repositories and
  revisions on reruns. Do not update core as part of plugin development.
- Generated `care/care_<name>/` and `care_<name>_fe/` are independent Git repositories from
  creation, inside this checkout. No separate parent or sibling workspace is required. Run Git
  commands in the intended repository; never stage these repositories in the scaffold or core.
- Root-anchored `/care/` and `/care_*/` ignores exclude core and plugin directories from scaffold
  commits. The generator excludes the nested backend plugin using core's local `.git/info/exclude`.
  Plugin source remains trackable in its own repository. `/.github/skills/` ignores generated skill
  copies; source `skills/` and `templates/` remain tracked.
- Keep app-specific briefs, local configuration and verification artifacts in `.agent/` or
  the plugin repositories. Keep reusable templates, scripts and guidance in this repository.
- Register plugins through external runtime configuration. Never edit core source, migrations,
  types, translations, `plug_config.py`, or core configuration files to make a plugin work.
  Dependency installs and generated runtime caches must leave tracked core files unchanged.

## Scaffold feedback

When scaffold tooling, templates or instructions block progress or lead in the wrong direction,
file an issue on **[ohcnetwork/care_scaffold](https://github.com/ohcnetwork/care_scaffold/issues)**.
Include the affected scaffold paths, actual core revisions, reproduction, expected and actual
behavior, and the impact on the plugin. Link an existing matching issue instead of duplicating it.
A reusable scaffold fix may be submitted as a PR referencing that issue; include no app code.
If issue creation is unavailable, save the report in `.agent/scaffold-issues.md` and report that
filing remains pending. Missing core capabilities are blockers to report, not permission to patch
core. Continue independent plugin work while the affected feature remains blocked.

## If the user asks you to set up an environment or start a new plugin

Execute [`bootstrap.prompt.md`](bootstrap.prompt.md). It is self-contained and idempotent.

Each workspace uses its own `care` and `care_fe` checkouts and ports saved in
`care-scaffold.env` by `scripts/configure-workspace.py`. Optional explicit ports go in that file
first (copy `care-scaffold.env.example`); blank or missing ports are allocated and saved. Use
`.agent/compose.sh` for backend
operations and external environment variables plus explicit `--port` / `--strictPort` for the
host frontend. Never adopt or restart
another workspace's services, and never use core `make` targets that omit the isolated override.

## If the user is already mid-build

Load the relevant skill(s) from `skills/` on demand:

| Skill | Load it when… |
| --- | --- |
| `care-plugin-architecture` | **Always load first.** Decides what goes in the plugin vs. core. |
| `care-backend-plugin` | Creating/altering the Django app, models, viewsets, settings, celery tasks. |
| `care-frontend-plugin` | Creating/altering the federated Vite app, manifest, API client, i18n, styling. |
| `care-design-system` | Writing ANY UI. Tailwind theme, CARE palette, shadcn/ui, icons, scoping, portals. |
| `care-extension-points` | Deciding *where* plugin UI attaches using existing core extension points. |
| `care-auth-contexts` | Anything touching staff JWT vs. patient OTP auth, or permissions. |
| `care-third-party-services` | Integrating an external service (LiveKit, LLM, SMS, payments) or webhooks. |
| `care-plugin-interop` | Talking to another plugin (notifications, scribe, devices). |
| `care-plugin-verification` | Running, debugging or testing the plugin end to end. |

## The one rule that matters

**Zero tracked core changes.** All feature code belongs in the plugin being built. Use existing extension
points, `meta` JSON fields and Django signals. If none can support the feature, report the blocker
using the scaffold feedback workflow above. There is no exception for a generic core change.

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
| `__PLUGIN_PORT__` | `18473` | Allocated Vite preview port for the remote |
| `__PLUGIN_API_URL__` | `http://localhost:18470` | Standalone preview API URL (host injects its own when federated) |

Never ship a file with an unsubstituted `__…__` token.
