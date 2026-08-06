#!/usr/bin/env python3
"""Snapshot every Greater London healthcare POI from OSM into a bundled dataset.

WHY. /nhs proxied Overpass on every request, and it kept falling back to nhs.uk
links. The query was not the problem — the identical query with identical
headers returns 200 in ~2s from a laptop. Lambda egress uses AWS-managed shared
IPs, so we compete for Overpass's per-IP budget with everything else on AWS. No
amount of query tuning fixes an address we do not control.

Mirrors are not the answer either. Measured 2026-08-06: overpass.kumi.systems
timed out at 60s, and overpass.osm.ch returned **200 with zero elements** for a
London query. That last one is the dangerous case — a silent empty result
renders as "no healthcare nearby", which is a lie rather than an error.

So: fetch once, ship the data, stop making a live third-party call on the hot
path. Same move as the DEFRA rasters. The whole of Greater London is 3,360
elements — the runtime dependency was never justified by the data volume.

/nhs keeps its live-Overpass path for coordinates OUTSIDE this snapshot's bbox
(the extension's Manchester case), where the fallback links remain correct
behaviour.

Refresh cadence: healthcare locations move on a timescale of years. Re-run when
convenient; nothing breaks if it is stale by months.

  python scripts/fetch_london_healthcare.py
"""

import json
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

OVERPASS = 'https://overpass-api.de/api/interpreter'

# Greater London plus a margin, so a property at the edge still has neighbours
# in every direction rather than a hard cut that looks like sparse coverage.
BBOX = (51.25, -0.55, 51.72, 0.35)

OUT = Path(__file__).resolve().parents[1] / 'backend' / 'lambdas' / 'nhs' / 'london_healthcare.json'

QUERY = (
    f'[out:json][timeout:180];'
    f'(nwr["amenity"~"^(hospital|pharmacy|doctors|clinic)$"]'
    f'({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]}););'
    f'out center tags;'
)


def coords(el):
    if el.get('type') == 'node':
        return el.get('lat'), el.get('lon')
    c = el.get('center') or {}
    return c.get('lat'), c.get('lon')


def main():
    # --from-file <path> reprocesses a previously saved Overpass response.
    #
    # Not a convenience. Overpass allows 2 concurrent slots per IP and running
    # this twice inside a minute earns a 504 — which happened while building it.
    # Re-querying a free shared service to fix a bug in our own trimming code is
    # rude and slow, so the download and the transform are separable.
    argv = sys.argv[1:]
    if '--from-file' in argv:
        src = Path(argv[argv.index('--from-file') + 1])
        print(f'reading saved response: {src}')
        elements = json.loads(src.read_text(encoding='utf-8')).get('elements', [])
    else:
        req = Request(
            OVERPASS,
            data=urlencode({'data': QUERY}).encode(),
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'sky-score/1.0 (https://d1oe4ftwutjpf.cloudfront.net)',
            },
        )
        print('one bulk query for Greater London...')
        with urlopen(req, timeout=240) as resp:
            elements = json.loads(resp.read().decode()).get('elements', [])
    print(f'  {len(elements)} elements')

    # Trim to exactly what the Lambda serves. Keeping the raw payload would
    # triple the bundle for tags nothing reads.
    rows = []
    for el in elements:
        tags = el.get('tags') or {}
        name = tags.get('name')
        lat, lon = coords(el)
        if not name or lat is None or lon is None:
            continue
        parts = [tags.get('addr:housenumber'), tags.get('addr:street')]
        rows.append(
            {
                'a': tags.get('amenity'),
                'n': name,
                'lat': round(float(lat), 6),
                'lon': round(float(lon), 6),
                'ad': ' '.join(p for p in parts if p).strip(),
                'pc': tags.get('addr:postcode', ''),
                'ph': tags.get('phone') or tags.get('contact:phone', ''),
                'w': tags.get('website') or tags.get('contact:website', ''),
            }
        )

    # Deterministic order so a re-run with unchanged upstream data produces a
    # byte-identical file and does not show up as a spurious diff.
    rows.sort(key=lambda r: (r['a'], r['n'], r['lat'], r['lon']))

    payload = {'bbox': list(BBOX), 'count': len(rows), 'items': rows}
    OUT.write_text(json.dumps(payload, separators=(',', ':')), encoding='utf-8')

    by = {}
    for r in rows:
        by[r['a']] = by.get(r['a'], 0) + 1
    print(f'  kept {len(rows)} named POIs: {by}')
    print(f'  wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
