---
name: care-plugin-verification
description: Running, testing and debugging a CARE plugin end to end — dev server topology and ports, Playwright/DB-snapshot workflow, and a symptom-to-cause table for the failure modes that waste the most time (stale celery plugin installs, silent federation load failures, raw i18n keys, 500s disguised as CORS errors, WebRTC/ICE issues). Use when the plugin does not work and you need to find out why.
---

# Verifying & Debugging a CARE Plugin

## Isolated dev topology

Run `bootstrap.prompt.md` first. `$WORKSPACE` defaults to the scaffold checkout itself. Bootstrap
clones missing independent cores at `$WORKSPACE/care` and `$WORKSPACE/care_fe`, preserving existing
repositories, and saves this workspace's ports in `care-scaffold.env`. Plugins have separate Git
roots at `$WORKSPACE/care/care_<name>` and `$WORKSPACE/care_<name>_fe`.
Load that file before using the commands below:

```bash
source "$WORKSPACE/care-scaffold.env"
source "$WORKSPACE/.agent/paths.env"
```

| Process | Command | Saved host port |
| --- | --- | --- |
| Backend and dependencies | `"$WORKSPACE/.agent/compose.sh" up -d --wait --build` | `CARE_API_PORT` |
| Frontend host | `"$WORKSPACE/.agent/frontend.sh"` | `CARE_FE_PORT` |
| Plugin frontend (inside its repo) | `npm run dev` | `PLUGIN_PORT`, written to `vite.config.ts` |
| PostgreSQL / Redis | Started by the Compose wrapper | `CARE_DB_PORT` / `CARE_REDIS_PORT` |
| S3 / S3 console / debugger | Started by the Compose wrapper | `CARE_S3_PORT` / `CARE_S3_CONSOLE_PORT` / `CARE_DEBUG_PORT` |

Always use the generated Compose wrapper for backend operations: it supplies the isolated
project and port overrides. Do not adopt another checkout's containers or frontend server.
Inspect a listener's command and working directory before deciding it belongs to this workspace:

```bash
"$WORKSPACE/.agent/compose.sh" ps
lsof -nP -iTCP:"$CARE_API_PORT" -sTCP:LISTEN
lsof -nP -iTCP:"$CARE_FE_PORT" -sTCP:LISTEN
lsof -nP -iTCP:"$PLUGIN_PORT" -sTCP:LISTEN
```

To check saved ports before a cold start, with this workspace's services stopped, run
`python3 <scaffold>/scripts/configure-workspace.py --workspace "$WORKSPACE" --check-ports`.
This checks availability without changing files. Saved ports stay the same on reruns.
If an unrelated process has taken a saved port, stop and resolve the conflict explicitly; do not
kill that process, adopt it, or let Vite increment the port. `strictPort: true` makes both frontend servers fail instead of silently drifting.

The external host launcher supplies the saved `CARE_API_URL` as `REACT_CARE_API_URL`.
`$WORKSPACE/.agent/frontend.env` must contain the plugin entry `ohcnetwork/care_connect_fe@localhost:<PLUGIN_PORT>/assets/remoteEntry.js`, with
`<PLUGIN_PORT>` replaced by its saved number. Additional plugins each need a separately checked,
recorded port.

Two things that are **not** hot-reloaded: the host process environment and the federated remote bundle.
Restart this workspace's `care_fe` for the former; hard-reload the browser after every plugin
rebuild for the latter.

## Fast sanity ladder

Run these in order; the first failure tells you which layer is broken.

```bash
# 1. Backend alive
curl -s -o /dev/null -w '%{http_code}\n' "$CARE_API_URL/api/v1/plug_config/"

# 2. Plugin mounted in the URL tree
curl -s -o /dev/null -w '%{http_code}\n' "$CARE_API_URL/api/care_connect/config/"   # not 404

# 3. Plugin installed in BOTH containers
"$WORKSPACE/.agent/compose.sh" exec backend pip show care_connect
"$WORKSPACE/.agent/compose.sh" exec celery pip show care_connect   # check Editable project location: /plugins/care_connect

# 4. Remote bundle served
curl -s -o /dev/null -w '%{http_code}\n' "http://127.0.0.1:$PLUGIN_PORT/assets/remoteEntry.js"

# 5. Host loaded it — in the browser console
window.__CARE_PLUGIN_RUNTIME__.meta
```

## Playwright

Use only this workspace's backend, frontend and database. Before running any Playwright command,
inspect `$CARE_FE/playwright.config.ts`, `tests/globalSetup`, the DB helpers and npm scripts.
Upstream versions can hardcode frontend port 4000, default DB port 5432, automatically restore a
database in global setup, or run reset commands through a host venv. Merely exporting
`CARE_BACKEND_DIR` or `CARE_API_URL` does not override those implementations.

Keep plugin tests and their configuration in the plugin repository or `.agent/`. Never edit core
test settings or run core autofix commands. Configure the independent test runner as follows:

- Set the test base URL, web-server URL and strict preview port to the saved `CARE_FE_URL` and
  `CARE_FE_PORT`; point auth/API helpers at `CARE_API_URL`.
