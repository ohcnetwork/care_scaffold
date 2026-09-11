---
name: care-extension-points
description: The catalog of care_fe plugin extension points (SupportedPluginComponents), where each one renders in the host, how to choose one, the component-override mechanism, and the exact procedure for adding a new generic extension point to core when none fits. Use when deciding where plugin UI attaches or when a core UI change seems necessary.
---

# CARE Frontend Extension Points

An extension point is a named slot in `care_fe` where any plugin can inject a component.
Core renders `<PLUGIN_Component __name="X" {...props} />`; every loaded plugin that declares
`components.X` in its manifest gets rendered there, each wrapped in its own error boundary.

**Using an existing extension point costs zero core changes.** Exhaust this catalog before
considering a core edit.

## Catalog

Names, props and render sites are defined in `care_fe/src/pluginTypes.ts`
(`SupportedPluginComponents`). Verify against that file — it moves.

### Appointments & scheduling

| Name | Props | Renders in |
| --- | --- | --- |
| `AppointmentActions` | `appointment: AppointmentRead`, `facilityId`, `className?` | `pages/Appointments/AppointmentDetail.tsx` — staff quick-actions grid |
| `AppointmentCardActions` | `appointment: Appointment \| PublicAppointment`, `patientId`, `className?` | `pages/Appointments/BookAppointment/BookingsList.tsx`, `pages/Patient/index.tsx` — patient-facing booking cards |
| `ScheduleAvailabilityActions` | `availability`, `scheduleId`, `facilityId`, `resourceType`, `resourceId` | `pages/Scheduling/components/EditScheduleTemplateSheet.tsx` — availability editor |
| `AppointmentSlotGroupHeader` | `availability: TokenSlot["availability"]`, `className?` | `pages/Appointments/BookAppointment/AppointmentSlotPicker.tsx` **and** `pages/PublicAppointments/Schedule.tsx` — two separate components; patch both or the badge is missing on the patient side |

### Patient

| Name | Props | Renders in |
| --- | --- | --- |
| `PatientHomeActions` | `patient: PatientRead`, `facilityId?`, `className?` | `components/Patient/PatientProfile.tsx` |
| `PatientHomeQuickActions` | same as above | `pages/Patient/PatientHome.tsx` |
| `PatientInfoCardActions` | `facilityId`, `patient`, `className?` | `pages/Patient/PatientHome.tsx` |
| `PatientSearchActions` | `facilityId`, `className?` | `components/Patient/PatientIndex.tsx` |
| `PatientRegistrationForm` | `form: UseFormReturn`, `facilityId?`, `patientId?`, `submitForm?` | `components/Patient/PatientRegistration.tsx` |
| `PatientDetailsTabDemographyGeneralInfo` | `facilityId`, `patientId`, `patientData` | patient demography tab |

### Encounter

| Name | Props | Renders in |
| --- | --- | --- |
| `EncounterActions` | `encounter: EncounterRead`, `className?` | `components/Encounter/EncounterCommandDialog.tsx`, `pages/Encounters/tabs/overview/summary-panel-actions.tab.tsx` |
| `EncounterOverviewTop` | `encounter`, `patientId`, `encounterId` | `pages/Encounters/tabs/overview.tsx` |
| `PatientInfoCardQuickActions` | `encounter`, `className?` | `pages/Encounters/EncounterShow.tsx` |
| `PatientInfoCardMarkAsComplete` | `encounter` | `pages/Encounters/MarkEncounterAsCompletedDialog.tsx` |
| `NoteMessageInput` | `message`, `setMessage` | `components/Notes/NoteManager.tsx` |

### Facility, orders, billing, labs

| Name | Props | Renders in |
| --- | --- | --- |
| `FacilityHomeActions` | `facility: FacilityRead`, `className?` | `components/Facility/FacilityHome.tsx` |
| `DeliveryOrderActions` | `facilityId`, `locationId` | `.../externalSupply/deliveryOrder/DeliveryOrderList.tsx` |
| `InvoiceRecordPaymentOptions` | `facilityId`, `invoice: InvoiceRead` | `pages/Facility/billing/invoice/InvoiceShow.tsx` |
| `ServiceRequestAction` | `serviceRequestId` | `.../serviceRequests/components/DiagnosticReportForm.tsx` |
| `DiagnosticReportOverride` | observation definitions + change handlers | same file |

