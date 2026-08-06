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
const VERSION = 'v1.0.16';
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
