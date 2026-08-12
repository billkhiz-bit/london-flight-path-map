// Sky Score service worker.
//
// Strategy is deliberately mixed by request type, not one-size-fits-all:
//   - Shell HTML: network-first, fall back to cache. Users see fresh
//     deploys when online but the app still launches offline.
//   - Same-origin /js/: network-first, fall back to cache. These URLs are
//     versionless but their *contents* change between deploys — js/api-base.js
//     holds the API host — so cache-first pinned installed PWAs to whichever
//     host was current at install time, dislodgeable only by a byte change to
//     this file (A-0724-M4).
//   - Same-origin static (icons, manifest, /data/ tiles): cache-first.
//     They rarely change and shipping them from cache is faster.
//   - API origins (Lambdas, postcodes.io): NEVER cache — data freshness
//     matters more than offline support, and stale scores would be
//     misleading.
//   - Google Fonts: stale-while-revalidate. Show cached fonts instantly
//     while we fetch updates in the background.
//
// Bump VERSION to force a cache-busting refresh on next activation.
// The activate handler clears any cache that doesn't match the current
// version names, so old shells get garbage-collected.
//
// The cache-first assets still have the stale-forever property /js/ used to
// have: nothing dislodges a precached copy until this file's bytes change.
// manifest.webmanifest and icons/ are rare-changing and cosmetic, so they
// stay cache-first — but bump VERSION in the same commit whenever either
// changes, or installed PWAs keep the old ones indefinitely.

