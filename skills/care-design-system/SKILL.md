---
name: care-design-system
description: How to make plugin UI look native to CARE — Tailwind v4 setup, the CARE colour palette and semantic tokens, shadcn/ui component installation and re-theming, the cn() helper, lucide icons, scoping utilities to the plugin container, the Radix portal escape problem, and cloning components from care_fe. Use whenever building or styling any plugin UI component.
---

# CARE Design System for Plugins

A plugin renders **inside** the host's DOM but is built from a **separate** Tailwind pipeline. It
inherits nothing automatically. If you run `npx shadcn add button` and ship it, you get a black
`bg-neutral-900` button sitting next to CARE's green `bg-primary-700` ones, in the wrong font.

This skill exists to prevent that.

## What the host uses

| Concern | care_fe |
| --- | --- |
| CSS framework | Tailwind **v4**, hybrid: `@import "tailwindcss"` + `@config "../../tailwind.config.js"` |
| Component library | **shadcn/ui**, style `new-york`, `baseColor: "gray"`, **`cssVariables: false`** |
| Primitives | Radix UI |
| Icons | **`lucide-react`** (use CAREUI icons only when explicitly asked) |
| Font | **Figtree**, via `@fontsource/figtree` weights 300–900 |
| Class merging | `cn()` = `twMerge(clsx(...))` from `@/lib/utils` |
| Variants | `class-variance-authority` (`cva`) |

### ⚠️ `cssVariables: false` is the key fact

CARE does **not** use shadcn's `bg-background` / `bg-primary` CSS-variable theming. Components
reference **literal Tailwind colour utilities** (`bg-gray-900`, `bg-primary-700`). Consequences:

- You cannot re-theme by overriding a few `--background` variables. There are none.
- Every component the shadcn CLI generates must have its colours **manually remapped** to CARE's
  palette after installation.
- Your plugin's `@theme` must define the same colour scales, or `bg-primary-700` won't compile.

## The CARE palette

Reproduce this in your plugin's CSS. `primary` is CARE green; `secondary` is a purple-tinted grey.

```css
@theme {
  /* CARE primary — green */
  --color-primary-50:  #ecfdf5;
  --color-primary-100: #def7ec;
  --color-primary-200: #bcf0da;
  --color-primary-300: #84e1bc;
  --color-primary-400: #31c48d;
  --color-primary-500: #0d9f6e;
  --color-primary-600: #057a55;
  --color-primary-700: #046c4e;
  --color-primary-800: #03543f;
  --color-primary-900: #014737;
  --color-primary:     #0d9f6e;

  /* CARE secondary — purple-tinted greys */
  --color-secondary-50:  #f9fafb;
  --color-secondary-100: #fbfafc;
  --color-secondary-200: #f7f5fa;
  --color-secondary-300: #f1edf7;
  --color-secondary-400: #dfdae8;
  --color-secondary-500: #bfb8cc;
  --color-secondary-600: #9187a1;
  --color-secondary-700: #7d728f;
  --color-secondary-800: #6a5f7a;
  --color-secondary-900: #453c52;

  /* Semantic aliases — these are what CARE actually uses for status colour */
  --color-warning-500: var(--color-amber-500);   /* warning-*  → amber-*  */
  --color-alert-500:   var(--color-violet-500);  /* alert-*    → violet-* */
  --color-danger-500:  var(--color-red-500);     /* danger-*   → red-*    */
  /* …repeat for 50–900 of each */
}
```

Other tokens: `--radius: 0.5rem`; body text colour `#453c52` (= `secondary-900`);
headings `font-bold`.

**Do not re-import Figtree.** The host already loads it. Inherit it (see scoping, below) —
re-importing duplicates a multi-hundred-kilobyte font download.

## Scoping — plugin CSS must not leak

Your bundle has `cssCodeSplit: false` and injects a single stylesheet into a page you don't own.
Nest all Tailwind utilities under your plugin's container class:

```css
@layer theme, base, components, utilities;

@import "tailwindcss/theme.css" layer(theme);
@import "tailwindcss/preflight.css" layer(base);

@custom-variant dark (&:where(.dark, .dark *));

@layer utilities {
  .care-connect-container {
    @tailwind utilities;      /* every utility, scoped to this class */
  }
}
```

and wrap every root you render:

```tsx
export default function Page({ children }: PropsWithChildren) {
  return (
    <div className="care-connect-container" style={{ display: "contents" }}>
      {children}
    </div>
  );
}
```

`display: contents` keeps the wrapper out of the host's layout flow, so a scoped extension-point
component still sits correctly inside the host's flex/grid.

Wrap **every** entry point: each extension-point component *and* each route.

## ⚠️ Radix portals escape the scope

`Dialog`, `Popover`, `Select`, `DropdownMenu`, `Tooltip` render into `document.body` via a portal —
**outside** `.care-connect-container`. Your scoped utilities do not apply, and the dialog renders
unstyled.

Fix: capture a ref to your container and pass it as the portal target.

