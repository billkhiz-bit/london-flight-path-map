# Neighbourhoods, stations and area labels

> Moved verbatim from `CLAUDE.md` on 2026-10-17 to keep the session-start file small.
> PPD category A, generated neighbourhoods, the deleted transport layer, NaPTAN stations, "best value" framing, corroborated labels, majority containment.
> Statements are dated as written; re-measure a number before relying on it, and when a
> rule here changes, update the one-line rule in `CLAUDE.md` too.

<!-- CLAUDE.md lines 455-636 (2026-10-16) -->
**Neighbourhood medians are HM Land Registry PPD CATEGORY A ONLY since 2026-09-01 (audit C2).** Category B is HMLR's additional class - repossessions, power-of-sale transfers, buy-to-lets identified by mortgage, and every property-type-'O' row - and **HMLR's own median statistics and the UK HPI use category A alone**. So while both classes were kept, one product published two price bases: a borough `avgPrice` on A, validated against HPI by a blocking gate, and a neighbourhood `price` on A+B in the same panel. **412 of 485 published prices were wrong** - TS26 Hartlepool by 40% (125k -> 175k), WV2 by 26.7%, LS2 by -18.5%. **485 rows became 481**: four districts (L2, L28, SR1, B7) fell below the 30-sale floor once the repossessions stopped propping them up, which is the floor working. `--check` re-derives every published median from the PPD with a **per-city 95% share floor**; it is ADVISORY because the 155 MB PPD cache is gitignored, and it reports INCONCLUSIVE rather than PASS when the file is absent. `--check-names` now scopes corroboration to the districts a build will actually PUBLISH - a curated label for a dropped district is dead config, not a false claim.

