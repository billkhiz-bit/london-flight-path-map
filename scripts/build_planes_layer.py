"""Planes overhead as a layer on the full map: one picture per city and kind of day, every postcode its own step.

WHY (Bill, 2026-11-02, from the mock-ups at claude.ai/artifact/EUGSYeSRLKHymJXLAt8kYW): he preferred the district
fill's look (B) but not its blur. A district, a sector or a hexagon given one colour washes out the strip under an
approach, which is only a few hundred metres wide where the planes are low (Hounslow TW4 on westerly days: 4% of its
postcodes at 100+, so a district share paints it paler than Lewisham). His pick, B2, groups NOTHING: each postcode
keeps its own count, drawn in B's four steps, with the districts outlined over it.

WHAT IT DRAWS, AND FROM WHAT
- Figures: the PUBLISHED per-postcode files, data/planes/<DISTRICT>.json (build_planes_overhead.py), the same files
  the front page's answer and the district pages read. Never a figure from anywhere else, never a middle figure.
- Positions: each postcode's NSPL grid reference, from data/adsb/postcode-averages.npz (the file those figures were
  built from). Postcodes whose ONS position is imputed or a sector mean (NSPL gridind 5, 6: the `approx` flag) are
  left out of the drawing: they can sit hundreds of metres from where they are.
- Each pixel (PX_M on the ground) takes the postcode nearest to it within REACH_M; farther than that, nothing.
- Steps: 10-49, 50-99, 100-199, 200+ a day; under 10, or not measured, is left clear. A postcode on a cone's edge
  (its figure a range, [least, most] within 100 m) is striped between the two steps. Several of the ten airports
  over one postcode: the higher step, for the least and the most separately. So a postcode shows its BUSIEST
  airport, never a total: each airport's kinds of day are its own (a day Heathrow flies west need not be one London
  City does), so two airports' counts cannot be added. Every surface that names the layer says "the busiest
  airport over it" (index.json `rule`, the map legend, CHANGELOG); review, 2026-11-02.
- Kinds of day: airports.json's `classes` (flying west, flying east, both ways), one picture each.
- Districts: one outline picture per city, where the nearest postcode's district changes.

THE PICTURES ARE IN WEB MERCATOR (EPSG:3857), the map's own projection (d3.geoMercator), so a picture placed by its
two corners lines up with the map at every zoom. index.json gives each city's corners in longitude and latitude.

OUTPUT
  data/planes-layer/<city>-<class>.png, <city>-districts.png, index.json   gitignored (built from gitignored files)
  data/planes-layer-manifest.json   TRACKED: each file's size and MD5, for the deploy drift check

  python scripts/build_planes_layer.py --write
  python scripts/build_planes_layer.py --check    # the pictures on disk show what --write would draw
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from pyproj import Transformer
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parent.parent
PLANES = ROOT / 'data' / 'planes'
AVERAGES = ROOT / 'data' / 'adsb' / 'postcode-averages.npz'
OUT_DIR = ROOT / 'data' / 'planes-layer'
MANIFEST = ROOT / 'data' / 'planes-layer-manifest.json'

PX_M = 25.0        # ground metres a pixel spans at the city's middle
REACH_M = 220.0    # a pixel takes a postcode no farther than this; beyond it, nothing
STEPS = (10, 50, 100, 200)   # step 1: 10-49, 2: 50-99, 3: 100-199, 4: 200+ a day
COLOURS = {1: '#dc8a4a', 2: '#c2622a', 3: '#9a4316', 4: '#662809'}   # B's ramp, validated against the map ground
OUTLINE = ('#fafaf9', 140)   # district outline colour and alpha (0-255)
APPROX_GRIDIND = (5, 6)
R_EARTH = 6378137.0


def step(v) -> int:
    """A published figure (a number or '<1') -> its step, 0 under 10."""
    if v == '<1':
        return 0
    s = 0
    for i, t in enumerate(STEPS, 1):
        if v >= t:
            s = i
    return s


def least_most(figures: dict, k: int) -> tuple[int, int]:
    """(least step, most step) for a postcode on kind of day k over every airport it lists; (0, 0) when none.

    A range is [least, most] within 100 m; several airports: the higher step, for each end separately.
    """
    lo = hi = 0
    for vals in figures.values():
        v = vals[k]
        if v is None:
            continue
        a, b = (step(v[0]), step(v[1])) if isinstance(v, list) else (step(v), step(v))
        lo, hi = max(lo, a), max(hi, b)
    return lo, hi


def backend_only_cities() -> frozenset[str]:
    """API-only cities have no map, so no layer: read from the one holder (build_hpi_prices.py), never retyped."""
    spec = importlib.util.spec_from_file_location('bhp_layer', ROOT / 'scripts' / 'build_hpi_prices.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return frozenset(mod._backend_only_cities())  # noqa: SLF001 - the holder's own reader


def merc_x(lon):
    return np.radians(lon) * R_EARTH


def merc_y(lat):
    return np.log(np.tan(np.pi / 4 + np.radians(lat) / 2)) * R_EARTH


def merc_lon(x):
    return math.degrees(x / R_EARTH)


def merc_lat(y):
    return math.degrees(math.atan(math.sinh(y / R_EARTH)))


def load():
    """(classes, credits, figures by postcode, npz arrays) from the published files and the averages file."""
    airports = json.loads((PLANES / 'airports.json').read_text(encoding='utf-8'))
    figures = {}
    for f in sorted(PLANES.glob('*.json')):
        if f.name == 'airports.json':
            continue
        figures.update(json.loads(f.read_text(encoding='utf-8')).get('postcodes', {}))
    z = np.load(AVERAGES, allow_pickle=False)
    arrays = {k: z[k] for k in ('postcode', 'city', 'easting', 'northing', 'gridind')}
    return airports, figures, arrays


def png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    return buf.getvalue()


def palette_image(index: np.ndarray, colours: list[tuple[str, int]]) -> Image.Image:
    """An 8-bit palette picture: index 0 clear, then each (hex, alpha)."""
    im = Image.frombytes('P', (index.shape[1], index.shape[0]), index.astype(np.uint8).tobytes())
    pal = [0, 0, 0]
    alpha = [0]
    for hexc, a in colours:
        pal += [int(hexc[i:i + 2], 16) for i in (1, 3, 5)]
        alpha.append(a)
    im.putpalette(pal + [0] * (768 - len(pal)))
    im.info['transparency'] = bytes(alpha)
    return im


def draw_city(city, pcs, east, north, figures, classes, to_bng):
    """{name: PIL image} and the city's index entry, for one city's measured postcodes."""
    tree = cKDTree(np.column_stack([east, north]))
    # The grid: Web Mercator, around the postcodes plus REACH_M, pixels PX_M on the ground at the middle.
    to_ll = Transformer.from_crs('EPSG:27700', 'EPSG:4326', always_xy=True)
    lon, lat = to_ll.transform(east, north)
    lat0 = float(np.median(lat))
    px = PX_M / math.cos(math.radians(lat0))
    pad = REACH_M / math.cos(math.radians(lat0))
    mx, my = merc_x(np.asarray(lon)), merc_y(np.asarray(lat))
    x0 = math.floor((mx.min() - pad) / px) * px
    x1 = math.ceil((mx.max() + pad) / px) * px
    y0 = math.floor((my.min() - pad) / px) * px
    y1 = math.ceil((my.max() + pad) / px) * px
    W, H = round((x1 - x0) / px), round((y1 - y0) / px)
    gx = x0 + (np.arange(W) + 0.5) * px
    gy = y1 - (np.arange(H) + 0.5) * px
    GX, GY = np.meshgrid(gx, gy)
    glon = np.degrees(GX / R_EARTH)
    glat = np.degrees(2 * np.arctan(np.exp(GY / R_EARTH)) - np.pi / 2)
    ge, gn = to_bng.transform(glon.ravel(), glat.ravel())
    dist, idx = tree.query(np.column_stack([ge, gn]), distance_upper_bound=REACH_M)
    valid = np.isfinite(dist).reshape(H, W)
    idx = np.where(valid, idx.reshape(H, W), 0)

    out = {}
    stripe = ((np.arange(H)[:, None] + np.arange(W)[None, :]) // 2) % 2 == 0   # 45-degree stripes, 2 px wide
    ramp = [(COLOURS[s], 255) for s in (1, 2, 3, 4)]
    for k, cls in enumerate(classes):
        lo = np.zeros(len(pcs), np.int8)
        hi = np.zeros(len(pcs), np.int8)
        for i, p in enumerate(pcs):
            f = figures.get(p)
            if f:
                lo[i], hi[i] = least_most(f, k)
        L, Hh = lo[idx], hi[idx]
        pix = np.where(stripe, Hh, L)
        pix = np.where(valid, pix, 0)
        out[f'{city}-{cls}.png'] = palette_image(pix, ramp)
    district = np.array([p.split()[0] for p in pcs])
    dg = district[idx]
    edge = np.zeros((H, W), bool)
    edge[:, 1:] |= (dg[:, 1:] != dg[:, :-1]) & valid[:, 1:] & valid[:, :-1]
    edge[1:, :] |= (dg[1:, :] != dg[:-1, :]) & valid[1:, :] & valid[:-1, :]
    out[f'{city}-districts.png'] = palette_image(edge.astype(np.uint8), [OUTLINE])
    entry = {
        'bounds': [round(merc_lon(x0), 7), round(merc_lat(y0), 7), round(merc_lon(x1), 7), round(merc_lat(y1), 7)],
        'size': [W, H],
        'files': {**{cls: f'{city}-{cls}.png' for cls in classes}, 'districts': f'{city}-districts.png'},
    }
    return out, entry


def placed(gridind, east, north):
    """Postcodes drawn: a grid reference ONS measured (not imputed or a sector mean), and one at all."""
    return ~np.isin(gridind, APPROX_GRIDIND) & np.isfinite(east) & np.isfinite(north)


def build():
    """{file name: bytes or PIL image}: every picture and index.json."""
    airports, figures, a = load()
    classes = airports['classes']
    skip = backend_only_cities()
    to_bng = Transformer.from_crs('EPSG:4326', 'EPSG:27700', always_xy=True)
    pcs_all = np.array([str(p) for p in a['postcode']])
    placed_ = placed(a['gridind'], a['easting'], a['northing'])
    files, cities = {}, {}
    for city in sorted(set(a['city'].tolist()) - skip):
        m = (a['city'] == city) & placed_
        pcs = pcs_all[m]
        # A city earns a layer only if some postcode in it reaches a step on some kind of day.
        if not any(least_most(figures[p], k)[1] for p in pcs if p in figures for k in range(len(classes))):
            continue
        imgs, entry = draw_city(city, pcs, a['easting'][m], a['northing'][m], figures, classes, to_bng)
        files.update(imgs)
        cities[city] = entry
    index = {
        'about': 'Planes overhead a day at each postcode, drawn for the full map (scripts/build_planes_layer.py).',
        'definition': airports['definition'],
        # The months counted, first and last over the airports drawn (YYYYMM), as airports.json gives them.
        'months': [min(v['months'][0] for v in airports['airports'].values()),
                   max(v['months'][1] for v in airports['airports'].values())],
        'classes': classes,
        'steps': [{'step': s, 'from': STEPS[s - 1], 'to': (STEPS[s] - 1) if s < len(STEPS) else None,
                   'colour': COLOURS[s]} for s in (1, 2, 3, 4)],
        'rule': 'Each postcode is drawn in the step of the busiest airport over it on that kind of day; two '
                'airports\' counts are never added, as each airport\'s kinds of day are its own.',
        'edge': 'A postcode on a cone\'s edge, where a few metres decide the step, is striped between the two.',
        'blank': 'Under 10 a day from every airport over it, or not measured.',
        'projection': 'EPSG:3857',
        'cities': cities,
        'credits': airports['credits'],
        'licence': airports['licence'],
    }
    files['index.json'] = (json.dumps(index, ensure_ascii=False, indent=1) + '\n').encode('utf-8')
    return files


def pixels(img_or_bytes):
    """What a picture SHOWS (size and every pixel's colour and alpha), for comparing two encodings of it.

    Not its palette indexes: saving with optimize=True re-orders and trims the palette, so the same picture can be
    stored with different indexes.
    """
    im = Image.open(io.BytesIO(img_or_bytes)) if isinstance(img_or_bytes, bytes) else img_or_bytes
    return (im.size, im.convert('RGBA').tobytes())


def encode(files):
    return {n: (v if isinstance(v, bytes) else png(v)) for n, v in files.items()}


def manifest_of(out_dir=OUT_DIR):
    return {p.name: {'bytes': p.stat().st_size, 'md5': hashlib.md5(p.read_bytes(), usedforsecurity=False).hexdigest()}
            for p in sorted(out_dir.glob('*')) if p.is_file()}


def write(files, out_dir=OUT_DIR, manifest_path=MANIFEST):
    out_dir.mkdir(parents=True, exist_ok=True)
    enc = encode(files)
    for old in out_dir.glob('*'):
        if old.name not in enc:
            old.unlink()
    for name, b in enc.items():
        (out_dir / name).write_bytes(b)
    manifest_path.write_text(json.dumps(manifest_of(out_dir), indent=1) + '\n', encoding='utf-8', newline='\n')


def check(files, out_dir=OUT_DIR, manifest_path=MANIFEST):
    """Differences between what --write would draw and what is on disk, as lines (none: in step).

    Pictures are compared by what they SHOW, not their bytes: another zlib may pack the same pixels differently.
    The manifest must describe the bytes on disk (it is what the deploy drift check compares the live files with).
    """
    problems = []
    on_disk = {p.name for p in out_dir.glob('*')} if out_dir.exists() else set()
    for name in sorted(set(files) | on_disk):
        if name not in on_disk:
            problems.append(f'missing: {name}')
        elif name not in files:
            problems.append(f'no longer built: {name}')
        elif name.endswith('.png'):
            if pixels((out_dir / name).read_bytes()) != pixels(files[name]):
                problems.append(f'stale: {name}')
        elif (out_dir / name).read_bytes() != files[name]:
            problems.append(f'stale: {name}')
    try:
        recorded = json.loads(manifest_path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        recorded = None
    if out_dir.exists() and recorded != manifest_of(out_dir):
        problems.append(f'{manifest_path.name} does not describe the files on disk')
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--strict', action='store_true', help='a missing input fails --check (the deploy uses this)')
    a = ap.parse_args()
    if not (a.write or a.check):
        ap.error('pass --write or --check')
    missing = [str(p.relative_to(ROOT)) for p in (AVERAGES, PLANES / 'airports.json') if not p.exists()]
    if missing:
        # Unrunnable is not failed, and never a pass: preflight reads a leading INCONCLUSIVE and names the gate.
        # A deploy must not read it at all (--strict): it would upload whatever happens to be on disk.
        soft = a.check and not (a.write or a.strict)
        print(('INCONCLUSIVE: ' if soft else 'FAIL: ') + 'missing ' + '; '.join(missing)
              + ' (scripts/adsb_postcode_averages.py, then build_planes_overhead.py --write)')
        return 0 if soft else 1
    files = build()
    if a.write:
        write(files)
        sizes = manifest_of()
        print(f'{len(sizes)} files, {sum(v["bytes"] for v in sizes.values()) / 1e6:.1f} MB; cities: '
              + ', '.join(json.loads(files['index.json'])['cities']))
    if a.check:
        problems = check(files)
        print('\n'.join(problems) if problems else 'OK')
        if problems:
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
