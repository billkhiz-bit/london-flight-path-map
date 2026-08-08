// cubitt33 extension — service worker.
//
// The only component that talks to the network. The content script is the
// untrusted half (it shares a tab with Rightmove's own JavaScript), so all
// fetching lives here. For this demo build there is no API key to protect —
// /transport and /nhs are both unauthenticated (backend/template.yaml has no
// ApiKeyRequired on either route) — but keeping the split now means adding
// /v1/score later is a one-line change rather than a refactor.

const API_BASE = 'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod';

// Coordinate precision for the cache key. 3 dp is ~110 m at London's latitude,
// so every flat in the same block collapses to one cache entry.
//
// This is not a micro-optimisation, it is the thing that keeps the extension
// inside OOM's Overpass usage policy. /nhs proxies Overpass, and every user of
// this extension reaches Overpass through ONE Lambda IP — so we present as a
// single heavy client rather than many light ones. People browse listings in
// clusters (same street, same area, ten tabs), which is exactly the access
// pattern this cache is shaped for.
const COORD_PRECISION = 3;

// Cache lifetime. Station locations and GP surgeries change on a timescale of
// years; TfL *line status* changes in minutes, but for a property-buying
// decision the durable facts are the ones that matter. 6 hours is a compromise
// that keeps the panel feeling live without hammering upstreams.
const CACHE_TTL_MS = 6 * 60 * 60 * 1000;

function cacheKey(lat, lon) {
  return `d:${lat.toFixed(COORD_PRECISION)},${lon.toFixed(COORD_PRECISION)}`;
}

async function readCache(key) {
  try {
    const stored = await chrome.storage.session.get(key);
    const hit = stored[key];
    if (!hit) return null;
    // Date.now() is compared against a timestamp we wrote ourselves, so clock
    // skew between machines is not a concern here.
    if (Date.now() - hit.storedAt > CACHE_TTL_MS) return null;
    return hit.payload;
  } catch {
    // storage.session can throw if the quota is exceeded or the API is
    // unavailable. A cache miss is always a safe answer, so swallow and refetch
    // rather than failing the user's request over a caching problem.
    return null;
  }
}

async function writeCache(key, payload) {
  try {
    await chrome.storage.session.set({ [key]: { storedAt: Date.now(), payload } });
  } catch {
    // Same reasoning as readCache — a failed write must never break the panel.
  }
}

// One endpoint fetch. Never throws: the panel needs to render partial results
// (transport up, NHS down) rather than an all-or-nothing error, so a failure
// here becomes a value, not an exception.
async function fetchEndpoint(path, query) {
  const url = `${API_BASE}${path}?${new URLSearchParams(query)}`;
  try {
    const res = await fetch(url, {
      headers: { Accept: 'application/json' },
      // 20s. /nhs has a 45s Lambda timeout because Overpass is slow, but a
      // property card that spins for 45 seconds is a card nobody reads. Giving
      // up early and saying so is better UX than an honest-but-endless wait.
      signal: AbortSignal.timeout(20000),
    });
    if (!res.ok) {
      return { ok: false, error: `HTTP ${res.status}` };
    }
    return { ok: true, data: await res.json() };
  } catch (err) {
    // AbortError (our timeout) and TypeError (network down / DNS) both land
    // here. The panel only needs to know it failed, not how.
    return { ok: false, error: err.name === 'TimeoutError' ? 'timeout' : 'unreachable' };
  }
}

