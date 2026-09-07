#!/usr/bin/env python3
"""Assert METHODOLOGY section 6's worked example still reproduces.

WHY THIS EXISTS. Section 6 is the reproduction procedure an auditor executes,
and README calls METHODOLOGY "the document that closes B2B audits". It has
broken its own reproducibility claim THREE times:

  2026-08-03  the nearest-waypoint distance was wrong, and the mismatch was
              reconciled with an invented "clipping step" that does not exist
  2026-08-03  again, hours later: the heliport term was ported into the engine
              and this example was left asserting the pre-port figure
  v3.2..v4.0  it asserted `quiet: 5.0` and a total of `6.4` while the API
              returned `6.4` and `6.7` - the two figures transposed - with
              every borough input beside them stale, under a closing sentence
              reading "The methodology is reproducible against the live API"

Each correction was written as a dated note BESIDE the old text, so the old
text survived. Prose cannot hold an example current. This can.

WHAT IT COMPARES, AND WHAT IT DELIBERATELY DOES NOT.
Every borough input, both cohort bounds, all five component values, the persona
weights and the final arithmetic are re-derived from `app` and compared against
what the document states.

`quiet` is the exception and the reason is the point: at SW11 1AA the live API
resolves it from the DEFRA RASTER (`quietResolution: "raster"`), which needs
DynamoDB. Run here, the engine falls back to flight-path geometry and returns a
different number - so comparing them would fail on a correct document. Instead
this asserts that section 6 SAYS the value is raster-resolved and does not
present it as hand-derivable, which is the claim that was actually wrong before.

It needs no network and no credentials, so it can be blocking.

  python scripts/check_worked_example.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / 'METHODOLOGY.md'
sys.path.insert(0, str(ROOT / 'backend' / 'lambdas' / 'score'))

POSTCODE = 'SW11 1AA'
CITY = 'london'
BOROUGH = 'Wandsworth'


def section6(text):
    """The body of section 6 alone. A match found elsewhere proves nothing."""
    start = text.index('## 6. Worked example')
    end = text.index('## 7. Data sources', start)
    return text[start:end]


def find(body, pattern, label, failures, cast=float):
    m = re.search(pattern, body)
    if not m:
        failures.append(
            f'{label}: section 6 no longer states this at all (pattern '
            f'{pattern!r}). Either the example was restructured and this gate '
            f'needs updating, or a number was silently dropped - do not assume '
            f'the first.')
        return None
    return cast(m.group(1).replace(',', ''))


def main():
    import app

    body = section6(DOC.read_text(encoding='utf-8'))
    bd = app.CITIES[CITY]['boroughs'][BOROUGH]
    failures = []
    checks = 0

    # ---- the borough inputs the example prints ----
    stated_inputs = {
        'avgPrice': r'avgPrice:\s+([\d,]+)',
        'trend': r'trend:\s+(-?[\d.]+)',
        'p8': r'p8:\s+(-?[\d.]+)',
        'crimeRate': r'crimeRate:\s+([\d.]+)',
        'airQualityWhoRatio': r'airQualityWhoRatio:\s+([\d.]+)',
        'roadNoiseAboveWhoPct': r'roadNoiseAboveWhoPct:\s+([\d.]+)',
        'floodMediumOrHighPct': r'floodMediumOrHighPct:\s+([\d.]+)',
    }
    for field, pattern in stated_inputs.items():
        said = find(body, pattern, f'input {field}', failures)
        if said is None:
            continue
        checks += 1
        real = bd.get(field)
        if real is None or abs(float(real) - said) > 0.005:
            failures.append(
                f'input {field}: section 6 says {said}, the engine holds {real}')

    # ---- the cohort bounds affordability and growth are anchored on ----
    prices = [b['avgPrice'] for b in app.CITIES[CITY]['boroughs'].values()
              if b.get('avgPrice')]
    trends = [b['trend'] for b in app.CITIES[CITY]['boroughs'].values()
              if b.get('trend') is not None]
    for label, pattern, real in (
        ('cohort min price', r'`min = ([\d,]+)`', min(prices)),
        ('cohort max price', r'`max = ([\d,]+)`', max(prices)),
        ('cohort min trend', r'`min = (-?[\d.]+)`', min(trends)),
        ('cohort max trend', r'`max = (-?[\d.]+)`', max(trends)),
    ):
        said = find(body, pattern, label, failures)
        if said is None:
            continue
        checks += 1
        if abs(said - float(real)) > 0.005:
            failures.append(f'{label}: section 6 says {said}, cohort is {real}')

    # ---- the five component values, from the Step 5 response block ----
    stated = {}
    for comp in ('quiet', 'afford', 'growth', 'live', 'env'):
        said = find(body, rf'"{comp}":\s*(-?[\d.]+)', f'component {comp}', failures)
        if said is not None:
            stated[comp] = said

    # Re-derive the four that do not need the raster.
    derived = {
        'afford': app.calc_afford(bd, CITY) if hasattr(app, 'calc_afford') else None,
        'live': app.get_live_score(bd),
        'env': app.get_env_score(bd),
    }
    for comp, real in derived.items():
        if real is None or comp not in stated:
            continue
        checks += 1
        if abs(stated[comp] - float(real)) > 0.051:
            failures.append(
                f'component {comp}: section 6 says {stated[comp]}, the engine '
                f'derives {real}')

    # ---- quiet must be DECLARED raster-resolved, not hand-derived ----
    checks += 1
    if 'quietResolution": "raster"' not in body and "quietResolution: \"raster\"" not in body:
        failures.append(
            'quiet: section 6 no longer states `quietResolution: "raster"` for '
            'this postcode. That declaration is load-bearing - the live value '
            'is a DEFRA measurement, and two of this example\'s three past '
            'corrections came from hand-deriving it from geometry instead.')

    # ---- the persona weights ----
    #
    # Scoped to the `"weights"` block rather than searched document-wide: the
    # component names appear in BOTH the components block and the weights block
    # with the same shape, so an unscoped search reads a component value as a
    # weight and compares 6.4 against 0.32.
    weights = app.PERSONAS['balanced']
    m = re.search(r'"weights":\s*\{(.+?)\}', body, re.S)
    if not m:
        failures.append('weights: section 6 no longer prints a weights block')
    else:
        checks += 1
        block = m.group(1)
        for comp, w in weights.items():
            got = re.search(rf'"{comp}":\s*(-?[\d.]+)', block)
            if not got:
                failures.append(f'weight {comp}: absent from the weights block')
            elif abs(float(got.group(1)) - w) > 0.005:
                failures.append(
                    f'weight {comp}: section 6 says {got.group(1)}, persona '
                    f'`balanced` carries {w}')

    # ---- and the arithmetic the reader is invited to check ----
    said_score = find(body, r'"score":\s*([\d.]+)', 'published score', failures)
    if said_score is not None and len(stated) == 5:
        checks += 1
        total = sum(stated[c] * weights.get(c, 0) for c in stated)
        if abs(total - said_score) > 0.051:
            failures.append(
                f'ARITHMETIC: the components and weights section 6 prints sum '
                f'to {total:.3f}, but it publishes a score of {said_score}. A '
                f'reader following this section does not get the number it '
                f'ends with - which is exactly the defect this gate exists for.')

    print('METHODOLOGY section 6 vs the engine')
    print('===================================')
    print(f'  postcode          {POSTCODE} ({BOROUGH}, {CITY})')
    print(f'  comparisons made  {checks}')

    if checks < 15:
        print()
        print(f'FAIL: only {checks} comparisons - section 6 was restructured and')
        print('      this gate is no longer reading it. Fix the patterns rather')
        print('      than lowering this floor: a gate that finds nothing to')
        print('      compare reports agreement it never established.')
        return 1

    if failures:
        print()
        print(f'FAIL: {len(failures)} mismatch(es) between the worked example and')
        print('      the engine it claims to reproduce.')
        for f in failures:
            print(f'  - {f}')
        print()
        print('  Section 6 is the reproduction procedure a B2B auditor executes.')
        print('  Re-derive it from the live API rather than patching one figure.')
        return 1

    print()
    print('OK: every input, bound, component, weight and the final arithmetic')
    print('    in section 6 agree with the engine.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
