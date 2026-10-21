"""Flood zones where the Bay Area's residents live: FEMA's 1%-a-year zone at every block (2026-10-18).

Release 2's flood input (ROADMAP "Release 2 plan"). The UK's `floodMediumOrHighPct` is the share of a
borough's postcodes the Environment Agency rates Medium or High (at least 1% a year); FEMA's Special
Flood Hazard Area (`SFHA_TF = 'T'`: zones A, AE, AH, AO, V, VE ...) is the same 1%-a-year line, so this
is the share of a city's RESIDENTS (2020 blocks, scripts/bayarea_blocks.py) inside it.

FEMA maps all of its studied land, minimal-risk zone X included, so a resident in NO polygon, or in zone
D ("possible but undetermined"), has an UNKNOWN risk, not a zero one: they are counted as `unknown` and
left out of the share. A city where they are more than UNKNOWN_MAX_PCT of residents gets NO share, only the
reason (`withheld`), so it is scored without flood (Bill, 2026-10-21). That is nine Santa Clara cities, San
Jose first: its valley floor is one explicit zone D polygon, so 76% of its residents have no determination,
and the 21.6% of the rest sit mostly along the creeks FEMA did study. Neither D-as-safe (5.2%) nor that
creek-biased share is a reading of San Jose.
Points are tested even-odd over every ring of a polygon, so a hole is outside without being told.

Input: data/fema/nfhl-bayarea.esrijson.gz and its manifest, pulled from the manual US-runner workflow
(`gh run download <run> -D data/fema/`), since FEMA refuses this network. Public domain (FEMA NFHL).

THE ANCHOR (Bill, 2026-10-21: measured, as crime's 22.27 per 1,000 and road's 6.88% are): the US flood scale
is linear on CALIFORNIA's share of residents in a determined zone who are inside the 1% zone, read the same
way at every 2020 block of the state, from FEMA's county downloads for all 58 counties (fetch_fema_nfhl_counties.py
--state, one file a county under data/fema/california/counties/). It is measured one county at a time, so
memory holds one county's polygons, and refused while any county with residents is missing.

  python scripts/build_bayarea_flood.py --write         write data/us-bayarea-flood.json
  python scripts/build_bayarea_flood.py --write-state   write data/us-california-flood.json, the anchor
  python scripts/build_bayarea_flood.py --check         both files are sound (offline); and, with the FEMA
                                                        files and the block frame on disk, every share
"""

import argparse
import gzip
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / 'data' / 'fema' / 'nfhl-bayarea.esrijson.gz'
MANIFEST = REPO / 'data' / 'fema' / 'manifest.json'
OUT = REPO / 'data' / 'us-bayarea-flood.json'
STATE_DIR = REPO / 'data' / 'fema' / 'california' / 'counties'
STATE_OUT = REPO / 'data' / 'us-california-flood.json'
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


def share(residents, sfha, unknown):
    """(sfha_pct, withheld): the 1% share of residents in a determined zone, or None and the reason."""
    if residents and 100 * unknown / residents > UNKNOWN_MAX_PCT:
        return None, (f'FEMA has not determined the flood risk for {100 * unknown / residents:.0f}% of '
                      f'residents (zone D or unmapped)')
    known = residents - unknown
    return (round(100 * sfha / known, 2), None) if known else (None, 'no resident is in a determined zone')


def build(frame, features, manifest):
    polys, cells = zone_index(features)
    rows = []
    for p in _load('bayarea_blocks').cities():
        n = {'sfha': 0, 'outside': 0, 'unknown': 0}
        for lon, lat, pop in frame[p['geoid']]:
            n[classify(lon, lat, polys, cells)] += pop
        pct, withheld = share(sum(n.values()), n['sfha'], n['unknown'])
        rows.append({'geoid': p['geoid'], 'name': p['name'], 'county': p['county'],
                     'residents': sum(n.values()), 'residents_sfha': n['sfha'], 'residents_unknown': n['unknown'],
                     'sfha_pct': pct, 'withheld': withheld})
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
                   'zone D or in no polygon are unknown, counted, and left out of the share; a city where they are '
                   f'over {UNKNOWN_MAX_PCT}% of residents has no share, only the reason (withheld)',
        'cities': rows,
    }


def problems(doc, want):
    out = []
    if {r['geoid'] for r in doc['cities']} != {p['geoid'] for p in want}:
        out.append(f"coverage: {len(doc['cities'])} cities, not the {len(want)} of the places file")
    for r in doc['cities']:
        pct, withheld = share(r['residents'], r['residents_sfha'], r['residents_unknown'])
        if withheld and r['sfha_pct'] is not None:
            out.append(f"{r['name']}: a share is printed, but {withheld}; it must be withheld")
        elif r['sfha_pct'] != pct or r.get('withheld') != withheld:
            out.append(f"{r['name']}: sfha_pct is not its counts")
    return out


