---
name: care-plugin-verification
description: Running, testing and debugging a CARE plugin end to end — dev server topology and ports, Playwright/DB-snapshot workflow, and a symptom-to-cause table for the failure modes that waste the most time (stale celery plugin installs, silent federation load failures, raw i18n keys, 500s disguised as CORS errors, WebRTC/ICE issues). Use when the plugin does not work and you need to find out why.
---

# Verifying & Debugging a CARE Plugin

## Dev topology

| Process | Command | Port |
| --- | --- | --- |
| Backend (Docker) | `make up` in `care` | 9000 |
| Backend (venv) | `manage.py runserver 0.0.0.0:9000` | 9000 |
| Frontend host | `npm run dev` in `care_fe` | 4000 |
| Plugin frontend | `npm run dev` in `care_<name>_fe` (`vite preview & vite build --watch`) | 4173 (next plugin: 10125, …) |

## Adopt what is running — never start a duplicate

Before starting anything, find out what already exists:

```bash
docker compose ls                                   # running compose projects
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Ports}}'
lsof -nP -iTCP:9000 -sTCP:LISTEN                    # backend
lsof -nP -iTCP:4000 -sTCP:LISTEN                    # care_fe host
lsof -nP -iTCP:4173 -sTCP:LISTEN                    # plugin preview
```

- **A compose project is up** → use it. Do not `make up` a second stack, and do not start a venv
  backend beside it.
- **Port 4000 is taken** → use that server. A second `vite` silently binds **4001**, so you end up
  reading a browser tab whose `REACT_ENABLED_APPS` differs from the one you just edited.
- **Port 4173 is taken** → another plugin owns it. Choose a different `preview.port` rather than
  killing theirs.
- Never mix Docker and venv backends against the same database. Ports and settings differ and you
  get migration errors that look like code bugs.
- Do **not** kill a process you did not start without asking.

Read real ports from `docker ps` rather than assuming defaults — a typical local CARE stack
exposes Postgres on **5433** and Redis on **6380** to avoid colliding with host installs.

`care_fe/.env.local`:

```
REACT_CARE_API_URL=http://127.0.0.1:9000
REACT_ENABLED_APPS=ohcnetwork/care_connect_fe@localhost:4173/assets/remoteEntry.js,ohcnetwork/care_notifications_fe@localhost:10125/assets/remoteEntry.js
```

Two things that are **not** hot-reloaded: `.env.local`, and the federated remote bundle.
Restart `care_fe` for the former; hard-reload the browser after every plugin rebuild for the latter.

## Fast sanity ladder

Run these in order; the first failure tells you which layer is broken.

```bash
# 1. Backend alive
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:9000/api/v1/plug_config/

# 2. Plugin mounted in the URL tree
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:9000/api/care_connect/config/   # not 404

# 3. Plugin installed in BOTH containers
docker exec care_be-backend-1 pip show care_connect | head -2
docker exec care_be-celery-1  pip show care_connect | head -2   # want 0.1.0-0.editable

# 4. Remote bundle served
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:4173/assets/remoteEntry.js

# 5. Host loaded it — in the browser console
window.__CARE_PLUGIN_RUNTIME__.meta
```

## Playwright

Requires the backend on :9000 and a production build of `care_fe`.

```bash
npm run playwright:install
npm run build
npm run playwright:test -- tests/path/to/spec.ts
npm run playwright:test -- --workers=4
npm run playwright:test:ui
```

Tests create data that collides on re-run. Use the DB snapshot system:

```bash
export CARE_BACKEND_DIR=/path/to/care
npm run playwright:db-reset      # migrate + fixtures + snapshot (first time, ~30s)
npm run playwright:db-restore    # before re-runs (~2s)
npm run playwright:db-snapshot   # save current state as the new baseline
npm run playwright:db-status
```

`globalSetup` auto-restores locally (not on CI). Write tests with `faker` / `Date.now()` for
unique data; don't rely on cleanup. **`care_fe/tests/PLAYWRIGHT_GUIDE.md`** — in the host
checkout, not in this scaffold — has the complete selector, form-interaction and assertion
patterns. Read it before writing a test.

For plugin tests, add the plugin to `REACT_ENABLED_APPS` so it is a build-time plugin and always
present during the run.

## Symptom → cause

### "My backend change had no effect" / "celery runs old code"

