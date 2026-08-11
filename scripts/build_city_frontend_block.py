"""Emit a city's frontend constants block from the score Lambda.

WHY THIS EXISTS RATHER THAN COPY-PASTE
--------------------------------------
The two holders describe the same geometry in two different dialects, and every
difference between them has already caused a production defect:

  * the Lambda's flight-path key is `coords`, the frontend's is `coordinates`.
    Porting a block across without renaming throws
    `Cannot read properties of undefined (reading 'map')` and draws no
    corridors. **This bit five cities on 2026-08-10**, and was invisible until a
    separate `center` bug was fixed, because the first exception aborted the
    render before the second could fire.
  * the Lambda stores `(lat, lon)`, the frontend stores `[lon, lat]`. Swapping
    them does not throw - it silently draws a corridor in the wrong hemisphere.
  * `avgPrice` becomes `avg_price`.

So the mapping is done once, here, by a script that reads the Lambda directly.
A city added by hand can get any of the three wrong; a city added by this
cannot.

The block still has to be PASTED into index.html and the editorial CITY_DATA
entry written by hand - legend copy is a provenance claim and is deliberately
not generated. `--insert` does the paste, before the anchor comment.

Usage
-----
    python scripts/build_city_frontend_block.py --city leicester
    python scripts/build_city_frontend_block.py --city leicester --insert
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend' / 'lambdas' / 'score'))
import app  # noqa: E402

SITE = Path('index.html')
# Everything this script writes goes immediately above this line, which is the
# first thing after the per-city constants in the current file.
ANCHOR = '      const MANCHESTER_AIRPORTS = ['


def js_num(x):
    """Render a float the way the existing blocks do - no trailing zeros."""
    s = f'{x:.6f}'.rstrip('0').rstrip('.')
    return s if s not in ('', '-') else '0'


def block(city: str) -> str:
    up = city.upper()
    cfg = app.CITIES[city]
    geo = app.CITY_GEOMETRY[city]
    out = [f'      const {up}_BOROUGH_DATA_RAW = {{']
    for borough, bd in cfg['boroughs'].items():
        out.append(
            f"          '{borough}': {{ impact: '{bd['impact']}', "
            f"avg_price: {bd['avgPrice']}, trend: {bd['trend']} }},"
        )
    out.append('      };')
    out.append(f'      let {up}_BOROUGH_EXTRA = {{}};')
    out.append(f'      const {up}_AREA_MAP = {{}};')
    out.append(f'      const {up}_NEIGHBOURHOOD_DETAIL = {{}};')
    # build_city_neighbourhoods.py --write-index rewrites BETWEEN these markers.
    # They must exist before it runs or it reports the city as unknown.
    out.append(f'      /* {up}-NEIGHBOURHOODS:START */')
    out.append(f'      const {up}_NEIGHBOURHOOD_VINTAGE = "2025";')
    out.append(f'      const {up}_NEIGHBOURHOOD_MIN_SALES = 30;')
    out.append(f'      /* {up}-NEIGHBOURHOODS:END */')
    out.append(f'      const {up}_STATIONS = [];')

    out.append(f'      const {up}_AIRPORTS = [')
    for ap in geo['airports']:
        out.append(
            f"        {{ code: '{ap['code']}', name: '{ap['name']}', "
            f"coords: [{js_num(ap['lon'])}, {js_num(ap['lat'])}] }},"
        )
    out.append('      ];')

    out.append(f'      const {up}_FLIGHT_PATHS = [')
    for p in geo['paths']:
        # coords -> coordinates, and (lat, lon) -> [lon, lat]. Both, every time.
        pts = ', '.join(f'[{js_num(lon)}, {js_num(lat)}]' for lat, lon in p['coords'])
        freq = f", freq: '{p['freq']}'" if p.get('freq') else ''
        out.append(
            f"        {{ name: '{p['name']}', airport: '{p['airport']}', "
            f"type: '{p['type']}'{freq}, coordinates: [{pts}] }},"
        )
    out.append('      ];')
    out.append('')
    return '\n'.join(out) + '\n'


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--city', required=True, choices=sorted(app.CITIES))
    ap.add_argument('--insert', action='store_true', help='splice into index.html')
    args = ap.parse_args()

    text = block(args.city)
    if not args.insert:
        print(text)
        return 0

    # newline='' on both sides: read_text/write_text translate line endings on
    # Windows and would rewrite all 11,163 of index.html's in passing.
    with open(SITE, encoding='utf-8', newline='') as fh:
        src = fh.read()
    if f'const {args.city.upper()}_BOROUGH_DATA_RAW' in src:
        print(f'{args.city} already present in index.html; nothing written')
        return 0
    if ANCHOR not in src:
        raise SystemExit(f'anchor not found in index.html: {ANCHOR!r}')
    i = src.index(ANCHOR)
    with open(SITE, 'w', encoding='utf-8', newline='') as fh:
        fh.write(src[:i] + text + src[i:])
    print(f'inserted {args.city} constants ({len(text.splitlines())} lines) before the anchor')
    return 0


if __name__ == '__main__':
    sys.exit(main())
