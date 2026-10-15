"""Count take-offs and landings per airport and runway from an adsb.lol extract,
and check the count against the CAA's official movement statistics.

WHY THIS EXISTS
---------------
Step 1 of "how often planes pass" (ROADMAP, Bill's ruling of 2026-10-15: as
accurate as the best available source allows). Before any per-home figure is
built on community flight tracking, the tracking has to be shown to SEE the
flights: an airport whose take-offs and landings the receivers miss would
publish a quiet sky over a busy runway, which is the absence-as-measurement
defect this repo has fixed four times. So the first number this pipeline makes
is one an official source also publishes - movements per airport - and the two
are compared before anything else is derived.

THE RULE (one airport, one aircraft's day of points, all from adsb_extract.py)
------------------------------------------------------------------------------
- The airport ZONE is a circle round the mean of its runway thresholds, wide
  enough to hold every threshold plus ZONE_PAD_KM.
- An aircraft is LOW in the zone when it reports 'ground', or its pressure
  altitude is within LOW_ABOVE_FT of the field's pressure level that day.
  Pressure altitude is not height: it moves ~27 ft per hPa of QNH, up to
  ~1,000 ft on a deep low. So the field level is MEASURED per airport per day -
  the median last airborne altitude before a 'ground' report (touchdown) - and
  falls back to a low percentile of in-zone minima where receivers do not hear
  the surface. The report says which.
- Low points are split into separate LOW RUNS wherever the aircraft climbs back
  above the low band (a touch-and-go circuit is a landing AND a take-off) or is
  unheard for more than RUN_GAP_S.
- A low run is a LANDING when the same aircraft was at least CLIMB_FT above the
  field in the WINDOW_S before it (and since the previous low run), and a
  TAKE-OFF when it is at least CLIMB_FT above the field in the WINDOW_S after
  it (and before the next one). CLIMB_FT is set under a training circuit's
  1,000 ft so circuits count, as the CAA counts them.
- The runway is the one whose bearing is within RUNWAY_MATCH_DEG of the
  aircraft's track over the zone, nearest its centreline (27L and 27R share a
  bearing; they differ by 1.4 km across it).

WHAT IT CANNOT SEE, stated so the comparison is read correctly
--------------------------------------------------------------
- A movement whose low run the receivers never hear is not counted; the report
  shows how many zone visits came near (UNSEEN_BAND_FT) without being heard low,
  so a coverage hole is visible rather than silent.
- Aircraft without ADS-B (some light aircraft) are invisible to it. Training
  airfields will undercount for that reason, not because the rule is wrong.
- A trace is one UTC day, so a landing in the first minutes of the day can lose
  its approach to the previous file. Heathrow's night restrictions make this
  rare there; the full-year run will join days.
- A go-around below the low band reads as a landing and a take-off.

THE FEED HAS OUTAGES, AND THEY ARE MEASURED, NOT GUESSED (2026-10-15)
---------------------------------------------------------------------
adsb.lol's archive has holes: in August 2026, 6 of 31 days lost hours (9 Aug
12:15-18:05 empty; 12 Aug 20:25 to 13 Aug 07:00 empty; 1 Aug 16:00 to 2 Aug
02:00 THINNED to ~5% of the usual aircraft with no gap at all, so a gap test
alone misses it). They hit the UK and the US in the same windows, and cost
Heathrow up to 47% of a day's movements. So each day's FEED is profiled -
distinct aircraft per FEED_BIN_S window, per region - against the median of the
same window over the nearby days, and a window under FEED_OUT_RATIO of it is an
outage. Measured over August: outage windows read 0.00-0.09 of usual, the worst
window on a healthy day 0.56 (UK, 27 Aug), and nothing in between; the cut sits
in that gap. The test is never made on an airport's own counts: London City's
Saturdays are a quarter of its weekdays by timetable, and 2 Aug's outage fell
in Heathrow's quiet night and cost East Midlands, a night freight hub, 31%.
Timetables run on LOCAL time, so each nearby day is turned onto the judged
day's clock first (clock_offset_bins()): measured on August, comparing in UTC
alone put false outages on 24 of 25 healthy UK days a clock change later.
A day of genuinely collapsed traffic (a nationwide air-traffic failure) would
also read as an outage and be left out; usable_share() would then give it a
normal day's share, lifting the ratio a little. None has been seen yet.

A day with an outage is LEFT OUT, never patched, and the official figure is
scaled to the days kept, each weekday weighted by the airport's own average on
kept days of that weekday (usable_share()). A month needs MIN_USABLE_FRACTION
of its days kept to be judged at all.

CIRCUITS ARE MOVEMENTS, AND AIRPORTS REPORT THEM UNEVENLY
---------------------------------------------------------
The CAA's definitions say so twice: "Touch and go operations are counted as
two movements" (Test and training; Aero-club). A landing followed by a take-off
from the same aircraft between CIRCUIT_MIN_S and CIRCUIT_S later is a circuit,
reported in its own column. Measured over August's UK pairs: 737 touch-and-goes
at 50-60 s, light aircraft at 70-130 s, and a separate group under 30 s - low
practice approaches, go-arounds, and the pairs a single bad altitude reading
makes (5-8 a day in the whole extract) - which stay ordinary movements.
Measured on August's complete days: Cardiff's return includes its circuits,
East Midlands' evidently omits most (a Ryanair 737 flew 32 circuits on 7 Aug
against 62 training movements in the CAA's whole month). So an airport passes
when ONE reading fits at both ends: every movement within 95-105% of the
official count (its return includes circuits), or every movement bar circuits
within it (its return leaves them out). Passing the floor on one reading and
the ceiling on the other would let through a 20% shortfall (code review,
2026-10-15).

THE COMPARISON IS LIKE FOR LIKE OR IT IS PROVISIONAL. The CAA publishes Table
03 per month and per year (data/caa/, gitignored; fetch from the CAA's "UK
airport data" pages - the site answers a browser User-Agent). Given extracts
for EVERY day of the table's period, totals are compared and the publish
verdict is real; anything else compares per-day averages and is provisional,
because the ratio then mixes coverage with traffic change. US airports print
their count with no official comparison yet.

Usage:
    python -I scripts/adsb_movements.py data/adsb/extract/2026-10-14.jsonl.gz
    python -I scripts/adsb_movements.py data/adsb/extract/2026-08-*.jsonl.gz \\
        --caa data/caa/table_03_aircraft_movements_2026-08.csv
    python -I scripts/adsb_movements.py <extracts> --airport LHR --runways
"""