### Global / misc

| Name | Props | Renders in |
| --- | --- | --- |
| `AppShellOverlay` | `{ className?: string }` | `src/Routers/AppRouter.tsx` (inside `PermissionProvider`, after `</main>`) — mounted once for the **staff shell only**, so it never leaks into the patient portal. Use for global banners, floating call bars, toasts. |
| `Scribe` | `formState`, `setFormState` | `components/Questionnaire/QuestionnaireForm.tsx` |
| `DoctorConnectButtons` | `user: UserReadMinimal` | legacy, via `manifest.extends` |

### Non-component surfaces (also zero core diff)

| Manifest key | What it gives you |
| --- | --- |
| `routes` | Whole pages at your own URLs. **Cheapest surface in the system — always prefer it.** |
| `navItems` / `userNavItems` / `adminNavItems` / `billingNavItems` | Sidebar links |
| `organizationTabs` | Extra tabs on organization pages |
| `encounterTabs` / `encounterFileTabs` | Extra encounter tabs |
| `devices` | Device-type integration: icon, configure form, page card, encounter overview |
| `overrides` | Conditionally replace a registered core component |

## Choosing

1. **Can it be its own page?** → `routes` + a nav item. Done, no core diff.
2. **Does it belong next to an existing object?** → find that object's page in the table above.
3. **Is it global/ambient?** → `AppShellOverlay`.
4. **Does it need to *replace* core UI rather than sit beside it?** → `overrides`.
5. **None of the above?** → add one, below.

## Overrides

```ts
overrides: [
  {
    component: "SomeRegisteredKey",     // must be registered in core via register()
    replacement: lazy(() => import("./components/MyReplacement")),
    condition: /* OverrideCondition */,
    priority: 10,                        // higher wins
    description: "Replace X for facilities with Y enabled",
  },
]
```

`PluginEngine` calls `addOverride(...)` for each and cleans up on unmount. Use sparingly: an
override silently changes core behaviour for every user of the deployment.

## Adding a new extension point to core

Only when nothing above fits. Keep it **generic** — a reviewer must be able to imagine three
different plugins using it.

### Rules

- Name it after the **location**, never the plugin. `AppointmentActions` ✅, `ConnectCallButton` ❌.
- Props are the surrounding domain object(s) plus `className?`. No plugin-specific data.
- No conditionals, imports, or feature flags referencing any plugin.
- One render site per logical location — but check for *duplicate* implementations of the same
  UI (staff vs. patient variants) and patch all of them.

### Procedure

1. In `care_fe/src/pluginTypes.ts`, add the props type and the entry:

```ts
/** Renders alongside an availability's name when picking a slot to book. */
export type AppointmentSlotGroupHeaderComponentType = React.FC<{
  availability: TokenSlot["availability"];
  className?: string;
}>;

export type SupportedPluginComponents = {
  // …
  AppointmentSlotGroupHeader: AppointmentSlotGroupHeaderComponentType;
};
```

2. Render it in the host component:

```tsx
<PLUGIN_Component
  __name="AppointmentSlotGroupHeader"
  availability={slot.availability}
  className="ml-2"
/>
```

3. Implement it in your plugin's manifest with a **structural mirror** of the props (you cannot
   import core types across the federation boundary):

```tsx
AppointmentSlotGroupHeader: lazy(() => import("./components/AppointmentSlotGroupHeader")),
```

4. Add the core diff to your `.agent/core-diff.md` and raise it as a small, standalone PR to
   `care_fe` — separate from your plugin work.

### ⚠️ Props-less extension points

A component that takes no props **must** be typed as:

```ts
export type MyOverlayComponentType = React.FC<{ className?: string }>;
```

`React.FC<Record<string, never>>` breaks the `PluginComponentProps` discriminated union in
`PluginEngine.tsx` and produces confusing type errors at every other call site.

## Sanity check

If your core diff contains anything other than (a) a props type + a `SupportedPluginComponents`
key, and (b) one or two `<PLUGIN_Component>` render sites — stop and reconsider. You are probably
putting plugin logic in core.