**Neighbourhood ranking data.** **New York alone** holds *curated* medians and a hand-assigned `crime` modifier inline. **LONDON IS GENERATED SINCE 2026-10-11**: its 134 hand-written neighbourhoods (round prices with no source; Chelsea GBP 1.2m against a 2025 SW3 median of 1.5m; crime modifiers no source supports) became 221 postcode districts, every one of 169 curated labels corroborated by `--check-names`, and London's ranking now carries the price-led disclosure like the other nine. `LONDON_AREA_MAP` keeps its 161 hand-written place names as SEARCH aids only (a name with no detail row is skipped by the ranking). **All ten UK city-regions' 702 entries are generated** (nine since 2026-08-11; was Greater Manchester's 85 alone) — `python scripts/build_city_neighbourhoods.py --write-index` rewrites `index.html` between each city's `<CITY>-NEIGHBOURHOODS:START/END` markers from HM Land Registry's **bulk** Price Paid CSV (the linked-data API returns **HTTP 200 with an empty list** for a district query, so it cannot be used) plus NSPL for coordinates. A "neighbourhood" is a **postcode district**, districts under 30 sales are dropped rather than estimated, and `crime` is 0 everywhere because sub-borough crime is not published at that geography. **Boroughs come from the Lambda's `LAD_TO_BOROUGH`, matched to Land Registry's own district spelling by normalisation** (`Westminster` → `CITY OF WESTMINSTER`); a borough matching nothing is reported loudly, because a silent miss reads as "this borough has no neighbourhoods". One PPD pass and one NSPL pass cover every city. Do not hand-edit inside the markers; re-run the script. The 155 MB PPD cache and the JSON by-product both land in gitignored `data/`.

**The transport MAP LAYER is DELETED; stations live in the PANEL (2026-08-12).**
Bill: "still messy for the other core cities - I can't click on them because it
will click on the borough instead." Both true, and together fatal: the markers
cluttered the thing you *can* click, could not be clicked themselves (the borough
path takes the event), and duplicated a signal already in the score. Toggle,
flag, renderer, `.layer-transport` selector entry and the `labelTransport`
registry field on all eleven cities are **removed**.

The DATA moved to where it is readable: the detail panel's nearest-stations
section, which is fed by `/transport` = **TfL**, and which had been telling ten
of eleven cities **"No stations found within 1.5km."** That is not what TfL
meant - it meant "TfL does not cover Manchester" - and the panel rendered a
confident absence in its place. **Third instance of that shape in one day**,
after the `-0.4` penalty and the `|| 'moderate'` fill layers. NaPTAN now backs
it: four nearest rail/metro/tram, straight-line distance, source named.

**The panel reads `lineStatusAvailable` since 2026-08-27, and until then nothing
did.** `/transport` has separated "TfL answered and nothing near you is
disrupted" from "we could not ask" since 2026-08-24, and the frontend gated the
whole section on `lineStatus.length > 0` - so a 403 on the Status route rendered
as NO SECTION AT ALL, which is indistinguishable from a clean network. **Fourth
instance of absence-as-measurement in this one panel's history.** The producing
comment is where it went wrong: "consumers can upgrade to read the flag; none is
required to" made the second half optional, so it never happened. **A field only
its producer reads is not a fix.** The notice DENIES the false reading rather
than merely withholding the claim, names the upstream, and scopes itself to the
status leg (the stations came from a different TfL route that answered). Use
`!== false`, never a truthiness test - a response cached before 2026-08-24 has
the field `undefined`, which meant "checked", and truthiness would turn every
stale cached response into a false outage claim.

**Three stale references survived the removal and Bill found the first**: the
metric card still said `TOGGLE "TRANSPORT" ON MAP TO SEE STATIONS`, the layer
selector map still listed `.layer-transport`, and the map's `aria-label` still
advertised the overlay (while naming three cities out of eleven). **When you
delete a feature, grep for its NAME, not just its function.**

The e2e asserted `toHaveCount(7)` on the toggles and went red - the gate working,
but the fix it invited was to edit the number. It now asserts the **set**, so a
removed layer fails with its own name in the diff. **Any count in an assertion is
scheduled staleness.**

**Stations are DISPLAY-ONLY, and the transport nudge is gone (2026-08-12).**
`scripts/build_city_stations.py --write` fills **`data/stations.json`** (keyed by
city; **the holder since 2026-09-18** - until then eleven inline
`<CITY>_STATIONS` constants, 92 KB of a `no-cache` page re-sent on every
deploy) from NaPTAN - **1,390 stations across ten cities, down from 1,651 on
2026-09-01 (audit I19) and 1,415 on 2026-09-15 (audit M23)** - **read by
`nearestStations()` for the detail panel** through `stationsFor(key)`. The page
fetches it on search intent exactly as it fetches the aircraft-quiet files
(`ensureStations(capMs)`, awaited beside `ensureAircraftQuiet` on both result
paths), it is NOT in `sw.js` `SHELL_ASSETS` for the same reason they are not,
and `renderNaptanStations()` has a third state - not loaded - that renders its
own sentence and returns true, so a slow network can never become "no station
near this postcode". The writer skips `BACKEND_ONLY_CITIES` (read by AST from
its one holder) so the file is what the site renders; the extraction was proven
byte-identical to a rebuild from NaPTAN. `tests/test_station_lists.py` reads the
same file; `make data-deploy` uploads it `no-cache` - **deploy it WITH
`index.html`**, since a page that expects it against an origin without it says
"station list could not be loaded" on every search. **AND DATA-DEPLOY FIRST:
`python scripts/make.py data-deploy web-deploy`, never the reverse (corrected
2026-09-19).** `web-deploy` uploads AND INVALIDATES `index.html`, which carries
5 references to this file and 0 inline `_STATIONS` arrays, so web-first leaves
a window between the two invalidations in which the live page fetches a file
the origin does not have. Reversed there is NO window: the page that is live
carries the inverse and ignores the new file until the new page lands. **This
was live for a day and the runbook had it backwards in three holders** -
ROADMAP twice and the 18 Sep memory - **while the Makefile's own comment on
this very file had the reasoning right all along.** Mirror drift between a
comment and a runbook. Deployed and verified 2026-09-19: three hash-MATCHes,
`stations.json` **200 where it was 403** (it had never existed at the origin),
both invalidations Completed, drift **134 of 134** (18 data files, this is the
18th), Manchester renders Market Street and Piccadilly Gardens, London renders
Clapham Junction. **`web-deploy-all` now runs `data-deploy` before `web-deploy`
too (2026-09-25)**; `test_web_deploy_all_ships_data_before_the_page` in
`tests/test_make_runner.py` asserts it and is proven red on the old order.

**Two things were wrong with that list until 2026-09-01, and both were MEASURED
before being fixed.** A trailing DIRECTION is a platform, not a place: Sheffield
Supertram names each direction as its own NaPTAN node and no strip in
`clean_name` touched them, so **Attercliffe published as five "stations"**
("Attercliffe", "... From City", "... To City", "... Platform to City",
"... Platform to Meadowhall"). Across the published arrays **170 of 943 entries
were a place already listed, 166 of them South Yorkshire** - which is how a
quarter of "nearest four stations" panels filled four rows with fewer than four
PLACES. South Yorkshire is **268 -> 102**. And NaPTAN keeps RETIRED nodes with
real names and coordinates, marked `Status: inactive` - **806 of them** were
published as current services, because nothing read the column.