- Check every DB reset/snapshot/restore target against this workspace's `CARE_DB_PORT`, database
  and credentials. Use a workspace-specific snapshot path. Route Django migrations and fixture
  loading through `"$WORKSPACE/.agent/compose.sh" exec backend python manage.py ...`.
- Inspect global setup's automatic restore before enabling it. Do not run stock DB scripts until
  their configured targets are verified; they can overwrite another running stack's data.
- Add the plugin's saved endpoint to `REACT_ENABLED_APPS` before building the host.

Then install Playwright in the plugin, build the host with external environment configuration
if needed, and run the plugin specs. Do not invoke unsafe stock core setup scripts.
Use unique test data and restore only this workspace's verified snapshot between runs.
**`$CARE_FE/tests/PLAYWRIGHT_GUIDE.md`** contains the selector and assertion patterns; read it
before writing a test.

## Symptom → cause

### "My backend change had no effect" / "celery runs old code"

The external Compose override mounts the plugin at `/plugins/care_connect` and installs it in
editable mode at startup in **both** services. Verify the actual rendered configuration:

```bash
"$WORKSPACE/.agent/compose.sh" config
"$WORKSPACE/.agent/compose.sh" exec backend python -c "import care_connect; print(care_connect.__file__)"
"$WORKSPACE/.agent/compose.sh" exec celery pip show care_connect
```

The import and editable project location must refer to the mounted plugin, not a stale installed
copy. Core's installer uses ordinary pip installation; do not run it as an editable-install fix.
Celery only watches `/app`, so restart it after changes under `/plugins`. Restart both services
after plugin metadata/dependency changes so their startup installs run again. Recreate services
with `compose.sh up -d --wait` after changing the external Compose configuration.

### "The plugin just isn't there — no error, no component"

Federation failures are caught and logged, then skipped. Check the console for
`There was an error enabling the app <slug>`. Then:

- Is `REACT_ENABLED_APPS` set, and was `care_fe` restarted after editing `.agent/frontend.env`?
- Is the plugin preview server running and serving `dist/assets/remoteEntry.js`?
- Did you hard-reload after the plugin rebuilt?
- Does `manifest.components` actually contain the extension-point key, spelled exactly as in
  `SupportedPluginComponents`?

### "404s for the plugin's lazy chunks against the frontend host"

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
`curl "http://127.0.0.1:$PLUGIN_PORT/locale/en.json"`.

### "Staff sees no data / no action button, but the doctor does"

The staff queryset falls back to "sessions I participate in" unless the client passes
`facility=<id>`. Add it. Conversely, OTP callers must **not** send `facility`.

### "Plugin CSS is missing"

`cssCodeSplit: false` and remote CSS is not auto-injected. Third-party packages that ship their
own CSS will not style anything. Inline the styles or drop the dependency.

### "An independent plugin isn't discovered automatically"

This workflow keeps frontend plugins at `$WORKSPACE/care_<name>_fe`, outside `care_fe/`.
Register the federated preview explicitly
through `REACT_ENABLED_APPS` in `.agent/frontend.env`, then restart `.agent/frontend.sh`.
Do not copy or symlink the plugin into `care_fe/apps/` to use core's local auto-discovery.

### WebRTC / LiveKit: "ICE failed, add a TURN server"

`rtc.node_ip: 127.0.0.1` only works if the browser offers host candidates. With a VPN (Cloudflare
WARP) or Firefox's mDNS obfuscation, the browser offers only public `srflx` candidates, which can
never pair with loopback.

```bash
# use the machine's LAN IP; VPNs exclude RFC1918 by default
ipconfig getifaddr $(route -n get default | awk '/interface/{print $2}')
```

Firefox additionally needs `media.peerconnection.ice.obfuscate_host_addresses=false`.
Inspect this workspace's LiveKit container logs for `ICE candidate pair stats` and
`responsesReceived: 0`; identify the container from its recorded service configuration.

## General debugging discipline

- **Re-check values programmatically.** Do not diagnose from wrapped/truncated terminal output;
  it is easy to misread two similar UUIDs as equal.
- **Verify the API with `curl` before blaming React.**
- **Read the backend log** whenever the browser reports something structural (CORS, network).
- **One change at a time**, then re-run the sanity ladder.

## Pre-PR checks

```bash
(cd "$PLUGIN_FE" && npm run build)
git -C "$CARE_BE" diff --exit-code
git -C "$CARE_BE" diff --cached --exit-code
git -C "$CARE_FE" diff --exit-code
git -C "$CARE_FE" diff --cached --exit-code
"$WORKSPACE/.agent/compose.sh" exec backend python manage.py makemigrations --check --dry-run
```

- [ ] Both core checkouts retain their starting revisions and tracked state.
- [ ] Scaffold status excludes core/plugin paths and generated local files; its index contains no
  core/plugin code or gitlinks. Source `skills/` and `templates/` remain trackable.
- [ ] Each plugin resolves to its own Git root, and core locally excludes the nested backend plugin.
- [ ] Tested as staff and (if relevant) as an OTP patient.
- [ ] Tested with companion plugins disabled.
- [ ] No secrets in any committed file; all local runtime configuration is external to core.
