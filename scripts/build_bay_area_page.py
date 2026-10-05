"""The San Francisco Bay Area flight-path page: bay-area/index.html.

    python scripts/build_bay_area_page.py --fetch   # Census boundaries + BTS noise picture (network), then write
    python scripts/build_bay_area_page.py --write   # render the page from the checked-in inputs
    python scripts/build_bay_area_page.py --check   # is the page what its inputs render? (blocking, offline)

WHY THIS EXISTS (2026-10-02)
----------------------------
Bill's ruling: the Bay Area goes live as a flight-path page FIRST, before it is
a scored city on the map. Making it a scored city means generalising about 25
places where New York is wired in by name and finding US sources for prices
and crime (EXPANSION.md); this page needs none of that, and it is the part the
product's niche is about. It shows the 50 cities of the four counties that
hold the three airports, the routes the FAA has coded for those airports, and
BTS's noise map, and it says of each city what the routes and the map say.

It publishes NO score. A score would need the inputs this page does not have.

THREE INPUTS, AND WHAT EACH IS TRUSTED FOR
------------------------------------------
  - data/us-flight-procedures.json (build_us_flight_paths.py): where the
    published routes are. Not how many aircraft use them: the FAA file does
    not say, and the page says that it does not.
  - bay-area/aircraft-noise-laeq-2022-<hash>.png: BTS's 2022 aviation noise
    tiles, stitched for this box. A modelled 24-hour average that DOES reflect which
    runways are used, so the table is ordered by it and not by route geometry
    (San Francisco's runway 10 approaches are published and rarely flown; a
    table ordered by "lowest aircraft overhead" would lead with them). BTS says
    its map "should not be used to evaluate noise levels in individual
    locations", so the page reports a share of a whole city, never an address.
  - data/us-bayarea-places.json: Census cartographic boundaries, simplified.

WHAT IT REFUSES TO DO
---------------------
  - Draw an approach to a runway end with no published glide angle. The
    record gives SFO 01L/01R and OAK 15/33 `glide_deg: null`; a line there
    would be this script's guess at where aircraft descend.
  - Report a height over the city that holds the airport. "Lowest aircraft
    overhead: 0 ft" is true of Oakland and says nothing.
  - Be more exact than the boundaries are. These are the Census's 1:500,000
    outlines, generalised by up to a few hundred feet, and beside an airport
    that is the whole answer: measured against the unsimplified file, San
    Jose's runway 12R threshold is 126 m inside SANTA CLARA and 12L is 23 m
    outside it. So "the airport is inside the city" is decided by the
    airport's reference point, in the middle of the field, never by a
    threshold or by a low height (two earlier versions used each, and told
    Alameda and then Santa Clara that a runway was theirs). And a height under
    LOW_FT is printed as "under 500 ft, beside the airport", which a boundary
    moved by 150 m cannot make false.
  - Print a decibel figure. The 2022 tile service publishes no legend, so the
    band values have not been re-read against BTS (check_noise_legend.py); the
    page shows BTS's colours from quieter to louder and no number.
  - Fill a failed tile with "no noise". A tile that fails for any reason but
    "not found" fails the fetch.

TWO CROSS-CHECKS THAT ARE NOT THE FILE AGAINST ITSELF
-----------------------------------------------------
  - Each city's area, measured from the polygon read out of the shapefile,
    against the land area the Census prints in the attribute table beside it.
    A reader that pairs record N's shape with record N+1's attributes, or
    loses a ring, fails here.
  - The drawn approaches against the noise picture. Every runway threshold
    must sit on a painted pixel, and at each airport the best-covered approach
    must have APPROACH_ON_NOISE of its first 8 km on painted pixels. Two
    publishers, two formats, one geography - the EA flood mosaics were
    stretched five times over for want of exactly this (CLAUDE.md).
    NOT "every approach": the first version asked that and failed on a
    correctly placed picture. BTS paints LAND only, so San Francisco's main
    approach, which comes in over the bay, is on painted pixels for 2% of its
    length (measured), and the runway 28 lobe only appears where it crosses
    the shore at Foster City.

The page carries the FAA's warranty disclaimer, which its licence requires of
anything built on the CIFP (LICENSING.md).
"""

import argparse
import hashlib
import html
import io
import json
import math
import struct
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import build_us_flight_paths  # noqa: E402
import check_noise_legend  # noqa: E402

PLACES = ROOT / 'data' / 'us-bayarea-places.json'
PAGE_DIR = ROOT / 'bay-area'
PAGE = PAGE_DIR / 'index.html'
# The picture is named after its own CONTENT (the first ten characters of its
# sha256). sw.js serves same-origin images cache-first and never asks again,
# so a picture rebuilt under an old name would stay pinned in a returning
# visitor's Cache Storage, and `preserveAspectRatio="none"` would stretch the
# old picture into the new frame without a word. The first version named it
# after the BTS edition alone, which a change of frame (a new Census vintage,
# another city) does not move.
NOISE_PREFIX = 'aircraft-noise-laeq-2022-'
# The link-preview picture the page's og:image names, drawn from the page's
# own map by scripts/render_bay_area_share.mjs. Its presence is checked here
# because the homepage's og:image pointed at a file that did not exist from
# launch until 2026-09-28, and every shared link showed a placeholder.
SHARE_NAME = 'share.png'
CENSUS = ROOT / 'data' / 'census'  # gitignored (data/*): re-fetchable
VINTAGE = '2023'
PLACE_STEM = f'cb_{VINTAGE}_06_place_500k'
COUNTY_STEM = f'cb_{VINTAGE}_us_county_500k'
CENSUS_URL = f'https://www2.census.gov/geo/tiger/GENZ{VINTAGE}/shp/{{stem}}.zip'
SITE = 'https://skyscore.co.uk'
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36'}

# County FIPS (California) -> name and how many incorporated cities and towns
# it holds. The counts are the gate: the place file has no county column, so a
# city is put in a county by where its interior falls, and a wrong pairing
# shows up as a count that is not the county's real one.
COUNTIES = {
    '075': ('San Francisco', 1),
    '081': ('San Mateo', 20),
    '085': ('Santa Clara', 15),
    '001': ('Alameda', 14),
}
AIRPORTS = ('SFO', 'OAK', 'SJC')
AIRPORT_NAMES = {'SFO': 'San Francisco', 'OAK': 'Oakland', 'SJC': 'San Jose'}
CITY, TOWN, CDP = '25', '43', '57'  # Census LSAD codes

FINAL_TOP_FT = 3000  # the UK builder's rule: a final approach is drawn from 3,000 ft down
FT_KM = 0.0003048
KM_MI = 0.621371
DEPARTURE_KM = 30.0  # beyond this a departing aircraft is high; the table reads the first 30 km
STEP_KM = 0.1
AIRFIELD_PAD_DEG = 0.1  # airfields just outside the frame can still be the nearest
LOW_FT = 500
PRUNE_FLOOR_KM = 0.01
NEAR_KM = 5.0  # "no drawn route within 3 miles" is said beyond this
MIN_SHARE_PCT = 1.0  # a city "is on the noise map" from this share of its area
APPROACH_ON_NOISE = 0.9
APPROACH_CHECK_KM = 8.0
AREA_TOLERANCE = 0.06

TILE_ZOOM = 11
TILE = 256
MAP_W = 900
PAD_DEG = (0.09, 0.03, 0.03, 0.03)  # west (departures run out over the ocean), south, east, north
SIMPLIFY_DEG = 0.0002  # about 20 m: under a quarter of a pixel on the drawn map
MIN_RING_KM2 = 0.02


