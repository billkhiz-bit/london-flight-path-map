"""Road noise where the Bay Area's residents live: BTS's 2022 road noise map at every block (2026-10-18).

Release 2's road-noise input (ROADMAP "Release 2 plan"). The UK's `roadNoiseAboveWhoPct` is the share of
a borough's postcodes at or above WHO's 53 dB Lden on DEFRA's road map; this is the share of a city's
RESIDENTS (2020 blocks, scripts/bayarea_blocks.py) inside BTS's band that holds WHO's 53 dB.

BTS publishes the 2022 road map (highway traffic of 2022/23, a 24-hour LAeq on a 30 m grid) as tiles
only, but unlike its aviation layer the road service carries a LEGEND: seven bands, 45-49.9 ... > 90 dB,
in exactly the colours of the site's NOISE_SCALE_BTS. A pixel is read as its band; unpainted is below
45 dB. Under BTS's flat-day model Lden = LAeq + 6.4 dB, so WHO's 53 dB Lden is about 46.6 dB LAeq, inside
the 45-49.9 band, not on an edge: the share counts from 45 dB (Lden about 51), the LOUDER side, as Bill
ruled for New York's bands. BTS: the map is "simplified noise modeling" and "should not be used to
evaluate noise levels in individual locations", so it is a city share, never a per-address figure.

Licence: a US government work (BTS, USDOT). Credit "USDOT Bureau of Transportation Statistics".

  python scripts/build_bayarea_road.py --fetch   the legend and every zoom-12 tile holding a block
                                                 (about 60 PNGs) into gitignored data/bts-road-2022/
  python scripts/build_bayarea_road.py --fetch-state  every zoom-12 tile holding a CALIFORNIA resident
                                                 (4,499), for the US scale's anchor (Bill, 2026-10-18)
  python scripts/build_bayarea_road.py --write   write data/us-bayarea-road.json
  python scripts/build_bayarea_road.py --check   the file is sound (offline); and, with the tiles and
                                                 the block frame on disk, every share against them
"""

import argparse
import base64
import importlib.util
import io
import json
import math
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SERVICE = 'https://tiles.arcgis.com/tiles/xOi1kZaI0eWDREZv/arcgis/rest/services/NTAD_Noise_2022_CONUS_road/MapServer'
RAW = REPO / 'data' / 'bts-road-2022'
OUT = REPO / 'data' / 'us-bayarea-road.json'
# The service lists 24 levels but CACHES only to 12: 13 and 14 answer 404 even over US-101 (measured
# 2026-10-18), so a 404 is "not cached", never "quiet", and fails the fetch. Level 12 is about 30 m a
# pixel at the Bay Area's latitude, BTS's own grid, so a point reads its own cell.
ZOOM = 12
MIN_ZOOM = 6  # a 404 is proven empty by climbing to the first parent that answers, never past this
TILE = 256
COUNT_FROM_DB = 45  # the band holding WHO's 53 dB Lden (46.6 dB LAeq); see the docstring
PAUSE_S = 0.05
UA = {'User-Agent': 'Sky Score data fetch (skyscore.co.uk; public-domain BTS noise map)'}


