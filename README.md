# care_scaffold

**Everything an AI coding agent needs to build a CARE plugin from scratch — in one prompt.**

CARE supports plugins on both sides of the stack:

- **Backend** — a standalone Django app, pip-installed into `care` and registered through external
  `ADDITIONAL_PLUGS` configuration.
- **Frontend** — a standalone Vite app, loaded into `care_fe` at runtime via Module Federation.

Done properly, a plugin adds a complete vertical feature **without changing core**. This repo encodes
"done properly" as machine-readable skills plus runnable templates.

## Quick start

Clone the scaffold; its checkout is also the default development workspace:

```bash
git clone https://github.com/ohcnetwork/care_scaffold.git
cd care_scaffold
```

Open an agent (Copilot / Claude Code / Codex) in this checkout and give it:

```
Read and execute ./bootstrap.prompt.md
```

The agent clones `care` + `care_fe` into this checkout, allocates available ports, brings up
isolated Docker services, and creates independent plugin repositories inside it. It registers
the plugin through external configuration and verifies it end to end without editing core.
No separate parent or sibling workspace is required.

### Repository layout

```text
care_scaffold/
├── scripts/, templates/, skills/   # tracked reusable scaffold tooling
├── care/                          # independent, ignored backend checkout
│   └── care_<name>/               # independent backend plugin repository
├── care_fe/                       # independent, ignored frontend checkout
├── care_<name>_fe/                # independent, ignored frontend plugin repository
├── care-scaffold.env              # ignored local configuration
└── .agent/                        # ignored generated files and verification artifacts
```

Core and plugin repositories have their own Git roots and histories; they are never scaffold
submodules or scaffold commits. Root-anchored `/care/` and `/care_*/` ignore rules keep them out
of scaffold status. The generator also adds `/care_<name>/` to the backend checkout's local
`.git/info/exclude`, keeping the nested plugin out of core commits without editing core files.
Run Git commands and source searches in the intended repository: each plugin's source remains
trackable inside its own Git root, with its own ignores for secrets, dependencies and build output.

Generated skill copies in `/.github/skills/` are ignored too. Source `skills/` and `templates/`
remain tracked scaffold content. Bootstrap clones missing core directories and preserves existing
repositories on reruns; record their actual revisions in `.agent/`. Do not update core revisions
or edit core tracked files as part of plugin work.

From this checkout, after cloning core and configuring ports, generate a plugin with:

```bash
./scripts/new-plugin.sh --name example --title "Care Example"
```

The generator initializes separate Git repositories at `care/care_example` and `care_example_fe`
without creating commits or remotes. Reruns preserve existing plugin repositories and create only
missing sides. Existing directories without their own Git root are rejected instead of being
silently adopted. An explicit `--out /path/to/workspace` selects a different workspace root with
the same layout; the default is the scaffold checkout, even when invoked from another directory.

Scaffold blockers and incorrect guidance must be reported on
[ohcnetwork/care_scaffold](https://github.com/ohcnetwork/care_scaffold/issues); a reusable fix may
follow in a linked scaffold PR. Follow the [feedback policy](AGENTS.md#scaffold-feedback).

### Workspace isolation

Requires Python 3 and Docker Compose 2.24.4 or newer. To choose ports on first setup, copy
[`care-scaffold.env.example`](care-scaffold.env.example) to your workspace as `care-scaffold.env`
and edit it before running the helper. Explicit port values win; leave any blank or omit them
for automatic allocation. This file is the only source for core paths and ports.

Before starting services:

```bash
python3 scripts/configure-workspace.py
source ./care-scaffold.env
```

The helper defaults to this scaffold checkout; `--workspace /path/to/workspace` is an optional
override. It validates explicit ports, fills blanks, and saves eight distinct host ports (API,
host frontend, plugin, PostgreSQL, Redis, MinIO API/console, debugger), plus workspace-specific
Compose identity and paths. It creates configuration only; the bootstrap initializes and starts the
stack. Reruns preserve saved assignments, including while this workspace is running. To change
a port, stop this workspace, edit this file, rerun the helper, source it again, and update the
external frontend environment and plugin registration/configuration to match.

Before a cold start, add `--check-ports` to check the saved ports without changing files. On
first configuration an occupied explicit port is rejected. No check reserves ports until
startup: Docker and Vite fail on a later conflict instead of changing ports or adopting services.

An existing `.agent/stack.env` is migrated to `care-scaffold.env` with its values preserved.
The old file is removed only after a successful write. If both files exist, the helper refuses
to proceed until you resolve the duplicate configuration.

Use `./.agent/compose.sh` for all backend operations, including `config`,
`up -d --build --wait`, and `exec backend python manage.py migrate`. Core `make` commands omit
the workspace override. Plugin mounts and registration go in `.agent/plugin.compose.yaml`, which
the wrapper loads when present. Start the host frontend with `REACT_CARE_API_URL` and
`REACT_ENABLED_APPS` supplied through its process environment, and explicit
`--host 127.0.0.1 --port "$CARE_FE_PORT" --strictPort` arguments.
Pass `--port "$PLUGIN_PORT" --api-url "$CARE_API_URL"` to `new-plugin.sh`; outside bootstrap,
the generator reads `care-scaffold.env` from the selected workspace root. The first plugin uses its
saved port; additional plugins receive another available port. Explicit CLI options take precedence.

## What's in here

| Path | Purpose |
| --- | --- |
| [`bootstrap.prompt.md`](bootstrap.prompt.md) | The single entrypoint prompt. Sets up core + scaffolds a plugin. |
| [`AGENTS.md`](AGENTS.md) | Orientation for any agent that opens this repo directly. |
| [`skills/`](skills/) | Nine `SKILL.md` files — the actual plugin-building knowledge. |
| [`templates/backend/`](templates/backend/) | Runnable Django plugin skeleton (`__PLUGIN_SNAKE__`). |
| [`templates/frontend/`](templates/frontend/) | Runnable federated Vite plugin skeleton (`__PLUGIN_FE__`). |
| [`scripts/new-plugin.sh`](scripts/new-plugin.sh) | Materializes both templates as independent Git repositories. |
| [`care-scaffold.env.example`](care-scaffold.env.example) | Optional starting configuration; blank ports are allocated automatically. |
| [`scripts/configure-workspace.py`](scripts/configure-workspace.py) | Validates and saves workspace ports and generates isolated Compose configuration. |
| [`reference/`](reference/) | Worked example: the LiveKit teleconsultation plugin, start to finish. |

## Check the scaffold

```bash
python3 scripts/test-configure-workspace.py
python3 scripts/test-new-plugin.py
```

These use temporary directories and loopback sockets, without starting CARE, modifying existing
services, or installing npm packages. They check independent plugin Git roots, safe reruns, local
core exclusion, scaffold ignores, and trackable scaffold sources alongside port/Compose behavior.
The generator check also needs Node.js; the Compose merge check needs the Docker CLI.

## The prime directive

> **Zero core changes.**
> A plugin owns its own models, migrations, API surface, UI and i18n keys.
> Do not edit tracked core files in `care` or `care_fe`, even to add a generic extension point. Report missing
> capabilities as scaffold blockers and keep working within existing plugin interfaces.

Read [`skills/care-plugin-architecture/SKILL.md`](skills/care-plugin-architecture/SKILL.md) first;
it links out to the rest.
