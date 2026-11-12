"""The Bay Area's scores on the front page (Bill, 2026-11-07: "score the Bay Area cards too").

The front page opens a card for each Bay Area city from the outlines and routes it already loads; until this
release the card said "Not scored". It reads one more file, written here:

    data/us-bayarea-front.json   one row per city, in the shape New York's rows take (scripts/build_nyc_front.py),
                                 so the card reads the score and its five components the same way, plus the
                                 city's inputs in words, each with its source and year, and the US-scales line

The ROWS come from the score engine itself (resolve_query, balanced weighting, as every front-page card), so a
card cannot show a score /v1/score would not. The words for the inputs, their sources and years, and the
US-scales sentence come from scripts/build_bayarea_records.py, the one holder the full map's card and the area
pages read too. Nothing here is typed.

    python scripts/build_bayarea_front.py --write   the rows from the engine
    python scripts/build_bayarea_front.py --check   blocking, offline: the file says what the engine says
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'backend' / 'lambdas' / 'score'))

import build_bayarea_records as records  # noqa: E402

OUT = ROOT / 'data' / 'us-bayarea-front.json'
CITY = 'bayarea'


def slug(name: str) -> str:
    """The front page's slug() and build_area_pages.slug(): lower case, runs of anything else to one hyphen."""
    out, dash = [], False
    for ch in name.lower():
        if ch.isalnum():
            out.append(ch)
            dash = False
        elif not dash and out:
            out.append('-')
            dash = True
    return ''.join(out).strip('-')


def document() -> dict:
    import app  # noqa: PLC0415  (the score Lambda: the one holder of the Bay Area's records and scores)

    anchors, rows = records.records()
    sources = records.input_sources()
    held = app.CITIES[CITY]['boroughs']
    if dict(rows) != held:
        raise SystemExit("the score Lambda's Bay Area records are not what the readers' files give: "
                         'run scripts/build_bayarea_records.py --write first')
    out = []
    for name, rec in rows:
        body, status = app.resolve_query({'borough': name, 'city': CITY})
        if status != 200 or not isinstance(body.get('score'), (int, float)):
            raise SystemExit(f'{CITY}/{name} did not score ({status}); refusing a partial file')
        comp, ctx = body.get('components') or {}, body.get('context') or {}
        out.append({
            'city': CITY,
            'city_name': app.CITIES[CITY]['name'],
            'borough': name,
            'county': rec['county'],
            'score': body['score'],
            'quiet': comp.get('quiet', ''),
            'afford': comp.get('afford', ''),
            'growth': comp.get('growth', ''),  # not scored for the Bay Area: the card says "not scored"
            'live': comp.get('live', ''),
            'env': comp.get('env', ''),
            'methodology_version': body.get('methodologyVersion', ''),
            'withheld': sorted(rec.get('withheld') or {}),
            'facts': [list(f) for f in records.input_facts(name, rec, anchors, sources, app.US_PRICE_TOP_CODE,
                                                           ctx.get('crimeNote'))],
            'area_page': f'/area/{CITY}/{slug(name)}/',
        })
    return {
        'generator': 'scripts/build_bayarea_front.py',
        'weighting': 'balanced',
        'us_scales': records.us_scales(len(rows)),
        'growth_not_scored': app.CITIES[CITY]['growthNotScored'],
        'rows': out,
    }


def dump(doc: dict) -> str:
    return json.dumps(doc, indent=1, ensure_ascii=False) + '\n'


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--write', action='store_true')
    g.add_argument('--check', action='store_true')
    a = ap.parse_args()
    want = dump(document())
    if a.write:
        OUT.write_text(want, encoding='utf-8', newline='\n')
        print(f'wrote {OUT.name}: {len(json.loads(want)["rows"])} cities')
        return 0
    if not OUT.exists():
        print(f'FAIL: {OUT.name} is missing; run --write')
        return 1
    have = OUT.read_text(encoding='utf-8').replace('\r\n', '\n')
    if have != want:
        old = {r['borough']: r for r in json.loads(have).get('rows', [])}
        new = {r['borough']: r for r in json.loads(want)['rows']}
        for b in sorted(set(old) | set(new)):
            if old.get(b) != new.get(b):
                print(f'  differs: {b}: file {old.get(b, {}).get("score")} vs engine {new.get(b, {}).get("score")}')
        print(f'FAIL: {OUT.name} is stale against the engine or the readers; run --write')
        return 1
    print(f'ok: {OUT.name} matches the engine for {len(json.loads(have)["rows"])} cities')
    return 0


if __name__ == '__main__':
    sys.exit(main())
