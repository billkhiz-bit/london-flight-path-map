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
async function fetchEndpoint(path, lat, lon) {
  const url = `${API_BASE}${path}?lat=${lat}&lon=${lon}`;
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

async function fetchPropertyData(lat, lon) {
  const key = cacheKey(lat, lon);

  const cached = await readCache(key);
  if (cached) return { ...cached, fromCache: true };

  // Parallel, not sequential. These are independent upstreams and /nhs is the
  // slow one (~3s via Overpass); running them in series would add TfL's latency
  // on top of it for no reason.
  const [transport, nhs] = await Promise.all([
    fetchEndpoint('/transport', lat, lon),
    fetchEndpoint('/nhs', lat, lon),
  ]);

  const payload = { transport, nhs };

  // Only cache when at least one upstream succeeded. Caching a double failure
  // would pin a broken panel for 6 hours over what may have been a 2-second
  // network blip.
  if (transport.ok || nhs.ok) {
    await writeCache(key, payload);
  }

  return { ...payload, fromCache: false };
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== 'FETCH_PROPERTY_DATA') return false;

  const { lat, lon } = message;
  if (typeof lat !== 'number' || typeof lon !== 'number') {
    sendResponse({ ok: false, error: 'bad-coords' });
    return false;
  }

  fetchPropertyData(lat, lon)
    .then((payload) => sendResponse({ ok: true, ...payload }))
    .catch((err) => sendResponse({ ok: false, error: String(err) }));

  // MUST return true, synchronously, to hold the message channel open for the
  // async sendResponse above. Without it Chrome closes the port the moment this
  // listener returns and the content script's callback fires with `undefined` —
  // the single most common MV3 bug, and a silent one.
  return true;
});
