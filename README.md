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

The agent will create dedicated `care` + `care_fe` checkouts inside your workspace, allocate
available ports, bring up isolated Docker services, scaffold your plugin from `templates/`, wire
it into both cores, and verify it end to end. Existing CARE installations are left alone.

### Workspace isolation

Requires Python 3 and Docker Compose 2.24.4 or newer. To choose ports on first setup, copy
[`care-scaffold.env.example`](care-scaffold.env.example) to your workspace as `care-scaffold.env`
and edit it before running the helper. Explicit port values win; leave any blank or omit them
for automatic allocation. This file is the only source for core paths and ports.

Before starting services:

```bash
python3 /path/to/care_scaffold/scripts/configure-workspace.py --workspace /path/to/workspace
source /path/to/workspace/care-scaffold.env
```

The helper validates explicit ports, fills blanks, and saves eight distinct host ports (API,
host frontend, plugin, PostgreSQL, Redis, MinIO API/console, debugger), plus workspace-specific
Compose identity and paths. It creates configuration only; the bootstrap clones and starts the
stack. Reruns preserve saved assignments, including while this workspace is running. To change
a port, stop this workspace, edit this file, rerun the helper, source it again, and update the
frontend API and plugin registration/configuration to match.

Before a cold start, add `--check-ports` to check the saved ports without changing files. On
first configuration an occupied explicit port is rejected. No check reserves ports until
startup: Docker and Vite fail on a later conflict instead of changing ports or adopting services.

An existing `.agent/stack.env` is migrated to `care-scaffold.env` with its values preserved.
The old file is removed only after a successful write. If both files exist, the helper refuses
to proceed until you resolve the duplicate configuration.

Use `/path/to/workspace/.agent/compose.sh` for all backend operations, including `config`,
`up -d --build --wait`, and `exec backend python manage.py migrate`. Core `make` commands omit
the workspace override. Start the host frontend with
`npm run dev -- --host 127.0.0.1 --port "$CARE_FE_PORT" --strictPort`.
Pass `--port "$PLUGIN_PORT" --api-url "$CARE_API_URL"` to `new-plugin.sh`; outside bootstrap,
the generator reads `care-scaffold.env` from its output directory. The first plugin uses its
saved port; additional plugins receive another available port. Explicit CLI options take precedence.

## What's in here

| Path | Purpose |
| --- | --- |
| [`bootstrap.prompt.md`](bootstrap.prompt.md) | The single entrypoint prompt. Sets up core + scaffolds a plugin. |
| [`AGENTS.md`](AGENTS.md) | Orientation for any agent that opens this repo directly. |
| [`skills/`](skills/) | Nine `SKILL.md` files — the actual plugin-building knowledge. |
| [`templates/backend/`](templates/backend/) | Runnable Django plugin skeleton (`__PLUGIN_SNAKE__`). |
| [`templates/frontend/`](templates/frontend/) | Runnable federated Vite plugin skeleton (`__PLUGIN_FE__`). |
| [`scripts/new-plugin.sh`](scripts/new-plugin.sh) | Materializes both templates with your plugin's name. |
| [`care-scaffold.env.example`](care-scaffold.env.example) | Optional starting configuration; blank ports are allocated automatically. |
| [`scripts/configure-workspace.py`](scripts/configure-workspace.py) | Validates and saves workspace ports and generates isolated Compose configuration. |
| [`reference/`](reference/) | Worked example: the LiveKit teleconsultation plugin, start to finish. |

## Check the scaffold

```bash
python3 scripts/test-configure-workspace.py
python3 scripts/test-new-plugin.py
```

These use temporary directories and loopback sockets, without starting CARE or installing npm
packages. The generator check also needs Node.js; the Compose merge check needs the Docker CLI.

## The prime directive

> **Minimal overlap with core.**
> A plugin owns its own models, migrations, API surface, UI and i18n keys.
> The only acceptable change to `care` or `care_fe` is adding a *generic, reusable extension point* —
> never plugin-specific logic.

Read [`skills/care-plugin-architecture/SKILL.md`](skills/care-plugin-architecture/SKILL.md) first;
it links out to the rest.