```tsx
// hooks/useContainerRef.tsx
const ContainerRefContext = createContext<React.RefObject<HTMLDivElement | null> | null>(null);

export const useContainerRef = () => {
  const ctx = useContext(ContainerRefContext);
  if (!ctx) throw new Error("useContainerRef must be used within a ContainerRefProvider");
  return ctx;
};
```

```tsx
// components/ui/dialog.tsx — thread a `container` prop through
<DialogPortal container={container}>…</DialogPortal>
```

```tsx
const containerRef = useContainerRef();
<DialogContent container={containerRef.current}>…</DialogContent>
```

Symptom if you skip this: the dialog works but is completely unstyled, or appears behind the host
UI. It is not a z-index bug.

## Installing shadcn components

`components.json` for a plugin — mirror the host's `style` and `baseColor`, and use `lucide`:

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "",
    "css": "src/style/index.css",
    "baseColor": "gray",
    "cssVariables": false,
    "prefix": ""
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  },
  "iconLibrary": "lucide"
}
```

> Use `baseColor: "gray"` — the host's. `neutral` produces a subtly different grey that reads as
> "not quite right" beside host UI. (`care_connect_fe` got this wrong; don't copy it.)

Then, after `npx shadcn@latest add <component>`:

1. Remap colours to CARE's palette (`neutral-*` → `gray-*`, and buttons/CTAs → `primary-*`).
2. Change the import to your `cn` location.
3. Add a `container` prop if it portals.

## Match the host's Button

CARE's `Button` **defaults to `variant: "primary"` (green)**, whereas stock shadcn defaults to a
black `default`. This single difference is the most visible mismatch. CARE also adds variants
stock shadcn does not have:

| Variant | Classes |
| --- | --- |
| `primary` *(default)* | `bg-primary-700 text-white shadow-sm hover:bg-primary-700/90` |
| `outline_primary` | `border border-primary-700 text-primary-700 bg-white hover:bg-primary-700 hover:text-white` |
| `primary_gradient` | `bg-linear-to-b from-primary-700 to-primary-800 hover:from-primary-800 hover:to-primary-900 text-white border border-primary-900 rounded-lg shadow-lg` |
| `white` | `bg-white border border-secondary-400 text-gray-900 shadow-xs hover:bg-gray-100` |
| `warning` | `bg-warning-100 text-warning-900 border border-warning-300` |
| `alert` | `bg-alert-100 text-alert-900 border border-alert-300` |
| `destructive` | `bg-red-500 text-gray-50 hover:bg-red-500/90` |

Base classes: `font-semibold`, `rounded-md`, `text-sm`, `focus-visible:ring-1
focus-visible:ring-gray-950`, `[&_svg]:size-4`.
Sizes: `xs` h-6, `sm` h-8, `md`/`default` h-9, `lg` h-10, `icon` size-9.

## Cloning components from the host (best fidelity)

For a plugin developed under `care_fe/apps/`, core ships a CLI that copies a host component **and
its whole transitive local import graph** into the plugin:

```bash
npm run clone-component -- @/components/ui/button care_connect_fe
npm run clone-component -- @/components/ui/button care_connect_fe --dry-run
npm run clone-component -- @/components/ui/button care_connect_fe --force
```

It rewrites host aliases (`@core/foo` → `@/foo`, `@careConfig` → `@/care.config`) and syncs any
missing npm packages into the plugin's `package.json` (it does not run `npm install`).

Caveat: clones are **independent copies** and will not stay in sync — re-run with `--force` to
refresh. Only files under `src/` and `care.config.ts` are followed; anything else is reported as
unresolved.

## Icons

Use `lucide-react`, at `size-4` inside buttons. `[&_svg]:size-4 [&_svg]:shrink-0` is already in
the Button base classes, so don't set sizes manually there. Do not pull in `@radix-ui/react-icons`
just for icons — it is a second icon set with a different visual weight.

## Third-party CSS is a trap

`cssCodeSplit: false` and the host does **not** auto-inject remote CSS. Any dependency that ships
its own stylesheet (`import "some-lib/dist/styles.css"`) will render unstyled. Either restyle it
with Tailwind or pick a headless alternative.

## Checklist

- [ ] `@theme` declares CARE's `primary`, `secondary`, `warning`, `alert`, `danger` scales.
- [ ] `--radius: 0.5rem`.
- [ ] Font inherited, not re-imported.
- [ ] All utilities scoped under the plugin container class.
- [ ] Every rendered root wrapped in the scoped container.
- [ ] Portalled Radix components receive a `container` target.
- [ ] `components.json` uses `baseColor: "gray"`, `cssVariables: false`, `iconLibrary: "lucide"`.
- [ ] Generated shadcn components remapped off `neutral-*` onto CARE colours.
- [ ] Buttons default to the green `primary` variant, matching the host.
- [ ] No dependency relying on its own bundled CSS.
- [ ] Screenshot-compared against a host component sitting next to it.
