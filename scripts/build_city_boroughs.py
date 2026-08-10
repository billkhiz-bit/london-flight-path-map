"""Trim the UK-wide LAD boundary file down to one city's authorities.

Generalises scripts/build_london_boroughs.py, which hardcodes London and matches
on NAMES. This one matches on ONS CODES, taken from the single CITY_LADS
registry in scripts/build_hpi_prices.py, so the boundaries a city draws and the
prices it scores from cannot describe different sets of authorities.

WHY NOT NAMES
-------------
The two files disagree about names for the same place, in both directions:
`St. Helens` here against `St Helens` in HPI, `Bristol, City of` here against
`City of Bristol` in HPI. build_london_boroughs.py already documents a third
case where a bare substring match drew **Brentwood** (Essex) as a London borough
because the key `Brent` is a prefix of it.

WHY THE CODES STILL NEED A MAP
------------------------------
The boundary source is a **2013** LAD vintage (`LAD13CD`) and ONS has reissued
some codes since. Checked across all 81 authorities in CITY_LADS, exactly two
differ, and both are in South Yorkshire:

    Barnsley    E08000038 (current)  ->  E08000016 (2013 file)
    Sheffield   E08000039 (current)  ->  E08000019 (2013 file)

Filtering on current codes alone would therefore have produced a South
Yorkshire of two boroughs that rendered perfectly and scored a cohort of two.
LEGACY_CODES closes that, and the per-city count assertion is what would catch
the next one - a city that comes up short FAILS rather than shipping thin.

Usage
-----
    python scripts/build_city_boroughs.py --city westmidlands
    python scripts/build_city_boroughs.py --all
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import urllib.request
from pathlib import Path

SRC_URL = "https://raw.githubusercontent.com/martinjc/UK-GeoJSON/master/json/administrative/gb/lad.json"
CACHE = Path("data/uk-lad.json")

# ~1 m at UK latitudes. Outlines are drawn at city scale, so the source's 13-15
# decimal places are bytes with no visible effect. Matches build_london_boroughs.
COORD_PRECISION = 5

# Current ONS code -> the code the 2013 boundary file uses. Only populate this
# from a MEASURED mismatch (run --all and read the failures), never from memory.
LEGACY_CODES = {
    "E08000038": "E08000016",  # Barnsley
    "E08000039": "E08000019",  # Sheffield
}

# London and Greater Manchester already have checked-in boundary files built by
# other routes; regenerating them here would churn bytes for no gain.
SKIP = {"london", "manchester"}


def city_lads() -> dict[str, dict[str, str]]:
    """CITY_LADS from the HPI script - one registry, not two."""
    spec = importlib.util.spec_from_file_location("bhp", "scripts/build_hpi_prices.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.CITY_LADS


def round_coords(node):
    if isinstance(node, list):
        return [round_coords(item) for item in node]
    if isinstance(node, float):
        return round(node, COORD_PRECISION)
    return node


def load_source() -> dict:
    if not CACHE.exists():
        print(f"fetching {SRC_URL} ...", file=sys.stderr)
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(SRC_URL, timeout=300) as resp:
            CACHE.write_bytes(resp.read())
    return json.loads(CACHE.read_text(encoding="utf-8"))


def build(city: str, lads: dict[str, str], source: dict) -> int:
    by_code = {}
    for feature in source.get("features", []):
        code = (feature.get("properties") or {}).get("LAD13CD")
        if code:
            by_code[code] = feature

    kept, missing = [], []
    for name, code in lads.items():
        feature = by_code.get(code) or by_code.get(LEGACY_CODES.get(code, ""))
        if not feature:
            missing.append(f"{name} ({code})")
            continue
        kept.append(
            {
                "type": "Feature",
                # The CURRENT code and the REGISTRY name, not the 2013 file's,
                # so downstream keys match what the score Lambda holds.
                "properties": {"code": code, "name": name},
                "geometry": {
                    "type": feature["geometry"]["type"],
                    "coordinates": round_coords(feature["geometry"]["coordinates"]),
                },
            }
        )

    if missing:
        print(f"{city}: FAILED - {len(missing)} authority/authorities unresolved:", file=sys.stderr)
        for m in missing:
            print(f"    {m}", file=sys.stderr)
        print("    Add a LEGACY_CODES entry, or the boundary vintage has moved again.", file=sys.stderr)
        return 1

    out = Path(f"data/{city}-boroughs.json")
    out.write_text(
        json.dumps({"type": "FeatureCollection", "features": kept}, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"{city}: wrote {out} - {len(kept)}/{len(lads)} authorities, {out.stat().st_size / 1024:.0f} KB")
    return 0


def main() -> int:
    registry = city_lads()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--city", choices=sorted(registry))
    ap.add_argument("--all", action="store_true", help="build every city without a checked-in file")
    args = ap.parse_args()
    if not args.city and not args.all:
        ap.error("pass --city or --all")

    source = load_source()
    cities = sorted(set(registry) - SKIP) if args.all else [args.city]
    bad = sum(build(c, registry[c], source) for c in cities)
    print(f"\nRESULT: {'PASS' if bad == 0 else f'FAIL ({bad} cities)'}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
