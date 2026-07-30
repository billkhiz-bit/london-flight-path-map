"""Trim the UK-wide LAD boundary file down to the London boroughs.

Why this exists
---------------
`index.html` used to load borough boundaries straight from
`raw.githubusercontent.com/martinjc/UK-GeoJSON` — a **19.2 MB** file covering
all 380 GB local authority districts — and then discard everything outside
London in the browser. Worse, `init()` awaits that download before it reveals
`#app`, so a slow or congested network held the entire app on its loading
spinner. Two consequences worth spelling out:

* first paint depended on a third party we do not control, and
* every visitor paid for 347 districts they never saw.

This script moves the filter to build time. The output is byte-for-byte
equivalent in *rendered* terms — the same features the browser kept before —
but small enough to serve from our own origin and precache offline.

The second URL the app used as a fallback
(`charlesroper/OSGB36-London-Boroughs`) has been returning **404** for some
time, so it was never a real fallback. It is dropped rather than repaired.

Usage
-----
    python scripts/build_london_boroughs.py            # fetch + trim
    python scripts/build_london_boroughs.py --src FILE  # trim a local copy

Re-run when the LAD vintage rolls (the source tracks ONS editions). Verify the
output by feature count, not file size: 33 features is correct, anything under
30 means the name matching has drifted and needs looking at.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

# The source of truth for "which boroughs" is index.html's BOROUGH_DATA_RAW.
# Kept in this order to mirror that block, so a diff between the two reads
# cleanly. 32 boroughs plus the City of London.
LONDON_BOROUGHS = [
    "Hounslow",
    "Hillingdon",
    "Richmond upon Thames",
    "Ealing",
    "Wandsworth",
    "Lambeth",
    "Lewisham",
    "Greenwich",
    "Tower Hamlets",
    "Camden",
    "Islington",
    "Hackney",
    "Barnet",
    "Croydon",
    "Bromley",
    "Newham",
    "Southwark",
    "Hammersmith and Fulham",
    "Kensington and Chelsea",
    "Brent",
    "Haringey",
    "Waltham Forest",
    "Merton",
    "Redbridge",
    "Enfield",
    "Kingston upon Thames",
    "Sutton",
    "Westminster",
    "City of London",
    "Barking",
    "Havering",
    "Bexley",
    "Harrow",
]

SRC_URL = "https://raw.githubusercontent.com/martinjc/UK-GeoJSON/master/json/administrative/gb/lad.json"
OUT_PATH = Path("data/london-boroughs.json")

# Matches getName() in index.html. Kept in the same precedence order — the
# source vintage decides which of these keys is actually populated.
NAME_KEYS = (
    "name",
    "NAME",
    "LAD13NM",
    "LAD21NM",
    "LAD24NM",
    "borough",
    "name_2",
    "lad_name",
)

# ~1 m at London's latitude. Borough outlines are drawn at city scale, so the
# 13-15 decimal places in the source are noise that costs bytes.
COORD_PRECISION = 5


def feature_name(feature: dict) -> str:
    """Mirror of getName() in index.html."""
    props = feature.get("properties") or {}
    for key in NAME_KEYS:
        value = props.get(key)
        if value:
            return str(value)
    return ""


def _boundary_match(shorter: str, longer: str) -> bool:
    """True when `shorter` is `longer` cut at a word boundary.

    This is the fix for a bug the browser-side filter still has. index.html
    matches with a bare substring test in both directions, which accepts
    **Brentwood** (Essex) because the borough key "Brent" is a prefix of it.
    Brentwood was being drawn as a London borough and, being ~30 km
    north-east of the others, was also feeding the projection's fitted extent
    an outlier.

    A plain equality test is not the answer either: the app's key is "Barking"
    while the LAD name is "Barking and Dagenham". So require a prefix match
    *terminated by a space* — "Barking and..." qualifies, "Brentwood" does not.
    """
    if not longer.startswith(shorter):
        return False
    return len(longer) == len(shorter) or longer[len(shorter)] == " "


def is_london(name: str) -> bool:
    """Word-boundary-safe version of index.html's borough match."""
    if not name:
        return False
    lowered = name.lower().strip()
    for borough in LONDON_BOROUGHS:
        key = borough.lower()
        if lowered == key:
            return True
        # Check both directions, as the source vintage may be more or less
        # verbose than our key (e.g. "Barking and Dagenham" vs "Barking").
        if _boundary_match(key, lowered) or _boundary_match(lowered, key):
            return True
    return False


def round_coords(node):
    """Recursively round coordinate floats, preserving nesting depth."""
    if isinstance(node, list):
        return [round_coords(item) for item in node]
    if isinstance(node, float):
        return round(node, COORD_PRECISION)
    return node


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", help="path to a local lad.json instead of fetching")
    parser.add_argument("--out", default=str(OUT_PATH), help="output path")
    args = parser.parse_args()

    if args.src:
        raw = Path(args.src).read_text(encoding="utf-8")
    else:
        print(f"fetching {SRC_URL} ...", file=sys.stderr)
        with urllib.request.urlopen(SRC_URL, timeout=120) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8")

    source = json.loads(raw)
    features = source.get("features") or []
    print(f"source features: {len(features)}", file=sys.stderr)

    kept = []
    for feature in features:
        name = feature_name(feature)
        if not is_london(name):
            continue
        feature["geometry"]["coordinates"] = round_coords(
            feature["geometry"]["coordinates"]
        )
        kept.append(feature)

    if len(kept) < 30:
        names = sorted(feature_name(f) for f in kept)
        print(
            f"ERROR: only matched {len(kept)} boroughs, expected 33.\n"
            f"Matched: {names}\n"
            "The source's name field has probably changed — check NAME_KEYS.",
            file=sys.stderr,
        )
        return 1

    out = {"type": "FeatureCollection", "features": kept}
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # separators= drops the whitespace json.dump would otherwise emit; this is
    # a served asset, not something a human reads.
    out_path.write_text(
        json.dumps(out, separators=(",", ":"), ensure_ascii=False), encoding="utf-8"
    )

    size_kb = out_path.stat().st_size / 1024
    print(
        f"wrote {out_path} — {len(kept)} boroughs, {size_kb:.0f} KB",
        file=sys.stderr,
    )
    for name in sorted(feature_name(f) for f in kept):
        print(f"  - {name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
