"""Replay the growth component month by month under each anchoring design and
measure the churn - the costing behind methodology v5.2 (2026-09-16).

Why this exists
---------------
The July 2026 HPI roll moved 78 of 99 `investor` scores on one ordinary monthly
release: Hartlepool's growth went 0.0 -> 10.0 because Teesside's fastest riser
changed hands, Newport's 8.5 -> 0.0 for the same reason in Cardiff's four. The
question was whether that is the formula or the data, and the answer had to be
measured rather than argued - the same discipline as `cost_real_growth.py`
(v5.1) and the linear-vs-log comparison that decided v5.0.

What it does
------------
Reads the cached HPI file for the engine's current vintage (a FULL time series,
every month for every area) and the cached ONS CPIH series, deflates every
borough's 12-month change by its own month's CPIH, and scores growth for each
of the last 24 months under four designs:

  current  the city cohort's extremes, monthly real trend        (v5.1)
  A        the whole currency pool's extremes, monthly real trend (v5.2)
  B        the city cohort, on a 3-month mean of the real trend
  A+B      both

For each it prints the mean absolute month-on-month change per borough, the
share of transitions moving 2+ and 5+ points, the largest, and the mean
within-city spread (max - min) - the last being the diagnosis: 8.79 of 10 under
the city cohort means nearly every city spans the whole scale every month by
construction, one borough at each rail.

Imports growth_score / real_trend_pct / round_1dp from the engine so the
arithmetic is the engine's, not a copy. Changes nothing; needs no network once
the two caches exist (`build_hpi_prices.py --check` and `cost_real_growth.py`
both populate them).

  python scripts/cost_growth_anchor.py
"""

import csv
import importlib.util
import json
import statistics
import sys
import types
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MONTHS_BACK = 24
MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def load_engine():
    """The score Lambda, compiled from source text like the gates do."""
    mod = types.ModuleType("score_app_growth_anchor")
    src = ROOT / "backend" / "lambdas" / "score" / "app.py"
    mod.__file__ = str(src)
    exec(compile(src.read_text(encoding="utf-8"), str(src), "exec"), mod.__dict__)  # noqa: S102
    return mod


def load_hpi_script():
    spec = importlib.util.spec_from_file_location("hpi", ROOT / "scripts" / "build_hpi_prices.py")
    hpi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hpi)
    return hpi


