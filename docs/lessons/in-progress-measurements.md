# Measurements held, not yet shown

> Moved verbatim from `CLAUDE.md` on 2026-10-17 to keep the session-start file small.
> DEFRA AURN monitors; Breathe London sensors; how often planes pass (adsb.lol, CAA comparison, outages, circuits).
> Statements are dated as written; re-measure a number before relying on it, and when a
> rule here changes, update the one-line rule in `CLAUDE.md` too.

<!-- CLAUDE.md lines 640-671 (2026-10-16) -->
**DEFRA's AURN reference monitors are HELD, not shown (2026-10-13).** `scripts/fetch_aurn.py --fetch` writes
`data/aurn-sites.json` (checked in; raw R files in ignored `data/aurn/`, `--fetch`/`--verify` need `pip install
pyreadr`). Its year is `load_defra_air_quality.PCM_YEAR`, never the newest summary: PCM is calibrated against AURN
of the same year, and `--check` (BLOCKING, offline) reds when air quality rolls until it is re-fetched. Ratified
only (a site that closed mid-year counts to its closing day), 75% capture, UK-AIR's attribution word for word
("licenced"), a usable site inside EVERY covered city or a `NO_SITE_INSIDE` reason. Display only, never scored,
never ranked (UK-AIR: "not scientifically sound"). Shown since 2026-10-19 (built; see
`front-page-and-site.md`, "AIR MEASURED NEARBY"): within 5 km only, so Greater Norwich (nearest NO2 clearing the
floor 77 km away) says nothing.