**A THIRD instance turned up the moment the new gate ran**, which is this
repo's "hardening a gate finds a new defect" for the fourth time: Manchester
published **"Besses o'th'Barn" AND "Besses o'th'barn"** - one Metrolink stop,
two entries, differing only in a capital B. Same root cause as the directional
suffixes, a dictionary keyed on an exact display string, and the directional
strip could not touch it. The key is `casefold()`ed now and the DISPLAY name is
CHOSEN - the spelling with more capitals wins, deterministically, because this
array is diffed on every rebuild.

**The strip is anchored to the end, and was proven safe rather than reasoned
about**, because `clean_name`'s own docstring records a strip that EDITED a name
("Station Approach" -> "Approach"): of the 180 names it changes, **175 merge
into a place listed within 800 m**, and the 5 with no sibling keep a real place
name ("Meadowhall Interchange To City" -> "Meadowhall Interchange"). The reader
**hard-fails if the `Status` column is absent** and **again if a scan that kept
stations excluded no inactive ones** - the same two-directional guard the
terminated-postcode reader carries, because either spelling of a silent
fall-through looks like a clean run.

**11 entries left entirely and 4 of those are not closures - read this before
re-deriving.** Angel Road, North Woolwich, Silvertown, Oldham Werneth and
Garston (Merseyside) are genuinely closed. Three Eccles Metrolink ENTRANCE nodes
went while Eccles itself stayed. **Woodlands Road has no active node in NaPTAN
at all**, which is an upstream claim we follow rather than second-guess. And
**Grange Hill is a live Central line station that London now does not list**:
its active nodes sit at lon 0.09207, **outside** the boundary polygon, while the
retired node at 0.09276 fell inside - the London/Essex boundary runs through the
station, about 50 m apart. It was published only because a decommissioned node
landed on the right side of a line. The limitation that exposes is real and
PRE-DATES this fix: point-in-polygon containment never lists a station just
outside a city, however near the reader is standing. (This paragraph said they "draw the map's transport layer" until
2026-08-23, contradicting the paragraph directly above it, which correctly
records that the transport MAP LAYER was deleted on 2026-08-12. There is no
transport layer: six toggles are declared - paths, defra-aircraft, defra-road,
flood, air-quality, labels - and a dead CSS rule for a seventh survived until
2026-08-23, the **fourth** stale reference from that one removal.) The `+/-0.4` liveability nudge those arrays
fed is **removed, not filled**: transport is already scored from the same NaPTAN
register at borough level since v3.6 (0.25 of liveability), so filling them would
count one measurement twice, and London's THEN 18 hand-picked interchanges meant
something different from "every station" (London's array is NaPTAN's ~670 rows
too since that same day; this line said "is 18" until 2026-09-15, audit M23).
**Since M23 (2026-09-15) a trailing QUALIFIER is split off and restored only
when unanimous**: "Abbey Wood" + "Abbey Wood (London)" and Hammersmith x4 (one per
line) merge, 1,415 -> 1,390; "Kensington (Olympia)" and "Hayes (Kent)" keep the
name every node carries. Two traps, both the bbox/first-match
family: **a bounding box is not containment** (Leicester's and Nottingham's
overlap - first-match-wins gave Leicester 104 stations and Nottingham 16; point-
in-polygon gives 19 and 69), and **stripping a descriptor anywhere in a name
edits the name** ("Station Approach" -> "Approach"; four Altrinchams). NYC is
untouched - NaPTAN is UK-only and correctly yields zero. **NYC's transport
layer has ALWAYS drawn nothing**: `NYC_STATIONS` was already `[]` before this
work, under a comment describing "major subway/rail hubs". Filling it needs an
MTA source, not NaPTAN.

