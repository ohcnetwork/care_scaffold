# care_scaffold

**Everything an AI coding agent needs to build a CARE plugin from scratch — in one prompt.**

CARE supports plugins on both sides of the stack:

- **Backend** — a standalone Django app, pip-installed into `care` and registered in `plug_config.py`.
- **Frontend** — a standalone Vite app, loaded into `care_fe` at runtime via Module Federation.

Done properly, a plugin adds a complete vertical feature **without forking core**. This repo encodes
"done properly" as machine-readable skills plus runnable templates.

## Quick start

Open an agent (Copilot / Claude Code / Codex) in an empty directory and give it:

```
Follow the instructions in https://github.com/ohcnetwork/plugin_scaffold/blob/main/bootstrap.prompt.md
```

Or, with this repo already cloned:

```
Read and execute ./bootstrap.prompt.md
```

The agent will clone core `care` + `care_fe`, bring up Postgres/Redis/LiveKit-free dev services,
install the skills into your workspace, scaffold your plugin from `templates/`, wire it into both
cores, and verify it end to end.

## What's in here

| Path | Purpose |
| --- | --- |
| [`bootstrap.prompt.md`](bootstrap.prompt.md) | The single entrypoint prompt. Sets up core + scaffolds a plugin. |
| [`AGENTS.md`](AGENTS.md) | Orientation for any agent that opens this repo directly. |
| [`skills/`](skills/) | Nine `SKILL.md` files — the actual plugin-building knowledge. |
| [`templates/backend/`](templates/backend/) | Runnable Django plugin skeleton (`__PLUGIN_SNAKE__`). |
| [`templates/frontend/`](templates/frontend/) | Runnable federated Vite plugin skeleton (`__PLUGIN_FE__`). |
| [`scripts/new-plugin.sh`](scripts/new-plugin.sh) | Materializes both templates with your plugin's name. |
| [`reference/`](reference/) | Worked example: the LiveKit teleconsultation plugin, start to finish. |

## The prime directive

> **Minimal overlap with core.**
> A plugin owns its own models, migrations, API surface, UI and i18n keys.
> The only acceptable change to `care` or `care_fe` is adding a *generic, reusable extension point* —
> never plugin-specific logic.

Read [`skills/care-plugin-architecture/SKILL.md`](skills/care-plugin-architecture/SKILL.md) first;
it links out to the rest.