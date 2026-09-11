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
   Both live *outside* the core checkouts.
3. **Never commit secrets.** Plugin credentials go in `plug_config.py` configs or environment,
   and `plug_config.py` must not be committed with real keys.
4. **Ask before destroying.** Dropping databases, `docker compose down -v`, force-pushing:
   confirm with the user first.
5. **Verify, don't assume.** Every phase has an explicit check. Do not advance past a failing check.

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
- **Preview port** for the plugin frontend. Default 4173; pick another if it is taken (4173,
  10120, 10125 are used by existing plugins).
- **Workspace root** — where to put everything. Default: the current directory.

Record the answers in `.agent/plugin-brief.md` in the workspace root. You will re-read it later.

---

## Phase 1 — Core repositories

Work in `$WORKSPACE`.

### 1.1 Detect or clone

For each of `care` (backend) and `care_fe` (frontend):

```bash
# Look for an existing checkout before cloning. Common locations:
#   $WORKSPACE/care, $WORKSPACE/care_be, ~/care, ~/eGov/care_be, ../care
```

If a checkout exists, **use it** — do not clone a second copy. Confirm the path with the user.
Otherwise:

```bash
git clone https://github.com/ohcnetwork/care.git      "$WORKSPACE/care"
git clone https://github.com/ohcnetwork/care_fe.git   "$WORKSPACE/care_fe"
```

> The backend repo is named `care` upstream. Some local checkouts are named `care_be`.
> Both are the same thing; use whatever exists. Refer to it as `$CARE_BE` from here on.

### 1.2 Record the paths

Write `$WORKSPACE/.agent/paths.env`:

```bash
CARE_BE=/abs/path/to/care
CARE_FE=/abs/path/to/care_fe
PLUGIN_BE=/abs/path/to/care_<name>
PLUGIN_FE=/abs/path/to/care_<name>_fe
```

**Check:** both core paths exist and contain `plug_config.py` / `src/pluginTypes.ts` respectively.

---

## Phase 2 — Backend up

### 2.0 Detect what is ALREADY running — do this first, always

**Never start a second backend.** If one is up, adopt it.

```bash
# Is a compose project already running?
docker compose ls
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Ports}}'

# Is anything answering on the API port?
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:9000/api/v1/plug_config/
lsof -nP -iTCP:9000 -sTCP:LISTEN
```

Decide from the result:

| Observation | Action |
| --- | --- |
| A compose project (e.g. `care_be`) is `running` | **Adopt it.** Skip to 2.2. Use its directory as `$CARE_BE`. |
| Port 9000 answers but no compose project | A local venv/runserver is already up. **Adopt it.** Do not start Docker. |
| Port 9000 answers from an unrelated process | Stop and ask the user. Do not kill it yourself. |
| Nothing is running | Proceed to 2.1 and pick a mode. |

Record the chosen mode (`docker` or `venv`) in `.agent/paths.env` as `CARE_BE_MODE`. Every later
phase must respect it. **Mixing modes corrupts state** — a venv `manage.py` run against the
Docker Postgres uses different ports and settings and will produce confusing migration errors.

Also note the real ports — this stack does **not** use defaults. Read them from `docker ps`
rather than assuming (a typical local setup exposes Postgres on **5433** and Redis on **6380**
to avoid colliding with host installs).

### 2.1 Start it (only if nothing is running)

**Docker (preferred):**

```bash
cd "$CARE_BE"
make up          # docker compose -f docker-compose.yaml -f docker-compose.local.yaml up -d --wait
```

**Local venv (only if the user has no Docker or explicitly asks):**

```bash
cd "$CARE_BE"
pg_isready   || sudo pg_ctlcluster 16 main start
redis-cli ping || redis-server --daemonize yes

python3.13 -m venv .venv && .venv/bin/pip install pipenv && .venv/bin/pipenv install --dev
DJANGO_SETTINGS_MODULE=config.settings.local DJANGO_READ_DOT_ENV_FILE=true \
  .venv/bin/python manage.py runserver 0.0.0.0:9000
```

### 2.2 Migrate and seed (safe on an already-running stack)

