---
name: care-extension-points
description: The catalog of care_fe plugin extension points (SupportedPluginComponents), where each one renders in the host, how to choose one, the component-override mechanism, and how to report unsupported UI requirements without changing core. Use when deciding where plugin UI attaches or when the available host surfaces do not fit.
---

# CARE Frontend Extension Points

An extension point is a named slot in `care_fe` where any plugin can inject a component.
Core renders `<PLUGIN_Component __name="X" {...props} />`; every loaded plugin that declares
`components.X` in its manifest gets rendered there, each wrapped in its own error boundary.

**Use existing extension points only.** The `care` and `care_fe` checkouts are read-only during
plugin development. A missing hook is a scaffold blocker, not permission to edit core.

## Catalog

This catalog is a reference snapshot. Names, props and render sites are defined in the checked-out
`care_fe/src/pluginTypes.ts` (`SupportedPluginComponents`) and its host components. Inspect those
files read-only to verify availability; a catalog entry does not guarantee support in that revision.

### Appointments & scheduling

| Name | Props | Renders in |
| --- | --- | --- |
| `AppointmentActions` | `appointment: AppointmentRead`, `facilityId`, `className?` | `pages/Appointments/AppointmentDetail.tsx` — staff quick-actions grid |
| `AppointmentCardActions` | `appointment: Appointment \| PublicAppointment`, `patientId`, `className?` | `pages/Appointments/BookAppointment/BookingsList.tsx`, `pages/Patient/index.tsx` — patient-facing booking cards |
| `ScheduleAvailabilityActions` | `availability`, `scheduleId`, `facilityId`, `resourceType`, `resourceId` | `pages/Scheduling/components/EditScheduleTemplateSheet.tsx` — availability editor |
| `AppointmentSlotGroupHeader` | `availability: TokenSlot["availability"]`, `className?` | `pages/Appointments/BookAppointment/AppointmentSlotPicker.tsx` **and** `pages/PublicAppointments/Schedule.tsx` — verify both render sites; staff support alone does not establish patient support |

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
5. **None of the above?** → report the blocker below and defer the affected feature.

## Overrides

```ts
overrides: [
  {
    component: "SomeRegisteredKey",     // must already be registered in core via register()
    replacement: lazy(() => import("./components/MyReplacement")),
    condition: /* OverrideCondition */,
    priority: 10,                        // higher wins
    description: "Replace X for facilities with Y enabled",
  },
]
```

`PluginEngine` calls `addOverride(...)` for each and cleans up on unmount. Use sparingly: an
override silently changes core behaviour for every user of the deployment.

## Implementing an existing extension point

Use a **structural mirror** of the checked-out host's props in the plugin; do not import core types
across the federation boundary. Register the implementation in your plugin's manifest:

```tsx
AppointmentSlotGroupHeader: lazy(() => import("./components/AppointmentSlotGroupHeader")),
```

### Props-less extension points

A plugin component whose host supplies only an optional class name can be typed as:

```ts
export type MyOverlayComponentType = React.FC<{ className?: string }>;
```

Match the host contract. The historical use of `React.FC<Record<string, never>>` in core broke
the `PluginComponentProps` discriminated union in `PluginEngine.tsx`; if the checked-out host still has
that problem, report it instead of patching core.

## When no supported surface fits

1. Inspect the checked-out host's manifest contract, registered overrides, and relevant staff/patient
   render sites read-only. Record the checkout commit and the missing props or render location.
2. File an issue on [`ohcnetwork/care_scaffold`](https://github.com/ohcnetwork/care_scaffold/issues)
   with the intended plugin behavior, the inspected paths, reproduction evidence, and the supported
   alternatives considered. If issue creation is unavailable, preserve an issue draft and report
   the blocker.
3. Use an existing supported surface if it meets the requirement; otherwise defer the affected
   feature and continue independent plugin work. A scaffold PR may correct template guidance or
   setup, but must not include a core patch as part of plugin development.

Do not add an extension point, edit core types, patch a render site, or open a core PR from this
workflow. The read-only boundary applies even to generic changes and bug fixes.

## Sanity check

The plugin work must leave `care` and `care_fe` unchanged. Verify their status against the starting
state; do not revert pre-existing user changes. All new UI implementation belongs in the plugin's
own repository.
