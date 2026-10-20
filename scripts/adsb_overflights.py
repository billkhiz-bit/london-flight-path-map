"""Count CAP 1498 overflights per 100 m grid cell per day from an adsb.lol extract. UK only, for now.

WHY THIS EXISTS
---------------
Step 2 of "how often planes pass" (ROADMAP "IN PROGRESS: how often planes fly"). Step 1
(scripts/adsb_movements.py) showed the community tracking SEES the flights: July 2026 passed the
coverage floor at 14 of 15 UK airports against the CAA's own monthly counts. This step turns the same
tracks into the number a resident asks for, how many aircraft pass over a home, per 100 m cell of the
British National Grid, one file per day. A postcode reads its cell at NSPL's `east1m`/`north1m`
(scripts/postcode_grid.py), never a re-projection, so the cells are BNG cells.

THE DEFINITION (Bill, 2026-10-19): the CAA's CAP 1498 "Definition of overflight" (Feb 2017): "An
aircraft in flight passing an observer at an elevation angle that is greater than an agreed threshold
and at an altitude below 7,000 ft". The headline threshold is 48.5 degrees and 60 degrees is computed
alongside; CAP 1498 says every result must state both thresholds, so both are in every file. Seen from
the ground, the aircraft is above the threshold while it is within its cone: radius = height / tan(angle),
0.885 x the height at 48.5 degrees and 0.577 x at 60.

HOW (the design a prototype on two days settled, 2026-10-19; sky-score-drafts/overflight_proto.py)
- HEIGHT: GPS height minus the geoid where the aircraft reports it (63-65% of points), else barometric
  plus that DAY's measured median (GPS above sea level minus barometric), per airport, because pressure
  altitude is not height (it read ~350 ft low near London City on a high-pressure day). Readsb's GPS
  height is above the WGS84 ellipsoid; the geoid sits 45-52 m above it across the UK airports (GEOID_M).
- STEPS: each segment between two airborne track points under SEGMENT_GAP_S apart is walked in STEP_M
  steps (25 m steps gave the prototype identical counts), height interpolated along it.
- ONE PASS, ONE OVERFLIGHT: an aircraft's low flying is split into PASSES wherever it stops contributing
  (above the ceiling, on the ground or unheard) for more than PASS_GAP_S, the prototype's five minutes.
  A cell inside the cone at any step of a pass counts that pass ONCE, however many steps cover it.
- CELLS: a cell counts when its CENTRE is inside the cone, so a postcode up to 71 m from its cell's
  centre reads the cell's count, not its own (validation reads both).
- AIRPORTS: each step is credited to the airport whose movement (adsb_movements.movements(): a landing
  up to ATTRIBUTE_BEFORE_LANDING_S before it, a take-off up to ATTRIBUTE_AFTER_TAKEOFF_S after it) is
  nearest in time, else to OTHER (transits, helicopters, and airports we do not track: Southend,
  Farnborough, Biggin Hill, Northolt). Only airports passing coverage_verdict() for the same period may
  ever be published, so a cell's count is kept per airport as well as in total.

WHAT A DAY FILE HOLDS, AND WHAT IT DOES NOT DECIDE
- data/adsb/overflights/<day>.npz (gitignored): per angle, the cells with a count as row runs
  [j, i_first, i_last, n] (cell (i, j) is easting i*100 to i*100+100, northing j*100 to j*100+100), the
  same per airport [a, j, i_first, i_last, n], and a JSON `meta`: the day's feed profile, each airport's
  movements by runway by hour, the height offsets and the geoid used, and the counts behind them.
- It is NOT judged for feed outages: that needs the days around it (adsb_movements.feed_gaps()), so the
  averaging step judges it from the stored profiles and LEAVES OUT outage days, listing them.
- It is NOT classed westerly or easterly: only the averaging step needs the direction (Kew TW9 3PZ read
  296 on westerly 14 Oct and 0 on easterly 15 Aug), and it asks classify_day(), Bill's call.

LIMITS, stated so a figure is read correctly
- GROUND ELEVATION is ignored: the height used is above sea level, not above the observer, so on high
  ground the cone is drawn too wide and the count errs HIGH (London's 5-50 m changes the 48.5 degree
  radius by under 45 m; Leeds Bradford's runway is ~200 m up, where it matters).
- An aircraft that stays low and returns over the same cell within one pass (circuits, orbits) counts
  once for that pass; the prototype counted each return more than five minutes apart.
- UK only: the grid is the British National Grid. The US needs its own grid (and US extracts are read
  only for the feed profile).
- ODbL: counts derived from adsb.lol are a Derivative Database; nothing leaves the machine until Bill
  publishes under ODbL with the credit (adsb_extract.py's LICENCE note).

Usage (the system Python: adsb_movements needs tzdata, which the isolated 3.13 lacks):
    python scripts/adsb_overflights.py data/adsb/extract/2026-10-14.jsonl.gz [--observe 519153,176729]
    python scripts/adsb_overflights.py --at 519153,176729 data/adsb/overflights/2026-10-*.npz
    python scripts/adsb_overflights.py --average data/adsb/overflights/2026-*.npz --out <file.npz>
"""

