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

