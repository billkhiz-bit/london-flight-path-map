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

## What it deliberately does not show

| Omitted | Why |
|---|---|
| Sky Score total + components | `/v1/score` takes postcode or borough, never lat/lon. Needs the reverse-geocode path. |
| EPC | `/epc` is postcode-keyed, same blocker. `floorArea` also comes back empty (`epc/app.py:186`) so no £/sq ft without a second upstream call. |
| Sold prices | `/sold-prices` is postcode-keyed, same blocker. |
| Aircraft noise | DEFRA quarantine stands. 89.5% of London sits outside the aircraft contours and 98% of postcodes score exactly 10.0. This is the number users would trust most and the one we can least defend. |

## What is already verified

Automated, all wired into `scripts/preflight.sh` so they cannot rot:

- **`tests/extension-extraction.mjs`** - 9 cases over the four extraction
  strategies: correct attribution, non-London flagged, out-of-UK and null
  island rejected. No `jsdom`; `extract.js` touches four DOM surfaces and the
  suite shims exactly those.
- **`tests/extension-e2e.mjs`** - 18 checks driving the real extension in a
  real Chromium. Badge injects, nothing fetches until clicked, panel renders
  live TfL and NHS data, attribution present, cache hit on a second nearby
  listing. Measured: transport paints in **852 ms**, cached view in **37 ms**.
- ESLint clean with `security/detect-unsafe-regex` at **error** for this
  directory, stricter than the repo default.
- Field names match the Lambdas: `transport/app.py:102`, `:135`, `nhs/app.py:134`.

The e2e serves its fixture **at** the rightmove.co.uk URL via request
interception, so the content script's match pattern fires and no request ever
reaches Rightmove.

## Verification still outstanding

**One thing, and only one: whether Rightmove's real markup still looks like the
fixture.** Everything else above is now covered automatically. That single
question needs a browser on a live listing:

```
sh scripts/build_extraction_probe.sh | clip
```

Then paste into DevTools on a Rightmove property page (type `allow pasting`
first if Chrome blocks it). It prints the winning strategy, coordinates,
outcode, and an OpenStreetMap link to confirm the pin. Check a **for-sale**, a
**to-rent** and a **new-build** listing - different templates.

`page-model` is the expected winner. Anything else means the primary strategy
has drifted and should be re-derived.

## Known limits

- **Rightmove only.** Zoopla and OnTheMarket need their own adapters.
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
