# Mobile Redesign Plan — Sky Score (Option A)

> Created 2026-05-22. Goal: a mobile-first UI for the iOS/Android store builds
> that feels like a native app, not a desktop site folded into a bottom sheet.
> Same `index.html` serves web desktop, web mobile, PWA, and native — so all
> changes are **scoped to `@media (max-width: 900px)`** and must not alter the
> desktop two-column layout.
>
> **Update (v3, 2026-05-29): web and native now diverge.** The redesign below
> is **native-app only** — gated behind an `is-native` class on `<html>` that
> `setupNativeFeatures()` adds only inside the Capacitor app. The **website
> (desktop + mobile browser + PWA) serves the classic bottom-sheet layout**;
> the iOS/Android apps keep this redesign. See "v3 — web/native split" at the
> end of this doc.

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

---

## v2 iteration — 2026-05-28 (map background + 3 tabs)

User feedback after living with v1 for six days: "the search tab is too blank
on first load; the product's identity is the map, but new users don't see it
until they tap a second tab". Resolved by collapsing Search and Map into a
single tab.

### Changes

- **Bottom nav: 4 tabs → 3 tabs.** Map tab removed; merged into Search.
  New users land on the map immediately with a clear search affordance overlaid.
- **Search view = map background + search overlay.** Map is z-index 1 visible;
  sidebar is z-index 2 transparent with `pointer-events:none` (children
  `pointer-events:auto` so the search card and any result card remain
  interactive). Empty-state is hidden via `:has(.empty-state)` so the
  first-load experience is just map + floating search bar.
- **Floating search card.** Search input + hint pinned to top as a rounded
  card with shadow. `margin-right:118px` reserved so the city chip never
  gets covered.
- **City switcher → compact chip top-right.** Repositioned `.city-selector`
  to `position:fixed; top: safe-area+16px; right:14px`; small monospace
  pills so London/NYC switching stays accessible without competing with
  the search bar.
- **Map chrome cleanup.** Desktop zoom buttons (`+`/`-`/`reset`) hidden on
  mobile (pinch + double-tap are native); only `#locate-me` (App Store 4.2
  GPS feature) survives, restyled as a circular FAB above the layer chips.
  `.first-hint` and `.map-title` hidden — the floating search card already
  carries that guidance and brand identity sits in PWA chrome.
- **Result close button.** New `#result-close` (`×`) in the top-right of
  the result card. Click handler restores the boot-time empty-state via
  `cloneNode(true)` + `replaceChildren()` (no `innerHTML` — security
  guidance flagged the string-snapshot pattern). Hidden on desktop and
  when there's nothing to close (`:has(.empty-state) .result-close`).

### Specificity gotchas captured

1. `switchTab()` sets `style.display='block'` inline on the active tab.
   External CSS `display:none` lost to this — fixed with `!important` on
   the empty-state hide rule.
2. Base `.result-close { display:none }` plus mobile-search rule that only
   set `position:absolute` left the button hidden. CSS `position` doesn't
   affect computed `display`; the mobile rule had to explicitly set
   `display:flex`.

### Verification (v2)

`tests/native-sim-render.mjs` updated to assert 3 tabs (not 4), map visible
in search view + hidden in ranking/saved, and search box visible across
states. End-to-end close-button flow tested separately (ad-hoc script):
empty → fake result rendered → close click → empty-state restored with
all 4 quick-search chips re-bound.

### Out of scope (still)

- NYC parity polish.
- Reworking `switchTab()` to use class toggling instead of inline styles
  (would let us drop the `!important` — but it's a wider refactor).

---

## v3 — 2026-05-29 (web/native split: redesign is native-app only)

User decision: keep the live **website** on its classic (pre-redesign) mobile
layout, and reserve the bottom-nav redesign for the **native iOS / Android
apps**. Rationale: the redesign never shipped to either store (the live App
Store build still runs the classic layout), so rather than push a half-deployed
experiment to the web, the two surfaces are deliberately separated. One file,
no fork.

### Mechanism (the single switch)

`setupNativeFeatures()` runs only when `window.Capacitor.isNativePlatform()` is
true; it adds `is-native` to `<html>`. That one class gates both layers:

- **CSS** — every redesign *base* rule in the `@media (max-width: 900px)` block
  is prefixed with `.is-native` (`.is-native .mobile-nav`, `.is-native .app >
  #map-container`, `.is-native .app > .sidebar`, `.is-native .sheet-handle`,
  `.is-native .sidebar > .tab-bar`). The `[data-mview]` *view* rules are left
  unprefixed because they can only match when `data-mview` is set — and JS only
  sets it on native (below). Written as `.is-native …` (class only);
  `html.is-native …` would add element-specificity and out-rank the
  `[data-mview]` rules, breaking the native map swap.
- **JS** — `setMobileView()` (the sole writer of `data-mview`) bails unless
  `is-native`; `revealSheetIfMobile()` branches: native →
  `setMobileView('search')`, web → the classic `setSheetState('open')`.

Because v1+v2 were almost purely additive (they removed only the viewport-meta
line and one `setSheetState('open')` call), the classic bottom-sheet CSS + JS
are still fully present and simply take back over on web once the redesign
rules are gated off.

### Verification

`tests/native-sim-render.mjs` now renders three contexts and asserts the split:
native sim (shim) → redesign (3-tab nav, map swap); **web mobile (no shim) →
classic layout** (no nav, `data-mview` unset, sheet handle present, zero
overflow); desktop 1440px → two-column grid. `tests/live-mobile-verify.mjs`
re-pointed to assert the live web serves the classic layout (a post-deploy
gate). Both verified locally on 2026-05-29.

### Remaining

- Deploy reverted `index.html` to CloudFront (`/*` invalidation) so live web
  shows the classic layout.
- Next native build (iOS Codemagic / Android `build:android`) copies this same
  `index.html` and ships the redesign — no extra step needed.