import argparse
import datetime as dt
import gzip
import importlib.util
import json
import math
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pyproj

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / 'data' / 'adsb' / 'overflights'


def _load(name):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


mv = _load('adsb_movements')

CEILING_FT = 7000
ANGLES = (48.5, 60.0)  # the headline first
FT_M = 0.3048
CELL_M = 100
STEP_M = 100
SEGMENT_GAP_S = 60  # the prototype's: a segment across a longer silence is not one we can trust
PASS_GAP_S = 300  # the prototype's: hits more than five minutes apart are separate overflights
# A landing's time is its FIRST low point (adsb_movements), ~40 s before touchdown, and a take-off's its
# LAST, so each window reaches a little past its movement; an arrival is under 7,000 ft for up to
# ~25 minutes of vectoring, a departure for a few minutes.
ATTRIBUTE_BEFORE_LANDING_S = 1800
ATTRIBUTE_AFTER_LANDING_S = 120
ATTRIBUTE_BEFORE_TAKEOFF_S = 120
ATTRIBUTE_AFTER_TAKEOFF_S = 900
MIN_OFFSET_POINTS = 200  # points with both heights before an airport's own day offset is trusted
OFFSET_BAND_FT = 1000  # offset_fit() takes one median per band of barometric height...
MIN_BAND_POINTS = 50  # ...from a band holding at least this many points


class DayError(Exception):
    """One day cannot be counted (too few heights to measure its offset; a cone off the grid). The batch
    goes on to the next day and lists it: a SystemExit here stopped a year's run at the first bad day."""
OTHER = 'other'
# The geoid's height above the WGS84 ellipsoid at each UK airport (the mean of its runway thresholds), in
# metres: EGM96, read 2026-10-20 through PROJ (EPSG:4979 -> EPSG:4326+5773, the us_nga_egm96_15 grid from
# PROJ's CDN). It does not change; a new airport needs its row (the test holds the set to the procedure file).
GEOID_M = {
    'BHX': 49.59, 'BRS': 50.25, 'CWL': 51.76, 'EMA': 49.31, 'LBA': 50.10, 'LCY': 45.77, 'LGW': 45.59,
    'LHR': 46.31, 'LPL': 52.34, 'LTN': 46.67, 'MAN': 51.44, 'MME': 49.52, 'NCL': 50.03, 'NWI': 44.93,
    'STN': 45.95,
}
# Cell keys pack (group, row, column) into one int64: BNG northings stay under 1,300 km and eastings
# under 700 km, so rows fit in 2**14 and columns in 2**13 with room for the "one past the end" column.
NROWS, NCOLS = 1 << 14, 1 << 13
STEPS_PER_CHUNK = 200_000  # cone expansion is done this many steps at a time, at pass boundaries

_TO_BNG = pyproj.Transformer.from_crs('EPSG:4326', 'EPSG:27700', always_xy=True)


def cone_radius_m(height_m, angle):
    """How far from the point below it an aircraft at `height_m` is still above `angle` degrees."""
    return np.asarray(height_m, dtype=float) / math.tan(math.radians(angle))


def uk_airports():
    """{code: airport} for the UK airports in the procedure files (adsb_movements.load_airports())."""
    return {code: ap for code, ap in mv.load_airports().items() if ap['region'] == 'uk'}


# ---------------------------------------------------------------- heights


def flatten(traces):
    """Every point of these traces as arrays: trace index, time, lat, lon, baro ft, GPS ft, on ground."""
    n = sum(len(r['pts']) for r in traces)
    tr = np.empty(n, np.int32)
    t, lat, lon = np.empty(n), np.empty(n), np.empty(n)
    baro, geom = np.full(n, np.nan), np.full(n, np.nan)
    ground = np.zeros(n, bool)
    k = 0
    for idx, rec in enumerate(traces):
        for p in rec['pts']:
            tr[k], t[k], lat[k], lon[k] = idx, p[0], p[1], p[2]
            if p[3] == 'ground':
                ground[k] = True
            elif isinstance(p[3], (int, float)):
                baro[k] = p[3]
            if isinstance(p[4], (int, float)):
                geom[k] = p[4]
            k += 1
    return {'trace': tr, 't': t, 'lat': lat, 'lon': lon, 'baro': baro, 'geom': geom, 'ground': ground}


def nearest_airport(x, y, codes, centres):
    """Index into `codes` of the nearest airport centre (BNG metres) to each point."""
    best = np.zeros(len(x), np.int16)
    best_d = np.full(len(x), np.inf)
    for k, code in enumerate(codes):
        cx, cy = centres[code]
        d = (x - cx) ** 2 + (y - cy) ** 2
        closer = d < best_d
        best[closer], best_d[closer] = k, d[closer]
    return best


