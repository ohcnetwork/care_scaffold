# CARE Plugin Bootstrap

**You are an AI coding agent. Execute this document top to bottom.**

Use `care_scaffold` as the reusable workspace for building the user's plugin. The plugin lives
in independent repositories inside this checkout; only reusable tooling and guidance are tracked
by the scaffold. No separate parent or sibling workspace is required.
Do the work and report decisions, blockers and the final state.

## Ground rules

1. **Work only on the plugin. Zero core changes.** `care` and `care_fe` are independent, ignored
   checkouts and read-only source dependencies. Do not edit their source, migrations, types,
   translations, settings, `plug_config.py`, Dockerfiles or other tracked files. Do not add even a generic
   extension point. Use existing plugin interfaces; report gaps as blockers.
2. **Independent plugin repositories.** Create `care/care_<name>` and `care_<name>_fe` with
   their own Git histories inside `care_scaffold`. Never register them as submodules or stage them
   in the scaffold or core. The scaffold ignores both; core locally excludes the nested backend
   plugin. Source stays trackable inside each plugin repository. Run Git commands in that root.
3. **External configuration.** Keep the brief, plugin paths, runtime configuration and evidence
   in `$WORKSPACE/.agent/`. Configure core through container/process environment and external
   Compose overrides, never by editing its files. Runtime caches and installed dependencies
   must leave tracked core files unchanged.
4. **Never commit secrets.** Keep local credentials in ignored `.agent/` configuration or secret
   environment variables. Plugin repositories have their own ignores for dependencies and secrets.
5. **Isolate the development stack.** Use only this workspace's checkouts, saved ports and Compose
   wrapper. Never adopt, configure or restart another workspace's services. Do not use core `make`
   targets or bare Compose commands that omit the isolated override.
6. **Ask before destroying.** Dropping databases, `down -v`, or force-pushing requires approval.
7. **Verify each phase.** Do not advance past a failing check. Do not silently patch core to pass.

## Scaffold feedback — applies in every phase

When a scaffold script, template or instruction blocks progress or sends the implementation in
an incorrect direction, file an issue on **ohcnetwork/care_scaffold**. Include affected scaffold
paths, actual core revisions, reproduction steps, expected versus actual behavior, and the plugin
impact. Link an existing matching issue instead of duplicating it. Missing supported core hooks
also belong in this feedback workflow; they do not authorize a core edit.

For example, write a concrete report to `.agent/scaffold-issue.md`, then use
`gh issue create --repo ohcnetwork/care_scaffold --title "..." --body-file .agent/scaffold-issue.md`.
Save the resulting URL in `.agent/scaffold-issues.md`. If filing is unavailable, save the report
and state that the issue is pending; continue independent plugin work.

A reusable fix may be submitted as a scaffold PR referencing that issue. Keep application code
out of the scaffold PR. Leave unsupported feature work blocked until a supported interface is
available; do not open or implement a core patch as part of the plugin task.

## Phase 0 — Brief and repository paths

Use known answers; ask only for missing product decisions, in one batch:

- Plugin name: short lowercase word, such as `connect`; derive `care_connect`, `care_connect_fe`,
  settings prefix `CONNECT`, and i18n prefix `connect__`.
- Feature, data model, lifecycle, roles and third-party services.
- UI surface and whether patient OTP flows are required. Consult existing extension points.
- Repository locations: default to `care/care_<name>` and `care_<name>_fe` inside this scaffold
  checkout. Use a separate scaffold checkout per isolated stack. Both plugin sides are optional.

Set absolute `$WORKSPACE` to this **scaffold checkout**, not its parent or a core checkout.
Record answers in `$WORKSPACE/.agent/plugin-brief.md`. Existing plugin repositories must be
inspected and reused only when they are the intended plugin; the generator preserves existing
plugin repositories and creates only missing sides.

## Phase 1 — Independent core checkouts and isolated configuration

Requires Git, Python 3 and Docker Compose **2.24.4+** (`!override` replaces upstream port lists).
If starting without a scaffold checkout, clone it first:

```bash
git clone https://github.com/ohcnetwork/care_scaffold.git
```

Inside the scaffold workspace, clone each core only if its directory does not exist. An existing
path must be the exact Git root, not a directory that resolves to the scaffold repository:

```bash
for core in care care_fe; do
  core_path="$WORKSPACE/$core"
  if [ ! -e "$core_path" ] && [ ! -L "$core_path" ]; then
    git clone "https://github.com/ohcnetwork/$core.git" "$core_path"
  fi
  [ ! -L "$core_path" ] || { echo "Refusing symlinked core: $core_path"; exit 1; }
  [ "$(git -C "$core_path" rev-parse --show-toplevel)" = "$core_path" ] || exit 1
  git -C "$core_path" status --short
  git -C "$core_path" remote -v
  git -C "$core_path" rev-parse HEAD
done
```

