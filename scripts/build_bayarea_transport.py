"""Rail access where the Bay Area's residents live: the share within a walk of a station, banded (2026-10-22).

Release 2's transport input (Bill, 2026-10-22: "rail access, banded"). The UK's `transport` is a curated band;
the Bay Area's is DERIVED: the share of a city's RESIDENTS (2020 blocks, scripts/bayarea_blocks.py) within
WALK_M of a rail, metro or light-rail station (data/us-bayarea-transit.json, BTS's National Transit Map), put
into the four bands the UK uses, so the Lambda's TRANSPORT_SCORE table scores both and no new scale is needed.
Buses and ferries are not counted (BTS's stops layer is read for rail only), and the file says so.

THE UK'S CUT-POINTS, READ FROM THEIR HOLDER (corrected 2026-10-22). This builder first typed 50/25/10% and
every note about it called those "the UK's four bands"; the UK's are 75/50/25% (build_borough_bands.py,
TRANSPORT_*_SHARE), so 25 of 49 cities read a band better than the same share earns in the UK (the code review
of 2026-10-22). Bill chose the UK's cut-points on the true figures, so BANDS is now parsed from that file, never
typed: 1 excellent (Colma), 1 good (San Francisco, 61.9%), 4 moderate, 43 poor.

The share is published ROUNDED DOWN to one place and the band taken from it, so anyone holding the file can
reproduce every band, `--check` can hold them offline, and rounding can never lift a city into a better band
(49.96% to nearest would publish 50.0, excellent): the err-loud rule of build_bayarea_quiet.py, from the code
review of 2026-10-22. No city sat within 0.05 of an edge when it changed, so no band moved.

A known gap in the source is WITHHELD, never read as no station: Capitol Corridor (Amtrak) is absent from
BTS's layer. Measured 2026-10-22 with its four stations put back by hand (approximate points, a scratch check,
never published): Emeryville 0.0% -> 50.5%, poor -> good; Berkeley 30.7 -> 34.4, Hayward 10.8 -> 11.0
and Oakland 16.8 -> 17.1 keep their bands. So Emeryville alone is withheld (SOURCE_GAP), and the set is held
both ways: a city in it carries no share, and every name in it must appear in the transit file's `known_gap`.

Licence: BTS's layer is CC-BY-3.0 US; credit "US Department of Transportation, Bureau of Transportation
Statistics". The resident frame is the 2020 Census (public domain).

  python scripts/build_bayarea_transport.py --write   write data/us-bayarea-transport.json
  python scripts/build_bayarea_transport.py --check   the file is sound (offline); and, with the block frame
                                                      on disk, every share against the stations file
"""

import argparse
import ast
import importlib.util
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STATIONS = REPO / 'data' / 'us-bayarea-transit.json'
OUT = REPO / 'data' / 'us-bayarea-transport.json'
WALK_M = 800  # about ten minutes' walk: the half-mile US transit planners use