def state_tally(counties, points_by_county, read_county):
    """California's residents by reading, one county at a time: `counties` [(name, FIPS)], `points_by_county`
    {FIPS: [(lon, lat, residents, unit)]}, and `read_county(FIPS)` giving that county's features. A unit is the
    block's place (a city or town, by GEOID) or its county's land outside every place ('<FIPS> rest'). Returns
    the totals, each county's, and each unit's. A county holding residents but missing from `counties` fails:
    its people would drop out of the anchor unseen."""
    stray = sorted(set(points_by_county) - {f for _, f in counties})
    if stray:
        raise SystemExit(f'residents in counties outside the list: {stray}')
    total, per, units = {'sfha': 0, 'outside': 0, 'unknown': 0}, [], {}
    for name, fips in counties:
        polys, cells = zone_index(read_county(fips))
        n = {'sfha': 0, 'outside': 0, 'unknown': 0}
        for lon, lat, pop, unit in points_by_county.get(fips, ()):
            reading = classify(lon, lat, polys, cells)
            n[reading] += pop
            units.setdefault(unit, {'sfha': 0, 'outside': 0, 'unknown': 0})[reading] += pop
        per.append({'county': name, 'fips': fips, 'residents': sum(n.values()), 'residents_sfha': n['sfha'],
                    'residents_unknown': n['unknown']})
        for k in total:
            total[k] += n[k]
    return total, per, units


def anchor_of(units):
    """(anchor %, residents counted, units counted) over the units a city would be given a share for: share()'s
    rule, so a place over UNKNOWN_MAX_PCT undetermined adds nothing. Its determined residents are the creek-biased
    sample a city is withheld for (code review, 2026-10-21: pooling them read the Bay Area at 4.39% where the 41
    cities with a share read 2.85%), and an inflated anchor would read every US city safer than it is."""
    kept = [u for u in units if share(u['residents'], u['residents_sfha'], u['residents_unknown'])[1] is None]
    sfha = sum(u['residents_sfha'] for u in kept)
    known = sum(u['residents'] - u['residents_unknown'] for u in kept)
    return (round(100 * sfha / known, 2) if known else None), sum(u['residents'] for u in kept), len(kept)


def state_doc(total, per, units, files):
    rows = [{'unit': k, 'residents': sum(c.values()), 'residents_sfha': c['sfha'], 'residents_unknown': c['unknown']}
            for k, c in sorted(units.items())]
    pct, counted, n_counted = anchor_of(rows)
    known = total['sfha'] + total['outside']
    return {
        'source': 'FEMA National Flood Hazard Layer, county-wide downloads for every California county, read at '
                  'the 2020 Census block internal points',
        'licence': 'public domain (FEMA, a US government work)',
        'generator': 'scripts/build_bayarea_flood.py --write-state',
        'measure': "California's share of residents in a determined zone who are inside the SFHA (SFHA_TF = T): "
                   "the anchor of the US flood scale (Bill, 2026-10-21). Read the way a city's share is: over the "
                   "places (and each county's land outside every place) where FEMA has determined the risk for "
                   f'at least {100 - UNKNOWN_MAX_PCT:g}% of residents; a place over that is left out whole',
        'sfha_pct': pct, 'residents_counted': counted,
        'units_counted': n_counted, 'units': len(rows),
        # for comparison only, never the anchor: every determined resident pooled, withheld places included
        'sfha_pct_all_determined': round(100 * total['sfha'] / known, 2) if known else None,
        'residents': sum(total.values()), 'residents_sfha': total['sfha'], 'residents_unknown': total['unknown'],
        'fema_files': files, 'counties': per, 'by_unit': rows,
    }


def state_problems(doc, counties):
    out = []
    if [(r['county'], r['fips']) for r in doc['counties']] != list(counties):
        out.append(f"{STATE_OUT.name}: {len(doc['counties'])} counties, not the {len(counties)} of the county list")
    for k in ('residents', 'residents_sfha', 'residents_unknown'):
        if doc[k] != sum(r[k] for r in doc['counties']) or doc[k] != sum(r[k] for r in doc['by_unit']):
            out.append(f'{STATE_OUT.name}: {k} is not the sum of its counties and of its units')
    if (doc['sfha_pct'], doc['residents_counted'], doc['units_counted']) != anchor_of(doc['by_unit']):
        out.append(f'{STATE_OUT.name}: sfha_pct is not its counted units')
    if doc['residents_counted'] < doc['residents'] / 2:
        out.append(f"{STATE_OUT.name}: the anchor rests on {doc['residents_counted']:,} of {doc['residents']:,} "
                   'residents, under half of California: decide before scoring on it')
    if not doc['sfha_pct'] or not 0 < doc['sfha_pct'] < 50:
        out.append(f"{STATE_OUT.name}: an implausible anchor, {doc['sfha_pct']}%")
    return out