def _load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / 'scripts' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tile_of(lon, lat, z=ZOOM):
    """(tile x, tile y, pixel x, pixel y) in Web Mercator, as the service tiles it."""
    n = TILE * 2 ** z
    gx = (lon + 180) / 360 * n
    s = math.sin(math.radians(lat))
    gy = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return int(gx // TILE), int(gy // TILE), int(gx % TILE), int(gy % TILE)


def legend_bands():
    """{(r, g, b): lower dB} from the service's own legend, held equal to the site's NOISE_SCALE_BTS."""
    from PIL import Image  # noqa: PLC0415
    doc = json.loads((RAW / 'legend.json').read_text(encoding='utf-8'))
    bands = {}
    for layer in doc['layers']:
        for item in layer.get('legend', []):
            label = item.get('label', '')
            if not label:
                continue
            low = float(label.split()[-1] if label.startswith('>') else label.split()[0])
            im = Image.open(io.BytesIO(base64.b64decode(item['imageData']))).convert('RGB')
            bands[im.getpixel((im.width // 2, im.height // 2))] = int(low)
    site = {(int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)): db
            for db, c in _load('check_noise_legend').scale_from_index('NOISE_SCALE_BTS')}
    if bands != site:
        raise SystemExit(f'the road legend {sorted(bands.items(), key=lambda kv: kv[1])} is not NOISE_SCALE_BTS')
    return bands


def needed_tiles(frame):
    return sorted({tile_of(lon, lat)[:2] for pts in frame.values() for lon, lat, _ in pts})


def fetch(frame):
    RAW.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(urllib.request.Request(f'{SERVICE}/legend?f=json', headers=UA), timeout=60) as r:  # noqa: S310
        (RAW / 'legend.json').write_bytes(r.read())
    tiles = needed_tiles(frame)
    got = 0
    for tx, ty in tiles:
        dest = RAW / f'{ZOOM}_{tx}_{ty}.png'
        if dest.exists():
            continue
        req = urllib.request.Request(f'{SERVICE}/tile/{ZOOM}/{ty}/{tx}', headers=UA)
        with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 - fixed https service
            body = r.read()
        if not body.startswith(b'\x89PNG'):
            raise SystemExit(f'tile {ZOOM}/{ty}/{tx}: not a PNG ({body[:60]!r})')
        dest.write_bytes(body)
        got += 1
        time.sleep(PAUSE_S)
    print(f'{len(tiles):,} tiles needed, {got:,} fetched, the rest already on disk')


def _tile(z, x, y, fetch):
    """A cached tile's path, or None where the service answered 404 (recorded, so it is asked once)."""
    path, miss = RAW / f'{z}_{x}_{y}.png', RAW / f'{z}_{x}_{y}.404'
    if path.exists():
        return path
    if miss.exists():
        return None
    if not fetch:
        raise SystemExit(f'{path.name} is not on disk (run --fetch-state)')
    try:
        with urllib.request.urlopen(urllib.request.Request(f'{SERVICE}/tile/{z}/{y}/{x}', headers=UA),  # noqa: S310
                                    timeout=60) as r:
            body = r.read()
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        miss.write_text('404\n', encoding='utf-8')
        return None
    finally:
        time.sleep(PAUSE_S)
    if not body.startswith(b'\x89PNG'):
        raise SystemExit(f'tile {z}/{y}/{x}: not a PNG ({body[:60]!r})')
    path.write_bytes(body)
    return path


def _area_painted(z, x, y, x0, y0, size, fetch):
    """Whether tile (z, x, y) paints anything in its square [x0, x0 + size), climbing parents through 404s:
    the cache skips blank tiles, so a 404 is EMPTY only when the first parent that answers paints nothing there."""
    from PIL import Image  # noqa: PLC0415
    path = _tile(z, x, y, fetch)
    if path is None:
        if z <= MIN_ZOOM:
            raise SystemExit(f'no tile answers over {z}/{y}/{x} down to zoom {MIN_ZOOM}: not cached, not quiet')
        return _area_painted(z - 1, x // 2, y // 2, (x % 2) * 128 + x0 // 2, (y % 2) * 128 + y0 // 2,
                             max(1, size // 2), fetch)
    return any(px[3] for px in Image.open(path).convert('RGBA').crop((x0, y0, x0 + size, y0 + size)).getdata())


def _state_by_tile():
    """{(tile x, tile y): [(pixel x, pixel y, residents)]} for every California block with residents."""
    out = {}
    for _, _, pop, lon, lat in _load('bayarea_blocks').pl_blocks():
        if pop > 0:
            tx, ty, px, py = tile_of(lon, lat)
            out.setdefault((tx, ty), []).append((px, py, pop))
    return out


def _empty(tx, ty, fetch):
    """A zoom-12 404, proven empty by its parent, or the run fails: a 404 under paint is unexplained."""
    if _area_painted(ZOOM - 1, tx // 2, ty // 2, (tx % 2) * 128, (ty % 2) * 128, 128, fetch):
        raise SystemExit(f'tile {ZOOM}/{ty}/{tx}: 404, yet its parent paints that quarter; not cached, not quiet')
    return True


def fetch_state():
    by_tile = _state_by_tile()
    for i, (tx, ty) in enumerate(sorted(by_tile)):
        if _tile(ZOOM, tx, ty, fetch=True) is None:
            _empty(tx, ty, fetch=True)
        if i % 500 == 499:
            print(f'  {i + 1:,} of {len(by_tile):,} tiles', flush=True)
    print(f'{len(by_tile):,} tiles hold California residents; all on disk')


def state_share():
    """California's share of residents at or above COUNT_FROM_DB: the anchor of the US road scale (Bill,
    2026-10-18: a US scale anchored on a published reference, as crime is on the state rate)."""
    from PIL import Image  # noqa: PLC0415
    bands = legend_bands()
    people = loud = empty = 0
    for (tx, ty), pts in sorted(_state_by_tile().items()):
        path = _tile(ZOOM, tx, ty, fetch=False)
        n = sum(p for _, _, p in pts)
        people += n
        if path is None:
            empty += _empty(tx, ty, fetch=False)
            continue
        im = Image.open(path).convert('RGBA')
        for px, py, pop in pts:
            r, g, b, a = im.getpixel((px, py))
            if a and (r, g, b) not in bands:
                raise SystemExit(f'tile {ZOOM}/{ty}/{tx}: a colour outside the legend, {(r, g, b, a)}')
            if a and bands[(r, g, b)] >= COUNT_FROM_DB:
                loud += pop
    return {'residents': people, 'share_at_or_above_45_db_pct': round(100 * loud / people, 2), 'empty_tiles': empty}


def build(frame):
    from PIL import Image  # noqa: PLC0415
    bands = legend_bands()
    ladder = sorted(set(bands.values()))
    cache, odd = {}, {}
    rows = []
    for p in _load('bayarea_blocks').cities():
        by_band, total = dict.fromkeys(['below_45', *map(str, ladder)], 0), 0
        for lon, lat, pop in frame[p['geoid']]:
            tx, ty, px, py = tile_of(lon, lat)
            if (tx, ty) not in cache:
                path = RAW / f'{ZOOM}_{tx}_{ty}.png'
                if not path.exists():
                    raise SystemExit(f'{path.name} is not on disk (run --fetch)')
                cache[(tx, ty)] = Image.open(path).convert('RGBA')
            r, g, b, a = cache[(tx, ty)].getpixel((px, py))
            if a == 0:
                key = 'below_45'
            elif (r, g, b) in bands:
                key = str(bands[(r, g, b)])
            else:
                odd[(r, g, b, a)] = odd.get((r, g, b, a), 0) + 1  # never guessed into a band
                continue
            by_band[key] += pop
            total += pop
        loud = sum(v for k, v in by_band.items() if k != 'below_45' and int(k) >= COUNT_FROM_DB)
        rows.append({'geoid': p['geoid'], 'name': p['name'], 'county': p['county'], 'residents': total,
                     'share_at_or_above_45_db_pct': round(100 * loud / total, 1),
                     'residents_by_band': by_band})
    if odd:
        raise SystemExit(f'{sum(odd.values())} block points read colours outside the legend: {sorted(odd)[:6]}')
    return {
        'source': 'USDOT Bureau of Transportation Statistics, National Transportation Noise Map 2022, road '
                  '(24-hour LAeq, 30 m, highway traffic 2022/23), read at the 2020 Census block internal points',
        'service': SERVICE,
        'licence': 'US government work; credit USDOT Bureau of Transportation Statistics',
        'generator': 'scripts/build_bayarea_road.py --write',
        'measure': f'share of residents at or above {COUNT_FROM_DB} dB LAeq, the BTS band holding WHO\'s '
                   '53 dB Lden (Lden = LAeq + 6.4 dB under BTS\'s flat-day model): the louder side of WHO',
        'scope': 'BTS: simplified modelling, not for individual locations; a city share only. NOT ON THE UK '
                 'SCALE: BTS models highway traffic, DEFRA far more of the urban network, and the two do not '
                 'overlap (measured 2026-10-18: Bay Area 0.9-24.8%, median 7.2%; UK boroughs 27.9-95.6%, '
                 'median 55.0%), so a score from this needs a US scale, never the UK ramp',
        'california': state_share(),
        'anchor': 'the US road scale is anchored on california.share_at_or_above_45_db_pct (Bill, 2026-10-18), '
                  'as the US crime scale is on the state rate: never the UK ramp',
        'cities': rows,
    }


def problems(doc, want):
    out = []
    have = {r['geoid'] for r in doc['cities']}
    if have != {p['geoid'] for p in want}:
        out.append(f'coverage: {len(have)} cities, not the {len(want)} of the places file')
    for r in doc['cities']:
        if not r['residents'] or sum(r['residents_by_band'].values()) != r['residents']:
            out.append(f"{r['name']}: bands do not add up to its residents")
            continue
        loud = sum(v for k, v in r['residents_by_band'].items() if k != 'below_45' and int(k) >= COUNT_FROM_DB)
        if r['share_at_or_above_45_db_pct'] != round(100 * loud / r['residents'], 1):
            out.append(f"{r['name']}: the share is not its bands'")
    ca = doc.get('california') or {}
    if not (ca.get('residents', 0) > 30_000_000 and 0 < ca.get('share_at_or_above_45_db_pct', 0) < 100):
        out.append(f'the California anchor is missing or implausible: {ca}')
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--fetch', action='store_true')
    g.add_argument('--fetch-state', action='store_true')
    g.add_argument('--write', action='store_true')
    g.add_argument('--check', action='store_true')
    a = ap.parse_args()
    blocks = _load('bayarea_blocks')
    if a.fetch:
        fetch(blocks.blocks())
        return 0
    if a.fetch_state:
        fetch_state()
        return 0
    if a.write:
        doc = build(blocks.blocks())
        OUT.write_text(json.dumps(doc, indent=1) + '\n', encoding='utf-8', newline='\n')
        top = sorted(doc['cities'], key=lambda r: -r['share_at_or_above_45_db_pct'])
        print(f"wrote {OUT.relative_to(REPO)}: {len(top)} cities; loudest "
              + ', '.join(f"{r['name']} {r['share_at_or_above_45_db_pct']}%" for r in top[:4])
              + '; quietest ' + ', '.join(f"{r['name']} {r['share_at_or_above_45_db_pct']}%" for r in top[-3:])
              + f"; California {doc['california']['share_at_or_above_45_db_pct']}%")
        return 0
    doc = json.loads(OUT.read_text(encoding='utf-8'))
    failures = problems(doc, blocks.cities())
    if (RAW / 'legend.json').exists() and blocks.PL_RAW.exists():
        if build(blocks.blocks()) != doc:
            failures.append(f'{OUT.name} is not what the tiles give (re-run --write)')
        else:
            print(f'  tiles          {OUT.name} == the BTS tiles at every block')
    else:
        print('INCONCLUSIVE for values: the tiles or the block frame are not on disk (run --fetch); shape checked')
    if failures:
        print('RESULT: FAIL')
        for f in failures:
            print('  ' + f)
        return 1
    print(f"RESULT: PASS ({len(doc['cities'])} cities)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
