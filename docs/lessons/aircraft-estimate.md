# The aircraft (Quiet Skies) estimate

> Moved verbatim from `CLAUDE.md` on 2026-10-17 to keep the session-start file small.
> AIP-derived flight paths and the fitted weights, the near-field contour floor, DEFRA coverage, corridor spacing, the per-airport ladder, the validation set, cities with no airport.
> Statements are dated as written; re-measure a number before relying on it, and when a
> rule here changes, update the one-line rule in `CLAUDE.md` too.

<!-- CLAUDE.md lines 186-268 (2026-10-16) -->
> ## LONDON'S FLIGHT PATHS ARE DERIVED FROM THE UK AIP - v5.3, 2026-09-26
>
> They were HAND-DRAWN until then, and a Reddit reply caught it: Ockham and
> Bovingdon ran due north-south into two east-west runways, and the departures
> fanned off the runway end where the published routes run straight ahead.
> **`scripts/build_flight_paths.py`** now generates both holders
> (`FLIGHT_PATHS_LONDON` in the Lambda, `FLIGHT_PATHS` in index.html, between
> `FLIGHT-PATHS-LONDON` markers) from the checked-in
> **`data/flight-procedures.json`**: every runway's final approach to 3,000 ft
> on its published glide path, Heathrow's NPRs from the wording of EGLL AD 2.21
> para 8, London City's departures from its RNAV SID coding tables. `--fetch`
> is the network half (AIP host needs a browser UA; WebFetch truncates the page,
> curl does not); `--check` is BLOCKING. **Do not hand-edit between the
> markers.** Stack-to-final is radar-vectored and deliberately NOT drawn.
>
> **The geometry was not the main error - the WEIGHT was.** Measured before
> deciding: the correct AIP lines at full weight scored WORSE against DEFRA than
> the hand-drawn ones (2.16 vs 1.97), because the airport and corridor terms
> double-count near every runway. `CORRIDOR_WEIGHT = 0.3` (three holders: the
> Lambda and both ramps in index.html, compared by
> `test_corridor_weight_matches_the_site`) is FITTED by
> `scripts/fit_corridor_weight.py` on a train half of 26,233 DEFRA-measured
> postcodes and reported on the other half: 2.36 -> 1.43, every city improves.
> **DEFRA sets the SIZE of the penalty, never the geometry** - it only maps the
> strip around the runway, so it rewards lines that hug the axis.
> **v5.4 extends it to all nine other UK airports** (finals everywhere; SID
> coding-table departures only at BHX and NCL - the other six publish
> conventional SIDs whose charts do not extract, and Teesside publishes none;
> MAN 23L / CWL 12 take their RNP charts' VPA). `AIRPORTS[...]['cities']` is a
> LIST (EMA feeds Leicester and Nottingham); `HOLDERS[...]['site']` is None for
> the two API-only cities. It left DEFRA error unchanged at 1.431.
>
> **v5.5 (2026-10-01): the AIRPORT term is runway-shaped, not a circle.**
> `airport_distance_km()` (Lambda) / `runwayShapedKm()` (both site ramps) read
> `sqrt(along^2 + (AIRPORT_SHAPE_K * side)^2)` across each airport's runway
> axis, `AIRPORT_SHAPE_K = 4`, and **`CORRIDOR_WEIGHT` is 0.5 now, not 0.3**.
> `RUNWAY_AXIS_DEG` is GENERATED into both holders by `build_flight_paths.py`
> (`RUNWAY-AXES` markers, under the same blocking `--check`); LGW/STN/LTN carry
> `not-drawn` runway-only records for it. **The pair is fitted together by
> `scripts/fit_airport_shape.py`** (advisory `--check` in preflight, which
> REPLACED `fit_corridor_weight.py --check`: that unconstrained fit now returns
> 0.35 against a correct 0.5). **The fit's rule is PER CITY: no city may come to
> read quieter than DEFRA.** Pooled, k = 6 / w = 0.5 looked best and neutral
> (-0.01) while reading quieter than DEFRA in FIVE of eight cities (West
> Midlands +0.66) - London is 72% of the strip and hid them. Held-out: strip
> 1.431 -> 1.141, beside the strip 1.226 -> 0.770, every city better and every
> city's bias negative. London's published figure 1.320 -> 1.032. Borough
> bands, borough scores and area pages do not move (only the version they print).

> ## THE AIRCRAFT NEAR-FIELD FLOOR WAS A DISC - FIXED 2026-09-01 (audit C1)
>
> `footprint_for()` returns an EQUIVALENT RADIUS, `sqrt(area/pi)`, and the
> near-field floor compared the borough ring against it as though DEFRA's 55 dB
> Lden contour were a circle centred on the airport. **Round 4 contours are
> strips along the runway centreline** - East Midlands' is 21.2 x 3.8 km against
> a disc of r = 3.46 km - so the test was wrong in both directions at once.
>
> **RUSHCLIFFE missed the disc by 180 m** and published `Quiet skies 10.0/10`,
> band `low`, over **10.43 km2 at or above 55 dB peaking at 65.6 dB** - the
> fourth-largest aircraft footprint in the product. Solihull, at a comparable
> 9.21 km2, published `moderate-high`. Not a threshold: an inconsistency.
>
> **The floor now tests the borough against the >=55 dB cells in that airport's
> own GeoTIFF.** The measurement is CHECKED IN
> (`data/aircraft-footprint.json`, 6.6 KB, un-ignored in `.gitignore`)
> because `build_aircraft_bands.py --check` is BLOCKING and the rasters are
> 2.6-29 MB and gitignored - the same shape as `district-msoa-names.json`.
> `scripts/measure_aircraft_footprint.py --verify` re-derives it from the
> GeoTIFFs, which is what stops the two drifting. **The builder REFUSES to fall
> back to the disc if the file is missing**, because a silent fallback would
> reinstate the defect on every fresh clone.
>
> **Effect: 3 bands moved.** Rushcliffe `low -> moderate` (balanced **5.0 ->
> 3.4**, quietlife 6.4 -> 4.0, both exactly as the audit predicted by hand),
> North Tyneside `low -> moderate`, and **Knowsley `moderate -> low`** - the one
> optimistic move, checked rather than accepted: its boundary is **0.76 km
> clear** of the nearest >=55 dB cell.
>
> **Teesside (MME) and Cardiff (CWL) keep the disc**, and the data file says so
> explicitly. They are **not mapped by Round 4 at all**, so there is no contour
> to test against - "no contour published" is not "not measured here", and an
> absent key and a measured zero are the same shape in JSON.

<!-- CLAUDE.md lines 294-303 (2026-10-16) -->
**DEFRA IS NOT A BLOCKER AND NEVER WAS (measured 2026-08-10).** GetCapabilities
on the WCS named in `scripts/download_defra_wcs.py` advertises **16 airports
with a Round 4 Lden surface** - Manchester, Birmingham, Leeds Bradford,
Liverpool, Newcastle, Bristol and East Midlands among them. Provenance for nine
cities used to say the raster "has not been run for" the city; that was false
and is corrected. We have not SAMPLED it. Use the **per-airport** coverages
(Birmingham is 979x1467, an 11.5 MB GeoTIFF), never `Airport_Noise_ALL_Lden`,
which is 26,097 x 48,046 - 1.25 billion cells. The host needs a browser
User-Agent; without one it answers 403 and looks bot-blocked.

<!-- CLAUDE.md lines 355-392 (2026-10-16) -->
**Corridors are on a common 1 km interval.** Corridor distance is measured to
the nearest waypoint, so a coarse polyline reads as further from the corridor
and therefore QUIETER - which is why resampling had to precede un-gating.
Measuring first also corrected a claim this file used to make: **London was
3.34 km median, not "~1 km"**, so the gap against the new cities' 4.00 km was
about 20% rather than 4x. Everything is now <=1.01 km. Regenerate at 1 km if
any corridor is ever re-derived.

**The aircraft ladder is scaled per airport, and the fix had to be made TWICE
(v3.8, 2026-08-11).** The distance ladder is calibrated on Heathrow and was
applied unweighted everywhere, so Stockton-on-Tees was published `severe` — the
same band as Hounslow — off an airport carrying 173,006 passengers a year. Each
airport's ladder is now divided by its **measured DEFRA 55 dB Lden footprint**
relative to Heathrow's; Heathrow is 1.000 so London bands cannot move. **Do not
reach for passenger numbers**: East Midlands has the second-largest footprint of
the twelve on 3.2M passengers because it flies freight at night, Gatwick 0.475 on
40.9M.

The important half is that **`calc_postcode_quiet` runs its OWN copy of the
ramp** and takes precedence over the borough band, so fixing only the band left
the two tiers contradicting each other by 4.0 points. **When correcting any
scoring input here, ask which tier answers first.** The borough path needs a
near-field floor (scaling alone moved 29 boroughs and moved all 29 *down*,
putting Vale of Glamorgan on `low` with Cardiff Airport inside it); the postcode
path does not, because a postcode carries a real distance.

**There is a validation set for quiet geometry — use it.**
`data/aircraft-quiet-london.json` holds DEFRA raster-measured quiet for 35,352
London postcodes, and the geometry tier only ever stands in for that raster, so
any change to it can be scored rather than argued: v3.8 cut mean absolute error
from 3.230 to 1.879, 14,730 postcodes closer and 20 further.

**A city with NO airports is a real case.** South Yorkshire has none (Doncaster
Sheffield closed to commercial flights in 2022), and un-gating turned that into
`min()` on an empty sequence - a 500 on every South Yorkshire postcode, which
the gate had been hiding. It now falls back to the borough band. Any new city
without an airport needs that path to stay intact.

