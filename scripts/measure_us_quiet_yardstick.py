"""Measure the Quiet Skies estimate against US airport noise monitors.

WHY THIS EXISTS
---------------
ROADMAP "Release 2 plan" decision 1 (accepted 2026-10-16): the Bay Area stays
facts-only until its aircraft estimate passes against MEASURED noise, under the
v5.5 rule that no area may read quieter than its yardstick. In the UK the
yardstick is DEFRA's map; the US has no national one, so it is the airports' own
permanent monitors (data/us-noise-monitors.json: SJC's 13, SFO's 29).

The 2026-10-11 measurement (SJC only, quieter at 10 of 13 by a mean 2.3) was
scratch work and was lost. This script reproduces it from files in the repo and
runs the REAL calc_postcode_quiet, with a Bay Area geometry patched in from
data/us-bayarea-routes.json and data/us-flight-procedures.json. It is a
MEASUREMENT, not yet a gate: nothing here changes what the API publishes.

WHAT IT REPORTS (each per airport, because a pooled figure hides one airport
reading quieter than measured behind another reading louder):
  1. today's US treatment: circles, every airport Heathrow-sized, SFO the one
     "major" airport;
  2. runway-shaped airports (k = AIRPORT_SHAPE_K), one axis PER RUNWAY - SFO's
     two runway pairs cross at right angles, so the UK builder's doubled-angle
     MEAN axis has a resultant of zero there and means nothing;
  3. every airport the major airport of its own area (the London-shaped single
     "major" leaves San Jose without its near-field term);
  4. a per-airport size fitted against its own monitors, the analogue of the
     UK's DEFRA-footprint AIRPORT_NOISE_SCALE, with the UK's fitted k and
     CORRIDOR_WEIGHT held, under the rule (mean signed error <= 0 at each
     airport) - reported in-sample and held out (fit on alternate monitors,
     report the rest).

WHAT IT FOUND (2026-10-16): see ROADMAP "Release 2 plan". In short, (3) and (4)
pass the rule at both airports IN sample, but held out the answer depends on
which monitors are held back: one alternating split passed at both airports,
this script's split (alternate ids in sorted order) reads San Jose QUIETER than
measured on its unseen monitors (+0.13). Thirteen monitors are too few to fit an
airport's size robustly. And SFO's error stays at 2.4-2.9 points, carried by
Millbrae, Burlingame and Hillsborough on the 01/19 line: measured 36-45 dB, read
5-8 points too loud, because a published runway is not a busy one and the
geometry cannot tell which runways and directions are actually flown.

THEN, USAGE-WEIGHTED (--usage, same day): each runway END becomes an arrival
lobe and a departure lobe weighted by its share of landings / take-offs counted
from adsb.lol tracks (July-August 2026), lobes under 10% dropped with their
routes, arrival routes not scored. That cut SFO to 1.85 in sample. The rest was
the ROUTE WEIGHT: refitted on these normal-year monitors it is 1.0, not the UK's
0.5 (fitted against DEFRA's lockdown-year map, about half a normal footprint).
NESTED leave-one-out (weight AND sizes chosen without the held-out monitor):
SFO MAE 1.43, mean -0.15; SJC MAE 1.06, mean -0.69; weight 1.0 in 35 of 42
folds, 1.25 in 7. Neither airport reads quieter than measured. A replica of
calc_postcode_quiet is used for speed and matches the engine exactly first.

CNEL is taken as Lden with no conversion (the data file says why: the safe
direction for this rule).
"""

import argparse
import json
import math
import statistics as st
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'backend' / 'lambdas' / 'score'))
import app  # noqa: E402

CODES = ('SFO', 'OAK', 'SJC')
ORIG_DISTANCE = app.airport_distance_km
ORIG_SCALE = app.airport_noise_scale
QUIETER = 0.05  # a monitor counts as "read quieter" beyond rounding