def main() -> int:
    app = load_engine()
    hpi = load_hpi_script()
    city_codes = {city: list(m.values()) for city, m in hpi.CITY_LADS.items()}
    code_to_city = {code: city for city, codes in city_codes.items() for code in codes}
    city_name = {city: app.CITIES[city]["name"] for city in city_codes}

    cpih_cache = ROOT / "data" / "ons_cpih_l55o.json"
    if not cpih_cache.exists():
        sys.exit(f"{cpih_cache} missing - run scripts/cost_real_growth.py once to fetch it")
    cpih = {}
    for m in json.loads(cpih_cache.read_text(encoding="utf-8"))["months"]:
        y, mon = m["date"].split()
        cpih[f"{y}-{MONTHS[mon]:02d}"] = float(m["value"])

    hpi_file = hpi.cache_path(hpi.DEFAULT_VINTAGE)
    if not hpi_file.exists():
        sys.exit(f"{hpi_file} missing - run scripts/build_hpi_prices.py --check --all once to fetch it")
    nominal = defaultdict(dict)
    names = {}
    with hpi_file.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            code = row["Area_Code"]
            if code not in code_to_city or not row["Annual_Change"]:
                continue
            nominal[row["Date"][:7]][code] = float(row["Annual_Change"])
            names[code] = row["Region_Name"]

    months = sorted(m for m in nominal if m in cpih)[-MONTHS_BACK:]
    codes = sorted(code_to_city)
    if len(months) < 12:
        sys.exit(f"only {len(months)} months with both HPI and CPIH - not enough to measure churn")
    missing = [m for m in months if len(nominal[m]) != len(codes)]
    if missing:
        sys.exit(f"months missing boroughs: {missing}")

    def real(month, code):
        return app.real_trend_pct(nominal[month][code], cpih[month])

    def smoothed_real(month, code, k=3):
        i = months.index(month)
        window = months[max(0, i - k + 1): i + 1]
        return app.round_1dp(statistics.mean(real(m, code) for m in window))

    def score_city_anchor(month, value_fn):
        by_city = defaultdict(list)
        for c in codes:
            by_city[code_to_city[c]].append(value_fn(month, c))
        return {
            c: app.round_1dp(app.growth_score(value_fn(month, c), max(by_city[code_to_city[c]]), min(by_city[code_to_city[c]])))
            for c in codes
        }

    def score_pool_anchor(month, value_fn):
        vals = [value_fn(month, c) for c in codes]
        return {c: app.round_1dp(app.growth_score(value_fn(month, c), max(vals), min(vals))) for c in codes}

    designs = {
        "current: city cohort, monthly real trend (v5.1)": lambda m: score_city_anchor(m, real),
        "A: currency POOL, monthly real trend (v5.2)": lambda m: score_pool_anchor(m, real),
        "B: city cohort, 3-month mean real trend": lambda m: score_city_anchor(m, smoothed_real),
        "A+B: pool, 3-month mean": lambda m: score_pool_anchor(m, smoothed_real),
    }

    def churn(series):
        deltas, per_city = [], defaultdict(list)
        for a, b in zip(months, months[1:], strict=False):  # a sliding pair, lengths differ by one
            for c in codes:
                d = abs(series[b][c] - series[a][c])
                deltas.append(d)
                per_city[code_to_city[c]].append(d)
        return deltas, per_city

    def spread(series):
        return statistics.mean(
            max(series[m][c] for c in cs) - min(series[m][c] for c in cs)
            for m in months for cs in city_codes.values()
        )

    print(f"{len(codes)} sterling boroughs, {len(months)} months ({months[0]} .. {months[-1]}), "
          f"{len(months) - 1} transitions each; HPI {hpi.DEFAULT_VINTAGE[:7]} file\n")
    hdr = f"{'design':50s} {'mean|d|':>8s} {'p90':>6s} {'>=2.0':>7s} {'>=5.0':>7s} {'max':>5s} {'city spread':>12s}"
    print(hdr)
    print("-" * len(hdr))
    results = {}
    for name, fn in designs.items():
        series = {m: fn(m) for m in months}
        results[name] = series
        deltas, _ = churn(series)
        p90 = statistics.quantiles(deltas, n=10)[8]
        print(f"{name:50s} {statistics.mean(deltas):8.3f} {p90:6.1f} "
              f"{sum(d >= 2 for d in deltas) / len(deltas):7.1%} {sum(d >= 5 for d in deltas) / len(deltas):7.1%} "
              f"{max(deltas):5.1f} {spread(series):12.2f}")

    print("\nMean |month-on-month growth change| by city, per design:")
    for city, cs in city_codes.items():
        row = [statistics.mean(churn(results[n])[1][city]) for n in designs]
        print(f"   {city_name[city]:20s} n={len(cs):2d}  " + "  ".join(f"{v:5.2f}" for v in row))

    last, prev = months[-1], months[-2]
    print(f"\nThe {prev} -> {last} transition, the largest movers under the city cohort:")
    cur = results[next(iter(designs))]
    movers = sorted(codes, key=lambda c: abs(cur[last][c] - cur[prev][c]), reverse=True)[:6]
    for c in movers:
        line = f"   {names[c]:24s}"
        for n in designs:
            s = results[n]
            line += f"  {s[prev][c]:4.1f}->{s[last][c]:4.1f}"
        print(line)

    print("\nBoroughs on a rail (10.0 or 0.0) in the latest month, per design:")
    for n in designs:
        s = results[n][last]
        print(f"   {n:50s} at 10.0: {sum(1 for c in codes if s[c] == 10.0):2d}   at 0.0: {sum(1 for c in codes if s[c] == 0.0):2d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
