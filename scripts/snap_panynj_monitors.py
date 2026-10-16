"""Snap New York's monitor positions onto the streets the Port Authority names (2026-10-16).

The report maps place a monitor only roughly: checked against OpenStreetMap, 13 of 21
map-derived positions lay within 150 m of their named street and 8 lay 238-648 m away,
spread over all four maps although each map's calibration was stable to tens of metres.
The pins are illustrative. The site table is authoritative about WHICH street; the pin
says roughly WHERE along it. So a monitor is placed at the nearest point on its named
street to its pin, and the snap distance is recorded as the uncertainty of the pin.
A monitor whose street cannot be found within 1 km keeps its pin and is marked
'street_verified': false, so the fit can leave it out.

Network: Overpass (OpenStreetMap, ODbL; only street geometry is read, and nothing is stored
but the snapped point, which is credited in the data file and LICENSING.md). ONE combined query, two public endpoints, retried.
Writes the result into data/us-noise-monitors.json ('NYC').
"""

import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / 'data' / 'us-noise-monitors.json'
ENDPOINTS = ('https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter')
UA = 'SkyScore-monitor-check/1.0 (support@skyscore.co.uk)'

# The street each site table names, as an OSM name pattern (case-insensitive).
STREET = {
    'L13_P': r'^39th Av', 'L22_P': r'^78th St', 'LFRNKLN': r'^Franklin Av', 'LCLGPT': r'^23rd Av',
    'L192FM': r'^192nd St', 'L78STJH': r'^78th St',
    'J13RP': r'Peppe', 'J13LP': r'^Broad St', 'J04BP': r'^147th St', 'J31RP': r'^150th Av',
    'J31LP': r'^Russell St', 'J22RP': r'^Almeda Av', 'CEDAH': r'Hanlon', 'ATL65': r'Plaza',
    'FLPRK': r'^Floral P', 'ARV64': r'^Beach 65', 'JMLVRN': r'^Hempstead Av', 'JOLDBRK': r'^Valentine',
    'JEHLS': r'^Harbor Hill', 'JHB165AV': r'^165th Av', 'J132BH': r'^Beach 132', 'JVLSTRM': r'^Nottingham',
    'JNHPRK': r'^Evergreen', 'JELMNT': r'^Fallon',
    'E22BP': r'^(3rd|Third) Av', 'E04BP': r'^Magazine St', 'E29_P': r'^Chancellor Av',
    'RMS01': r'^7th St', 'RMS02': r'^Hamilton St', 'RMS03': r'^Prospect Av', 'RMS04': r'^Park St',
    'RMS05': r'^Highwood', 'RMS06': r'^Joseph St',
}


def query_all(monitors, radius=1000):
    """ONE request for every monitor's named street (a busy public server answered one
    query every few minutes on 2026-10-16; 32 of them would have taken hours)."""
    parts = ''.join(f'way(around:{radius},{m["pin_lat"]},{m["pin_lon"]})["highway"]["name"~"{STREET[m["id"]]}",i];'
                    for m in monitors)
    q = f'[out:json][timeout:180];({parts});out geom;'
    data = urllib.parse.urlencode({'data': q}).encode()
    for attempt in range(6):
        url = ENDPOINTS[attempt % 2]
        try:
            req = urllib.request.Request(url, data=data, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.load(r)['elements']
        except Exception as e:  # noqa: BLE001 - a busy public server; retry, then report
            print(f'    retry {attempt + 1}: {e}')
            time.sleep(10 + 10 * attempt)
    return None


def nearest_on(lat, lon, ways):
    """(metres, snapped lat, snapped lon, street name) to the nearest named segment."""
    k = 111320 * math.cos(math.radians(lat))
    best = (math.inf, None, None, None)
    for w in ways:
        g = [(p['lat'], p['lon']) for p in w.get('geometry', [])]
        for a, b in zip(g, g[1:], strict=False):
            ax, ay = (a[1] - lon) * k, (a[0] - lat) * 111320
            bx, by = (b[1] - lon) * k, (b[0] - lat) * 111320
            dx, dy = bx - ax, by - ay
            t = max(0.0, min(1.0, -(ax * dx + ay * dy) / max(dx * dx + dy * dy, 1e-9)))
            px, py = ax + t * dx, ay + t * dy
            d = math.hypot(px, py)
            if d < best[0]:
                best = (d, lat + py / 111320, lon + px / k, w['tags'].get('name'))
    return best


def main():
    d = json.loads(DATA.read_text(encoding='utf-8'))
    block = d['airports']['NYC']
    for m in block['monitors']:
        if 'pin_lat' not in m:  # keep the map-derived pin once, whatever reruns do
            m['pin_lat'], m['pin_lon'] = m['lat'], m['lon']
    ways = query_all(block['monitors'])
    if ways is None:
        print('Overpass did not answer; nothing written')
        return 1
    for m in block['monitors']:
        rx = re.compile(STREET[m['id']], re.IGNORECASE)
        mine = [w for w in ways if rx.search(w.get('tags', {}).get('name', ''))]
        dist, slat, slon, name = nearest_on(m['pin_lat'], m['pin_lon'], mine)
        if slat is None or dist > 1000:
            print(f"{m['id']:9} UNVERIFIED: no '{STREET[m['id']]}' within 1 km of the pin")
            m['street_verified'] = False
            m['lat'], m['lon'] = m['pin_lat'], m['pin_lon']
            m.pop('street', None)
            m.pop('snap_m', None)
        else:
            print(f"{m['id']:9} snapped {dist:5.0f} m onto {name}")
            m['street_verified'] = True
            m['street'] = name
            m['snap_m'] = round(dist)
            m['lat'], m['lon'] = round(slat, 5), round(slon, 5)
    block['positions_from'] = (
        'the report maps place a pin only roughly, so each monitor is the nearest point on the street its site table '
        "names to its map pin (scripts/snap_panynj_monitors.py, OpenStreetMap geometry, (c) OpenStreetMap contributors, ODbL 1.0); snap_m is how far the pin was "
        'from that street; pin_lat/pin_lon is the map-derived pin (scripts/georef_panynj_monitors.py: pins detected, '
        'maps calibrated symmetrically on the FAA runway thresholds at three colour thresholds; position_spread_m is how '
        "far a pin moves between those calibrations). street_verified false or null: the street was not confirmed, and "
        'the monitor is left out of any fit')
    with open(DATA, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(d, fh, indent=2, ensure_ascii=False)
        fh.write('\n')
    ok = sum(1 for m in block['monitors'] if m.get('street_verified'))
    print(f'verified {ok} of {len(block["monitors"])}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
