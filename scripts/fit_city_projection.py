"""Derive a d3.geoMercator centre and scale for a city from its boundary file.

Why this exists
---------------
Every city in ``CITY_DATA`` needs a projection ``center`` and ``scale``. Picking
them by eye is how the first three got theirs, and it does not scale: by city
ten nobody remembers what "48000" was fitted to, and a number that is merely
plausible renders a region half off the canvas without erroring.

So the six Core Cities regions added on 2026-08-10 are FITTED rather than
guessed. London's hand-tuned pair is treated as the calibration: at scale 48000
its bounding box occupies a particular pixel box, and every other city is
scaled to fit that same box. Regions then read at a comparable on-screen size
whether they are Tyne and Wear (0.51 deg wide) or West Yorkshire (0.97 deg).

London, New York and Greater Manchester KEEP their hand-tuned values in
``index.html`` — they have always rendered correctly and this script is not a
reason to move them. Run it for a NEW city, or to re-check an existing one.

    python scripts/fit_city_projection.py                  # every city on disk
    python scripts/fit_city_projection.py --city bristol   # just one

The output is paste-ready for the ``center`` / ``scale`` fields of a CITY_DATA
entry. It is NOT written back automatically: the value belongs beside the rest
of the city's registry entry, where the smoke-local key-parity assertion can
see it, rather than in a generated block.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

# The calibration city. Its centre and scale are hand-chosen and known good;
# everything else is fitted to the box it produces.
CALIBRATION_CITY = "london"
CALIBRATION_SCALE = 48000


def merc_y(lat_deg: float) -> float:
    """Mercator y for a latitude, in the same units d3.geoMercator uses."""
    lat = math.radians(lat_deg)
    return math.log(math.tan(math.pi / 4 + lat / 2))


def bbox(path: Path) -> tuple[float, float, float, float]:
    """(min_lon, min_lat, max_lon, max_lat) over every coordinate in a GeoJSON.

    Walks the coordinate tree rather than trusting a ``bbox`` member: the ONS
    extracts do not all carry one, and a stale bbox would silently mis-fit the
    city while looking authoritative.
    """
    with path.open(encoding="utf-8") as fh:
        gj = json.load(fh)
    feats = gj["features"] if gj.get("type") == "FeatureCollection" else gj

    lons: list[float] = []
    lats: list[float] = []

    def walk(coords) -> None:
        if isinstance(coords[0], (int, float)):
            lons.append(coords[0])
            lats.append(coords[1])
            return
        for part in coords:
            walk(part)

    for feature in feats:
        walk(feature["geometry"]["coordinates"])

    if not lons:
        raise ValueError(f"{path.name} holds no coordinates")
    return min(lons), min(lats), max(lons), max(lats)


def fit(path: Path, box_w: float, box_h: float) -> dict:
    lon0, lat0, lon1, lat1 = bbox(path)
    d_lambda = math.radians(lon1 - lon0)
    d_phi = merc_y(lat1) - merc_y(lat0)
    # min() of the two fits, not max(): the larger scale would fill the box on
    # one axis and overflow the other, which is exactly the failure that is
    # invisible until someone opens the city.
    scale = min(box_w / d_lambda, box_h / d_phi)
    return {
        "center": [round((lon0 + lon1) / 2, 4), round((lat0 + lat1) / 2, 4)],
        "scale": int(round(scale / 500) * 500),
        "span": (lon1 - lon0, lat1 - lat0),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--city", help="one city key (default: every boundary file)")
    args = ap.parse_args()

    cal_path = DATA / f"{CALIBRATION_CITY}-boroughs.json"
    if not cal_path.exists():
        print(f"missing calibration file {cal_path}", file=sys.stderr)
        return 1
    lon0, lat0, lon1, lat1 = bbox(cal_path)
    box_w = CALIBRATION_SCALE * math.radians(lon1 - lon0)
    box_h = CALIBRATION_SCALE * (merc_y(lat1) - merc_y(lat0))
    print(
        f"calibration: {CALIBRATION_CITY} at scale {CALIBRATION_SCALE} "
        f"occupies {box_w:.0f} x {box_h:.0f} px\n"
    )

    if args.city:
        paths = [DATA / f"{args.city}-boroughs.json"]
        if not paths[0].exists():
            print(f"no boundary file for {args.city}", file=sys.stderr)
            return 1
    else:
        paths = sorted(DATA.glob("*-boroughs.json"))

    for path in paths:
        key = path.name.replace("-boroughs.json", "")
        try:
            result = fit(path, box_w, box_h)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            print(f"{key:16s} FAILED: {exc}")
            continue
        centre = f"[{result['center'][0]}, {result['center'][1]}]"
        print(
            f"{key:16s} center: {centre:22s} scale: {result['scale']:6d}"
            f"   (bbox {result['span'][0]:.3f} x {result['span'][1]:.3f} deg)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