# ---- shapefile (no library: the format is 30 lines of struct) ---------------


def read_dbf(raw):
    n, hlen, rlen = struct.unpack('<IHH', raw[4:12])
    fields, off = [], 32
    while raw[off] != 0x0D:
        fields.append((raw[off : off + 11].split(b'\0')[0].decode(), raw[off + 16]))
        off += 32
    rows = []
    for i in range(n):
        rec = raw[hlen + i * rlen : hlen + (i + 1) * rlen]
        pos, row = 1, {}
        for name, ln in fields:
            row[name] = rec[pos : pos + ln].decode('utf-8', 'replace').strip()
            pos += ln
        rows.append(row)
    return rows


def read_shp(raw):
    """Every record's rings, as [(lon, lat), ...] lists. Polygons only."""
    shapes, off = [], 100
    while off < len(raw):
        _, words = struct.unpack('>II', raw[off : off + 8])
        body = raw[off + 8 : off + 8 + words * 2]
        off += 8 + words * 2
        kind = struct.unpack('<i', body[:4])[0]
        if kind == 0:
            shapes.append([])
            continue
        if kind != 5:
            raise SystemExit(f'shape type {kind}: this reader handles polygons (5) only')
        nparts, npts = struct.unpack('<ii', body[36:44])
        parts = [*struct.unpack(f'<{nparts}i', body[44 : 44 + 4 * nparts]), npts]
        base = 44 + 4 * nparts
        pts = struct.unpack(f'<{2 * npts}d', body[base : base + 16 * npts])
        shapes.append(
            [[(pts[2 * i], pts[2 * i + 1]) for i in range(a, b)] for a, b in zip(parts, parts[1:], strict=False)]
        )
    return shapes


def read_layer(stem):
    with zipfile.ZipFile(CENSUS / f'{stem}.zip') as z:
        rows, shapes = read_dbf(z.read(f'{stem}.dbf')), read_shp(z.read(f'{stem}.shp'))
    if len(rows) != len(shapes):
        raise SystemExit(f'{stem}: {len(rows)} attribute rows for {len(shapes)} shapes')
    return list(zip(rows, shapes, strict=True))


# ---- geometry ---------------------------------------------------------------

LAT0 = 37.5  # the box's middle; every distance here is within 60 km of it


def xy(lon, lat):
    """Degrees -> km on a local plane. Good to a part in a thousand over this box."""
    return (lon * 111.32 * math.cos(math.radians(LAT0)), lat * 110.574)


def ring_area_km2(ring):
    pts = [xy(*p) for p in ring]
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1], strict=True)) / 2


def area_km2(rings):
    """Holes wind the other way in a shapefile, so signed areas net them out."""
    return abs(sum(ring_area_km2(r) for r in rings))


def inside(rings, lon, lat):
    """Even-odd over every ring, so a hole is outside without being told it is one."""
    c = False
    for r in rings:
        for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1], strict=True):
            if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
                c = not c
    return c


def simplify(ring, tol):
    """Douglas-Peucker, iterative. The ring's first point is kept."""
    if len(ring) < 5:
        return ring
    keep = [False] * len(ring)
    keep[0] = keep[-1] = True
    stack = [(0, len(ring) - 1)]
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = ring[a], ring[b]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy)
        far, at = 0.0, None
        for i in range(a + 1, b):
            px, py = ring[i]
            d = abs(dx * (py - ay) - dy * (px - ax)) / norm if norm else math.hypot(px - ax, py - ay)
            if d > far:
                far, at = d, i
        if at is not None and far > tol:
            keep[at] = True
            stack += [(a, at), (at, b)]
    return [p for p, k in zip(ring, keep, strict=True) if k]


def tidy(rings, tol=SIMPLIFY_DEG):
    out = []
    for r in rings:
        if abs(ring_area_km2(r)) < MIN_RING_KM2:
            continue
        s = simplify(r, tol)
        if len(s) >= 4:
            out.append([[round(x, 5), round(y, 5)] for x, y in s])
    return out


def main_ring(rings):
    """A place's largest ring. San Francisco's boundary includes the Farallon
    Islands, 45 km out to sea, and a box round every ring is mostly ocean."""
    return max(rings, key=lambda r: abs(ring_area_km2(r)))


def interior_points(rings, n=14):
    """A grid of points strictly inside a shape: its boundary may BE a county line."""
    xs = [x for x, _ in main_ring(rings)]
    ys = [y for _, y in main_ring(rings)]
    pts = []
    for i in range(n):
        for j in range(n):
            lon = min(xs) + (max(xs) - min(xs)) * (i + 0.5) / n
            lat = min(ys) + (max(ys) - min(ys)) * (j + 0.5) / n
            if inside(rings, lon, lat):
                pts.append((lon, lat))
    return pts


def destination(lat, lon, bearing, km):
    b = math.radians(bearing)
    return (lat + km * math.cos(b) / 110.574, lon + km * math.sin(b) / (111.32 * math.cos(math.radians(lat))))


def densify(line, step=STEP_KM):
    """[(lat, lon), ...] -> the same line with a point every `step` km, and each point's distance along it."""
    out, along = [], 0.0
    for (a, b), (c, d) in zip(line, line[1:], strict=False):
        (x1, y1), (x2, y2) = xy(b, a), xy(d, c)
        seg = math.hypot(x2 - x1, y2 - y1)
        n = max(1, round(seg / step))
        out += [(a + (c - a) * i / n, b + (d - b) * i / n, along + seg * i / n) for i in range(n)]
        along += seg
    out.append((*line[-1], along))
    return out


def clip_line(line, km):
    """[(lat, lon), ...] cut off `km` along it."""
    out, along = [line[0]], 0.0
    for (a, b), (c, d) in zip(line, line[1:], strict=False):
        (x1, y1), (x2, y2) = xy(b, a), xy(d, c)
        seg = math.hypot(x2 - x1, y2 - y1)
        if along + seg >= km:
            t = (km - along) / seg if seg else 0.0
            out.append((a + (c - a) * t, b + (d - b) * t))
            return out
        out.append((c, d))
        along += seg
    return out


def seg_distance(p, a, b):
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy) if dx or dy else 0.0
    t = max(0.0, min(1.0, t))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


class Shape:
    """A place's rings with what the distance tests need worked out once."""

    def __init__(self, rings):
        self.rings = rings
        self.km = [[xy(*p) for p in r] for r in rings]
        xs = [x for r in self.km for x, _ in r]
        ys = [y for r in self.km for _, y in r]
        self.box = (min(xs), min(ys), max(xs), max(ys))

    def box_distance(self, p):
        dx = max(self.box[0] - p[0], 0, p[0] - self.box[2])
        dy = max(self.box[1] - p[1], 0, p[1] - self.box[3])
        return math.hypot(dx, dy)

    def distance(self, lon, lat, best=float('inf')):
        """km from a point to the shape, 0 inside it. Skips the work when the box is already further than `best`."""
        p = xy(lon, lat)
        if self.box_distance(p) >= best:
            return best
        if inside(self.rings, lon, lat):
            return 0.0
        return min(seg_distance(p, a, b) for r in self.km for a, b in zip(r, r[1:] + r[:1], strict=True))


# ---- routes -----------------------------------------------------------------