**BREATHE LONDON'S SENSORS ARE HELD, not shown (2026-10-19).** `scripts/fetch_breathe_london.py --fetch` writes
`data/breathe-london-sensors.json` (checked in; the raw API answers, ~15 MB gzipped, in ignored
`data/breathe-london/<fetch day>/`, so a re-run the same day resumes and `--verify` re-derives exactly). The GLA key is
in `.env` as `BREATHE_LONDON_API_KEY` ONLY: Bill typed it in with Notepad, it was never pasted into the chat, and every
command that uses it reads `.env` itself and prints nothing of it (a check prints set/MISSING and the length). It
travels in the `X-API-KEY` header, never a URL; error bodies are redacted; `--fetch` refuses to cache or write
anything holding it and `--check` (BLOCKING) searches the file for it. Three API shapes measured on day one, each
held by a test proven RED on a scratch copy of the script: `endTime` is INCLUSIVE (two days returned 49 hours), a
missing hour is a ROW with a null `ScaledValue` (so capture is valid hours over the WINDOW's hours, never over the
rows returned: a sensor installed mid-window has no rows before it and would read 100%), and a null is missing,
never zero. The window is the 12 whole months before the fetch month (UTC), 75% capture, the borough by
point-in-polygon on `london-boroughs.json` keyed by ONS code (the API's borough NAME disagreed once: Prior Weston
Primary School, BL0060, on the City/Islington line; postcodes.io's two nearest postcodes are City of London, so the
boundary stands and the API names the school's council), a usable sensor in EVERY borough or a `NO_SENSOR_INSIDE`
reason. **First fetch, 19 Oct (window Oct 2025-Sep 2026): 116 of 153 live sensors usable** (114 NO2, 104 PM2.5),
all 33 boroughs; 49 of the 88 dropped means are places that began measuring after the window opened, 39 belong
to 26 sensors in place all year with too many gaps (8-72% of hours). Kerbside survives worst (7 of 23; all 16
left out are new). **ONE PLACE PER MEAN (review, same day):** `/ListSensors` is one row per INSTALLATION (327
rows, 153 live) and `/SensorData` by site code returns EVERY installation's hours (BL0005: 5,996 valid hours
before its live device went in), so a sensor moved under its code would blend two places into one mean.
`measuring_since()` keeps only hours since the run of same-place installations (position ~10 m,
classification, kerb distance; height ignored, BL0056's swap rose 0.4 m) began; `--check` refuses a capture
larger than those hours allow. On 19 Oct none had moved (27 overlapping installations, all same-post swaps),
so no mean changed; my first count of "new" sensors (78) had used the live device's date and was wrong.
The same review: urllib copies `X-API-KEY` onto a REDIRECT to any host (redirects now refused), error bodies
are redacted before being cut, and every line printed while the key is known goes through a redacting
stream (a check that FINDS the key in a field would otherwise echo it). Each proven red on a scratch copy. 2.16 million hourly values, none
negative or zero. Medians NO2 19.9 background / 20.6 roadside / 29.9 kerbside; PM2.5 about 7 everywhere. Display
only, never scored, never ranked; `check_data_freshness.py` reads NEWER 45 days after the window ends.

**HOW OFTEN PLANES PASS IS BEING MEASURED, NOT SHOWN (2026-10-15).** Bill: as accurate as possible, time no
object; the plan and its gates are ROADMAP "IN PROGRESS: how often planes fly". `scripts/adsb_extract.py` streams
one day of adsb.lol history (ODbL) into `data/adsb/extract/<day>.jsonl.gz` (raw days ~3.7 GB in `data/adsb/raw/`,
all gitignored; run it with `-I` under a CURRENT Python, the archive is untrusted input: 3.11's tarfile fixes stop at 3.11.9 on Windows, so Bill's machine uses an unregistered 3.13 at `~/tools/python-3.13.15/python.exe`, 2026-10-16); `scripts/adsb_movements.py` counts
landings and take-offs per runway and compares the UK airports with CAA Table 03 (`data/caa/`, gitignored). Two
traps found on day one, both held by `tests/test_adsb_movements.py` (the first proven red): a silent wait at the
holding point split one take-off into two (bound each low run's climb by its neighbours), and a circuit's climb is
measured from the FIELD, not the run's edge. **Nothing derived from it is published yet.** Bill accepted ODbL
share-alike (15 Oct: published counts go out under ODbL, credited); the per-airport floor is `coverage_verdict()`
(same period as the CAA's figure, 300+ official movements, tracked within 95-105%); the "never say how often
planes pass" copy rule lifts only for airports that pass it. **August 2026 against the CAA's August: 12 of 15 UK
airports pass** (Heathrow 98.8%; fail Liverpool 94.8, Teesside 91.0, Norwich 94.0), and **July 2026: 14 of 15** (2026-10-16; only Teesside short, 87.8%, as in August), once two more traps were
handled (2026-10-15, both rules with tests proven red): **the archive has OUTAGES** (6 of 31 August days, the UK
and US together, one THINNED to ~5% with no gap, so never test for gaps alone): `feed_gaps()` profiles distinct
aircraft per 10 minutes per region against nearby days, outage days are left out and the CAA figure scaled by
`usable_share()` (weekday-weighted; never judge an outage from an airport's own counts, London City's Saturdays
are a quarter of its weekdays; the reference is turned onto LOCAL time, or a clock change reads as an outage on
almost every day after it). And **circuits are movements** by the CAA's definition but airports report them unevenly
(Cardiff includes them, East Midlands evidently not): a count passes only if ONE reading fits at both ends, with
`circuits` or without (never the floor on one and the ceiling on the other: that passed 110%/80%), and a pair under
`CIRCUIT_MIN_S` (30 s) is a low approach or a glitch, not a circuit. The report takes ~2.5 min a month on six workers.

**AN OVERFLIGHT IS CAP 1498's, AND THE FETCH IS SAFE TO STOP (2026-10-19).** Bill chose the CAA's CAP 1498
definition for step 2: an aircraft above a 48.5 degree elevation angle (the headline; 60 degrees computed alongside)
and below 7,000 ft; CAP 1498 says results must state both thresholds. At 48.5 degrees the cone's radius is 0.885 x
the height. A prototype (outside the repo) on two days settled three questions: (1) altitude: barometric and GPS
differ by ~500 ft on a day (GPS is above the ellipsoid; the geoid is ~46 m above it here), so use GPS minus the
geoid where present (63-65% of points), else barometric plus that DAY'S median offset; (2) 100 m steps along each
segment are enough (25 m gave identical counts); (3) a day must be classed westerly or easterly before averaging:
Kew TW9 3PZ counted 296 on 14 Oct (westerly) and 0 on 15 Aug (easterly). 48.5 vs 60 barely differs under a
centreline (296/295) but does off it (Silvertown 90/54). **`adsb_fetch.py --workers N`** (default 6) passes N to
the extractor: six workers on a machine in use (Chrome at 17 GB) ran it out of memory and background jobs were
stopped; 3 gives the same extracts, more slowly. **Stopping is always safe:** a day is skipped only when its
extract EXISTS, and the extractor writes `<day>.jsonl.gz.partial` and renames it when complete, so a killed day is
redone, never half-counted; a part download resumes from the bytes it has.

**THE OVERFLIGHT COUNTER IS BUILT (2026-10-20): `scripts/adsb_overflights.py`.** One file a day,
`data/adsb/overflights/<day>.npz` (gitignored, ~8.6 MB, written `.partial` then renamed): for each angle (48.5 headline,
60 alongside, under 7,000 ft) the count per 100 m British National Grid cell, in total and per airport, plus the day's
feed profile, movements by runway and UTC hour, and the height offsets used. A pass counts ONCE per cell (hits more
than 5 minutes apart are separate passes); each 100 m step is credited to the movement nearest in time (30 min before
a landing, 15 after a take-off), else "other" (~40% of steps: transits, helicopters, Southend, Farnborough). Height:
GPS minus the airport's EGM96 geoid where present, else barometric plus that AIRPORT's own day offset (186 ft at
Newcastle to 425 ft at Gatwick on 14 Oct, so one UK offset would be wrong), and the offset is a LINE in barometric
height (`offset_fit()`, medians of 1,000 ft bands): **pressure height drifts from true height with height when the
air is off ISA**, measured near Heathrow on 15 Aug as 123 ft under 1,000 ft and 348 ft at 7,000-8,000 ft, where one
median (173 ft) was ~50 ft high near the ground and ~175 ft low at the ceiling. A code review also found the walk
rounded its step count DOWN (a 199 m segment had only its ends, a gap a low cone missed), a bad day stopping a
year's batch, `--observe` overwriting a day file, and averages summed as fractions; all fixed, each proven red.
Against the prototype on 14 Oct, after the fixes: Kew 296, Battersea 341, Hackney 14, Hounslow 4, Silvertown 148 at
the point (140 for its cell, whose centre is up to 71 m away); 15 Aug (easterly) Kew 0. ~35 s and ~2 GB a day on one
process.
**The direction rule (Bill asked Claude to choose, 2026-10-20): `classify_day()`.** A runway end with a bearing over
180 is westerly (every runway has one end of each, so 04/22 and 15/33 work as 09/27 does); landings and take-offs,
circuits subtracted, `?` ignored; 80% on one direction's ends makes the day that direction, else `mixed` (its own
average); under 20 movements, left out. On 88 held 2026 days at Heathrow: 48 westerly, 26 easterly, 14 mixed;
65.4% of movements westerly, near the published ~70/30; 70% or 90% instead moves 1-4 days. A first version tested
the westerly share against `1 - 0.8` (0.19999999999999996), so a day exactly 80% easterly read "mixed": compare each
direction's OWN share with the one threshold. Averaging 14 Oct + 15 Aug: Kew 292 a westerly day from Heathrow, 0
easterly. **The first year-so-far run (2026-10-20):** all 195 held days counted in ~2 h on one process beside
the fetch, none failed; `average()` left out 15 outage days (feed_gaps over the stored profiles) and classed
Heathrow's 180 kept days 98 westerly / 51 easterly / 31 mixed. Kew 307 a westerly day, 5 easterly, 180 mixed;
Battersea 318 / 2 / 177; Silvertown 105 from Heathrow and 39 from London City on westerly days, falling to 70 and 1
at 60 degrees (off the centreline, and London City's 5.5 degree approach is ~250 ft there: a cone under 70 m
wide), where Kew does not move (under the centreline). **Not settled:** heights are above sea level, not ground, so high airfields (Leeds Bradford ~200 m) count
high; a low aircraft orbiting back over a cell within one pass counts once; by-hour classing would place a mixed
day's hours properly (needs per-hour counts); `average()` does not apply `coverage_verdict()`, publishing must.
**The year so far, 2026-10-21:** the fetch finished at 289 of 291 days (adsb.lol's 5 May archive is near-empty,
6 May's is a 404), all counted (~35 s a day, none failed). **`average()` then ran out of 32 GB**: holding every
day at once meant 388 million rows at 48.5 degrees, ~3 GB a column. It now reads the metas alone first, then
each kept day's cells once, summing whole counts 30 days at a time (`BATCH_DAYS`) and folding each batch into a
running total with `sweep()`; whole counts sum exactly, so the batch size changes nothing (identical arrays on
40 real days at 7 and 30, and a test at 1, 3 and 100, proven red twice). Year readout (270 days kept, 19 outage
days out; Heathrow 166 westerly / 66 easterly / 38 mixed = 72% westerly of the classed days), per day at 48.5
degrees (60): Kew TW9 3PZ 309 (308) westerly / 4 easterly / 160 mixed; Battersea SW11 1AA 321 (313) / 4 / 189;
Silvertown E16 2QD Heathrow 104 (68) + London City 36 (0) westerly; Hackney N1 7SX 20 (12); Hounslow TW3 1ES 1.
Stable against the 195-day run (Kew 307, Battersea 318). Unpublished.

**PER-POSTCODE AVERAGES ARE BUILT, NOT SHOWN (2026-10-22): `scripts/adsb_postcode_averages.py`.** Every day file is
read at the 100 m cell of each of the 591,910 live postcodes in the 97 covered councils (NSPL `east1m`/`north1m`
only: `grid_ref()` gets a transformer that refuses; every BT row, 63,293, left out explicitly; gridind 9, no
position, left out and counted). It writes `data/adsb/postcode-averages.npz`: per published airport, westerly /
easterly / mixed, both angles, summed passes, days and mean; NaN where an airport had no day of a kind (not
measured), 0 where it had days and no pass (measured); a failing airport absent with its reason once; `gridind`
carried as position quality (1,582 imputed and 150 sector-mean positions kept and flagged, never silently read as
exact); and `context_all_traffic_unpublishable`, every pass at the cell (all airports plus "other"), so a postcode
under unpublished traffic cannot read quiet by omission (Biggin Hill TN16 3GH: 6.3 a westerly day from Heathrow
under 28.8 of all traffic). The CAA's January-June tables now sit beside July and August; verdicts come from the
day files' own movements, which reproduced `report()`'s July and August ratios to the tenth at all 15.
**`year_rule()`: every checked month must pass, on ONE circuits reading, six months at least; only those months'
days are averaged.** Nine pass; Luton (failed February 93.2% and June 72.7%), Newcastle, Liverpool, Cardiff,
Norwich and Teesside do not. **A trap at Luton:** on 3-6 and 13-16 June a transponder alternated 'ground' and 0 ft,
`field_level()` counted up to 111,382 "touchdowns" from it and set the field at 0 ft, the low band then sat under
the runway, and the day's movements went uncounted (2-108 against ~420), so the overflights went to "other". It
recurred on 10 May, 4 Jul, 30 Aug and 11-14 Sep. Unfixed: the monthly verdict refuses Luton's June. **A code review
found the first tests could not fail on the main rule** (five mutations passed all six, among them the month
filter removed and left-out days averaged as westerly, because a fixture put the same count on every day): the
tests now vary the count by day and compare the build with `average()` itself; 20 mutations, all red. Kew 309.9 a
westerly day over January-August; `--every-month` reproduces the 21 Oct readout exactly. ~3.5 min, 1.1 GiB.
Unpublished; Bill's open calls are in ROADMAP's START HERE (2026-10-22, evening).

**LUTON'S FEBRUARY WAS THE WEATHER, AND THE COUNTER NOW READS IT (2026-10-23/24, branch `luton-field-metar`).** After
the field-at-0 fixes Luton failed only February (93.1% of the CAA's count). Counting it per day showed WHAT it missed:
take-offs, not flights (landings/take-offs 1.109 against January's 1.038), almost all on 13, 16 and 19 Feb, with
unheard visits at 15-31 a day against ~2. Luton's METARs (Iowa Mesonet archive) showed WHY: QNH moved 11-21 hPa within
those days, 300-570 ft of the field's pressure altitude, and the counter's ONE field value per day sat near the bottom
of the swing, so aircraft departing in the high hours were first heard above the low band and dropped. (The 15th and
18th swung as much and lost nothing: their value sat near the top.) **Step 1, the votes through the day**
(`FieldLevel`, the median of the nearest touchdown votes on a 10-minute grid) recovered the 16th but left February at
94.9%: Luton's mornings are DEPARTURES, so there were no morning votes to read, and the 13th had six votes in all.
Compared with the METAR-implied field (elevation + (1013.25 - QNH) x 27.3 ft), the evening matched to tens of feet and
the morning read 300-420 ft low. **Step 2, the shape from the METARs and the level from the aircraft** (each vote less
the METAR shape at its time, the median of those, plus the shape at t): Luton January 98.4%, **February 97.0%**, March
98.1%; the 13th 63 -> 191 take-offs against 192 landings. The day's VALUE is unchanged (FieldLevel is a float), so
every report and stored field reads the same number; `movements()` reads `at(t)`. **The first real run died
unpickling it**: a float subclass crossing ProcessPoolExecutor is rebuilt from the bare number, which handed the
votes argument a float; `__reduce__` now pickles it as the day value (tested). The counter never fetches: an
uncached month falls back to the aircraft alone. Tests: the morning departure (red with movements() ignoring the
time), the evening-only day (red without the METARs), the cache read in hPa for the UTC day, fetch_metar fetching a month still running again (a partial month cached as done would stay partial), and fetch_metar refusing
a web page or an empty station. NOT MERGED until the all-airport check shows no airport worse.
**RESULT (2026-10-24 evening): the year rule publishes TEN airports, Luton the tenth** (Jan-Aug 98.4, 97.0, 98.1,
98.1, 99.0, 96.9, 98.2, 98.5%). The recount ran in two parts (223 days, then the 66 still on the old counts, chosen by
day-file mtime, after Claude Code stopped it for low system memory with Blender at 11.7 GB). Compare a fix's
outcome by running `adsb_postcode_averages.py --verdicts` on the BACKUP's day files and on the new ones: only Luton's
outcome changed; the published 9 moved at most 0.2 points, Cardiff and Teesside ~1.3 (both still fail).
The per-postcode averages were then rebuilt with all ten and compared postcode by postcode with the backup's file:
the nine moved a median 0, at most 0.12 a day at the 99th percentile, and 0.69 at the very most (EMA, where one day
was reclassified). Compare the AVERAGES as well as the verdicts: a fix that leaves every verdict alone can
still move what a postcode would be told. Luton is new at up to 1.4 a day over a covered postcode (443 postcodes at 1
or more on westerly days); most of its traffic passes north of the councils we cover.

**IS IT ACCURATE? THE GROUND, THE EDGE, AND TWO INDEPENDENT CHECKS (2026-10-26, branch `planes-overhead`).** Bill
ruled the three serving calls ("go with yours": static per-district files on the site, the front page's answer
first, site-only with an ODbL download later) and asked "is this accurate". Answer given: the flights SEEN were
proven (97-99% of the CAA's count every month at the ten), WHICH pass overhead was not checked by anyone else, and
one bias was known. Four things followed.
(1) **The ground.** The cone was drawn from the height above SEA LEVEL, so on high ground it was always too wide.
Measured with OS Terrain 50 (OGL, free from the OS Downloads API, no key) at the postcodes with a plane a day or
more on westerly days: ground median 26 m in London, 87-131 m in Manchester, West Yorkshire and the West
Midlands, so cones a median 77-116 m too wide there. Judging each 100 m cell on its own ground is exact but
~1,000x the work; the ground UNDER THE AIRCRAFT leaves 0.885 x the change in ground across the cone, measured
at those postcodes as a median 3-14 m at 500 m and 8-33 m at 2 km, in either direction, so it cancels over
passes. `scripts/build_ground_grid.py` writes `data/terrain50/gb-ground-100m.npy` (int16, Ben Nevis reads
1,343 m: the orientation check; 0.99965 correlation with an independent 50 m sample at every postcode); the
counter's `agl_ft` draws the cone, the 7,000 ft ceiling stays ABOVE SEA LEVEL (CAP 1498 says "altitude"), a
missing grid refuses (`load_ground()`), and `one_definition()` makes `average()` and `read_metas()` refuse day
files counted two ways, because a recount stopped halfway would otherwise be averaged silently. Recount into a
NEW folder (`data/adsb/overflights-ground/`, no `--force`, so it resumes), then swap. One day (14 Oct): Kew 296
unchanged (under the centreline); London -1.7%, Manchester -8.3%, West Midlands -13.7%, South Yorkshire -17.6%.
A test that could not fail: "a height under the ground never counts" stayed green with the filter removed,
because a negative cone is empty anyway; what the filter really does is split passes across an underground
stretch, so the test now asserts `passes()` on that.
(2) **The knife edge** (a product question, ruled by Bill: show a range). Near a runway arrivals are 300-600 ft
up and the 48.5 degree cone ~100 m wide, so a postcode ~95 m off the centreline is in or out for EVERY arrival:
Hounslow TW3 3QL read 339 and then 7 on 14 Oct for 21 m of ground. ~800 postcodes halved that day, all on cone
edges along approaches; the old count had the same edge ~20 m further out, and a postcode sits up to 71 m from
its cell's centre anyway. `adsb_postcode_averages.py` now also reads the eight cells around each postcode
(`mean_lo` / `mean_hi`, +-100 m), and the builder gives `[least, most]` where `edge()` says the spread is wide.
(3) **Heathrow's own direction record**: its monthly "% of time on westerly operations" for 2026 (heathrow.com,
noise > data > operational data) against our share of movements on westerly runway ends: within 3 points in 8
of 9 months, September 92.0 v 92; May +6.8 (the 5-6 May archive gap); ours ~2 points more westerly on average
(movements against time: quiet night hours count as time).
(4) **The centreline check, the independent test of the counting**: a point 6 km out on each runway's extended
centreline, that airport's overflights on days it flew that way over the landings on that runway end. Two
codes (landings from airfield behaviour, overflights from cone sweeps km away): 0.994-1.033 at every
well-separated runway end of all ten airports (Heathrow's four 0.997-1.005). The odd rows are geometry, not
counting: Gatwick's standby runway ~200 m from the main one (x28), Stansted's one runway split "22"/"22C" in the
table (summed 1.002), Manchester's 05L/05R ~390 m apart (cones overlap). It validates the counting, not the
cone's edge, which is definitional: that is what the ranges are for. Not comparable: Luton's SAIP AD6
airspace-change appendix (CAP 1498 contours, 2018, arrivals only, CACI population, mostly outside our councils).
**The serving side**: `scripts/build_planes_overhead.py` (district files gitignored, `data/planes-manifest.json`
tracked; `airports.json` lists the districts, so an uncovered postcode costs no request and no console 404),
`js/planes.mjs` (pure `planesModel()` tested in Node by `tests/planes-model.mjs`, `planesNodes()` with
textContent only), `#ans-planes` in the front page's answer, `planes-deploy` (refuses unless `--check` passes),
`/how-it-works/#planes-overhead`. Every rule proven red on its defect (rounding by Python's ties-to-even, a
missing kind of day written 0, an unpublished airport let through, the uncounted traffic's figure written, a
never-measured postcode told something, the district guard).
**Double-checked on 95-127 recounted days (Bill: "is our data still accurate", 2026-10-26).** (a) Everything in a day
file but the cells is IDENTICAL to the sea-level count (movements, feed, field levels, height offsets, traces), so
the CAA monthly verdicts and the Heathrow direction check stand unchanged. (b) Passes over covered postcodes fell
at every airport, in step with the ground (LHR -2.0%, LCY -2.3%, BRS -5.1%, MAN -7.9%, BHX -13.1%). (c) A RISE, which a
narrower cone cannot make, at ~11,000 postcode-cell-days (+2 typically, +58 at Fulham SW6 4JH under the 27R/27L
approach): traced pass by pass, matched by time, every extra pass was a single step at the cone's edge over ground
BELOW SEA LEVEL under the aircraft (Terrain 50 reads the tidal Thames -2 m, the Severn estuary -4 m), which widens
the cone 1.8-3.5 m. That is the documented two-way residual of "the ground under the aircraft", not a bug; it shows
only where a square sits on a cone's edge, which the ranges cover. Not worth a recount to clamp water to 0 m. A
first tally wrongly blamed "splits": an airframe landing several times a day has several passes, so match extra
passes by TIME, never by their order in a trace. (d) The centreline check on the recounted days: 0.992-1.031 at
every well-separated runway end, as before.
**LIVE, 2026-10-26 (evening; Bill: "go live now" after the preview, claude.ai/artifact/TueRqSvmPrkjxmsrcDD3S8).**
Averages rebuilt on the ground counts (London -1.9% median, West Midlands -9.2%, South Yorkshire -15.4%; Kew 310 and
Hackney 20 unchanged; Hounslow TW3 3QL 310 -> 15, range 1-316). Thresholds MEASURED (scratch `measure_rules.py`): a range
at gap 10 / ratio 2 on 17,103 postcodes (4.0% of the 431,678 with a figure; London 6.4%); the other-flying flag at 5 a
day and 50% on 34,239, mostly round the airports that failed the check. 988 district files (15.4 MB). The preview found
figures cut off on phones ("1 to 316 a": the 84 px column phones give the rows above) and "(c)" for "©"; the planes
rows' figure column now sizes to its text, held by a front-page check at 390 px. Thursday re-checked with
`git stash create` + `git merge-tree` (no branch touched): unchanged. Ship order: `planes-deploy`, `web-deploy`,
`home-deploy` (the block is silent while a file is missing, so the order only decides when it shows).
**THE GO-LIVE REVIEW, 2026-10-27** (`/code-review`, 10 findings; 8 fixed, each held by a check proven red first):
a FAILED fetch of airports.json or a district file was kept as null, so one blip on a phone hid the block for the
whole visit: now retried on the next search (front-page check, TW3's file answering 503 once). A district file
older than airports.json could list only an airport since dropped, and drew a heading over no rows (read as a
measurement): now null. A model fault was an unhandled rejection; it now hides the block and logs
"Planes overhead hidden", which the front-page test counts as a failure. A range from a measured zero said "0 to
12 a day" (11 of 29,766 ranges): now "up to 12 a day". The definition typed 48.5 and 7,000 beside the constants:
now DERIVED, and How it works' 48.5 degrees / 7,000 ft / 80% / within 5% are held to the constants by a test.
`adsb_postcode_averages` checked a postcode's own cell but not the 8 around it (an edge cell's neighbour keys into
the next row): now one cell in from every edge (no real postcode is within 70 cells). `build_ground_grid` built
from a zip short of tiles, reading missing land as sea level: now refuses fewer than the 2,858 of the GB set.
`check_deploy_drift.sh` could not see `data/planes/` at all: it now byte-checks airports.json and 24 sampled
districts against the TRACKED manifest at the origin (red before the first deploy, as it should be). NOT changed,
with reasons: a late planes fetch from an earlier search fills only a CLOSED answer (render() is the only thing
that opens it, and clears the block first); "% of days" rounds each kind on its own, so three can sum to 99 or 101.

### THE DISTRICT PAGES (2026-10-28, built, not live)

Step 1 of the marketing plan: `/planes-overhead/<district>/`, one static page per postcode district, from
`scripts/build_planes_pages.py`, because robots.txt keeps crawlers out of `/data/` and the front page tells one
postcode at a time from a script, so search saw none of planes overhead. Bill's rulings, 28 Oct: figures BUILT INTO
the page (as area pages bake scores); a page only where some postcode is shown 10+ a day (PAGE_FROM); the address
`/planes-overhead/tw9/`; and, of three ways to read a sector, **bands** (option C): a cell counts the sector's
postcodes "at 100+ / at 10 to 99 / on an edge / under 10". A MIDDLE FIGURE WAS REFUSED for the reason he refused
averaging west and east days: near an approach a sector is two places (TW9 1 on a west day: 66 at ~317, 25 under 10,
69 on the edge between), so its median (317) is true of none of the quiet ones. Least-to-most ("1 to 317") read the
same in every sector, which on 464 pages is the doorway shape. An edge postcode counts in a band when both its ends
fall in it; "on an edge" only when they straddle. The busiest figure sits on the line above each table (bands alone
read SE10's 89-153 and Kew's 317 alike).

Measured exclusions beyond Bill's rule (522 districts reach 10 a day): 37 mostly outside the covered councils (CM13:
1 of its 702 live postcodes is in Havering; COVERED_FROM 0.5 of NSPL's live postcodes), 20 mostly large users
(SE1P, N1P, W1A: PO boxes, positioned at a sorting office; LARGE_UNDER 0.5), 1 under MIN_POSTCODES: **464 pages**.
A postcode not listed under an airport is UNLISTED = '<1' (every postcode is measured under every airport: NaN only
when an airport had no days of a kind, and all ten have all three). Labels and airport names are PARSED from
`js/planes.mjs` KINDS and `js/flight_geometry.mjs` AIRPORT_NAME; `per_day()`/`period()` are held equal to the
module's by running it in Node (`tests/test_build_planes_pages.py`).

Gitignored (pages and `sitemap-planes.xml`), like `data/planes/`: pushing the public repo must not publish every
district's figures ahead of Bill's review and the site. TRACKED `data/planes-pages-manifest.json` (bytes, md5 = S3
ETag, and `changed`, the day each page's bytes last changed) dates the sitemap, since git cannot date an ignored
file. `--check` (preflight, blocking) holds pages, manifest and sitemap byte-equal to a fresh build and prints
INCONCLUSIVE where the inputs are absent; `planes-pages-deploy` passes `--strict` so a deploy never reads that as OK.
The wording gate reads all 465 pages (they sit in the Makefile's sync list) and passes them on its own patterns: no
cell writes "N planes a day". Proven red: a typed "About 317 planes a day" in TW9 trips both the wording gate and
`--check`; eight builder mutations each turn their own test red.

PHONES: the first band cells wrapped mid-phrase ("at 10 to / 99") and every table then scrolled 40-76 px sideways at
390 px (axe also counts a scrolling table as a keyboard fault). Each band is now its own unbroken line, and the
site bar's 680 px breakpoint shrinks the table (12.5 px, 6/3 px padding): all 464 pages measured at 390 px, 0 scroll.
`tests/a11y-source.mjs` scans a sample DERIVED from the pages (the first carrying each feature, the biggest, the
widest row) at 1440 and 390 and measures the sideways scroll at 390, proven red by removing the phone rule.

DEPLOY-DRIFT PASS (28 Oct, later): `check_deploy_drift.sh` reads the TRACKED manifest, fetches the index and 24
evenly sampled pages and compares md5s, and compares the live `sitemap-planes.xml`'s URL set with the manifest's
pages. Red before the first deploy, as the planes-file pass was. Proven: live 25 UNREACHABLE; a local copy 25 of 25,
gap 0; an edited index DRIFT; a dropped sitemap URL "gap 1". Thursday's runbook carries it as an OPTIONAL Part D
(merge rehearsed on A, B and C: clean). NOT YET: links from the area pages (after Thursday: Part C regenerates
them), and Search Console (Bill's). Ships after Thursday's three changesets and Bill's review of the preview.
