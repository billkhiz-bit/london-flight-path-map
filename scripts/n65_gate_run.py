#!/usr/bin/env python3
"""The N65 gate's input made by code from the day files, never typed by hand: N65's frozen method (2026-11-12).

WHY THIS EXISTS (2026-11-12)
----------------------------
scripts/n65_gate.py held Bill's 27 Oct publish rule from the start, but nothing built its input: the period, the day,
the window and the database were strings a caller typed, so a run from 300 of 365 days could be typed in as the full
year, and the CAA's own figures failed after one JSON round trip (the 12 Nov review). This reads saved day files
(scripts/n65_day.py) and makes the run from them alone:

- the PERIOD is the first and last day the files hold, and every date between them that has no file is listed as
  missing (n65_gate fails a run missing any day but a known source gap, which it says);
- the DAY is the average of every day held, equal weights (the CAA's annual or summer average day), named from the
  period: 'annual average' for a whole year, 'summer average' for 16 Jun - 15 Sep, else 'N-day average', which no
  target matches;
- the WINDOW is the files' own;
- rule 1: each day's counts times its `scale` (the CAA's movements over those computed), unless `--unscaled`;
- rule 2: the 5-12 shares (Doc 29's distribution of levels), unless `--no-spread`;
- rule 3: BOTH stage ends, lightest and heaviest, each judged at every level;
- the DATABASE is n65_gate.database_label() of the files' noise-table fingerprint, never a label;
- days made by other code, noise tables, grid, threshold, window, spread or variant are refused (n65_day.incompatible).

The verdict is written to a file beside the day files (or `--out`), with every line behind it and the run itself.
One airport's verdict decides nothing alone: n65_gate.publish_verdict needs both airports on the deciding database.
Nothing here is published, and the files it reads and writes are EASA-derived: outside the repo or gitignored only.

    python -B scripts/n65_gate_run.py --day <dir>/LHR-2025-*.npz [--unscaled] [--no-spread] [--out <dir>]
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import sys
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import n65_day as nd  # noqa: E402
import n65_gate as gate  # noqa: E402


class Refused(ValueError):
    """These day files cannot make a run."""


def load_day(path: Path) -> tuple[dict, dict]:
    """(meta, {array name: array}) from one day file."""
    with np.load(path, allow_pickle=False) as z:
        return json.loads(str(z['meta'])), {k: z[k] for k in z.files if k != 'meta'}


def day_kind(period: tuple[str, str]) -> str:
    """The average day a period makes: 'annual average' for a whole year, 'summer average' for 16 Jun - 15 Sep (the
    CAA's 92-day summer), else 'N-day average'."""
    first, last = dt.date.fromisoformat(period[0]), dt.date.fromisoformat(period[1])
    span = (last - first).days + 1
    if span == (dt.date(first.year + 1, first.month, first.day) - first).days:
        return 'annual average'
    if (first.month, first.day, last.month, last.day) == (6, 16, 9, 15) and first.year == last.year:
        return 'summer average'
    return f'{span}-day average'


def build_runs(days: list[tuple[dict, dict]], *, scaled: bool = True, spread: bool = True) -> tuple[str, dict, dict]:
    """(airport, {'light': run, 'heavy': run}, about) from loaded day files, or Refused."""
    if not days:
        raise Refused('no day files')
    metas = [m for m, _ in days]
    problems = nd.incompatible(metas)
    if problems:
        raise Refused('the days cannot be averaged together: ' + '; '.join(problems))
    names = [m['day'] for m in metas]
    if len(set(names)) != len(names):
        raise Refused(f'a day is given twice: {sorted(n for n in names if names.count(n) > 1)}')
    airport = metas[0]['airport']
    if airport not in gate.TARGETS:
        raise Refused(f'no CAA yardstick for {airport}')
    if scaled:
        unscaled = [m['day'] for m in metas if not isinstance(m.get('scale'), (int, float))]
        if unscaled:
            raise Refused(f'rule 1: no scale in {", ".join(unscaled)} (made before rule 1; run them again, or '
                          'ask for --unscaled)')
    keys = [f'{k}_p' if spread else k for k in ('arrivals', 'departures_light', 'departures_heavy')]
    for meta, arrays in days:
        lacking = [k for k in keys if k not in arrays]
        if lacking:
            raise Refused(f'rule 2: {meta["day"]} has no {", ".join(lacking)} (made before rule 2; run it again, or '
                          'ask for --no-spread)')
    period = (min(names), max(names))
    missing = gate.missing_days(period, names)
    levels = list(gate.TARGETS[airport]['areas_km2'])
    cell = metas[0]['cell_m']
    runs = {}
    for end in gate.STAGE_ENDS:
        total = None
        for meta, arrays in days:
            n = arrays[keys[0]].astype(np.float64) + arrays[keys[1 if end == 'light' else 2]]
            n = n * (meta['scale'] if scaled else 1.0)
            total = n if total is None else total + n
        mean = total / len(days)
        runs[end] = {
            'period': period, 'day': day_kind(period), 'window': metas[0]['window_local'],
            'areas_km2': {int(k): v for k, v in nd.areas_km2(mean, cell, levels).items()},
            'population_above_50': None,  # not built yet (the lesson's step 5, item 3): the gate says so
            'missing_days': missing,
        }
    about = {
        'airport': airport, 'days': [{'day': m['day'], 'computed_share': m.get('computed_share'),
                                      'scale': m.get('scale')} for m in metas],
        'missing_days': missing, 'variant': metas[0].get('variant', 'default'),
        'rule_1_scaled': scaled, 'rule_2_spread': spread,
        'database': gate.database_label(metas[0].get('anp_fingerprint')),
        'code': metas[0].get('code'),
    }
    return airport, runs, about


def verdict(days: list[tuple[dict, dict]], *, scaled: bool = True, spread: bool = True) -> dict:
    """{'ok': this airport passes on the deciding database, 'lines': every line, 'runs', 'about'}."""
    airport, runs, about = build_runs(days, scaled=scaled, spread=spread)
    ok, lines = gate.bracket_verdict(airport, runs)
    if about['variant'] != 'default':
        ok = False
        lines.append(f"variant {about['variant']!r}: a bound, never the model (rule 4): it decides nothing")
    if about['database'] != gate.DECIDING_DATABASE:
        ok = False
        lines.append(f"built with {about['database']!r}: a building run, never a deciding one")
    for name, on in (('rule 1 (scaled to the CAA movements)', scaled), ('rule 2 (Doc 29 level distribution)', spread)):
        if not on:
            ok = False
            lines.append(f'{name} OFF: a variant reported beside, never the deciding run')
    lines.append('one airport alone decides nothing: n65_gate.publish_verdict needs both airports')
    return {'ok': ok, 'lines': lines, 'runs': runs, 'about': about}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--day', action='append', required=True, help='day file(s) or a glob (n65_day.py day output)')
    p.add_argument('--unscaled', action='store_true', help='rule 1 off: the variant reported beside')
    p.add_argument('--no-spread', action='store_true', help='rule 2 off: the variant reported beside')
    p.add_argument('--out', help='where the verdict goes (default: beside the first day file)')
    a = p.parse_args(argv)
    paths = sorted({Path(f) for spec in a.day for f in (glob.glob(spec) or [spec])})
    try:
        days = [load_day(f) for f in paths]
        result = verdict(days, scaled=not a.unscaled, spread=not a.no_spread)
    except (Refused, OSError, KeyError) as e:
        print(f'REFUSED: {e}')
        return 2
    out = Path(a.out) if a.out else paths[0].parent
    if not nd._safe_out(out):
        print(f'REFUSED: --out {out} is a tracked place in the repo; the verdict holds EASA-derived areas')
        return 2
    first, last = result['runs']['light']['period']
    tag = ('scaled' if not a.unscaled else 'unscaled') + ('-spread' if not a.no_spread else '-nospread')
    name = f"gate-{result['about']['airport']}-{first}_{last}-{result['about']['variant']}-{tag}.json"
    out.mkdir(parents=True, exist_ok=True)
    (out / name).write_text(json.dumps(result, indent=1), encoding='utf-8')
    print('\n'.join(result['lines']))
    print(f"{'PASS' if result['ok'] else 'NO'}: written to {out / name}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
