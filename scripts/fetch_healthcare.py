#!/usr/bin/env python3
"""Snapshot the healthcare POIs of every UK area we cover from OSM into one bundled dataset.

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
path. Same move as the DEFRA rasters.

EVERY UK AREA, NOT LONDON ONLY (2026-10-27). Until then only Greater London was
bundled, and every other point went to live Overpass: in October the map's
Manchester centre alone fell back to links 147 times, some after waiting up to
26 s (the Lambda-duration alarm's main cause). The areas are DERIVED from the
boundary files the site and the API score with (data/*-boroughs.json), each as
its bounding box plus MARGIN_KM so a home near the edge still has neighbours
over it; a file outside Great Britain's extent (New York) is skipped, since
/nhs is UK healthcare. Greater London's derived box reproduces the one this
script used to type (51.25..51.72 by -0.55..0.35) to within 0.03 degrees.

An area answering fewer than MIN_NAMED named services is REFUSED, never
written: the empty success above is the failure this guards, and a city's real
count is in the hundreds.

Refresh cadence: healthcare locations move on a timescale of years. Re-run when
convenient; nothing breaks if it is stale by months.

  python scripts/fetch_healthcare.py                # one polite query per area, every area
  python scripts/fetch_healthcare.py --resume       # after a failed run: query only the areas not yet saved
  python scripts/fetch_healthcare.py --from-raw     # rebuild from the saved responses, no query at all
"""

import json
import math
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OVERPASS = 'https://overpass-api.de/api/interpreter'
OUT = ROOT / 'backend' / 'lambdas' / 'nhs' / 'healthcare.json'
RAW = ROOT / 'data' / 'healthcare-raw'  # gitignored (data/*): Overpass's answers, for --from-raw
MARGIN_KM = 3.0
GB = (49.8, -8.7, 60.9, 1.8)  # Great Britain's extent (lat, lon): an area wholly inside it is UK
MIN_NAMED = 100  # measured 2026-10-27: the smallest area, Greater Norwich, keeps 220; London 3,291
PAUSE_S = 15  # Overpass allows 2 slots per IP; one query at a time, with a gap, is the polite use

AMENITIES = ('hospital', 'pharmacy', 'doctors', 'clinic')


def _points(coords, out):
    if isinstance(coords[0], (int, float)):
        out.append(coords)
    else:
        for c in coords:
            _points(c, out)
    return out


def areas(data_dir=ROOT / 'data'):
    """{name: (south, west, north, east)} for every UK boundary file, widened by MARGIN_KM."""
    found = {}
    for path in sorted(data_dir.glob('*-boroughs.json')):
        pts = []
        for feature in json.loads(path.read_text(encoding='utf-8'))['features']:
            _points(feature['geometry']['coordinates'], pts)
        lons, lats = [p[0] for p in pts], [p[1] for p in pts]
        s, w, n, e = min(lats), min(lons), max(lats), max(lons)
        if not (GB[0] <= s and n <= GB[2] and GB[1] <= w and e <= GB[3]):
            continue
        dlat = MARGIN_KM / 111.0
        dlon = MARGIN_KM / (111.0 * math.cos(math.radians((s + n) / 2)))
        found[path.name.removesuffix('-boroughs.json')] = (
            round(s - dlat, 3), round(w - dlon, 3), round(n + dlat, 3), round(e + dlon, 3))
    return found


def query(bbox):
    s, w, n, e = bbox
    return (f'[out:json][timeout:180];'
            f'(nwr["amenity"~"^({"|".join(AMENITIES)})$"]({s},{w},{n},{e}););'
            f'out center tags;')


def fetch(bbox):
    """Overpass's answer for one box, retried ONCE after a minute on a busy server."""
    req = Request(OVERPASS, data=urlencode({'data': query(bbox)}).encode(), headers={
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': 'sky-score/1.0 (https://skyscore.co.uk)',
    })
    for attempt in (1, 2):
        try:
            with urlopen(req, timeout=240) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as exc:
            # 502 is Overpass's gateway too (first run, 2026-10-27: Cardiff, then fine on retry)
            if attempt == 2 or exc.code not in (429, 502, 503, 504):
                raise
            print(f'    Overpass busy ({exc.code}); one retry in 60 s')
            time.sleep(60)
    raise AssertionError('unreachable')


def coords(el):
    if el.get('type') == 'node':
        return el.get('lat'), el.get('lon')
    c = el.get('center') or {}
    return c.get('lat'), c.get('lon')


def rows_of(elements):
    """Trim to exactly what the Lambda serves, in a deterministic order (an unchanged upstream gives a
    byte-identical file). Keeping the raw payload would triple the bundle for tags nothing reads."""
    rows = []
    for el in elements:
        tags = el.get('tags') or {}
        name = tags.get('name')
        lat, lon = coords(el)
        if not name or lat is None or lon is None or tags.get('amenity') not in AMENITIES:
            continue
        parts = [tags.get('addr:housenumber'), tags.get('addr:street')]
        rows.append({
            'a': tags.get('amenity'),
            'n': name,
            'lat': round(float(lat), 6),
            'lon': round(float(lon), 6),
            'ad': ' '.join(p for p in parts if p).strip(),
            'pc': tags.get('addr:postcode', ''),
            'ph': tags.get('phone') or tags.get('contact:phone', ''),
            'w': tags.get('website') or tags.get('contact:website', ''),
        })
    rows.sort(key=lambda r: (r['a'], r['n'], r['lat'], r['lon']))
    return rows


def build(answers, bboxes):
    """The bundle from {name: Overpass answer}: refuses any area under MIN_NAMED, so nothing is half-written."""
    out, short = [], []
    for name, bbox in bboxes.items():
        rows = rows_of(answers[name].get('elements', []))
        if len(rows) < MIN_NAMED:
            short.append(f'{name}: {len(rows)} named services (fewer than {MIN_NAMED})')
        out.append({'name': name, 'bbox': list(bbox), 'count': len(rows), 'items': rows})
    if short:
        raise SystemExit('refused, nothing written: an answer this small is an empty success, not a city:\n  '
                         + '\n  '.join(short))
    return {'areas': out, 'count': sum(a['count'] for a in out)}


def main(argv):
    bboxes = areas()
    answers = {}
    RAW.mkdir(parents=True, exist_ok=True)
    asked = 0
    for name, bbox in bboxes.items():
        raw = RAW / f'{name}.json'
        # A saved answer is reused only when asked for: a refresh months later must not quietly ship old data.
        if '--from-raw' in argv or ('--resume' in argv and raw.exists()):
            answers[name] = json.loads(raw.read_text(encoding='utf-8'))
            continue
        if asked:
            time.sleep(PAUSE_S)
        asked += 1
        print(f'{name}: one bulk query for {bbox}...')
        try:
            answers[name] = fetch(bbox)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise SystemExit(f'{name}: Overpass failed ({exc}); nothing written. The areas already answered are '
                             f'saved in {RAW}: re-run with --resume to ask only for the rest.') from exc
        raw.write_text(json.dumps(answers[name]), encoding='utf-8')
        print(f'  {len(answers[name].get("elements", []))} elements')
    bundle = build(answers, bboxes)
    OUT.write_text(json.dumps(bundle, separators=(',', ':')), encoding='utf-8')
    for a in bundle['areas']:
        by = {}
        for r in a['items']:
            by[r['a']] = by.get(r['a'], 0) + 1
        print(f'  {a["name"]:<14} {a["count"]:>5} named {by}')
    print(f'wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB, {bundle["count"]} services in {len(bundle["areas"])} areas)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
