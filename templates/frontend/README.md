# __PLUGIN_TITLE__ (frontend)

__PLUGIN_DESCRIPTION__

A [care_fe](https://github.com/ohcnetwork/care_fe) plugin, loaded at runtime through Vite
Module Federation. It is a separate build; it never imports from `care_fe`.

## Develop

```bash
npm install
npm run dev        # initial build, then preview :__PLUGIN_PORT__ + build watcher
```

Enable it in `care_fe/.env.local`:

```
REACT_ENABLED_APPS=ohcnetwork/__PLUGIN_FE__@localhost:__PLUGIN_PORT__/assets/remoteEntry.js
```

Then restart the `care_fe` dev server — `.env.local` is not hot-reloaded.

The preview binds only to localhost and requires port **__PLUGIN_PORT__**. If another
service takes that port, startup fails instead of silently changing the remote URL.
The standalone harness uses `__PLUGIN_API_URL__`; inside CARE the host supplies its API URL.

When generating into a configured workspace, `new-plugin.sh` reads `care-scaffold.env`
for its API URL and first plugin port. Later plugins receive another available port if
that port is already recorded in a sibling plugin. `--port` and `--api-url` override
these defaults; generated settings stay in this plugin until you edit them.

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