Verify the expected ohcnetwork remotes and record starting core revisions and status in `.agent/`
for comparison at the end. Preserve existing repositories, branches and modifications on reruns;
do not pull, reset or replace them. Core updates are separate maintenance. Never reuse another
workspace's checkouts or symlink to them. Core and plugins must not appear as gitlinks in the
scaffold index. If migrating an older submodule layout, preserve its Git metadata and working
tree before removing submodule registration; do not delete or reclone existing work.

Use `$WORKSPACE/care-scaffold.env` as the single source for core paths and ports. Optionally copy
`care-scaffold.env.example` there **only on first setup**, and edit explicit ports before running:

```bash
python3 "$WORKSPACE/scripts/configure-workspace.py" --workspace "$WORKSPACE"
source "$WORKSPACE/care-scaffold.env"
```

The helper validates explicit ports, allocates missing ones, and preserves saved assignments.
`CARE_BE` is `$WORKSPACE/care`; `CARE_FE` is `$WORKSPACE/care_fe`. It saves `COMPOSE_PROJECT_NAME`,
`CARE_API_URL`, `CARE_FE_URL`, and eight distinct loopback host ports:

| Variable | Service |
| --- | --- |
| `CARE_API_PORT` | Backend API |
| `CARE_FE_PORT` | Host frontend |
| `PLUGIN_PORT` | First plugin preview |
| `CARE_DB_PORT` | PostgreSQL |
| `CARE_REDIS_PORT` | Redis |
| `CARE_S3_PORT` | MinIO API / browser uploads |
| `CARE_S3_CONSOLE_PORT` | MinIO console |
| `CARE_DEBUG_PORT` | Backend debugger |

It generates `.agent/compose.override.yaml` and `.agent/compose.sh` with isolated ports,
network, volumes and image names. The wrapper also reads `.agent/paths.env` and loads
`.agent/plugin.compose.yaml` when present; neither is overwritten by the helper.

Before a cold start, check saved ports without changing configuration:

```bash
python3 "$WORKSPACE/scripts/configure-workspace.py" --workspace "$WORKSPACE" --check-ports
```

No check reserves a port. Docker and Vite must fail on conflicts; never kill an unrelated owner
or silently select another port. To reassign, stop this workspace, edit `care-scaffold.env`,
rerun the helper and refresh external plugin/host configuration. If `.agent/stack.env` exists,
the helper migrates it; if both old and new files exist, resolve the duplicate explicitly.

**Check:** each core resolves to its own Git root and its initial revision/status is recorded.
Both core directories are ignored by the scaffold; no tracked core files were changed by setup.
Inspect core Compose files for fixed names, external resources or mounts that escape isolation;
adapt only the external override if needed, and report a scaffold issue.

## Phase 2 — Start the backend

```bash
"$WORKSPACE/.agent/compose.sh" config
"$WORKSPACE/.agent/compose.sh" ps
```

Check all host ports and workspace-specific network/image/volume names before starting.
Browser-facing S3 URLs must use `CARE_S3_PORT`; internal traffic remains `http://minio:9000`.

```bash
"$WORKSPACE/.agent/compose.sh" up -d --build --wait
"$WORKSPACE/.agent/compose.sh" exec backend python manage.py migrate
# First setup only; never reload fixtures into an existing populated workspace.
"$WORKSPACE/.agent/compose.sh" exec backend python manage.py load_fixtures
```

If Docker is unavailable, report the requirement. Do not fall back to the user's databases or
an existing host backend. `compose.sh down` preserves volumes; never use `down -v` without approval.

Fixture users include `care-admin`, `care-doctor`, `care-nurse`, `care-staff`, `care-volunteer`,
`care-fac-admin`, `care-role-admin`, `care-role-manager`, `care-role-member`; password `Ohcn@123`.

**Check:** `curl -s "$CARE_API_URL/api/v1/plug_config/"` returns JSON (401 means the server is
reachable). `compose.sh ps` must show only this workspace's saved ports.

## Phase 3 — Start the host frontend without editing core

Inspect the saved port with `lsof -nP -iTCP:"$CARE_FE_PORT" -sTCP:LISTEN`. Reuse a listener only
when its working directory, arguments and API URL identify this workspace's host.

On first setup create `.agent/frontend.env` with `REACT_ENABLED_APPS=''`. Preserve it on reruns.
Create executable `$WORKSPACE/.agent/frontend.sh` with:

```bash
#!/usr/bin/env bash
set -euo pipefail
STACK_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
set -a
source "$STACK_DIR/../care-scaffold.env"
source "$STACK_DIR/frontend.env"
set +a
cd "$CARE_FE"
exec env REACT_CARE_API_URL="$CARE_API_URL" \
  npm run dev -- --host 127.0.0.1 --port "$CARE_FE_PORT" --strictPort
```

Install dependencies without changing the core lockfile, then start that wrapper:

```bash
cd "$CARE_FE"
npm ci --ignore-scripts && npm_config_package_lock=false npm run postinstall
"$WORKSPACE/.agent/frontend.sh"
```

Do not write `care_fe/.env.local` or edit Vite configuration. If additional backend CORS/CSRF
configuration is needed, supply supported environment settings in the external Compose override.

**Check:** sign in at `CARE_FE_URL` as `care-admin`; requests use `CARE_API_URL`. Check that
tracked core files are unchanged. Environment changes require a host restart on the same port.

## Phase 4 — Load skills

Read `$WORKSPACE/skills/care-plugin-architecture/SKILL.md` first, then the skills relevant to the
current step. `AGENTS.md` is the repository-boundary policy for future sessions. Keep skill
installation copies, if required by the agent runtime, in the ignored `$WORKSPACE/.github/skills/`.
Keep the source `skills/` and `templates/` tracked; do not edit generated copies as the source.

## Phase 5 — Create independent plugin repositories

For example (substitute the agreed plugin name and title):

```bash
"$WORKSPACE/scripts/new-plugin.sh" \
  --name connect \
  --title "Care Connect" \
  --description "Teleconsultation for CARE" \
  --port "$PLUGIN_PORT" \
  --api-url "$CARE_API_URL"
```

The generator defaults to this scaffold checkout, regardless of the current directory. It creates
`$WORKSPACE/care/care_connect` and `$WORKSPACE/care_connect_fe`, initializes Git separately in
each, and creates no commits or remotes. Use `--out "$WORKSPACE"` only when explicitly selecting
another workspace with the same layout. The backend core must already be its own Git root.

Reruns leave existing plugin repositories intact, including their history, remotes, changes and
configuration, and create only missing sides. An existing directory without its own Git root is
rejected. The generator adds `/care_connect/` to core's local `.git/info/exclude` without editing
tracked core files. The scaffold's root-anchored `/care/` and `/care_*/` rules ignore both plugin
paths. If only one side is needed, remove only a newly generated unused side before feature work;
never delete an existing plugin repository on a rerun.

Record absolute `PLUGIN_BE` and `PLUGIN_FE` paths as shell-quoted assignments in
`$WORKSPACE/.agent/paths.env`. Keep core paths and ports only in `care-scaffold.env`; source both
files in future sessions. For this example, `PLUGIN_BE="$WORKSPACE/care/care_connect"` and
`PLUGIN_FE="$WORKSPACE/care_connect_fe"`. The nested backend plugin remains its own repository.

**Check:** no template placeholders remain; `git -C "$PLUGIN_BE" rev-parse --show-toplevel` and
its frontend equivalent identify the two independent roots, not the scaffold. Plugin source is
visible to Git and agent searches run from each plugin root. Verify generated paths are excluded:

```bash
git -C "$WORKSPACE" status --short --untracked-files=all
git -C "$WORKSPACE" check-ignore care/ care_fe/ care_connect_fe/ .agent/ care-scaffold.env .github/skills/
git -C "$CARE_BE" check-ignore care_connect/
```

No core or plugin gitlink appears in the scaffold index; source `scripts/`, `templates/` and
`skills/` remain trackable.

## Phase 6 — Register through external configuration

### 6.1 Backend

Core's `PlugManager` already reads `ADDITIONAL_PLUGS` (JSON). Use it without editing
`plug_config.py`. For the example plugin, write `$WORKSPACE/.agent/plugin.compose.yaml`:

```yaml
services:
  backend:
    build:
      args:
        ADDITIONAL_PLUGS: ""
    environment: &plugin_environment
      ADDITIONAL_PLUGS: >-
        [{"name":"care_connect","package_name":"/plugins/care_connect","version":"","configs":{"CONNECT_ENABLED":true}}]
    volumes:
      - &plugin_mount
        type: bind
        source: ${PLUGIN_BE:?Set PLUGIN_BE in .agent/paths.env}
        target: /plugins/care_connect
        bind:
          create_host_path: false
    entrypoint:
      - bash
      - -c
      - python -m pip install -e /plugins/care_connect && exec bash scripts/start-dev.sh
  celery:
    environment: *plugin_environment
    volumes:
      - *plugin_mount
    entrypoint:
      - bash
      - -c
      - python -m pip install -e /plugins/care_connect && exec bash scripts/celery-dev.sh
```

