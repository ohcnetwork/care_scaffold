---
name: care-auth-contexts
description: The two authentication contexts in CARE — staff JWT (care_access_token) and patient OTP (care_patient_token) — and how a plugin must serve both. Covers the /otp route-prefix convention, phone-number-scoped querysets, permission scoping, and the shells each context renders in. Use when a plugin needs to work in the patient portal, or when queryset scoping/permissions are involved.
---

# CARE Auth Contexts

CARE has **two independent authenticated experiences**. A plugin that only handles the first one
will silently do nothing in the patient portal.

> Authenticating to an **external** service (minting third-party tokens, verifying inbound
> webhooks) is a different problem — see the `care-third-party-services` skill.

| | Staff | Patient portal |
| --- | --- | --- |
| Login | username + password (+ 2FA) | phone number + OTP |
| Token storage key | `localStorage.care_access_token` (raw JWT string) | `localStorage.care_patient_token` (**JSON object**, token at `.token`) |
| JWT type | standard access token | `patient_login` |
| Router | `AppRouter` | `PatientRouter` |
| Identity | a `User` row, with roles/permissions | a **phone number** — possibly several patients |
| Scoping | facility / organization / role permissions | everything filtered by that phone number |

## Reading the token in a plugin

```ts
const STAFF_KEY   = "care_access_token";
const PATIENT_KEY = "care_patient_token";

function getPatientToken(): string | null {
  try {
    const stored = JSON.parse(localStorage.getItem(PATIENT_KEY) || "null");
    return stored?.token ?? null;      // note: it's an object, not a bare string
  } catch {
    return null;
  }
}

function isPatientSession() {
  return !localStorage.getItem(STAFF_KEY) && !!getPatientToken();
}

function getAuthToken() {
  return localStorage.getItem(STAFF_KEY) ?? getPatientToken();
}
```

Staff wins when both are present (a staff member testing the patient flow in the same browser).

### `localStorage` or `window.AuthUserContext`?

Both are available. Use them for different things:

| Need | Use |
| --- | --- |
| A bearer token for a `fetch` call | `localStorage` (as above). Non-reactive, callable outside React. |
| The current user's name, id, roles, or to trigger sign-out | `React.useContext(window.AuthUserContext)` |

The context is reactive and correct across tab-sync and token refresh, so anything **rendered** should read it. The API client is not a component and must not depend on React, so it reads `localStorage` directly. Never cache the token in module scope — it is refreshed every few minutes.

The context only exists in the **staff** shell. In the patient portal `window.AuthUserContext` yields no user; identify the caller from the OTP-scoped API responses instead.

## The `/otp` route-prefix convention

Patient tokens **cannot** authenticate against the staff endpoints — the permission classes and
querysets assume a `User`. Expose a parallel, read-restricted set of routes under an `otp/`
prefix, and have the client pick the prefix automatically.

Backend (`care_<name>/urls.py`):

```python
router.register("sessions",           TeleSessionViewSet,        basename="tele-session")
router.register("otp/sessions",       OTPTeleSessionViewSet,     basename="otp-tele-session")
router.register("otp/availabilities", OTPTeleAvailabilityViewSet, basename="otp-tele-availability")

urlpatterns = [
    *router.urls,
    path("config/",     ConfigView.as_view()),
    path("otp/config/", OTPConfigView.as_view()),
]
```

Frontend (`src/utils/api.ts`):

```ts
/** OTP callers get a separate, phone-number-scoped set of routes. */
function scope() {
  return isPatientSession() ? "/otp" : "";
}

sessions.list = (params) =>
  request(`${scope()}/sessions/`, "GET", undefined,
    // OTP sessions are already scoped to the caller's phone number.
    isPatientSession() ? { ...params, facility: undefined } : params);
```

### What belongs on each side

| Operation | Staff routes | OTP routes |
| --- | --- | --- |
| List / retrieve own records | ✅ | ✅ (phone-scoped) |
| Join / decline / act on own record | ✅ | ✅ |
| Read public config | ✅ | ✅ |
| Create records, invite others, end sessions | ✅ | ❌ |
| Write to core objects (schedules, availabilities) | ✅ | ❌ (read-only, public rows only) |

Keep the OTP viewsets **deliberately anaemic**. They are the internet-facing surface.

## Backend OTP viewsets

Use CARE's OTP authentication + permission classes and scope on the phone number carried by the
token — never on a client-supplied identifier:

```python
class OTPTeleSessionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GenericViewSet):
    authentication_classes = [MiddlewareAuthentication]     # OTP/patient-login auth
    permission_classes = [IsAuthenticated]
    filterset_fields = ["booking"]        # NOTE: no `facility` field here — see gotcha below

    def get_queryset(self):
        phone = self.request.user.phone_number    # from the patient_login token
        return TeleSession.objects.filter(
            booking__patient__phone_number=phone, deleted=False
        )
```

## Queryset scoping on the staff side

Default to "only what I participate in", widen only after an explicit authorization check:

```python
def get_queryset(self):
    qs = TeleSession.objects.filter(deleted=False)
    facility_id = self.request.query_params.get("facility")
    if facility_id:
        AuthorizationController.call("can_view_facility", self.request.user, facility_id)
        return qs.filter(...facility=facility_id)
    return qs.filter(participants__user=self.request.user)
```

### ⚠️ The scoping gotcha this creates

Staff lookups **must pass `facility=<id>`**. Without it the queryset narrows to sessions the
caller personally participates in, so front-desk or non-assigned staff see an empty list and no
action buttons — with no error to debug.

Conversely, patient (OTP) calls **must not** pass `facility` — the OTP filterset has no such
field and it is meaningless there. Strip it in the client, as shown above.

## Which shell am I in?
- `AppShellOverlay` is mounted only in `AppRouter` (staff). It never renders in the patient
  portal — useful when you want a global banner that must not leak to patients.
- Patient-facing extension points are `AppointmentCardActions` and
  `AppointmentSlotGroupHeader` (the `PublicAppointments/Schedule.tsx` render site).
- Plugin `routes` are injected into the **staff** router. A patient-portal page needs the
  patient-facing extension points, or a core change — check before promising one.

## Data prerequisites for testing patient self-booking

Not code, but the two things that make patient booking silently return zero results:

1. `Facility.geo_organization` must be the **district** (e.g. Ernakulam), not the state. The
   patient location picker only offers districts.
2. The `Schedule.is_public` flag must be `True` ("Make the template public") — `get_slots_for_day`
   filters `schedule__is_public=True` for OTP callers.

Flow: `/patient/home` → Book Appointment → district → View Facility → practitioner → date →
slot → Continue → select patient → Confirm.

## Checklist

- [ ] Client picks the token and the `/otp` prefix automatically.
- [ ] OTP viewsets are read-mostly and scoped by the token's phone number.
- [ ] No OTP endpoint accepts a caller-supplied patient/facility identifier as its scope.
- [ ] Staff client always sends `facility=<id>` where the viewset expects it.
- [ ] Tested as staff **and** as an OTP patient.
