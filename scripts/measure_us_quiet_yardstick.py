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
data/us-bayarea-routes.json and data/us-flight-procedures.json.

Since 2026-10-16 it is also the GENERATOR and the GATE: --write fits the
usage-weighted method below and writes the US-QUIET-BAYAREA block into the
score Lambda; --check (blocking in preflight, offline) reds if that block is
stale or hand-edited, if either airport reads quieter than its monitors under
nested leave-one-out, or if the real engine disagrees with the fit at any
monitor. 'bayarea' is in no CITIES entry yet, so nothing is published from it.
Runway use comes from data/us-runway-use.json (--usage-from rebuilds it).

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

THEN ANEEM (Bill, same evening): SFO's yardstick is its ANEEM reading, which also
counts the quieter aircraft events the conventional method misses (up to 9.5 dB at
Millbrae); the fit needs each airport MARGIN = 0.2 louder in sample. Nested leave-one-
out: SFO MAE 0.96, mean -0.17; SJC 1.21, mean -0.46; route weight 1.25.

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
    # Each airport's YARDSTICK: ANEEM where its block says so (SFO, which publishes both all
    # year), else the conventional CNEL (SJC publishes only that). Bill, 2026-10-16.
    monitors = [
        (code, m['id'], m['lat'], m['lon'],
         m['aneem_cnel_db'] if block.get('yardstick') == 'aneem' else m['cnel_db'])
        for code, block in mons['airports'].items()
        if code in CODES  # the file also holds New York's ('NYC'): never the Bay Area's yardstick
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
# take-offs) is under MIN_SHARE is published but rarely flown, and is dropped;
# so are the final approaches and departure lines that belong to it. Arrival
# routes (drawn from 10,000 ft) are not scored, as UK ones are not drawn.
#
# Shares are over the movements MATCHED to a runway. Counting the unmatched in
# the total lowered every share, which can only drop lobes, and a dropped lobe
# reads QUIETER - the wrong direction for this rule.
#
# The arithmetic is a REPLICA of calc_postcode_quiet, for speed under the fits;
# the lobe distance itself is the engine's runway_lobe_km, one holder. --check
# proves the replica against the REAL engine on the SHIPPED block.
# ---------------------------------------------------------------------------

MIN_SHARE = 0.10  # 10% and 20% gave identical fits on 2026-10-16
# The fit's own rule is stricter than the gate's: in sample each airport must read at least
# MARGIN louder than measured, so that HELD OUT it does not read quieter. Without it the
# ANEEM yardstick fitted SFO to +0.12 quieter under nested leave-one-out (2026-10-16).
MARGIN = 0.2
WEIGHTS = (0.5, 0.75, 1.0, 1.25, 1.5)
SIZE_GRID = [round(0.3 + 0.05 * i, 2) for i in range(75)]
USAGE_JSON = REPO / 'data' / 'us-runway-use.json'
MARK_START = '# US-QUIET-BAYAREA:START (generated by scripts/measure_us_quiet_yardstick.py --write; do not hand-edit)'
MARK_END = '# US-QUIET-BAYAREA:END'
AIRPORT_LADDER = ((3, 5), (6, 4), (10, 3), (15, 2), (20, 1))
PATH_LADDER = ((1, 4), (2, 3), (4, 2), (6, 1))
NAMES = {'SFO': 'San Francisco', 'OAK': 'Oakland', 'SJC': 'San Jose'}


def usage_from_report(path):
    """adsb_movements.py --runways output -> the checked-in usage document."""
    usage, current, header = {}, None, None
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            head = line.split()
            if len(head) > 1 and head[1] == 'day(s),':
                header = line.strip()
            if head and head[0] in CODES and len(head) > 2 and head[1].isdigit():
                current = head[0]
                days = next((t for t in head if '/' in t and t.replace('/', '').isdigit()), None)
                usage[current] = {'days_kept': days, 'runways': {}}
            elif current and len(head) == 5 and head[1] == 'landings' and head[3] == 'take-offs':
                usage[current]['runways'][head[0]] = {'landing': int(head[2]), 'take-off': int(head[4])}
    if not header or set(usage) != set(CODES):
        raise SystemExit(f'{path}: not adsb_movements --runways output for {CODES} (found {sorted(usage)})')
    return {
        'purpose': 'How each Bay Area runway end is actually flown: the weights of the runway lobes in '
                   'calc_postcode_quiet (scripts/measure_us_quiet_yardstick.py). A published runway is not a busy one.',
        'source': 'adsb.lol daily archive, extracted by scripts/adsb_extract.py and counted by '
                  'scripts/adsb_movements.py --runways (feed-outage days left out)',
        'licence': "ODbL 1.0. Derived from adsb.lol data: credit 'aircraft positions via adsb.lol (ODbL)', and this "
                   'file is offered under ODbL (accepted by Bill, 2026-10-15)',
        'period': header.split(';')[0],
        'unmatched': "'?' is a movement no runway matched by heading and position; kept here, left out of the shares",
        'airports': usage,
    }


def load_usage():
    with open(USAGE_JSON, encoding='utf-8') as fh:
        return json.load(fh)['airports']


def lobes(proc, usage, min_share=MIN_SHARE):
    """{airport: [lobe]} kept at this share; bearings rounded so the engine's copy is exact."""
    out = {}
    for code in CODES:
        counts = {rw: c for rw, c in usage[code]['runways'].items() if rw != '?'}
        land = sum(c['landing'] for c in counts.values()) or 1
        take = sum(c['take-off'] for c in counts.values()) or 1
        kept = []
        for rw, info in sorted(proc['airports'][code]['runways'].items()):
            c = counts.get(rw, {'landing': 0, 'take-off': 0})
            a, d = c['landing'] / land, c['take-off'] / take
            if a >= min_share:
                kept.append({'bearing': round((info['true_brg'] + 180) % 360, 2), 'runway': rw,
                             'kind': 'arrival', 'share': round(a, 3)})
            if d >= min_share:
                kept.append({'bearing': round(info['true_brg'] % 360, 2), 'runway': rw,
                             'kind': 'departure', 'share': round(d, 3)})
        out[code] = kept
    return out


def bearing_deg(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    f1, f2, dl = lat1 * p, lat2 * p, (lon2 - lon1) * p
    y = math.sin(dl) * math.cos(f2)
    x = math.cos(f1) * math.sin(f2) - math.sin(f1) * math.cos(f2) * math.cos(dl)
    return math.degrees(math.atan2(y, x)) % 360


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


def kept_routes(paths, proc, kept):
    """Finals and departures that belong to a kept lobe, with the runway named."""
    out = []
    for p in paths:
        if p['kind'] == 'arrival':
            continue
        rw = p['name'].split()[1] if p['kind'] == 'final' else departure_runway(proc, p)
        want = 'arrival' if p['kind'] == 'final' else 'departure'
        if any(lb['runway'] == rw and lb['kind'] == want for lb in kept[p['airport']]):
            out.append(dict(p, runway=rw))
    return out


def components(monitors, airports, routes, kept):
    """Per monitor, the scale-free distances: per airport, the lobe distance and the
    nearest kept route point."""
    out = []
    for code, mid, lat, lon, cnel in monitors:
        ap_km = {ap['code']: app.runway_lobe_km(lat, lon, ap, kept[ap['code']]) for ap in airports}
        path_km = {c: math.inf for c in CODES}
        for p in routes:
            for plat, plon in p['coords']:
                path_km[p['airport']] = min(path_km[p['airport']], app.haversine_km(lat, lon, plat, plon))
        out.append((code, mid, cnel, ap_km, path_km))
    return out


def ladder(d, steps):
    for limit, pts in steps:
        if d < limit:
            return pts
    return 0


def replica(comp, sizes, weight):
    """calc_postcode_quiet's arithmetic on precomputed distances, for a city whose
    every airport is a major one and which has no heliports."""
    _, _, _, ap_km, path_km = comp
    nearest = min(ap_km[c] / sizes[c] for c in CODES)
    noise = ladder(nearest, AIRPORT_LADDER)
    noise += weight * ladder(min(path_km[c] / sizes[c] for c in CODES), PATH_LADDER)
    if nearest < 15:
        noise += 2
    return max(0.0, min(10.0, 10.0 - noise))


def err(comp, sizes, weight):
    return replica(comp, sizes, weight) - app.lden_db_to_quiet(comp[2])


def fit_sizes(comps, weight, keep=None):
    """Per-airport size under the rule (mean signed error <= 0 at each airport),
    then the smallest MAE. OAK has no monitors in hand: it takes the LARGER of the
    fitted sizes, the louder direction."""
    sizes = {c: 1.0 for c in CODES}
    fitted = sorted({c[0] for c in comps})
    for _ in range(3):
        for target in fitted:
            best = None
            for s in SIZE_GRID:
                trial = dict(sizes, **{target: s})
                e = [err(c, trial, weight) for c in comps
                     if c[0] == target and (keep is None or (c[0], c[1]) in keep)]
                mean, mae = st.mean(e), st.mean(abs(v) for v in e)
                if mean <= -MARGIN and (best is None or mae < best[1]):
                    best = (s, mae)
            sizes[target] = best[0] if best else SIZE_GRID[-1]
    sizes['OAK'] = max(sizes[c] for c in fitted)
    return sizes


def choose(comps, keep=None):
    """(weight, sizes): the weight whose fitted sizes give the smallest MAE."""
    best = None
    use = [c for c in comps if keep is None or (c[0], c[1]) in keep]
    for w in WEIGHTS:
        sizes = fit_sizes(comps, w, keep)
        mae = st.mean(abs(err(c, sizes, w)) for c in use)
        if best is None or mae < best[0]:
            best = (mae, w, sizes)
    return best[1], best[2]


def nested_loo(comps):
    """Leave-one-out with the weight AND sizes chosen without the held-out monitor."""
    out = []
    for c in comps:
        keep = {(x[0], x[1]) for x in comps if x is not c}
        w, sizes = choose(comps, keep)
        out.append((c[0], c[1], err(c, sizes, w)))
    return out


def render(airports, routes, kept, sizes, weight):
    lines = ['AIRPORTS_BAYAREA = [']
    lines += [f"    {{'code': {a['code']!r}, 'name': {NAMES[a['code']]!r}, 'lat': {a['lat']!r}, 'lon': {a['lon']!r}}},"
              for a in airports]
    lines += [']', 'FLIGHT_PATHS_BAYAREA = [']
    for p in routes:
        lines += ['    {', f"        'name': {p['name']!r},", f"        'airport': {p['airport']!r},",
                  f"        'kind': {p['kind']!r},", f"        'runway': {p['runway']!r},", "        'coords': ["]
        lines += [f'            ({la!r}, {lo!r}),' for la, lo in p['coords']]
        lines += ['        ],', '    },']
    lines += [']', 'BAYAREA_QUIET = {', "    'runway_lobes': {"]
    for code, lbs in kept.items():
        lines.append(f'        {code!r}: [')
        lines += [f"            {{'bearing': {lb['bearing']!r}, 'runway': {lb['runway']!r}, "
                  f"'kind': {lb['kind']!r}, 'share': {lb['share']!r}}}," for lb in lbs]
        lines.append('        ],')
    lines += ['    },', f"    'airport_sizes': {sizes!r},", f"    'corridor_weight': {weight!r},",
              f"    'major_airports': {list(CODES)!r},", '}']
    return '\n'.join(lines)


def splice(body, write):
    """True when the block in app.py differs from body; rewrites it when write."""
    sys.path.insert(0, str(REPO / 'scripts'))
    from build_flight_paths import replace_block  # noqa: PLC0415
    return replace_block(REPO / 'backend' / 'lambdas' / 'score' / 'app.py', MARK_START, MARK_END, body, write)


def engine_vs_replica(monitors, comps, weight, sizes):
    """Worst |engine - replica| at every monitor, through the REAL calc_postcode_quiet
    and the SHIPPED 'bayarea' geometry - no patching."""
    worst = 0.0
    for (_, _, lat, lon, _), c in zip(monitors, comps, strict=True):
        engine = app.calc_postcode_quiet(lat, lon, 'bayarea', raster_lden=None)
        worst = max(worst, abs(engine - replica(c, sizes, weight)))
    return worst


def run_fit(write):
    monitors, airports, paths, proc = load()
    kept = lobes(proc, load_usage())
    routes = kept_routes(paths, proc, kept)
    comps = components(monitors, airports, routes, kept)
    weight, sizes = choose(comps)
    print(f'lobes kept (share >= {MIN_SHARE:.0%} of matched movements): ' + '; '.join(
        f'{c} ' + ', '.join(f"{lb['kind'][:3]} {lb['runway']} {lb['share']:.0%}" for lb in lbs)
        for c, lbs in kept.items()))
    print(f'routes scored: {len(routes)} (finals and departures of kept lobes)')
    print(f'fitted: corridor weight {weight}, sizes {sizes}')
    print('in sample : ' + summary([(c[0], c[1], err(c, sizes, weight)) for c in comps]))
    held = nested_loo(comps)
    print('nested LOO: ' + summary(held))
    failures = []
    for code in sorted({h[0] for h in held}):
        mean = st.mean(h[2] for h in held if h[0] == code)
        if mean > 0:
            failures.append(f'{code} reads QUIETER than its monitors held out (mean {mean:+.2f})')
    changed = splice(render(airports, routes, kept, sizes, weight), write)
    if write:
        print('app.py block ' + ('rewritten' if changed else 'already current'))
    elif changed:
        failures.append('app.py US-QUIET-BAYAREA block is not what --write would produce (re-run --write)')
    else:
        worst = engine_vs_replica(monitors, comps, weight, sizes)
        print(f'engine vs replica at {len(monitors)} monitors: worst difference {worst:.6f}')
        if worst > 1e-9:
            failures.append(f'the engine disagrees with the fit at the monitors (worst {worst:.6f})')
    for f in failures:
        print('FAIL: ' + f)
    print('RESULT: ' + ('FAIL' if failures else 'PASS'))
    return 1 if failures else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--usage-from', metavar='FILE',
                      help='write data/us-runway-use.json from adsb_movements.py --runways output')
    mode.add_argument('--write', action='store_true', help='fit and write the US-QUIET-BAYAREA block into app.py')
    mode.add_argument('--check', action='store_true',
                      help='fail if the shipped block is stale, reads quieter than the monitors held out, '
                           'or the engine disagrees with the fit')
    args = ap.parse_args()
    if args.usage_from:
        doc = usage_from_report(args.usage_from)
        with open(USAGE_JSON, 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(doc, fh, indent=2)
            fh.write('\n')
        print(f'wrote {USAGE_JSON.relative_to(REPO)}')
        return 0
    if args.write or args.check:
        return run_fit(args.write)
    monitors, airports, paths, proc = load()
    for c in CODES:
        axis, resultant = mean_axis(proc, c)
        print(f'{c}: runway axes {[round(a, 1) for a in runway_axes(proc, c)]}, '
              f'mean axis {axis:.1f} (resultant {resultant:.2f})')
    heathrow = {c: 1.0 for c in CODES}
    print('\ntoday\'s method and its first repairs, per airport (+ = reads quieter than measured):')
    for shape in ('circle', 'mean', 'per-runway'):
        set_shape(proc, shape)
        print(f'  {shape:10} Heathrow-sized, SFO major: {summary(errors(monitors, airports, paths, heathrow, False))}')
    set_shape(proc, 'per-runway')
    print(f'  per-runway, each its own major: {summary(errors(monitors, airports, paths, heathrow, True))}')
    print('\nthe shipped method: --check')
    return 0


if __name__ == '__main__':
    sys.exit(main())
