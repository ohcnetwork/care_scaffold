# __PLUGIN_TITLE__ (frontend)

__PLUGIN_DESCRIPTION__

A [care_fe](https://github.com/ohcnetwork/care_fe) plugin, loaded at runtime through Vite
Module Federation. It is a separate build; it never imports from `care_fe`.
This directory is an independent Git repository, with no initial commit or remote.
Publish it as its own repo; never add it as a scaffold submodule. By default it lives at
`$WORKSPACE/__PLUGIN_FE__`, where `$WORKSPACE` is the scaffold checkout. The scaffold ignores
this directory; run Git commands in this repository to track and publish its source.

## Develop

```bash
npm install
npm run dev        # initial build, then preview :__PLUGIN_PORT__ + build watcher
```

After bootstrap Phase 6, enable it through the host process environment:

```bash
source "$WORKSPACE/care-scaffold.env"
cd "$CARE_FE"
REACT_ENABLED_APPS="ohcnetwork/__PLUGIN_FE__@localhost:__PLUGIN_PORT__/assets/remoteEntry.js" \
  REACT_CARE_API_URL="$CARE_API_URL" \
  npm run dev -- --host 127.0.0.1 --port "$CARE_FE_PORT" --strictPort
```

Preserve existing enabled plugins as a comma-separated list when restarting the host.
All implementation work belongs in this plugin repository. Do not edit either core checkout,
including `care_fe/.env.local`, routes, extension points, or locale files. If an existing
extension point cannot support the feature, document the blocker in a `care_scaffold` issue
and continue the supported plugin work. Template fixes belong in a separate `care_scaffold`
change.

The preview binds only to localhost and requires port **__PLUGIN_PORT__**. If another
service takes that port, startup fails instead of silently changing the remote URL.
The standalone harness uses `__PLUGIN_API_URL__`; inside CARE the host supplies its API URL.

When generating into a configured workspace, `new-plugin.sh` reads `care-scaffold.env`
for its API URL and first plugin port. Later plugins receive another available port if
that port is already recorded in another frontend plugin in the workspace. `--port` and
`--api-url` override these defaults; generated settings stay in this plugin until you edit them.

> There is no HMR across the federation boundary. After the plugin rebuilds, **hard-reload**
> `care_fe`.

## Structure

| Path | Purpose |
| --- | --- |
| `src/manifest.tsx` | The only module federation exposes. Routes, components, nav items, side-effect registrations. |
| `src/utils/api.ts` | Fetch client. Uses `window.CARE_API_URL` and the staff/OTP token, with the `/otp` prefix applied automatically. |
| `src/components/Page.tsx` | Tailwind scoping wrapper. Wrap every rendered root. |
| `public/locale/en.json` | i18n keys, all prefixed `__I18N_PREFIX__`. |

## Conventions

- Every entry in `components` and `routes` must be `lazy()` — the manifest chunk loads on
  every page of `care_fe`.
- Every user-facing string is `t("__I18N_PREFIX__key")`, defined in this repo's `en.json`.
  Never add keys to `care_fe`'s locale files.
- `cssCodeSplit: false` and remote CSS is not auto-injected: do not depend on packages that
  ship their own stylesheets.
- Prop types are structural mirrors of `care_fe/src/pluginTypes.ts`, never imports.