// v1.0.5 (methodology v3.5): data/borough-extra.json changed — corrected crime
// rates plus a new `p8` field. It is NOT precached, but it is same-origin
// static, so the fetch handler serves it CACHE-FIRST out of RUNTIME_CACHE, and
// only the activate handler's version sweep evicts it.
//
// index.html is network-first and would have updated on its own, so without
// this bump a returning visitor got FRESH scoring code against STALE data:
// `ex.p8` undefined, silent fallback to the retired editorial bands, and a site
// showing different borough scores from the ones /v1/score returns. Any future
// change to a file under /data/ needs this same bump for the same reason.
// v1.0.6 (2026-08-03): index.html now derives the SCHOOLS badge from Progress 8
// via schoolBandFromP8() instead of printing the retired Ofsted band. Without a
// bump, a returning visitor keeps the precached v1.0.5 index.html and still sees
// Camden badged 'excellent' against a P8 of -0.03 — the stale-shell failure the
// note above describes, in the very feature it describes it for.
// v1.0.7 (2026-08-03): heliport noise is now weighted by published annual
// movements, so the two air-ambulance pads no longer score like a commercial
// heliport. Affects quiet within 5 km of five rotary sites — 14.1% of London.
// v1.0.8 (2026-08-03): crime rates re-verified against ONS Table C4 — 29 of 33
// boroughs corrected — and the detail panel now explains WHY from the offence
// breakdown instead of asserting "nightlife, tourism, or town centre activity".
// Both index.html and data/borough-extra.json changed, so this bump is required
// twice over.
// v1.0.9 (2026-08-03): post-audit doc-truth pass. The footer said Methodology
// v3.4 while the API returned 3.5, and the City of London crime note contradicted
// itself — "2.2x the London median" beside "nothing stands out" — while crediting
// ONS for a rate ONS explicitly suppresses. Both are in index.html, so returning
// visitors keep them until this bumps.
// v1.0.10 (2026-08-03): the favourites button recomputed its own score from
// retired weights with no liveability term, so the value a user SAVED differed
// from the one shown above the save button - and the favourites Lambda persists
// it, so the wrong number reached DynamoDB. Also drops the 'exact dB' claim the
// noise legend made, which no code path delivers.
// v1.0.11 (2026-08-03): fixes a live breakage plus three website findings.
// pcScore was hoisted to function scope - v1.0.10 shipped it as a const inside
// `if (boroughData)` while the favourites button reads it OUTSIDE that block,
// which threw and took the whole postcode result panel down in production.
// Also: a visible notice when borough data fails to load, the heliport term
// added to the neighbourhood scorer so it agrees with the postcode panel, and
// --yellow darkened to clear WCAG AA on the noise badge.
// v1.0.12 (2026-08-03): the map no longer re-centres on every search, so the
// orange pin visibly MOVES between nearby areas instead of always landing dead
// centre while the map slid underneath it. Fly duration 800ms -> 450ms. Also
// removes 184 em dashes from the deployed pages.
// v1.0.13 (2026-08-03): the ranking table (128 rows) and every saved postcode
// bound click alone, so keyboard, switch and voice users could not activate any
// of them. Now focusable with Enter/Space handlers and visible focus rings.
// v1.0.14 (2026-08-03): borough-extra.json is fetched no-cache (revalidate)
// instead of force-cache. A user was served crime figures from before the
// 2 Aug correction, days after it shipped, because force-cache plus an S3
// object with no Cache-Control let the browser hold it indefinitely - and no
// sw.js bump could evict it, because that is the HTTP cache, not this one.
// v1.0.15 (2026-08-03): dead DEFRA_WMS block removed along with two CSP hosts
// it was the only reason for; 21 school notes now mark any Ofsted grade they
// name as historic (withdrawn Sept 2024, not feeding the score). data/ changed,
// so this bump is required.
// (v1.0.16 has no entry here. It was bumped without one, which is why this log
// is worth keeping: the next reader cannot tell what a returning visitor was
// getting a fresh shell for.)
// v1.0.17 (2026-08-09): Greater Manchester joins as a third city. Both
// index.html and data/borough-extra.json changed - the latter gained a
// `manchester` block - so this bump is required twice over by the rule at the
// top. data/manchester-boroughs.json is new in SHELL_ASSETS, and cache.addAll()
// is atomic, so it must reach the origin BEFORE or WITH this file or the worker
// stops installing entirely.
// v1.0.18 (2026-08-10): locator inset carried role="img" while holding ten
// focusable role="button" markers. An img role is a LEAF, so the markers were
// in the tab order and absent from the accessibility tree at the same time -
// axe scores it `nested-interactive`, serious, and it failed the WCAG gate on
// two pages. Changed to role="group". index.html is in SHELL_ASSETS, so this
// bump is required by the rule at the top; without it an installed PWA keeps
// serving the inaccessible shell indefinitely.
// v1.0.19 (2026-08-10): London's 33 `trend` values corrected to HM Land
// Registry HPI 2026-05, which is what CITY_PROVENANCE already claimed they
// were. They matched no HPI month at all, while the same test identifies the
// price source at 33/33, so the growth input was reading from something nobody
// could name. Also in this version: scoring went lazy and registry-driven - recalcAllScores
// and hydrateBoroughExtra no longer name any city. index.html changed again,
// and v1.0.18 has already SHIPPED, so a returning visitor holds that shell
// precached; without this bump they would keep the pre-refactor page, including
// the autocomplete that offers London boroughs while you are in Manchester.
// v1.0.20 (2026-08-10): the locator inset is no longer UK-only - New York draws
// the contiguous United States instead of hiding the panel. index.html changed
// and v1.0.19 has already shipped, so without this bump a returning visitor
// keeps the shell that has no USA silhouette in it. data/usa-locator.json is
// deliberately NOT in SHELL_ASSETS (a decoration must not be able to stop an
// atomic cache.addAll()), so it needs `make data-deploy`, not this bump.
// v1.0.21 (2026-08-10): six Core Cities regions reach the consumer site, so
// six boundary files join SHELL_ASSETS. DEPLOY ORDER IS LOAD-BEARING:
// cache.addAll() is atomic, so `make data-deploy` MUST land these at the origin
// before this file ships, or the service worker fails to install for EVERY
// city. index.html changed too, and v1.0.20 has already shipped.
// v1.0.22 (2026-08-10): corridor polylines resampled to a common 1 km interval
// in BOTH holders. Corridor distance is measured to the nearest waypoint, so a
// coarse polyline reads as further from the corridor and therefore quieter -
// shipping the Lambda's densified geometry without the site's would make the
// two disagree on every neighbourhood quiet score. index.html is in
// SHELL_ASSETS and v1.0.21 has already shipped.
// v1.0.23 (2026-08-11): index.html only, and the bump is what makes the fix
// REACH anyone. Six of nine cities threw on selection (a second city registry
// held center/scale for three of them) and the city chips overflowed the
// viewport unreachably on every phone. index.html is in SHELL_ASSETS and served
// CACHE-FIRST, so without this bump a returning visitor or an installed PWA
// keeps the broken copy indefinitely - the deploy would look done and change
// nothing for exactly the people who use the site most. No SHELL_ASSETS entries
// added, so there is no deploy-order hazard this time.
// v1.0.24 (2026-08-11): the three borough fill layers stopped inventing values
// for cities with no reading, and road noise + air quality are now DERIVED from
// DEFRA for every city. index.html and data/borough-extra.json both change.
// borough-extra.json is deliberately NOT in SHELL_ASSETS and is served
// no-cache, but index.html is cache-first, so without this bump a returning
// visitor keeps a build that reads fields the new data file no longer arranges
// the same way.
// v1.0.25 (2026-08-11): flood risk derived from the Environment Agency for all
// 73 UK boroughs, completing the three fill layers. index.html and
// data/borough-extra.json both change; index.html is cache-first.
// v1.0.26 (2026-08-11): 448 neighbourhoods across seven UK cities, up from 85,
// plus two search fixes that had never worked - generated-city area keys were
// unreachable by search, and every South Yorkshire search threw on a city with
// no airport. All inline in index.html, which is cache-first.
// v1.0.27 (2026-08-11): methodology v3.6 - transport derived from NaPTAN for all
// 81 boroughs, a SCORING input at 0.25 of liveability. 52 of 86 boroughs move.
// index.html carries the version string and data/borough-extra.json carries the
// values, so both change and this bump is required by the rule at the top.
// v1.0.28 (2026-08-11): methodology v3.7 - healthcare derived from the NHS ODS
// register for all 81 boroughs. 78 of 86 boroughs now score on all four
// liveability inputs, up from 38. index.html carries the version string and
// borough-extra.json the values, so both change.
// v1.0.29 (2026-08-11): methodology v3.8 - the aircraft distance ladder is
// scaled by each airport's measured DEFRA 55 dB Lden footprint instead of being
// applied at Heathrow's size everywhere. 31 borough bands move, all upward.
//
// The POSTCODE tier moves too, London included: it runs its own copy of the
// ramp client-side, and leaving it unscaled would have contradicted the
// corrected borough band by up to 4.0 points. Validated on the 35,352 London
// postcodes DEFRA measured - mean absolute error 3.230 -> 1.879. index.html
// holds both the impact bands and the client-side ramp, so a stale shell would
// publish different numbers from /v1/score.
// v1.0.30 (2026-08-11): Leicester and Teesside reach the consumer site, taking
// it from nine cities to eleven and matching the API exactly. Two new boundary
// files join SHELL_ASSETS, and cache.addAll() is atomic - they must reach the
// origin BEFORE or WITH this file or the worker stops installing for EVERY
// city, not just these two. `make data-deploy` covers them.
//
// Also here: the city strip's bound and fade moved from the <=900px block to
// the base rule. Eleven chips ran off the edge at 901px, where the phone fix
// did not reach, so `Greater Manchester` sat at 806..906px in a 901px window
// with the map container clipping it and nothing scrollable around it.
// v1.0.31 (2026-08-12): 285 postcode districts across nine city-regions gained a
// curated area name, so a returning visitor on a precached shell would keep
// seeing thirty-five rows labelled "Birmingham" while a new one sees Edgbaston,
// Harborne and Selly Oak. index.html is in SHELL_ASSETS, so this bump is what
// actually delivers the labels. No new SHELL_ASSETS entries: the corroboration
// evidence (data/district-msoa-names.json) is a build-time artefact and is
// never fetched by the page.
const VERSION = 'v1.0.31';
const SHELL_CACHE = `sky-score-shell-${VERSION}`;
const RUNTIME_CACHE = `sky-score-runtime-${VERSION}`;

