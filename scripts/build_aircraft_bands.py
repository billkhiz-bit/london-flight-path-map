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
The thresholds are calibrated on Heathrow, and until 2026-08-11 they were
applied to every airport UNWEIGHTED. This section used to call that "pessimistic
and therefore survivable". It was not survivable: at Teesside, an airport 485
times smaller than Heathrow by passengers, it published Stockton-on-Tees as
`severe` - the same band as Hounslow - and drove a borough-wide quiet of 0.0 and
an overall score of 2.6. A caveat in a docstring does not make a wrong number
right, and "erring pessimistic" stops being a defence once the magnitude of the
error exceeds the thing being measured.

The ladder is now scaled per airport by its MEASURED 55 dB Lden footprint (see
AIRPORT_NOISE_SCALE), with a near-field floor so the correction cannot overshoot
into the optimistic direction. Residual error is still pessimistic-leaning,
because the floor binds upward and never downward.

Sources, all fetched not remembered:
  * airport and runway geometry - OurAirports (public domain)
  * noise footprints - DEFRA Round 4 strategic noise maps, per-airport Lden
    surfaces, area above 55 dB measured 2026-08-11
  * borough outlines - data/<city>-boroughs.json, built by build_city_boroughs.py

Usage
-----
    python scripts/build_aircraft_bands.py --city westmidlands   # print one city
    python scripts/build_aircraft_bands.py --check               # gate both holders
    python scripts/build_aircraft_bands.py --write               # correct both
