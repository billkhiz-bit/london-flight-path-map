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

Every endpoint already exists in production, and all of them are either
coordinate-keyed or reachable from the postcode `/v1/environment` reverse-
geocodes, so this build needs no backend change and no API key.

**Environment** — `GET /v1/environment?lat=&lon=`, detailed in the next section.

**EPC register** — `GET /epc?postcode=` (MHCLG)
- Recent certificates for the postcode, band and lodgement date
- The band distribution for the postcode, so a single certificate has context,
  drawn as seven discrete columns with the MEES threshold (band E, the lowest a
  property may legally be let at) marked. Deliberately **not** a continuous bar:
  `cert.rating` is synthesised from band midpoints upstream, so every C returns
  75 and plotting it would invent a precision the data does not carry

**Sold nearby** — `GET /sold-prices?postcode=` (HM Land Registry Price Paid)
- The recorded sales as a range, with **this listing's asking price marked on
  it**. Where the asking price falls outside the sales entirely the chart says
  so in words, because that is the case where the dots collapse into one blob
  and the spread stops being readable
- Recent transactions, most recent first, with date, price and property type.
  Any field identical across the whole list (Land Registry keys on PAON, so a
  block of flats repeats one address and one type) is stated once above the rows
- **No verdict**: no colour, no "% above average". Land Registry lags completion
  by around two months and is unadjusted for size, condition, floor or lease, so
  position is a fact it supports and "overpriced" is not

### Sales and lettings show different panels (2026-08-08)

The listing's own `channel` (`RES_BUY` / `RES_LET`) already had to be read to
stop a monthly rent being plotted against completed sales. The same fact now
decides what renders at all.

| | Sale | Letting |
|---|---|---|
| Order | Environment, EPC, Sold nearby, Healthcare | **EPC**, Environment, Healthcare |
| Sold nearby | Chart with the asking price marked | **Removed** |
| EPC | Band chart | Band chart **+ MEES line + tenant disclosure** |

**Why Sold nearby goes rather than rendering empty.** Land Registry Price Paid
records *sales*. On a rental it is a column of six-figure sums beside a property
nobody is selling, in a different unit from the only price on the page. An empty
section would still assert that the question was worth asking.

**Why EPC leads instead.** For a buyer the band is context. For a tenant it is
two live facts, neither of which is on the listing page: under MEES a property
in band F or G generally cannot be let on a new tenancy, and the band is a
heating bill the tenant pays on fabric only the landlord can change.

**What it must never say.** No certificate can be tied to the listing — the
extension deliberately never reads the address — so every sentence is about the
*postcode's* lodged certificates and says so. "This flat is band D" is the claim
we are not entitled to make, and it is the one a reader would most like to be
given. There is an e2e assertion whose only job is to fail if that wording ever
appears.

**A null channel keeps the sale layout**, deliberately. An unnecessary Sold
nearby on a rental is noise; a missing one on a sale removes the section most
likely to be why someone opened the panel.

**Verified against a real To Rent listing** (`rightmove-real-letting-nw2.html`,
Ashford Road NW2, saved 2026-08-08). This path shipped first against the SW5
*sale* fixture with `BUY` rewritten to `LET` — which tested a model of
Rightmove against itself, and, found afterwards, also rewrote strings inside
their cookie manifest nobody knew were there. The synthetic variant has been
deleted rather than kept alongside: two fixtures asserting the same thing would
imply two independent proofs where there was one.

**Rental comparables are NOT shown, and this is not an oversight.** There is no
open, postcode-level UK rental dataset — Price Paid is sales only, and ONS
publishes rents at local-authority level. Drawing a borough median in the
sold-price chart's visual grammar would say "here is what things like this go
for near here" while being a materially weaker claim, which is exactly the
failure `decidePresentation()`'s own docstring warns about.

**Healthcare** — `GET /nhs?lat=&lon=` (OpenStreetMap via Overpass)
- Nearest 3 GP surgeries, pharmacies and hospitals, with distances
- Falls back to nhs.uk search links when Overpass is down

~~**Transport**~~ — **dropped 2026-08-06.** Rightmove already prints the nearest
stations with distances on every listing, so the section duplicated the page it
was sitting on. `GET /transport?lat=&lon=` still exists and is still deployed;
nothing about it was wrong, it just had nothing to add here.

**From the page, no network call** — map-pin coordinates, address, outcode, and
since 2026-08-08 the **asking price**.

The price is **read, never transmitted.** The only value that leaves the browser
is still a rounded coordinate pair; the comparison against sold prices happens
in the tab, against a payload already fetched on that coordinate. `extract.js`'s
header comment previously said the price was never read at all, and was
corrected rather than quietly weakened — that sentence is what a Chrome Web
Store listing and `privacy.html` would both rest on.