// Pre-cached on install. Just enough for the shell to render offline.
// We deliberately keep this small — the heavier prototype assets are
// lazy-cached on first visit (see fetch handler).
//
// /js/api-base.js is deliberately NOT here. Precaching it froze the API host
// at install time for every installed PWA, and neither a CloudFront
// invalidation nor a re-upload of the file could shift it — only a byte
// change to this worker. It is served network-first instead (A-0724-M4).
// d3 and the borough boundaries ARE precached, unlike api-base.js, because
// both are content-stable: d3 is version-pinned in its filename, and the
// boundary files only change when their source vintage rolls (regenerate with
// scripts/build_london_boroughs.py / build_nyc_boroughs.mjs and bump VERSION
// in the same commit).
// All three were third-party requests until 2026-07-30; the London boundaries
// in particular were a 19.2 MB fetch from raw.githubusercontent.com that
// init() awaited before revealing the app, so a slow network held first
// paint indefinitely. Precaching them is what makes an offline launch
// actually render a map rather than an empty shell.
//
// NYC is precached too even though London is the default city: at 238 KB it
// is a fifth of the shell, and the alternative is that switching city is the
// one interaction that silently needs the network. Note cache.addAll() is
// atomic — if any entry here 404s the worker does not install at all, so a
// new asset must be deployed before, or with, this file.
const SHELL_ASSETS = [
  '/',
  '/index.html',
  '/manifest.webmanifest',
  '/icons/icon.svg',
  '/icons/icon-maskable.svg',
  '/js/vendor/d3.v7.min.js',
  '/data/london-boroughs.json',
  '/data/nyc-boroughs.json',
  // Greater Manchester, added 2026-08-09 with the third city. DEPLOY ORDER IS
  // LOAD-BEARING: cache.addAll() is atomic, so shipping this sw.js before the
  // data file exists at the origin makes the service worker fail to INSTALL AT
  // ALL, taking offline support for all three cities with it. `make
  // data-deploy` before `make pwa-deploy`, exactly as the fonts do.
  '/data/manchester-boroughs.json',
  '/data/westmidlands-boroughs.json',
  '/data/westyorkshire-boroughs.json',
  '/data/southyorkshire-boroughs.json',
  '/data/merseyside-boroughs.json',
  '/data/tyneandwear-boroughs.json',
  '/data/bristol-boroughs.json',
  '/data/leicester-boroughs.json',
  '/data/teesside-boroughs.json',
  // Self-hosted fonts, 2026-08-05. Only the two families index.html actually
  // uses — Geist is for pricing/changes/api and is not part of the app shell.
  // These are precached rather than left to the runtime because they replaced
  // cross-origin fonts that this SW used to stale-while-revalidate, so leaving
  // them out would make the offline shell render worse than before the change.
  '/fonts/fonts.css',
  '/fonts/inter.woff2',
  '/fonts/jetbrains-mono.woff2',
];

