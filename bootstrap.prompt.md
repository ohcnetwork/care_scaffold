# CARE Plugin Bootstrap

**You are an AI coding agent. Execute this document top to bottom.**

Your goal: take the user from an empty workspace to a **running CARE stack with a working
plugin scaffold wired into it**, then help them build their feature.

Do not summarise this document back to the user. Do the work. But **do** announce each
infrastructure step as you take it — what you are cloning, what you are starting, on which ports —
in one or two lines, then proceed. Otherwise report only decisions, blockers, and the final state.

**The stack comes first.** Cloning and running `care` + `care_fe` is not optional preparation you
can skip when you think you already know CARE. It is the source of every type, field name and
extension point you are about to use.

---

## Ground rules (non-negotiable)

1. **Core first, always. No exceptions.** You may not write a single line of plugin code until
   `care` and `care_fe` are cloned, running locally, and *read* (Phase 3.5). There is no
   "the user probably has it already" path, no "I know CARE well enough" path, and no
   "I'll set it up later" path. A plugin written without core in front of you is slop:
   invented model fields, invented extension points, invented API shapes.
2. **Assume nothing is set up.** Treat every session as a cold start. Clone core, bring up the
   backend, bring up the frontend, in that order, every time.
3. **Minimal overlap with core.** `care` and `care_fe` are *reference* checkouts. They exist so
   you can read their types, extension points and patterns. You modify them only to add a
   **generic** extension point, and only after proving no existing one fits.
4. **Two new repos, not a fork.** The plugin is `care_<name>` (Django) + `care_<name>_fe` (Vite).
   Both live *outside* the core checkouts.
5. **Never commit secrets.** Plugin credentials go in `plug_config.py` configs or environment,
   and `plug_config.py` must not be committed with real keys.
6. **Ask before destroying.** Dropping databases, `docker compose down -v`, force-pushing:
   confirm with the user first.
7. **Verify, don't assume.** Every phase has an explicit check. Do not advance past a failing check.
8. **Say what you are about to do.** Before each phase that clones, installs or binds a port,
   tell the user in one or two lines: what you are cloning, what you are starting, and on which
   ports. Then do it.

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

Then, **before touching the disk**, state the plan out loud to the user. Something like:

> Setting up CARE from scratch before we write any plugin code.
> 1. Cloning `ohcnetwork/care` → `$WORKSPACE/care` and `ohcnetwork/care_fe` → `$WORKSPACE/care_fe`.
> 2. Bringing the backend up on **:9000** (Docker compose; Postgres and Redis on the ports that
>    compose maps — typically **5433** / **6380**).
> 3. Bringing the `care_fe` host dev server up on **:4000**.
> 4. Reading core (`plug_config.py`, `pluginTypes.ts`, `PluginEngine`, the extension-point
>    registry, the EMR models you will touch) and writing notes to `.agent/core-notes.md`.
> 5. Only then scaffolding `care_<name>` + `care_<name>_fe` and running the plugin preview on
>    **:4173**.

Substitute the real names and ports. Do not proceed silently.

---

## Phase 1 — Core repositories (mandatory, from scratch)

Work in `$WORKSPACE`. **Assume nothing exists.** There is no detection step and no
"already set up, skip ahead" branch — that shortcut is exactly how agents end up guessing at
core's API and producing unusable plugins.

### 1.1 Clone core

Tell the user you are cloning both core repos, then:

```bash
mkdir -p "$WORKSPACE" && cd "$WORKSPACE"
git clone https://github.com/ohcnetwork/care.git      "$WORKSPACE/care"
git clone https://github.com/ohcnetwork/care_fe.git   "$WORKSPACE/care_fe"
```

If the target directory already exists, you still do **not** skip anything:

| Situation | What you do |
| --- | --- |
| Directory exists and is a clean CARE checkout | `git -C <dir> fetch --all && git -C <dir> pull --ff-only`, then run **all** of Phases 2, 3 and 4.5 against it as if it were fresh. |
| Directory exists with uncommitted changes | Show `git status` to the user and ask how to proceed. Never stash or discard their work. |
| Directory exists and is not a CARE checkout | Ask the user for a different `$WORKSPACE`. |

> The backend repo is named `care` upstream; some machines name the directory `care_be`.
> Same thing. Refer to it as `$CARE_BE` from here on, `$CARE_FE` for the frontend.

### 1.2 Record the paths

Write `$WORKSPACE/.agent/paths.env`:

```bash
CARE_BE=/abs/path/to/care
CARE_FE=/abs/path/to/care_fe
PLUGIN_BE=/abs/path/to/care_<name>
PLUGIN_FE=/abs/path/to/care_<name>_fe
```

**Check — hard gate:**

```bash
test -f "$CARE_BE/plug_config.py"       || echo "FAIL: backend core not cloned"
test -f "$CARE_FE/src/pluginTypes.ts"   || echo "FAIL: frontend core not cloned"
```

Both must pass. If either fails, stop and fix it. Do not continue to any later phase.

---

## Phase 2 — Backend up (mandatory)

You are starting the backend. Say so first, naming the port:

> Starting the CARE backend on **http://localhost:9000** via Docker compose, plus Postgres and
> Redis containers.

### 2.0 Check the port is free

This is a collision check, **not** an excuse to skip the phase.

```bash
lsof -nP -iTCP:9000 -sTCP:LISTEN
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Ports}}'
```

- **Port free** → proceed to 2.1.
- **Port busy** → tell the user exactly what is holding it and ask whether to stop it or to run
  CARE on a different port. Never kill a process you did not start, and never assume the thing on
  :9000 is the CARE you want.

Pick a mode — `docker` (default) or `venv` — and record it in `.agent/paths.env` as
`CARE_BE_MODE`. Every later phase must respect it. **Mixing modes corrupts state**: a venv
`manage.py` run against the Docker Postgres uses different ports and settings and produces
migration errors that look like code bugs.

Once containers are up, read the **real** ports from `docker ps` rather than assuming defaults —
a typical CARE compose file exposes Postgres on **5433** and Redis on **6380** to avoid
colliding with host installs. Report the actual mapping to the user.

### 2.1 Start it

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

### 2.2 Migrate and seed

Run these every time, even if you suspect the database is already migrated. Both commands are
idempotent.

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

**Check — hard gate:** `curl -s http://localhost:9000/api/v1/plug_config/ | head -c 200` returns
JSON (401 is fine — it means the server is up). If it does not, the backend is not running and
you may not continue.

---

## Phase 3 — Frontend up (mandatory)

Announce it:

> Installing `care_fe` dependencies and starting the host dev server on **http://localhost:4000**,
> pointed at the backend on :9000.

### 3.0 Check the port is free

```bash
lsof -nP -iTCP:4000 -sTCP:LISTEN
```

If :4000 is taken, tell the user what holds it and agree on a resolution before starting. Do not
let Vite silently fall through to 4001 — the plugin's `REACT_ENABLED_APPS` will not match the tab
you are looking at, and you will debug the wrong instance for an hour.

### 3.1 Start it

```bash
cd "$CARE_FE"
npm install --ignore-scripts && npm run postinstall
grep -q REACT_CARE_API_URL .env.local 2>/dev/null \
  || printf 'REACT_CARE_API_URL=http://127.0.0.1:9000\n' >> .env.local
npm run dev     # http://localhost:4000
```

**Check — hard gate:** the login page renders at http://localhost:4000 and you can sign in as
`care-admin` / `Ohcn@123`. Verify it; do not assume it.

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

## Phase 4.5 — Read core before you design anything (mandatory)

A running stack is not context. You must actually read core, because the plugin's entire surface
is defined by it. Skipping this is what produces invented model fields, invented extension points
and invented API shapes.

