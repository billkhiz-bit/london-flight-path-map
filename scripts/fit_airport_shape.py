"""Measure a RUNWAY-SHAPED airport term against DEFRA, on the strip and off it.

WHY THIS EXISTS
---------------
calc_postcode_quiet's airport term is a CIRCLE: it ladders the straight-line
distance to the airport whatever the direction. Aircraft noise is a STRIP along
the runway axis, because every arrival and departure flies down that line. The
2026-09-30 breakdown found the cost: 3-15 km from an airport the estimate erred
by 1.30 within 15 deg of the axis and by 3.70 at 30-60 deg, reading 3.7 points
too LOUD beside the runway. That is the audit-C1 disc defect (the borough
floor, fixed 2026-09-01) one tier down, in the geometry estimate.

The candidate shape stretches distance ACROSS the axis. With `along` and `side`
the components of the airport-to-postcode vector along and across the runway,

    distance = sqrt(along^2 + (k * side)^2)

so k = 1 is today's circle and a larger k makes noise fall away faster to the
side. It replaces the distance in every airport term (the 5/4/3/2/1 ladder and
the major/secondary bonuses), still divided by AIRPORT_NOISE_SCALE. The axis is
each airport's runway bearing from data/flight-procedures.json; an airport with
no record there stays a circle and the report names it.

TWO YARDSTICKS, BECAUSE ONE IS BIASED
-------------------------------------
ON THE STRIP: the DEFRA-measured postcodes (data/aircraft-quiet-*.json), the
same set and the same crc32 train/test split as fit_corridor_weight.py. DEFRA
maps only the loud strip, so this set rewards shapes that hug the axis: fitted
against it alone, k ran to 8.

OFF THE STRIP: DEFRA's aircraft rasters hold no below-floor zeros (unlike road),
so a BLANK cell inside a raster's box is ground below that raster's lowest band.
Each floor is MEASURED here, never assumed - on 2026-09-30 it was 40 dB (quiet
exactly 10) or 49 dB (quiet >= 7.8, a BOUND, scored as a hinge). A postcode is
read only when every airport its city scores is covered by a raster whose box
contains it, because a blank in one airport's file says nothing about another
airport's noise. Outside the box nothing is claimed: East Midlands' and
Birmingham's contours run off the edge of their files.

For each k the corridor weight is refitted on the TRAIN half of the strip (the
yardstick that set CORRIDOR_WEIGHT) and every lens is reported on the TEST half.
Two guards make the baseline the engine's own: at k = 1 and the shipped weight,
every strip postcode and a sample of the rest must reproduce
calc_postcode_quiet exactly, and at k = 1 the refit must return the shipped
CORRIDOR_WEIGHT.

DEFRA Round 4 maps 2021, a COVID year, so any fit against it inherits that
understatement (see the PROVISIONAL note on CORRIDOR_WEIGHT in the Lambda).

WHAT IT CHANGED ABOUT THE 2026-09-30 RECORD (written 2026-10-01)
---------------------------------------------------------------
The first measurement was scratch work and was lost. This script reproduces its
figures, and they turn out to be k = 4 with the weight HELD at w = 0.45, over
ALL postcodes rather than the test half: 1.118 on the strip (bias -0.24), 0.715
below the floor, hinge 0.173, 18.2% read over a point quieter than DEFRA -
against the recorded 1.12, 0.72, 0.18 and 18.5%. Refitting w per k, as below
and as CORRIDOR_WEIGHT itself was set, gives k = 4 a weight of 0.35, and there
it is slightly OPTIMISTIC on the axis (+0.17), while k = 6 refits to 0.50 and
sits near zero (+0.02). The recorded reason for preferring 4 to 6 ("6 turns
optimistic along the axis") holds only at the held weight. Which k ships is a
decision; recommend() is where its rule lives.

Advisory, and it changes nothing: data/nspl.csv and the GeoTIFFs are gitignored,
and without them this reports INCONCLUSIVE and exits 0. About 20 seconds.

    python scripts/fit_airport_shape.py              # fit every k and report
    python scripts/fit_airport_shape.py --k 6        # detail tables for another shape
    python scripts/fit_airport_shape.py --w 0.45     # hold the weight instead of refitting
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fit_corridor_weight as fcw  # noqa: E402  same app loader, weight grid, data and split

ROOT = fcw.ROOT
PROCEDURES = ROOT / 'data' / 'flight-procedures.json'
# Each raster, and the airports whose noise a blank cell in it speaks for.
# London's region export maps every airport over London; the rest are one
# airport each. The same eight files the aircraft-quiet datasets came from.
RASTERS = {
    'london-region': ('defra_lden_2022.tif', ('LHR', 'LGW', 'LCY', 'STN', 'LTN')),
    'birmingham': ('defra_aircraft_lden_birmingham.tif', ('BHX',)),
    'bristol': ('defra_aircraft_lden_bristol.tif', ('BRS',)),
    'eastmidlands': ('defra_aircraft_lden_eastmidlands.tif', ('EMA',)),
    'leedsbradford': ('defra_aircraft_lden_leedsbradford.tif', ('LBA',)),
    'liverpool': ('defra_aircraft_lden_liverpool.tif', ('LPL',)),
    'manchester': ('defra_aircraft_lden_manchester.tif', ('MAN',)),
    'newcastle': ('defra_aircraft_lden_newcastle.tif', ('NCL',)),
}
K_GRID = [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0]
# Nodata is +3.4e38 in London's region export and -3.4e38 in the per-airport
# files, so absence is tested by MAGNITUDE (build_aircraft_quiet_dataset.py).
SENTINEL_MAGNITUDE = 1e30
MAX_AXIS_SPREAD_DEG = 15.0  # wider and the runways cross; one axis cannot describe them
AXIS_BAND_DEG = 30.0  # "on the axis", for the optimism lens
QUIETER_BY = 1.0  # a strip reading the estimate puts this much QUIETER than DEFRA
GUARD_SAMPLE = 25  # off-strip rows checked against the engine: 1 in this many
RING_KM = (3.0, 15.0)  # where the angle breakdown is measured
ANGLE_BANDS = [(0, 15), (15, 30), (30, 60), (60, 90.01)]
STRIP, BELOW, BOUND = 0, 1, 2


def off_axis(bearing, axis):
    """Signed angle from the axis in [-90, 90). Which END of the runway does not matter."""
    return (bearing - axis + 90) % 180 - 90


def runway_axes():
    """{airport code: runway axis, degrees true in [0, 180)}, from the AIP record."""
    data = json.loads(PROCEDURES.read_text(encoding='utf-8'))
    axes = {}
    for code, ap in data['airports'].items():
        brgs = [r['true_brg'] % 180 for r in ap['runways'].values()]
        # Doubled-angle mean: an axis has no direction, so 179 and 1 must
        # average to 0, not 90.
        s = sum(math.sin(math.radians(2 * b)) for b in brgs)
        c = sum(math.cos(math.radians(2 * b)) for b in brgs)
        axis = math.degrees(math.atan2(s, c)) / 2 % 180
        spread = max(abs(off_axis(b, axis)) for b in brgs)
        if spread > MAX_AXIS_SPREAD_DEG:
            raise SystemExit(f'{code}: runways {brgs} cross ({spread:.0f} deg apart); one axis cannot describe them')
        axes[code] = axis
    return axes


def haversine_np(lat1, lon1, lat2, lon2):
    """app.haversine_km, term for term, over arrays."""
    p = math.pi / 180.0
    a = 0.5 - np.cos((lat2 - lat1) * p) / 2 + np.cos(lat1 * p) * np.cos(lat2 * p) * (1 - np.cos((lon2 - lon1) * p)) / 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def bearing_np(lat1, lon1, lat2, lon2):
    """Initial great-circle bearing from point 1 to point 2, degrees true."""
    p = math.pi / 180.0
    f1, f2, dl = lat1 * p, lat2 * p, (lon2 - lon1) * p
    y = np.sin(dl) * np.cos(f2)
    x = np.cos(f1) * np.sin(f2) - np.sin(f1) * np.cos(f2) * np.cos(dl)
    return np.degrees(np.arctan2(y, x)) % 360


def is_reading(v, nodata):
    sentinel = ~np.isfinite(v) | (np.abs(v) >= SENTINEL_MAGNITUDE)
    if nodata is not None:
        sentinel |= v == nodata
    return ~sentinel


def load_rasters(app):
    """Every raster with its MEASURED floor, or None if any file is absent."""
    import rasterio

    out = {}
    for name, (fname, airports) in RASTERS.items():
        path = ROOT / 'data' / fname
        if not path.exists():
            return None
        with rasterio.open(path) as r:
            if r.crs.to_epsg() != 27700:
                raise SystemExit(f'{name}: expected EPSG:27700, found {r.crs}')
            arr = r.read(1)
            meta = {
                'bounds': r.bounds,
                'res_x': r.transform.a,
                'res_y': -r.transform.e,
                'h': r.height,
                'w': r.width,
                'nodata': r.nodata,
            }
        vals = arr[is_reading(arr, meta['nodata'])]
        odd = int(((vals < app._RASTER_MIN_PLAUSIBLE_DB) | (vals > app._RASTER_MAX_PLAUSIBLE_DB)).sum())
        if odd:
            # The road rasters carry 0.0 for "surveyed, below the lowest band".
            # If an aircraft raster ever does, a blank no longer means quiet.
            raise SystemExit(
                f'{name}: {odd:,} readings outside '
                f'{app._RASTER_MIN_PLAUSIBLE_DB}-{app._RASTER_MAX_PLAUSIBLE_DB} dB; '
                'a blank cell may not mean below the floor any more'
            )
        out[name] = {**meta, 'array': arr, 'airports': set(airports), 'floor': float(vals.min())}
    return out


def sample(r, x, y):
    """(inside the box, holds a reading) for each BNG point."""
    b = r['bounds']
    col = np.floor((x - b.left) / r['res_x']).astype(np.int64)
    row = np.floor((b.top - y) / r['res_y']).astype(np.int64)
    inside = (
        (b.left <= x)
        & (x < b.right)
        & (b.bottom < y)
        & (y <= b.top)
        & (row >= 0)
        & (row < r['h'])
        & (col >= 0)
        & (col < r['w'])
    )
    v = np.full(len(x), np.nan)
    v[inside] = r['array'][row[inside], col[inside]]
    return inside, inside & is_reading(v, r['nodata'])


def read_nspl(app):
    """Live postcodes in every city whose geometry has an airport."""
    rows = []
    with open(fcw.NSPL, newline='', encoding='utf-8') as fh:
        r = csv.DictReader(fh)
        lad_col = next(c for c in r.fieldnames if c.startswith('lad') and c.endswith('cd'))
        for row in r:
            if row['doterm']:
                continue
            hit = app.LAD_TO_BOROUGH.get(row[lad_col])
            if not hit or hit[0] not in app.CITY_GEOMETRY or not app.CITY_GEOMETRY[hit[0]].get('airports'):
                continue
            lat, lon = float(row['lat']), float(row['long'])
            if lat > 90:  # NSPL's "no grid reference" marker
                continue
            rows.append((row['pcds'].replace(' ', ''), hit[0], lat, lon))
    return rows


def truths(app, rows, rasters, measured):
    """Per row: (kind, value), or None where nothing is claimed. Plus a count of
    rows that hold a DEFRA reading the aircraft-quiet datasets do not carry."""
    from pyproj import Transformer

    lat = np.array([r[2] for r in rows])
    lon = np.array([r[3] for r in rows])
    x, y = Transformer.from_crs('EPSG:4326', 'EPSG:27700', always_xy=True).transform(lon, lat)
    hits = {name: sample(r, x, y) for name, r in rasters.items()}
    city = np.array([r[1] for r in rows])
    out = [None] * len(rows)
    unexplained = 0
    for c in sorted(set(city)):
        idx = np.flatnonzero(city == c)
        wanted = {ap['code'] for ap in app.CITY_GEOMETRY[c]['airports']}
        relevant = [n for n, r in rasters.items() if r['airports'] & wanted]
        if not relevant:
            continue
        covered = np.ones(len(idx), bool)
        for code in wanted:
            covered &= np.logical_or.reduce(
                [hits[n][0][idx] for n in relevant if code in rasters[n]['airports']] + [np.zeros(len(idx), bool)]
            )
        reading = np.logical_or.reduce([hits[n][1][idx] for n in relevant])
        floor = np.max([np.where(hits[n][0][idx], rasters[n]['floor'], -np.inf) for n in relevant], axis=0)
        for j, i in enumerate(idx):
            pc = rows[i][0]
            if pc in measured:
                out[i] = (STRIP, measured[pc])
            elif reading[j]:
                unexplained += 1
            elif covered[j]:
                if floor[j] <= app._QUIET_CEILING_DB:
                    out[i] = (BELOW, 10.0)
                else:
                    out[i] = (BOUND, app.lden_db_to_quiet(round(float(floor[j]), 1)))
    return out, unexplained


def city_features(app, c, sub, axes):
    """Everything the airport term needs, for one city's rows, as arrays."""
    geo = app.CITY_GEOMETRY[c]
    lat = np.array([r[2] for r in sub])[:, None]
    lon = np.array([r[3] for r in sub])[:, None]
    aps = geo['airports']
    alat = np.array([ap['lat'] for ap in aps])[None, :]
    alon = np.array([ap['lon'] for ap in aps])[None, :]
    d = haversine_np(lat, lon, alat, alon)
    brg = bearing_np(alat, alon, lat, lon)
    axis = np.array([axes.get(ap['code'], np.nan) for ap in aps])[None, :]
    delta = off_axis(brg, axis)  # NaN where the airport has no runway record
    scale = np.array([app.airport_noise_scale(ap['code']) for ap in aps])
    codes = [ap['code'] for ap in aps]
    major = codes.index(geo['major_airport']) if geo.get('major_airport') in codes else None
    secondary = codes.index(geo['secondary_airport']) if geo.get('secondary_airport') in codes else None

    # Corridor points, as fcw.path_points ranks them, chunked over the waypoints.
    wp = np.array(
        [(plat, plon, app.airport_noise_scale(p.get('airport'))) for p in geo['paths'] for plat, plon in p['coords']]
    )
    best = np.full(len(sub), np.inf)
    for s in range(0, len(sub), 2000):
        dd = haversine_np(lat[s : s + 2000], lon[s : s + 2000], wp[None, :, 0], wp[None, :, 1]) / wp[None, :, 2]
        best[s : s + 2000] = dd.min(axis=1)
    pts = np.select([best < 1, best < 2, best < 4, best < 6], [4, 3, 2, 1], 0).astype(float)

    heli = np.zeros(len(sub))
    for hp in geo.get('heliports', []):
        hd = haversine_np(lat[:, 0], lon[:, 0], hp['lat'], hp['lon'])
        heli = np.maximum(heli, np.where(hd < 3, hp['bands'][0], np.where(hd < 5, hp['bands'][1], 0)))

    # The LOUDEST airport under today's circle, which the angle lenses describe.
    loud = (d / scale).argmin(axis=1)
    pick = np.arange(len(sub))
    return {
        'd': d,
        'delta': delta,
        'scale': scale,
        'major': major,
        'secondary': secondary,
        'pts': pts,
        'heli': heli,
        'ring_km': d[pick, loud],
        'ring_delta': np.abs(delta[pick, loud]),
    }


