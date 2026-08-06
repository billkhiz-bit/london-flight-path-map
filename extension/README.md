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

- ESLint clean, including `security/detect-unsafe-regex` as an **error** (not
  the repo default of `warn`) for this directory. It caught a genuine ReDoS
  star-height problem in the outcode pattern during the build.
- `manifest.json` parses; all three JS files parse.
- Field names rendered by the panel match the Lambdas: stations expose
  `name` / `distance` / `lines` (`transport/app.py:102`), line status exposes
  `name` / `status` (`transport/app.py:135`), NHS items expose
  `name` / `distance` / `fallback` (`nhs/app.py:134`).
- Outcode extraction passes 9 cases including full postcodes (`SW2 5TT` → `SW2`),
  bare outcodes (`W8`), non-London (`M1`), the 4-character `EC1A`, and three
  negatives that must return empty. The first version of that regex silently
  failed every full-postcode case; only running it showed that.

## Verification still outstanding

**No part of the DOM extraction has been run against a live Rightmove page.** It
was written from the outside, so the four strategies in `content/extract.js` are
best-effort and at least one is likely wrong today. There is also no automated
test for them: that needs `jsdom`, which is not currently a dependency, plus
wiring into `scripts/preflight.sh` — an unwired test file would just be another
check that cannot fail. Do this manual pass first:

- [ ] Panel appears on a **for-sale** listing
- [ ] Panel appears on a **to-rent** listing
- [ ] Panel appears on a **new-build** listing (different template)
- [ ] The address echoed in the panel matches the property on screen
- [ ] The debug line (bottom of panel) shows which strategy won — `page-model`
      is the expected winner. `static-map` or `meta` means the primary
      extraction has already drifted
- [ ] Coordinates in the debug line land on the right place when pasted into a
      map
- [ ] Navigating listing → listing without a page reload re-renders the badge
- [ ] A non-London property (try Manchester) shows the healthcare section and
      the transport caveat, **not** an empty transport list
- [ ] Second view of a nearby property shows `· cached` in the debug line

If the badge never appears, open DevTools → Console on the listing page and run
`extractListing()`. It returns `null` when every strategy missed.

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

1. **`privacy.html` must be corrected.** The Chrome Web Store requires a privacy
   policy URL, and §2d currently claims 30-day log retention while all 13 log
   groups are verified `None`. Replacement wording is in
   `DRAFT_security_retention_passage.md` §2b.
2. **Caching must move server-side.** The session cache here dies with the
   browser; a shared DynamoDB cache in front of `/epc`, `/sold-prices` and
   `/nhs` is what actually protects skyscore.co.uk from the extension's traffic.
3. **cubitt33 needs its attorney opinion.** A store listing is a durable public
   first use of the mark.
4. **Portal ToS.** Rightmove prohibits automated extraction. This build's
   posture is deliberately defensive — user-triggered, DOM-read only, no listing
   content transmitted (only a rounded coordinate pair leaves the browser), no
   content hidden or reflowed. That reduces the risk; it does not remove it.