def load():
    with open(REPO / 'data' / 'us-noise-monitors.json', encoding='utf-8') as fh:
        mons = json.load(fh)
    with open(REPO / 'data' / 'us-flight-procedures.json', encoding='utf-8') as fh:
        proc = json.load(fh)
    with open(REPO / 'data' / 'us-bayarea-routes.json', encoding='utf-8') as fh:
        routes = json.load(fh)['routes']
    monitors = [
        (code, m['id'], m['lat'], m['lon'], m['cnel_db'])
        for code, block in mons['airports'].items()
        for m in block['monitors']
    ]
    airports = [
        {'code': c, 'name': c, 'lat': proc['airports'][c]['ref'][0], 'lon': proc['airports'][c]['ref'][1]}
        for c in CODES
    ]
    paths = [
        {'airport': r['airport'], 'name': r['name'], 'kind': r['kind'],
         'coords': [(lat, lon) for lon, lat in r['coordinates']]}
        for r in routes
    ]
    return monitors, airports, paths, proc


def runway_axes(proc, code):
    """Distinct runway axes, degrees mod 180 (parallel runways within 5 deg are one)."""
    out = []
    for rw in proc['airports'][code]['runways'].values():
        a = rw['true_brg'] % 180
        if not any(abs(((a - b + 90) % 180) - 90) < 5 for b in out):
            out.append(a)
    return out


def mean_axis(proc, code):
    """The UK builder's rule: doubled-angle mean of the bearings, and its resultant (0-1)."""
    bs = [rw['true_brg'] for rw in proc['airports'][code]['runways'].values()]
    x = sum(math.cos(math.radians(2 * b)) for b in bs)
    y = sum(math.sin(math.radians(2 * b)) for b in bs)
    return (math.degrees(math.atan2(y, x)) / 2) % 180, math.hypot(x, y) / len(bs)


def set_shape(proc, mode):
    """'circle', 'mean' (one averaged axis) or 'per-runway' (nearest of each runway's axis)."""
    for c in CODES:
        app.RUNWAY_AXIS_DEG.pop(c, None)
    app.airport_distance_km = ORIG_DISTANCE
    if mode == 'mean':
        for c in CODES:
            app.RUNWAY_AXIS_DEG[c] = mean_axis(proc, c)[0]
    elif mode == 'per-runway':
        axes = {c: runway_axes(proc, c) for c in CODES}

        def per_runway(lat, lon, ap):
            if ap['code'] not in axes:
                return ORIG_DISTANCE(lat, lon, ap)
            best = math.inf
            for a in axes[ap['code']]:
                app.RUNWAY_AXIS_DEG[ap['code']] = a
                best = min(best, ORIG_DISTANCE(lat, lon, ap))
            app.RUNWAY_AXIS_DEG.pop(ap['code'], None)
            return best

        app.airport_distance_km = per_runway


def set_scale(scales):
    app.airport_noise_scale = lambda code: scales.get(code, ORIG_SCALE(code))


def errors(monitors, airports, paths, scales, each_major):
    """(airport, id, estimate - measured quiet) per monitor; + means read QUIETER."""
    set_scale(scales)
    out = []
    for code, mid, lat, lon, cnel in monitors:
        major = 'SFO'
        if each_major:  # airports are 17-48 km apart, beyond the 15 km bonus radius
            eff = {a['code']: app.airport_distance_km(lat, lon, a) / scales[a['code']] for a in airports}
            major = min(eff, key=eff.get)
        app.CITY_GEOMETRY['bayarea'] = {'airports': airports, 'paths': paths, 'major_airport': major,
                                        'secondary_airport': None, 'heliports': []}
        est = app.calc_postcode_quiet(lat, lon, 'bayarea', raster_lden=None)
        out.append((code, mid, est - app.lden_db_to_quiet(cnel)))
    return out


def summary(errs, keep=None):
    parts = []
    for code in sorted({e[0] for e in errs}):
        e = [x[2] for x in errs if x[0] == code and (keep is None or x[1] in keep[code])]
        parts.append(f'{code}: n {len(e):2} quieter {sum(v > QUIETER for v in e):2} '
                     f'mean {st.mean(e):+.2f} MAE {st.mean(abs(v) for v in e):.2f}')
    return ' | '.join(parts)