def msl_heights(pts, near, codes):
    """Each point's height above sea level in feet (NaN on the ground or with no height), and how.

    GPS height minus the geoid where reported; else barometric plus the day's median offset between
    the two for the nearest airport, measured on the points that carry both (or the whole UK's when an
    airport has under MIN_OFFSET_POINTS of them that day). QNH differs across the country on a day,
    so the offset is measured per airport, not once."""
    geoid_ft = np.array([GEOID_M[c] for c in codes]) / FT_M
    gps_msl = pts['geom'] - geoid_ft[near]
    both = np.isfinite(gps_msl) & np.isfinite(pts['baro']) & ~pts['ground']
    diff = gps_msl - pts['baro']
    if both.sum() < MIN_OFFSET_POINTS:
        raise DayError(f'only {both.sum()} points carry both heights: the day offset cannot be measured')
    uk = offset_fit(diff[both], pts['baro'][both])
    fits, how = np.empty((len(codes), 2)), {}
    for k, code in enumerate(codes):
        mine = both & (near == k)
        if mine.sum() >= MIN_OFFSET_POINTS:
            fits[k] = offset_fit(diff[mine], pts['baro'][mine])
            how[code] = {'offset_ft': round(fits[k][0], 1), 'per_1000_ft': round(1000 * fits[k][1], 1),
                         'points': int(mine.sum())}
        else:
            fits[k] = uk
            how[code] = {'offset_ft': round(uk[0], 1), 'per_1000_ft': round(1000 * uk[1], 1),
                         'points': int(mine.sum()), 'from': 'the UK fit'}
    baro_msl = pts['baro'] + fits[near, 0] + fits[near, 1] * pts['baro']
    msl = np.where(np.isfinite(gps_msl), gps_msl, baro_msl)
    msl[pts['ground']] = np.nan
    return msl, {'uk_offset_ft': round(uk[0], 1), 'uk_per_1000_ft': round(1000 * uk[1], 1), 'airports': how,
                 'gps_share': round(float(np.isfinite(gps_msl).mean()), 3) if len(msl) else None}


def offset_fit(diff, baro):
    """(a, b) with GPS-MSL minus barometric height ~ a + b x barometric height, fitted through the medians of
    OFFSET_BAND_FT bands (weighted by the square root of their points), so outliers do not steer it.

    Why a line and not one median: barometric height is pressure height, and how far it sits from true
    height grows with height when the air is not at ISA temperature. Measured 2026-10-20 (code review): on
    15 Aug near Heathrow the gap was 123 ft under 1,000 ft and 348 ft at 7,000-8,000 ft, where one all-heights
    median (173 ft) put a barometric-only aircraft ~50 ft high near the ground and ~175 ft low by the 7,000 ft
    ceiling. With under two usable bands it falls back to that one median (b = 0)."""
    bands = np.floor(baro / OFFSET_BAND_FT)
    xs, ys, ws = [], [], []
    for band in np.unique(bands):
        m = bands == band
        if m.sum() >= MIN_BAND_POINTS:
            xs.append(float(np.median(baro[m])))
            ys.append(float(np.median(diff[m])))
            ws.append(float(np.sqrt(m.sum())))
    if len(xs) < 2:
        return float(np.median(diff)), 0.0
    b, a = np.polyfit(xs, ys, 1, w=ws)
    return float(a), float(b)


# ---------------------------------------------------------------- steps and passes


def walk(pts, x, y, msl):
    """Steps STEP_M apart along every usable segment, in trace and time order: x, y, height ft, time, trace.

    A segment is usable when both ends are airborne with a height and they are at most SEGMENT_GAP_S
    apart. Both ends are steps (the prototype's), so a single segment shorter than STEP_M is still seen."""
    tr, t = pts['trace'], pts['t']
    dt_s = t[1:] - t[:-1]
    ok = (tr[1:] == tr[:-1]) & np.isfinite(msl[1:]) & np.isfinite(msl[:-1]) & (dt_s >= 0) & (dt_s <= SEGMENT_GAP_S)
    a = np.flatnonzero(ok)
    dx, dy = x[a + 1] - x[a], y[a + 1] - y[a]
    # Rounded UP: rounded down, a 199 m segment had only its two ends, 199 m apart, and a cell centre
    # between them could sit outside both cones under a low aircraft (code review, 2026-10-20).
    n = np.maximum(1, np.ceil(np.hypot(dx, dy) / STEP_M).astype(np.int64))
    seg = np.repeat(np.arange(len(a)), n + 1)
    starts = np.repeat(np.cumsum(n + 1) - (n + 1), n + 1)
    f = (np.arange(len(seg)) - starts) / n[seg]
    s = a[seg]
    return {
        'x': x[s] + f * dx[seg], 'y': y[s] + f * dy[seg],
        'h_ft': msl[s] + f * (msl[s + 1] - msl[s]), 't': t[s] + f * dt_s[a][seg], 'trace': tr[s],
    }


def passes(steps):
    """Keep the steps under the ceiling and number their passes: a new pass where the trace changes or
    the aircraft has not contributed for over PASS_GAP_S."""
    keep = (steps['h_ft'] < CEILING_FT) & (steps['h_ft'] > 0)
    out = {k: v[keep] for k, v in steps.items()}
    tr, t = out['trace'], out['t']
    new = np.ones(len(t), bool)
    new[1:] = (tr[1:] != tr[:-1]) | (t[1:] - t[:-1] > PASS_GAP_S)
    out['pass'] = np.cumsum(new) - 1
    return out


