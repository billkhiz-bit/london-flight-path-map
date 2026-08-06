/* exported extractListing */
// cubitt33 extension — listing extraction (Rightmove).
//
// Turns whatever the page happens to expose into a normalised
// { lat, lon, address, outcode, confidence } object, or null.
//
// THE CENTRAL CONSTRAINT: a content script runs in an ISOLATED WORLD. It shares
// the DOM with the page but NOT the JavaScript context, so `window.PAGE_MODEL`
// — where Rightmove keeps the property's coordinates — is invisible from here.
// Reading it would need a MAIN-world injection, which is both more fragile and
// a more intrusive posture towards a site we are a guest on.
//
// What we CAN see is the DOM, and a <script> element's text is part of the DOM.
// So every strategy below reads *text*, never live page objects. That is also
// why this survives Rightmove's obfuscated CSS class names: we never depend on
// a class name to find data.
//
// Nothing here is transmitted anywhere. The only value that leaves the browser
// is a rounded coordinate pair (see background.js) — never listing content,
// never the address, never the price.
//
// TIMING IS PART OF THE CONTRACT. manifest.json sets run_at: "document_end",
// NOT the more usual "document_idle", and manifest.json cannot carry a comment
// saying why — so it is recorded here.
//
// Rightmove server-renders a `window.__PAGE_MODEL` blob into the HTML and then
// React hydrates over it. That script is TRANSIENT: observed present on a
// freshly loaded listing on 2026-08-06 and absent from the same tab minutes
// later, with `outerHTML.includes('__PAGE_MODEL')` returning false. document_idle
// fires after `load`, by which point hydration may already have removed it — so
// the extension would arrive after the data had gone, find nothing, and render
// no badge, which is indistinguishable from "this page has no coordinates".
//
// document_end runs once the DOM is parsed but before subresources finish, which
// is early enough to read server-rendered markup. If a future change needs even
// earlier access, the next step is document_start plus a DOMContentLoaded hook —
// do not simply move back to idle.

// UK bounding box. A page contains many numbers and some of them are called
// "latitude"; without this a stray match in an analytics blob or an advert
// silently sends the panel to the wrong place, which is worse than showing
// nothing. Rejecting out-of-range coordinates makes a bad match fail loudly.
const UK_BOUNDS = { minLat: 49.8, maxLat: 61.0, minLon: -8.7, maxLon: 1.8 };

// Greater London, approximately. TfL's StopPoint API only knows about London,
// so a Manchester listing would come back with zero stations — which reads as
// "no transport here" when it actually means "wrong data source". The panel
// uses this to caption that case honestly instead of rendering a confident
// emptiness. Same failure class the /transport Lambda already guards against
// for outages (backend/lambdas/transport/app.py:41).
const LONDON_BOUNDS = { minLat: 51.28, maxLat: 51.70, minLon: -0.52, maxLon: 0.34 };

function inBounds(lat, lon, b) {
  return lat >= b.minLat && lat <= b.maxLat && lon >= b.minLon && lon <= b.maxLon;
}

function validCoords(lat, lon) {
  return (
    Number.isFinite(lat) &&
    Number.isFinite(lon) &&
    // Reject exact zeroes: (0, 0) is the classic value for an uninitialised
    // coordinate field in a page's JSON, and it passes a naive finite check.
    //
    // REDUNDANT TODAY and deliberately kept. UK_BOUNDS already excludes it,
    // because latitude 0 is far below minLat — so removing this line does not
    // change any current behaviour, and tests/extension-extraction.mjs cannot
    // isolate it (proven: deleting it leaves the suite green). It stays as
    // defence for the day someone widens UK_BOUNDS to cover another country
    // and silently readmits null island with it.
    !(lat === 0 && lon === 0) &&
    inBounds(lat, lon, UK_BOUNDS)
  );
}

