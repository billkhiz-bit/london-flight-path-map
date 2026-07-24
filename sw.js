// Sky Score service worker.
//
// Strategy is deliberately mixed by request type, not one-size-fits-all:
//   - Shell HTML: network-first, fall back to cache. Users see fresh
//     deploys when online but the app still launches offline.
//   - Same-origin static (icons, manifest, /js/, /data/ tiles): cache-
//     first. They rarely change and shipping them from cache is faster.
//   - API origins (Lambdas, postcodes.io): NEVER cache — data freshness
//     matters more than offline support, and stale scores would be
//     misleading.
//   - Google Fonts: stale-while-revalidate. Show cached fonts instantly
//     while we fetch updates in the background.
//
// Bump VERSION to force a cache-busting refresh on next activation.
// The activate handler clears any cache that doesn't match the current
// version names, so old shells get garbage-collected.

const VERSION = 'v1.0.1';
const SHELL_CACHE = `sky-score-shell-${VERSION}`;
const RUNTIME_CACHE = `sky-score-runtime-${VERSION}`;

// Pre-cached on install. Just enough for the shell to render offline.
// We deliberately keep this small — the heavier prototype assets are
// lazy-cached on first visit (see fetch handler).
const SHELL_ASSETS = [
  '/',
  '/index.html',
  '/manifest.webmanifest',
  '/icons/icon.svg',
  '/icons/icon-maskable.svg',
  '/js/api-base.js',
];

// Origins where we always go to the network — caching scores or
// postcode lookups would be misleading for users.
const NEVER_CACHE_ORIGINS = [
  'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com',
  'https://api.postcodes.io',
  'https://environment.data.gov.uk',
];

// Cross-origin assets where stale-while-revalidate is appropriate.
const SWR_ORIGINS = ['https://fonts.googleapis.com', 'https://fonts.gstatic.com'];

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