def routes(record):
    """The lines this page draws: (approaches, departures, runway ends not drawn)."""
    approaches, departures, undrawn = [], [], []
    for code in AIRPORTS:
        ap = record['airports'][code]
        for rwy, r in sorted(ap['runways'].items()):
            if r['glide_deg'] is None:
                undrawn.append(f'{code} {rwy}')
                continue
            length = FINAL_TOP_FT * FT_KM / math.tan(math.radians(r['glide_deg']))
            far = destination(r['thr'][0], r['thr'][1], (r['true_brg'] + 180) % 360, length)
            approaches.append(
                {
                    'airport': code,
                    'runway': rwy,
                    'glide': r['glide_deg'],
                    'line': [tuple(r['thr']), far],
                    'points': densify([tuple(r['thr']), far]),
                }
            )
        for dep in ap['departures']:
            if not dep['waypoints']:
                continue
            start = ap['runways'][dep['runways'][0]]['thr']
            # Cut at DEPARTURE_KM, and the MAP draws this same cut line. The
            # first version measured the first 30 km and drew the whole route,
            # so six cities had a line across them and "No" in their row.
            line = clip_line([tuple(start)] + [tuple(w) for w in dep['waypoints']], DEPARTURE_KM)
            departures.append({'airport': code, 'name': dep['name'], 'line': line, 'points': densify(line)})
    return approaches, departures, undrawn


def height_ft(route, along_km):
    return along_km * math.tan(math.radians(route['glide'])) / FT_KM


def measure(shape, approaches, departures):
    """What the routes say about one place."""
    over_app, over_dep, nearest = {}, set(), (float('inf'), None)

    def reach(lon, lat):
        # distance() hands back its `best` argument when the shape's box is
        # already further away than that. The floor keeps that answer above
        # zero: once one route is overhead `nearest` is 0, and an unfloored
        # prune would return 0 - "overhead" - for every later point on the map.
        return shape.distance(lon, lat, max(nearest[0], PRUNE_FLOOR_KM))

    for r in approaches:
        label = f'{r["airport"]} {r["runway"]}'
        for lat, lon, along in r['points']:
            d = reach(lon, lat)
            if d == 0.0:
                h = height_ft(r, along)
                over_app[label] = min(over_app.get(label, h), h)
            if d < nearest[0]:
                nearest = (d, f'{label} approach')
    for r in departures:
        label = f'{r["airport"]} {r["name"]}'
        for lat, lon, _ in r['points']:
            d = reach(lon, lat)
            if d == 0.0:
                over_dep.add(label)
            if d < nearest[0]:
                nearest = (d, f'{label} departure')
    return {
        'approaches': over_app,
        'departures': sorted(over_dep),
        'nearest_km': nearest[0],
        'nearest': nearest[1],
    }


# ---- the map projection: web mercator, in the noise tiles' own pixels --------


def global_px(lon, lat, z=TILE_ZOOM):
    n = TILE * 2**z
    return ((lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)


def lonlat_of(px, py, z=TILE_ZOOM):
    n = TILE * 2**z
    return (px / n * 360 - 180, math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * py / n)))))


class Frame:
    """The box the map and the noise picture share, as whole pixels at TILE_ZOOM."""

    def __init__(self, px_box):
        self.x0, self.y0, self.x1, self.y1 = px_box
        self.w, self.h = self.x1 - self.x0, self.y1 - self.y0
        self.scale = MAP_W / self.w
        self.height = round(self.h * self.scale)

    @classmethod
    def around(cls, places):
        lons = [x for p in places for x, _ in main_ring(p['rings'])]
        lats = [y for p in places for _, y in main_ring(p['rings'])]
        x0, y1 = global_px(min(lons) - PAD_DEG[0], min(lats) - PAD_DEG[1])
        x1, y0 = global_px(max(lons) + PAD_DEG[2], max(lats) + PAD_DEG[3])
        return cls((math.floor(x0), math.floor(y0), math.ceil(x1), math.ceil(y1)))

    def pixel(self, lon, lat):
        """Position in the noise picture, in its own pixels."""
        gx, gy = global_px(lon, lat)
        return gx - self.x0, gy - self.y0

    def svg(self, lon, lat):
        x, y = self.pixel(lon, lat)
        return x * self.scale, y * self.scale


# ---- fetch: Census boundaries -----------------------------------------------


def download(url, dest, what):
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix('.part')
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
        part.write_bytes(r.read())
    if not zipfile.is_zipfile(part):
        part.unlink()
        raise SystemExit(f'{url} did not arrive as a zip: nothing was cached, run it again')
    part.replace(dest)
    print(f'fetched {what}: {dest.name} ({dest.stat().st_size:,} bytes)')


def build_places():
    """The four counties' cities, towns and unincorporated communities, from the Census files."""
    for stem in (PLACE_STEM, COUNTY_STEM):
        download(CENSUS_URL.format(stem=stem), CENSUS / f'{stem}.zip', 'Census boundaries')
    counties = {r['COUNTYFP']: (r['NAME'], rings) for r, rings in read_layer(COUNTY_STEM) if r['STATEFP'] == '06'}
    ours = {fips: counties[fips][1] for fips in COUNTIES}

    places = []
    for row, rings in read_layer(PLACE_STEM):
        if row['LSAD'] not in (CITY, TOWN, CDP) or not rings:
            continue
        pts = interior_points(rings)
        if not pts:
            continue
        votes = {fips: sum(inside(c, *p) for p in pts) for fips, c in ours.items()}
        fips = max(votes, key=votes.get)
        if votes[fips] < 0.6 * len(pts):
            continue  # outside the four counties (or, for a community, astride a county line)
        tidied = tidy(rings)
        land = int(row['ALAND']) / 1e6
        places.append(
            {
                'name': row['NAME'],
                'geoid': row['GEOID'],
                'kind': 'cdp' if row['LSAD'] == CDP else ('town' if row['LSAD'] == TOWN else 'city'),
                'county': COUNTIES[fips][0],
                'land_km2': round(land, 2),
                'water_km2': round(int(row['AWATER']) / 1e6, 2),
                'rings': tidied,
            }
        )
    places.sort(key=lambda p: (p['kind'] == 'cdp', p['name']))

    frame = Frame.around([p for p in places if p['kind'] != 'cdp'])
    w, n = lonlat_of(frame.x0, frame.y0)
    e, s = lonlat_of(frame.x1, frame.y1)
    land = []
    for _fips, (name, rings) in sorted(counties.items()):
        lons = [x for r in rings for x, _ in r]
        lats = [y for r in rings for _, y in r]
        if max(lons) < w or min(lons) > e or max(lats) < s or min(lats) > n:
            continue
        land.append({'name': name, 'rings': tidy(rings, SIMPLIFY_DEG * 2)})
    return {
        'source': f'US Census Bureau cartographic boundary files {VINTAGE} ({PLACE_STEM}, {COUNTY_STEM}), public domain',
        'vintage': VINTAGE,
        'generator': 'scripts/build_bay_area_page.py --fetch',
        'frame': {'zoom': TILE_ZOOM, 'px': [frame.x0, frame.y0, frame.x1, frame.y1]},
        'land': land,
        'places': places,
    }


# ---- fetch: the BTS noise picture -------------------------------------------


