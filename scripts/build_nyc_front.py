"""New York on the front page (Bill, 2026-10-06: "show on the main screen instead of
going to the full map").

The front page draws a city from three things: its outlines, its routes and a noise
picture, and opens a card per council area from the open-data CSV. New York is not in
that CSV, deliberately (it is UK open data, and New York's figures are curated, not
measured to the UK's standard), so this script writes the one file the front page needs:

    data/us-nyc.json   the noise picture's frame and file, and one row per borough in the
                       open-data CSV's own row shape, so the card reads it unchanged

and the picture itself, data/aircraft-noise-nyc-laeq.png. The outlines are the map's
data/nyc-boroughs.json and the routes the FAA's data/us-flight-procedures.json (JFK,
LaGuardia, Newark and Teterboro), both already deployed.

The ROWS come from the score engine itself (resolve_query), so a card cannot show a
score /v1/score would not. The PICTURE is the US DOT's National Transportation Noise Map
2022 (aviation), fetched exactly as the Bay Area page's is (build_bay_area_page.build_noise,
which refuses any colour the legend has no band for).

    python scripts/build_nyc_front.py --fetch   network: the noise picture, then --write
    python scripts/build_nyc_front.py --write   the rows (and frame) from the engine
    python scripts/build_nyc_front.py --check   blocking: the file says what the engine says,
                                                and the picture is the one the file names
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'backend' / 'lambdas' / 'score'))

import build_bay_area_page as bay  # noqa: E402  (shares the frame and picture code)
import build_bayarea_map_data as mapdata  # noqa: E402  (the route records, one derivation for both US cities)

OUT = ROOT / 'data' / 'us-nyc.json'
# New York's front-page lines (2026-10-07): finals, departures cut at 30 km and the coded
# arrivals, from the SAME functions the Bay Area's routes file and the /bay-area/ page use
# (bay.routes, bay.arrival_routes, mapdata.route_records). The front page drew New York's
# finals and departures from the raw FAA record, whole, and no arrivals at all.
ROUTES_OUT = ROOT / 'data' / 'us-nyc-routes.json'
NYC_AIRPORTS = ('JFK', 'LGA', 'EWR', 'TEB')
NYC_AIRPORT_NAMES = {'JFK': 'JFK', 'LGA': 'LaGuardia', 'EWR': 'Newark', 'TEB': 'Teterboro'}
PICTURE = ROOT / 'data' / 'aircraft-noise-nyc-laeq.png'
OUTLINES = ROOT / 'data' / 'nyc-boroughs.json'
PAD_DEG = 0.02  # the picture is clipped to the boroughs' outline on the map
CITY = 'nyc'
CITY_NAME = 'New York City'

# Said on every New York card, because the card's look is the UK's and its figures are
# not: they are the API's own source lines in short (resolve_query's "sources").
NOTE = (
    "New York's figures are curated from public city sources (NYPD CompStat for crime, "
    'borough median sale prices in dollars), not measured to the standard of the UK '
    "figures, and its scores are not comparable with the UK's. The map draws the FAA's "
    'published routes for JFK, LaGuardia, Newark and Teterboro; the Quiet skies score is '
    "the API's band from JFK and LaGuardia."
)


def slug(name: str) -> str:
    """The front page's slug(): lower case, runs of anything else to one hyphen."""
    out, dash = [], False
    for ch in name.lower():
        if ch.isalnum():
            out.append(ch)
            dash = False
        elif not dash and out:
            out.append('-')
            dash = True
    return ''.join(out).strip('-')


def frame() -> bay.Frame:
    """The picture's box: the five boroughs' outlines, padded, in whole tile-zoom pixels."""
    gj = json.loads(OUTLINES.read_text(encoding='utf-8'))
    lons, lats = [], []

    def walk(c):
        if isinstance(c[0], (int, float)):
            lons.append(c[0])
            lats.append(c[1])
        else:
            for x in c:
                walk(x)

    for f in gj['features']:
        walk(f['geometry']['coordinates'])
    x0, y1 = bay.global_px(min(lons) - PAD_DEG, min(lats) - PAD_DEG)
    x1, y0 = bay.global_px(max(lons) + PAD_DEG, max(lats) + PAD_DEG)
    return bay.Frame((math.floor(x0), math.floor(y0), math.ceil(x1), math.ceil(y1)))


