---
name: care-frontend-plugin
description: How to build the React side of a CARE plugin — Vite Module Federation config, the manifest.tsx contract, REACT_ENABLED_APPS wiring, the window globals a plugin may use, the API client pattern, i18n namespacing via fallbackNS, Tailwind scoping, and bundle/CSS constraints. Use when creating or modifying a care_<name>_fe plugin.
---

# CARE Frontend Plugin (Module Federation)

`care_fe` loads plugins at **runtime** as federated remotes. Your plugin is a separate repo, a
separate build, and a separate bundle. It shares React with the host, so it renders inside the
host's provider tree and can use host context.

## The loading pipeline (src/PluginEngine.tsx)

1. Host fetches `GET /api/v1/plug_config/` → API-managed plugins.
2. Host merges that with build-time plugins parsed from `REACT_ENABLED_APPS` (`care.config.ts` →
   `careConfig.careApps`, normalised by `src/Utils/plugConfig.ts`). Build-time wins on conflicts
   and is marked read-only.
3. For each config, host calls `setFederationRemote(slug, { url, format: "esm", from: "vite" })`.
4. Host loads `./manifest` from the remote and unwraps the default export.
5. Manifest + `config.meta` are exposed on `window.__CARE_PLUGIN_RUNTIME__.meta` and via
   `CareAppsContext` / `useCareApps()`.
6. `PLUGIN_Component` renders your components by looking up `manifest.components[__name]`.

Failures are logged and skipped — a broken plugin never takes down the app, which also means a
broken plugin fails **silently in the UI**. Always check the console.

## vite.config.ts

```ts
import federation from "@originjs/vite-plugin-federation";

export default defineConfig({
  plugins: [
    federation({
      name: "care_connect",                       // internal federation name
      filename: "remoteEntry.js",
      exposes: { "./manifest": "./src/manifest.tsx" },   // the ONLY export
      shared: ["react", "react-dom", "react-i18next"],
    }),
    tailwindcss(),
    react(),
  ],
  build: {
    target: "esnext",
    cssCodeSplit: false,                          // remote CSS is not auto-injected
    modulePreload: { polyfill: false },
    rollupOptions: { input: { main: "./index.html" }, output: { format: "esm" } },
  },
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  preview: { port: 4173, host: "0.0.0.0", cors: true, allowedHosts: true },
});
```

`package.json` dev script: `"dev": "vite preview & vite build --watch"` — preview serves
`dist/assets/remoteEntry.js`; the watch build keeps it fresh. **There is no HMR across the
federation boundary**: after a plugin rebuild you must hard-reload `care_fe`.

React/react-dom belong in `peerDependencies`, not `dependencies`.

## Enabling it in the host

`care_fe/.env.local`:

```
REACT_ENABLED_APPS=ohcnetwork/care_connect_fe@localhost:4173/assets/remoteEntry.js
```

Format: `org/repo` or `org/repo@host/path/to/remoteEntry.js`, comma-separated for several plugins.

- No `@host` ⇒ defaults to GitHub Pages `https://{org}.github.io/{repo}`.
- Host containing `localhost` ⇒ prefixed `http://`; anything else ⇒ `https://`.
- The resolved **slug** is the repo name (`care_connect_fe`) — that is what appears in
  `window.__CARE_PLUGIN_RUNTIME__.meta`.

`.env.local` is **not** hot-reloaded. Restart `npm run dev` after editing it.

### Preview port allocation

Each plugin needs its own `preview.port`, hardcoded in its `vite.config.ts`, because several
plugins run side by side against one host. There is no registry — pick an unused port and record
it in the plugin's README. Ports already in use by known plugins:

| Port | Plugin |
| --- | --- |
| 4173 | first/default plugin (`care_hello_fe`, `care_connect_fe`) |
| 10120 | `care_teleicu_devices_fe` |
| 10125 | `care_notifications_fe` |

If two plugins share a port, the second `vite preview` fails to bind and the host silently skips
that plugin.

Alternative for host-side development: drop the plugin under `care_fe/apps/<name>/` with a
`src/manifest.tsx`; in dev mode the host auto-discovers it and loads it through its own Vite graph
(real HMR). Note: auto-discovery uses `Dirent.isDirectory()`, so **symlinks into `apps/` do not
work** — you need a real directory.

## manifest.tsx — the contract

This is the only module federation exposes, so it is also your **only guaranteed load-time hook**
(use it for side-effectful registrations, see `care-plugin-interop`).

```tsx
import { lazy } from "react";

const manifest = {
  plugin: "care_connect_fe",
  routes: {
    "/connect/session/:sessionId": ({ sessionId }) => (
      <Page><CallSession sessionId={sessionId} /></Page>
    ),
  },
  extends: [],
  components: {
    AppointmentActions: lazy(() => import("./components/AppointmentActions")),
    AppShellOverlay:    lazy(() => import("./components/AppShellOverlay")),
  },
  navItems: [], userNavItems: [], adminNavItems: [],
};

export default manifest;
```

Full shape (`care_fe/src/pluginTypes.ts` → `PluginManifest`):