// --- Strategy 0: Rightmove's flattened page model ------------------------
//
// The authoritative source on Rightmove, and the reason every regex strategy
// below failed on real listings. Derived from a saved page on 2026-08-06, not
// from assumption.
//
// The shape:
//
//   window.__PAGE_MODEL = {"data":"[ ...1612 entries... ]","encoding":...}
//
// Three things make this invisible to a naive pattern:
//
//   1. `data` is a JSON STRING containing JSON, so every key in it appears
//      escaped as \"latitude\" — a quote, a backslash, then the word. No
//      pattern matching "latitude" as a bare quoted key will ever hit.
//   2. It is a FLATTENED array. Objects do not hold values, they hold indices
//      into the top-level array: {"latitude":160,"longitude":161} means
//      flat[160] and flat[161]. So even after unescaping, the number sitting
//      next to "latitude" is 160, not a coordinate.
//   3. It is `window.__PAGE_MODEL`, two leading underscores.
//
// Verified: flat[160] === 51.49423, flat[161] === -0.18825, which is
// Collingham Road SW5 — the listing the fixture was saved from.
//
// Cost is one ~100 KB JSON.parse, once, on a page that already parsed it
// itself. Everything is wrapped so a Rightmove format change degrades to the
// regex strategies below rather than throwing.
function fromRightmovePageModel() {
  const script = [...document.querySelectorAll('script:not([src])')].find((s) =>
    s.textContent.includes('__PAGE_MODEL')
  );
  if (!script) return null;

  const raw = script.textContent;
  const start = raw.indexOf('{', raw.indexOf('__PAGE_MODEL'));
  if (start < 0) return null;

  // Balanced-brace scan. The assignment is followed by more script, so the
  // last `}` in the element is not the end of this object. Must track string
  // state and escapes, because the payload is dense with both.
  let depth = 0;
  let inString = false;
  let escaped = false;
  let end = -1;
  for (let i = start; i < raw.length; i++) {
    const ch = raw[i];
    if (escaped) {
      escaped = false;
    } else if (ch === '\\') {
      escaped = true;
    } else if (ch === '"') {
      inString = !inString;
    } else if (!inString) {
      if (ch === '{') {
        depth += 1;
      } else if (ch === '}') {
        depth -= 1;
        if (depth === 0) {
          end = i + 1;
          break;
        }
      }
    }
  }
  if (end < 0) return null;

  let flat;
  try {
    const outer = JSON.parse(raw.slice(start, end));
    flat = typeof outer.data === 'string' ? JSON.parse(outer.data) : outer.data;
  } catch {
    // Malformed or re-encoded: fall through to the regex strategies.
    return null;
  }
  if (!Array.isArray(flat)) return null;

  // Resolve an index reference into the flat array. A direct number is
  // accepted too, in case Rightmove ever inlines the values.
  const deref = (v) => {
    if (typeof v !== 'number') return NaN;
    const target = flat[v];
    return typeof target === 'number' ? target : v;
  };

  const seen = new Set();
  const search = (node, depth2) => {
    if (!node || typeof node !== 'object' || depth2 > 6 || seen.has(node)) return null;
    seen.add(node);

    for (const [key, value] of Object.entries(node)) {
      if (/^lat(itude)?$/i.test(key)) {
        const pair = Object.entries(node).find(([k]) => /^l(on|ng|ongitude)$/i.test(k));
        if (pair) {
          const lat = deref(value);
          const lon = deref(pair[1]);
          if (validCoords(lat, lon)) return { lat, lon };
        }
      }
      if (value && typeof value === 'object') {
        const found = search(value, depth2 + 1);
        if (found) return found;
      }
    }
    return null;
  };

  for (const entry of flat) {
    const found = search(entry, 0);
    if (found) return { ...found, source: 'rightmove-page-model' };
  }
  return null;
}

