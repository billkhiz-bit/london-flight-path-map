"""The aircraft-noise legend must describe the colours the map actually paints.

WHY THIS EXISTS (2026-09-25)
----------------------------
For months the legend beside the aircraft-noise overlay was five static rows -
55-59 blue, 60-64 mint, 65-69 yellow, 70-74 orange, 75+ red - describing a
palette that neither overlay uses. DEFRA's Round 4 style is ten intervals from
40 dB in teal, green, peach and plum, and the served London PNG's largest area
is 50-55 dB: the pale green halo the old legend labelled 60-64. Every visitor
read the map 10-15 dB louder than DEFRA published. New York's BTS layer is a
third palette again. Nothing compared the legend to the image, because the
legend was prose and the image was a file.

WHAT IT CHECKS
--------------
Offline (the default, blocking): every opaque colour in
data/aircraft-noise-london-lden.png appears in NOISE_SCALE_DEFRA_LDEN, and every
band of that scale appears in the image. Both directions, because a legend can
be wrong by describing a colour the map never paints as easily as by missing
one it does.

--live (network): NOISE_SCALE_DEFRA_LDEN equals DEFRA's own ColorMap
(GetStyles), and the colours of NOISE_SCALE_BTS equal the colours BTS's tiles
actually paint. This is what catches a publisher restyling a layer under us.

THE BTS HALF CHANGED ON 2026-10-02, AND IT IS WEAKER THAN IT WAS. It used to
read BTS's own legend from geo.dot.gov and compare colour AND decibel band.
That host stopped answering, and the service BTS now publishes (the 2022
edition, on tiles.arcgis.com) is a tile cache with NO legend endpoint. So this
half samples tiles over five large airports and compares COLOURS, both
directions. The band VALUES in NOISE_SCALE_BTS (45, 50, 55, 60, 70, 80, 90) are
what the 2020 service's legend published when they were copied on 2026-09-25;
the 2022 tiles use the same seven colours, but nothing published and
machine-readable says the 2022 breaks are the same, and bts.gov answers 403 to
a script. If BTS ever publishes a legend for the tile service, compare the
values again.

    python scripts/check_noise_legend.py [--live]
"""

import io
import json
import math
import re
import sys
import urllib.request
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / 'index.html'
LONDON_PNG = ROOT / 'data' / 'aircraft-noise-london-lden.png'
DEFRA_STYLES = (
    'https://environment.data.gov.uk/spatialdata/airport-noise-all-metrics-england-round-4/wms'
    '?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetStyles&LAYERS=Airport_Noise_ALL_Lden'
)
# BTS's 2022 aviation noise tiles: the service index.html's US_MAP_SERVICES
# names, read from there so the two cannot drift.
BTS_TILE_ZOOM = 11
# Large airports, so every band up to the loudest is painted somewhere.
BTS_SAMPLES = {
    'JFK': (40.6413, -73.7781),
    'LAX': (33.9416, -118.4085),
    'ORD': (41.9742, -87.9073),
    'SFO': (37.6213, -122.3790),
    'ATL': (33.6407, -84.4277),
}
# Fewer tiles than this and the source was not really read.
BTS_MIN_TILES = 3
# A colour on this many pixels across the samples counts as painted.
BTS_MIN_PIXELS = 5
# DEFRA draws <=40 dB white at 0.5; the layer's multiply blend renders it as
# nothing, so the site's scale omits it and this check must too.
DEFRA_INVISIBLE = {'#FFFFFF'}
# A rendered image carries a few stray pixels at band edges; a colour must
# cover more than this share of the opaque area to count as painted.
MIN_SHARE = 0.0005
UA = {'User-Agent': 'Mozilla/5.0 (Sky Score noise-legend check)'}


def hexcolour(pixel):
    """An RGB(A) pixel as #RRGGBB, the form both styles publish."""
    r, g, b = pixel[:3]
    return f'#{r:02X}{g:02X}{b:02X}'


def scale_from_index(name):
    """The (from, colour) bands of one NOISE_SCALE_* constant in index.html."""
    src = INDEX.read_text(encoding='utf-8')
    m = re.search(rf'const {name} = \[(.*?)\]\.map', src, re.S)
    if not m:
        sys.exit(f'FAIL: {name} not found in index.html')
    bands = [(int(f), c.upper()) for f, c in re.findall(r"from: (\d+), colour: '(#[0-9A-Fa-f]{6})'", m.group(1))]
    if len(bands) < 3:
        sys.exit(f'FAIL: parsed only {len(bands)} bands from {name}; the pattern has probably stopped matching')
    return bands


