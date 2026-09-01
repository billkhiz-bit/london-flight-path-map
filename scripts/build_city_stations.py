#!/usr/bin/env python3
"""Rail, metro and tram stations per city, for DISPLAY only.

WHY DISPLAY ONLY, STATED UP FRONT.

`index.html` carried a `<CITY>_STATIONS` array per city and used the distance
to the nearest entry to nudge a neighbourhood's liveability by up to +/-0.4.
Every generated city's array was empty, so `minStDist` stayed `Infinity` and
`Infinity > 5` applied the FULL PENALTY to every neighbourhood outside London -
a penalty whose real meaning was "nobody has built this file yet". That was
fixed on 2026-08-12 by making an empty list a no-op.

The obvious next step was to fill the arrays. It is the wrong step, for two
reasons that only show up if you look at what the numbers mean:

  1. IT WOULD DOUBLE-COUNT. Liveability already scores transport from NaPTAN
     since methodology v3.6 - the share of a borough's postcodes within 800 m
     of a rail/metro/tram node, at 0.25 of the component. Deriving a station
     list from the same register and letting it move the same score again
     counts one measurement twice.
  2. LONDON'S LIST IS NOT THE SAME KIND OF THING. `STATIONS` in index.html is
     18 hand-picked major interchanges - King's Cross, Bank, Waterloo - so
     London's nudge means "distance to a major hub". A NaPTAN-derived list is
     every station. Filling the other cities that way would have made London
     incomparable with them while looking like consistency.

So this script emits stations for the DETAIL PANEL - "your nearest stations,
with distances" - and the scoring nudge is removed rather than generalised.
The user-visible information is better (every city gets it, from a national
register) and the score stops counting NaPTAN twice.

SOURCE
  NaPTAN, the DfT National Public Transport Access Node register.
  https://naptan.api.dft.gov.uk/v1/access-nodes?dataFormat=csv
  Open Government Licence v3.0.

  Rail, metro and tram only, never bus: 416,539 of NaPTAN's 435,298 nodes are
  bus stops, and a bus stop is not what "nearest station" means to anyone
  reading a property listing. Same StopType filter the borough band uses, so
  the two cannot drift apart in what they call a station.

  StopType RLY (rail), RSE (rail station entrance), PLT (platform), TMU (tram
  or metro underground), MET (metro). Entrances and platforms are collapsed
  into one entry per station name, because six Piccadilly Gardens platforms
  are one station to a reader.

  python scripts/build_city_stations.py --write-index
  python scripts/build_city_stations.py --city manchester
"""

import argparse
import csv
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAPTAN_CSV = os.path.join(REPO, 'data', 'naptan.csv')
INDEX_PATH = os.path.join(REPO, 'index.html')

# Same set as scripts/build_borough_bands.py. Kept identical deliberately: if
# these two ever disagree, the panel would name a station the score does not
# count, or the reverse.
RAIL_TYPES = {'RLY', 'RSE', 'PLT', 'TMU', 'MET'}


def bng_to_wgs84(easting, northing):
    """OSGB36 eastings/northings -> WGS84 lat/lon via pyproj."""
    from pyproj import Transformer

    if not hasattr(bng_to_wgs84, '_t'):
        bng_to_wgs84._t = Transformer.from_crs('EPSG:27700', 'EPSG:4326', always_xy=True)
    lon, lat = bng_to_wgs84._t.transform(easting, northing)
    return lat, lon


def city_shapes():
    """{city: (bbox, [geometries])} from each boundary file.

    The bbox is kept only as a cheap pre-filter; containment is decided by
    point-in-polygon against the real geometry. Derived from the boundaries we
    already ship rather than typed, so a city whose boundaries change cannot
    keep an old catchment.
    """
    import glob

    out = {}
    for path in sorted(glob.glob(os.path.join(REPO, 'data', '*-boroughs.json'))):
        city = os.path.basename(path).replace('-boroughs.json', '')
        with open(path, encoding='utf-8') as fh:
            gj = json.load(fh)
        lats, lons = [], []

        def walk(coords, _lats=lats, _lons=lons):
            if isinstance(coords[0], (int, float)):
                _lons.append(coords[0])
                _lats.append(coords[1])
                return
            for c in coords:
                walk(c, _lats, _lons)

        for feat in gj.get('features', []):
            geom = feat.get('geometry') or {}
            if geom.get('coordinates'):
                walk(geom['coordinates'])
        geoms = [
            f['geometry']
            for f in gj.get('features', [])
            if (f.get('geometry') or {}).get('coordinates')
        ]
        if lats and geoms:
            out[city] = ((min(lats), min(lons), max(lats), max(lons)), geoms)
    return out


