#!/usr/bin/env python3
"""Cost a real-terms (CPIH-adjusted) growth component before deciding on it.

WHY THIS EXISTS (2026-09-13). ROADMAP's open-decisions table carries "CPI /
real-terms growth adjustment" with the instruction: "After a decision AND a
costing like v5.0's: measure the movement on every borough before writing
it." This is that costing. It changes nothing - no holder, no engine, no
page - and prints what WOULD move, so the decision is made on numbers rather
than on the intuition that inflation matters.

WHAT IT MEASURES. `trend` today is the UK HPI 12-month change in NOMINAL
terms, and growth_score() anchors 0% at 5.0 with each tail scaled to the
cohort extreme. A real-terms version deflates every borough's trend by the
CPIH 12-month rate for the same month:

    real = ((1 + nominal/100) / (1 + cpih/100) - 1) * 100

which is not `nominal - cpih` (the difference is a few hundredths of a point
at these rates, but the exact form costs nothing). The 5.0 anchor then means
"holding its value against prices in general" rather than "not falling in
cash terms". The cohort extremes are re-derived from the real trends.

Reported per city: how many boroughs FLIP sign (rising in cash, falling in
real terms - the product-facing number, because "rising" is a word the panel
prints), the growth-component movement, and the investor composite movement
(growth is weighted for the `investor` persona only, so `balanced` scores do
not move - but `trend` is a published field for everyone, which is the
other half of the decision).

SOURCE. ONS CPIH ANNUAL RATE 00: ALL ITEMS (series L55O, dataset MM23),
fetched from www.ons.gov.uk and cached in data/ (gitignored). The month is
matched to the HPI vintage the registry carries; pass --cpih to override
(e.g. to cost a hypothetical rate).

USAGE
    python scripts/cost_real_growth.py            # CPIH for the engine's SNAPSHOT_VINTAGE_LABEL month
    python scripts/cost_real_growth.py --cpih 2.8 # a stated rate
    python scripts/cost_real_growth.py --csv out.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import types
import urllib.request
from pathlib import Path

SCORE_APP = Path('backend/lambdas/score/app.py')
CPIH_URL = 'https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/l55o/mm23/data'
CPIH_CACHE = Path('data/ons_cpih_l55o.json')


def load_engine():
    """Compile the score Lambda from its SOURCE TEXT, never import it.

    Same reason refresh_crime_from_ons.py gives: importlib honours
    __pycache__, and a same-length edit inside one clock second has been
    seen to run stale bytecode here. The text has no cache to be stale.
    """
    mod = types.ModuleType('score_app_growth_costing')
    mod.__file__ = str(SCORE_APP)
    exec(  # noqa: S102 - first-party file in this repo, maintainer-run
        compile(SCORE_APP.read_text(encoding='utf-8'), str(SCORE_APP), 'exec'), mod.__dict__
    )
    return mod


def cpih_for(vintage: str) -> float:
    """The CPIH 12-month rate for `vintage`, from the cached ONS series.

    `vintage` is the engine's SNAPSHOT_VINTAGE_LABEL ('June 2026') - the one
    holder for the HPI month, which is why it is read rather than typed.
    """
    if not CPIH_CACHE.exists():
        CPIH_CACHE.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(CPIH_URL, headers={'User-Agent': 'Mozilla/5.0'})  # noqa: S310
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            CPIH_CACHE.write_bytes(resp.read())
    series = json.loads(CPIH_CACHE.read_text(encoding='utf-8'))
    title = series.get('description', {}).get('title', '')
    if 'CPIH' not in title.upper():
        sys.exit(f'{CPIH_CACHE} is not the CPIH series (title: {title!r}); delete it and re-run.')
    month_name, year = vintage.split()
    want = f'{year} {month_name[:3].upper()}'
    for m in series['months']:
        if m['date'] == want:
            return float(m['value'])
    latest = series['months'][-1]['date'] if series.get('months') else 'none'
    sys.exit(f'CPIH has no month {want!r} (latest cached: {latest}). Pass --cpih, or delete the cache to refetch.')


def real_terms(nominal: float, cpih: float) -> float:
    return ((1 + nominal / 100) / (1 + cpih / 100) - 1) * 100


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--cpih', type=float, help='CPIH 12-month rate to use instead of the vintage month')
    ap.add_argument('--csv', type=Path, help='write the per-borough table here')
    args = ap.parse_args()

    app = load_engine()
    vintage = getattr(app, 'SNAPSHOT_VINTAGE_LABEL', None)
    if args.cpih is not None:
        cpih, basis = args.cpih, 'stated'
    else:
        if not vintage:
            sys.exit('the engine exposes no HPI vintage constant; pass --cpih')
        cpih, basis = cpih_for(vintage), f'ONS L55O for {vintage}'
    # PERSONAS maps persona -> weights dict directly (no 'weights' key).
    weight = app.PERSONAS['investor']['growth']
    weighted = [p for p, v in app.PERSONAS.items() if v.get('growth', 0) > 0]

    print(f'CPIH 12-month rate: {cpih:.1f}% ({basis})')
    print(f'growth weight: {weight} for {weighted} - every other persona weights it 0, so only those composites move')
    print()

    rows = []
    for city, cd in sorted(app.CITIES.items()):
        boroughs = {n: b for n, b in cd['boroughs'].items() if isinstance(b.get('trend'), (int, float))}
        if not boroughs:
            continue
        nominal = {n: float(b['trend']) for n, b in boroughs.items()}
        real = {n: real_terms(t, cpih) for n, t in nominal.items()}
        n_max, n_min = max(nominal.values()), min(nominal.values())
        r_max, r_min = max(real.values()), min(real.values())
        flips = []
        moves = []
        for n in boroughs:
            g0 = app.growth_score(nominal[n], n_max, n_min)
            g1 = app.growth_score(real[n], r_max, r_min)
            moves.append(g1 - g0)
            if nominal[n] > 0 >= real[n]:
                flips.append(n)
            rows.append({
                'city': city, 'borough': n,
                'trend_nominal': round(nominal[n], 2), 'trend_real': round(real[n], 2),
                'growth_nominal': round(g0, 2), 'growth_real': round(g1, 2),
                'growth_delta': round(g1 - g0, 2),
                'investor_composite_delta_approx': round((g1 - g0) * weight, 2),
                'sign_flip': nominal[n] > 0 >= real[n],
            })
        rising_now = sum(1 for t in nominal.values() if t > 0)
        rising_real = sum(1 for t in real.values() if t > 0)
        print(f'{city:16s} boroughs={len(boroughs):2d}  rising: nominal {rising_now:2d} -> real {rising_real:2d}'
              f'  sign flips={len(flips):2d}  growth delta: mean {statistics.mean(moves):+.2f}'
              f'  range [{min(moves):+.2f}, {max(moves):+.2f}]')
        for n in flips:
            print(f'    flips: {n:28s} {nominal[n]:+.1f}% nominal -> {real[n]:+.1f}% real')

    total = len(rows)
    flips = sum(1 for r in rows if r['sign_flip'])
    rising_now = sum(1 for r in rows if r['trend_nominal'] > 0)
    rising_real = sum(1 for r in rows if r['trend_real'] > 0)
    deltas = [r['growth_delta'] for r in rows]
    comp = [r['investor_composite_delta_approx'] for r in rows]
    moved_01 = sum(1 for d in comp if abs(d) >= 0.05)
    print()
    print(f'TOTAL {total} boroughs: "rising" reads {rising_now} today and would read {rising_real} in real terms '
          f'({flips} flip from rising to falling).')
    print(f'growth component: mean {statistics.mean(deltas):+.2f}, worst {min(deltas):+.2f}, best {max(deltas):+.2f}')
    print(f'investor composite (growth delta x {weight}, before the engine rounds): '
          f'mean {statistics.mean(comp):+.2f}; {moved_01} of {total} would move by 0.1 or more at 1dp')
    print()
    print('Not measured here, and part of the decision: `trend` is PUBLISHED to every persona as the')
    print('nominal HPI change, so a real-terms score needs either a second field (trendReal) or a')
    print('relabel - and either is a methodology version bump with the 14 days\' notice s12 promises.')

    if args.csv:
        with args.csv.open('w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f'\nwrote {args.csv}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