"""

from __future__ import annotations

import argparse
import json
import math
import re
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
    # Added 2026-08-11, and it was MISSING rather than deliberately excluded.
    # Greater Manchester was city #3, added before this script existed, so its
    # ten bands were hand-assigned against a Heathrow-calibrated ladder and were
    # the only site city whose aircraft input no script could reproduce.
    "manchester": {
        "code": "MAN", "name": "Manchester", "icao": "EGCC",
        "lat": 53.349375, "lon": -2.279521,
        "le": (53.345100, -2.292740), "he": (53.362400, -2.257140), "runway": "05L/23R",
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

# The ladder above is calibrated on HEATHROW and, until 2026-08-11, was applied
# unweighted to every airport. That put Stockton-on-Tees in the same `severe`
# band as Hounslow from an airport handling 173,006 passengers a year against
# Heathrow's 83.9 million - a 485x difference scoring identically, and a
# borough-wide quiet of 0.0 on the strength of it.
#
# WHY MEASURED FOOTPRINTS AND NOT PASSENGER NUMBERS. A passenger-count proxy was
# tried first and is recorded here because it looked reasonable and was wrong.
# Scaling by sqrt(pax/pax_LHR) collapsed Birmingham, Bristol, Newcastle,
# Liverpool, Leeds Bradford and East Midlands onto one value, so it stopped
# discriminating exactly where most of these cities are. Worse, it is the wrong
# quantity: EAST MIDLANDS has the second-largest measured noise footprint of the
# twelve here (0.705 of Heathrow) on 3.2 million passengers, because it is a
# freight hub flying at night, while GATWICK is 0.475 on 40.9 million. Counting
# passengers would have understated EMA by a factor of two, in the city this
# work was adding.
#
# So the scale is the PUBLISHED CONTOUR itself: the area above 55 dB Lden in
# each airport's DEFRA Round 4 surface, expressed as an equivalent radius
# (sqrt(area/pi)) and divided by Heathrow's. Heathrow is 1.000 by construction,
# so LONDON'S BANDS DO NOT MOVE.
#
# Measured 2026-08-11 by scripts/fetch_defra_aircraft_noise.py surfaces:
#   heathrow 75.6 km2 (4.91 km)   stansted 41.6   eastmidlands 37.6
#   manchester 26.3   luton 22.6   gatwick 17.0   birmingham 15.3
#   bristol 10.0   newcastle 9.1   liverpool 7.3   leedsbradford 5.7
#   londoncity 2.7 km2 (0.93 km)
AIRPORT_NOISE_SCALE = {
    "LHR": 1.000, "STN": 0.741, "EMA": 0.705, "MAN": 0.589, "LTN": 0.547,
    "LGW": 0.475, "BHX": 0.449, "BRS": 0.365, "NCL": 0.346, "LPL": 0.312,
    "LBA": 0.275, "LCY": 0.190,
}

# An airport DEFRA does not map at all. The END mapping duty applies to major
# airports, so absence from Round 4 is itself evidence of a small footprint -
# but it is not a measurement, so this takes the SMALLEST value DEFRA does
# publish (London City, 2.7 km2) rather than extrapolating below it. That keeps
# the estimate pessimistic without pretending to a number nobody published.
UNMAPPED_AIRPORT_SCALE = 0.190

# The equivalent radius of the same measured footprint, in km. Scaling every
# rung of the ladder without this FLIPPED THE ERROR OPTIMISTIC, which is the one
# direction METHODOLOGY refuses: it moved 29 boroughs and moved all 29 DOWN,
# putting VALE OF GLAMORGAN on `low` - the same band as a borough with no
# airport within 50 km - when Cardiff Airport sits inside it. Liverpool and
# Leeds did the same thing, each with its airport inside the boundary.
#
# So the near field is floored by the CONTOUR ITSELF rather than by a chosen
# number: if any part of a borough falls within the published 55 dB Lden
# footprint, DEFRA has already reported significant exposure there and the
# borough cannot be called quiet. Distance is measured to the borough POLYGON,
# not its centroid, so containment reads as 0 km.
FOOTPRINT_RADIUS_KM = {
    "LHR": 4.91, "STN": 3.64, "EMA": 3.46, "MAN": 2.89, "LTN": 2.69,
    "LGW": 2.33, "BHX": 2.20, "BRS": 1.79, "NCL": 1.70, "LPL": 1.53,
    "LBA": 1.35, "LCY": 0.93,
}
UNMAPPED_FOOTPRINT_KM = 0.93

# Part of the borough is inside the 55 dB contour; most of it is not. `moderate`
# says exposed-but-not-typical, which is what a borough-wide figure can honestly
# claim. It is a FLOOR - a borough already banded higher keeps its band.
NEAR_FIELD_FLOOR = "moderate"
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


def band_for(km, scale=1.0):
    """Band for a radial distance, with the ladder scaled to this airport."""
    for limit, name in BANDS:
        if km < limit * scale:
            return name
    return DEFAULT_BAND


def scale_for(code):
    return AIRPORT_NOISE_SCALE.get(code, UNMAPPED_AIRPORT_SCALE)


def footprint_for(code):
    return FOOTPRINT_RADIUS_KM.get(code, UNMAPPED_FOOTPRINT_KM)


def dist_to_polygon(geom, lat, lon):
    """Great-circle km from a point to the nearest vertex of a polygon, or 0.0
    if the point is inside it. Vertex distance overstates slightly on a coarse
    ring, which errs toward NOT applying the floor - the pessimistic direction
    here is to apply it, so this is checked against containment first."""
    rings = []
    if geom["type"] == "Polygon":
        rings = [geom["coordinates"][0]]
    elif geom["type"] == "MultiPolygon":
        rings = [poly[0] for poly in geom["coordinates"]]
    for ring in rings:
        inside = False
        j = len(ring) - 1
        for i, (xi, yi) in enumerate(ring):
            xj, yj = ring[j]
            if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
                inside = not inside
            j = i
        if inside:
            return 0.0
    return min((hav(lat, lon, y, x) for ring in rings for x, y in ring), default=float("inf"))


LAMBDA_PATH = Path("backend/lambdas/score/app.py")
SITE_PATH = Path("index.html")


# FOUR spellings of the same record live across the two holders, and a pattern
# that knows only one reads NOTHING rather than failing: the Lambda has London
# expanded and every later city compact, and index.html has the newer cities
# compact with quoted keys but Greater Manchester expanded with UNQUOTED ones.
# Both reading and writing go through this pair so they cannot drift apart.
KEY_RE = re.compile(r"^\s*'?([A-Za-z][A-Za-z .'\-]*?)'?\s*:\s*\{")
IMPACT_RE = re.compile(r"('?impact'?:\s*')([a-z-]+)(')")


def _scan(blk):
    """borough -> impact, for any of the four spellings."""
    out, name = {}, None
    for ln in blk.splitlines():
        m = KEY_RE.match(ln)
        if m:
            name = m.group(1)
        m = IMPACT_RE.search(ln)
        if m and name:
            out[name] = m.group(2)
    return out


def _block(text, marker, end):
    """The text of ONE named dict, start..end. Every read and every write goes
    through this. It exists because a global search for `'Hillingdon': {` once
    matched LONDON_PREVIOUS_PT rather than LONDON_BOROUGHS and rewrote 81 lines
    of the previous-vintage table - the values were plausible, so nothing failed
    until the diff was read."""
    i = text.index(marker)
    j = text.index(end, i)
    return i, j, text[i:j]


def _slurp(path):
    # NORMALISE LINE ENDINGS. `newline=""` preserves whatever is on disk, and
    # every block scan below matches on the literal "\n}\n" - so the moment a
    # file arrives as CRLF this gate stops finding ANY block and dies with
    # `ValueError: substring not found` for all eleven cities at once.
    #
    # That is not hypothetical: on 2026-08-12 a `git restore` of
    # backend/lambdas/score/app.py applied core.autocrlf and flipped the file
    # from LF to CRLF, and this gate went from green to a traceback with no
    # data change whatsoever. A gate that depends on a checkout artefact is
    # reporting on the checkout, not on the data.
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read().replace("\r\n", "\n")


def read_lambda(city):
    t = _slurp(LAMBDA_PATH)
    marker = f"{city.upper()}_BOROUGHS = {{"
    if marker not in t:
        return None
    _, _, blk = _block(t, marker, "\n}\n")
    return _scan(blk)


def read_site(city):
    t = _slurp(SITE_PATH)
    marker = f"{city.upper()}_BOROUGH_DATA_RAW = {{"
    if marker not in t:
        return None  # backend-only city; it has no site holder to disagree
    _, _, blk = _block(t, marker, "\n      };")
    return _scan(blk)


def _rewrite(path, marker, end, bands):
    # newline="" on BOTH sides, and it is load-bearing on Windows. Path.read_text
    # folds CRLF to LF and write_text expands LF back to os.linesep, so an
    # innocuous read-modify-write REWRITES EVERY LINE ENDING IN THE FILE. The
    # first run of this did exactly that: 62 real changes arrived alongside
    # 11,163 line endings in index.html and 6,253 in app.py, invisible to
    # `git diff --stat` because autocrlf normalises them back.
    with open(path, encoding="utf-8", newline="") as fh:
        t = fh.read()
    if marker not in t:
        return 0
    i, j, blk = _block(t, marker, end)
    n = 0
    lines = blk.splitlines(keepends=True)
    cur = None
    for k, ln in enumerate(lines):
        m = KEY_RE.match(ln)
        if m:
            cur = m.group(1)
        if cur in bands:
            # Bound as a default argument, not captured: the band is a fixed
            # `[a-z-]+` token so it is also safe as a literal replacement.
            lines[k], cnt = IMPACT_RE.subn(
                lambda mm, b=bands[cur]: mm.group(1) + b + mm.group(3), ln
            )
            n += cnt
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(t[:i] + "".join(lines) + t[j:])
    return n


def derive(city):
    """Every band for one city, from boundaries + runway geometry alone."""
    path = Path(f"data/{city}-boroughs.json")
    if not path.exists():
        raise SystemExit(f"{path} missing - run scripts/build_city_boroughs.py --city {city}")
    gj = json.loads(path.read_text(encoding="utf-8"))
    airport = AIRPORTS[city]
    if airport is None:
        rows = [(0.0, f["properties"]["name"], 0.0, DEFAULT_BAND, DEFAULT_BAND, False, False)
                for f in gj["features"]]
        return rows, None, 1.0, 0.0

    pts = corridor(airport)
    scale = scale_for(airport["code"])
    footprint = footprint_for(airport["code"])
    rows = []
    for f in gj["features"]:
        lon, lat = centroid(f["geometry"])
        d_air = hav(lat, lon, airport["lat"], airport["lon"])
        d_cor = min(hav(lat, lon, p[0], p[1]) for p in pts)
        base = band_for(d_air, scale)
        floored = dist_to_polygon(f["geometry"], airport["lat"], airport["lon"]) < footprint
        if floored and ORDER.index(base) < ORDER.index(NEAR_FIELD_FLOOR):
            base = NEAR_FIELD_FLOOR
        # The LATERAL width does not scale and the ALONG-TRACK reach does. A
        # single aircraft on approach is about as loud overhead at Teesside as
        # at Heathrow, so the corridor is no narrower; what falls at a small
        # airport is how FAR OUT the approach still dominates, which is the
        # same total-energy question the radial ladder answers.
        under = d_cor < CORRIDOR_LATERAL_KM and d_air < CORRIDOR_MAX_RANGE_KM * scale
        band = ORDER[min(ORDER.index(base) + 1, len(ORDER) - 1)] if under else base
        rows.append((d_air, f["properties"]["name"], d_cor, band, base, under, floored))
    return rows, airport, scale, footprint


def check_or_write(args):
    """Compare or correct BOTH holders. A city on the site has two; a
    backend-only city has one. Either way they are done together or not at all -
    a partial write is how the site and the API came to disagree before."""
    cities = [args.city] if args.city else sorted(AIRPORTS)
    bad = 0
    for city in cities:
        rows, _, _, _ = derive(city)
        want = {name: band for _, name, _, band, _, _, _ in rows}
        for label, reader, path, marker, end in (
            ("lambda", read_lambda, LAMBDA_PATH, f"{city.upper()}_BOROUGHS = {{", "\n}\n"),
            ("site", read_site, SITE_PATH, f"{city.upper()}_BOROUGH_DATA_RAW = {{", "\n      };"),
        ):
            have = reader(city)
            if have is None:
                continue
            diff = {b: (have.get(b), want[b]) for b in want if have.get(b) != want[b]}
            if args.write:
                n = _rewrite(path, marker, end, want)
                print(f"  {city:14s} {label:7s} wrote {n} bands ({len(diff)} changed)")
            elif diff:
                bad += len(diff)
                for b, (h, w) in sorted(diff.items()):
                    print(f"  DIFF {city:14s} {label:7s} {b:26s} holds {h!s:15s} derives {w}")
    if args.write:
        return 0
    print(f"\n{bad} disagreement(s) between the holders and the derivation.")
    return 1 if bad else 0


def main() -> int:
    ap_arg = argparse.ArgumentParser(description=__doc__)
    ap_arg.add_argument("--city", choices=sorted(AIRPORTS))
    ap_arg.add_argument("--check", action="store_true",
                        help="compare BOTH holders against the derivation; exit 1 on any difference")
    ap_arg.add_argument("--write", action="store_true",
                        help="correct both holders")
    args = ap_arg.parse_args()

    if args.check or args.write:
        return check_or_write(args)
    if not args.city:
        ap_arg.error("--city is required unless --check or --write is given")

    rows, airport, scale, footprint = derive(args.city)
    if airport is None:
        print(f"# {args.city}: NO operating commercial airport. Every borough is 'low'.")
        print("# Doncaster Sheffield is `type=closed` in OurAirports (commercial flights")
        print("# ceased 2022). This is a measured ABSENCE OF A NOISE SOURCE, not an")
        print("# unmeasured borough - the provenance must say which.")
        for _, name, _, band, _, _, _ in rows:
            print(f"    '{name}': '{band}',")
        return 0

    measured = ("measured 55 dB Lden footprint" if airport["code"] in AIRPORT_NOISE_SCALE
                else "NOT MAPPED by DEFRA; floored at the smallest published footprint")
    print(f"# {args.city}: estimated from {airport['name']} ({airport['code']}) runway {airport['runway']}.")
    print("# NOT DEFRA. Distance to the airport or to its extended centreline.")
    print(f"# Ladder scaled x{scale:.3f} vs Heathrow ({measured}).")
    for d_air, name, d_cor, band, base, under, floored in sorted(rows):
        note = f"# {d_air:5.1f} km to {airport['code']} (x{scale:.2f}), {d_cor:5.1f} km off corridor"
        if floored:
            note += f", inside the {footprint:.2f} km 55 dB footprint (floored)"
        if under:
            note += f" (under approach: {base} -> {band})"
        print(f"    '{name}': '{band}',".ljust(42) + note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
