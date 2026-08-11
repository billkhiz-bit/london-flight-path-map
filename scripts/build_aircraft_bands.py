"""Estimate a city's per-borough aircraft `impact` band from runway geometry.

WHAT THIS IS, AND WHAT IT IS NOT
--------------------------------
It is an ESTIMATE from the extended runway centreline, the same kind Greater
Manchester ships and labelled the same way. It is **not** a DEFRA sample, and
the band vocabulary it emits must never be presented as one - `CITY_PROVENANCE`
and the map legend both have to say "ESTIMATED".

`impact` is effectively REQUIRED: `calc_score` reads `bd['impact']` directly, so
a borough without one raises rather than degrading. That is why this exists at
all rather than leaving the field out.

WHY NOT A DISTANCE LADDER FITTED TO LONDON
------------------------------------------
Measured: London's bands are distance-driven only in the near field. Sorting all
33 boroughs by centroid distance to Heathrow gives a clean severe (6.4-7.9 km)
and high (10.6-10.7 km), and then it falls apart - `moderate-high` appears at
both 16.8 km and 34.9 km, because Newham is a London City Airport borough, not a
Heathrow one, and several mid-range bands are corridor-driven rather than
radial. A ladder fitted to that spread would be fitting noise.

So this uses the part that IS evidenced (near-field radial distance), applies it
to the airport AND to the extended centreline where approaches actually run, and
declines to invent a long tail: beyond the corridor, a single-airport city with
no second airport and no measured contour is `low`. Absence of evidence is
reported as quiet only where there is genuinely nothing to be near.

DIRECTION OF ERROR
------------------
The thresholds are calibrated on Heathrow, which is several times the size of
any airport here, so they reach further than these airports really do and the
result is pessimistic - places read noisier than they are. That is the
survivable direction. `CITY_GEOMETRY` already records the same caveat for
Manchester (Core Cities finding 7), and the DEFRA raster incident is on record
precisely because it erred the other way, publishing quiet where it had no data.

Sources, both fetched not remembered:
  * airport and runway geometry - OurAirports (public domain)
  * borough outlines - data/<city>-boroughs.json, built by build_city_boroughs.py

Usage
-----
    python scripts/build_aircraft_bands.py --city westmidlands
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

# Verified from OurAirports runways.csv. le/he are the two runway thresholds, so
# the segment between them IS the centreline and needs no heading arithmetic.
AIRPORTS = {
    "westmidlands": {
        "code": "BHX", "name": "Birmingham", "icao": "EGBB",
        "lat": 52.453899, "lon": -1.74803,
        "le": (52.465599, -1.76111), "he": (52.442964, -1.735894), "runway": "15/33",
    },
    "westyorkshire": {
        "code": "LBA", "name": "Leeds Bradford", "icao": "EGNM",
        "lat": 53.865898, "lon": -1.66057,
        "le": (53.873402, -1.672070), "he": (53.858398, -1.649070), "runway": "14/32",
    },
    "merseyside": {
        "code": "LPL", "name": "Liverpool John Lennon", "icao": "EGGP",
        "lat": 53.334863, "lon": -2.849637,
        "le": (53.332848, -2.866881), "he": (53.334424, -2.832649), "runway": "09/27",
    },
    "tyneandwear": {
        "code": "NCL", "name": "Newcastle", "icao": "EGNT",
        "lat": 55.037958, "lon": -1.689577,
        "le": (55.033501, -1.70634), "he": (55.042301, -1.67327), "runway": "07/25",
    },
    "bristol": {
        "code": "BRS", "name": "Bristol", "icao": "EGGD",
        "lat": 51.382326, "lon": -2.716453,
        "le": (51.382099, -2.7335), "he": (51.383202, -2.70467), "runway": "09/27",
    },
    "nottingham": {
        "code": "EMA", "name": "East Midlands", "icao": "EGNX",
        "lat": 52.8311, "lon": -1.32806,
        "le": (52.830601, -1.34957), "he": (52.831402, -1.30667), "runway": "09/27",
    },
    # East Midlands, shared with Nottingham. EMA sits IN North West
    # Leicestershire, which is part of this cohort, so Leicester is one of the
    # few cities here whose airport is inside its own boundary rather than
    # beyond it.
    "leicester": {
        "code": "EMA", "name": "East Midlands", "icao": "EGNX",
        "lat": 52.8311, "lon": -1.32806,
        "le": (52.830601, -1.34957), "he": (52.831402, -1.30667), "runway": "09/27",
    },
    # Teesside International, the former Durham Tees Valley. Verified from
    # OurAirports: single 05/23 runway, 7,516 ft, open.
    "teesside": {
        "code": "MME", "name": "Teesside International", "icao": "EGNV",
        "lat": 54.509201, "lon": -1.42941,
        "le": (54.502201, -1.442430), "he": (54.516201, -1.416380), "runway": "05/23",
    },
    "cardiff": {
        "code": "CWL", "name": "Cardiff", "icao": "EGFF",
        "lat": 51.396702, "lon": -3.34333,
        "le": (51.401501, -3.35868), "he": (51.3918, -3.32799), "runway": "12/30",
    },
    # South Yorkshire has NO operating commercial airport. Doncaster Sheffield is
    # listed `type=closed` by OurAirports; it ceased commercial flights in 2022.
    # Every borough is therefore `low`, and that is a measured absence of a noise
    # source rather than a missing measurement - the provenance must say which.
    "southyorkshire": None,
}

# Radial km from the AIRPORT. The first two are evidenced by London's near
# field; the rest are a documented editorial ramp, deliberately monotone so no
# band can appear at two unrelated distances.
BANDS = [(6.0, "severe"), (10.0, "high"), (16.0, "moderate"), (25.0, "low-moderate")]
DEFAULT_BAND = "low"
ORDER = ["low", "low-moderate", "moderate", "moderate-high", "high", "severe"]

# Being under the approach makes a place ONE band noisier, it does not make it
# equivalent to the airport.
#
# The first version of this took min(distance-to-airport, distance-to-corridor)
# and it was wrong in a way worth keeping written down: it rated **Walsall
# `severe` at 21.9 km from Birmingham**, on the strength of sitting 3.2 km from
# the extended centreline. Aircraft 20 km out on a 3-degree approach are around
# 6,000 ft up; they are not the same noise source as one on short final. That
# rule would have published "Walsall is as aircraft-affected as the airport" -
# false, and precisely the sort of claim that discredits a noise product.
#
# A one-band bump reproduces the shape London actually shows: Hounslow and
# Hillingdon are severe by being both close AND under the path, Ealing and
# Richmond sit a band lower at ~10.6 km, and boroughs off-corridor fall away
# regardless of range.
CORRIDOR_LATERAL_KM = 5.0
CORRIDOR_MAX_RANGE_KM = 25.0
CORRIDOR_KM = 20.0  # how far out along the centreline approaches are modelled
# 1.0 km, and this is a CORRECTION rather than a preference. It read 2.0 until
# 2026-08-11, while every corridor actually shipped in the Lambda measures
# 0.85-1.00 km spacing - they were resampled to a common 1 km interval on
# 2026-08-10 and this constant was never brought with them. Corridor distance is
# measured to the NEAREST WAYPOINT, so a coarser polyline reads as further from
# the corridor and therefore QUIETER: the next city added with 2.0 would have
# been systematically and invisibly quieter than the nine already here.
# CLAUDE.md states the rule as "regenerate at 1 km if any corridor is ever
# re-derived"; this makes the code obey it instead of relying on the reader.
CORRIDOR_STEP_KM = 1.0


def hav(lat1, lon1, lat2, lon2):
    r = 6371.0
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def centroid(geom):
    """Area-weighted centroid across every outer ring of a (Multi)Polygon."""

    def ring(r):
        a = cx = cy = 0.0
        for i in range(len(r) - 1):
            x1, y1 = r[i][:2]
            x2, y2 = r[i + 1][:2]
            cross = x1 * y2 - x2 * y1
            a += cross
            cx += (x1 + x2) * cross
            cy += (y1 + y2) * cross
        return None if a == 0 else (cx / (3 * a), cy / (3 * a), abs(a / 2))

    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    sx = sy = tot = 0.0
    for poly in polys:
        c = ring(poly[0])
        if c:
            sx += c[0] * c[2]
            sy += c[1] * c[2]
            tot += c[2]
    return (sx / tot, sy / tot) if tot else None


def corridor(ap):
    """Waypoints along the extended runway centreline, both directions."""
    (la1, lo1), (la2, lo2) = ap["le"], ap["he"]
    # Unit vector along the centreline in degrees, latitude-corrected so the
    # bearing is right rather than merely plausible.
    coslat = math.cos(math.radians((la1 + la2) / 2))
    dx, dy = (lo2 - lo1) * coslat, la2 - la1
    norm = math.hypot(dx, dy)
    dx, dy = dx / norm, dy / norm
    km_per_deg = 111.32
    pts = []
    steps = int(CORRIDOR_KM / CORRIDOR_STEP_KM)
    for sign in (1, -1):
        base_lat, base_lon = (la2, lo2) if sign == 1 else (la1, lo1)
        for i in range(1, steps + 1):
            d = i * CORRIDOR_STEP_KM
            pts.append(
                (
                    base_lat + sign * dy * d / km_per_deg,
                    base_lon + sign * dx * d / (km_per_deg * coslat),
                )
            )
    return pts


def band_for(km):
    for limit, name in BANDS:
        if km < limit:
            return name
    return DEFAULT_BAND


def main() -> int:
    ap_arg = argparse.ArgumentParser(description=__doc__)
    ap_arg.add_argument("--city", required=True, choices=sorted(AIRPORTS))
    args = ap_arg.parse_args()

    path = Path(f"data/{args.city}-boroughs.json")
    if not path.exists():
        raise SystemExit(f"{path} missing - run scripts/build_city_boroughs.py --city {args.city}")
    gj = json.loads(path.read_text(encoding="utf-8"))
    airport = AIRPORTS[args.city]

    if airport is None:
        print(f"# {args.city}: NO operating commercial airport. Every borough is 'low'.")
        print("# Doncaster Sheffield is `type=closed` in OurAirports (commercial flights")
        print("# ceased 2022). This is a measured ABSENCE OF A NOISE SOURCE, not an")
        print("# unmeasured borough - the provenance must say which.")
        for f in gj["features"]:
            print(f"    '{f['properties']['name']}': 'low',")
        return 0

    pts = corridor(airport)
    print(f"# {args.city}: estimated from {airport['name']} ({airport['code']}) runway {airport['runway']}.")
    print("# NOT DEFRA. Distance to the airport or to its extended centreline.")
    rows = []
    for f in gj["features"]:
        c = centroid(f["geometry"])
        lon, lat = c
        d_air = hav(lat, lon, airport["lat"], airport["lon"])
        d_cor = min(hav(lat, lon, p[0], p[1]) for p in pts)
        base = band_for(d_air)
        under = d_cor < CORRIDOR_LATERAL_KM and d_air < CORRIDOR_MAX_RANGE_KM
        band = ORDER[min(ORDER.index(base) + 1, len(ORDER) - 1)] if under else base
        rows.append((d_air, f["properties"]["name"], d_cor, band, base, under))
    for d_air, name, d_cor, band, base, under in sorted(rows):
        note = f"# {d_air:5.1f} km to {airport['code']}, {d_cor:5.1f} km off corridor"
        if under:
            note += f" (under approach: {base} -> {band})"
        print(f"    '{name}': '{band}',".ljust(42) + note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