def airport_term(f, k):
    """The airport points (ladder + bonuses) under shape k. k = 1 is the engine's circle."""
    if k == 1.0:
        eff = f['d'] / f['scale']
    else:
        rad = np.radians(np.nan_to_num(f['delta'], nan=0.0))  # no runway record: stays a circle
        eff = f['d'] * np.sqrt(np.cos(rad) ** 2 + (k * np.sin(rad)) ** 2) / f['scale']
    m = eff.min(axis=1)
    term = np.select([m < 3, m < 6, m < 10, m < 15, m < 20], [5, 4, 3, 2, 1], 0).astype(float)
    if f['major'] is not None:
        term += 2 * (eff[:, f['major']] < 15)
    if f['secondary'] is not None:
        term += 1 * (eff[:, f['secondary']] < 10)
    return term


def quiet(a, pts, heli, w):
    return np.clip(10.0 - (a + w * pts + heli), 0.0, 10.0)


def collect(app):
    measured = {}
    for f in fcw.MEASURED:
        if f.exists():
            measured.update(json.loads(f.read_text(encoding='utf-8'))['quiet'])
    if not measured or not fcw.NSPL.exists():
        return None
    rasters = load_rasters(app)
    if rasters is None:
        return None
    axes = runway_axes()
    rows = read_nspl(app)
    truth, unexplained = truths(app, rows, rasters, measured)
    kept = [(r, t) for r, t in zip(rows, truth, strict=True) if t is not None]
    groups = []
    for c in sorted({r[1] for r, _ in kept}):
        sub = [r for r, _ in kept if r[1] == c]
        tt = [t for r, t in kept if r[1] == c]
        f = city_features(app, c, sub, axes)
        f.update(
            city=c,
            rows=sub,
            kind=np.array([t[0] for t in tt]),
            truth=np.array([t[1] for t in tt], float),
            train=np.array([zlib.crc32(r[0].encode()) % 2 == 0 for r in sub]),
        )
        guard(app, f)
        groups.append(f)
    circles = sorted({ap['code'] for g in groups for ap in app.CITY_GEOMETRY[g['city']]['airports']} - set(axes))
    return {'groups': groups, 'rasters': rasters, 'unexplained': unexplained, 'circles': circles}


