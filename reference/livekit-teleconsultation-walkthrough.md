# Reference walkthrough — building the LiveKit teleconsultation plugin

This is the **acceptance test** for `care_scaffold`. It reconstructs `care_connect` /
`care_connect_fe` (video consultations for CARE, backed by LiveKit) from nothing, and records
exactly how much of core had to change: **five extension points and one type fix.**

Use it two ways:

- As a **worked example** an agent can pattern-match against for any new plugin.
- As **ground truth** to diff a fresh agent's output against when validating this repo.

---

## The brief

> Doctors and patients hold a video consultation attached to an existing appointment.
> Staff toggle "teleconsultation" on a schedule availability. Bookings against that availability
> automatically get a call session. Both parties see a Join button at the right time, patients
> included (they log in with OTP, not a password). A banner shows an in-progress call anywhere in
> the app. Missed calls and invites raise notifications, if the notifications plugin is installed.

---

## Step 1 — Decide what lives where

Run the decision tree from `care-plugin-architecture`:

| Requirement | Where it goes | Core cost |
| --- | --- | --- |
| "Is this availability teleconsultation-enabled?" | `Availability.meta["teleconsultation"]["enabled"]` | **0** — `meta` JSONField already exists |
| A call session (room name, participants, times, status) | New `TeleSession` model in the plugin, FK → `TokenBooking` | **0** |
| Auto-create a session when a booking is made | `post_save` signal on `TokenBooking` | **0** |
| LiveKit credentials | `PluginSettings` + `Plug(configs=…)` | **0** |
| Join/decline/invite/end APIs | Plugin viewsets under `/api/care_connect/` | **0** |
| Patient portal access | `otp/`-prefixed viewsets, phone-scoped | **0** |
| Buttons on appointment pages | Extension points | **small** |
| In-progress call banner | `AppShellOverlay` extension point | **small** |
| Full call page | `manifest.routes` → `/connect/session/:id` | **0** |

The only thing needing a new column would have been the availability flag — and `meta` removes
that need. **No core migration.**

---

## Step 2 — Backend

```
care_connect/care_connect/
├── apps.py            PLUGIN_NAME = "care_connect"; ready() → signals
├── settings.py        CONNECT_LIVEKIT_URL / _HOST / _API_KEY / _API_SECRET (required),
│                      CONNECT_JOIN_BUFFER_MINUTES=10, CONNECT_GRACE_MINUTES=15,
│                      CONNECT_TOKEN_TTL_MINUTES=60, CONNECT_NOTIFY_ENABLED=True, …
├── urls.py            router: sessions, availabilities, invites, otp/sessions,
│                      otp/availabilities  +  config/, otp/config/, livekit/webhook/
├── signals.py         post_save(TokenBooking) → create TeleSession if enabled
├── models/            TeleSession, participants, choices
├── serializers/       TeleSession, TeleAvailability (write_only flag!), base
├── viewsets/          tele_session, availability, invite, config, otp, webhook
├── utils/             livekit.py (token minting), session.py, availability.py
├── tasks/             notify.py, reminders.py, session.py
└── integrations/      notifications.py  (guarded, optional)
```

