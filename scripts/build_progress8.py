"""Borough `p8` from DfE Key Stage 4 Progress 8, by local authority.

Why this exists
---------------
`p8` was hand-entered for London and Greater Manchester and had NO pipeline at
all, which made it the blocker for every city added after them: with no schools
input a city has crime alone, `live` falls below its two-input floor and is
dropped, and the whole liveability component disappears. Eight Core Cities
regions shipped API-only for exactly that reason.

VERIFIED AGAINST THE EXISTING DATA, which is the point of doing it this way.
The DfE file reproduces **32 of the 33 London boroughs exactly, none differing**
- so the values already in the repo are this release, and the eight new cities
inherit the same source rather than a second one.

Two things that verification pinned down and guesswork would not have:

  * The vintage is **Revised**, not Final. The same file carries both, and
    `Final` disagrees with the repo on 30 of 32 boroughs. Picking the wrong one
    would have looked like a plausible extraction and quietly re-based every
    London school score.
  * **City of London has no value** - one school, suppressed as `z`. It is
    absent rather than zero, exactly as its crime rate is absent, and the
    suppression markers are non-numeric so a naive float() raises rather than
    silently coercing.

2022/23 is the TERMINAL vintage until 2026/27 publishes: Progress 8 cannot be
calculated for 2023/24 onwards because the KS2 baseline was lost to the 2020 and
2021 test cancellations, and DfE announced no replacement. So this is a one-off
extraction, not a recurring roll.

Source: DfE "Key stage 4 performance", Explore Education Statistics, release
2022-23, file `data/2223_la_data_revised.csv` inside the release bundle.
Open Government Licence v3.0.

Usage
-----
    python scripts/build_progress8.py --check            # against the registry
    python scripts/build_progress8.py --emit --city bristol
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import sys
import types
import zipfile
from pathlib import Path

BUNDLE = Path("data/ks4-2022-23.zip")
MEMBER = "data/2223_la_data_revised.csv"
EXTRACT = Path("data/ks4-la-2022-23.csv")
SCORE_APP = Path("backend/lambdas/score/app.py")

# The release carries both, and they disagree. See the module docstring.
VERSION = "Revised"
GENDER = "Total"
LEVEL = "Local authority"

# Registry borough name -> DfE LA name, only where they differ. Declared, not
# fuzzy-matched: a fuzzy match pairs a genuinely missing authority with a
# similar one and reports success.
LA_RENAME = {
    "City of Bristol": "Bristol, City of",
    "City of Nottingham": "Nottingham",
    "St Helens": "St. Helens",
}


def _city_lads():
    spec = importlib.util.spec_from_file_location("bhp", "scripts/build_hpi_prices.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.CITY_LADS


def _score_app():
    mod = types.ModuleType("score_app_p8")
    mod.__file__ = str(SCORE_APP)
    exec(  # noqa: S102 - first-party file, maintainer-run script, never deployed
        compile(SCORE_APP.read_text(encoding="utf-8"), str(SCORE_APP), "exec"), mod.__dict__
    )
    return mod


def _num(value):
    """None for DfE suppression markers ('z', 'c', ':', '') rather than a raise."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_p8() -> dict[str, float]:
    """{LA name: Progress 8}, all-pupil, revised, local-authority level."""
    if EXTRACT.exists():
        raw = EXTRACT.read_text(encoding="utf-8")
    elif BUNDLE.exists():
        raw = zipfile.ZipFile(BUNDLE).read(MEMBER).decode("utf-8-sig", errors="replace")
        EXTRACT.write_text(raw, encoding="utf-8")
    else:
        raise SystemExit(
            f"Neither {EXTRACT} nor {BUNDLE} is present. Both are gitignored (data/*).\n"
            "Re-download the release bundle from Explore Education Statistics:\n"
            "  https://content.explore-education-statistics.service.gov.uk/api/releases/"
            "90c95fb2-f2a1-4723-aba8-09c4b6e231a5/files\n"
            "That host needs a browser User-Agent; without one it answers 403 and looks bot-blocked."
        )
    out: dict[str, float] = {}
    for row in csv.DictReader(io.StringIO(raw)):
        if (
            row.get("geographic_level") == LEVEL
            and row.get("gender") == GENDER
            and row.get("version") == VERSION
        ):
            value = _num(row.get("avg_p8score"))
            if value is not None:
                out[row["la_name"].strip()] = round(value, 2)
    if len(out) < 100:
        raise SystemExit(f"Only {len(out)} authorities parsed - the file layout has moved.")
    return out