def guard(app, f):
    """At k = 1 and the shipped weight the decomposition must BE the engine."""
    q = quiet(airport_term(f, 1.0), f['pts'], f['heli'], app.CORRIDOR_WEIGHT)
    for i, (pc, c, lat, lon) in enumerate(f['rows']):
        if f['kind'][i] != STRIP and zlib.crc32(pc.encode()) % GUARD_SAMPLE:
            continue
        want = app.calc_postcode_quiet(lat, lon, c, raster_lden=None)
        if abs(q[i] - want) > 1e-9:
            raise SystemExit(f'{pc}: decomposition gives {q[i]} where calc_postcode_quiet gives {want}')


def flat(groups, key):
    return np.concatenate([g[key] for g in groups])


def lenses(est, truth, kind, test, delta):
    """Every lens over the TEST half. Error is estimate minus DEFRA: below 0 reads LOUDER."""

    def mean(x):
        return float(x.mean()) if len(x) else float('nan')

    s, b, h = test & (kind == STRIP), test & (kind == BELOW), test & (kind == BOUND)
    err = est - truth
    return {
        'strip_mae': mean(np.abs(err[s])),
        'strip_bias': mean(err[s]),
        'below_mae': mean(np.abs(err[b])),
        'below_bias': mean(err[b]),
        'bound_hinge': mean(np.maximum(0.0, truth[h] - est[h])),
        'axis_bias': mean(err[s & (delta <= AXIS_BAND_DEG)]),
        'quieter_share': mean((err[s] > QUIETER_BY).astype(float)),
    }