**The neighbourhood ranking says "best value" where price leads it (2026-08-12).**
Rank-to-price correlation, measured over the rendered rows and
**RE-MEASURED 2026-09-03**: **+0.55 London (was -0.23 on 2026-08-12),
-0.06 NYC, 0.65-0.89 every generated city**. So nine of eleven lists are largely
cheapest-first - each puts Bradford City Centre, Middlesbrough Town Centre,
Chopwell or Bootle at #1. Structural, not a fault: a generated "neighbourhood" is
a postcode district with `crime: 0` (not published at that geography) and a
liveability inherited from its borough, so districts differ mainly by price and
aircraft quiet while affordability is 27% of the score. **Nothing is
miscomputed; the LABEL over-claims** - the same distinction as WA8 publishing a
Knowsley median as "Widnes". **The threshold is MEASURED at render time, never a
per-city string**, so a city that gains a differentiating input drops the
disclosure by itself - the `markLayerCoverage()` principle, applied before the
stale-string version could be written. **0.6 was chosen because nothing sat between -0.23 and 0.67, and that
justification has EXPIRED**: London is now +0.55, squarely inside the gap
that was said to be empty, and 0.05 from flipping the disclosure on its
128 neighbourhoods. Nothing is over-claimed today - the threshold is
measured, so London simply says nothing - but the constant is now
arbitrary in a way it was not when picked. The cause is `environment`
(v3.9): prime central London scores badly on NO2, so Mayfair (GBP 2.5M)
and Belgravia sank while Cheam (GBP 470k) leads. Re-measure before
touching it; do not reason from the old figures.

**The 281 curated area labels are CORROBORATED, not recalled (2026-08-12).** Until then only Greater Manchester had any, so **273 of 503 districts rendered under a repeated post town** — Birmingham ×35, Liverpool ×29, Leeds ×16, Sheffield ×15. Nothing was false (the outward code is always beside the label) but a ranked list of thirty-five "Birmingham" rows says nothing. `NAME_OVERRIDES_BY_CITY` now covers all nine cities, and **`--check-names` asserts every label against that district's own House of Commons Library MSOA name**, evidence checked in at `data/district-msoa-names.json` so the gate needs neither NSPL nor a network. Blocking in preflight. **273 → 5**, the five being Bath ×2 and Darlington ×3, left as post towns on purpose.

**A district is published only if it is MAJORITY INSIDE the city publishing it (2026-08-12).** Transactions are bucketed by the Land Registry `district` field, a LOCAL AUTHORITY, but an entry is published as a POSTCODE DISTRICT, Royal Mail's — and those do not nest. **WA8 was 4% inside Knowsley and 94% inside Halton, which we do not cover**, so it published a Knowsley median of £345k off 32 sales — Merseyside's *fourth priciest* entry — under the label "Widnes", at a centroid averaged over all 1,591 postcodes and therefore sitting in Halton. Every step was arithmetically correct; the join was wrong. 34 of 501 were under 75% contained, 8 under 20%. **18 dropped**, 503 → 485.

- **`lat/lon` and `postcodes` now cover the COVERED part only**, so the marker sits in what the price describes. This moved 43 retained markers, Darlington (DL2, 64%) by **4.4 km**.
- **A district belongs to exactly ONE city.** WN4 and WN5 straddle Wigan/St Helens and were published TWICE at identical coordinates — WN5 as `Pemberton & Orrell` £165k in Greater Manchester *and* `Billinge` £235k in Merseyside. At the 50% floor the arbitration cannot fire (two cities cannot each hold a majority) but it is kept for `--min-containment` below 0.5.
- **The label is the part that cannot be repaired by maths.** The covered slice of WA8 has no name of its own; "Widnes" is the only name the district has. That is why the floor drops rather than relabels.

- **Deriving the name was tried and rejected ON MEASUREMENT.** A district spans 4–13 MSOAs, so the modal name carries 15–33% and names a sub-area: BS8 came out `Clifton East`, SK5 came out `Brinnington` when the district is Reddish, and a shared-token variant gave `Five` for B16, `Quays` for M50 and `Mossley` for **both** L17 and L18 — recreating the duplicate it was meant to fix. Manchester's 26 hand-written names were the answer key.
- **The check caught four names that had shipped for months** — `Chorlton-on-Medlock` (M13 is Ardwick and Victoria Park), `Chorlton-cum-Hardy`, `Ancoats & Northern Quarter`, `The Heatons` — plus `West Derby` and `Kelham Island`, none of which any published source places in those districts.
- **It cannot catch a name that is merely the NEIGHBOUR's**: MSOA lists reach over district boundaries, so `CH47: Hoylake & West Kirby` corroborated cleanly while CH48 *is* West Kirby. Read the sibling districts before writing a label.
- **A dict keyed to a city nobody looks up passes perfectly and reaches nothing.** Four of the eight were first written `west_midlands` / `south_yorkshire` when the builder's keys are `westmidlands` / `southyorkshire`: the check read all-285-green while **163 of them were dead**. There is now an UNKNOWN CITY KEYS guard, and the marker-derived `DEFAULT_CITIES` is the only source of truth for a city key.