def fit(monitors, airports, paths, keep=None):
    """Per-airport size with monitors, by coordinate descent; OAK (no monitors in
    hand) takes the larger of the fitted sizes, the louder direction."""
    grid = [round(0.3 + 0.05 * i, 2) for i in range(55)]
    scales = {c: 1.0 for c in CODES}
    fitted = sorted({m[0] for m in monitors})
    for _ in range(2):
        for target in fitted:
            best = None
            for s in grid:
                trial = dict(scales, **{target: s})
                e = [x[2] for x in errors(monitors, airports, paths, trial, True)
                     if x[0] == target and (keep is None or x[1] in keep[target])]
                mean, mae = st.mean(e), st.mean(abs(v) for v in e)
                if mean <= 0 and (best is None or mae < best[1]):
                    best = (s, mae)
            scales[target] = best[0]
    scales['OAK'] = max(scales[c] for c in fitted)
    return scales


# ---------------------------------------------------------------------------
# Usage-weighted runways (2026-10-16): a published runway is not a busy one.
#
# Each runway END gets two LOBES, half-lines from the airport: an ARRIVAL lobe on
# the approach side (aircraft landing on 28L come in from the east-south-east, so
# the lobe points along 28L's heading + 180) and a DEPARTURE lobe on the climb-out
# side (along the heading). A lobe whose share of the airport's landings (or
# take-offs) is below `min_share` is published but rarely flown, and is dropped;
# so are the final approaches and departure lines that belong to it. Shares are
# counted from adsb.lol flight tracks (ODbL) by adsb_movements.py --runways.
# Arrival routes (drawn from 10,000 ft) are not scored, as UK ones are not drawn.
#
# The arithmetic is a REPLICA of calc_postcode_quiet, for speed under the fits;
# replica_matches_engine() proves it against the engine before any result counts.
# ---------------------------------------------------------------------------


def parse_usage(path):
    """{airport: {runway: {'landing': n, 'take-off': n}}} from adsb_movements --runways output."""
    usage, current = {}, None
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            head = line.split()
            if head and head[0] in CODES and len(head) > 2 and head[1].isdigit():
                current = head[0]
                usage[current] = {}
            elif current and len(head) == 5 and head[1] == 'landings' and head[3] == 'take-offs':
                usage[current][head[0]] = {'landing': int(head[2]), 'take-off': int(head[4])}
    return usage


def lobes(proc, usage, min_share):
    """{airport: [(bearing, share, kind, runway)]} for the lobes kept at this share."""
    out = {}
    for code in CODES:
        rws = proc['airports'][code]['runways']
        counts = usage.get(code, {})
        land = sum(c['landing'] for c in counts.values()) or 1
        take = sum(c['take-off'] for c in counts.values()) or 1
        kept = []
        for rw, info in rws.items():
            c = counts.get(rw, {'landing': 0, 'take-off': 0})
            a, d = c['landing'] / land, c['take-off'] / take
            if a >= min_share:
                kept.append(((info['true_brg'] + 180) % 360, a, 'arrival', rw))
            if d >= min_share:
                kept.append((info['true_brg'] % 360, d, 'departure', rw))
        out[code] = kept
    return out