def clean_name(raw):
    """'Manchester Piccadilly (Platform 13)' -> 'Manchester Piccadilly'.

    ONLY strips a trailing descriptor and parenthetical platform detail. An
    earlier version stripped the words anywhere in the string and turned
    "Station Approach" into "Approach" and "Beaconsfield Street Tram Stop" into
    "Beaconsfield Street" - real NaPTAN names mangled into something that reads
    like a fragment. Anchoring to the end is the difference between removing a
    suffix and editing a place name.
    """
    s = raw or ''
    # Trailing parenthetical: platform detail, or the operator's own tag.
    # NaPTAN lists "Altrincham", "Altrincham (Manchester Metrolink)",
    # "Altrincham Interchange" and "Altrincham Station (Manchester Metrolink)"
    # as four nodes; a reader wants one Altrincham.
    s = re.sub(
        r'\s*\((?:platform|stand|bay|stop|.*?(?:metrolink|tramlink|tram|metro|'
        r'supertram|light rail))[^)]*\)\s*$',
        '',
        s,
        flags=re.I,
    )
    # Trailing entrance detail: " - main ent", " - Park Lane",
    # "Metrolink Station North West Ent".
    s = re.sub(r'\s*\b(?:metrolink|tram|metro)?\s*station\s+.*\bent(?:rance)?\.?\s*$', '', s, flags=re.I)
    s = re.sub(r'\s+-\s+(?:main\s+)?ent(?:rance)?\.?\s*$', '', s, flags=re.I)
    s = re.sub(
        r'\s*\b(?:rail station|railway station|underground station|metro station|'
        r'metrolink station|tram stop|tram station|station entrance|station|interchange)\s*$',
        '',
        s,
        flags=re.I,
    )
    # "Darlington Rail Station - main ent" loses the entrance first, so by the
    # time the descriptor strip runs it sees "... Rail Station" and removes
    # only "Station". One more pass takes the orphaned "Rail".
    s = re.sub(r'\s+\brail\s*$', '', s, flags=re.I)
    # A TRAILING DIRECTION IS A PLATFORM, NOT A PLACE (audit I19, 2026-09-01).
    #
    # Sheffield Supertram names each direction as its own NaPTAN node, and none
    # of the strips above touches them, so one stop published as up to five
    # "stations": Attercliffe, "... From City", "... To City", "... Platform to
    # City", "... Platform to Meadowhall". Measured across the published
    # arrays: 170 of 943 entries were a place already listed, 166 of them South
    # Yorkshire, which is why a quarter of "nearest four stations" panels
    # showed fewer than four PLACES while still filling four rows.
    #
    # Anchored to the end, like every strip above it, and for the same reason
    # the docstring gives. Checked before shipping rather than reasoned about:
    # of the 180 names this changes, 175 merge into a place listed within
    # 800 m, and the 5 with no sibling keep a real place name - "Meadowhall
    # Interchange To City" -> "Meadowhall Interchange". It runs LAST because
    # "X To City Rail Station" must lose the descriptor first.
    s = re.sub(r'\s*\b(?:platform\s+)?(?:to|from|towards)\s+.+$', '', s, flags=re.I)
    return ' '.join(s.split()).strip(' -,')


def _point_in_ring(lon, lat, ring):
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > lat) != (y2 > lat):
            xin = (x2 - x1) * (lat - y1) / (y2 - y1) + x1
            if lon < xin:
                inside = not inside
    return inside


def _point_in_geometry(lon, lat, geom):
    """Point-in-polygon against a GeoJSON Polygon or MultiPolygon.

    A BOUNDING BOX IS NOT ENOUGH, and assuming it was produced the exact defect
    this codebase keeps meeting. Leicester's eight districts and Nottingham's
    four have overlapping bounding boxes, so a first-match-wins bbox test filed
    Attenborough, Beeston, Basford and Bingham - all Nottinghamshire - under
    Leicester, giving Leicester 104 stations and Nottingham 16. Bristol's box
    reached across the Severn and collected Chepstow and Caldicot.
    """
    polys = geom['coordinates'] if geom['type'] == 'MultiPolygon' else [geom['coordinates']]
    for poly in polys:
        if not poly:
            continue
        if _point_in_ring(lon, lat, poly[0]):
            # Subtract holes.
            if not any(_point_in_ring(lon, lat, hole) for hole in poly[1:]):
                return True
    return False