def attribute(steps, moves_by_trace, codes):
    """The airport each step's flying belongs to: the movement nearest in time whose window holds it
    (see ATTRIBUTE_*), as an index into `codes`, or len(codes) for OTHER."""
    out = np.full(len(steps['t']), len(codes), np.int16)
    index = {c: k for k, c in enumerate(codes)}
    tr = steps['trace']
    for trace, moves in moves_by_trace.items():
        lo, hi = np.searchsorted(tr, trace, 'left'), np.searchsorted(tr, trace, 'right')
        if lo == hi:
            continue
        ts = steps['t'][lo:hi]
        best = np.full(hi - lo, np.inf)
        who = out[lo:hi]
        for t_move, code, kind, _ in moves:
            d = ts - t_move
            if kind == 'landing':
                ok = (d >= -ATTRIBUTE_BEFORE_LANDING_S) & (d <= ATTRIBUTE_AFTER_LANDING_S)
            else:
                ok = (d >= -ATTRIBUTE_BEFORE_TAKEOFF_S) & (d <= ATTRIBUTE_AFTER_TAKEOFF_S)
            closer = ok & (np.abs(d) < best)
            best[closer], who[closer] = np.abs(d[closer]), index[code]
    return out


# ---------------------------------------------------------------- cones on the grid


def cone_rows(x, y, r):
    """For each step, the grid rows whose cell centres its cone holds, and the columns in each row:
    (step index, row j, first column, last column). A centre is inside when its distance is UNDER r:
    CAP 1498's angle is "greater than" the threshold."""
    j_lo = np.floor((y - r - CELL_M / 2) / CELL_M).astype(np.int64) + 1
    j_hi = np.ceil((y + r - CELL_M / 2) / CELL_M).astype(np.int64) - 1
    count = np.maximum(0, j_hi - j_lo + 1)
    step = np.repeat(np.arange(len(x)), count)
    j = j_lo[step] + (np.arange(len(step)) - np.repeat(np.cumsum(count) - count, count))
    dy = j * CELL_M + CELL_M / 2 - y[step]
    w = np.sqrt(np.maximum(0.0, r[step] ** 2 - dy ** 2))
    i_lo = np.floor((x[step] - w - CELL_M / 2) / CELL_M).astype(np.int64) + 1
    i_hi = np.ceil((x[step] + w - CELL_M / 2) / CELL_M).astype(np.int64) - 1
    ok = i_hi >= i_lo
    return step[ok], j[ok], i_lo[ok], i_hi[ok]


def union(group, j, i_lo, i_hi):
    """The cells each group covers, as merged row intervals (group, j, first, last): a group's steps that
    overlap on a cell count it once."""
    if not len(j):
        e = np.empty(0, np.int64)
        return e, e, e, e
    if j.min() < 0 or j.max() >= NROWS or i_lo.min() < 0 or i_hi.max() >= NCOLS - 2:
        raise DayError('a cone reaches off the British National Grid: is a US trace among the UK ones?')
    row = group.astype(np.int64) * NROWS + j
    lo, hi = row * NCOLS + i_lo, row * NCOLS + i_hi
    order = np.argsort(lo, kind='stable')
    lo, hi = lo[order], hi[order]
    reach = np.maximum.accumulate(hi)
    start = np.ones(len(lo), bool)
    start[1:] = lo[1:] > reach[:-1] + 1  # neither overlapping nor touching what came before in the row
    at = np.flatnonzero(start)
    first, last = lo[at], np.maximum.reduceat(hi, at)
    row = first // NCOLS
    return row // NROWS, row % NROWS, first % NCOLS, last % NCOLS