def bearing_deg(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    f1, f2, dl = lat1 * p, lat2 * p, (lon2 - lon1) * p
    return math.degrees(math.atan2(math.sin(dl) * math.cos(f2),
                                   math.cos(f1) * math.sin(f2) - math.sin(f1) * math.cos(f2) * math.cos(dl))) % 360


def lobe_km(lat, lon, ap, bearing):
    """Shaped distance to a half-line: on its side, sqrt(along^2 + (k side)^2);
    behind it, k times the distance, i.e. off the strip."""
    d = app.haversine_km(lat, lon, ap['lat'], ap['lon'])
    off = math.radians(bearing_deg(ap['lat'], ap['lon'], lat, lon) - bearing)
    along, side = d * math.cos(off), d * math.sin(off)
    if along < 0:
        return app.AIRPORT_SHAPE_K * d
    return math.hypot(along, app.AIRPORT_SHAPE_K * side)


def departure_runway(proc, path):
    """The runway end a departure line belongs to: initial bearing within 30 deg of
    its true bearing, nearest threshold wins."""
    (la1, lo1), (la2, lo2) = path['coords'][0], path['coords'][1]
    brg = bearing_deg(la1, lo1, la2, lo2)
    best = None
    for rw, info in proc['airports'][path['airport']]['runways'].items():
        diff = abs((brg - info['true_brg'] + 180) % 360 - 180)
        if diff <= 30:
            dist = app.haversine_km(la1, lo1, *info['thr'])
            if best is None or dist < best[0]:
                best = (dist, rw)
    return best and best[1]


def components(monitors, airports, paths, proc, kept, include_arrivals=False, axis_mode=False):
    """Per monitor, the scale-free distances the estimate needs: per airport, the
    airport-term distance and the nearest kept route point."""
    keep_routes = []
    for p in paths:
        if p['kind'] == 'arrival':
            if include_arrivals:
                keep_routes.append(p)
            continue
        if axis_mode:
            keep_routes.append(p)
            continue
        rw = p['name'].split()[1] if p['kind'] == 'final' else departure_runway(proc, p)
        kinds = {(r, k) for _, _, k, r in kept[p['airport']]}
        if (rw, 'arrival' if p['kind'] == 'final' else 'departure') in kinds:
            keep_routes.append(p)
    out = []
    for code, mid, lat, lon, cnel in monitors:
        ap_km, path_km = {}, {c: math.inf for c in CODES}
        for ap in airports:
            if axis_mode:  # the per-runway AXIS of the engine, both directions
                ap_km[ap['code']] = app.airport_distance_km(lat, lon, ap)
            elif kept[ap['code']]:
                ap_km[ap['code']] = min(lobe_km(lat, lon, ap, b) for b, _, _, _ in kept[ap['code']])
            else:
                ap_km[ap['code']] = app.haversine_km(lat, lon, ap['lat'], ap['lon'])
        for p in keep_routes:
            for plat, plon in p['coords']:
                path_km[p['airport']] = min(path_km[p['airport']], app.haversine_km(lat, lon, plat, plon))
        out.append((code, mid, cnel, ap_km, path_km))
    return out


def ladder(d, steps):
    for limit, pts in steps:
        if d < limit:
            return pts
    return 0


AIRPORT_LADDER = ((3, 5), (6, 4), (10, 3), (15, 2), (20, 1))
PATH_LADDER = ((1, 4), (2, 3), (4, 2), (6, 1))


def replica(comp, scales):
    """calc_postcode_quiet's arithmetic on precomputed distances; every airport its
    own major (+2 within 15 effective km), no secondary, no heliports."""
    _, _, _, ap_km, path_km = comp
    eff = {c: ap_km[c] / scales[c] for c in CODES}
    nearest = min(eff.values())
    noise = ladder(nearest, AIRPORT_LADDER)
    noise += app.CORRIDOR_WEIGHT * ladder(min(path_km[c] / scales[c] for c in CODES), PATH_LADDER)
    if nearest < 15:
        noise += 2
    return max(0.0, min(10.0, 10.0 - noise))


def replica_matches_engine(monitors, airports, paths, proc, scales):
    """The replica must equal the engine wherever both describe the same model:
    per-runway axes, every route, each airport its own major."""
    comps = components(monitors, airports, paths, proc, None, include_arrivals=True, axis_mode=True)
    engine = errors(monitors, airports, paths, scales, True)
    worst = max(abs((replica(c, scales) - app.lden_db_to_quiet(c[2])) - e[2]) for c, e in zip(comps, engine, strict=True))
    return worst


def fit_fast(comps, keep=None):
    """fit() on the replica: per-airport size under the rule (mean signed <= 0)."""
    grid = [round(0.3 + 0.05 * i, 2) for i in range(75)]
    scales = {c: 1.0 for c in CODES}
    fitted = sorted({c[0] for c in comps})
    for _ in range(3):
        for target in fitted:
            best = None
            for s in grid:
                trial = dict(scales, **{target: s})
                e = [replica(c, trial) - app.lden_db_to_quiet(c[2]) for c in comps
                     if c[0] == target and (keep is None or c[1] in keep)]
                mean, mae = st.mean(e), st.mean(abs(v) for v in e)
                if mean <= 0 and (best is None or mae < best[1]):
                    best = (s, mae)
            scales[target] = best[0] if best else grid[-1]
    scales['OAK'] = max(scales[c] for c in fitted)
    return scales


def loo(comps):
    """Leave-one-out: refit without each monitor, predict it. Per airport, the
    mean signed error of the held-out predictions and their MAE."""
    out = []
    for c in comps:
        keep = {x[1] for x in comps if x[0] == c[0] and x[1] != c[1]}
        sc = fit_fast([x for x in comps if x[0] != c[0] or x[1] in keep])
        out.append((c[0], c[1], replica(c, sc) - app.lden_db_to_quiet(c[2])))
    return out


def usage_report(monitors, airports, paths, proc, usage_path):
    usage = parse_usage(usage_path)
    for code in CODES:
        counts = usage.get(code, {})
        land = sum(c['landing'] for c in counts.values()) or 1
        take = sum(c['take-off'] for c in counts.values()) or 1
        print(f'{code} use: ' + ', '.join(
            f"{rw} land {c['landing'] / land:.0%} dep {c['take-off'] / take:.0%}" for rw, c in sorted(counts.items())))
    heathrow = {c: 1.0 for c in CODES}
    set_shape(proc, 'per-runway')
    worst = replica_matches_engine(monitors, airports, paths, proc, heathrow)
    print(f'\nreplica vs engine (per-runway axes, all routes, each its own major): worst difference {worst:.6f}')
    if worst > 1e-9:
        print('REPLICA DOES NOT MATCH THE ENGINE - results below are not valid')
        return 1
    print('\nusage-weighted lobes, finals + departures only; per airport size fitted under the rule:')
    for share in (0.0, 0.02, 0.05, 0.10, 0.20):
        kept = lobes(proc, usage, share)
        comps = components(monitors, airports, paths, proc, kept)
        sc = fit_fast(comps)
        ins = [(c[0], c[1], replica(c, sc) - app.lden_db_to_quiet(c[2])) for c in comps]
        held = loo(comps)
        print(f'  min share {share:4.0%} sizes {sc}')
        print(f'      in sample : {summary(ins)}')
        print(f'      leave-one-out: {summary(held)}')
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--usage', metavar='FILE',
                    help='adsb_movements.py --runways output for SFO, OAK and SJC: run the usage-weighted model')
    args = ap.parse_args()
    monitors, airports, paths, proc = load()
    if args.usage:
        return usage_report(monitors, airports, paths, proc, args.usage)
    for c in CODES:
        axis, resultant = mean_axis(proc, c)
        print(f'{c}: runway axes {[round(a, 1) for a in runway_axes(proc, c)]}, '
              f'mean axis {axis:.1f} (resultant {resultant:.2f})')
    heathrow = {c: 1.0 for c in CODES}
    print('\nestimate - measured quiet, per airport (+ = reads quieter than measured):')
    for shape in ('circle', 'mean', 'per-runway'):
        set_shape(proc, shape)
        print(f'  {shape:10} Heathrow-sized, SFO major:      {summary(errors(monitors, airports, paths, heathrow, False))}')
    set_shape(proc, 'per-runway')
    print(f'  per-runway Heathrow-sized, each its own major: {summary(errors(monitors, airports, paths, heathrow, True))}')
    scales = fit(monitors, airports, paths)
    print(f'  per-runway fitted {scales}: {summary(errors(monitors, airports, paths, scales, True))}')
    ids = {c: sorted(m[1] for m in monitors if m[0] == c) for c in {m[0] for m in monitors}}
    train = {c: set(v[0::2]) for c, v in ids.items()}
    test = {c: set(v[1::2]) for c, v in ids.items()}
    held = fit(monitors, airports, paths, keep=train)
    print(f'  held out: fitted on alternate monitors {held}; on the rest: '
          f'{summary(errors(monitors, airports, paths, held, True), keep=test)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