Tell the user: *"Reading core to ground the design — plugin registration, plugin types, extension
points, auth, and the EMR models this feature touches."*

Read, in `$CARE_BE`:

| File / area | What you are extracting |
| --- | --- |
| `plug_config.py` + `plugs/manager.py` | How a `Plug` is declared, installed and configured. |
| `install_plugins.py` | When plugin installation actually happens (build time vs. run time). |
| `config/settings/base.py`, `config/urls.py` | Settings layering, how plugin URLs get mounted. |
| `care/emr/models/` | The **real** fields of the models you will relate to. Never guess a field name. |
| `care/emr/resources/` | The EMR resource/spec pattern that plugin serializers should mirror. |
| `care/security/` + `care/emr/api/` permissions | Permission and role plumbing you must reuse, not reinvent. |

Read, in `$CARE_FE`:

| File / area | What you are extracting |
| --- | --- |
| `src/pluginTypes.ts` | The exact shape of a plugin manifest: `routes`, `components`, `navItems`, etc. |
| `src/PluginEngine.tsx` + plugin registry/loader | How remotes are loaded and where failures surface. |
| The extension-point call sites | The real names of the extension points you may attach to. |
| `src/Utils/request/` | The request/API conventions your plugin client must match. |
| The auth user hook + patient-portal routes | Staff JWT vs. OTP auth boundaries. |
| Tailwind config / `src/style/` | The palette and tokens `care-design-system` expects you to reproduce. |

File paths drift between CARE releases. If one of the above is not where this table says, **find
it** — `grep` for the symbol — and record the real path. Do not skip the row.

Write what you found to `$WORKSPACE/.agent/core-notes.md`, with **file paths and line references**,
under these headings:

```markdown
# Core notes
## Plugin registration (backend)       — how plug_config.py + install_plugins.py work here
## Plugin manifest contract (frontend) — verbatim type from pluginTypes.ts
## Extension points available          — name → file:line → props it receives
## Core models this feature touches    — model → real field names → where defined
## Auth & permissions                  — which classes/hooks this plugin must use
## Open questions for the user
```

**Check — hard gate:** `.agent/core-notes.md` exists, every extension point listed cites a real
`file:line` in `$CARE_FE`, and every core model field listed was copied from a real model file.
If you cannot cite it, you do not know it — go read it. **Do not enter Phase 5 until this file is
written.**

---

## Phase 5 — Scaffold the plugin

> **Gate.** Do not start this phase unless all four are true: `$CARE_BE` and `$CARE_FE` are
> cloned, :9000 answers, :4000 renders the login page, and `.agent/core-notes.md` is written.
> If any is false, go back — do not compensate by guessing.

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

Tell the user you are starting the plugin preview server and on which port, then start it after
checking the port is free:

```bash
lsof -nP -iTCP:4173 -sTCP:LISTEN     # if taken, pick another port and update vite.config.ts
cd "$PLUGIN_FE" && npm install && npm run dev    # vite preview :4173 + vite build --watch
```

Restart the `care_fe` dev server you started in Phase 3 so it picks up `.env.local` — restart that
one, do not start a second.

**Check:** browser console shows no `There was an error enabling the app care_connect_fe`, and
`window.__CARE_PLUGIN_RUNTIME__.meta` contains your slug.

### 6.3 Extension points — only if needed

If your UI has nowhere to attach, add a new extension point to core. Load the
`care-extension-points` skill and follow its "Adding a new extension point" procedure exactly.
Keep the change generic and plugin-agnostic; it is a PR to core and will be reviewed as such.

Track every core file you touch in `$WORKSPACE/.agent/core-diff.md`. The list should stay short.

---

## Phase 7 — Build the feature

Now, and only now, implement what the user described in Phase 0. Keep `.agent/core-notes.md` open
alongside `.agent/plugin-brief.md`: every core symbol you reference must appear in the notes, or
you go back to core and read it before using it.

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
