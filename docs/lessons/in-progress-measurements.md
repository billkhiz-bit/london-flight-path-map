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
all gitignored; run it with `-I` under a CURRENT Python, the archive is untrusted input: 3.11's tarfile fixes stop at 3.11.9 on Windows, so Bill's machine uses an unregistered 3.13 at `C:/Users/bilal/tools/python-3.13.15/python.exe`, 2026-10-16); `scripts/adsb_movements.py` counts
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

