# Product rules: scale direction, branding, no basemap

> Moved verbatim from `CLAUDE.md` on 2026-10-17 to keep the session-start file small.
> Scores rise and measurements rise; branding; why there is no street basemap.
> Statements are dated as written; re-measure a number before relying on it, and when a
> rule here changes, update the one-line rule in `CLAUDE.md` too.

<!-- CLAUDE.md lines 1057-1115 (2026-10-16) -->
## Scale direction — do NOT "fix" the apparent site/extension disagreement

**Scores rise, measurements rise, and the label names which.** See `METHODOLOGY.md` §11.0.

- **Scores** (0–10 components) run **higher = better** and are labelled with the *good* thing: `Quiet Skies`, `Affordability`, `Liveability`. Site score panel and `/v1/score`.
- **Measurements** run **higher = worse** and are labelled with the *bad* thing: `Road noise 49.5 dB Lden`, `Aircraft noise 2/10 noise`. `/v1/environment` and the extension's Environment section.

So the same postcode reads **`Quiet Skies 8/10` on the site** and **`Aircraft noise 2/10` in the extension**. That is one value under two labels, *not* a divergence: `/v1/environment` returns `aircraftQuietEstimated: 8` and the extension shows `10 − 8`, asserted against the live endpoint in `tests/extension-e2e.mjs` (on an **asymmetric** value — SW5 scores 5, which inverts to itself and cannot detect a missing transform).

The rule is not "noise always goes up" — it is that direction must agree with whatever the number sits *beside*. Until 2026-08-08 the extension rendered a quiet score under a "noise" label, so the longest bar in the section marked the quietest row. Harmonising the two surfaces reintroduces that defect in one direction or the other.

## Branding

Always use "Sky Score" in all public-facing files and UI text.

## Do NOT add Co-Authored-By lines to git commits

## There is NO basemap, and that is a decision (evaluated 2026-08-30)

The map is `d3.geoMercator` + `geoPath` over our own GeoJSON. **No tiles, no map
API, no key, no per-load cost.** The handful of "basemap" mentions in
`index.html` are comments about the grey background, not a tile layer.

`design/map-basemap.html` toggles the same borough data between that vector
ground and an OpenStreetMap raster basemap, so the trade can be seen rather than
argued. Adding a street basemap would mean: a third-party runtime dependency at
the centre of the product, widening the CSP `img-src`, **losing offline** (tiles
cannot be `cache.addAll`'d, and `tests/failure-path.mjs` asserts an offline
launch), permanent provider attribution, and per-load billing if it is Google.
The product argument is separate and stronger: **street detail implies a
precision we do not have**, since every figure published is borough-level.

**2026-10-03: there is a street-map TRIAL, on the front page only (`/preview/` until 2026-10-06, `/` since), and the decision
above still stands for the live map.** Bill asked to trial Ordnance Survey's
maps (Geovation's suggestion, costed in ROADMAP at GBP 0 in tiles). The preview
is where it can be judged without touching the two objections: it is not in the
app shell, so offline launch is not at stake, and its answers are postcode-level
with a pin. `drawStreets()` in `preview/hp-engine.js` lays OS Maps API tiles
under the d3 map by plain web-mercator arithmetic (no MapLibre, no d3-tile).
**No key is in the source**: `/#oskey=<key>` (the fragment since audit M-1) stores a Data Hub key in
that browser and strips it from the URL, the Streets button is hidden without
one, and `tests/front-page.mjs` asserts nothing is ever requested from
`api.os.uk` keyless. The grid is checked against the pin of a known postcode,
because a tile grid one tile out still looks like a map (the flood-georef
lesson). If it ships, ship self-hosted OS Open Zoomstack: no key in a page, no
CSP host, no third party in the visitor's browser (LICENSING.md has the row).

**Two gotchas found building it, both the "graceful failure" shape:**

- **CARTO serves HTTP 200 with a valid 76 KB PNG when unauthenticated** - a
  placeholder stamped "API KEY REQUIRED" on every tile. A health check on status
  and content-type PASSES on a useless tile. **Assert pixels, not status**, if a
  tile provider is ever wired in.
- **A MapLibre `symbol` layer with no `glyphs` URL means the style never
  finishes loading.** Tiles paint perfectly, `isStyleLoaded()` stays false
  forever, and the data layers are never added - a flawless street map carrying
  none of our data, which reads as a design choice rather than a fault. Poll
  readiness; do not hang data layers off a single `load` event.

## The English audit (2026-11-21 to 22)

Bill asked for one after "Whatever your view" on the planes pages "doesn't make sense". Three read-only reviewers
(hand-written pages, generated pages through their builders, JS-written text) found 176 items, every quote matched in
its file by a script: 52 wrong or misleading, 46 broken English, 31 clearer, 47 polish. No figure was wrong; the
words were. Bill's pick, "go with recommended": groups 1-3 in one batch, the 25 privacy/terms items to him one by one,
two calls his ("Reports for an address" or "a postcode"; the planes legend's "CLEAR").

Four root causes, each now held:
- **A registry label slotted into a sentence.** `noiseAuthorityPlain` is a label ('estimated', 'not applicable'), and
  "Your next steps" printed "official not applicable noise contours"; `runwayNote` ran into "..., so noise changes
  between morning and afternoon" for every city, true only of Heathrow's alternation. The steps are now numbered as
  drawn, and `runwayNote` holds the whole cause where there is one, else null.
- **A template with no count-of-1 branch** ("1 council areas score lower", "1 of its postcodes have", "1 more might fit
  but do not publish"). Each now takes the singular.
- **"Measured DEFRA".** The gate caught "DEFRA measured" but not the word before; seven map legends and eight API
  sources lines said "its measured DEFRA Round 4 55 dB Lden footprint". `tests/test_public_wording.py` now refuses
  both orders (not "measured" + "DEFRA's model", where the front page's heading meets its paragraph) and "order of
  magnitude", which is a factor of ten: the COVID caveat is x1.9, "a sense of scale".
- **A "City of" council in a sentence** ("flight paths over City of London"): `in_sentence()` in
  `scripts/build_area_pages.py`, read by the planes builder too.

Found on the way, a fact and not only words: the City of London's sources line said its schools "fall back to a
curated band", but `score_parts` scores no schools part for an English borough without Progress 8 (v3.5 removed the
band as editorial). It now says the schools part is not scored there. "1.3 times lower than the London median" became
"N% below" in all three holders (the map's crime note, `js/panel-findings.mjs`, `build_area_pages.crime_against_london`),
rounded the same way in both languages: Python's `round()` takes ties to even, so the builder uses `int(x + 0.5)`.