// --- Strategy A: the page model blob -------------------------------------
// Rightmove serialises the property into a <script> as window.PAGE_MODEL. We
// cannot read the object, but we can read the script's source text. Prefer the
// pattern where latitude and longitude are adjacent keys, which is how a real
// coordinate pair is serialised — two lone "latitude" mentions far apart in a
// document are much more likely to be something else.
function fromScriptBlob() {
  // The `"?` around each value is not defensive padding — it is the whole
  // reason this works. Rightmove serialises coordinates as STRINGS:
  //
  //     "latitude":"51.473422"
  //
  // not as bare numbers. A pattern requiring digits immediately after the colon
  // dies on the opening quote.
  //
  // PROVENANCE, because it matters: this was observed on a live
  // apparentproperties.com listing on 2026-08-06, NOT on Rightmove. Rightmove's
  // own serialisation is still unverified — nobody has run this against one.
  // The quoted form is real and worth handling either way, but do not read this
  // comment as evidence about Rightmove specifically.
  //
  // Both forms are accepted rather than switching to the quoted one: portals
  // differ, and handling both costs one character each.
  const pairPattern =
    /"latitude"\s*:\s*"?(-?\d{1,3}\.\d+)"?\s*,\s*"longitude"\s*:\s*"?(-?\d{1,3}\.\d+)"?/;
  // Some builds order the keys the other way round.
  const reversePattern =
    /"longitude"\s*:\s*"?(-?\d{1,3}\.\d+)"?\s*,\s*"latitude"\s*:\s*"?(-?\d{1,3}\.\d+)"?/;

  for (const script of document.querySelectorAll('script')) {
    // Skip JSON-LD and leave it to fromJsonLd(). querySelectorAll('script')
    // returns ld+json blocks too, and a schema.org Residence carries
    // "latitude"/"longitude" as adjacent keys — so without this the blob
    // strategy matches the JSON-LD text and the panel reports `page-model`
    // for what was really a `json-ld` hit. The coordinates would still be
    // correct, but the strategy label is the drift signal: it exists to say
    // which source is holding up, and a label that cannot distinguish two
    // sources cannot do that. Caught by scripts/build_extraction_probe.sh's
    // shim tests, not by reading.
    const type = (script.getAttribute('type') || '').toLowerCase();
    if (type.includes('ld+json')) continue;

    const text = script.textContent;
    // Real page models are tens of kilobytes; this skips the many tiny inline
    // analytics snippets without scanning each with two regexes.
    if (!text || text.length < 50) continue;

    const forward = text.match(pairPattern);
    if (forward) {
      const lat = parseFloat(forward[1]);
      const lon = parseFloat(forward[2]);
      if (validCoords(lat, lon)) return { lat, lon, source: 'page-model' };
    }

    const reverse = text.match(reversePattern);
    if (reverse) {
      const lon = parseFloat(reverse[1]);
      const lat = parseFloat(reverse[2]);
      if (validCoords(lat, lon)) return { lat, lon, source: 'page-model' };
    }

    // Last resort WITHIN this script: the two keys exist but are not adjacent,
    // e.g. separated by other fields or nested differently. Adjacency was the
    // original guard against pairing a latitude from one object with a
    // longitude from another, so this is deliberately the third attempt rather
    // than the first, and it is still scoped to a single script element —
    // never across the whole document, which is where mismatched pairing gets
    // genuinely dangerous.
    //
    // validCoords is what makes this safe enough to try: a mispaired result
    // almost always lands outside the UK bounding box and is rejected.
    const loneLat = text.match(/"lat(?:itude)?"\s*:\s*"?(-?\d{1,3}\.\d+)"?/);
    const loneLon = text.match(/"l(?:on|ng|ongitude)"\s*:\s*"?(-?\d{1,3}\.\d+)"?/);
    if (loneLat && loneLon) {
      const lat = parseFloat(loneLat[1]);
      const lon = parseFloat(loneLon[1]);
      if (validCoords(lat, lon)) return { lat, lon, source: 'page-model-split' };
    }
  }
  return null;
}

// --- Strategy B: JSON-LD --------------------------------------------------
// schema.org markup is what Rightmove serves to search engines, so it tends to
// be stable across redesigns — the SEO team notices before the users do.
function fromJsonLd() {
  for (const node of document.querySelectorAll('script[type="application/ld+json"]')) {
    let parsed;
    try {
      parsed = JSON.parse(node.textContent);
    } catch {
      // Malformed JSON-LD is common and never worth failing over — try the
      // next block.
      continue;
    }

    // A JSON-LD block can be a single object, an array, or a @graph wrapper.
    const candidates = Array.isArray(parsed) ? parsed : [parsed, ...(parsed['@graph'] || [])];

    for (const item of candidates) {
      const geo = item?.geo;
      if (!geo) continue;
      const lat = parseFloat(geo.latitude);
      const lon = parseFloat(geo.longitude);
      if (validCoords(lat, lon)) return { lat, lon, source: 'json-ld' };
    }
  }
  return null;
}