def sweep(group, j, i_lo, i_hi, weight):
    """Sum weighted row intervals into runs of equal value: (group, j, first, last, value), value > 0."""
    if not len(j):
        return np.empty((0, 5))
    row = group.astype(np.int64) * NROWS + j
    keys = np.concatenate([row * NCOLS + i_lo, row * NCOLS + i_hi + 1])
    w = np.concatenate([weight, -np.asarray(weight)])
    uniq, inv = np.unique(keys, return_inverse=True)
    level = np.cumsum(np.bincount(inv, weights=w))
    # Each row's +w and -w cancel, so the level is zero between rows and runs never cross one.
    keep = level[:-1] > 1e-9
    first, end = uniq[:-1][keep], uniq[1:][keep] - 1
    row = first // NCOLS
    return np.column_stack([row // NROWS, row % NROWS, first % NCOLS, end % NCOLS, level[:-1][keep]])


def count_cells(steps, airport, ncodes):
    """{angle: (total runs [j, first, last, n], per-airport runs [a, j, first, last, n])} for steps
    already numbered into passes (passes()) and credited to airports (attribute())."""
    out = {}
    cuts = [0]  # chunks end on a pass boundary, never inside one: a pass split in two would count twice
    for b in np.flatnonzero(np.diff(steps['pass'])) + 1:
        if b - cuts[-1] >= STEPS_PER_CHUNK:
            cuts.append(int(b))
    cuts.append(len(steps['pass']))
    for angle in ANGLES:
        r_all = cone_radius_m(steps['h_ft'] * FT_M, angle)
        tot, per = [[], [], [], []], [[], [], [], []]
        for a, b in zip(cuts[:-1], cuts[1:], strict=True):
            s, j, i_lo, i_hi = cone_rows(steps['x'][a:b], steps['y'][a:b], r_all[a:b])
            p = steps['pass'][a:b][s]
            for acc, grp in ((tot, p), (per, p * (ncodes + 1) + airport[a:b][s])):
                for lst, arr in zip(acc, union(grp, j, i_lo, i_hi), strict=True):
                    lst.append(arr)
        tot = [np.concatenate(v) for v in tot]
        per = [np.concatenate(v) for v in per]
        totals = sweep(np.zeros_like(tot[1]), tot[1], tot[2], tot[3], np.ones(len(tot[1])))[:, 1:]
        by_airport = sweep(per[0] % (ncodes + 1), per[1], per[2], per[3], np.ones(len(per[1])))
        out[angle] = (totals.astype(np.int32), by_airport.astype(np.int32))
    return out


def lookup(runs, easting, northing, group=None):
    """The value in the cell holding (easting, northing) from runs [j, first, last, value] (with a leading
    group column when `group` is given): a day's count, or an average's mean; 0 when no run holds it."""
    i, j = int(easting // CELL_M), int(northing // CELL_M)
    if group is not None:
        runs = runs[runs[:, 0] == group][:, 1:]
    hit = runs[(runs[:, 0] == j) & (runs[:, 1] <= i) & (runs[:, 2] >= i)]
    return hit[0, 3].item() if len(hit) else 0


def observe(steps, easting, northing, angle):
    """Passes whose cone holds the exact point (not its cell's centre): the validation reading."""
    r = cone_radius_m(steps['h_ft'] * FT_M, angle)
    inside = (steps['x'] - easting) ** 2 + (steps['y'] - northing) ** 2 < r ** 2
    return len(np.unique(steps['pass'][inside]))


# ---------------------------------------------------------------- one day


def day_movements(traces, airports):
    """({trace index: [(t, code, kind, runway)]}, {code: field and how}, {(trace index, t, code) of each
    movement that is half of a circuit, by adsb_movements.circuit_pairs()})."""
    boxes = mv.trace_boxes(traces)
    index = {id(r): k for k, r in enumerate(traces)}
    by_trace, summary, circuits = defaultdict(list), {}, set()
    for code, ap in airports.items():
        near = mv.near_traces(traces, boxes, ap)
        field, how = mv.field_level(near, ap)
        if field is None:
            summary[code] = {'field': None, 'how': how}
            continue
        for rec in near:
            moves, _ = mv.movements(rec, ap, field)
            for kind, runway, t in moves:
                by_trace[index[id(rec)]].append((t, code, kind, runway or '?'))
            for pair in mv.circuit_pairs(moves):
                circuits.update((index[id(rec)], moves[i][2], code) for i in pair)
        summary[code] = {'field': field, 'how': how}
    for moves in by_trace.values():
        moves.sort()
    return by_trace, summary, circuits


def hourly(by_trace, day, codes, circuits=frozenset()):
    """{code: {'landing'|'take-off': {runway: [movements in each UTC hour]}, 'circuits': the same for the
    circuit movements among them}}: classify_day()'s input. Circuits are told apart because training
    touch-and-gos on one runway end can outnumber a quiet day's traffic (East Midlands, 7 Aug: one 737
    flew 32) and would tilt a direction rule; whether to leave them out is classify_day()'s choice."""
    t0 = dt.datetime(day.year, day.month, day.day, tzinfo=dt.UTC).timestamp()
    out = {c: {'landing': {}, 'take-off': {}, 'circuits': {'landing': {}, 'take-off': {}}} for c in codes}
    for trace, moves in by_trace.items():
        for t, code, kind, runway in moves:
            hour = min(23, max(0, int((t - t0) // 3600)))
            out[code][kind].setdefault(runway, [0] * 24)[hour] += 1
            if (trace, t, code) in circuits:
                out[code]['circuits'][kind].setdefault(runway, [0] * 24)[hour] += 1
    return out


def count_traces(traces, airports, by_trace, observers=()):
    """The cell counts and their meta for one day's UK traces (each trace's points all in the UK)."""
    return count_points(flatten(traces), airports, by_trace, observers)


def count_points(pts, airports, by_trace, observers=()):
    """count_traces() on points already flatten()ed, so a caller can free the traces first."""
    codes = sorted(airports)
    centres = {c: _TO_BNG.transform(airports[c]['centre'][1], airports[c]['centre'][0]) for c in codes}
    x, y = _TO_BNG.transform(pts['lon'], pts['lat'])
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    near = nearest_airport(x, y, codes, centres)
    msl, heights = msl_heights(pts, near, codes)
    steps = passes(walk(pts, x, y, msl))
    airport = attribute(steps, by_trace, codes)
    cells = count_cells(steps, airport, len(codes))
    seen = {f'{e},{n}': {str(a): observe(steps, e, n, a) for a in ANGLES} for e, n in observers}
    meta = {
        'codes': codes + [OTHER], 'heights': heights, 'geoid_m': {c: GEOID_M[c] for c in codes},
        'points': int(len(msl)), 'steps': int(len(steps['t'])), 'passes': int(steps['pass'][-1] + 1) if len(
            steps['pass']) else 0, 'observed': seen,
        'steps_by_airport': {(codes + [OTHER])[k]: int(n) for k, n in enumerate(np.bincount(
            airport, minlength=len(codes) + 1))},
    }
    return cells, meta


def count_day(extract_path, observers=()):
    """(cells, meta) for one day's extract: count_traces() over its UK traces, plus the day's feed profile
    (UK and US, for the averaging step's outage test) and each airport's movements by runway and hour."""
    day = mv.day_of(Path(extract_path))
    # Read in batches, keeping only UK points: holding the whole day (the US too) as Python lists peaked
    # at 3.5 GB on 2026-08-15. The feed profile counts each trace on its own, so batches simply add up.
    feed, uk, batch = {r: [0] * (86400 // mv.FEED_BIN_S) for r in mv.REGIONS}, [], []

    def take(batch):
        for region, bins in mv.feed_profile(batch, day).items():
            feed[region] = [a + b for a, b in zip(feed[region], bins, strict=True)]
        for rec in batch:
            pts = [p for p in rec['pts'] if mv.region_of(p[2]) == 'uk']
            if len(pts) > 1:
                uk.append({**rec, 'pts': pts})

    with gzip.open(extract_path, 'rt', encoding='utf-8') as fh:
        for line in fh:
            batch.append(json.loads(line))
            if len(batch) == 500:
                take(batch)
                batch = []
    take(batch)
    airports = uk_airports()
    by_trace, fields, circuits = day_movements(uk, airports)
    n_uk = len(uk)
    pts = flatten(uk)
    uk.clear()  # the points are in arrays now; the lists were most of the memory
    cells, meta = count_points(pts, airports, by_trace, observers)
    meta.update({
        'day': day.isoformat(), 'extract': Path(extract_path).name, 'uk_traces': n_uk,
        'feed': feed, 'movements': hourly(by_trace, day, sorted(airports), circuits), 'fields': fields,
        'definition': {'source': 'CAA CAP 1498 (Feb 2017)', 'angles_deg': list(ANGLES), 'ceiling_ft': CEILING_FT,
                       'cell_m': CELL_M, 'step_m': STEP_M, 'pass_gap_s': PASS_GAP_S,
                       'segment_gap_s': SEGMENT_GAP_S, 'counts_at': 'cell centre', 'ground': 'sea level'},
        'generator': 'scripts/adsb_overflights.py', 'licence': 'derived from adsb.lol (ODbL 1.0); unpublished',
    })
    return cells, meta


def tag(angle):
    return f'{angle:g}'.replace('.', '')


def pack(runs, prefix):
    """Runs [(a,) j, first, last, n], sorted, as small delta-coded columns. A day held as the runs
    themselves was 26.7 MB (2026-10-14: 1.5 million runs at 48.5 degrees, 3.1 cells each on average);
    as these columns it is 8.6 MB, so a year is ~3.1 GB beside ~30 GB of extracts."""
    lead = 1 if runs.shape[1] == 5 else 0
    j, first = runs[:, lead].astype(np.int64), runs[:, lead + 1].astype(np.int64)
    new_row = np.ones(len(j), bool)
    new_row[1:] = j[1:] != j[:-1]
    if lead:
        new_row[1:] |= runs[1:, 0] != runs[:-1, 0]
    out = {
        f'{prefix}_dj': np.diff(j, prepend=0).astype(np.int16),
        f'{prefix}_di': np.where(new_row, first, np.diff(first, prepend=0)).astype(np.int16),
        f'{prefix}_len': (runs[:, lead + 2] - runs[:, lead + 1]).astype(np.uint16),
        f'{prefix}_n': runs[:, lead + 3].astype(np.uint16),
    }
    if lead:
        out[f'{prefix}_a'] = runs[:, 0].astype(np.uint8)
    if runs[:, lead + 3].max(initial=0) > np.iinfo(np.uint16).max:
        raise SystemExit('a cell count over 65,535 in one day: not a real count')
    return out


def unpack(z, prefix):
    """pack()'s columns back into runs."""
    j = np.cumsum(z[f'{prefix}_dj'].astype(np.int64))
    di = z[f'{prefix}_di'].astype(np.int64)
    new_row = np.ones(len(j), bool)
    new_row[1:] = j[1:] != j[:-1]
    lead = f'{prefix}_a' in z
    if lead:
        a = z[f'{prefix}_a'].astype(np.int64)
        new_row[1:] |= a[1:] != a[:-1]
    # Within a row each first column is the previous one plus di; a new row starts from di itself.
    seg = np.cumsum(new_row) - 1
    csum = np.cumsum(di)
    base = (csum - di)[new_row][seg]
    first = csum - base
    last = first + z[f'{prefix}_len'].astype(np.int64)
    cols = [j, first, last, z[f'{prefix}_n'].astype(np.int64)]
    return np.column_stack(([a] if lead else []) + cols).astype(np.int32)


def write_day(cells, meta, out):
    """One .npz per day, written whole or not at all (a .partial renamed), as the extracts are."""
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + '.partial')
    arrays = {'meta': np.array(json.dumps(meta, separators=(',', ':')))}
    for angle, (totals, by_airport) in cells.items():
        arrays.update(pack(totals, f'cells_{tag(angle)}'))
        arrays.update(pack(by_airport, f'airport_{tag(angle)}'))
    with open(tmp, 'wb') as fh:
        np.savez_compressed(fh, **arrays)
    os.replace(tmp, out)


def read_day(path):
    """(meta, {angle: (totals, by airport)}) from a day file; no pickles are loaded."""
    with np.load(path, allow_pickle=False) as z:
        cols = {k: z[k] for k in z.files}
    meta = json.loads(str(cols['meta']))
    cells = {a: (unpack(cols, f'cells_{tag(a)}'), unpack(cols, f'airport_{tag(a)}')) for a in ANGLES}
    return meta, cells


# ---------------------------------------------------------------- averaging


def classify_day(code, movements, runways):
    """The direction an airport flew on one day, as a label the averaging step groups days by, or None
    to leave the day out of every direction's average. BILL'S CALL (methodology), left as a stub.

    `movements` is {'landing'|'take-off': {runway designator: [movements in each UTC hour, 0-23]}} for
    that airport and day (runway '?' when adsb_movements could not tell), plus 'circuits': the same shape
    for the training circuits counted among them, which a rule may subtract; `runways` is {designator: true
    bearing in degrees}, from data/flight-procedures.json. Why it matters: Kew TW9 3PZ read 296 overflights
    on westerly 14 Oct and 0 on easterly 15 Aug, so an average over both kinds of day describes neither.

    The options, and what each costs:
    - MAJORITY: the label of whichever direction carried most of the day's movements. Simple and never
      leaves a day out, but a day that switched at 14:00 puts its morning into the wrong average.
    - THRESHOLD: a direction only when it carried, say, 80% or more of the movements; otherwise 'mixed'
      (its own average) or None (left out). Cleaner averages, fewer days in each; the threshold is a
      choice to state with the figures.
    - BY HOUR: classify each hour instead of the day. The most faithful, but the day files count a cell
      once per pass over the WHOLE day, so this needs per-hour (or per-pass direction) counts stored,
      a bigger change to count_cells().
    - WHICH MOVEMENTS: landings and take-offs both follow the wind, but a quiet hour, the night period
      or a runway closed for works can tilt a count; a minimum number of movements (else None) guards a
      day the airport barely flew.
    - LABELS: 'westerly'/'easterly' reads well for runways near 090/270 (Heathrow, London City), but
      Birmingham's 15/33 and Stansted's 04/22 are not east-west: labelling by the bearing in use (the
      runway end, e.g. '27' vs '09') works everywhere.
    Heathrow publishes its yearly westerly/easterly split (about 70/30), a check on whatever rule is used.
    """
    raise NotImplementedError('TODO(Bill): choose how a day is classed westerly / easterly / mixed '
                              '(classify_day in scripts/adsb_overflights.py lists the options)')


def average(day_files, classify=None):
    """Average daily counts per cell, per airport and direction class, over the days whose feed was whole.

    Outage days (adsb_movements.feed_gaps() over the stored UK profiles) are LEFT OUT and listed, never
    patched; days the feed test cannot judge (under FEED_MIN_REFERENCE_DAYS nearby) are kept and listed,
    as adsb_movements.report() keeps them. Every kept airport-day goes through classify_day(), the
    explicit dependency: an airport's traffic is averaged over the days of its own class only. OTHER
    traffic has no runway to class it by and is averaged over every kept day. Publishing any airport's
    figures still needs coverage_verdict() for the same period (adsb_movements.report())."""
    classify = classify or classify_day
    days = {}
    for path in day_files:
        meta, cells = read_day(path)
        days[dt.date.fromisoformat(meta['day'])] = (meta, cells)
    if len(days) != len(day_files):
        raise SystemExit('the same day appears twice among the day files')
    gaps = mv.feed_gaps({d: m['feed']['uk'] for d, (m, _) in days.items()}, 'uk')
    kept = sorted(d for d in days if not gaps[d])
    bearings = {code: {des: brg for des, (_, brg) in ap['runways'].items()} for code, ap in uk_airports().items()}

    labels, unknown = {}, set()
    for d in kept:
        meta = days[d][0]
        for code in meta['codes']:
            if code == OTHER:
                continue
            if code not in bearings:  # in a day file, gone from the procedure file since: left out, listed
                labels[(d, code)] = None
                unknown.add(code)
                continue
            labels[(d, code)] = classify(code, meta['movements'][code], bearings[code])
    groups = sorted({(code, lab) for (_, code), lab in labels.items() if lab is not None}) + [(OTHER, None)]
    gindex = {g: k for k, g in enumerate(groups)}
    ndays = defaultdict(int)
    for (_, code), lab in labels.items():
        if lab is not None:
            ndays[(code, lab)] += 1
    ndays[(OTHER, None)] = len(kept)

    runs = {}
    for angle in ANGLES:
        acc = [[], [], [], [], []]
        for d in kept:
            meta, cells = days[d]
            per = cells[angle][1]
            for k, code in enumerate(meta['codes']):
                g = (OTHER, None) if code == OTHER else (code, labels[(d, code)])
                if g[1] is None and code != OTHER:
                    continue
                mine = per[per[:, 0] == k]
                acc[0].append(np.full(len(mine), gindex[g]))
                for lst, col in zip(acc[1:4], (1, 2, 3), strict=True):
                    lst.append(mine[:, col].astype(np.int64))
                acc[4].append(mine[:, 4])
        cols = [np.concatenate(v) if v else np.empty(0) for v in acc]
        # Summed as whole counts and divided by each group's days AFTER the sweep: summing fractions
        # (count / days) over a year left float residue between rows, and a residue over the sweep's
        # threshold made a run cross from one row into the next (code review, 2026-10-20).
        summed = sweep(cols[0].astype(np.int64), cols[1].astype(np.int64), cols[2].astype(np.int64),
                       cols[3].astype(np.int64), cols[4].astype(np.int64))
        days_of = np.array([ndays[g] for g in groups], dtype=float)
        summed[:, 4] /= days_of[summed[:, 0].astype(np.int64)] if len(summed) else 1
        runs[angle] = summed
    return {
        'groups': [list(g) for g in groups], 'days_per_group': [ndays[g] for g in groups],
        'runs': runs, 'kept': [d.isoformat() for d in kept],
        'left_out_outage': [d.isoformat() for d in sorted(days) if gaps[d]],
        'not_judged': [d.isoformat() for d in sorted(days) if gaps[d] is None],
        'unclassified': sorted(f'{d} {code}' for (d, code), lab in labels.items() if lab is None),
        'airports_no_longer_drawn': sorted(unknown),
    }


# ---------------------------------------------------------------- command line


def _point(text):
    e, n = (float(v) for v in text.split(','))
    return e, n


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('files', type=Path, nargs='+', help='extracts to count, or day files with --at / --average')
    ap.add_argument('--out-dir', type=Path, default=OUT_DIR)
    ap.add_argument('--force', action='store_true', help='recount a day whose file exists')
    ap.add_argument('--observe', type=_point, action='append', default=[],
                    help='also count passes at this exact BNG point (easting,northing), for validation')
    ap.add_argument('--at', type=_point, help='print the count in the cell holding this BNG point')
    ap.add_argument('--average', action='store_true', help='average day files (needs classify_day)')
    ap.add_argument('--out', type=Path, help='--average: where to write the averages (.npz)')
    a = ap.parse_args()

    if a.at:
        for path in a.files:
            meta, cells = read_day(path)
            row = '  '.join(f'{ang:g} deg: {lookup(cells[ang][0], *a.at):4}' for ang in ANGLES)
            print(f'{meta["day"]}  {row}')
        return 0
    if a.average:
        res = average(a.files)
        print(f'{len(res["kept"])} day(s) kept; outage days left out: {res["left_out_outage"] or "none"}; '
              f'not judged: {len(res["not_judged"])}')
        if a.out:
            arrays = {f'runs_{tag(ang)}': r for ang, r in res['runs'].items()}
            arrays['meta'] = np.array(json.dumps({k: v for k, v in res.items() if k != 'runs'}))
            with open(a.out, 'wb') as fh:
                np.savez_compressed(fh, **arrays)
        return 0
    failed = []
    for path in a.files:
        out = a.out_dir / (mv.day_of(path).isoformat() + '.npz')
        # An existing day is recounted only with --force; --observe on it counts and prints, but keeps the
        # file (it overwrote it, possibly made under another definition, without asking: code review 2026-10-20).
        write = a.force or not out.exists()
        if not write and not a.observe:
            print(f'{out.name}: exists, skipped')
            continue
        t0 = time.time()
        try:
            cells, meta = count_day(path, a.observe)
        except DayError as exc:  # one bad day must not stop a year's batch: listed at the end instead
            failed.append(f'{Path(path).name}: {exc}')
            print(f'{Path(path).name}: NOT COUNTED: {exc}', flush=True)
            continue
        if write:
            write_day(cells, meta, out)
        else:
            out = f'{out} kept (observed only; --force to recount)'
        cells_485 = len(cells[ANGLES[0]][0])
        print(f'{meta["day"]}: {meta["uk_traces"]:,} UK traces, {meta["steps"]:,} steps in {meta["passes"]:,} '
              f'passes, {cells_485:,} runs at {ANGLES[0]:g} deg; GPS height on {meta["heights"]["gps_share"]:.0%} '
              f'of points -> {out} in {time.time() - t0:.0f} s', flush=True)
        for point, seen in meta['observed'].items():
            e, n = _point(point)
            at_cell = {ang: lookup(cells[ang][0], e, n) for ang in ANGLES}
            print(f'  {point}: exact point ' + ', '.join(f'{k} deg {v}' for k, v in seen.items())
                  + '; its cell ' + ', '.join(f'{ang:g} deg {v}' for ang, v in at_cell.items()))
    if failed:
        print(f'{len(failed)} day(s) not counted:\n  ' + '\n  '.join(failed))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
