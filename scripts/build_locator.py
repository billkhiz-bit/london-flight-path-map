"""Generate a locator-inset silhouette from a boundary GeoJSON.

Why this exists
---------------
`data/uk-locator.json` was checked in with **no generator**, so the one piece of
map furniture that states the roadmap could not be rebuilt, corrected or
extended to a second country without hand-editing 83 KB of path data. Adding
the United States needed a generator anyway; writing it generically means the
UK file stops being un-reproducible too.

Output schema matches `data/uk-locator.json` exactly, because `renderLocator()`
reads both through the same code path:

    {"w": int, "h": int, "region": str, "d": str,
     "cities": [{"name": str, "x": float, "y": float}, ...]}

`d` is one closed subpath per ring rather than a dissolved national outline.
That is deliberate and matches the UK file: `#locator-land` fills with no
stroke, so adjacent rings share edges and read as a single landmass, while a
dissolved outline would need a topology library to compute.

KNOWN LIMITATION, stated rather than glossed: the source GeoJSON is not
topologically shared - neighbouring features hold their own copies of a common
border - so simplifying each ring independently can leave hairline slivers
along internal borders. Quantising before simplification (see `to_view`) closes
those that DO share vertices, and the rest survive as sub-pixel seams. They are
invisible at the 112px the inset actually renders at and faintly visible at 2x
DPR. Closing them properly means a real polygon union, which is a dependency
this repo does not have and a decoration does not justify.

Projection
----------
`albers-us` is the standard equal-area conic for the contiguous United States
(standard parallels 29.5 and 45.5). `equirect` is a plain lon/lat scaling with
a cos(latitude) correction, adequate for a small island group.

Usage
-----
    python scripts/build_locator.py --src us-states.json --out data/usa-locator.json \\
        --region "Contiguous United States" --projection albers-us \\
        --exclude Alaska Hawaii "Puerto Rico" \\
        --city "New York City:40.7128:-74.0060"
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

# Albers equal-area conic, contiguous US. The parallels are the conventional
# choice (USGS/Census); changing them changes the shape, so they are named here
# rather than buried as magic numbers.
ALBERS_PHI1 = math.radians(29.5)
ALBERS_PHI2 = math.radians(45.5)
ALBERS_PHI0 = math.radians(37.5)
ALBERS_LON0 = math.radians(-96.0)


def albers_us(lon: float, lat: float) -> tuple[float, float]:
    phi, lam = math.radians(lat), math.radians(lon)
    n = (math.sin(ALBERS_PHI1) + math.sin(ALBERS_PHI2)) / 2.0
    c = math.cos(ALBERS_PHI1) ** 2 + 2.0 * n * math.sin(ALBERS_PHI1)
    rho = math.sqrt(max(c - 2.0 * n * math.sin(phi), 0.0)) / n
    rho0 = math.sqrt(max(c - 2.0 * n * math.sin(ALBERS_PHI0), 0.0)) / n
    theta = n * (lam - ALBERS_LON0)
    return rho * math.sin(theta), rho0 - rho * math.cos(theta)


def equirect(lon: float, lat: float) -> tuple[float, float]:
    # Scale longitude by cos(lat) so the aspect ratio is not stretched at high
    # latitudes; adequate for one country, not for a world map.
    return lon * math.cos(math.radians(lat)), lat


PROJECTIONS = {"albers-us": albers_us, "equirect": equirect}


def rings(geom: dict):
    """Yield every linear ring in a Polygon or MultiPolygon."""
    kind = geom.get("type")
    coords = geom.get("coordinates") or []
    if kind == "Polygon":
        yield from coords
    elif kind == "MultiPolygon":
        for poly in coords:
            yield from poly


def simplify(points: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    """Douglas-Peucker. Keeps the coastline legible while cutting the file size.

    Without this the US states file lands at ~1.5 MB of path data, which is
    larger than the borough boundaries the map actually scores from - absurd for
    a 112px decoration.
    """
    if len(points) < 3:
        return points
    first, last = points[0], points[-1]
    dx, dy = last[0] - first[0], last[1] - first[1]
    span = math.hypot(dx, dy)
    worst_i, worst_d = 0, -1.0
    for i in range(1, len(points) - 1):
        px, py = points[i]
        if span == 0:
            dist = math.hypot(px - first[0], py - first[1])
        else:
            dist = abs(dy * px - dx * py + last[0] * first[1] - last[1] * first[0]) / span
        if dist > worst_d:
            worst_i, worst_d = i, dist
    if worst_d <= tol:
        return [first, last]
    left = simplify(points[: worst_i + 1], tol)
    right = simplify(points[worst_i:], tol)
    return left[:-1] + right


def ring_area(points: list[tuple[float, float]]) -> float:
    """Absolute shoelace area, used only to drop specks."""
    total = 0.0
    for i in range(len(points)):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % len(points)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", required=True, help="boundary GeoJSON")
    ap.add_argument("--out", required=True, help="output locator JSON")
    ap.add_argument("--region", required=True, help="caption, e.g. 'Contiguous United States'")
    ap.add_argument(
        "--unit",
        default="core cities",
        help="what the markers COUNT. 'Core Cities' is the name of a specific UK "
        "group of ten, so it must not be reused for another country's markers.",
    )
    ap.add_argument("--projection", default="albers-us", choices=sorted(PROJECTIONS))
    ap.add_argument("--name-key", default="name", help="feature property holding the name")
    ap.add_argument("--exclude", nargs="*", default=[], help="feature names to drop")
    ap.add_argument("--width", type=int, default=170, help="viewBox width")
    ap.add_argument("--pad", type=float, default=2.0, help="padding in output units")
    ap.add_argument("--tolerance", type=float, default=0.30, help="simplify tolerance, output units")
    ap.add_argument("--min-area", type=float, default=0.6, help="drop rings smaller than this")
    ap.add_argument(
        "--city",
        action="append",
        default=[],
        metavar="NAME:LAT:LON",
        help="marker, repeatable. Name may contain spaces but not a colon.",
    )
    args = ap.parse_args()

    project = PROJECTIONS[args.projection]
    source = json.loads(Path(args.src).read_text(encoding="utf-8"))
    excluded = {e.lower() for e in args.exclude}

    kept, dropped = [], []
    for feature in source.get("features", []):
        name = str((feature.get("properties") or {}).get(args.name_key, ""))
        if name.lower() in excluded:
            dropped.append(name)
            continue
        for ring in rings(feature.get("geometry") or {}):
            pts = [project(float(c[0]), float(c[1])) for c in ring if len(c) >= 2]
            if len(pts) >= 4:
                kept.append(pts)
    if not kept:
        raise SystemExit("No rings survived - check --name-key and --exclude.")

    xs = [x for ring in kept for x, _ in ring]
    ys = [y for ring in kept for _, y in ring]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    # Projected y grows northward; SVG y grows downward, so flip.
    scale = (args.width - 2 * args.pad) / (maxx - minx)
    height = (maxy - miny) * scale + 2 * args.pad

    def to_view(x: float, y: float) -> tuple[float, float]:
        # QUANTISED before simplification, and that ordering is load-bearing.
        # Neighbouring features share a border, but each ring is simplified
        # independently, so on full-precision input Douglas-Peucker keeps
        # slightly different vertices either side and the shared edge splits
        # into a sliver. `#locator-land` fills semi-transparent with NO stroke
        # (stroking would draw every internal border), so those slivers render
        # as pale hairlines across the landmass - clearly visible on the first
        # US render. Rounding first makes coincident vertices bit-identical, and
        # Douglas-Peucker is symmetric, so both sides then simplify the same way
        # and the edge stays shut.
        vx = (x - minx) * scale + args.pad
        vy = (maxy - y) * scale + args.pad
        return round(vx, 1), round(vy, 1)

    parts, specks = [], 0
    for ring in kept:
        view = [to_view(x, y) for x, y in ring]
        view = simplify(view, args.tolerance)
        if len(view) < 4 or ring_area(view) < args.min_area:
            specks += 1
            continue
        head = f"M{view[0][0]:.1f} {view[0][1]:.1f}"
        body = "".join(f"L{x:.1f} {y:.1f}" for x, y in view[1:])
        parts.append(head + body + "Z")

    cities = []
    for spec in args.city:
        name, lat, lon = spec.rsplit(":", 2)
        x, y = to_view(*project(float(lon), float(lat)))
        cities.append({"name": name, "x": round(x, 1), "y": round(y, 1)})

    out = {
        "w": args.width,
        "h": int(round(height)),
        "region": args.region,
        "unit": args.unit,
        "d": "".join(parts),
        "cities": cities,
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")

    print(
        f"wrote {path} - {args.width}x{out['h']}, {len(parts)} rings, "
        f"{len(out['d']) / 1024:.0f} KB of path, {len(cities)} marker(s)",
        file=sys.stderr,
    )
    if dropped:
        print(f"  excluded: {', '.join(sorted(dropped))}", file=sys.stderr)
    if specks:
        print(f"  dropped {specks} ring(s) below --min-area {args.min_area}", file=sys.stderr)
    for c in cities:
        print(f"  marker {c['name']} at {c['x']},{c['y']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
