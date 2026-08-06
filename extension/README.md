# cubitt33 browser extension — demo build

Unlisted demo. Shows independent transport and healthcare data alongside a
Rightmove listing, to prove the wedge before committing to the product build.

**Not for publication.** See "Before this could ship" below.

## Load it

1. Chrome → `chrome://extensions`
2. Enable **Developer mode** (top right)
3. **Load unpacked** → select this `extension/` directory
4. Open any Rightmove property page, e.g.
   `https://www.rightmove.co.uk/properties/<id>`
5. Click the **cubitt33** badge, bottom right

Nothing is fetched until the badge is clicked.

## What it shows

Both endpoints already exist in production and take `lat`/`lon`, so this build
needs no backend change and no API key.

**Transport** — `GET /transport?lat=&lon=` (TfL, 1,500 m radius)
- Up to 5 nearest stations, name and distance
- Lines serving each station
- Live line status, shown **only when something is disrupted** (a wall of
  "Good Service" trains the eye to skip the block)
- An explicit outage state, because `backend/lambdas/transport/app.py:41`
  deliberately distinguishes "TfL unreachable" from "no stations nearby"

**Healthcare** — `GET /nhs?lat=&lon=` (OpenStreetMap via Overpass)
- Nearest 3 GP surgeries, pharmacies and hospitals, with distances
- Falls back to nhs.uk search links when Overpass is down

**From the page, no network call** — map-pin coordinates, address, outcode.

## Environment (added 2026-08-06)

`GET /v1/environment?lat=&lon=` - unauthenticated, like `/transport` and `/nhs`.

Listing pages give COORDINATES; every environmental dataset here is keyed by
POSTCODE, so none of it could reach a listing. That endpoint does the reverse
geocode server-side, which is the one thing the extension cannot do for itself.

- **Aircraft noise** - DEFRA Round 4 Lden where measured (~9% of London
  postcodes; the contours are localised lobes around airports)
- **Road noise** - DEFRA Round 4 road Lden (92.2% coverage; roads are everywhere)
- **NO2 and PM2.5** - DEFRA PCM background maps, annual mean, each shown against
  its WHO guideline, because a bare concentration means nothing without one

Every row appears only where a real measurement exists. Absent means the key is
missing, never null and never a default - and what was NOT measured is stated in
a notice rather than left to be assumed.

It is unauthenticated deliberately: an extension is a public artefact, so it
cannot hold a key, and a bundled key would meter every install against one plan.
What it returns is measurements, not the product - no weights, no persona, no
composite score. The scoring engine stays behind the key.

## What it still does not show

| Omitted | Why |
|---|---|
| Sky Score total + components | `/v1/score` is API-key gated and an extension cannot hold a key. `/v1/environment` deliberately returns measurements only. |
| EPC | `/epc` is postcode-keyed; the reverse geocode now exists, so this is a smaller job than it was. `floorArea` also comes back empty (`epc/app.py:186`). |
| Sold prices | Same: postcode-keyed, now unblocked by the reverse geocode. |

## What is already verified

Automated, all wired into `scripts/preflight.sh` so they cannot rot:

- **`tests/extension-extraction.mjs`** - 12 cases over all five extraction
  strategies, including one against a **real saved Rightmove listing**.
  Correct attribution, non-London flagged, out-of-UK and null island rejected.
  No `jsdom`; `extract.js` touches four DOM surfaces and the suite shims those.
- **`tests/extension-e2e.mjs`** - 24 checks driving the real extension in a
  real Chromium, against the real saved listing. Badge injects, nothing fetches
  until clicked, panel renders live TfL and NHS data, attribution present,
  cache hit on a second view, plus the degraded paths: non-London suppresses
  transport with a caveat, an unlocatable page renders nothing at all.
- ESLint clean with `security/detect-unsafe-regex` at **error** for this
  directory, stricter than the repo default.
- Field names match the Lambdas: `transport/app.py:102`, `:135`, `nhs/app.py:134`.

The e2e serves its fixture **at** the rightmove.co.uk URL via request
interception, so the content script's match pattern fires and no request ever
reaches Rightmove.

## How Rightmove actually encodes coordinates

Derived from a saved listing on 2026-08-06, not assumed. Four regex strategies
failed on every real listing before this was understood:

```
window.__PAGE_MODEL = {"data":"[ ...1612 entries... ]","encoding":...}
```