def collect(bboxes):
    """{city: [{'name','coords':[lon,lat]}...]} from one NaPTAN pass."""
    if not os.path.exists(NAPTAN_CSV):
        sys.exit(
            f'NaPTAN not found at {NAPTAN_CSV}. Fetch with:\n'
            '  curl -o data/naptan.csv '
            '"https://naptan.api.dft.gov.uk/v1/access-nodes?dataFormat=csv"'
        )
    per_city = {c: {} for c in bboxes}
    scanned = kept = 0
    skipped_inactive = 0
    with open(NAPTAN_CSV, newline='', encoding='utf-8-sig', errors='replace') as fh:
        reader = csv.DictReader(fh)
        # HARD-FAIL ON AN ABSENT COLUMN, never fall through. `row.get('Status')`
        # returns None if NaPTAN renames the field, which compares unequal to
        # 'active' and would drop EVERY station - and the opposite spelling of
        # this guard would keep every retired one. Either way the run looks
        # normal, which is the failure this repo keeps paying for.
        if 'Status' not in (reader.fieldnames or []):
            sys.exit(
                'NaPTAN has no Status column - it was renamed or the CSV is a '
                'different export. Refusing to publish retired stations as '
                f'current. Columns seen: {reader.fieldnames}'
            )
        for row in reader:
            scanned += 1
            if row.get('StopType') not in RAIL_TYPES:
                continue
            # NaPTAN keeps RETIRED nodes, with real coordinates and a real
            # name, marked `Status: inactive` - 806 of the 11,163 rows of
            # the types above. Nothing read the column, so closed stations and
            # heritage halts shipped in the panel as current (audit I19).
            # Same shape as the terminated postcodes in build_borough_bands.py:
            # a retired record with plausible coordinates is indistinguishable
            # from a live one unless you read the flag that says so.
            if (row.get('Status') or '').strip().lower() != 'active':
                skipped_inactive += 1
                continue
            try:
                lat, lon = bng_to_wgs84(float(row['Easting']), float(row['Northing']))
            except (KeyError, ValueError, TypeError):
                continue
            name = clean_name(row.get('CommonName'))
            if not name:
                continue
            for city, ((min_lat, min_lon, max_lat, max_lon), geoms) in bboxes.items():
                if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
                    continue
                if not any(_point_in_geometry(lon, lat, g) for g in geoms):
                    continue
                # One entry per station NAME. Platforms and entrances are
                # separate NaPTAN nodes and would otherwise list the same
                # station six times.
                # RAIL WINS over a tram/metro node of the same name. Where
                # both exist - Altrincham, Eccles, Ashton - the rail station is
                # the one a reader means, and it is what decides whether the
                # map labels it.
                st = row.get('StopType')
                kind = 'rail' if st in ('RLY', 'RSE', 'PLT') else 'metro'
                # KEYED CASE-INSENSITIVELY, and the display name is chosen
                # rather than taken from whichever row arrived first. NaPTAN
                # spells the same stop both ways: "Besses o'th'Barn" and
                # "Besses o'th'barn" were both published, one Metrolink stop
                # listed twice. An exact-string key is what audit I19 is about;
                # the directional strip fixed one shape of it and this is the
                # other. Preferring the spelling with more capitals keeps
                # "Besses o'th'Barn" over "...barn" and is deterministic, which
                # matters because this file is diffed on every rebuild.
                key = name.casefold()
                prev = per_city[city].get(key)
                if prev is None:
                    per_city[city][key] = [round(lon, 5), round(lat, 5), kind, name]
                    kept += 1
                else:
                    if kind == 'rail' and prev[2] != 'rail':
                        prev[2] = 'rail'
                    caps = sum(1 for c in name if c.isupper())
                    if (caps, name) > (sum(1 for c in prev[3] if c.isupper()), prev[3]):
                        prev[3] = name
                break
    # A FLOOR ON THE EXCLUSION, not just on the intake. A scan that kept
    # stations and found no inactive ones means the Status values changed
    # shape (title case, a new vocabulary) and the filter is passing
    # everything - which reads exactly like a clean dataset.
    if kept and not skipped_inactive:
        sys.exit(
            f'scanned {scanned:,} NaPTAN nodes and kept {kept:,} stations '
            'without excluding a single inactive one. NaPTAN publishes 806 '
            'inactive rail-type nodes, so the Status vocabulary has changed '
            'and this filter is no longer filtering.'
        )
    print(f'  scanned {scanned:,} NaPTAN nodes, kept {kept:,} stations '
          f'({skipped_inactive:,} skipped as inactive)')
    return {
        c: [{'name': v[3], 'coords': v[:2], 'type': v[2]}
            for _key, v in sorted(st.items())]
        for c, st in per_city.items()
    }


def write_index(city, stations):
    """Replace `const <CITY>_STATIONS = [...]` in index.html."""
    const = 'STATIONS' if city == 'london' else f'{city.upper()}_STATIONS'
    with open(INDEX_PATH, encoding='utf-8') as fh:
        src = fh.read()
    pattern = re.compile(
        r'(const ' + re.escape(const) + r' = )\[.*?\](;)', re.S
    )
    if not pattern.search(src):
        return 0
    payload = json.dumps(stations, separators=(',', ':'))
    out = pattern.sub(lambda m: m.group(1) + payload + m.group(2), src, count=1)
    with open(INDEX_PATH, 'w', encoding='utf-8', newline='') as fh:
        fh.write(out)
    return len(stations)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--city')
    ap.add_argument('--write-index', action='store_true')
    args = ap.parse_args()

    bboxes = city_shapes()
    if args.city:
        bboxes = {k: v for k, v in bboxes.items() if k == args.city}
        if not bboxes:
            sys.exit(f'no boundary file for {args.city!r}')
    print(f'Stations from NaPTAN for: {", ".join(sorted(bboxes))}')
    found = collect(bboxes)

    total = 0
    for city in sorted(found):
        n = len(found[city])
        total += n
        note = ''
        if args.write_index:
            written = write_index(city, found[city])
            note = f' -> wrote {written}' if written else ' -> NO CONSTANT IN index.html'
        print(f'  {city:16} {n:5} stations{note}')
    print(f'\n{total:,} stations across {len(found)} cities')
    return 0


if __name__ == '__main__':
    sys.exit(main())
