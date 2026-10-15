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
            out[code] = {'centre': (lat, lon), 'zone_km': reach + ZONE_PAD_KM, 'runways': rw}
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


def coverage_verdict(tracked, official, same_period):
    """Whether an airport's tracking is complete enough to publish anything
    built on it: (ok, reason). `same_period` is False when the official figure
    covers a different stretch of time (one day against 2025's average day), and
    then nothing passes, because the ratio mixes coverage with traffic change."""
    if not same_period:
        return False, ('provisional: compare a whole month with the CAA figure '
                       'for that month')
    if official < MIN_OFFICIAL:
        return False, f'too little traffic to judge ({official:.0f} official; need {MIN_OFFICIAL})'
    ratio = tracked / official
    if ratio < COVERAGE_FLOOR:
        return False, f'misses flights ({ratio:.1%} of the official count): would understate'
    if ratio > COVERAGE_CEILING:
        return False, f'counts more than the official figure ({ratio:.1%}): not every count is a movement'
    return True, f'{ratio:.1%} of the official count'


def period_verdict(tracked, official, same_period, missing_days):
    """coverage_verdict() for a whole period. A day the airport could not be
    measured leaves the tracked total short of the period the official figure
    covers, so the comparison is no longer like for like and cannot pass,
    however close the ratio happens to land."""
    if same_period and missing_days:
        return False, f'{missing_days} day(s) unmeasured: the period is incomplete'
    return coverage_verdict(tracked, official, same_period)


def count_day(extract_path, only=None):
    """{code: {'landing', 'take-off', 'runways', 'unseen', 'field', 'how'} or
    None} for one day's extract. The field level is measured per DAY, because
    QNH - and with it every pressure altitude - moves from day to day."""
    airports = load_airports()
    with gzip.open(extract_path, 'rt', encoding='utf-8') as fh:
        traces = [json.loads(line) for line in fh]
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
        kinds, by_runway, unseen = Counter(), defaultdict(Counter), 0
        for rec in near:
            moves, u = movements(rec, ap, field)
            unseen += u
            for kind, rw, _ in moves:
                kinds[kind] += 1
                by_runway[rw or '?'][kind] += 1
        out[code] = {'landing': kinds['landing'], 'take-off': kinds['take-off'],
                     'runways': {rw: dict(c) for rw, c in by_runway.items()},
                     'unseen': unseen, 'field': field, 'how': how}
    return out


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
    is provisional, because the ratio then mixes coverage with traffic change."""
    days = sorted(day_of(p) for p in extracts)
    if len(set(days)) != len(days):
        raise SystemExit('the same day appears twice among the extracts')
    period, official = caa_table(caa_path)
    same = period is not None and set(days) == period_days(period)
    with ProcessPoolExecutor(min(workers, len(extracts))) as pool:
        per_day = dict(pool.map(_count_day, [(p, only) for p in extracts]))

    span = f'{days[0]} to {days[-1]}' if len(days) > 1 else f'{days[0]}'
    print(f'{len(days)} day(s), {span}; CAA table {caa_path.name} (period {period})'
          + ('' if same else '  [different periods: per-day averages, provisional]'))
    head = 'tracked' if same else 'tracked/day'
    print(f'\n{"airport":7} {"landings":>8} {"take-offs":>9} {head:>11} {"CAA":>8} {"ratio":>6} '
          f'{"unheard":>7}  days  verdict')
    airports = load_airports()
    for code in airports:
        if only and code not in only:
            continue
        rows = [d[code] for d in per_day.values() if d.get(code)]
        if not rows:
            print(f'{code:7} {"-":>8} {"-":>9} {"-":>11}  too few aircraft')
            continue
        land = sum(r['landing'] for r in rows)
        take = sum(r['take-off'] for r in rows)
        unseen = sum(r['unseen'] for r in rows)
        total = land + take
        caa = official.get(code)
        if same:
            tracked, official_v = total, caa
        else:
            tracked = total / len(rows)
            official_v = caa / len(period_days(period)) if caa else None
        ratio = f'{tracked / official_v:6.1%}' if official_v else '     -'
        caa_s = f'{official_v:8.0f}' if official_v else '       -'
        verdict = (period_verdict(tracked, official_v, same, len(days) - len(rows))
                   if official_v else None)
        note = (verdict[1] if verdict else 'no official figure')
        print(f'{code:7} {land:8} {take:9} {tracked:11.0f} {caa_s} {ratio} {unseen:7}  {len(rows):4}  '
              + ('PUBLISHABLE: ' if verdict and verdict[0] else '') + note)
        if show_runways:
            by_rw = defaultdict(Counter)
            for r in rows:
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