### Resulting API (all under `/api/care_connect/`)

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/config/` | `enabled`, `livekit_url`, `join_buffer_minutes`, `grace_minutes` |
| GET / POST | `/sessions/` | Staff **must** pass `facility=<id>`, else the queryset narrows to own participation |
| POST | `/sessions/{id}/join\|invite\|decline\|end/` | |
| GET / PATCH | `/availabilities/{id}/` | `teleconsultation_enabled` → `Availability.meta`; list requires `?schedule=<uuid>` |
| GET | `/otp/sessions/?booking={id}` | Patient portal, phone-scoped |
| POST | `/otp/sessions/{id}/join\|decline/` | |
| GET | `/otp/config/`, `/otp/availabilities/?schedule={id}` | Read-only, public schedules only |
| POST | `/livekit/webhook/` | Drives `participant_joined` → "call started" notification |

### How LiveKit auth works (the broker pattern)

The LiveKit API secret lives only in `plugin_settings`. The browser never sees it.

1. Browser calls `POST /api/care_connect/sessions/{id}/join/` with its CARE JWT (or OTP token).
2. Backend authorises: `resolve_participant(session, request.user)` then `ensure_joinable(session)`.
3. Backend mints a LiveKit JWT scoped to **that one room**, with `can_publish` derived from the
   participant's role, identity `user:{external_id}` / `patient:{external_id}`, and a
   `CONNECT_TOKEN_TTL_MINUTES` TTL. Identity and grants are never read from the request body.
4. Browser connects straight to LiveKit with that token and `config.livekit_url`.
5. LiveKit posts back to `/api/care_connect/livekit/webhook/` with `authentication_classes = []`
   and a signed `Authorization` header, verified against the raw body via `WebhookReceiver`.

Two settings, not one: `CONNECT_LIVEKIT_URL` (`ws://localhost:7880`, browser-resolvable) and
`CONNECT_LIVEKIT_HOST` (`http://host.docker.internal:7880`, container-resolvable for the
management API). Conflating them works in exactly one of the two environments.

### Two bugs worth pre-empting
1. `TeleAvailabilitySerializer.teleconsultation_enabled` **must be `write_only=True`**. The flag
   lives in `meta`, not on the model, so DRF's `to_representation` raises `AttributeError` → 500.
   The 500 has no CORS header, so the browser reports a *CORS error*. Hours lost.
2. Availabilities are capped at 30 slots per session (09:00–17:00 @ 15 min = 32 → 400), and
   `day_of_week` is an integer with 0 = Monday.

---

## Step 3 — Frontend

```
care_connect_fe/src/
├── manifest.tsx                     routes + 5 components + notification handler registration
├── utils/api.ts                     window.CARE_API_URL, staff/OTP token, /otp prefix
├── utils/notificationHandler.tsx    pushes onto window.__CARE_NOTIFICATION_HANDLERS__
├── components/
│   ├── Page.tsx                     .care-connect-container, display: contents
│   ├── AppointmentActions.tsx       staff quick-actions
│   ├── AppointmentCardActions.tsx   patient booking card
│   ├── ScheduleAvailabilityActions.tsx   the enable toggle
│   ├── AppointmentSlotGroupHeader.tsx    "video" badge on slots
│   ├── AppShellOverlay.tsx          in-progress call banner
│   ├── CallDialog.tsx / CallRoom.tsx     lazy — LiveKit is ~600 kB
├── pages/CallSession.tsx            deep-linkable /connect/session/:id
├── hooks/                           useTeleSession, useBookingJoinState, useActiveSessions
└── public/locale/en.json            keys prefixed connect__
```

`AppShellOverlay` polls the participant-scoped session list every 20s and filters
`is_joinable && !closed`. Because it is mounted only in `AppRouter`, the banner never leaks into
the patient portal.

---

## Step 4 — Cross-plugin notifications (optional dependency)

Backend `integrations/notifications.py`, guarded by
`CONNECT_NOTIFY_ENABLED and apps.is_installed("care_notifications")`. Four event types, all
`resource_type="tele_session"`:

| Event | Trigger |
| --- | --- |
| `tele_session_invite` | viewset `invite` action → `notify_tele_session_invite.delay()` |
| `tele_session_started` | LiveKit `participant_joined` webhook, when the patient joins first |
| `tele_session_missed` | `utils/session.py` end-of-session flow |
| `tele_session_join_reminder` | celery beat sweep, `CONNECT_JOIN_REMINDER_LEAD_MINUTES` before start |

Frontend registers a handler at the top of `manifest.tsx`:

```tsx
(window.__CARE_NOTIFICATION_HANDLERS__ ??= []).push({
  resourceType: "tele_session",
  label: "connect__tele_session",
  path: (n) => `/connect/session/${n.resource_id}`,
});
```

The `connect__tele_session` key lives in **care_connect_fe's own** `en.json`; the notifications
plugin renders it with a bare `t(label)` and relies on `fallbackNS`. Get this wrong and the UI
shows the raw string `tele_session` and clicking does nothing.

---

## Step 5 — The complete core diff

**care_fe — 5 extension points added to `src/pluginTypes.ts` + their render sites:**

| Extension point | Render site |
| --- | --- |
| `AppointmentActions` | `pages/Appointments/AppointmentDetail.tsx` |
| `AppointmentCardActions` | `pages/Appointments/BookAppointment/BookingsList.tsx`, `pages/Patient/index.tsx` |
| `ScheduleAvailabilityActions` | `pages/Scheduling/components/EditScheduleTemplateSheet.tsx` |
| `AppointmentSlotGroupHeader` | `pages/Appointments/BookAppointment/AppointmentSlotPicker.tsx` **and** `pages/PublicAppointments/Schedule.tsx` |
| `AppShellOverlay` | `src/Routers/AppRouter.tsx`, inside `PermissionProvider`, after `</main>` |

Plus one genuine bug fix: `TokenSlot["availability"]` was missing the `id` field that the API
already returned.

**care — 1 file:** the `Plug(name="care_connect", …)` entry in `plug_config.py`.

Every name is generic and location-based. Nothing in core mentions teleconsultation, LiveKit, or
the plugin. **That is the bar.**

---

## Step 6 — Running it locally

```bash
# backend
cd care && make up && make migrate && make load-fixtures
docker exec care_be-backend-1 python install_plugins.py
docker exec care_be-celery-1  python install_plugins.py     # ← required for notifications
docker compose restart backend celery

# livekit
docker run --rm -p 7880:7880 -v ./livekit.yaml:/livekit.yaml livekit/livekit-server --config /livekit.yaml

# plugin frontend
cd care_connect_fe && npm run dev          # :4173

# host
cd care_fe && npm run dev                  # :4000
```

`care_fe/.env.local`:

```
REACT_CARE_API_URL=http://127.0.0.1:9000
REACT_ENABLED_APPS=ohcnetwork/care_connect_fe@localhost:4173/assets/remoteEntry.js
```

### Data prerequisites for the patient flow

Not code — these silently produce zero results:

1. `Facility.geo_organization` must be a **district**, not a state. The patient location picker
   only lists districts.
2. `Schedule.is_public` must be `True` — `get_slots_for_day` filters on it for OTP callers.

### LiveKit ICE failures

`rtc.node_ip: 127.0.0.1` fails whenever the browser offers only public `srflx` candidates —
Cloudflare WARP, or Firefox's mDNS host obfuscation. Set `node_ip` to the machine's LAN IP:

```bash
ipconfig getifaddr $(route -n get default | awk '/interface/{print $2}')
```

For Firefox also set `media.peerconnection.ice.obfuscate_host_addresses=false`.

---

## Scoring a fresh agent's attempt

| Criterion | Pass |
| --- | --- |
| Availability flag stored in `meta`, no core migration | ☐ |
| Sessions auto-created via a signal, not a core viewset edit | ☐ |
| All routes under `/api/care_connect/`, mounted by the core loop | ☐ |
| Separate OTP route surface for the patient portal | ☐ |
| Manifest exposes lazy components; LiveKit not in the manifest chunk | ☐ |
| i18n keys prefixed and in the plugin's own locale file | ☐ |
| Core diff ≤ 5 generic extension points + `plug_config.py` | ☐ |
| No core file mentions the plugin by name | ☐ |
| Notifications integration degrades to a no-op when absent | ☐ |

Anything the agent had to ask about, or got wrong, is a gap in the skills — fix the skill, not
the agent.