| Key | Type | Purpose |
| --- | --- | --- |
| `plugin` | `string` | Plugin identifier. |
| `routes` | `AppRoutes` | Full pages, injected into the host router. **Zero core changes.** |
| `components` | `PluginComponentMap` | Extension-point implementations. Must be `lazy()`. |
| `navItems` / `userNavItems` / `adminNavItems` / `billingNavItems` | `NavigationLink[]` | Sidebar entries. |
| `organizationTabs` | `PluginOrganizationTab[]` | Extra org tabs. |
| `encounterTabs` / `encounterFileTabs` | `Record<string, Lazy<FC>>` | Extra encounter tabs. |
| `devices` | `PluginDeviceManifest[]` | Device type integrations (icon, configure form, cards). |
| `overrides` | `PluginOverride[]` | Replace a registered core component conditionally. |
| `extends` | `readonly ("DoctorConnectButtons" \| "PatientExternalRegistration")[]` | Legacy extension flags. |

**You cannot import `care_fe` types** — separate builds. Declare a minimal *structural mirror* of
the props you need locally in your manifest. Keep it narrow: only the fields you actually read.

`routes` is the cheapest surface in the system: a whole page with no core diff at all. Prefer it.

## Window globals (set by the host in `src/index.tsx`)

| Global | Use |
| --- | --- |
| `window.CARE_API_URL` | Backend base URL. Build all requests from this. |
| `window.AuthUserContext` | The host's auth React context object. `React.useContext(window.AuthUserContext)` gives `user`, `signIn`, `signOut` — works because React is shared and your tree renders inside the host's provider. |
| `window.__CORE_ENV__` | The full `careConfig` (feature flags, locale settings). |
| `window.__CARE_PLUGIN_RUNTIME__.meta` | Per-plugin runtime metadata from `plug_config`. Frozen. |

Declare them in your own `src/vite-env.d.ts` via `declare global { interface Window { … } }`.
Module augmentation is per-compilation, so this never conflicts with other plugins.

## API client

```ts
const BASE_PATH = "/api/care_connect";

function getAuthToken() {
  return localStorage.getItem("care_access_token") ?? getPatientToken();
}

async function request<T>(endpoint: string, method = "GET", body?, queryParams?): Promise<T> {
  const url = `${window.CARE_API_URL}${BASE_PATH}${endpoint}`;
  const res = await fetch(url, {
    method,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  // parse text-then-JSON so empty 204 bodies don't throw
  // throw a typed ApiError carrying status + parsed data on !res.ok
}
```

Use `@tanstack/react-query` on top for caching. Do **not** import the host's `query`/`mutate`
helpers — they are not exposed across federation.

See `care-auth-contexts` for the `/otp` prefix logic on the patient portal.

## i18n

- Your plugin serves its own `public/locale/en.json` from its own origin. The host's i18n backend
  fetches `{pluginBaseUrl}/locale/{lng}.json` and registers it as a namespace.
- Host `src/i18n.ts` sets `fallbackNS: pluginNamespaces`, so `t("connect__join_call")` with **no
  namespace prefix** resolves from whichever plugin defines it.
- **Prefix every key** with your plugin's short name (`connect__`, `scribe__`). This is the only
  thing preventing cross-plugin key collisions.
- Never add your keys to `care_fe/public/locale/en.json`. Never edit non-English locale files
  (Crowdin-managed).

## Styling constraints

> Full details — CARE's colour palette, shadcn/ui setup, icons, Radix portals — are in the
> **`care-design-system`** skill. Load it before writing any component. The essentials:

- `cssCodeSplit: false` and remote CSS is **not auto-injected**. Do not depend on third-party
  packages that ship their own CSS — it will not load.
- Your plugin is a **separate Tailwind build**. It inherits none of the host's theme; you must
  reproduce CARE's palette in your own `@theme` block.
- Scope your Tailwind under a container class so plugin styles cannot leak into the host:

```tsx
// components/Page.tsx
export default function Page({ children }: PropsWithChildren) {
  return <div className="care-connect-container" style={{ display: "contents" }}>{children}</div>;
}
```

  …with your Tailwind entry CSS scoped to `.care-connect-container`. Wrap every root your plugin
  renders (each extension-point component and each route).

## Bundle discipline

The manifest chunk loads on **every page load of care_fe**, for every user. Keep it tiny.

- `lazy()` every component in `components` and every page in `routes`.
- Keep heavy SDKs (LiveKit ≈ 600 kB, video/AI libs) out of anything the manifest imports eagerly.
- A side-effect registration at the top of `manifest.tsx` is fine; importing the library it
  registers is not.

## Checklist

- [ ] `npm run build` succeeds and `dist/assets/remoteEntry.js` exists.
- [ ] Console shows no "There was an error enabling the app …".
- [ ] Every extension-point component is `lazy()`.
- [ ] Every user-facing string is `t("<prefix>__key")` and defined in the plugin's `en.json`.
- [ ] Every rendered root is wrapped in the scoped container.
- [ ] No core `care_fe` file changed, except an extension point you deliberately added.
