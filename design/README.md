# Design exploration — desktop, 2026-08-30

Nothing in this folder is deployed, referenced by `index.html`, or covered by any
gate. It is a scratch area for looking at desktop layout options. **`make
web-deploy-all` does not touch it**, and it must stay that way until something
here is actually adopted.

## How to look at these

Serve the repo root, then open the pages. They read `/data/*` and
`/js/vendor/d3.v7.min.js`, so they need the repo root as the document root, not
this folder.

```bash
python -m http.server 8932 --bind 127.0.0.1
```

| Page | What it is |
|---|---|
| `desktop-combined.html` | **The current candidate**, and no longer desktop-only. Live site's palette and type, the prototype's metric switching and measurement panel, the mobile view's bordered city containers, a working mobile layout, and live EPC + sold-price lookup. |
| `prototype-desktop.html` | First interactive pass. My own visual direction, not Stitch's. |
| `stitch-live.html` | Stitch's *actual* generated design (its Tailwind config spliced verbatim) wired to live data. |
| `stitch/` | The raw Stitch output, unmodified. Static, invented content. |

## What `desktop-combined.html` combines, and why

Bill's brief, 2026-08-30: he liked the live mobile view; the prototype made it
easier to move between road noise and flood risk and presented the right sidebar
better; but he preferred the **live site's colour scheme** over both Stitch
systems, and liked the **containers around the cities** in the mobile view.

- **Palette and type are lifted verbatim from `index.html`'s `:root`** — not
  reinterpreted. `--bg #e4e3e0`, `--white #fafaf9`, `--orange #f27d26`, JetBrains
  Mono for labels, Inter for prose, loaded from the repo's self-hosted
  `/fonts/fonts.css`.
- **The city chips are `.city-btn` from the live site**: 4px/12px padding, mono
  9px, 1px tracking, `1px solid var(--dark)`, dark fill when active.
- **The metric switcher reuses that same container language**, one row below the
  cities, so the two tiers read as one control surface. The active metric takes
  the **orange** fill rather than dark, so it cannot be confused with the active
  city.
- **The right panel is the prototype's**: per-measurement rows with a value, a
  scale bar carrying a tick at the published guideline, and the source named
  underneath.

## Rules these pages keep, and why they are not cosmetic

Each of these exists because the live product shipped the opposite at some point:

1. **A borough with no reading is drawn hollow with a dashed edge**, never given a
   mid-range colour. Three map fill layers once ended their lookup with
   `|| 'moderate'` and painted seven cities a confident colour meaning a reading
   nobody had taken.
2. **The legend is measured from what actually painted**, and a band that painted
   nothing shows no row. 41 of 99 rendered legend rows once described a band no
   borough on that map carried.
3. **Direction follows the label.** Transport and Healthcare invert the ramp so
   "more is better" reads well; air, road, flood and crime run the other way.
4. **Every value is real**, read from `data/borough-extra.json`. The Stitch output
   invented Scotland and Wales coverage, a population-density metric, "LF rumble"
   and "Peak transient" — none of which Sky Score publishes.

## If any of this is adopted

It goes through the real gates, and one cost is not obvious from a mockup:
`fittedScale()` scales by `MAP_FIT_REF_W`/`MAP_FIT_REF_H`, and each city's
`scale` in `CITY_DATA` was fitted by `scripts/fit_city_projection.py` to the
desktop map box. **Changing that box means refitting all 11 cities**, and
`tests/map-fit.mjs` (90 city/viewport combinations) reds until they are.

These pages sidestep it with `d3.geoMercator().fitExtent(...)`, which frames each
city from its own geometry and needs no constants. That is worth considering on
its own merits, separately from any visual change.

## Round two, after Bill's review

Three things came back: the mobile view failed, and there was no sold-price or
EPC data.