def build_noise(frame):
    """BTS's aviation noise tiles over the frame, as one PNG. Returns (bytes, tiles read)."""
    from PIL import Image

    base = check_noise_legend.bts_tile_service()
    mosaic = Image.new('RGBA', (frame.w, frame.h), (0, 0, 0, 0))
    read = 0
    for ty in range(frame.y0 // TILE, (frame.y1 - 1) // TILE + 1):
        for tx in range(frame.x0 // TILE, (frame.x1 - 1) // TILE + 1):
            url = f'{base}/tile/{TILE_ZOOM}/{ty}/{tx}'
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                    tile = Image.open(io.BytesIO(r.read())).convert('RGBA')
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    continue  # the service holds no tile where it maps no noise
                raise SystemExit(
                    f'{url}: HTTP {exc.code}. A failed tile is not "no noise"; nothing was written'
                ) from exc
            if tile.size != (TILE, TILE):
                raise SystemExit(f'{url}: a {tile.size} tile, not {TILE}x{TILE}: the mosaic would be mis-placed')
            mosaic.paste(tile, (tx * TILE - frame.x0, ty * TILE - frame.y0))
            read += 1
    scale = {c for _, c in check_noise_legend.scale_from_index('NOISE_SCALE_BTS')}
    seen = {check_noise_legend.hexcolour(p) for p in mosaic.getdata() if p[3] > 0}
    if seen - scale:
        raise SystemExit(f'the tiles paint {sorted(seen - scale)}, which NOISE_SCALE_BTS has no band for')
    buf = io.BytesIO()
    mosaic.save(buf, 'PNG', optimize=True)
    return buf.getvalue(), read


def fetch():
    data = build_places()
    frame = Frame(data['frame']['px'])
    png, tiles = build_noise(frame)
    PAGE_DIR.mkdir(exist_ok=True)
    digest = hashlib.sha256(png).hexdigest()
    name = f'{NOISE_PREFIX}{digest[:10]}.png'
    (PAGE_DIR / name).write_bytes(png)
    data['airfields'] = build_airfields(frame)
    data['noise'] = {
        'file': name,
        'publisher': 'US DOT Bureau of Transportation Statistics, National Transportation Noise Map 2022 (aviation)',
        'service': check_noise_legend.bts_tile_service(),
        'tiles_read': tiles,
        'sha256': digest,
    }
    PLACES.write_text(json.dumps(data, separators=(',', ':')) + '\n', encoding='utf-8', newline='\n')
    cities = sum(p['kind'] != 'cdp' for p in data['places'])
    print(f'wrote {PLACES.name}: {cities} cities and towns, {len(data["places"]) - cities} communities')
    print(f'wrote {name}: {frame.w}x{frame.h} px from {tiles} tiles, {len(png):,} bytes')
    stale = sorted(f.name for f in PAGE_DIR.glob(f'{NOISE_PREFIX}*.png') if f.name != name)
    if stale:
        print(f'  superseded and still on disk, delete before deploying: {", ".join(stale)}')


def build_airfields(frame):
    """Every airfield the FAA file holds in and just round the frame.

    BTS's map shades every airfield it models, not the three this page draws:
    Livermore is 36% on the map from Livermore's own municipal airport. So
    each row names the airfield its shading belongs to (patch_owners), and for
    that the page needs to know where the airfields are. The CIFP holds an airport record
    for each (the name is columns 94-123, read off the real file).
    """
    record = json.loads(build_us_flight_paths.RECORD.read_text(encoding='utf-8'))
    stamp = record['effective'].replace('-', '')[2:]
    zip_path = build_us_flight_paths.CACHE / f'CIFP_{stamp}.zip'
    if not zip_path.exists():
        zip_path = build_us_flight_paths.fetch()
    w, n = lonlat_of(frame.x0, frame.y0)
    e_, s = lonlat_of(frame.x1, frame.y1)
    out = []
    for line in build_us_flight_paths.lines_of(zip_path):
        if not (line.startswith('SUSAP ') and line[12] == 'A' and line[21] in '01'):
            continue
        lat, lon = build_us_flight_paths.latlon(line)
        if s - AIRFIELD_PAD_DEG <= lat <= n + AIRFIELD_PAD_DEG and w - AIRFIELD_PAD_DEG <= lon <= e_ + AIRFIELD_PAD_DEG:
            out.append({'ident': line[6:10].strip(), 'name': line[93:123].strip(), 'ref': [lat, lon]})
    if not {f'K{code}' for code in AIRPORTS} <= {a['ident'] for a in out}:
        raise SystemExit('the airfield list lacks one of SFO, OAK, SJC: the airport records were not read')
    return sorted(out, key=lambda a: a['ident'])


# The FAA's abbreviations, spelt out for a reader who is not a pilot.
FAA_WORDS = {'Muni': 'Municipal', 'Exec': 'Executive', 'Intl': 'International', 'Fld': 'Field', 'Rgnl': 'Regional'}
NAME_WIDTH = 30  # the record's name field: a name this long has been cut short


def airfield_name(a):
    words = a['name'].title().split()
    if len(a['name']) >= NAME_WIDTH:
        words = words[:-1]  # the last word is a fragment ("REID-HILLVIEW OF SANTA CLARA C")
    return ' '.join(FAA_WORDS.get(w, w if w not in ('Of', 'The') else w.lower()) for w in words)


def patch_owners(noise, airfields, approaches):
    """{shaded patch: the airfields it belongs to}.

    A patch belongs to the airfield INSIDE it. Because BTS shades land only, an
    approach over water leaves a patch on the far shore with no airfield in
    it; that patch belongs to the airport whose drawn approach runs through it.
    Anything else is left unowned and the page names no airfield for it.

    NOT "the nearest airfield", which was the first version: Foster City's
    shading is San Francisco's runway 28 approach coming ashore, and the
    nearest airfield to it is San Carlos, three miles away and nothing to do
    with it.
    """
    owners = {}
    for a in airfields:
        patch = noise.patch_at(a['ref'][1], a['ref'][0])
        if patch:
            owners.setdefault(patch, []).append(a)
    by_ident = {a['ident']: a for a in airfields}
    ashore = {}
    for r in approaches:
        for lat, lon, _ in r['points']:
            patch = noise.patch_at(lon, lat)
            if patch and patch not in owners:
                ashore.setdefault(patch, set()).add(f'K{r["airport"]}')
    for patch, idents in ashore.items():
        owners[patch] = [by_ident[i] for i in sorted(idents)]
    return owners


def shading_airfield(noise, owners, sample):
    """The airfield most of a city's shading belongs to, or None where its patch has no owner."""
    votes = {}
    for lon, lat in sample:
        mine = owners.get(noise.patch_at(lon, lat))
        if not mine:
            ident = None
        elif len(mine) == 1:
            ident = mine[0]['ident']
        else:
            # Two airfields in one patch (Oakland's runs into Hayward's): the nearer of those two.
            x, y = xy(lon, lat)
            ident = min(mine, key=lambda a: math.dist((x, y), xy(a['ref'][1], a['ref'][0])))['ident']
        votes[ident] = votes.get(ident, 0) + 1
    if not votes:
        return None
    ident = max(sorted(votes, key=str), key=votes.get)
    return next((a for mine in owners.values() for a in mine if a['ident'] == ident), None)


# ---- the noise picture, read back -------------------------------------------


class Noise:
    def __init__(self, frame, path):
        from PIL import Image

        self.frame = frame
        self.image = Image.open(path).convert('RGBA')
        if self.image.size != (frame.w, frame.h):
            raise SystemExit(f'{path.name} is {self.image.size}, the frame is {(frame.w, frame.h)}: re-run --fetch')
        self.alpha = self.image.getchannel('A').point(lambda a: 255 if a else 0)
        self._patches = None
        self.colours = {
            check_noise_legend.hexcolour(c) for _, c in self.image.getcolors(maxcolors=frame.w * frame.h) if c[3] > 0
        }

    def patches(self):
        """Label each connected shaded patch, on a half-size copy.

        Half size (a block is shaded if any of its four pixels is) so that a
        one-pixel gap does not split a patch in two, and so that a pure-Python
        flood fill over the picture takes a second and not eight.
        """
        # reduce(2), not resize(): its blocks are exactly pixels 2k and 2k+1,
        # which is what patch_at() assumes. resize() to a rounded-up size
        # shifts the blocks by a fraction and left a few shaded pixels unlabelled.
        small = self.alpha.reduce(2).point(lambda a: 255 if a else 0)
        w, h = small.size
        cells = small.tobytes()
        label, count = [0] * (w * h), 0
        for start, shaded in enumerate(cells):
            if not shaded or label[start]:
                continue
            count += 1
            label[start] = count
            stack = [start]
            while stack:
                j = stack.pop()
                x = j % w
                for k in (j - 1 if x else -1, j + 1 if x < w - 1 else -1, j - w, j + w):
                    if 0 <= k < w * h and cells[k] and not label[k]:
                        label[k] = count
                        stack.append(k)
        return label, w, h

    def patch_at(self, lon, lat):
        """The label of the shaded patch at a point, or 0."""
        if self._patches is None:
            self._patches = self.patches()
        label, w, h = self._patches
        x, y = self.frame.pixel(lon, lat)
        if not (0 <= x < self.frame.w and 0 <= y < self.frame.h):
            return 0
        return label[(int(y) // 2) * w + int(x) // 2]

    def painted(self, lon, lat):
        x, y = self.frame.pixel(lon, lat)
        if not (0 <= x < self.frame.w and 0 <= y < self.frame.h):
            return False
        return self.alpha.getpixel((int(x), int(y))) > 0

    def share_pct(self, rings):
        """(percent of a shape's pixels the map paints, a sample of where). Even-odd, so holes are not counted."""
        from PIL import Image, ImageChops, ImageDraw

        pts = [[self.frame.pixel(*p) for p in r] for r in rings]
        xs = [x for r in pts for x, _ in r]
        ys = [y for r in pts for _, y in r]
        box = (
            max(0, math.floor(min(xs))),
            max(0, math.floor(min(ys))),
            min(self.frame.w, math.ceil(max(xs))),
            min(self.frame.h, math.ceil(max(ys))),
        )
        size = (box[2] - box[0], box[3] - box[1])
        if size[0] <= 0 or size[1] <= 0:
            return 0.0, []  # wholly off the picture
        mask = Image.new('1', size, 0)
        for r in pts:
            one = Image.new('1', size, 0)
            ImageDraw.Draw(one).polygon([(x - box[0], y - box[1]) for x, y in r], fill=1)
            mask = ImageChops.logical_xor(mask, one)
        total = mask.histogram()[-1]
        if not total:
            return 0.0, []
        both = ImageChops.logical_and(mask, self.alpha.crop(box).convert('1'))
        painted = both.histogram()[-1]
        # Every third painted pixel each way, as positions, for nearest_airfield().
        px = both.load()
        sample = [
            lonlat_of(self.frame.x0 + box[0] + x + 0.5, self.frame.y0 + box[1] + y + 0.5)
            for y in range(0, size[1], 3)
            for x in range(0, size[0], 3)
            if px[x, y]
        ]
        return 100.0 * painted / total, sample


# ---- everything the page says, worked out once ------------------------------


def facts(data, record):
    frame = Frame(data['frame']['px'])
    noise = Noise(frame, PAGE_DIR / data['noise']['file'])
    approaches, departures, undrawn = routes(record)
    owners = patch_owners(noise, data['airfields'], approaches)
    rows = []
    for p in data['places']:
        m = measure(Shape(p['rings']), approaches, departures)
        pct, sample = noise.share_pct(p['rings'])
        rows.append({**p, **m, 'noise_pct': pct, 'airfield': shading_airfield(noise, owners, sample)})
    on_noise, home, off_noise = {}, {}, []
    for r in approaches:
        pts = [q for q in r['points'] if q[2] <= APPROACH_CHECK_KM]
        share = sum(noise.painted(lon, lat) for lat, lon, _ in pts) / len(pts)
        on_noise[r['airport']] = max(on_noise.get(r['airport'], 0.0), share)
        if not noise.painted(r['line'][0][1], r['line'][0][0]):
            off_noise.append(f'{r["airport"]} {r["runway"]}')
    for code in AIRPORTS:
        lat, lon = record['airports'][code]['ref']
        home[code] = next((p['name'] for p in data['places'] if inside(p['rings'], lon, lat)), None)
    for r in rows:
        r['airports_inside'] = sorted(code for code, name in home.items() if name == r['name'])
    return {
        'frame': frame,
        'record': record,
        'approaches': approaches,
        'departures': departures,
        'undrawn': undrawn,
        'cities': [r for r in rows if r['kind'] != 'cdp'],
        'communities': [r for r in rows if r['kind'] == 'cdp'],
        'on_noise': on_noise,
        'off_noise': off_noise,
        'picture_colours': noise.colours,
        'home': home,
    }


def invariants(data, f):
    """What must be true before a page is written or passed. Returns the failures."""
    fails = []
    by_county = {}
    for c in f['cities']:
        by_county[c['county']] = by_county.get(c['county'], 0) + 1
    for name, want in COUNTIES.values():
        if by_county.get(name) != want:
            fails.append(f'{name} County: {by_county.get(name, 0)} cities and towns, and it has {want}')
    for p in f['cities'] + f['communities']:
        got = area_km2(p['rings'])
        # The boundary file is clipped to the shoreline, so the polygon is the
        # land plus any INLAND water: it must not be under the land area, nor
        # over land and water together.
        low, high = p['land_km2'] * (1 - AREA_TOLERANCE), (p['land_km2'] + p['water_km2']) * (1 + AREA_TOLERANCE)
        if not low <= got <= high:
            fails.append(f'{p["name"]}: the polygon is {got:.1f} km2, the Census prints {p["land_km2"]} km2 of land')
    for code in AIRPORTS:
        share = f['on_noise'].get(code, 0.0)
        if share < APPROACH_ON_NOISE:
            fails.append(
                f'{code}: its best-covered approach has {share:.0%} of its last {APPROACH_CHECK_KM:.0f} km on the '
                f'noise picture, under {APPROACH_ON_NOISE:.0%}: the picture or the routes are mis-placed'
            )
    if f['off_noise']:
        fails.append(
            f'runway thresholds off the noise picture: {", ".join(f["off_noise"])}. '
            'A runway end is the loudest place on the map; the picture or the routes are mis-placed'
        )
    for code in AIRPORTS:
        # Per airport, not a total: San Francisco alone has more coded
        # departures than the other two together, so a cycle that parsed
        # Oakland and San Jose as all radar vectors passed a floor on the sum.
        drawn = [sum(r['airport'] == code for r in f[kind]) for kind in ('approaches', 'departures')]
        if not all(drawn):
            fails.append(f'{code}: {drawn[0]} approaches and {drawn[1]} departures drawn: the record was not read')
    ramp = {c for _, c in check_noise_legend.scale_from_index('NOISE_SCALE_BTS')}
    if f['picture_colours'] - ramp:
        fails.append(
            f'the picture paints {sorted(f["picture_colours"] - ramp)}, which the key under the map does not show: '
            'NOISE_SCALE_BTS in index.html has changed since the picture was fetched'
        )
    if not (PAGE_DIR / SHARE_NAME).exists():
        fails.append(f'bay-area/{SHARE_NAME} is missing and the page names it: node scripts/render_bay_area_share.mjs')
    name = data['noise']['file']
    if hashlib.sha256((PAGE_DIR / name).read_bytes()).hexdigest() != data['noise']['sha256']:
        fails.append(f'{name} is not the picture {PLACES.name} was built with: re-run --fetch')
    if not name.startswith(NOISE_PREFIX) or data['noise']['sha256'][:10] not in name:
        fails.append(f'{name} is not named after its own content: re-run --fetch')
    stale = sorted(x.name for x in PAGE_DIR.glob(f'{NOISE_PREFIX}*.png') if x.name != name)
    if stale:
        fails.append(f'superseded pictures still in bay-area/, which the deploy would upload: {", ".join(stale)}')
    return fails


# ---- rendering --------------------------------------------------------------

e = html.escape


def miles(km):
    return f'{km * KM_MI:.1f}'


def hundreds(ft):
    return f'{round(ft / 100) * 100:,}'


def path_d(frame, rings):
    out = []
    for r in rings:
        pts, last = [], None
        for lon, lat in r:
            x, y = frame.svg(lon, lat)
            cur = (round(x, 1), round(y, 1))
            if cur != last:
                pts.append(f'{cur[0]:g} {cur[1]:g}')
                last = cur
        if len(pts) >= 3:
            out.append('M' + 'L'.join(pts) + 'Z')
    return ''.join(out)


def line_d(frame, line):
    return 'M' + 'L'.join(f'{x:.1f} {y:.1f}' for x, y in (frame.svg(lon, lat) for lat, lon in line))


def label_point(frame, rings):
    ring = main_ring(rings)
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1], strict=True):
        k = x1 * y2 - x2 * y1
        a += k
        cx += (x1 + x2) * k
        cy += (y1 + y2) * k
    return frame.svg(cx / (3 * a), cy / (3 * a))


def approach_cell(c):
    if not c['approaches']:
        return 'No'
    lowest = min(c['approaches'], key=c['approaches'].get)
    low = c['approaches'][lowest]
    names = ', '.join(sorted(c['approaches']))
    if lowest.split()[0] in c['airports_inside']:
        return f'Yes: {e(names)}. The airport is inside the city'
    if low < LOW_FT:
        return f'Yes: {e(names)}. Lowest under {LOW_FT} ft above the runway, beside the airport'
    return f'Yes: {e(names)}. Lowest about {hundreds(low)} ft above the runway'


def departure_cell(c):
    if not c['departures']:
        return 'No'
    by_airport = {}
    for d in c['departures']:
        code, name = d.split(' ', 1)
        by_airport.setdefault(code, []).append(name)
    return 'Yes: ' + e('; '.join(f'{code} {", ".join(names)}' for code, names in sorted(by_airport.items())))


def nearest_cell(c):
    if c['approaches'] or c['departures']:
        return 'Overhead'
    if c['nearest_km'] * KM_MI < 0.05:
        return f'Under 0.1 mi ({e(c["nearest"])})'
    return f'{miles(c["nearest_km"])} mi ({e(c["nearest"])})'


def noise_cell(c):
    if c['noise_pct'] <= 0:
        return 'None'
    if c['noise_pct'] < MIN_SHARE_PCT:
        return 'Under 1%'
    if 99.5 <= c['noise_pct'] < 100:
        return 'Over 99%'
    return f'{c["noise_pct"]:.0f}%'


def airfield_cell(c):
    """The airfield the city's shading belongs to (patch_owners), or that none could be named."""
    if c['noise_pct'] < MIN_SHARE_PCT:
        return ''
    return e(airfield_name(c['airfield'])) if c['airfield'] else 'Not identified'


def order(cities):
    # Any shading ranks above none: rounded to 1 dp, Hillsborough's 0.04% tied
    # with 0.0, and the tie fell to route distance, so 'Under 1%' sat below two
    # 'None' rows under a heading promising the noise-map order (audit
    # 2026-10-05 M-19). Rounding still keeps float noise from reordering ties.
    return sorted(cities, key=lambda c: (c['noise_pct'] <= 0, -round(c['noise_pct'], 1), c['nearest_km'], c['name']))


def render_map(f, data):
    frame = f['frame']
    out = [
        f'<svg viewBox="0 0 {MAP_W} {frame.height}" role="img" aria-labelledby="map-title map-desc" class="map">',
        '<title id="map-title">Map of the San Francisco Bay Area with the published flight routes of SFO, OAK and SJC</title>',
        '<desc id="map-desc">Fifty cities in four counties, the final approach to each runway, the coded departure '
        'routes and the 2022 aircraft noise map. The table below gives the same information city by city.</desc>',
        f'<rect width="{MAP_W}" height="{frame.height}" fill="#dfe7ea"/>',
    ]
    out += [f'<path d="{path_d(frame, c["rings"])}" fill="#efeeea" fill-rule="evenodd"/>' for c in data['land']]
    for p in f['communities']:
        out.append(
            f'<path d="{path_d(frame, p["rings"])}" fill="#f6f5f1" stroke="#b5b4ae" stroke-width="0.5" '
            f'stroke-dasharray="2 2" fill-rule="evenodd"><title>{e(p["name"])} (unincorporated)</title></path>'
        )
    for c in f['cities']:
        out.append(
            f'<path d="{path_d(frame, c["rings"])}" fill="#fbfaf8" stroke="#85847e" stroke-width="0.6" '
            f'fill-rule="evenodd"><title>{e(c["name"])}</title></path>'
        )
    out.append(
        f'<image href="/bay-area/{e(data["noise"]["file"])}" width="{MAP_W}" height="{frame.height}" opacity="0.8" '
        'preserveAspectRatio="none" style="pointer-events:none"/>'
    )
    out.append('<g fill="none" style="pointer-events:none">')
    out += [
        f'<path d="{line_d(frame, r["line"])}" stroke="#1d5fa8" stroke-width="1.1" opacity="0.8"/>'
        for r in f['departures']
    ]
    out += [f'<path d="{line_d(frame, r["line"])}" stroke="#141414" stroke-width="1.7"/>' for r in f['approaches']]
    out.append('</g>')

    # Labels: airports always; cities loudest first, skipping any that would sit on one already placed.
    placed = []

    def room(x, y, text, size):
        w, h = len(text) * size * 0.56, size * 1.25
        box = (x - w / 2 - 2, y - h / 2 - 1, x + w / 2 + 2, y + h / 2 + 1)
        if box[0] < 2 or box[2] > MAP_W - 2 or box[1] < 2 or box[3] > frame.height - 2:
            return False
        if any(box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in placed):
            return False
        placed.append(box)
        return True

    labels = []
    for code in AIRPORTS:
        lat, lon = f['record']['airports'][code]['ref']
        x, y = frame.svg(lon, lat)
        room(x + 22, y - 12, code, 13)
        labels.append(f'<rect x="{x - 4:.1f}" y="{y - 4:.1f}" width="8" height="8" fill="#f27d26" stroke="#141414"/>')
        labels.append(f'<text x="{x + 22:.1f}" y="{y - 8:.1f}" class="ap">{code}</text>')
    for c in sorted(f['cities'], key=lambda c: (-c['noise_pct'], -c['land_km2'])):
        x, y = label_point(frame, c['rings'])
        if room(x, y, c['name'], 9.5):
            labels.append(f'<text x="{x:.1f}" y="{y + 3:.1f}" class="ct">{e(c["name"])}</text>')
    out.append('<g style="pointer-events:none" text-anchor="middle">' + ''.join(labels) + '</g>')
    out.append('</svg>')
    return '\n'.join(out)


PAGE_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src https://gc.zgo.at; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data: https://cubitt33.goatcounter.com; connect-src https://cubitt33.goatcounter.com; base-uri 'self'; form-action 'self';">
<title>Bay Area flight paths: which cities are under the routes into SFO, Oakland and San Jose - Sky Score</title>
<meta name="description" content="The published landing and departure routes of San Francisco, Oakland and San Jose airports, drawn over {n} Bay Area cities from the FAA's own procedure file, with the federal aircraft noise map. {n_app} cities have a landing path overhead below 3,000 ft." />
<link rel="canonical" href="{site}/bay-area/" />
<meta property="og:type" content="article" />
<meta property="og:title" content="Which Bay Area cities are under a flight path?" />
<meta property="og:description" content="The FAA's published routes for SFO, Oakland and San Jose, drawn over {n} cities, with the federal aircraft noise map." />
<meta property="og:url" content="{site}/bay-area/" />
<meta property="og:image" content="{site}/bay-area/{share}" />
<meta property="og:image:width" content="1200" />
<meta property="og:image:height" content="630" />
<meta name="twitter:card" content="summary_large_image" />
<link rel="stylesheet" href="/fonts/fonts.css" />
<style>
  :root {{ color-scheme: light; --dark:#141414; --mid:#55554f; --line:#dcdbd6; --bg:#fafaf9; --link:#b03a0b; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:'Inter',system-ui,sans-serif; color:var(--dark); background:#fff; line-height:1.6; }}
  .wrap {{ max-width:980px; margin:0 auto; padding:24px 20px 64px; }}
  a {{ color:var(--link); }}
  nav.crumbs {{ font-size:12px; color:var(--mid); margin-bottom:20px; }}
  h1 {{ font-size:32px; line-height:1.15; letter-spacing:-0.02em; margin:0 0 8px; }}
  h2 {{ font-size:20px; margin:40px 0 8px; }}
  .sub {{ color:var(--mid); margin:0 0 24px; max-width:68ch; }}
  .figures {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px; margin:0 0 28px; padding:0; list-style:none; }}
  .figures li {{ border:1px solid var(--line); background:var(--bg); padding:14px 16px; }}
  .figures b {{ display:block; font-size:30px; line-height:1.1; letter-spacing:-0.02em; }}
  .figures span {{ font-size:13px; color:var(--mid); }}
  .map {{ display:block; width:100%; height:auto; border:1px solid var(--line); }}
  .map .ap {{ font:700 13px 'JetBrains Mono',ui-monospace,monospace; fill:#141414; paint-order:stroke; stroke:#fff; stroke-width:3px; }}
  .map .ct {{ font:500 9.5px 'Inter',system-ui,sans-serif; fill:#141414; paint-order:stroke; stroke:#fff; stroke-width:2.5px; }}
  /* The map is drawn 900 units wide, so on a phone it renders at about 40%: the city
     names came out 3-4px tall (audit 2026-10-05 M-19). Below 600px they go - the table
     beneath names every city - and the three airport codes grow to stay legible. */
  @media (max-width: 600px) {{ .map .ct {{ display:none; }} .map .ap {{ font-size:28px; stroke-width:6px; }} }}
  .key {{ display:flex; flex-wrap:wrap; gap:6px 22px; margin:10px 0 0; padding:0; list-style:none; font-size:13px; color:var(--mid); }}
  .key li {{ display:flex; align-items:center; gap:8px; }}
  .key i {{ display:inline-block; width:26px; height:0; border-top:2px solid #141414; }}
  .key i.dep {{ border-top-color:#1d5fa8; }}
  .key i.ap {{ width:9px; height:9px; border:1px solid #141414; background:#f27d26; }}
  .ramp {{ display:inline-flex; border:1px solid var(--line); }}
  .ramp b {{ width:16px; height:12px; }}
  .tw {{ overflow-x:auto; }}
  .tw:focus-visible {{ outline:2px solid var(--link); outline-offset:2px; }}
  table {{ width:100%; min-width:860px; border-collapse:collapse; font-size:13px; }}
  th, td {{ text-align:left; padding:8px; border-bottom:1px solid var(--line); vertical-align:top; }}
  th {{ font-weight:600; }}
  td.n {{ font-family:'JetBrains Mono',ui-monospace,monospace; white-space:nowrap; }}
  ul.notes {{ padding-left:20px; }}
  ul.notes li {{ margin:0 0 8px; max-width:78ch; }}
  .small {{ font-size:13px; color:var(--mid); max-width:78ch; }}
  footer {{ margin-top:40px; font-size:12px; color:var(--mid); }}
</style>
</head>
<body>
<div class="wrap">
<nav class="crumbs" aria-label="Breadcrumb"><a href="/">Sky Score</a> &rsaquo; Bay Area flight paths</nav>
<main>
<h1>Which Bay Area cities are under a flight path?</h1>
<p class="sub">The published landing and departure routes of San Francisco (SFO), Oakland (OAK) and San Jose (SJC), drawn over the {n} cities and towns of the four counties around them. The routes come from the FAA's own procedure file and the shading from the federal aircraft noise map. The figures in the table are measured from those two.</p>

<ul class="figures">
<li><b>{n_app} of {n}</b><span>cities have a published landing path overhead, below 3,000 ft</span></li>
<li><b>{n_dep} of {n}</b><span>have a coded departure route overhead, within {dep_mi} miles of the runway</span></li>
<li><b>{n_noise} of {n}</b><span>have at least 1% of their area on the federal aircraft noise map, from any airfield</span></li>
</ul>

{svg}
<ul class="key">
<li><i></i>Final approach, from 3,000 ft down to the runway</li>
<li><i class="dep"></i>Coded departure route, first {dep_mi} miles</li>
<li><i class="ap"></i>Airport</li>
<li><span class="ramp" aria-hidden="true">{ramp}</span>Aircraft noise, 2022: quieter to louder</li>
</ul>

<h2>City by city</h2>
<p class="small">Ordered by how much of each city the federal noise map shades. That map is the better guide to what is actually flown, but it covers every airfield the Bureau models, not only these three, so each row names the airfield its shading belongs to. Heights are of landing aircraft on the published glide path, above the runway, to the nearest 100 ft.</p>
<div class="tw" tabindex="0" role="region" aria-label="City by city table, scrolls sideways on a narrow screen">
<table>
<caption style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)">Flight routes and mapped aircraft noise for {n} Bay Area cities</caption>
<thead><tr><th scope="col">City</th><th scope="col">County</th><th scope="col">Share of city on the noise map</th><th scope="col">Airfield that shading belongs to</th><th scope="col">Landing path overhead</th><th scope="col">Departure route overhead</th><th scope="col">Nearest drawn route</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
</div>

{communities}

<h2>How to read this</h2>
<ul class="notes">
<li><strong>The lines are published routes, not radar tracks.</strong> Aircraft fly either side of them, and a city with no line can still hear aircraft.</li>
<li><strong>This shows where the routes are, not how many aircraft use them.</strong> Which runways are in use depends on the wind, and the FAA's file does not say how often each is flown. The noise shading is the better guide to that.</li>
<li><strong>Landing lines</strong> are each runway's final approach, from 3,000 ft down to the runway, at the glide angle the FAA publishes. "SFO 28L" means runway 28 Left at San Francisco. {undrawn}</li>
<li><strong>Departure lines</strong> are the coded departure procedures, drawn for their first {dep_mi} miles, or as far as their named waypoints go if that is less: where controllers take over and steer aircraft by radar, the line stops. Names such as GAPP7 are the FAA's own names for them.</li>
<li><strong>Heights are above the runway, not above the ground.</strong> A city on a hill is closer to the aircraft than its figure says. Read each figure as give or take 100 ft.</li>
<li><strong>Arrivals further out are not drawn.</strong> Before the final approach, aircraft descending towards an airport are steered by air traffic control, higher up and over a wide area. Cities under those arrival streams show no line here.</li>
<li><strong>The noise shading</strong> is the aviation layer of the National Transportation Noise Map, 2022 edition, from the US Bureau of Transportation Statistics. It is a modelled 24-hour average, drawn over land only (which is why an approach over the bay has no shading until it reaches the shore), and it includes airfields this page draws no routes for, such as Livermore's and Hayward's own. The table names, for each city, the airfield inside its patch of shading; where water cuts a patch off from its airport, it is named for the airport whose approach runs through it, and where a patch holds two airfields, for the nearer. The Bureau publishes it to track trends and says it should not be used to evaluate noise at an individual location, so this page gives a share of a whole city and never a figure for an address.</li>
<li><strong>City outlines are approximate.</strong> They are the Census Bureau's generalised boundaries, good to a few hundred feet, so treat anything right on a city line as approximate.</li>
<li><strong>Cities only.</strong> The table lists incorporated cities and towns in San Francisco, San Mateo, Santa Clara and Alameda counties. {homes}</li>
</ul>

<h2>Sources</h2>
<p class="small"><strong>Flight procedures:</strong> FAA Coded Instrument Flight Procedures (CIFP), cycle {cycle}, effective {effective}. The FAA supplies the CIFP "as is", without warranty of any kind, and neither the FAA nor its personnel is liable for its content or for any use made of it. This page is not for navigation.<br />
<strong>Aircraft noise:</strong> US Department of Transportation, Bureau of Transportation Statistics, National Transportation Noise Map 2022.<br />
<strong>City and county boundaries:</strong> US Census Bureau cartographic boundary files, {vintage}.</p>

<h2>About Sky Score</h2>
<p class="small">Sky Score shows aircraft noise, air quality and flood risk for homes, from official open data. It covers city regions across England, and New York, on <a href="/">the map</a>. Full scores for each Bay Area city are in progress. If your city is not here, or something on this page looks wrong, write to <a href="mailto:support@skyscore.co.uk">support@skyscore.co.uk</a>.</p>
</main>
<footer>
<p><a href="/">Sky Score</a> &middot; <a href="/area/">All areas</a> &middot; <a href="/open-data/">Open data</a> &middot; <a href="/api/">For developers</a> &middot; <a href="/privacy">Privacy</a></p>
</footer>
</div>
<script data-goatcounter="https://cubitt33.goatcounter.com/count" async src="https://gc.zgo.at/count.js"></script>
</body>
</html>
"""


def render(data, record):
    f = facts(data, record)
    fails = invariants(data, f)
    if fails:
        raise SystemExit('the inputs fail their own checks:\n  ' + '\n  '.join(fails))
    cities = order(f['cities'])
    rows = '\n'.join(
        f'<tr><th scope="row">{e(c["name"])}</th><td>{e(c["county"])}</td><td class="n">{noise_cell(c)}</td>'
        f'<td>{airfield_cell(c)}</td>'
        f'<td>{approach_cell(c)}</td><td>{departure_cell(c)}</td><td>{nearest_cell(c)}</td></tr>'
        for c in cities
    )
    under = sorted(c['name'] for c in f['communities'] if c['approaches'] or c['departures'])
    communities = ''
    if under:
        communities = (
            '<p class="small"><strong>Not cities, but under a route:</strong> '
            f'{len(under)} unincorporated communities in these counties have a drawn route overhead: '
            f'{e(", ".join(under))}. They are outlined with a dashed line on the map.</p>'
        )
    undrawn = ''
    if f['undrawn']:
        undrawn = (
            f'{len(f["undrawn"])} runway ends have no published glide angle and are not drawn: '
            f'{e(", ".join(f["undrawn"]))}.'
        )
    homes = ' '.join(
        f'{AIRPORT_NAMES[code]} airport ({code}) is inside the city of {city}.'
        if city
        else f'{AIRPORT_NAMES[code]} airport ({code}) is on unincorporated land, inside no city.'
        for code, city in f['home'].items()
    )
    ramp = ''.join(f'<b style="background:{c}"></b>' for _, c in check_noise_legend.scale_from_index('NOISE_SCALE_BTS'))
    return PAGE_HTML.format(
        site=SITE,
        share=SHARE_NAME,
        n=len(cities),
        n_app=sum(bool(c['approaches']) for c in cities),
        n_dep=sum(bool(c['departures']) for c in cities),
        n_noise=sum(c['noise_pct'] >= MIN_SHARE_PCT for c in cities),
        dep_mi=f'{DEPARTURE_KM * KM_MI:.0f}',
        svg=render_map(f, data),
        ramp=ramp,
        rows=rows,
        communities=communities,
        undrawn=undrawn,
        homes=e(homes),
        cycle=e(record['cycle']),
        effective=e(record['effective']),
        vintage=e(data['vintage']),
    )


def load():
    if not PLACES.exists():
        raise SystemExit(f'{PLACES.name} is missing: run --fetch')
    data = json.loads(PLACES.read_text(encoding='utf-8'))
    if not (PAGE_DIR / data['noise']['file']).exists():
        raise SystemExit(f'bay-area/{data["noise"]["file"]} is missing: run --fetch')
    record = json.loads(build_us_flight_paths.RECORD.read_text(encoding='utf-8'))
    return data, record


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--fetch', action='store_true', help='rebuild the boundaries and the noise picture, then write')
    ap.add_argument('--write', action='store_true', help='render the page from the checked-in inputs')
    ap.add_argument('--check', action='store_true', help='fail if the page is not what its inputs render')
    args = ap.parse_args()

    if args.fetch:
        fetch()
    if args.fetch or args.write:
        page = render(*load())
        PAGE_DIR.mkdir(exist_ok=True)
        PAGE.write_text(page, encoding='utf-8', newline='\n')
        print(f'wrote {PAGE.relative_to(ROOT).as_posix()} ({len(page.encode("utf-8")):,} bytes)')
        return 0
    if args.check:
        page = render(*load())
        current = PAGE.read_text(encoding='utf-8').replace('\r\n', '\n') if PAGE.exists() else None
        if current != page:
            print(f'FAIL: {PAGE.relative_to(ROOT).as_posix()} is not what its inputs render - run --write')
            return 1
        data, record = load()
        cities = sum(p['kind'] != 'cdp' for p in data['places'])
        print(
            f'{PAGE.relative_to(ROOT).as_posix()}: {cities} cities, CIFP cycle {record["cycle"]}, '
            'page matches its inputs; areas agree with the Census and the approaches lie on the noise picture'
        )
        return 0
    ap.print_help()
    return 2


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.exit(main())
