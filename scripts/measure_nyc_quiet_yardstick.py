"""New York: is the PUBLISHED Quiet Skies honest against the Port Authority's monitors,
and what does the Bay Area's usage-weighted method give when fitted here? (2026-10-16)

A MEASUREMENT: it changes nothing New York publishes. Reads the yardstick from
data/us-noise-monitors.json ('NYC'), the routes from data/us-nyc-routes.json and runway
use from adsb_movements.py --runways output (pass its path).

FOUND 2026-10-16 (year DNL + measured gap, the 29 street-verified monitors): the
PUBLISHED method reads quieter than measured at 15 of 17 JFK monitors, mean +2.38 (all
airports +1.74, MAE 2.52). The usage-weighted method, nested leave-one-out: JFK 1.41
(mean -0.06), LGA 1.22, EWR 1.10 (2 monitors), TEB 1.98; all 1.43, mean -0.47 - no
airport quieter than measured. Runway use is July-August only.
"""
import json
import math
import statistics as st
import sys
from pathlib import Path

REPO = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, f'{REPO}/backend/lambdas/score')
sys.path.insert(0, f'{REPO}/scripts')
import app  # noqa: E402
import measure_us_quiet_yardstick as bay  # noqa: E402

CODES = ('JFK', 'LGA', 'EWR', 'TEB')
YARD = json.load(open(f'{REPO}/data/us-noise-monitors.json', encoding='utf-8'))['airports']['NYC']
GAP = YARD['lden_minus_dnl']
proc = json.load(open(f'{REPO}/data/us-flight-procedures.json', encoding='utf-8'))
routes = json.load(open(f'{REPO}/data/us-nyc-routes.json', encoding='utf-8'))['routes']


def monitors(which):
    """[(airport, id, lat, lon, Lden)] for 'dnl_year' or 'dnl_aneem'."""
    # Only monitors whose named street was confirmed (scripts/snap_panynj_monitors.py): an
    # unverified position must not vote on whether the published figure is honest.
    return [(m['airport'], m['id'], m['lat'], m['lon'], m[which] + GAP[m['airport']])
            for m in YARD['monitors'] if m[which] is not None and m.get('street_verified')]


def summary(errs):
    parts = []
    for code in CODES:
        e = [x[2] for x in errs if x[0] == code]
        if e:
            parts.append(f'{code}: n {len(e):2} quieter {sum(v > 0.05 for v in e):2} mean {st.mean(e):+.2f} MAE {st.mean(abs(v) for v in e):.2f}')
    allv = [x[2] for x in errs]
    return ' | '.join(parts) + f' | ALL mean {st.mean(allv):+.2f} MAE {st.mean(abs(v) for v in allv):.2f}'


def published(mons):
    """The engine as it stands (since v5.6, the fitted geometry; before it, the hand-drawn corridors)."""
    return [(c, s, app.calc_postcode_quiet(la, lo, 'nyc', raster_lden=None) - app.lden_db_to_quiet(db))
            for c, s, la, lo, db in mons]


# ---- the Bay Area method, generalised to these four airports ----
def usage(path):
    out, cur = {}, None
    for line in open(path, encoding='utf-8'):
        h = line.split()
        if h and h[0] in CODES and len(h) > 2 and h[1].isdigit():
            cur = h[0]
            out[cur] = {'runways': {}}
        elif cur and len(h) == 5 and h[1] == 'landings':
            out[cur]['runways'][h[0]] = {'landing': int(h[2]), 'take-off': int(h[4])}
    return out


def lobes(use, min_share=0.10):
    out = {}
    for code in CODES:
        counts = {rw: c for rw, c in use[code]['runways'].items() if rw != '?'}
        land = sum(c['landing'] for c in counts.values()) or 1
        take = sum(c['take-off'] for c in counts.values()) or 1
        kept = []
        for rw, info in sorted(proc['airports'][code]['runways'].items()):
            c = counts.get(rw, {'landing': 0, 'take-off': 0})
            if c['landing'] / land >= min_share:
                kept.append({'bearing': round((info['true_brg'] + 180) % 360, 2), 'runway': rw, 'kind': 'arrival'})
            if c['take-off'] / take >= min_share:
                kept.append({'bearing': round(info['true_brg'] % 360, 2), 'runway': rw, 'kind': 'departure'})
        out[code] = kept
    return out


