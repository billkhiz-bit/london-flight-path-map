"""Flood zones where the Bay Area's residents live: FEMA's 1%-a-year zone at every block (2026-10-18).

Release 2's flood input (ROADMAP "Release 2 plan"). The UK's `floodMediumOrHighPct` is the share of a
borough's postcodes the Environment Agency rates Medium or High (at least 1% a year); FEMA's Special
Flood Hazard Area (`SFHA_TF = 'T'`: zones A, AE, AH, AO, V, VE ...) is the same 1%-a-year line, so this
is the share of a city's RESIDENTS (2020 blocks, scripts/bayarea_blocks.py) inside it.

FEMA maps all of its studied land, minimal-risk zone X included, so a resident in NO polygon, or in zone
D ("possible but undetermined"), has an UNKNOWN risk, not a zero one: they are counted as `unknown`,
left out of the share, and the check fails a city where they are more than UNKNOWN_MAX_PCT of residents.
Points are tested even-odd over every ring of a polygon, so a hole is outside without being told.

Input: data/fema/nfhl-bayarea.esrijson.gz and its manifest, pulled from the manual US-runner workflow
(`gh run download <run> -D data/fema/`), since FEMA refuses this network. Public domain (FEMA NFHL).

  python scripts/build_bayarea_flood.py --write   write data/us-bayarea-flood.json
  python scripts/build_bayarea_flood.py --check   the file is sound (offline); and, with the FEMA file
                                                  and the block frame on disk, every share against them
"""

import argparse
import gzip
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / 'data' / 'fema' / 'nfhl-bayarea.esrijson.gz'
MANIFEST = REPO / 'data' / 'fema' / 'manifest.json'
OUT = REPO / 'data' / 'us-bayarea-flood.json'
# Zones that are not a determination of flood risk, read as UNKNOWN like "no polygon". D is "possible but
# undetermined"; the first real file (run 39443609009, 2026-10-20) also held 'AREA NOT INCLUDED' (3 polygons,
# land outside the study) and 'OPEN WATER' (13), both SFHA_TF 'F', which read as 'outside' (safe) before.
UNDETERMINED = {'D', 'AREA NOT INCLUDED', 'OPEN WATER'}
UNKNOWN_MAX_PCT = 5.0
CELL_DEG = 0.02  # polygon index cells, about 2 km


def _load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / 'scripts' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


inside = _load('build_bay_area_page').inside  # the repo's one even-odd test