def rows() -> list[dict]:
    import app  # noqa: PLC0415  (the score Lambda: the one holder of New York's figures)

    out = []
    for borough in sorted(app.CITIES[CITY]['boroughs']):
        body, status = app.resolve_query({'borough': borough, 'city': CITY})
        if status != 200 or not isinstance(body.get('score'), (int, float)):
            raise SystemExit(f'{CITY}/{borough} did not score ({status}); refusing a partial file')
        comp, ctx = body.get('components') or {}, body.get('context') or {}
        rec = app.CITIES[CITY]['boroughs'][borough]
        out.append({
            'city': CITY,
            'city_name': CITY_NAME,
            'borough': borough,
            'score': body['score'],
            'quiet': comp.get('quiet', ''),
            'afford': comp.get('afford', ''),
            'growth': comp.get('growth', ''),
            'live': comp.get('live', ''),
            'env': comp.get('env', ''),  # not scored for New York: the card says "not scored"
            'methodology_version': body.get('methodologyVersion', ''),
            'avg_price_usd': ctx.get('avgPriceUsd', ''),
            'price_trend_pct': ctx.get('priceTrendPct', ''),
            'crime_per_1000': rec.get('crimeRate', ''),
            'area_page': f'/area/{CITY}/{slug(borough)}/',
            'note': NOTE,
        })
    return out


def document(picture_sha: str) -> dict:
    fr = frame()
    return {
        'generator': 'scripts/build_nyc_front.py',
        'frame': {'zoom': bay.TILE_ZOOM, 'px': [fr.x0, fr.y0, fr.x1, fr.y1]},
        'noise': {
            'file': PICTURE.name,
            'publisher': 'US DOT Bureau of Transportation Statistics, National Transportation Noise Map 2022 (aviation)',
            'sha256': picture_sha,
        },
        'rows': rows(),
    }


def routes_text() -> tuple[str, list[dict]]:
    """data/us-nyc-routes.json's text, and its records (for the counts printed)."""
    record = json.loads(mapdata.RECORD.read_text(encoding='utf-8'))
    approaches, departures, _ = bay.routes(record, NYC_AIRPORTS)
    arrivals = bay.arrival_routes(record, NYC_AIRPORTS)
    records = mapdata.route_records({'approaches': approaches, 'departures': departures, 'arrivals': arrivals}, record)
    doc = mapdata.routes_doc(
        records,
        record,
        NYC_AIRPORTS,
        NYC_AIRPORT_NAMES,
        'scripts/build_nyc_front.py --write; the same derivation as data/us-bayarea-routes.json',
    )
    return mapdata.render(doc), records


def dump(doc: dict) -> str:
    return json.dumps(doc, indent=1, ensure_ascii=False) + '\n'


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--fetch', action='store_true')
    g.add_argument('--write', action='store_true')
    g.add_argument('--check', action='store_true')
    a = ap.parse_args()

    if a.fetch:
        png, tiles = bay.build_noise(frame())
        PICTURE.write_bytes(png)
        print(f'wrote {PICTURE.name}: {len(png):,} bytes from {tiles} tiles')
        if tiles == 0:
            raise SystemExit('no tile read: an empty picture is not "no noise"; nothing more written')
    if a.fetch or a.write:
        if not PICTURE.exists():
            raise SystemExit(f'{PICTURE.name} is missing: run --fetch first')
        doc = document(hashlib.sha256(PICTURE.read_bytes()).hexdigest())
        OUT.write_text(dump(doc), encoding='utf-8', newline='\n')
        print(f'wrote {OUT.name}: {len(doc["rows"])} boroughs, frame {doc["frame"]["px"]}')
        text, records = routes_text()
        ROUTES_OUT.write_text(text, encoding='utf-8', newline='\n')
        kinds = {k: sum(r['kind'] == k for r in records) for k in ('final', 'departure', 'arrival')}
        print(f'wrote {ROUTES_OUT.name}: {kinds}')
        return 0

    # --check: the file is what the engine and the picture say, byte for byte.
    if not OUT.exists() or not PICTURE.exists():
        print(f'FAIL: {OUT.name} or {PICTURE.name} is missing')
        return 1
    have = OUT.read_text(encoding='utf-8')
    want = dump(document(hashlib.sha256(PICTURE.read_bytes()).hexdigest()))
    if have != want:
        old = {r['borough']: r for r in json.loads(have).get('rows', [])}
        new = {r['borough']: r for r in json.loads(want)['rows']}
        for b in sorted(set(old) | set(new)):
            if old.get(b) != new.get(b):
                print(f'  differs: {b}: file {old.get(b, {}).get("score")} vs engine {new.get(b, {}).get("score")}')
        print(f'FAIL: {OUT.name} is stale against the engine or the picture; run --write')
        return 1
    text, records = routes_text()
    if not ROUTES_OUT.exists() or ROUTES_OUT.read_text(encoding='utf-8') != text:
        print(f'FAIL: {ROUTES_OUT.name} is stale against the FAA record; run --write')
        return 1
    if not any(r['kind'] == 'arrival' for r in records):
        print(f'FAIL: {ROUTES_OUT.name} holds no arrival: the derivation found nothing to draw')
        return 1
    n = len(json.loads(have)['rows'])
    if n < 5:
        print(f'FAIL: {n} boroughs, expected all five')
        return 1
    print(f'ok: {OUT.name} matches the engine for {n} boroughs, {PICTURE.name} is the picture it names, '
          f'and {ROUTES_OUT.name} is a fresh derivation ({len(records)} routes)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