It is returned **only on a positive `RES_BUY` / `BUY` signal**, never when the
channel is merely absent. On a letting Rightmove's `price` is a *monthly* figure,
so £2,400 pcm would plot at the far left of a range of completed sales and read
as the bargain of the century. That is one field away at all times, so the
default is to withhold.

## How it reads (reworked 2026-08-07, extended 2026-08-08)

**2026-08-08 layout.** Each section leads with a chart that answers its question
at a glance and folds the rows it was built from into a closed `<details>`. The
panel itself collapses to its header on a header click (504px → 48px), because
it is fixed-position over someone else's page and "out of the way" has to mean
genuinely small.

Gotcha worth keeping: **`display: flex` on a `<summary>` removes the `::marker`
box entirely in Chrome**, so `list-style: revert` cannot bring the disclosure
triangle back — there is no marker left to style. "About these readings" had
been rendering with no affordance at all. The panel draws its own triangle now.
Only a screenshot found it; the element and its handler were both correct.


The panel was mostly prose: a real SW5 listing carried four lines of caveat
supporting two numbers, and outside London it showed one measurement under two
notices. Caveats that long stop being read.

- Each measurement gets a **scale bar** showing where it sits against its WHO
  guideline. The domain is 0 to twice the guideline, with the guideline at the
  midpoint — deliberately *not* the observed range across London, which would
  be a number invented at the point of drawing it. So the bar answers "how does
  this compare to the guideline", not "how does this compare to London".
- Over or under is legible from **which side of the tick the dot sits**, so it
  does not depend on colour (WCAG 1.4.1). The `aria-label` says it in words.
- The 0–10 aircraft estimate gets a bar with **no tick and a neutral fill**.
  Colouring it green would assert it is good against a threshold that does not
  exist.
- The DEFRA vintage is a **`2021` tag on the two rows it applies to**, not a
  paragraph beneath rows it has nothing to do with.
- Everything explanatory collapses into one **"About these readings"**
  disclosure. What stays visible is the fact — "(estimated)" in a label, the
  vintage tag, the value, the guideline. What collapses is the justification.
- A source with nothing to say is **one quiet line**, not a heading and a
  sentence. Four dead sources used to cost eight lines and push the data that
  did arrive below the fold.

## Environment (added 2026-08-06)

`GET /v1/environment?lat=&lon=` - unauthenticated, like `/transport` and `/nhs`.

Listing pages give COORDINATES; every environmental dataset here is keyed by
POSTCODE, so none of it could reach a listing. That endpoint does the reverse
geocode server-side, which is the one thing the extension cannot do for itself.

- **Aircraft noise** - DEFRA Round 4 Lden where measured (~9% of London
  postcodes; the contours are localised lobes around airports)
- **Road noise** - DEFRA Round 4 road Lden (92.2% coverage; roads are everywhere)
- **NO2 and PM2.5** - DEFRA PCM background maps, annual mean, each shown against
  its WHO guideline, because a bare concentration means nothing without one.
  **Being loaded as of 2026-08-07 22:09 and not yet complete**: the loader had
  never been run, so these two rows have never rendered for anyone. The load
  works in postcode-string order, so coverage arrives alphabetically - East
  London before South West - and a listing showing no air quality mid-load is
  the frontier, not a fault

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
| EPC floor area | `floorArea` comes back empty from the search API (`epc/app.py:186`), so a £/m² comparison is not available. This is the single field that would let the sold-price chart adjust for size. |

**Corrected 2026-08-08:** this table listed EPC and Sold prices as omitted while
the section above documented both — they were unblocked by the reverse geocode
and shipped, and the table was never updated. A "what we don't do" list that
disagrees with the "what we do" list six paragraphs above it is worse than
absent, because it is the one a reviewer quotes.

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
   needed covering what the extension itself handles — and since 2026-08-08 that
   must state plainly that the **asking price is read from the page and never
   transmitted**. Chrome's data-use declarations ask what is *collected*, and
   "read into a content script, compared locally, never sent" is a different
   answer from both "collected" and "not handled". Get that wording right before
   filing, not after.
2. **Caching must move server-side.** The session cache here dies with the
   browser; a shared DynamoDB cache in front of `/epc`, `/sold-prices` and
   `/nhs` is what actually protects skyscore.co.uk from the extension's traffic.
3. **cubitt33 needs its attorney opinion.** A store listing is a durable public
   first use of the mark.
4. **Portal ToS.** Rightmove prohibits automated extraction. This build's
   posture is deliberately defensive — user-triggered, DOM-read only, no listing
   content transmitted (only a rounded coordinate pair leaves the browser), no
   content hidden or reflowed. That reduces the risk; it does not remove it.