def kept_routes(kept):
    out = []
    for r in routes:
        if r['kind'] == 'arrival':
            continue
        p = {'airport': r['airport'], 'name': r['name'], 'kind': r['kind'],
             'coords': [(la, lo) for lo, la in r['coordinates']]}
        rw = r['name'].split()[1] if r['kind'] == 'final' else bay.departure_runway(proc, p)
        want = 'arrival' if r['kind'] == 'final' else 'departure'
        if any(lb['runway'] == rw and lb['kind'] == want for lb in kept[r['airport']]):
            out.append(p)
    return out


def components(mons, kept, rts):
    aps = [{'code': c, 'lat': proc['airports'][c]['ref'][0], 'lon': proc['airports'][c]['ref'][1]} for c in CODES]
    out = []
    for code, site, lat, lon, db in mons:
        ap_km = {a['code']: app.runway_lobe_km(lat, lon, a, kept[a['code']]) for a in aps}
        path_km = {c: math.inf for c in CODES}
        for p in rts:
            for pla, plo in p['coords']:
                path_km[p['airport']] = min(path_km[p['airport']], app.haversine_km(lat, lon, pla, plo))
        out.append((code, site, db, ap_km, path_km))
    return out


def replica(comp, sizes, w):
    _, _, _, ap_km, path_km = comp
    nearest = min(ap_km[c] / sizes[c] for c in CODES)
    noise = bay.ladder(nearest, bay.AIRPORT_LADDER) + w * bay.ladder(min(path_km[c] / sizes[c] for c in CODES), bay.PATH_LADDER)
    if nearest < 15:
        noise += 2
    return max(0.0, min(10.0, 10.0 - noise))


def err(c, sizes, w):
    return replica(c, sizes, w) - app.lden_db_to_quiet(c[2])


def fit_sizes(comps, w, keep=None, margin=0.0):
    sizes = {c: 1.0 for c in CODES}
    for _ in range(3):
        for target in CODES:
            best = None
            for s in bay.SIZE_GRID:
                trial = dict(sizes, **{target: s})
                e = [err(c, trial, w) for c in comps if c[0] == target and (keep is None or (c[0], c[1]) in keep)]
                if not e:
                    continue
                mean, mae = st.mean(e), st.mean(abs(v) for v in e)
                if mean <= -margin and (best is None or mae < best[1]):
                    best = (s, mae)
            sizes[target] = best[0] if best else bay.SIZE_GRID[-1]
    return sizes


def choose(comps, keep=None, margin=0.0):
    best = None
    use = [c for c in comps if keep is None or (c[0], c[1]) in keep]
    for w in bay.WEIGHTS:
        sizes = fit_sizes(comps, w, keep, margin)
        mae = st.mean(abs(err(c, sizes, w)) for c in use)
        if best is None or mae < best[0]:
            best = (mae, w, sizes)
    return best[1], best[2]


def nested(comps, margin=0.0):
    out = []
    for c in comps:
        keep = {(x[0], x[1]) for x in comps if x is not c}
        w, sizes = choose(comps, keep, margin)
        out.append((c[0], c[1], err(c, sizes, w)))
    return out


if __name__ == '__main__':
    use = usage(sys.argv[1])
    for code in CODES:
        counts = {rw: c for rw, c in use[code]['runways'].items() if rw != '?'}
        land = sum(c['landing'] for c in counts.values()) or 1
        take = sum(c['take-off'] for c in counts.values()) or 1
        print(f'{code} use: ' + ', '.join(f"{rw} land {c['landing'] / land:.0%} dep {c['take-off'] / take:.0%}"
                                          for rw, c in sorted(counts.items()) if c['landing'] / land >= 0.02 or c['take-off'] / take >= 0.02))
    kept = lobes(use)
    rts = kept_routes(kept)
    for which in ('dnl_year', 'dnl_aneem'):
        mons = monitors(which)
        print(f'\n=== yardstick: {which} ({len(mons)} monitors; DNL + measured Lden gap) ===')
        print('PUBLISHED by the engine as it stands:', summary(published(mons)))
        comps = components(mons, kept, rts)
        for margin in (0.0, 0.2):
            w, sizes = choose(comps, margin=margin)
            print(f'usage-weighted, margin {margin}: weight {w}, sizes {sizes}')
            print('   in sample :', summary([(c[0], c[1], err(c, sizes, w)) for c in comps]))
            print('   nested LOO:', summary(nested(comps, margin)))
