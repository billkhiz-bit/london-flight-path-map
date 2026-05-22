# Mobile Redesign Plan — Sky Score (Option A)

> Created 2026-05-22. Goal: a mobile-first UI for the iOS/Android store builds
> that feels like a native app, not a desktop site folded into a bottom sheet.
> Same `index.html` serves web desktop, web mobile, PWA, and native — so all
> changes are **scoped to `@media (max-width: 900px)`** and must not alter the
> desktop two-column layout.

## Decision

**Option A — bottom tab bar, search-first.** Chosen 2026-05-22.

Rationale: bottom nav is the universal, thumb-reachable mobile pattern; it
matches the core task (look up a place → read its score); it separates the
four jobs that currently collide in one bottom sheet; and giving the map its
own full-screen tab removes the pan-vs-scroll gesture conflict that caused the
"page dragged sideways" confusion.

## Navigation model

A fixed bottom navigation bar with four destinations, driven by a single
`data-mview` state attribute on `.app`:

| Nav item | `data-mview` | Shows | Reuses |
|---|---|---|---|
| 🔍 Search | `search` | Search box + score result (the Analysis panel), full-screen | `switchTab('analysis')` |
| 🗺️ Map | `map` | Full-screen D3 map + its layer/legend/zoom chrome | existing map |
| 📊 Rankings | `ranking` | Persona selector + borough league table | `switchTab('ranking')` |
| ★ Saved | `saved` | Saved locations | `switchTab('favourites')` + `loadFavourites()` |

Default view on mobile load = **search** (search-first). A landing search
result (postcode search or borough tap on the map) auto-switches to **search**
so the user always sees their result.

## What changes (and what doesn't)

- **Reused as-is**: `triggerSearch()`, `switchTab()`, `updateSidebar()`,
  `loadFavourites()`, `switchCity()`, all scoring/data logic, the autocomplete,
  the persona bar, the metric cards. No backend or data changes.
- **Replaced**: the `≤900px` bottom-sheet model (peek/expand `transform`,
  `.sheet-handle`) gives way to full-screen views toggled by the bottom nav.
  The sheet handle is hidden on mobile; `setSheetState()` becomes a shim that
  routes to the new `setMobileView('search')`.
- **Added**: bottom-nav markup, `@media (max-width:900px)` CSS for the nav +
  full-screen views + **safe-area insets** (`env(safe-area-inset-*)`), and a
  `setMobileView()` controller in JS.
- **Untouched**: everything `≥901px` (desktop keeps its 2-column grid and the
  in-sidebar tab bar). Bottom nav is `display:none` above 900px.

## Safe-area handling (the native polish)

`viewport-fit=cover` added to the viewport meta so `env(safe-area-inset-*)`
resolves. Bottom nav pads `env(safe-area-inset-bottom)`; header pads
`env(safe-area-inset-top)`; map chrome (legend, layer toggles, zoom) sits above
the nav. This fixes the home-indicator overlap noted during diagnosis.

## Build order (incremental, each step verifiable)

1. ✅ Gate PWA install prompt out of native + make `[hidden]` authoritative.
2. ✅ Bottom-nav markup + `setMobileView()` controller + nav wiring.
3. ✅ `@media (max-width:900px)` CSS: nav bar, full-screen views, safe-area.
4. ✅ Hook `revealSheetIfMobile()` → `setMobileView('search')` on result.
5. ✅ Verify via Playwright at iPhone viewport (native sim) across all four views;
   zero overflow, nav reachable, install prompt gone in-app.
6. ✅ Desktop regression check at 1440px (2-column grid + nav hidden — unchanged).
7. ✅ Committed to canonical clone (`78aea08`+`a0e518b`), `/preflight` clean,
   deployed to web/CloudFront, **verified live at 360/390/414px**.
8. ⏳ **User-only, remaining:** `git push` → Codemagic ios-workflow Start build →
   ASC submit ("What's New" in iOS `release_notes.txt`); Android `npm run
   build:android` (needs `JAVA_HOME` + keystore env vars) → Play flow.

**Status (2026-05-22): code complete, committed, live on web. Native store
submission pending the user-only push/build/submit steps above.**

## Verification

`tests/native-sim-render.mjs` renders the local file at an iPhone viewport with
a Capacitor shim. Extend it to snapshot each `data-mview` and assert
`overflowPx === 0` and the bottom nav is visible. Desktop snapshot at 1440px to
prove no regression.

## Out of scope (later)

- Reworking the Analysis result card visual hierarchy (separate pass).
- NYC parity polish.
- Native gestures beyond the map's existing pinch/drag.