def zone_index(features):
    """[(bbox, rings, sfha, zone)] and {cell: [polygon numbers]} for a quick candidate lookup."""
    polys, cells = [], {}
    for f in features:
        rings = (f.get('geometry') or {}).get('rings')
        if not rings:
            continue
        a = f['attributes']
        xs = [x for r in rings for x, _ in r]
        ys = [y for r in rings for _, y in r]
        box = (min(xs), min(ys), max(xs), max(ys))
        i = len(polys)
        polys.append((box, rings, a.get('SFHA_TF') == 'T', a.get('FLD_ZONE')))
        for cx in range(int(box[0] // CELL_DEG), int(box[2] // CELL_DEG) + 1):
            for cy in range(int(box[1] // CELL_DEG), int(box[3] // CELL_DEG) + 1):
                cells.setdefault((cx, cy), []).append(i)
    return polys, cells


def classify(lon, lat, polys, cells):
    """'sfha', 'outside' (a determined zone that is not the 1% one) or 'unknown' (zone D, or no polygon)."""
    hits = set()
    for i in cells.get((int(lon // CELL_DEG), int(lat // CELL_DEG)), ()):
        box, rings, sfha, zone = polys[i]
        if box[0] <= lon <= box[2] and box[1] <= lat <= box[3] and inside(rings, lon, lat):
            hits.add('sfha' if sfha else 'unknown' if zone in UNDETERMINED else 'outside')
    # overlapping studies (a county map and a newer revision) can both hold a point: the riskier reading wins
    return 'sfha' if 'sfha' in hits else 'outside' if 'outside' in hits else 'unknown'


def build(frame, features, manifest):
    polys, cells = zone_index(features)
    rows = []
    for p in _load('bayarea_blocks').cities():
        n = {'sfha': 0, 'outside': 0, 'unknown': 0}
        for lon, lat, pop in frame[p['geoid']]:
            n[classify(lon, lat, polys, cells)] += pop
        known = n['sfha'] + n['outside']
        rows.append({'geoid': p['geoid'], 'name': p['name'], 'county': p['county'],
                     'residents': sum(n.values()), 'residents_sfha': n['sfha'], 'residents_unknown': n['unknown'],
                     'sfha_pct': round(100 * n['sfha'] / known, 2) if known else None})
    return {
        'source': 'FEMA National Flood Hazard Layer, flood hazard zones (Special Flood Hazard Area, 1% annual '
                  'chance), read at the 2020 Census block internal points',
        'fema_fetched_utc': manifest.get('fetched_utc'), 'fema_sha256_gz': manifest.get('sha256_gz'),
        'generalised_polygons': len(manifest.get('generalised_deg') or {}),
        # left out because FEMA would not return them at any detail; residents they hold read as unknown
        'refused_polygons': manifest.get('refused') or {},
        'licence': 'public domain (FEMA, a US government work)',
        'generator': 'scripts/build_bayarea_flood.py --write',
        'measure': 'share of residents in a determined zone who are inside the SFHA (SFHA_TF = T); residents in '
                   'zone D or in no polygon are unknown, counted, and left out of the share',
        'cities': rows,
    }


def problems(doc, want):
    out = []
    if {r['geoid'] for r in doc['cities']} != {p['geoid'] for p in want}:
        out.append(f"coverage: {len(doc['cities'])} cities, not the {len(want)} of the places file")
    for r in doc['cities']:
        if r['residents'] and 100 * r['residents_unknown'] / r['residents'] > UNKNOWN_MAX_PCT:
            out.append(f"{r['name']}: {r['residents_unknown']:,} of {r['residents']:,} residents have no "
                       f'determined zone (over {UNKNOWN_MAX_PCT}%); find out why before scoring it')
        known = r['residents'] - r['residents_unknown']
        if r['sfha_pct'] != (round(100 * r['residents_sfha'] / known, 2) if known else None):
            out.append(f"{r['name']}: sfha_pct is not its counts")
    return out


def read_raw():
    doc = json.loads(gzip.decompress(RAW.read_bytes()))
    if doc.get('format') != 'esrijson' or doc.get('spatialReference', {}).get('wkid') != 4326:
        raise SystemExit(f'{RAW.name}: not WGS84 Esri JSON')
    return doc['features'], json.loads(MANIFEST.read_text(encoding='utf-8'))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--write', action='store_true')
    g.add_argument('--check', action='store_true')
    a = ap.parse_args()
    blocks = _load('bayarea_blocks')
    if a.write:
        doc = build(blocks.blocks(), *read_raw())
        OUT.write_text(json.dumps(doc, indent=1) + '\n', encoding='utf-8', newline='\n')
        top = sorted((r for r in doc['cities'] if r['sfha_pct'] is not None), key=lambda r: -r['sfha_pct'])
        print(f"wrote {OUT.relative_to(REPO)}: highest " + ', '.join(f"{r['name']} {r['sfha_pct']}%" for r in top[:5]))
        for f in problems(doc, blocks.cities()):
            print('  WARNING: ' + f)
        return 0
    doc = json.loads(OUT.read_text(encoding='utf-8'))
    failures = problems(doc, blocks.cities())
    if RAW.exists() and blocks.PL_RAW.exists():
        if build(blocks.blocks(), *read_raw()) != doc:
            failures.append(f'{OUT.name} is not what the FEMA file gives (re-run --write)')
        else:
            print(f'  FEMA file      {OUT.name} == {RAW.name} at every block')
    else:
        print('INCONCLUSIVE for values: the FEMA file or the block frame is not on disk; shape checked')
    if failures:
        print('RESULT: FAIL')
        for f in failures:
            print('  ' + f)
        return 1
    print(f"RESULT: PASS ({len(doc['cities'])} cities)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