import argparse
import calendar
import csv
import datetime as dt
import gzip
import json
import math
import re
import statistics
import sys
import zoneinfo
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROCEDURE_FILES = (ROOT / 'data' / 'flight-procedures.json',
                   ROOT / 'data' / 'us-flight-procedures.json')
CAA_TABLE = ROOT / 'data' / 'caa' / 'table_03_1_aircraft_movements_2025.csv'

ZONE_PAD_KM = 1.5
LOW_ABOVE_FT = 400
CLIMB_FT = 700
WINDOW_S = 900
RUN_GAP_S = 300
RUNWAY_MATCH_DEG = 30
TRACK_WINDOW_S = 120
UNSEEN_BAND_FT = 1200
MIN_TOUCHDOWNS = 5
# A landing then a take-off by the same aircraft in this window is a circuit.
# Measured: 737 touch-and-goes 50-60 s, light aircraft 70-130 s, a turnaround
# on the stand never under 20 minutes; under 30 s is a low approach, a
# go-around or a glitch (see "CIRCUITS ARE MOVEMENTS" above).
CIRCUIT_MIN_S = 30
CIRCUIT_S = 180

# The feed test. See "THE FEED HAS OUTAGES" above for the measurement behind
# FEED_OUT_RATIO; the window is two weeks either side so a year-long run follows
# the seasons, and fewer than FEED_MIN_REFERENCE_DAYS nearby days cannot say
# what usual is. REGION_ZONE gives each region's clock (New York and the Bay
# Area change on the same dates).
FEED_BIN_S = 600
FEED_OUT_RATIO = 0.3
FEED_WINDOW_DAYS = 14
FEED_MIN_REFERENCE_DAYS = 7
REGIONS = ('uk', 'us')
REGION_ZONE = {'uk': 'Europe/London', 'us': 'America/New_York'}