**Mobile is now modelled on the live site rather than merely not breaking.** The
map is the landing surface, the chip rows are horizontal scroll strips instead of
wrapping onto four lines, and the panel is a bottom sheet that boots at
`--sheet-peek` (220px capped at 42dvh, the live site's own value). It must never
boot expanded: Apple rejected build 19 under Guideline 4.0 because a sheet
covered the map. Measured at 852x847: **56% of the viewport is map at boot**, no
horizontal overflow, no covered controls, and tapping a borough opens the sheet
because at that point a result exists and opening is useful.

**EPC and sold prices come from the live API**, `/epc?postcode=` and
`/sold-prices?postcode=`, both unauthenticated (the browser extension uses them
and cannot hold a key). Try `M1 1AE`: 32 certificates and 10 transactions.

**The EPC chart is seven discrete band columns and must stay that way.**
`cert.rating` looks plottable but is synthesised from a band midpoint in the
Lambda, because MHCLG dropped the numeric rating - so every C returns exactly 75
and a continuous bar would claim a precision the data has never had.

**Sold prices show a median of the returned transactions and say so.** They are
recorded sale prices, not an estimate of any particular property, and the copy
says that rather than letting the layout imply a valuation.

Two defects were found by measuring rather than looking, both worth recording:

- **The legend was unreachable on mobile.** `.legend-toggle { display:none }` sat
  at the END of the stylesheet, so equal specificity plus later source order beat
  the media query that showed it. Nothing looked wrong; `getComputedStyle`
  reported `none`.
- **Two city chips read as "covered"** until the check applied the repo's own
  exemption: a control parked outside its own scroller is a scroll case, not an
  occlusion. They were simply scrolled out of the strip.

## Round three

**Mobile is not part of this proposal.** Bill wants the live mobile layout kept,
so the page says so on a phone rather than letting a mobile visitor read it as a
mobile redesign. What renders there is a readable fallback, nothing more.

**Overview is the default view**, matching the live site: neutral boroughs with
airports and flight paths over them. Arrivals orange, departures blue, stroke
weight by frequency. London draws 5 airports and 10 paths; New York 4 and 8.

**The geometry is GENERATED, not copied.**
`scripts/extract_airports_paths.py` parses the `AIRPORTS` and `FLIGHT_PATHS`
constants out of `index.html` into `design/airports-paths.json`. CLAUDE.md is
explicit that these constants are generated rather than transcribed, because the
two holders use different dialects for the same geometry (`coords` against
`coordinates`) and hand-porting a corridor block once threw
`Cannot read properties of undefined (reading 'map')` in five cities at once.
Verified against the live registry: **633 coordinates, an exact match**.

**New York was showing nothing, and that was a real defect.** It holds curated
band strings but only ONE of the six continuous fields (`crimeRate`), so shading
by the default Air Quality painted every borough `null` and the map read as
broken. Now: a measurement a city has no readings for is **disabled and struck
through** with a reason on hover, the view falls back to Overview rather than
drawing an empty map, and Crime still works for New York and paints all five.

**South Yorkshire's zero airports is stated, not implied.** Doncaster Sheffield
closed to commercial flights in 2022, so the legend reads "no airports in this
city" instead of leaving a blank where paths would be. An absence that looks
identical to a failed load is the defect this product keeps auditing itself for.

## Round four

**Airports and flight paths are drawn under every shading**, not only in
Overview - a separate `Overlay: Flight paths` toggle, on by default. Verified
across Overview, air quality, road noise, flood risk and crime: 10 paths, 10
casings and 5 airports in every one, with the legend appending airport, arrival
and departure rows beneath the band rows.

**Each line is drawn twice, and that is the whole trick.** A white casing goes
down first, then the coloured line on top. Without it the orange arrivals
disappear into the orange and red end of the severity ramp: the layer would be
present and unreadable, which is worse than absent, because it looks like it is
working.

**The toggle is disabled, not merely off, where a city has no airports.** South
Yorkshire reports "This city has no airports" on hover. Off and unavailable look
identical on a control that is only ever off, and they mean different things.