Substitute names and settings for the actual plugin. Preserve any existing local override entries.
This uses the unmodified core Dockerfile and mounts the independent plugin outside `/app`.
The empty **build** argument prevents Docker from trying to install an unpublished host path
while building. The **runtime** environment registers the mounted plugin; both entrypoints
install it in editable mode on every container start. Core's `install_plugins.py` by itself
performs an ordinary installation, not an editable one.

```bash
"$WORKSPACE/.agent/compose.sh" config
"$WORKSPACE/.agent/compose.sh" up -d --build --wait
"$WORKSPACE/.agent/compose.sh" exec backend python manage.py makemigrations care_connect
"$WORKSPACE/.agent/compose.sh" exec backend python manage.py migrate
```

Verify the mount, runtime registration and entrypoints in **both** services. Never mount over
core files. Celery's core watcher watches `/app`, so restart this workspace's Celery after plugin
source changes: `"$WORKSPACE/.agent/compose.sh" restart celery`.

**Check:** import paths in both containers point to `/plugins/care_connect`; `pip show` reports
an editable project location there; the plugin API is mounted. Keep generated migrations in the
plugin repository. For a frontend-only plugin, skip this backend registration.

### 6.2 Frontend

Set `REACT_ENABLED_APPS` in `.agent/frontend.env` to
`ohcnetwork/care_connect_fe@localhost:<PLUGIN_PORT>/assets/remoteEntry.js`, using the saved numeric
port and actual plugin slug. Preserve any other comma-separated entries. Additional plugins need
separate available ports, not the first plugin's saved port.

```bash
cd "$PLUGIN_FE"
npm install
npm run dev
```

Restart only the host through `.agent/frontend.sh` and hard-reload the browser after rebuilding
the remote. The plugin uses a strict preview port; resolve conflicts without adopting other servers.

**Check:** `http://localhost:$PLUGIN_PORT/assets/remoteEntry.js` is served, the browser reports no
plugin-loading error, and `window.__CARE_PLUGIN_RUNTIME__.meta` contains the slug.

### 6.3 UI placement

Use existing components, routes, tabs, navigation or registered overrides. Read
`care-extension-points` and verify the checked-out host's types without editing them. If no supported
surface can satisfy the requirement, follow the scaffold-feedback workflow. There is no core-edit
fallback.

## Phase 7 — Build the plugin

Re-read `.agent/plugin-brief.md`. Keep all feature work in the selected plugin repositories:

1. Models and migrations; reuse existing core `meta` fields and signals when appropriate.
2. Serializers and viewsets, permission-scoped querysets, then URLs. Load `care-auth-contexts`.
3. Verify the API with an authenticated request before writing React against it.
4. Frontend types and API client, then components and manifest. Read `care-design-system` first.
5. Namespaced i18n in the plugin's own locale files.
6. Background jobs and integrations. For external services, read `care-third-party-services`
   before designing authorization, tokens and webhook verification.

Use structurally mirrored host types; never fix a mismatch by changing core. Consult the
matching skill for each step and report scaffold defects as they are found.

## Phase 8 — Verify

1. Exercise the staff happy path and patient OTP flows when applicable.
2. Confirm plugin requests hit its API and use the right permission scope.
3. Build the frontend plugin and run relevant plugin tests. Keep test configuration and test code
   in the plugin or `.agent/`, never patch core test settings to make a run pass.
4. Inspect both core checkouts:
   `git -C "$CARE_BE" diff --exit-code` and `git -C "$CARE_BE" diff --cached --exit-code`, then
   repeat for `CARE_FE`. Compare HEAD and status with the recorded starting state. If generated
   tools changed a tracked file, inspect and remove only your change; preserve pre-existing work.
5. Confirm generated paths stay out of scaffold status, each plugin resolves to its own Git root,
   and the scaffold index contains only scaffold files, with no core/plugin code or gitlinks.
   Confirm the nested backend plugin is excluded locally from the backend core checkout.

Read `care-plugin-verification` for debugging. A required unsupported core capability remains an
explicit blocker; never claim completion by patching core.

## Phase 9 — Publish plugin repositories

Once the plugin is built and verified, publish each required plugin repository to its own remote
using the agreed owner and visibility. Ask only if those destination details are missing. Review
and commit within each plugin root; never commit app code or add app submodules in the scaffold.
Keep the scaffold checkout reusable. Local Git repositories can be used throughout development
before remote publication. Scaffold issue fixes belong in a separate scaffold PR.

## Final report

Report plugin paths and remote URLs (or pending publication), functionality and verification,
API routes and extension points, unchanged core revisions, saved ports and exact restart commands
(`.agent/compose.sh`, `.agent/frontend.sh`, plugin `npm run dev`), and scaffold issue/PR links.
Call out unsupported features and any verification or publication still pending.