Plugins are pip-installed **at image build time** (`dev.Dockerfile` runs `install_plugins.py` into
`/.venv`, which is baked into the image — only the source tree is bind-mounted). A newly
registered or newly renamed plug does not exist in a running container until you rebuild:

```bash
cd "$CARE_BE"
make down && make build && make up     # NOT `make teardown` — that deletes the database volume
```

If you previously used `docker exec … install_plugins.py` as a shortcut, remember it writes to a
single container's writable layer, not the shared `care_local` image — so it must be run against
**both** `backend` and `celery`, and it is discarded whenever a container is recreated. That is
the usual reason one service behaves correctly and the other silently runs stale code with no
import error.

```bash
docker exec <container> python -c "import care_connect; print(care_connect.__file__)"
docker exec <container> pip show care_connect
```

Also check the plugin is a **real directory** inside `$CARE_BE`, not a symlink — `COPY . /app`
cannot follow a symlink out of the build context, so the image gets an empty plugin.

### "The plugin just isn't there — no error, no component"

Federation failures are caught and logged, then skipped. Check the console for
`There was an error enabling the app <slug>`. Then:

- Is `REACT_ENABLED_APPS` set, and was `care_fe` restarted after editing `.env.local`?
- Is the plugin preview server running and serving `dist/assets/remoteEntry.js`?
- Did you hard-reload after the plugin rebuilt?
- Does `manifest.components` actually contain the extension-point key, spelled exactly as in
  `SupportedPluginComponents`?

### "404s for the plugin's lazy chunks against localhost:4000"

Federation retries against the plugin origin after failing on the host origin. **Harmless noise.**

### "CORS error" on a request that should work

Very often a **500** in disguise: a Django 500 response carries no CORS headers, so the browser
reports it as CORS. Check the backend logs, not the browser.

The classic cause: a serializer field backed by a core model's `meta` JSON that is not
`write_only=True`, so DRF's `to_representation` raises `AttributeError`.

### "The UI shows a raw key like `tele_session` instead of a label"

i18n key not found in any loaded namespace. The key must live in the **owning plugin's**
`public/locale/en.json`, prefixed (`connect__…`), and resolution relies on `fallbackNS` in
`care_fe/src/i18n.ts`. Verify the plugin's locale file is actually served:
`curl http://localhost:4173/locale/en.json`.

### "Staff sees no data / no action button, but the doctor does"

The staff queryset falls back to "sessions I participate in" unless the client passes
`facility=<id>`. Add it. Conversely, OTP callers must **not** send `facility`.

### "Plugin CSS is missing"

`cssCodeSplit: false` and remote CSS is not auto-injected. Third-party packages that ship their
own CSS will not style anything. Inline the styles or drop the dependency.

### "Local plugin under `apps/` isn't discovered"

Auto-discovery uses `Dirent.isDirectory()` — **symlinks do not work**. Use a real directory.

### WebRTC / LiveKit: "ICE failed, add a TURN server"

`rtc.node_ip: 127.0.0.1` only works if the browser offers host candidates. With a VPN (Cloudflare
WARP) or Firefox's mDNS obfuscation, the browser offers only public `srflx` candidates, which can
never pair with loopback.

```bash
# use the machine's LAN IP; VPNs exclude RFC1918 by default
ipconfig getifaddr $(route -n get default | awk '/interface/{print $2}')
```

Firefox additionally needs `media.peerconnection.ice.obfuscate_host_addresses=false`.
Diagnose with `docker logs care-livekit | grep -A2 'ICE candidate pair stats'` — look for
`responsesReceived: 0`.

## General debugging discipline

- **Re-check values programmatically.** Do not diagnose from wrapped/truncated terminal output;
  it is easy to misread two similar UUIDs as equal.
- **Verify the API with `curl` before blaming React.**
- **Read the backend log** whenever the browser reports something structural (CORS, network).
- **One change at a time**, then re-run the sanity ladder.

## Pre-PR checks

```bash
cd care_fe        && npx tsc --noEmit && npm run lint-fix && npm run format
cd care_<name>_fe && npm run build
cd care           && make checkmigration          # makemigrations --check --dry-run
```

- [ ] `.agent/core-diff.md` reviewed; every core file justified in one line.
- [ ] Tested as staff and (if relevant) as an OTP patient.
- [ ] Tested with companion plugins disabled.
- [ ] No secrets in `plug_config.py` or any committed file.
