# CARE Plugin Bootstrap

**You are an AI coding agent. Execute this document top to bottom.**

Your goal: take the user from an empty workspace to a **running CARE stack with a working
plugin scaffold wired into it**, then help them build their feature.

Do not summarise this document back to the user. Do the work. Report only decisions,
blockers, and the final state.

---

## Ground rules (non-negotiable)

1. **Minimal overlap with core.** `care` and `care_fe` are *reference* checkouts. They exist so
   you can read their types, extension points and patterns. You modify them only to add a
   **generic** extension point, and only after proving no existing one fits.
2. **Two new repos, not a fork.** The plugin is `care_<name>` (Django) + `care_<name>_fe` (Vite).
   Both have their own Git history. The backend plugin lives inside the dedicated backend
   checkout's Docker build context; exclude it from core Git tracking.
3. **Never commit secrets.** Plugin credentials go in `plug_config.py` configs or environment,
   and `plug_config.py` must not be committed with real keys.
4. **Ask before destroying.** Dropping databases, `docker compose down -v`, force-pushing:
   confirm with the user first.
5. **Isolate the development stack.** Use this workspace's own `care` and `care_fe` checkouts,
   saved ports, and Compose wrapper. Never adopt, configure, or restart another workspace's
   services. Reuse only resources recorded for this workspace.
6. **Verify, don't assume.** Every phase has an explicit check. Do not advance past a failing check.

---

## Phase 0 — Interview