def check_png(defra):
    im = Image.open(LONDON_PNG).convert('RGBA')
    counts = Counter(hexcolour(p) for p in im.getdata() if p[3] > 0)
    total = sum(counts.values())
    painted = {c for c, n in counts.items() if n / total > MIN_SHARE} - DEFRA_INVISIBLE
    legend = {c for _, c in defra}
    fails = []
    for c in sorted(painted - legend):
        fails.append(f'the map paints {c} ({counts[c] / total:.1%} of the overlay) and the legend has no band for it')
    for c in sorted(legend - painted):
        fails.append(f'the legend shows {c} and the London overlay never paints it')
    print(f'  offline: {len(painted)} colours painted in {LONDON_PNG.name}, {len(legend)} legend bands')
    # EVERY OTHER CITY'S PNG (2026-09-26, scripts/build_aircraft_rasters.py).
    # One direction only: every colour a city paints must be a legend band.
    # The reverse is a London property - a smaller airport never reaches the
    # loudest intervals, so "every band painted" would fail on a true map.
    meta_path = ROOT / 'data' / 'aircraft-noise-rasters.json'
    if meta_path.exists():
        for m in json.loads(meta_path.read_text(encoding='utf-8'))['cities'].values():
            png = ROOT / m['png'].lstrip('/')
            cim = Image.open(png).convert('RGBA')
            cc = Counter(hexcolour(p) for p in cim.getdata() if p[3] > 0)
            ct = sum(cc.values())
            cp = {c for c, n in cc.items() if n / ct > MIN_SHARE} - DEFRA_INVISIBLE
            for c in sorted(cp - legend):
                fails.append(f'{png.name} paints {c} ({cc[c] / ct:.1%} of it) and the legend has no band for it')
            print(f'  offline: {len(cp)} colours painted in {png.name}, all must be legend bands')
    return fails


def fetch_bytes(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def fetch(url):
    return fetch_bytes(url).decode('utf-8', 'replace')


def bts_tile_service():
    """The aircraft tile service index.html actually requests."""
    src = INDEX.read_text(encoding='utf-8')
    m = re.search(r"const US_MAP_SERVICES = \{\s*aircraft: \{.*?url: '([^']+)'", src, re.S)
    if not m:
        sys.exit('FAIL: US_MAP_SERVICES.aircraft.url not found in index.html')
    return m.group(1)


def bts_painted_colours():
    """(colours BTS's tiles paint over the sample airports, tiles read)."""
    base = bts_tile_service()
    n = 2**BTS_TILE_ZOOM
    counts = Counter()
    tiles = 0
    for name, (lat, lon) in BTS_SAMPLES.items():
        x = int((lon + 180) / 360 * n)
        y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
        try:
            im = Image.open(io.BytesIO(fetch_bytes(f'{base}/tile/{BTS_TILE_ZOOM}/{y}/{x}'))).convert('RGBA')
        except Exception as exc:  # noqa: BLE001 - counted below; one airport's tile may be missing
            print(f'  live: BTS tile over {name} not read ({exc})')
            continue
        counts.update(hexcolour(p) for p in im.getdata() if p[3] > 0)
        tiles += 1
    # An absolute floor, NOT MIN_SHARE. The loudest band (90 dB and over) is a
    # few dozen pixels at the runway ends, a share far under MIN_SHARE, and the
    # share test silently dropped it - so a legend missing that band passed.
    # These tiles carry no blended edge pixels (eight exact colours, measured),
    # so a handful of pixels is a painted band, not noise.
    return {c for c, k in counts.items() if k >= BTS_MIN_PIXELS}, tiles


def check_live(defra, bts):
    fails = []
    try:
        sld = fetch(DEFRA_STYLES)
        entries = re.findall(r'ColorMapEntry color="(#[0-9A-Fa-f]{6})" opacity="[\d.]+" quantity="(\d+)"', sld)
        # An interval entry's quantity is its UPPER bound, so its lower bound is
        # the previous entry's quantity.
        published = [
            (int(entries[i - 1][1]), entries[i][0].upper())
            for i in range(1, len(entries))
            if entries[i][0].upper() not in DEFRA_INVISIBLE
        ]
        if published != defra:
            fails.append(
                f'DEFRA style differs from NOISE_SCALE_DEFRA_LDEN:\n      DEFRA {published}\n      site  {defra}'
            )
        print(f'  live: DEFRA ColorMap {len(published)} bands compared')
    except Exception as exc:  # noqa: BLE001 - reported as a failure, never swallowed
        fails.append(f'could not read DEFRA style ({exc})')
    painted, tiles = bts_painted_colours()
    legend = {c for _, c in bts}
    if tiles < BTS_MIN_TILES:
        # Unreadable is a FAILURE here, never a pass: this is the half that
        # reported nothing while the old host was already dead.
        fails.append(f'could not read BTS tiles ({tiles} of {len(BTS_SAMPLES)} sample tiles answered)')
    else:
        for c in sorted(painted - legend):
            fails.append(f'BTS tiles paint {c} and NOISE_SCALE_BTS has no band for it')
        for c in sorted(legend - painted):
            fails.append(f'NOISE_SCALE_BTS shows {c} and no sampled BTS tile paints it')
        print(f'  live: BTS tiles {len(painted)} colours painted over {tiles} airports, {len(legend)} legend bands')
    return fails


def main():
    defra = scale_from_index('NOISE_SCALE_DEFRA_LDEN')
    bts = scale_from_index('NOISE_SCALE_BTS')
    print('Aircraft-noise legend vs what the map paints:')
    fails = check_png(defra)
    if '--live' in sys.argv:
        fails += check_live(defra, bts)
    if fails:
        for f in fails:
            print(f'  FAIL {f}')
        sys.exit(1)
    print('  ok   the legend describes the overlay')


if __name__ == '__main__':
    main()
