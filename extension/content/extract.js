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

// --- Strategy A: the page model blob -------------------------------------
// Rightmove serialises the property into a <script> as window.PAGE_MODEL. We
// cannot read the object, but we can read the script's source text. Prefer the
// pattern where latitude and longitude are adjacent keys, which is how a real
// coordinate pair is serialised — two lone "latitude" mentions far apart in a
// document are much more likely to be something else.
function fromScriptBlob() {
  const pairPattern =
    /"latitude"\s*:\s*(-?\d{1,3}\.\d+)\s*,\s*"longitude"\s*:\s*(-?\d{1,3}\.\d+)/;
  // Some builds order the keys the other way round.
  const reversePattern =
    /"longitude"\s*:\s*(-?\d{1,3}\.\d+)\s*,\s*"latitude"\s*:\s*(-?\d{1,3}\.\d+)/;

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
  const coords =
    fromScriptBlob() || fromJsonLd() || fromStaticMap() || fromMetaTags();

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
