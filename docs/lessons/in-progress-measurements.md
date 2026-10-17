# Measurements held, not yet shown

> Moved verbatim from `CLAUDE.md` on 2026-10-17 to keep the session-start file small.
> DEFRA AURN monitors; how often planes pass (adsb.lol, CAA comparison, outages, circuits).
> Statements are dated as written; re-measure a number before relying on it, and when a
> rule here changes, update the one-line rule in `CLAUDE.md` too.

<!-- CLAUDE.md lines 640-671 (2026-10-16) -->
**DEFRA's AURN reference monitors are HELD, not shown (2026-10-13).** `scripts/fetch_aurn.py --fetch` writes
`data/aurn-sites.json` (checked in; raw R files in ignored `data/aurn/`, `--fetch`/`--verify` need `pip install
pyreadr`). Its year is `load_defra_air_quality.PCM_YEAR`, never the newest summary: PCM is calibrated against AURN
of the same year, and `--check` (BLOCKING, offline) reds when air quality rolls until it is re-fetched. Ratified
only (a site that closed mid-year counts to its closing day), 75% capture, UK-AIR's attribution word for word
("licenced"), a usable site inside EVERY covered city or a `NO_SITE_INSIDE` reason. Display only, never scored,
never ranked (UK-AIR: "not scientifically sound"). Nothing reads it yet: the "nearest official monitor" line ships
with the Breathe London half (ROADMAP plan, GLA key pending) and needs a distance scope - Greater Norwich's
nearest NO2 clearing the floor is 77 km away.

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