# CAA Table 03 names -> the airport codes our procedure files use. Every one
# must match exactly one row (asserted), because name matching has failed in
# this repo five times.
CAA_NAMES = {
    'HEATHROW': 'LHR', 'GATWICK': 'LGW', 'STANSTED': 'STN', 'LUTON': 'LTN',
    'LONDON CITY': 'LCY', 'MANCHESTER': 'MAN', 'BIRMINGHAM': 'BHX',
    'LEEDS BRADFORD': 'LBA', 'LIVERPOOL (JOHN LENNON)': 'LPL',
    'NEWCASTLE': 'NCL', 'BRISTOL': 'BRS', 'EAST MIDLANDS INTERNATIONAL': 'EMA',
    'CARDIFF WALES': 'CWL', 'TEESSIDE INTERNATIONAL AIRPORT': 'MME',
    'NORWICH': 'NWI',
}


def km_between(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 12742.0 * math.asin(math.sqrt(a))


def region_of(lon):
    """'us' west of the mid-Atlantic, 'uk' otherwise: the extract holds nothing else."""
    return 'us' if lon < -30 else 'uk'


def angle_diff(a, b):
    return abs((a - b + 180) % 360 - 180)


def cross_track_km(lat, lon, thr, bearing):
    """Signed distance of a point from the runway centreline through `thr`."""
    d = km_between(thr[0], thr[1], lat, lon)
    if d == 0:
        return 0.0
    y = math.sin(math.radians(lon - thr[1])) * math.cos(math.radians(lat))
    x = (math.cos(math.radians(thr[0])) * math.sin(math.radians(lat))
         - math.sin(math.radians(thr[0])) * math.cos(math.radians(lat))
         * math.cos(math.radians(lon - thr[1])))
    brg = math.degrees(math.atan2(y, x))
    return d * math.sin(math.radians(brg - bearing))


def load_airports(paths=PROCEDURE_FILES):
    """{code: {'centre', 'zone_km', 'runways': {des: (thr, bearing)}}}."""
    out = {}
    for path in paths:
        for code, ap in json.loads(path.read_text(encoding='utf-8'))['airports'].items():
            rw = {d: (tuple(r['thr']), float(r['true_brg']))
                  for d, r in ap.get('runways', {}).items() if r.get('thr')}
            lat = sum(t[0] for t, _ in rw.values()) / len(rw)
            lon = sum(t[1] for t, _ in rw.values()) / len(rw)
            reach = max(km_between(lat, lon, t[0], t[1]) for t, _ in rw.values())
            out[code] = {'centre': (lat, lon), 'zone_km': reach + ZONE_PAD_KM, 'runways': rw,
                         'region': region_of(lon)}
    return out


def caa_table(path=CAA_TABLE):
    """(period, {code: official movements in that period}) from a CAA Table 03
    CSV, or (None, {}) if absent. The period is 'YYYY' for an annual table and
    'YYYYMM' for a monthly one. The two layouts name their columns differently
    (rpt_apt_name / report_period in the annual, reporting_airport_name /
    reporting_period in the monthly), so both are read."""
    if not path.exists():
        return None, {}
    rows = list(csv.DictReader(path.open(encoding='utf-8-sig')))
    name_col = next(c for c in ('rpt_apt_name', 'reporting_airport_name') if c in rows[0])
    period_col = next(c for c in ('report_period', 'reporting_period') if c in rows[0])
    periods = {r[period_col].strip() for r in rows}
    if len(periods) != 1 or not re.fullmatch(r'\d{4}(\d{2})?', next(iter(periods))):
        raise SystemExit(f'CAA table {path.name}: expected one period, got {sorted(periods)}')
    out = {}
    for name, code in CAA_NAMES.items():
        hits = [r for r in rows if r[name_col].strip() == name]
        if len(hits) != 1:
            raise SystemExit(f'CAA table: {name!r} matched {len(hits)} rows, expected 1')
        out[code] = int(hits[0]['grand_total'])
    return periods.pop(), out


def period_days(period):
    """Every date the CAA period covers."""
    year = int(period[:4])
    if len(period) == 4:
        first, last = dt.date(year, 1, 1), dt.date(year, 12, 31)
    else:
        month = int(period[4:])
        first = dt.date(year, month, 1)
        last = dt.date(year, month, calendar.monthrange(year, month)[1])
    return {first + dt.timedelta(days=i) for i in range((last - first).days + 1)}


def is_ground(p):
    return p[3] == 'ground'


def baro(p):
    return p[3] if isinstance(p[3], (int, float)) else None


def field_level(traces, ap):
    """The field's pressure altitude that day, and how it was found."""
    (clat, clon), zone = ap['centre'], ap['zone_km']
    touchdowns, minima = [], []
    for rec in traces:
        pts = rec['pts']
        lows = []
        for i, p in enumerate(pts):
            if km_between(p[1], p[2], clat, clon) > zone:
                continue
            if is_ground(p) and i and baro(pts[i - 1]) is not None and p[0] - pts[i - 1][0] <= 60:
                touchdowns.append(baro(pts[i - 1]))
            elif baro(p) is not None:
                lows.append(baro(p))
        if lows:
            minima.append(min(lows))
    if len(touchdowns) >= MIN_TOUCHDOWNS:
        return statistics.median(touchdowns), f'touchdown median of {len(touchdowns)}'
    if len(minima) >= MIN_TOUCHDOWNS:
        return sorted(minima)[len(minima) // 10], f'p10 of {len(minima)} in-zone minima (no surface reports)'
    return None, 'too few aircraft'


def runway_for(points, ap):
    """Designator of the runway this stretch of flight lines up with, or None."""
    tracks = [p[6] for p in points if p[6] is not None and not is_ground(p)]
    if not tracks:
        return None
    # Mean of angles, not of numbers: 359 and 1 average to 0, not 180.
    s = sum(math.sin(math.radians(t)) for t in tracks)
    c = sum(math.cos(math.radians(t)) for t in tracks)
    heading = math.degrees(math.atan2(s, c)) % 360
    lat = statistics.median(p[1] for p in points)
    lon = statistics.median(p[2] for p in points)
    best = None
    for des, (thr, brg) in ap['runways'].items():
        if angle_diff(heading, brg) > RUNWAY_MATCH_DEG:
            continue
        off = abs(cross_track_km(lat, lon, thr, brg))
        if best is None or off < best[0]:
            best = (off, des)
    return best and best[1]


def movements(rec, ap, field):
    """[(kind, runway, epoch_s)] for one aircraft's day at one airport, plus
    the number of zone visits that came within UNSEEN_BAND_FT unheard low."""
    pts = rec['pts']
    (clat, clon), zone = ap['centre'], ap['zone_km']
    low_cut = field + LOW_ABOVE_FT
    inzone = [km_between(p[1], p[2], clat, clon) <= zone for p in pts]
    low = [z and (is_ground(p) or (baro(p) is not None and baro(p) <= low_cut))
           for p, z in zip(pts, inzone, strict=True)]

    # Split low points into runs: a new run starts after a gap, or after the
    # aircraft has been seen above the low band (a circuit or a go-around).
    runs, cur, last_t = [], [], None
    for i, p in enumerate(pts):
        if low[i]:
            if cur and (p[0] - last_t > RUN_GAP_S):
                runs.append(cur)
                cur = []
            cur.append(i)
            last_t = p[0]
        elif cur and inzone[i] and baro(p) is not None and baro(p) > low_cut:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)

    # Higher means CLIMB_FT above the FIELD, not above the run's edge point: a
    # run's last low point can sit LOW_ABOVE_FT up, and measuring from there
    # asked a 1,000 ft circuit for 1,100 ft and missed its take-off.
    high = field + CLIMB_FT
    out = []
    for k, run in enumerate(runs):
        first, last = pts[run[0]], pts[run[-1]]
        # The climb that makes a landing must come AFTER the previous low run,
        # and the climb that makes a take-off BEFORE the next one. Without the
        # bound, an aircraft waiting silent at the holding point for over
        # RUN_GAP_S splits its time on the ground into two runs, both of which
        # see the same climb: one take-off counted twice.
        since = pts[runs[k - 1][-1]][0] if k else -math.inf
        until = pts[runs[k + 1][0]][0] if k + 1 < len(runs) else math.inf
        before = [p for p in pts if max(first[0] - WINDOW_S, since) < p[0] < first[0]]
        after = [p for p in pts if last[0] < p[0] <= last[0] + WINDOW_S and p[0] < until]
        if any(baro(p) is not None and baro(p) >= high for p in before):
            approach = [p for p in before if first[0] - p[0] <= TRACK_WINDOW_S
                        and km_between(p[1], p[2], clat, clon) <= zone + 3]
            out.append(('landing', runway_for(approach, ap), first[0]))
        if any(baro(p) is not None and baro(p) >= high for p in after):
            climb = [p for p in after if p[0] - last[0] <= TRACK_WINDOW_S
                     and km_between(p[1], p[2], clat, clon) <= zone + 3]
            out.append(('take-off', runway_for(climb, ap), last[0]))

    # Visits that came close but were never heard low: a coverage signal.
    unseen = 0
    if not runs:
        near = [baro(p) for p, z in zip(pts, inzone, strict=True) if z and baro(p) is not None]
        if near and min(near) <= field + UNSEEN_BAND_FT:
            unseen = 1
    return out, unseen


def circuit_movements(moves):
    """How many of one aircraft's movements (in time order, as movements()
    returns them) are circuits: a landing followed by a take-off between
    CIRCUIT_MIN_S and CIRCUIT_S later, two movements each."""
    n, i = 0, 0
    while i + 1 < len(moves):
        (k1, _, t1), (k2, _, t2) = moves[i], moves[i + 1]
        if k1 == 'landing' and k2 == 'take-off' and CIRCUIT_MIN_S <= t2 - t1 <= CIRCUIT_S:
            n += 2
            i += 2
        else:
            i += 1
    return n


def feed_profile(traces, day):
    """{region: [distinct aircraft heard in each FEED_BIN_S window of the UTC
    day]}. Each trace is one aircraft's day, so an aircraft counts once per
    window per region however many points it reported there."""
    t0 = dt.datetime(day.year, day.month, day.day, tzinfo=dt.UTC).timestamp()
    nbins = 86400 // FEED_BIN_S
    counts = {r: [0] * nbins for r in REGIONS}
    for rec in traces:
        hit = {(region_of(p[2]), int((p[0] - t0) // FEED_BIN_S)) for p in rec['pts']}
        for region, b in hit:
            if 0 <= b < nbins:
                counts[region][b] += 1
    return counts


def clock_offset_bins(day, region):
    """The region's clock ahead of UTC at midday on `day`, in FEED_BIN_S windows."""
    zone = zoneinfo.ZoneInfo(REGION_ZONE[region])
    return int(zone.utcoffset(dt.datetime(day.year, day.month, day.day, 12)).total_seconds()) // FEED_BIN_S


def feed_gaps(profiles, region='uk'):
    """{day: number of windows in which the feed carried under FEED_OUT_RATIO
    of that window's usual aircraft} for one region's {day: profile}. Usual is
    the median of the same LOCAL time over the days within FEED_WINDOW_DAYS:
    across a clock change each nearby day is turned by the change, so 07:00 is
    compared with 07:00 (the hour it wraps is midnight, from the same clock). A
    day with fewer than FEED_MIN_REFERENCE_DAYS nearby days is None, not judged."""
    offset = {d: clock_offset_bins(d, region) for d in profiles}
    out = {}
    for day, prof in profiles.items():
        ref = []
        for d, p in profiles.items():
            if abs((d - day).days) <= FEED_WINDOW_DAYS:
                k = (offset[day] - offset[d]) % len(p)
                ref.append(p[k:] + p[:k])
        if len(ref) < FEED_MIN_REFERENCE_DAYS:
            out[day] = None
            continue
        usual = [statistics.median(p[b] for p in ref) for b in range(len(prof))]
        out[day] = sum(1 for n, u in zip(prof, usual, strict=True) if u and n < FEED_OUT_RATIO * u)
    return out


def usable_share(kept, period):
    """The share of the period's movements expected on the kept days, from
    {day: tracked movements} on those days: each weekday is weighted by the
    airport's own average on kept days of that weekday, because a weekly
    timetable is not flat (London City's Saturdays are a quarter of its
    weekdays). None when a weekday of the period has no kept day to weight by."""
    by_weekday = defaultdict(list)
    for day, n in kept.items():
        by_weekday[day.weekday()].append(n)
    if any(not by_weekday[d.weekday()] for d in period):
        return None
    weight = {wd: statistics.mean(v) for wd, v in by_weekday.items()}
    whole = sum(weight[d.weekday()] for d in period)
    if not whole:
        return None
    return sum(weight[d.weekday()] for d in kept) / whole


# The publish floor, set 2026-10-15 (Bill: "if you feel it's right"). Below the
# floor the tracking misses flights, and every per-home figure built on it would
# read QUIETER than the sky is - the one direction this product never errs in.
# Above the ceiling the rule is counting something that is not a movement. Both
# are a first setting: month-for-month comparisons will show whether it can
# tighten towards +/-3%.
COVERAGE_FLOOR = 0.95
COVERAGE_CEILING = 1.05
# Official movements in the compared period. Below this a ratio is mostly noise
# (Cardiff's 46 a day swings by half from one day to the next).
MIN_OFFICIAL = 300
# Outage days are left out and the official figure scaled to the rest; past a
# quarter of the period, the scaling would be carrying the comparison.
MIN_USABLE_FRACTION = 0.75


def coverage_verdict(tracked, official, same_period, circuits=0):
    """Whether an airport's tracking is complete enough to publish anything
    built on it: (ok, reason). `same_period` is False when the official figure
    covers a different stretch of time (one day against 2025's average day), and
    then nothing passes, because the ratio mixes coverage with traffic change.
    `circuits` is how many of `tracked` are circuits. Airports report them
    unevenly, so the count passes if ONE reading fits at both ends: with
    circuits (the return holds them) or without (it leaves them out)."""
    if not same_period:
        return False, ('provisional: compare a whole month with the CAA figure '
                       'for that month')
    if official < MIN_OFFICIAL:
        return False, f'too little traffic to judge ({official:.0f} official; need {MIN_OFFICIAL})'
    ratio = tracked / official
    plain = (tracked - circuits) / official
    if COVERAGE_FLOOR <= ratio <= COVERAGE_CEILING:
        return True, f'{ratio:.1%} of the official count'
    if COVERAGE_FLOOR <= plain <= COVERAGE_CEILING:
        return True, (f'{plain:.1%} of the official count without circuits, which this '
                      f"airport's return evidently leaves out ({ratio:.1%} with them)")
    if ratio < COVERAGE_FLOOR:
        return False, f'misses flights ({ratio:.1%} of the official count): would understate'
    if plain > COVERAGE_CEILING:
        return False, (f'counts more than the official figure ({ratio:.1%}, {plain:.1%} '
                       'without circuits): not every count is a movement')
    return False, (f'neither reading fits ({ratio:.1%} with circuits, {plain:.1%} without): '
                   'an over-count or a shortfall, and the figures cannot say which')


def period_verdict(tracked, official, same_period, missing_days, circuits=0,
                   kept_days=None, period_len=None):
    """coverage_verdict() for a whole period. `official` is the CAA's figure
    scaled to the kept days (usable_share()), or None if it could not be.

    A day the FEED was complete on but the airport could not be measured is not
    an outage, so it is not left out: the comparison is then no longer like for
    like and cannot pass, however close the ratio happens to land. Outage days
    are left out, but only up to MIN_USABLE_FRACTION of the period."""
    if same_period and missing_days:
        return False, f'{missing_days} day(s) unmeasured: the period is incomplete'
    if same_period and kept_days is not None and kept_days < MIN_USABLE_FRACTION * period_len:
        return False, (f'the feed was complete on only {kept_days} of {period_len} days: '
                       'too few to judge the period')
    if official is None:
        return False, ('a weekday has no day with a complete feed: the official count '
                       'on the kept days cannot be estimated')
    return coverage_verdict(tracked, official, same_period, circuits)


def count_day(extract_path, only=None):
    """{'airports': {code: {'landing', 'take-off', 'circuits', 'runways',
    'unseen', 'field', 'how'} or None}, 'feed': feed_profile()} for one day's
    extract. The field level is measured per DAY, because QNH - and with it
    every pressure altitude - moves from day to day."""
    airports = load_airports()
    with gzip.open(extract_path, 'rt', encoding='utf-8') as fh:
        traces = [json.loads(line) for line in fh]
    feed = feed_profile(traces, day_of(Path(extract_path)))
    # Each trace's box, once: an airport's zone is a few km across, so most of a
    # day's ~7,000 aircraft can be ruled out by four comparisons instead of a
    # great-circle distance per point (~5M points x 22 airports).
    boxes = [(min(p[1] for p in r['pts']), max(p[1] for p in r['pts']),
              min(p[2] for p in r['pts']), max(p[2] for p in r['pts'])) for r in traces]
    out = {}
    for code, ap in airports.items():
        if only and code not in only:
            continue
        (clat, clon), zone = ap['centre'], ap['zone_km']
        dlat = zone / 111.2
        dlon = zone / (111.2 * math.cos(math.radians(clat)))
        near = [r for r, (la0, la1, lo0, lo1) in zip(traces, boxes, strict=True)
                if la0 <= clat + dlat and la1 >= clat - dlat and lo0 <= clon + dlon and lo1 >= clon - dlon
                and any(km_between(p[1], p[2], clat, clon) <= zone for p in r['pts'])]
        field, how = field_level(near, ap)
        if field is None:
            out[code] = None
            continue
        kinds, by_runway, unseen, circuits = Counter(), defaultdict(Counter), 0, 0
        for rec in near:
            moves, u = movements(rec, ap, field)
            unseen += u
            circuits += circuit_movements(moves)
            for kind, rw, _ in moves:
                kinds[kind] += 1
                by_runway[rw or '?'][kind] += 1
        out[code] = {'landing': kinds['landing'], 'take-off': kinds['take-off'],
                     'circuits': circuits,
                     'runways': {rw: dict(c) for rw, c in by_runway.items()},
                     'unseen': unseen, 'field': field, 'how': how}
    return {'airports': out, 'feed': feed}


def _count_day(args):
    path, only = args
    return path, count_day(path, only)


def day_of(path):
    m = re.match(r'(\d{4}-\d{2}-\d{2})', path.name)
    if not m:
        raise SystemExit(f'{path.name}: extract names must start with the day (YYYY-MM-DD)')
    return dt.date.fromisoformat(m.group(1))


def report(extracts, caa_path=CAA_TABLE, only=None, show_runways=False, workers=6):
    """Sum every day's counts per airport and compare with the CAA table.

    Like for like only: when the extracts cover EVERY day of the table's period
    (a whole month against a monthly table), totals are compared and the publish
    verdict is real. Otherwise the per-day averages are compared and the verdict
    is provisional, because the ratio then mixes coverage with traffic change.

    Days with a feed outage in the airport's region are left out of both sides:
    the tracked total is summed over the kept days, and the CAA's figure is
    scaled to them by usable_share()."""
    days = sorted(day_of(p) for p in extracts)
    if len(set(days)) != len(days):
        raise SystemExit('the same day appears twice among the extracts')
    period, official = caa_table(caa_path)
    whole = period_days(period) if period else set()
    same = period is not None and set(days) == whole
    with ProcessPoolExecutor(min(workers, len(extracts))) as pool:
        per_day = {day_of(p): r for p, r in pool.map(_count_day, [(p, only) for p in extracts])}
    gaps = {region: feed_gaps({d: r['feed'][region] for d, r in per_day.items()}, region)
            for region in REGIONS}

    span = f'{days[0]} to {days[-1]}' if len(days) > 1 else f'{days[0]}'
    print(f'{len(days)} day(s), {span}; CAA table {caa_path.name} (period {period})'
          + ('' if same else '  [different periods: per-day averages, provisional]'))
    for region in REGIONS:
        g = gaps[region]
        out = [d for d in days if g[d]]
        unjudged = [d for d in days if g[d] is None]
        line = (f'feed, {region.upper()}: complete on {len(days) - len(out) - len(unjudged)} '
                f'of {len(days)} day(s)')
        if out:
            line += '; outages ' + ', '.join(f'{d:%d %b} ({g[d] * FEED_BIN_S // 60} min)' for d in out)
        if unjudged:
            line += (f'; not judged on {len(unjudged)} (needs {FEED_MIN_REFERENCE_DAYS}+ days '
                     f'within {FEED_WINDOW_DAYS})')
        print(line)
    if same:
        print('CAA = the official figure for the period, scaled to the days kept (weekday-weighted)')
    head = 'tracked' if same else 'tracked/day'
    print(f'\n{"airport":7} {"landings":>8} {"take-offs":>9} {head:>11} {"circuits":>8} {"CAA":>8} '
          f'{"ratio":>6} {"w/o circ":>8} {"unheard":>7}   days  verdict')
    airports = load_airports()
    for code, ap in airports.items():
        if only and code not in only:
            continue
        g = gaps[ap['region']]
        # A day whose feed is not judged (too few days to know usual) is kept:
        # such a run is never a whole period, so its verdict is provisional anyway.
        open_days = [d for d in days if not g[d]]
        kept = {d: per_day[d]['airports'][code] for d in open_days if per_day[d]['airports'].get(code)}
        missing = len(open_days) - len(kept)
        if not kept:
            print(f'{code:7} {"-":>8} {"-":>9} {"-":>11}  no day with a complete feed and enough aircraft')
            continue
        land = sum(r['landing'] for r in kept.values())
        take = sum(r['take-off'] for r in kept.values())
        circ = sum(r['circuits'] for r in kept.values())
        unseen = sum(r['unseen'] for r in kept.values())
        total = land + take
        caa = official.get(code)
        if same:
            tracked = total
            share = usable_share({d: r['landing'] + r['take-off'] for d, r in kept.items()}, whole)
            official_v = caa * share if caa is not None and share else None
        else:
            tracked, circ = total / len(kept), circ / len(kept)
            official_v = caa / len(whole) if caa is not None else None
        ratio = f'{tracked / official_v:6.1%}' if official_v else '     -'
        plain = f'{(tracked - circ) / official_v:8.1%}' if official_v else '       -'
        caa_s = f'{official_v:8.0f}' if official_v else '       -'
        if caa is None:
            note = 'no official figure'
        elif same:
            if any(g[d] is None for d in days):
                verdict = (False, 'feed not judged on every day')
            else:
                verdict = period_verdict(tracked, official_v, True, missing, circ, len(kept), len(whole))
            note = ('PUBLISHABLE: ' if verdict[0] else '') + verdict[1]
        else:
            note = period_verdict(tracked, official_v, False, missing)[1]
        print(f'{code:7} {land:8} {take:9} {tracked:11.0f} {circ:8.0f} {caa_s} {ratio} {plain} '
              f'{unseen:7}  {len(kept):2}/{len(days):<2}  {note}')
        if show_runways:
            by_rw = defaultdict(Counter)
            for r in kept.values():
                for rw, c in r['runways'].items():
                    by_rw[rw].update(c)
            for rw in sorted(by_rw):
                c = by_rw[rw]
                print(f'        {rw:5} landings {c["landing"]:6}  take-offs {c["take-off"]:6}')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('extracts', type=Path, nargs='+', help='one or more data/adsb/extract/<day>.jsonl.gz')
    ap.add_argument('--caa', type=Path, default=CAA_TABLE,
                    help='CAA Table 03 CSV, annual or monthly (default: the 2025 annual table)')
    ap.add_argument('--airport', action='append', help='limit to these codes (repeatable)')
    ap.add_argument('--runways', action='store_true', help='also break each airport down by runway')
    ap.add_argument('--workers', type=int, default=6)
    args = ap.parse_args()
    report(args.extracts, args.caa, set(args.airport) if args.airport else None,
           args.runways, args.workers)
    return 0


if __name__ == '__main__':
    sys.exit(main())
