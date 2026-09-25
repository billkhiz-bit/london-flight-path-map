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
(GetStyles), and NOISE_SCALE_BTS equals BTS's own legend swatches. This is what
catches a publisher restyling a layer under us.

    python scripts/check_noise_legend.py [--live]
"""

import base64
import io
import json
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
BTS_LEGEND = 'https://geo.dot.gov/server/rest/services/Hosted/NTAD_Noise_2020_CONUS_Aviation/MapServer/legend?f=json'
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
    return fails


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', 'replace')


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
    try:
        legend = json.loads(fetch(BTS_LEGEND))
        rows = next(L['legend'] for L in legend['layers'] if L['layerId'] == 3)
        published = []
        for row in rows:
            px = Image.open(io.BytesIO(base64.b64decode(row['imageData']))).convert('RGBA').getdata()
            colour = Counter(hexcolour(p) for p in px if p[3] > 0).most_common(1)[0][0]
            low = int(float(re.findall(r'[\d.]+', row['label'])[0]))
            published.append((low, colour))
        if published != bts:
            fails.append(f'BTS legend differs from NOISE_SCALE_BTS:\n      BTS  {published}\n      site {bts}')
        print(f'  live: BTS legend {len(published)} bands compared')
    except Exception as exc:  # noqa: BLE001
        fails.append(f'could not read BTS legend ({exc})')
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