```bash
# docker mode
make migrate && make load-fixtures

# venv mode
DJANGO_SETTINGS_MODULE=config.settings.local DJANGO_READ_DOT_ENV_FILE=true \
  .venv/bin/python manage.py migrate
```

> ⚠️ **Never run `make teardown`.** It is `docker compose down -v`, which deletes the volumes —
> the entire database, including any data the user cares about. `make down` is the safe stop.
> If you think you need `teardown`, ask first.

### Fixture credentials (all password `Ohcn@123`)

`care-doctor`, `care-admin`, `care-nurse`, `care-staff`, `care-volunteer`, `care-fac-admin`,
`care-role-admin`, `care-role-manager`, `care-role-member`.

**Check:** `curl -s http://localhost:9000/api/v1/plug_config/ | head -c 200` returns JSON
(401 is fine — it means the server is up).

---

## Phase 3 — Frontend up

### 3.0 Detect first

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:4000
lsof -nP -iTCP:4000 -sTCP:LISTEN
```

If the host dev server is already running, **adopt it**. Do not start a second one — Vite will
silently bind a different port (4001), the plugin's `REACT_ENABLED_APPS` will not match what you
are looking at in the browser, and you will debug the wrong instance for an hour.

You will still need to **restart** it later if you change `.env.local` (see 6.2). Restarting a
server you adopted is fine; ask the user first if they started it themselves in another terminal.

### 3.1 Start it (only if nothing is running)

```bash
cd "$CARE_FE"
npm install --ignore-scripts && npm run postinstall
grep -q REACT_CARE_API_URL .env.local 2>/dev/null \
  || printf 'REACT_CARE_API_URL=http://127.0.0.1:9000\n' >> .env.local
npm run dev     # http://localhost:4000
```

**Check:** the login page renders at http://localhost:4000 and you can sign in as
`care-admin` / `Ohcn@123`.

> `.env.local` changes are **not** hot-reloaded. Restart `npm run dev` after every edit to it.

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
  --out "$WORKSPACE"
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

This is the **only** phase that touches core, and it should be a handful of lines.

### 6.1 Backend registration — `$CARE_BE/plug_config.py`

Append a `Plug` and add it to the `plugs` list:

```python
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

Then install it, according to `CARE_BE_MODE`:

#### Docker mode — rebuild the image

`dev.Dockerfile` runs `install_plugins.py` **at image build time**, into `/.venv`, which is baked
into the image. Only the source tree is bind-mounted, not the virtualenv. So a newly registered
plug does not exist until the image is rebuilt:

```bash
cd "$CARE_BE"
make down        # safe stop. NOT `make teardown` — that deletes the database volume.
make build       # re-runs install_plugins.py inside the image
make up
```

`backend` and `celery` share the same `care_local` image, so one rebuild fixes both.

> **Fast iteration only:** while actively editing plugin code you can skip the rebuild with
> `docker exec <container> python install_plugins.py`. But `docker exec` writes to that *one
> container's* writable layer, so you must run it against **both** `backend` and `celery` and
> restart them. It is a temporary patch — the change is lost on recreate. Rebuild is canonical.

#### venv mode

```bash
.venv/bin/python install_plugins.py
```

Then migrate:

```bash
make makemigrations && make migrate
```

**Check:** `curl -s http://localhost:9000/api/care_connect/config/` returns something other
than 404.

### 6.2 Frontend registration — `$CARE_FE/.env.local`

```bash
REACT_ENABLED_APPS=ohcnetwork/care_connect_fe@localhost:4173/assets/remoteEntry.js
```

Append to any existing value (comma-separated) rather than overwriting — other plugins may
already be enabled.

Start the plugin's dev server, after checking the port is free:

```bash
lsof -nP -iTCP:4173 -sTCP:LISTEN     # if taken, pick another port and update vite.config.ts
cd "$PLUGIN_FE" && npm install && npm run dev    # vite preview :4173 + vite build --watch
```

Restart the `care_fe` dev server so it picks up `.env.local` — restart the existing one, do not
start a second.

**Check:** browser console shows no `There was an error enabling the app care_connect_fe`, and
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
- How to run everything again from cold (`make up`, two `npm run dev`s, ports).
- Anything you could not do without further core changes.
