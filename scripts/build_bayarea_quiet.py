"""A Bay Area city's aircraft band, from the fitted geometry, where its residents live (2026-10-22).

Release 2's Quiet Skies input at the city level. A city's Quiet Skies comes from its `impact` band
(IMPACT_TO_QUIET), as a New York borough's and a UK borough's do. New York's bands are derived by
scripts/build_nyc_impact.py over ZIP areas; the Bay Area's are derived the same way over the 2020 resident
frame (scripts/bayarea_blocks.py), the frame its road, flood and transport inputs use: each resident block is
scored by the Lambda's own calc_postcode_quiet at its internal point (the US-QUIET-BAYAREA fit, held to SFO's
and San Jose's monitors by measure_us_quiet_yardstick.py), and the city's figure is the mean weighted by
residents, so the airport's own land and the bay do not count as people.

The band is the QUIETEST one whose IMPACT_TO_QUIET value does not exceed that mean, so a city never publishes
quieter than its own estimate (Bill's rule for New York, 2026-10-16, after the audit). The mean is published
ROUNDED DOWN to two places, toward loud, and the band is taken from the published figure: rounding down can
never lift a mean over a band's edge, so the band is the unrounded mean's and every band reproduces from the
file.

The fit lives in app.py and moves when it is refitted, so the file carries a fingerprint of the
US-QUIET-BAYAREA block and, per city, one probe (its most populous block's point and the estimate there).
Offline, --check re-scores the 50 probes with the Lambda as it now stands: a refit, or a change to
calc_postcode_quiet itself, that has not been re-derived here reds without the Census frame on disk.

  python scripts/build_bayarea_quiet.py --write   write data/us-bayarea-quiet.json
  python scripts/build_bayarea_quiet.py --check   bands against their means, the fingerprint and every probe
                                                  against the Lambda (offline); and, with the Census frame on
                                                  disk, every mean against the blocks
"""

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'backend' / 'lambdas' / 'score'))
import app  # noqa: E402

LAMBDA = REPO / 'backend' / 'lambdas' / 'score' / 'app.py'
OUT = REPO / 'data' / 'us-bayarea-quiet.json'
MARKER = 'US-QUIET-BAYAREA'


def _load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / 'scripts' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fingerprint():
    """sha256 of the generated geometry block, line endings aside (a checkout may rewrite them)."""
    text = LAMBDA.read_text(encoding='utf-8').replace('\r\n', '\n')
    start, end = text.find(f'# {MARKER}:START'), text.find(f'# {MARKER}:END')
    if start < 0 or end < start:
        raise SystemExit(f'{LAMBDA.name}: no {MARKER} block')
    return hashlib.sha256(text[start:end].encode('utf-8')).hexdigest()


def quiet_at(lat, lon):
    q = app.calc_postcode_quiet(lat, lon, 'bayarea', raster_lden=None)
    if q is None:
        raise SystemExit("calc_postcode_quiet has no geometry for 'bayarea'")
    return q


def floor2(x):
    """Down to two places, toward loud. The 1e-9 keeps a mean that IS on a figure (5.0) from flooring past it."""
    return math.floor(x * 100 + 1e-9) / 100


def band_of(mean):
    # 'severe' is 0.0, so some band always qualifies
    return max((k for k, v in app.IMPACT_TO_QUIET.items() if v <= mean), key=lambda k: app.IMPACT_TO_QUIET[k])


def build(frame, cities):
    rows = []
    for c in sorted(cities, key=lambda c: c['name']):
        blocks = frame[c['geoid']]
        people = sum(p for *_, p in blocks)
        if not blocks or not people:
            raise SystemExit(f"{c['name']}: no resident block")
        mean = floor2(sum(p * quiet_at(lat, lon) for lon, lat, p in blocks) / people)
        lon, lat, _ = max(blocks, key=lambda b: (b[2], b[1], b[0]))
        rows.append({'geoid': c['geoid'], 'name': c['name'], 'county': c['county'], 'residents': people,
                     'quiet_mean': mean, 'band': band_of(mean),
                     'probe': {'lat': lat, 'lon': lon, 'quiet': quiet_at(lat, lon)}})
    return {
        'source': "the Lambda's calc_postcode_quiet (the US-QUIET-BAYAREA fit to SFO's and San Jose's monitors) at "
                  'every 2020 Census resident block of the 50 cities, weighted by population',
        'generator': 'scripts/build_bayarea_quiet.py --write',
        'measure': 'mean Quiet Skies of a resident (0-10), rounded down to two places; the band is the quietest '
                   'whose IMPACT_TO_QUIET value does not exceed it (never quieter than the estimate)',
        'impact_to_quiet': app.IMPACT_TO_QUIET,
        'geometry_sha256': fingerprint(),
        'cities': rows,
    }


def problems(doc, want):
    out = []
    if sorted(r['name'] for r in doc['cities']) != sorted(c['name'] for c in want):
        out.append('the file does not cover exactly the 50 cities of data/us-bayarea-places.json')
    if doc['impact_to_quiet'] != app.IMPACT_TO_QUIET:
        out.append("IMPACT_TO_QUIET has changed since the file was written (re-run --write)")
    if doc['geometry_sha256'] != fingerprint():
        out.append(f'the {MARKER} block has changed since the file was written: refitted? (re-run --write)')
    for r in doc['cities']:
        if not 0 <= r['quiet_mean'] <= 10 or floor2(r['quiet_mean']) != r['quiet_mean']:
            out.append(f"{r['name']}: quiet_mean {r['quiet_mean']} is not a 0-10 figure to two places")
        elif band_of(r['quiet_mean']) != r['band']:
            out.append(f"{r['name']}: band {r['band']!r} is not the band of {r['quiet_mean']}")
        p = r['probe']
        if quiet_at(p['lat'], p['lon']) != p['quiet']:
            out.append(f"{r['name']}: the Lambda now reads {quiet_at(p['lat'], p['lon'])} at its probe, not "
                       f"{p['quiet']} (re-run --write)")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--write', action='store_true')
    g.add_argument('--check', action='store_true')
    a = ap.parse_args()
    blocks = _load('bayarea_blocks')
    if a.write:
        doc = build(blocks.blocks(), blocks.cities())
        OUT.write_text(json.dumps(doc, indent=1) + '\n', encoding='utf-8', newline='\n')
        tally = {}
        for r in doc['cities']:
            tally[r['band']] = tally.get(r['band'], 0) + 1
        print(f'wrote {OUT.relative_to(REPO)}: ' + ', '.join(f'{k} {tally[k]}' for k in app.IMPACT_TO_QUIET if k in tally))
        for f in problems(doc, blocks.cities()):
            print('  WARNING: ' + f)
        return 0
    doc = json.loads(OUT.read_text(encoding='utf-8'))
    failures = problems(doc, blocks.cities())
    if blocks.PL_RAW.exists():
        if build(blocks.blocks(), blocks.cities()) != doc:
            failures.append(f'{OUT.name} is not what the fit gives at every block (re-run --write)')
        else:
            print(f'  blocks         {OUT.name} == the fit at every resident block')
    else:
        print('INCONCLUSIVE for values: the Census block frame is not on disk; bands, fingerprint and probes checked')
    if failures:
        print('RESULT: FAIL')
        for f in failures:
            print('  ' + f)
        return 1
    print(f"RESULT: PASS ({len(doc['cities'])} cities)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