- `data` is a JSON **string** containing JSON, so keys appear escaped as
  `\"latitude\"` - no pattern matching a bare quoted key can hit
- the array is **flattened**: `{"latitude":160,"longitude":161}` holds INDICES,
  so even after unescaping the number beside `latitude` is `160`, not a
  coordinate. `flat[160] === 51.49423`, `flat[161] === -0.18825`
- it is `window.__PAGE_MODEL`, **two** leading underscores

`fromRightmovePageModel()` unpacks this and runs first in the cascade.
`tests/fixtures/rightmove-real-sw5.html` carries that script verbatim, so if
Rightmove changes the format the suite says so.

**Timing is part of the contract.** `run_at` is `document_end`, not
`document_idle`. The page model is transient - present on a fresh load, gone
from the same tab minutes later once React has hydrated. At `document_idle` the
extension arrived after the data left, found nothing, and rendered no badge,
which looks identical to "this page has no coordinates".

## Verification still outstanding

Whether the strategies hold on **other** portals, and on rent/new-build
templates. To check any page:

```
sh scripts/build_extraction_probe.sh | clip
```

Then paste into DevTools on a Rightmove property page (type `allow pasting`
first if Chrome blocks it). It prints the winning strategy, coordinates,
outcode, and an OpenStreetMap link to confirm the pin. Check a **for-sale**, a
**to-rent** and a **new-build** listing - different templates.

On Rightmove, `rightmove-page-model` is the expected winner. Anything else
means the page model changed and the unpacker needs re-deriving. On other
portals any strategy winning is a success - the cascade is the point.

## Known limits

- **Rightmove only.** Zoopla and OnTheMarket need their own adapters.
- **"GP surgeries" is looser than it sounds.** The bucket comes from OSM's
  `amenity=doctors`, which tags private clinics the same as NHS practices - the
  Manchester e2e fixture returns "Skinspace UK" and "Deansgate Hospital" under
  GP surgeries. That is upstream tagging, not our partitioning, but a demo
  audience will read it as an NHS list. Either relabel the bucket honestly
  ("Doctors and clinics") or filter on additional OSM tags before this goes in
  front of anyone who matters.
- **Selectors will rot.** A portal redesign breaks extraction silently. The
  debug line exists so the failure is diagnosable in one glance.
- **No icons.** Chrome requires PNG for extension icons and this repo only has
  SVG, so `manifest.json` omits the `icons` key and Chrome shows a placeholder.
- **Style isolation is by specificity, not Shadow DOM.** Fine for a demo; see
  the note at the top of `content/panel.css` before this goes further.

## Cost

~$0.0000232 per property view (2 API Gateway requests + 2 Lambda invocations at
256 MB). About **$0.02 per 1,000 views**; roughly 420,000 views a month sit
inside Lambda's perpetual free tier. Money is not the constraint at any
plausible scale.

**Overpass is the real ceiling.** `/nhs` proxies OpenStreetMap's Overpass, which
is free but rate-limited, and every extension user reaches it through one Lambda
IP — so we present as a single heavy client rather than many light ones. The
service worker caches on coordinates rounded to 3 dp (~110 m), which collapses
every flat in a block to one upstream call. That cache is why this is safe to
demo; it is not sufficient for a published product.

## Attribution

TfL Open Data and OpenStreetMap (ODbL) both require credit wherever their data
is displayed. Both Lambdas return the correct strings in `sources` and the panel
renders them in its footer. Do not drop that footer.

## Before this could ship publicly

1. ~~**`privacy.html` must be corrected.**~~ **DONE 2026-08-06.** §2d now states
   what is actually configured, and the page is deployed. The Chrome Web Store
   requires a privacy policy URL and this is the page it would cite, so it had
   to be true before any listing. A **store-specific** disclosure is still
   needed covering what the extension itself handles.
2. **Caching must move server-side.** The session cache here dies with the
   browser; a shared DynamoDB cache in front of `/epc`, `/sold-prices` and
   `/nhs` is what actually protects skyscore.co.uk from the extension's traffic.
3. **cubitt33 needs its attorney opinion.** A store listing is a durable public
   first use of the mark.
4. **Portal ToS.** Rightmove prohibits automated extraction. This build's
   posture is deliberately defensive — user-triggered, DOM-read only, no listing
   content transmitted (only a rounded coordinate pair leaves the browser), no
   content hidden or reflowed. That reduces the risk; it does not remove it.