def uk_bands(path=REPO / 'scripts' / 'build_borough_bands.py'):
    """The UK's transport cut-points as ((lower edge %, band), ...), read top down, PARSED from their holder
    rather than imported: that module loads pyproj and the NSPL helpers, which this builder never needs."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    found = {t.id: ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
             for t in n.targets if isinstance(t, ast.Name) and t.id.startswith('TRANSPORT_')}
    try:
        return ((float(found['TRANSPORT_EXCELLENT_SHARE']), 'excellent'), (float(found['TRANSPORT_GOOD_SHARE']), 'good'),
                (float(found['TRANSPORT_MODERATE_SHARE']), 'moderate'), (0.0, 'poor'))
    except KeyError as missing:
        raise SystemExit(f'{path.name} no longer holds {missing}: the Bay Area cannot take the UK bands') from None


# Lower edge of each band, in percent of residents within WALK_M: the UK's own (Bill, 2026-10-22).
BANDS = uk_bands()
SOURCE_GAP = {
    'Emeryville': "its only rail station, Capitol Corridor's, is absent from BTS's transit layer, and with it put "
                  'back the city reads good, not poor (measured 2026-10-22)',
}


def _load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / 'scripts' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def metres(a, b):
    """Metres between two (lat, lon) points, as build_bayarea_transit.py measures (equirectangular)."""
    k = 111_320
    return math.hypot((a[0] - b[0]) * k, (a[1] - b[1]) * k * math.cos(math.radians(a[0])))


def floor1(x):
    """Down to one place, toward the worse band. The 1e-9 keeps a share that IS on a figure from flooring past it."""
    return math.floor(x * 10 + 1e-9) / 10


def band_of(share_pct):
    for low, name in BANDS:
        if share_pct >= low:
            return name
    raise ValueError(f'a share below zero: {share_pct!r}')


def build(frame, cities, stations):
    pts = [(s['lat'], s['lon']) for s in stations]
    rows = []
    for c in sorted(cities, key=lambda c: c['name']):
        blocks = frame[c['geoid']]
        residents = sum(p for *_, p in blocks)
        near = sum(p for lon, lat, p in blocks if any(metres((lat, lon), s) <= WALK_M for s in pts))
        row = {'geoid': c['geoid'], 'name': c['name'], 'county': c['county'], 'residents': residents}
        if c['name'] in SOURCE_GAP:
            row.update(residents_within_walk=None, share_within_walk_pct=None, band=None,
                       withheld=SOURCE_GAP[c['name']])
        else:
            share = floor1(100 * near / residents)
            row.update(residents_within_walk=near, share_within_walk_pct=share, band=band_of(share), withheld=None)
        rows.append(row)
    return {
        'source': 'US Department of Transportation, Bureau of Transportation Statistics, National Transit Map '
                  'Stops (rail, metro and light rail; data/us-bayarea-transit.json), over the 2020 Census block '
                  'internal points weighted by population',
        'licence': 'CC-BY-3.0 US (BTS): credit US Department of Transportation, Bureau of Transportation Statistics',
        'generator': 'scripts/build_bayarea_transport.py --write',
        'measure': f'share of residents within {WALK_M} m (straight line) of a rail, metro or light-rail station; '
                   'buses and ferries are not counted',
        'walk_m': WALK_M,
        'bands': [{'from_pct': low, 'band': name} for low, name in BANDS],
        'banded_on': 'the published share, rounded DOWN to one place, so every band can be reproduced from this file '
                     'and rounding never lifts a city into a better band',
        'decided': 'Bill, 2026-10-22: rail access, banded into the UK four, scored by the same table',
        'cities': rows,
    }


def problems(doc, want, known_gap):
    out = []
    if sorted(r['name'] for r in doc['cities']) != sorted(c['name'] for c in want):
        out.append('the file does not cover exactly the 50 cities of data/us-bayarea-places.json')
    for name in SOURCE_GAP:
        if name not in known_gap:
            out.append(f"{name} is withheld for a source gap the transit file's known_gap does not name")
    held = {r['name'] for r in doc['cities'] if r['withheld'] is not None}
    if held != set(SOURCE_GAP):
        out.append(f'withheld {sorted(held)} is not SOURCE_GAP {sorted(SOURCE_GAP)}')
    for r in doc['cities']:
        if r['withheld'] is not None:
            if any(r[k] is not None for k in ('residents_within_walk', 'share_within_walk_pct', 'band')):
                out.append(f"{r['name']}: withheld, yet carries a count, a share or a band")
            continue
        if not isinstance(r['residents_within_walk'], int) or not isinstance(r['share_within_walk_pct'], float):
            out.append(f"{r['name']}: not withheld, yet carries no counts or no share")
            continue
        if not 0 <= r['residents_within_walk'] <= r['residents']:
            out.append(f"{r['name']}: {r['residents_within_walk']} within a walk of {r['residents']} residents")
            continue
        if floor1(100 * r['residents_within_walk'] / r['residents']) != r['share_within_walk_pct']:
            out.append(f"{r['name']}: share {r['share_within_walk_pct']}% is not its counts")
        if band_of(r['share_within_walk_pct']) != r['band']:
            out.append(f"{r['name']}: band {r['band']!r} is not the band of {r['share_within_walk_pct']}%")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--write', action='store_true')
    g.add_argument('--check', action='store_true')
    a = ap.parse_args()
    blocks = _load('bayarea_blocks')
    transit = json.loads(STATIONS.read_text(encoding='utf-8'))
    if a.write:
        doc = build(blocks.blocks(), blocks.cities(), transit['stations'])
        OUT.write_text(json.dumps(doc, indent=1) + '\n', encoding='utf-8', newline='\n')
        tally = {}
        for r in doc['cities']:
            tally[r['band'] or 'withheld'] = tally.get(r['band'] or 'withheld', 0) + 1
        print(f'wrote {OUT.relative_to(REPO)}: ' + ', '.join(f'{k} {v}' for k, v in tally.items()))
        for f in problems(doc, blocks.cities(), transit['known_gap']):
            print('  WARNING: ' + f)
        return 0
    doc = json.loads(OUT.read_text(encoding='utf-8'))
    failures = problems(doc, blocks.cities(), transit['known_gap'])
    if blocks.PL_RAW.exists():
        if build(blocks.blocks(), blocks.cities(), transit['stations']) != doc:
            failures.append(f'{OUT.name} is not what the stations and the block frame give (re-run --write)')
        else:
            print(f'  stations       {OUT.name} == {STATIONS.name} at every block')
    else:
        print('INCONCLUSIVE for values: the Census block frame is not on disk; shape and bands checked')
    if failures:
        print('RESULT: FAIL')
        for f in failures:
            print('  ' + f)
        return 1
    print(f"RESULT: PASS ({len(doc['cities'])} cities)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
