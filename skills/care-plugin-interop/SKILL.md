---
name: care-plugin-interop
description: How one CARE plugin integrates with another without a hard dependency — optional Django app detection, window-based registry bridges (e.g. care_notifications_fe notification handlers), structural type mirroring across federation boundaries, and i18n label resolution across plugin namespaces. Use when a plugin should send notifications, extend another plugin's UI, or degrade gracefully when a companion plugin is absent.
---

# Cross-Plugin Integration

Plugins must not hard-depend on each other. A deployment may enable any subset. The rule:

> **Detect, don't require.** Integration code is a no-op when the companion plugin is absent,
> and never raises at import time.

## Backend: optional Django app detection

Put every integration behind an `is_enabled()` guard in a dedicated module
(`care_<name>/integrations/<other>.py`):

```python
from django.apps import apps
from care_connect.settings import plugin_settings

def is_enabled() -> bool:
    return bool(plugin_settings.CONNECT_NOTIFY_ENABLED) and apps.is_installed("care_notifications")

def notify_invite(session, recipient) -> bool:
    if not is_enabled():
        return False
    from care_notifications.api import create_notification   # import INSIDE the function
    create_notification(
        recipient=recipient,
        resource_type="tele_session",
        resource_id=str(session.external_id),
        ...
    )
    return True
```

Rules:

- Import the other plugin **inside the function**, never at module top level — a top-level import
  crashes the whole app when the companion is not installed.
- Expose a settings flag (`<PREFIX>_NOTIFY_ENABLED`) so operators can turn it off.
- Return a boolean so callers/tests can assert whether it actually fired.
- Fan out through a celery task (`notify_x.delay(...)`) so a slow companion never blocks the
  request. Remember: **the celery container needs its own editable install** (see
  `care-backend-plugin`).

## Frontend: window-registry bridges

Federated plugins are separate bundles and cannot import each other. The interop mechanism is a
**global array/object on `window`**, published by the host plugin and pushed to by consumers.

Example — registering a notification handler with `care_notifications_fe`:

```tsx
// src/utils/notificationHandler.tsx

// Separate bundles ⇒ cannot import the real types. Mirror only what we use.
interface NotificationHandler {
  resourceType: string;
  label: string;
  icon?: React.ReactNode;
  path?: (n: { resource_id: string }) => string;
  onClick?: (n: { resource_id: string }) => void;
}

declare global {
  interface Window {
    __CARE_NOTIFICATION_HANDLERS__?: NotificationHandler[];
  }
}

export function registerTeleSessionNotificationHandler() {
  (window.__CARE_NOTIFICATION_HANDLERS__ ??= []).push({
    resourceType: "tele_session",
    label: "connect__tele_session",
    path: (n) => `/connect/session/${n.resource_id}`,
  });
}
```

```tsx
// src/manifest.tsx — the ONLY module federation exposes, so the only guaranteed load-time hook
import { registerTeleSessionNotificationHandler } from "./utils/notificationHandler";

registerTeleSessionNotificationHandler();
```

Key points:

- **`manifest.tsx` is your only reliable entrypoint.** Side-effectful registrations go at its top
  level. Anything in another module runs only if something imports it.
- `??= []` — you may load before or after the plugin that owns the registry. Never assume it
  exists; never overwrite it.
- **Structural type mirrors, not imports.** Declare a local interface with just the fields you
  use. TypeScript `Window` augmentation is per-compilation, so two plugins declaring the same
  global do not conflict.
- Keep the registration cheap. It runs on every page load of `care_fe`; do not pull in an SDK.

## i18n across plugin boundaries

The consumer plugin renders your label with a bare `t(label)` and **no namespace**. Resolution
works because `care_fe/src/i18n.ts` sets `fallbackNS` to the list of all loaded plugin namespaces.

Therefore:

- The label key must be defined in **your own** `public/locale/en.json`, not in the consumer's
  and not in `care_fe`'s.
- It must be prefixed with your plugin's convention (`connect__tele_session`) so it cannot
  collide with another plugin's key.

Symptom of getting this wrong: the UI renders the raw resource type (`tele_session`) instead of a
friendly label. That means the key was not found in any loaded namespace.

## Designing your own registry (when you're the host plugin)

If other plugins should extend *you*:

1. Publish `window.__CARE_<NAME>_<THING>__` as an array, initialised with `??= []`.
2. Read it lazily at render time, not once at module scope — consumers may register later.
3. Document the entry shape in your README, including which fields are required.
4. Never break the shape; only add optional fields.

## Checklist

- [ ] No top-level import of another plugin, on either side.
- [ ] Backend integration guarded by `apps.is_installed(...)` **and** a settings flag.
- [ ] Frontend registration happens at the top of `manifest.tsx`.
- [ ] Registry writes use `??= []` and `push`, never assignment.
- [ ] Types are locally-declared structural mirrors.
- [ ] Labels are prefixed keys defined in the *owning* plugin's `en.json`.
- [ ] Tested with the companion plugin **disabled** — nothing crashes, nothing is logged as an error.