Ask the user (batch these into one question set, don't drip-feed):

- **Plugin name** — short lowercase word, e.g. `connect`, `scribe`, `labs`.
  Derive: `care_<name>` (backend), `care_<name>_fe` (frontend), `<NAME>` uppercase settings
  prefix, `<name>__` i18n prefix.
- **What does it do?** One paragraph. You will turn this into a data model and a UI surface.
- **Does it need its own database tables?** If it only annotates existing records, prefer a
  `meta` JSON field on a core model over a new table (see `care-plugin-architecture` skill).
- **Where in the UI should it appear?** Offer the extension-point catalog from the
  `care-extension-points` skill as a menu.
- **Does the patient portal need it?** (OTP-authenticated flows are a separate, phone-scoped
  API surface — see `care-auth-contexts`.)
- **Lifecycle and roles** — if the feature has records with states, ask explicitly: what are the
  states, who may move between them, and what capability does each role get? Agents reliably
  invent these; they are product decisions, not technical ones.
- **Third-party services?** LiveKit, an LLM provider, an SMS gateway, etc.
- **Workspace root** — where to put everything. Default: the current directory.

Record the answers in `.agent/plugin-brief.md` in the workspace root. You will re-read it later.

---

## Phase 1 — Isolated workspace and core repositories

Use an absolute `$WORKSPACE` path. This bootstrap requires Python 3 and Docker Compose **2.24.4+**.
The version requirement is for [`!override` port replacement](https://docs.docker.com/reference/compose-file/merge/#replace-value),
so the upstream published ports are removed, not retained alongside the new ports.

### 1.1 Configure and save ports

Use `$WORKSPACE/care-scaffold.env` as the single source for core paths and ports. On first setup,
optionally copy `<this-repo>/care-scaffold.env.example` there and edit the port values before
running the helper. Explicit values win; blank or missing port entries are allocated. Do not
replace an existing workspace configuration with the example.

```bash
python3 <this-repo>/scripts/configure-workspace.py --workspace "$WORKSPACE"
source "$WORKSPACE/care-scaffold.env"
```

The helper checks IPv4 and IPv6 availability, rejects occupied explicit ports on first setup,
and fills blank or missing ports from a workspace-specific starting point. It saves eight
distinct ports. `care-scaffold.env` records `CARE_BE`, `CARE_FE`,
`COMPOSE_PROJECT_NAME`, `CARE_API_URL`, `CARE_FE_URL`, and:

| Variable | Host service |
| --- | --- |
| `CARE_API_PORT` | CARE backend |
| `CARE_FE_PORT` | CARE frontend |
| `PLUGIN_PORT` | Plugin preview |
| `CARE_DB_PORT` | PostgreSQL |
| `CARE_REDIS_PORT` | Redis |
| `CARE_S3_PORT` | MinIO API / browser uploads |
| `CARE_S3_CONSOLE_PORT` | MinIO console |
| `CARE_DEBUG_PORT` | Backend debugger |

It also generates `.agent/compose.override.yaml` and executable `.agent/compose.sh`. They isolate
published ports, the network, database/Redis volumes, and the backend/Celery image name. Published
ports bind to loopback. Internal container ports and service names stay unchanged.

Rerunning the helper preserves saved assignments, including when this stack is running. Before
a cold start, with this workspace's services stopped, check availability without changing files:

```bash
python3 <this-repo>/scripts/configure-workspace.py --workspace "$WORKSPACE" --check-ports
```

Availability checks cannot reserve ports until startup: if another process later takes a saved
port, startup must fail. Identify the owner; never kill or adopt it or silently choose a new
port. For a deliberate reassignment, stop this workspace, edit `care-scaffold.env`, rerun the
helper to refresh derived URLs, source `care-scaffold.env` again, then update the frontend API
URL, plugin configuration, and federation registration together before restarting.

If an older workspace has only `.agent/stack.env`, the helper migrates its values to
`care-scaffold.env` and removes the old file only after a successful write. If both files exist,
resolve the duplicate configuration explicitly before proceeding; the helper will not choose
between them.

### 1.2 Clone dedicated core checkouts

`CARE_BE` is always `$WORKSPACE/care`; `CARE_FE` is always `$WORKSPACE/care_fe`.
Clone missing repositories:

```bash
git clone https://github.com/ohcnetwork/care.git "$CARE_BE"
git clone https://github.com/ohcnetwork/care_fe.git "$CARE_FE"
```

On reruns, reuse these directories only after confirming they are this workspace's checkouts
with the expected Git remotes and files. Do not search `~/git`, siblings, or other workspaces for
reusable installations, and do not symlink these paths to another checkout. If either directory
predates this bootstrap and ownership is unclear, choose a fresh workspace before proceeding.

**Check:** both paths are real directories under `$WORKSPACE`, with `plug_config.py` and
`src/pluginTypes.ts` respectively. Inspect the cloned Compose files for additional services,
fixed container names, external volumes, or host bind mounts that would escape isolation; adapt
only this workspace's override if upstream has changed.

### 1.3 Record plugin paths

Write `$WORKSPACE/.agent/paths.env` with only the absolute paths for `PLUGIN_BE` and `PLUGIN_FE`.
Keep core paths and ports only in `care-scaffold.env`; source both files in future sessions.
Initially the generator creates plugins at `$WORKSPACE/care_<name>` and
`$WORKSPACE/care_<name>_fe`. Update `PLUGIN_BE` after moving it into the dedicated backend in 6.1.

Do not commit `care-scaffold.env` or `.agent/` (add both to the workspace's ignore rules if needed).

---

## Phase 2 — Backend up

### 2.0 Verify the isolated configuration

```bash
"$WORKSPACE/.agent/compose.sh" config
"$WORKSPACE/.agent/compose.sh" ps
```

Before starting, verify the rendered config: every published host port matches `care-scaffold.env`,
the project/network/image/volume names are workspace-specific, and bind mounts refer to this
workspace. Confirm browser-facing S3 endpoints use `CARE_S3_PORT`; internal requests still use
`http://minio:9000`. Existing services on 9000, 4000, 5433, 6380, 9100, or 9001 belong to other
stacks and are left alone. Only reuse containers belonging to the saved project and checkout.

**Use `.agent/compose.sh` for every operation.** Plain `make` targets and bare `docker compose`
commands can omit the override and return to shared ports or resources.

### 2.1 Start and seed

```bash
"$WORKSPACE/.agent/compose.sh" up -d --build --wait
"$WORKSPACE/.agent/compose.sh" exec backend python manage.py migrate
# First setup only; do not reload fixtures into an existing populated workspace.
"$WORKSPACE/.agent/compose.sh" exec backend python manage.py load_fixtures
```

If Docker is unavailable, stop and report the requirement. Do not fall back to the user's host
PostgreSQL/Redis or an existing venv backend. An explicitly requested venv setup must preserve
these same checkout, database, storage, and port boundaries.

> Never use `down -v` or `make teardown` without approval: these delete database volumes.
> `"$WORKSPACE/.agent/compose.sh" down` stops only this workspace and preserves named volumes.

### Fixture credentials (all password `Ohcn@123`)

`care-doctor`, `care-admin`, `care-nurse`, `care-staff`, `care-volunteer`, `care-fac-admin`,
`care-role-admin`, `care-role-manager`, `care-role-member`.

**Check:** `curl -s "$CARE_API_URL/api/v1/plug_config/"` returns JSON
(401 is fine — it means the server is up). Confirm `compose.sh ps` shows only the saved ports.

---

## Phase 3 — Frontend up

### 3.0 Detect only this workspace's server

```bash
lsof -nP -iTCP:"$CARE_FE_PORT" -sTCP:LISTEN
```

If occupied, inspect the listener's working directory and arguments. Reuse it only if it is
`$CARE_FE` on the saved port with the correct API URL. A listener from another workspace is a
conflict to resolve, not a server to adopt. Restart only this workspace's server after env edits.

### 3.1 Configure and start

In `$CARE_FE/.env.local`, set exactly one `REACT_CARE_API_URL` entry to the saved `CARE_API_URL`.
Update any old value rather than appending a duplicate or retaining a default URL. Preserve other
settings. Verify local backend CORS/CSRF settings allow `CARE_FE_URL` if the checked-out version
restricts them; make any needed development override only for this workspace.

```bash
cd "$CARE_FE"
npm install --ignore-scripts && npm run postinstall
npm run dev -- --host 127.0.0.1 --port "$CARE_FE_PORT" --strictPort
```

**Check:** the login page renders at `$CARE_FE_URL`, its network requests use `$CARE_API_URL`, and
you can sign in as `care-admin` / `Ohcn@123`. `--strictPort` prevents an unexpected port change.

> `.env.local` changes are **not** hot-reloaded. Restart this workspace's server with the same
> explicit port arguments after every edit.

---

## Phase 4 — Install the skills

The skills are the reason this works. Put them where your agent runtime will find them.

```bash
mkdir -p "$WORKSPACE/.github/skills"
cp -R <this-repo>/skills/* "$WORKSPACE/.github/skills/"
```

Also copy `AGENTS.md` guidance into the workspace root `AGENTS.md` if one does not exist, so a
future session re-orients itself without re-running this prompt.

**Check:** `ls "$WORKSPACE/.github/skills"` lists nine directories, each with a `SKILL.md`.

**Now read `skills/care-plugin-architecture/SKILL.md` in full before writing any plugin code.**

---

## Phase 5 — Scaffold the plugin

```bash
<this-repo>/scripts/new-plugin.sh \
  --name connect \
  --title "Care Connect" \
  --description "Teleconsultation for CARE" \
  --out "$WORKSPACE" \
  --port "$PLUGIN_PORT" \
  --api-url "$CARE_API_URL"
```

This materialises:

- `$WORKSPACE/care_connect/` — Django package (`setup.py`, `care_connect/{apps,settings,urls}.py`,
  `models/`, `serializers/`, `viewsets/`, `migrations/`, `tests/`).
- `$WORKSPACE/care_connect_fe/` — Vite app (`vite.config.ts` with federation, `src/manifest.tsx`,
  `src/utils/api.ts`, `src/components/Page.tsx`, `public/locale/en.json`).

**Check:** no file under either directory still contains a `__PLUGIN` placeholder token:

```bash
grep -rn '__PLUGIN_\|__I18N_PREFIX__' "$WORKSPACE/care_connect" "$WORKSPACE/care_connect_fe" && echo "FAIL: unsubstituted tokens"
```

---

## Phase 6 — Wire into core

This phase wires the plugin into the dedicated core checkouts. Keep the changes to a handful of lines.

### 6.1 Backend registration — `$CARE_BE/plug_config.py`

Append a `Plug` and add it to the `plugs` list:

```python
import sys
from pathlib import Path

# Prevent namespace package shadowing.
sys.path.insert(0, str(Path(__file__).resolve().parent / "care_connect"))

care_connect = Plug(
    name="care_connect",
    package_name="care_connect",   # local dir for dev; git+https://… for deploys
    version="",                    # empty version + local dir ⇒ pip install -e ./care_connect
    configs={
        "CONNECT_SOME_KEY": "value",
    },
)

plugs = [care_connect, ...]
```

Place the plugin inside the backend checkout so pip — and Docker's build context — can see it:

```bash
# A REAL directory, not a symlink.
mv "$PLUGIN_BE" "$CARE_BE/care_connect"       # or: git clone straight into $CARE_BE/
```

> ⚠️ **Do not use a symlink.** `dev.Dockerfile` does `COPY . /app`, and Docker's build context
> cannot follow a symlink that points outside it. The link resolves to nothing in the image and
> `install_plugins.py` fails or silently installs nothing. Keep the plugin repo as a real
> directory inside `$CARE_BE` and give it its own git remote.

Update `PLUGIN_BE` in `.agent/paths.env` to the new path and exclude this nested plugin repo
from the dedicated core checkout's Git tracking.

Rebuild the workspace image: `dev.Dockerfile` installs plugins **at image build time** into
`/.venv`, and only the source tree is bind-mounted. Both backend and Celery must use the rebuilt
workspace-specific image.

```bash
"$WORKSPACE/.agent/compose.sh" up -d --build --wait
"$WORKSPACE/.agent/compose.sh" exec backend python manage.py makemigrations care_connect
"$WORKSPACE/.agent/compose.sh" exec backend python manage.py migrate
```

**Check:** `curl -s "$CARE_API_URL/api/care_connect/config/"` returns something other than 404.

### 6.2 Frontend registration — `$CARE_FE/.env.local`

Set this entry using the **numeric value** saved as `PLUGIN_PORT` (substitute it when writing the
file, do not leave a shell variable reference in `.env.local`):

```bash
REACT_ENABLED_APPS=ohcnetwork/care_connect_fe@localhost:${PLUGIN_PORT}/assets/remoteEntry.js
```

Append to any existing value (comma-separated) rather than overwriting — other plugins in this
workspace may already be enabled. The generator has also written the selected preview port and
standalone API URL into the plugin template.

```bash
lsof -nP -iTCP:"$PLUGIN_PORT" -sTCP:LISTEN
cd "$PLUGIN_FE" && npm install && npm run dev
```

Reuse a listener only after verifying it belongs to `$PLUGIN_FE`. The plugin uses `strictPort`;
if a foreign process owns the port, resolve the conflict explicitly and keep registration and
preview configuration aligned. For additional plugins, allocate separate available ports; do
not give every plugin the workspace's first `PLUGIN_PORT`.

Restart only `$CARE_FE` with `--host 127.0.0.1 --port "$CARE_FE_PORT" --strictPort` so it picks up
`.env.local`. Hard-reload the browser after rebuilding the plugin.

**Check:** the remote is served at `http://localhost:$PLUGIN_PORT/assets/remoteEntry.js`, the
browser console has no `There was an error enabling the app care_connect_fe`, and
`window.__CARE_PLUGIN_RUNTIME__.meta` contains your slug.

### 6.3 Extension points — only if needed

If your UI has nowhere to attach, add a new extension point to core. Load the
`care-extension-points` skill and follow its "Adding a new extension point" procedure exactly.
Keep the change generic and plugin-agnostic; it is a PR to core and will be reviewed as such.

Track every core file you touch in `$WORKSPACE/.agent/core-diff.md`. The list should stay short.

---

## Phase 7 — Build the feature

Now, and only now, implement what the user described in Phase 0.

Recommended order — do not build the UI before the API works:

1. **Model** the domain in `care_<name>/models/`. Prefer extending core via `meta` JSON +
   signals over new FKs into core tables. Generate + apply migrations.
2. **Serializers + viewsets**, registered in `care_<name>/urls.py`. Scope every queryset by
   permission (see `care-auth-contexts`). Add the OTP-scoped variants if the patient portal
   needs them.
3. **Verify the API with `curl`** before touching React. Log in via
   `POST /api/v1/auth/login/` to get a token.
4. **Frontend types + API client** in `src/types.ts` / `src/utils/api.ts`.
5. **Components**, registered in `src/manifest.tsx` under `components` / `routes`.
   Load the `care-design-system` skill first — the plugin has its own Tailwind build and will
   look foreign unless you reproduce CARE's palette and match the host's shadcn conventions.
6. **i18n**: every user-facing string uses `t("<name>__some_key")`, defined in the plugin's own
   `public/locale/en.json`.
7. **Async work** (celery tasks, webhooks, beat schedules) last.
   If the plugin brokers a third-party service, load `care-third-party-services` **before**
   step 2 — the API secret must never leave the backend, and the token/webhook design shapes
   your viewsets.

Consult the matching skill before each step. Re-read `.agent/plugin-brief.md` if you drift.

---

## Phase 8 — Verify end to end

1. Hard-reload `care_fe`; confirm your component renders at its extension point.
2. Exercise the happy path as a staff user, and (if applicable) as an OTP patient user.
3. Check the network tab: requests hit `/api/care_<name>/…`, not core routes.
4. `cd "$CARE_FE" && npx tsc --noEmit` and `cd "$PLUGIN_FE" && npm run build` both pass.
5. Re-read `.agent/core-diff.md`. For each core file listed, justify it in one line. If you
   cannot, revert it and find another way.

Load `care-plugin-verification` for debugging recipes (stale plugin installs, federation 404s,
i18n keys rendering raw, CORS-looking errors that are really 500s).

---

## Final report

Produce a short summary containing:

- Paths to the two new plugin repos.
- The exact list of core files touched, with a one-line justification each.
- The API surface added, as a route table.
- The extension points consumed.
- Saved stack configuration, every assigned host port, and exact commands to restart this workspace
  (`.agent/compose.sh`, host Vite with explicit port and `--strictPort`, plugin `npm run dev`).
- Anything you could not do without further core changes.