def for_city(city: str, p8: dict[str, float]) -> tuple[dict[str, float], list[str]]:
    lads = _city_lads()[city]
    got, missing = {}, []
    for name in lads:
        value = p8.get(LA_RENAME.get(name, name))
        if value is None:
            missing.append(name)
        else:
            got[name] = value
    return got, missing


def main() -> int:
    registry = _city_lads()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--city", choices=sorted(registry))
    ap.add_argument("--check", action="store_true", help="compare against what the Lambda holds")
    ap.add_argument("--emit", action="store_true", help="print p8 per borough for a city")
    args = ap.parse_args()
    if not (args.check or args.emit):
        ap.error("pass --check or --emit")

    p8 = load_p8()
    print(f"DfE KS4 2022/23 ({VERSION}, {GENDER}): {len(p8)} local authorities\n", file=sys.stderr)

    if args.emit:
        if not args.city:
            ap.error("--emit needs --city")
        got, missing = for_city(args.city, p8)
        for name, value in got.items():
            print(f"    '{name}': {value},")
        for name in missing:
            print(f"    # '{name}': NO PUBLISHED VALUE (suppressed or not an LA)")
        return 1 if missing and not got else 0

    # --check: every city the Lambda holds that has p8 in its boroughs.
    app = _score_app()
    bad = 0
    compared = 0
    skipped = []
    for city in registry:
        if city not in app.CITIES:
            skipped.append(f"{city} (not in the Lambda registry)")
            continue
        held = app.CITIES[city]["boroughs"]
        with_p8 = {n: bd["p8"] for n, bd in held.items() if bd.get("p8") is not None}
        if not with_p8:
            # Legitimate for Cardiff - Progress 8 is an ENGLAND measure. But it
            # is also what a renamed `p8` key looks like, so it is COUNTED and
            # reported rather than silently skipped; see the floor below.
            skipped.append(f"{city} (no borough carries p8)")
            continue
        compared += len(with_p8)
        got, _missing = for_city(city, p8)
        diffs = [
            f"{n}: registry {v} vs DfE {got[n]}"
            for n, v in with_p8.items()
            if n in got and abs(got[n] - v) > 0.005
        ]
        absent = [n for n in with_p8 if n not in got]
        print(f"{city}: {len(with_p8)} boroughs carry p8, {len(diffs)} differ, {len(absent)} not in DfE")
        for d in diffs:
            print(f"    DRIFT: {d}")
        for a in absent:
            print(f"    NOT PUBLISHED: {a}")
        bad += len(diffs)

    # THE FLOOR. `if not with_p8: continue` meant that renaming the `p8` key
    # made every city skip and this print "RESULT: PASS" having compared
    # nothing - output indistinguishable from a clean run. Audit finding I5's
    # class. Cardiff legitimately has no p8, so the floor is on the TOTAL
    # rather than per city, and the skips are named either way.
    for line in skipped:
        print(f"  skipped: {line}")
    print(f"\nCompared {compared} Progress 8 value(s).")
    if not compared:
        print("FAIL: compared nothing. Every city was skipped, so this run "
              "proves no agreement with DfE whatsoever - it is not a pass.")
        return 1
    print(f"RESULT: {'PASS' if bad == 0 else f'FAIL ({bad} differ)'}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