def recommend(results, today):
    """Pick the k to ship, or None.

    `results` is one dict per k in K_GRID, in order, each holding `k`, the
    refitted weight `w`, and the TEST-half lenses from lenses(): `strip_mae`,
    `strip_bias`, `below_mae`, `below_bias`, `bound_hinge`, `axis_bias` (strip
    readings within AXIS_BAND_DEG of the runway axis) and `quieter_share` (the
    share of strip readings the estimate puts more than QUIETER_BY points
    QUIETER than DEFRA). `today` holds the same lenses for the engine as shipped.
    Bias is estimate minus DEFRA, so a POSITIVE bias is optimistic: it tells a
    reader a place is quieter than DEFRA measured.

    TODO(Bill): the rule that turns this table into one k. See the request in
    the session that wrote this script.
    """
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        '--k', type=float, default=4.0, help='shape for the detail tables (default 4, recommended 2026-09-30)'
    )
    ap.add_argument('--w', type=float, default=None, help='hold the corridor weight at this value for every k')
    args = ap.parse_args()
    app = fcw.load_app()
    data = collect(app)
    if not data:
        print(
            'INCONCLUSIVE: data/nspl.csv, the aircraft-quiet datasets or the DEFRA GeoTIFFs are absent (all gitignored)'
        )
        return 0
    groups = data['groups']
    kind, truth, train = flat(groups, 'kind'), flat(groups, 'truth'), flat(groups, 'train')
    pts, heli, delta, ring = (
        flat(groups, 'pts'),
        flat(groups, 'heli'),
        flat(groups, 'ring_delta'),
        flat(groups, 'ring_km'),
    )
    cities = np.concatenate([[g['city']] * len(g['kind']) for g in groups])
    test = ~train

    print('Floors, measured from each raster (a blank cell inside the box reads as below it):')
    for name, r in data['rasters'].items():
        q = app.lden_db_to_quiet(round(r['floor'], 1))
        print(
            f'  {name:14} {r["floor"]:5.1f} dB -> '
            + ('quiet exactly 10' if r['floor'] <= app._QUIET_CEILING_DB else f'quiet >= {q} (a bound)')
        )
    for label, kd in (('on the strip', STRIP), ('below the floor, exact', BELOW), ('below the floor, bound', BOUND)):
        print(f'  {label:23} {int((kind == kd).sum()):>8,}  ({int((kind == kd)[test].sum()):,} test)')
    print(f'  airports still circles   {", ".join(data["circles"]) or "none"}')
    if data['unexplained']:
        print(
            f'  WARNING: {data["unexplained"]:,} live postcodes hold a DEFRA reading the aircraft-quiet datasets '
            'do not carry; excluded. Rebuild them (build_aircraft_quiet_dataset.py).'
        )

    def term(k):
        return np.concatenate([airport_term(g, k) for g in groups])

    a1 = term(1.0)
    today = lenses(quiet(a1, pts, heli, app.CORRIDOR_WEIGHT), truth, kind, test, delta)
    results, terms = [], {}
    for k in K_GRID:
        terms[k] = a = term(k)
        on = train & (kind == STRIP)
        fits = {w: float(np.abs(quiet(a[on], pts[on], heli[on], w) - truth[on]).mean()) for w in fcw.GRID}
        w = min(fcw.GRID, key=lambda w: (round(fits[w], 6), -w)) if args.w is None else args.w
        results.append({'k': k, 'w': w, **lenses(quiet(a, pts, heli, w), truth, kind, test, delta)})

    if args.w is None and abs(results[0]['w'] - app.CORRIDOR_WEIGHT) > fcw.TOLERANCE:
        print(
            f'\nWARNING: at k = 1 the refit gives w = {results[0]["w"]:.2f}, not the shipped '
            f'{app.CORRIDOR_WEIGHT:.2f}. Run fit_corridor_weight.py before trusting the baseline.'
        )

    print('\nTEST half. Error is estimate minus DEFRA; below 0 the estimate reads LOUDER (the safe side).')
    print(
        f'{"k":>6} {"w":>5} {"strip MAE":>10} {"bias":>6} {"below MAE":>10} {"bound hinge":>12} '
        f'{"axis bias":>10} {">1 quieter":>11}'
    )

    def line(label, w, r):
        print(
            f'{label:>6} {w:>5.2f} {r["strip_mae"]:>10.3f} {r["strip_bias"]:>+6.2f} {r["below_mae"]:>10.3f} '
            f'{r["bound_hinge"]:>12.3f} {r["axis_bias"]:>+10.2f} {r["quieter_share"]:>10.1%}'
        )

    line('today', app.CORRIDOR_WEIGHT, today)
    for r in results:
        line(f'{r["k"]:g}', r['w'], r)

    k = args.k
    pick = next((r for r in results if r['k'] == k), None)
    if pick is None:
        print(f'\n--k {k:g} is not on the grid {K_GRID}')
        return 1
    est0 = quiet(a1, pts, heli, app.CORRIDOR_WEIGHT)
    estk = quiet(terms[k], pts, heli, pick['w'])
    err0, errk = np.abs(est0 - truth), np.abs(estk - truth)

    print(f'\nBy city, TEST half: today vs k = {k:g} (w = {pick["w"]:.2f})')
    print(f'{"city":15} {"strip n":>8} {"strip MAE":>15} {"below n":>8} {"below MAE":>15}')
    for c in sorted(set(cities)):
        s = test & (cities == c) & (kind == STRIP)
        b = test & (cities == c) & (kind == BELOW)

        def pair(m):
            return f'{err0[m].mean():.2f} -> {errk[m].mean():.2f}' if m.sum() >= fcw.MIN_PER_CITY else 'too thin'

        print(f'{c:15} {int(s.sum()):>8,} {pair(s):>15} {int(b.sum()):>8,} {pair(b):>15}')

    lo, hi = RING_KM
    print(f'\nOn the strip, {lo:g}-{hi:g} km from the loudest airport, by angle off its runway axis (TEST half)')
    print(f'{"angle":>9} {"n":>6} {"MAE today":>10} {"bias":>6} {f"MAE k={k:g}":>10} {"bias":>6}')
    for a0, a1_ in ANGLE_BANDS:
        m = test & (kind == STRIP) & (ring >= lo) & (ring < hi) & (delta >= a0) & (delta < a1_)
        if not m.any():
            continue
        print(
            f'{f"{a0}-{min(a1_, 90):g}":>9} {int(m.sum()):>6,} {err0[m].mean():>10.2f} {(est0 - truth)[m].mean():>+6.2f} '
            f'{errk[m].mean():>10.2f} {(estk - truth)[m].mean():>+6.2f}'
        )

    chosen = recommend(results, today)
    print(
        f'\nRECOMMENDED k = {chosen:g}' if chosen is not None else '\nRECOMMENDED k: no rule written yet (recommend())'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