// Origins where we always go to the network — caching scores or
// postcode lookups would be misleading for users.
const NEVER_CACHE_ORIGINS = [
  'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com',
  'https://api.postcodes.io',

];

// Cross-origin assets where stale-while-revalidate is appropriate.
// Emptied 2026-08-05: both entries were the Google Fonts hosts, and the fonts
// are now self-hosted under /fonts/ and precached in SHELL_ASSETS above. Kept
// as an empty list rather than deleted because the fetch handler still branches
// on it and a future cross-origin asset belongs here.
const SWR_ORIGINS = [];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL_ASSETS))
      // skipWaiting lets a new SW take control immediately on next page load
      // without waiting for all tabs to close. Combined with clients.claim()
      // in activate, deploys propagate within one refresh cycle.
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k !== SHELL_CACHE && k !== RUNTIME_CACHE)
            .map((k) => caches.delete(k))
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  // SWs only handle GETs cleanly; POST/PUT/DELETE flow straight through.
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // API origins: don't intercept at all. The browser handles them as if
  // there were no SW — which is what we want for fresh data.
  if (NEVER_CACHE_ORIGINS.includes(url.origin)) return;

  // Navigations / same-origin HTML: network-first.
  if (
    url.origin === self.location.origin &&
    (req.mode === 'navigate' || req.destination === 'document')
  ) {
    event.respondWith(networkFirst(req));
    return;
  }

  // Same-origin /js/: network-first. Versionless URLs with mutable contents
  // (see header note), so the freshest copy must win whenever there is a
  // network; the cache is the offline fallback only.
  if (url.origin === self.location.origin && url.pathname.startsWith('/js/')) {
    event.respondWith(networkFirstAsset(req));
    return;
  }

  // Same-origin static assets: cache-first.
  if (url.origin === self.location.origin) {
    event.respondWith(cacheFirst(req));
    return;
  }

  // Google Fonts (and other declared SWR origins): stale-while-revalidate.
  if (SWR_ORIGINS.includes(url.origin)) {
    event.respondWith(staleWhileRevalidate(req));
    return;
  }

  // Default: pass-through. Don't intercept random cross-origin fetches.
});