def read_state_county(fips):
    """One county of the --state fetch, checked against its own manifest's sha256 before it is read."""
    blob = (STATE_DIR / f'{fips}.esrijson.gz').read_bytes()
    manifest = json.loads((STATE_DIR / f'{fips}.json').read_text(encoding='utf-8'))
    if hashlib.sha256(blob).hexdigest() != manifest['sha256_gz']:
        raise SystemExit(f'{fips}.esrijson.gz is not the file its manifest describes')
    doc = json.loads(gzip.decompress(blob))
    if doc.get('fips') != fips or doc.get('spatialReference', {}).get('wkid') != 4326:
        raise SystemExit(f'{fips}.esrijson.gz: not WGS84 Esri JSON for county {fips}')
    return doc['features']


def build_state(blocks, counties):
    missing = [f for _, f in counties if not (STATE_DIR / f'{f}.esrijson.gz').exists()]
    if missing:
        raise SystemExit(f'{len(missing)} of {len(counties)} counties are not on disk ({",".join(missing)}): '
                         f'fetch them with the workflow (scope california, only {",".join(missing)})')
    points = {}
    for block, place, pop, lon, lat in blocks.pl_blocks():
        if pop > 0:
            points.setdefault(block[:5], []).append((lon, lat, pop, place or f'{block[:5]} rest'))
    files = {f: json.loads((STATE_DIR / f'{f}.json').read_text(encoding='utf-8'))['sha256_gz'] for _, f in counties}
    return state_doc(*state_tally(counties, points, read_state_county), files)


def read_raw():
    doc = json.loads(gzip.decompress(RAW.read_bytes()))
    if doc.get('format') != 'esrijson' or doc.get('spatialReference', {}).get('wkid') != 4326:
        raise SystemExit(f'{RAW.name}: not WGS84 Esri JSON')
    return doc['features'], json.loads(MANIFEST.read_text(encoding='utf-8'))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--write', action='store_true')
    g.add_argument('--write-state', action='store_true', help='measure the anchor (all 58 counties on disk)')
    g.add_argument('--check', action='store_true')
    a = ap.parse_args()
    blocks = _load('bayarea_blocks')
    fetcher = _load('fetch_fema_nfhl_counties')
    ca = fetcher.state_counties(json.loads(fetcher.CA_COUNTIES.read_text(encoding='utf-8')))
    if a.write_state:
        doc = build_state(blocks, ca)
        STATE_OUT.write_text(json.dumps(doc, indent=1) + '\n', encoding='utf-8', newline='\n')
        print(f"wrote {STATE_OUT.relative_to(REPO)}: California {doc['sfha_pct']}% (the anchor), over "
              f"{doc['units_counted']:,} of {doc['units']:,} places and county remainders holding "
              f"{doc['residents_counted']:,} of {doc['residents']:,} residents; every determined resident pooled "
              f"would read {doc['sfha_pct_all_determined']}%")
        for f in state_problems(doc, ca):
            print('  WARNING: ' + f)
        return 0
    if a.write:
        doc = build(blocks.blocks(), *read_raw())
        OUT.write_text(json.dumps(doc, indent=1) + '\n', encoding='utf-8', newline='\n')
        top = sorted((r for r in doc['cities'] if r['sfha_pct'] is not None), key=lambda r: -r['sfha_pct'])
        print(f"wrote {OUT.relative_to(REPO)}: highest " + ', '.join(f"{r['name']} {r['sfha_pct']}%" for r in top[:5]))
        held = [r['name'] for r in doc['cities'] if r['withheld']]
        print(f'  withheld ({len(held)}): ' + ', '.join(held))
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
    if STATE_OUT.exists():
        state = json.loads(STATE_OUT.read_text(encoding='utf-8'))
        failures += state_problems(state, ca)
        whole = all((STATE_DIR / f'{f}.esrijson.gz').exists() for _, f in ca)
        if whole and blocks.PL_RAW.exists():
            if build_state(blocks, ca) != state:
                failures.append(f'{STATE_OUT.name} is not what the 58 county files give (re-run --write-state)')
            else:
                print(f"  FEMA files     {STATE_OUT.name} == {len(ca)} county files at every block "
                      f"(California {state['sfha_pct']}%)")
        else:
            print("INCONCLUSIVE for the anchor's value: not every county file, or the block frame, is on disk")
    else:
        print(f'  {STATE_OUT.name} not built yet: the US flood scale has no anchor, so flood is not scored')
    if failures:
        print('RESULT: FAIL')
        for f in failures:
            print('  ' + f)
        return 1
    print(f"RESULT: PASS ({len(doc['cities'])} cities)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