// --- Strategy C: the static map image ------------------------------------
// The map thumbnail on a listing is a static image whose URL carries the pin
// coordinates. It survives JS changes entirely because it is just an <img>.
function fromStaticMap() {
  for (const img of document.querySelectorAll('img')) {
    // Lazy-loaded images keep the real URL in data-src until they enter the
    // viewport, and the map is usually below the fold on first paint.
    const src = img.src || img.getAttribute('data-src') || '';
    if (!src.includes('staticmap') && !src.includes('maps')) continue;

    const centre = src.match(/[?&](?:center|centre)=(-?\d{1,3}\.\d+)(?:,|%2C)(-?\d{1,3}\.\d+)/i);
    if (centre) {
      const lat = parseFloat(centre[1]);
      const lon = parseFloat(centre[2]);
      if (validCoords(lat, lon)) return { lat, lon, source: 'static-map' };
    }
  }
  return null;
}

// --- Strategy D: Open Graph / geo meta tags ------------------------------
function fromMetaTags() {
  const read = (sel) => document.querySelector(sel)?.getAttribute('content');

  const lat = parseFloat(
    read('meta[property="place:location:latitude"]') || read('meta[name="geo.position"]')?.split(';')[0] || ''
  );
  const lon = parseFloat(
    read('meta[property="place:location:longitude"]') || read('meta[name="geo.position"]')?.split(';')[1] || ''
  );

  if (validCoords(lat, lon)) return { lat, lon, source: 'meta' };
  return null;
}

// --- Address and outcode -------------------------------------------------
// Only used for the panel's "we think this is the place" line, so the user can
// spot a mislocation immediately. Never sent anywhere.
function extractAddress() {
  // The <h1> on a Rightmove detail page is the property address. Falling back
  // to og:title covers layout changes, since the SEO tags outlive the markup.
  const h1 = document.querySelector('h1')?.textContent?.trim();
  if (h1 && h1.length > 3 && h1.length < 200) return h1;

  const og = document.querySelector('meta[property="og:title"]')?.getAttribute('content');
  return og?.trim() || '';
}

// UK outcode: 1-2 letters, 1-2 digits, optional trailing letter. Requires
// uppercase, so "sw11" in prose does not match while a real "SW11" does.
//
// The optional trailing incode group is load-bearing. Rightmove usually shows
// only the outcode ("Battersea, London SW11") but sometimes carries the full
// postcode, and a pattern that stops dead at the outcode would need a boundary
// that a following " 1AA" breaks. Matching the whole postcode and capturing
// only group 1 handles both without a lookahead.
//
// Requiring letters-then-digits also rejects flat numbers: "Flat 4B" is
// digit-then-letter and cannot match.
//
// Two passes rather than one pattern with an optional incode group. Wrapping
// the incode as `(?:\s?\d[A-Z]{2})?` puts quantifiers inside a quantified
// group — star height 2, which security/detect-unsafe-regex correctly rejects
// as ReDoS-shaped. That matters here because the input is page-controlled text,
// not a value we chose. Two flat patterns are both safe and easier to read:
// prefer a full postcode when the page carries one, otherwise take the bare
// outcode Rightmove more usually shows.
function extractOutcode(address) {
  const full = address.match(/\b([A-Z]{1,2}\d{1,2}[A-Z]?)\s?\d[A-Z][A-Z]\b/);
  if (full) return full[1];

  const outcodeOnly = address.match(/\b([A-Z]{1,2}\d{1,2}[A-Z]?)\b/);
  return outcodeOnly ? outcodeOnly[1] : '';
}

/**
 * Read the current listing page.
 * Returns null when no strategy yields a usable coordinate — the caller is
 * expected to render nothing in that case rather than guess.
 */
function extractListing() {
  // Ordered by authority, not convenience. The page model is Rightmove's own
  // structured data; everything after it is inference from whatever the page
  // happens to leak. A cascade is what makes this portable across portals —
  // apparentproperties.com is served entirely by fromScriptBlob, Rightmove
  // entirely by the page-model unpacker, and neither knows about the other.
  const coords =
    fromRightmovePageModel() ||
    fromScriptBlob() ||
    fromJsonLd() ||
    fromStaticMap() ||
    fromMetaTags();

  if (!coords) return null;

  const address = extractAddress();

  return {
    lat: coords.lat,
    lon: coords.lon,
    address,
    outcode: extractOutcode(address),
    // Which strategy won. Surfaced in the panel's debug line because when this
    // breaks after a Rightmove redesign, the first question is always "did we
    // fall through to a weaker strategy, or fail outright?"
    source: coords.source,
    inLondon: inBounds(coords.lat, coords.lon, LONDON_BOUNDS),
  };
}