async function networkFirst(req) {
  try {
    const fresh = await fetch(req);
    // Only cache successful responses — a CloudFront/S3 error page must
    // never overwrite the last-good offline shell (A-0724-I1).
    if (fresh.ok) {
      const cache = await caches.open(SHELL_CACHE);
      cache.put(req, fresh.clone());
    }
    return fresh;
  } catch {
    const cached = await caches.match(req);
    if (cached) return cached;
    // Last-resort fallback: the cached index.html. Better to show a
    // shell with stale data than a browser-default offline page.
    const fallback = await caches.match('/index.html');
    if (fallback) return fallback;
    return new Response('Offline', { status: 503, statusText: 'Offline' });
  }
}

// Network-first for versionless same-origin assets. Differs from
// networkFirst() in two ways: it writes to RUNTIME_CACHE rather than the
// offline shell, and it never falls back to /index.html — handing an HTML
// body to a <script src> fails louder and weirder than a 504.
async function networkFirstAsset(req) {
  try {
    // A plain fetch() inside a SW still reads the HTTP cache, so a CloudFront
    // or browser TTL would quietly re-create the staleness this strategy
    // exists to remove. 'no-cache' forces a revalidation; 304s still satisfy
    // it, so the extra round-trip stays cheap.
    const fresh = await fetch(req, { cache: 'no-cache' });
    if (fresh.ok) {
      const cache = await caches.open(RUNTIME_CACHE);
      cache.put(req, fresh.clone());
      return fresh;
    }
    // A 403/404 mid-deploy (this repo's PWA assets 403'd for weeks once)
    // must not win over a known-good cached copy — the read-side twin of
    // the A-0724-I1 write guard.
    const cached = await caches.match(req);
    return cached || fresh;
  } catch {
    const cached = await caches.match(req);
    if (cached) return cached;
    return new Response('', { status: 504, statusText: 'Offline' });
  }
}

async function cacheFirst(req) {
  const cached = await caches.match(req);
  if (cached) return cached;
  try {
    const fresh = await fetch(req);
    if (fresh.ok) {
      const cache = await caches.open(RUNTIME_CACHE);
      cache.put(req, fresh.clone());
    }
    return fresh;
  } catch {
    return new Response('', { status: 504, statusText: 'Offline' });
  }
}

async function staleWhileRevalidate(req) {
  const cache = await caches.open(RUNTIME_CACHE);
  const cached = await cache.match(req);
  const fetchPromise = fetch(req)
    .then((fresh) => {
      if (fresh.ok) cache.put(req, fresh.clone());
      return fresh;
    })
    .catch(() => cached); // network down: silently fall back to cache
  return cached || fetchPromise;
}