// ONE endpoint per message, deliberately.
//
// The first version fetched both under a single Promise.all and answered once
// both had settled. TfL returns in about a second; /nhs goes through Overpass,
// which is why that Lambda carries a 45s timeout — so the panel sat on
// "Loading…" for up to half a minute with the transport data already in memory,
// and showed nothing at all if Overpass hung. Measured in tests/extension-e2e.mjs
// against a live Overpass outage, which is exactly when it hurts most.
//
// Splitting the request lets the panel paint each section the moment its own
// upstream answers, so a slow or dead Overpass costs the healthcare section
// only. It also makes the cache per-endpoint, so a working /transport is not
// re-fetched just because /nhs failed alongside it.
// Two families, and the difference matters to the caller.
//
// COORDINATE-KEYED endpoints can be called immediately from what the listing
// page yields. POSTCODE-KEYED ones cannot: a listing gives a point, not a
// postcode, so they have to wait for /v1/environment to reverse-geocode one.
// panel.js chains them accordingly.
//
// /transport was removed 2026-08-06. Rightmove already prints nearest stations
// with distances on every listing, so that section duplicated the page it sat
// on. Being useful here means showing what the portal does not.
const ENDPOINTS = {
  environment: { path: '/v1/environment', key: 'coords' },
  nhs: { path: '/nhs', key: 'coords' },
  epc: { path: '/epc', key: 'postcode' },
  soldPrices: { path: '/sold-prices', key: 'postcode' },
};

async function fetchOne(name, { lat, lon, postcode }) {
  const spec = ENDPOINTS[name];
  if (!spec) return { ok: false, error: 'unknown-endpoint' };

  let query;
  let key;
  if (spec.key === 'postcode') {
    if (!postcode) return { ok: false, error: 'no-postcode' };
    query = { postcode };
    // Keyed on the postcode, not the coordinate: two listings on the same
    // postcode share one answer, which is the whole point of these two.
    key = `p:${postcode.replace(/\s+/g, '').toUpperCase()}:${name}`;
  } else {
    query = { lat, lon };
    key = `${cacheKey(lat, lon)}:${name}`;
  }

  const cached = await readCache(key);
  if (cached) return { ...cached, fromCache: true };

  const result = await fetchEndpoint(spec.path, query);

  // Only cache a success. Caching a failure would pin a broken section for six
  // hours over what may have been a two-second blip — and Overpass outages are
  // exactly that shape.
  if (result.ok) await writeCache(key, result);

  return { ...result, fromCache: false };
}

// The bundled ONS borough rent reference, served from HERE rather than fetched
// by the content script.
//
// A content script can only fetch an extension file if it is declared in
// `web_accessible_resources`, which also exposes it to the HOST PAGE - every
// site matching our patterns could then read it. The service worker has no such
// restriction on its own package, so serving it over the existing message
// channel keeps the file private to the extension and the manifest unchanged.
//
// Memoised: ~275 KB parsed once per worker lifetime, not once per listing.
let rentsPromise = null;
function loadRents() {
  if (!rentsPromise) {
    rentsPromise = fetch(chrome.runtime.getURL('data/london-rents.json'))
      .then((r) => (r.ok ? r.json() : null))
      // A missing or unparseable dataset must cost the rent line only. It is
      // one optional row on one listing type; it is not worth a dead panel.
      .catch(() => null);
  }
  return rentsPromise;
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === 'GET_RENTS') {
    loadRents()
      .then((data) => sendResponse(data ? { ok: true, data } : { ok: false, error: 'no-dataset' }))
      .catch(() => sendResponse({ ok: false, error: 'no-dataset' }));
    return true;
  }
  if (message?.type !== 'FETCH_ENDPOINT') return false;

  const { endpoint, lat, lon, postcode } = message;
  const needsCoords = ENDPOINTS[endpoint]?.key !== 'postcode';
  if (needsCoords && (typeof lat !== 'number' || typeof lon !== 'number')) {
    sendResponse({ ok: false, error: 'bad-coords' });
    return false;
  }

  fetchOne(endpoint, { lat, lon, postcode })
    .then((payload) => sendResponse(payload))
    .catch((err) => sendResponse({ ok: false, error: String(err) }));

  // MUST return true, synchronously, to hold the message channel open for the
  // async sendResponse above. Without it Chrome closes the port the moment this
  // listener returns and the content script's callback fires with `undefined` —
  // the single most common MV3 bug, and a silent one.
  return true;
});
