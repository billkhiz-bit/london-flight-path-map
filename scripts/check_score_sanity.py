#!/usr/bin/env python3
"""Production sanity check for /v1/score. Asserts invariants nothing else can.

WHY THIS EXISTS (2026-08-03). The DEFRA raster served Heathrow Airport a quiet
score of 7.5/10 for roughly a week, in production, with preflight green
throughout. Nothing in the gate could have caught it:

  * the unit suites never reach DynamoDB, so they scored the Haversine tier and
    passed while production served something else entirely;
  * the Playwright suite asserts the consumer site against itself, so a site/API
    divergence is invisible to it;
  * both are correctness checks on CODE, and the defect was in DATA.

This closes that gap. It runs against the live API and asserts properties that
must hold whatever the data says, so a bad load fails loudly on the day it lands
rather than after someone notices by eye.

It also guards the OTHER failure mode from that day: conclusions drawn from a
handful of postcodes. Two separate wrong diagnoses came out of eight-postcode
samples, one of them confident enough to be written into the methodology. Every
distribution assertion here therefore runs over the full sample, and the failure
messages print the evidence rather than just a verdict.

Usage:
    python scripts/check_score_sanity.py                 # live API
    python scripts/check_score_sanity.py --api-key KEY
    SKY_SCORE_API_KEY=... python scripts/check_score_sanity.py

Exit status is 0 only if every invariant holds. Intended for preflight and for
the checklist after any data load, which is the moment it matters most.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = 'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod'

# No default key any more (changed 2026-08-07). This used to fall back to the
# demo key embedded in score-demo/index.html, on the reasoning that a public key
# is not a secret and hard-coding it leaks nothing. That reasoning was sound
# about secrecy and wrong about QUOTA: it put a blocking preflight stage on the
# same 2,000/month allowance as a page anyone can load, and on 2026-08-07 the
# allowance ran out and every commit in the repo was blocked by an exhausted
# counter rather than by a defect.
#
# CI now uses its own key on SkyScoreCiTier, supplied via SKY_SCORE_API_KEY out
# of the gitignored .env, which scripts/preflight.sh sources. Missing is a hard
# failure rather than a silent fallback, because falling back to a shared key is
# exactly the failure this replaced.
DEFAULT_KEY = None

# A spread chosen to span the noise gradient, not a convenience sample. Includes
# the airport itself, the approach corridor, inner and outer London.
PROBES = [
    ('TW6 1AP', 'Heathrow Airport'),
    ('TW3 1AA', 'Hounslow, under the approach'),
    ('TW7 5QD', 'Isleworth'),
    ('TW9 1AA', 'Richmond'),
    ('SW11 1AA', 'Battersea'),
    ('SW1A 1AA', 'Westminster'),
    ('WC1E 6BT', 'Bloomsbury'),
    ('E1 8BL', 'Whitechapel'),
    ('SE22 8AA', 'East Dulwich'),
    ('SE5 9RS', 'Denmark Hill'),
    ('N4 1AA', 'Finsbury Park'),
    ('BR1 1AA', 'Bromley'),
    ('HA7 3JA', 'Stanmore'),
    ('UB9 6JH', 'Harefield, Hillingdon near Denham'),
    ('CR0 1LH', 'Croydon'),
    ('E17 4JB', 'Walthamstow'),
]

COMPONENTS = ('quiet', 'afford', 'growth', 'live')


def fetch(base, key, postcode, timeout=30, attempts=4):
    """GET one score, retrying on 429.

    The demo key is metered, and a tight loop over the probe list trips the rate
    limit partway through. Left unhandled that is worse than a slow check: the
    probes that 429 drop out of the sample, and the distribution assertions below
    then pass on whatever happens to be left — a check that gets weaker exactly
    when it is working hardest.
    """
    url = f'{base}/v1/score?postcode={urllib.parse.quote(postcode)}'
    req = urllib.request.Request(url, headers={'X-Api-Key': key})
    delay = 2.0
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode('utf-8')), None
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < attempts - 1:
                time.sleep(delay)
                delay *= 2
                continue
            return None, f'HTTP {exc.code}: {exc.read()[:200].decode("utf-8", "replace")}'
        except Exception as exc:  # noqa: BLE001 - any transport failure is a skip
            return None, str(exc)
    return None, 'rate limited after retries'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default=os.environ.get('SKY_SCORE_API_BASE', DEFAULT_BASE))
    ap.add_argument('--api-key', default=os.environ.get('SKY_SCORE_API_KEY', DEFAULT_KEY))
    args = ap.parse_args()

    if not args.api_key:
        print('SCORE SANITY, live API')
        print('=' * 22)
        print('  FAIL: no API key.')
        print('  Set SKY_SCORE_API_KEY in .env (gitignored), or pass --api-key.')
        print('  preflight sources .env; a bare `python scripts/check_score_sanity.py`')
        print('  does not, so export it or run it through preflight.')
        print('  The key belongs to the SkyScoreCiTier usage plan. Do NOT reuse the')
        print('  demo key from score-demo/index.html: that is what coupled this')
        print('  blocking check to a public quota and blocked commits on 2026-08-07.')
        return 1

    print('SCORE SANITY, live API')
    print('=' * 22)
    print(f'  base: {args.base}\n')

    rows, transport_failures = [], []
    for pc, label in PROBES:
        body, err = fetch(args.base, args.api_key, pc)
        time.sleep(0.4)  # stay under the CI key's 5 rps rate limit
        if err:
            transport_failures.append(f'{pc} ({label}): {err}')
            continue
        rows.append((pc, label, body))

    # A transport failure is not an invariant failure, but silence about it would
    # let the whole check pass while covering two postcodes. Fail if most of the
    # sample is missing, because the distribution assertions become meaningless.
    if transport_failures:
        print('  transport failures:')
        for f in transport_failures:
            print(f'    ! {f}')
        print()
    if len(rows) < len(PROBES) * 0.9:
        print(f'RESULT: FAIL - only {len(rows)}/{len(PROBES)} probes returned; '
              f'distribution checks need a real sample')
        return 1

    failures = []

    def check(name, ok, detail):
        print(f'  {name:<46}{"PASS" if ok else "FAIL"}')
        if not ok:
            failures.append((name, detail))

    # 1. An airport must never score as a quiet place. This is the exact
    #    assertion the raster defect violated, at 7.5/10.
    #
    #    Hoisted out of a `for ... continue` loop on 2026-08-03. In the loop form
    #    this assertion QUIETLY DISAPPEARED whenever its own probe failed: every
    #    other row was skipped by the continue, check() was never reached, and the
    #    gate printed eight PASS lines and RESULT: PASS with no line at all for the
    #    airport. The dropout guard did not save it either — 15 of 16 probes clears
    #    the 90% threshold. TW6 1AP is the first request in the run, so it is the
    #    one most likely to meet a cold Lambda or a rate limit.
    #
    #    That is the single most important assertion in this file: preflight calls
    #    this "the only check here that can catch a DATA defect", and app.py names
    #    it as the gate on lifting the raster quarantine. A check that silently
    #    stops running is worse than no check, because the green is believed.
    airport = next((r for r in rows if r[0] == 'TW6 1AP'), None)
    check('airport probe returned at all', airport is not None,
          'TW6 1AP did not return, so the airport invariant could not be evaluated. '
          'This is a FAILURE, not a skip: the assertion it guards is the reason this '
          'script exists.')
    if airport is not None:
        q = (airport[2].get('components') or {}).get('quiet')
        check('airport postcode is not scored quiet', q is not None and q <= 3.0,
              f'TW6 1AP ({airport[1]}) scored quiet={q}; an airport must be <= 3.0')
    else:
        print(f'  {"airport postcode is not scored quiet":<46}SKIP (probe missing)')

    # 2. Every component must discriminate. Growth once floored 14 boroughs onto
    #    one value, schools published 2 distinct scores citywide, and the raster
    #    put 98% of London on a single quiet value. Same defect, three times.
    for comp in COMPONENTS:
        vals = {(b.get('components') or {}).get(comp) for _, _, b in rows}
        vals.discard(None)
        check(f'{comp} takes >= 4 distinct values', len(vals) >= 4,
              f'{comp} produced only {len(vals)} distinct values across '
              f'{len(rows)} postcodes: {sorted(vals)}')

    # 3. The response must not contradict itself. TW7 5QD once reported
    #    noiseImpactBand 'severe' beside quiet 10.0, in the same payload.
    contradictions = []
    for pc, _, body in rows:
        ctx = body.get('context') or {}
        band, q = ctx.get('noiseImpactBand'), (body.get('components') or {}).get('quiet')
        if q is None or not band:
            continue

        # SKIPPED FOR RASTER-RESOLVED POSTCODES, from 2026-08-06.
        #
        # noiseImpactBand is a BOROUGH-level curated label; quiet may now be a
        # POSTCODE-level measurement. Where DEFRA measured, the two are expected
        # to disagree, and that disagreement is the product's entire claim:
        # Lden varies 10-15 dB inside a borough.
        #
        # This fired on TW7 5QD, Isleworth, band=severe but quiet=6.8. Verified
        # against the GeoTIFF before touching the check: it samples 50.75 dB,
        # its neighbour TW7 5QB 50.87, while TW3 4DX reads 59.29 and Heathrow
        # TW6 1AP 58.23 — all inside Hounslow. An 8.5 dB spread across one
        # borough, every value a genuine reading. The measurement was right and
        # the assertion had gone stale.
        #
        # The guard is NOT weakened where it still applies. Borough- and
        # geometry-resolved postcodes have nothing better than the band to
        # contradict, so they are still checked, and the airport ceiling in
        # section 2 above still holds raster-resolved Heathrow to <= 3.0.
        if (ctx.get('quietResolution') or '') == 'raster':
            continue

        if band == 'severe' and q > 5.0:
            contradictions.append(f'{pc}: band=severe but quiet={q}')
        if band == 'low' and q < 3.0:
            contradictions.append(f'{pc}: band=low but quiet={q}')
    check('noiseImpactBand agrees with quiet', not contradictions,
          '; '.join(contradictions))

    # 4. A defaulted component must never present as a measurement. This is what
    #    liveResolution was added for; assert it actually means something.
    bad = []
    for pc, _, body in rows:
        ctx = body.get('context') or {}
        if ctx.get('liveResolution') == 'measured':
            if 'PARTIAL' in (body.get('sourceBreakdown') or {}).get('live', ''):
                bad.append(f'{pc}: liveResolution=measured but breakdown says PARTIAL')
    check('liveResolution is not contradicted', not bad, '; '.join(bad))

    # 5. Scores must stay on the published scale. A neighbourhood view once
    #    computed -56.4 on a 0-10 scale and shipped it.
    off = [f'{pc}: {k}={v}'
           for pc, _, b in rows
           for k, v in ((b.get('components') or {}).items())
           if not isinstance(v, (int, float)) or not (0.0 <= v <= 10.0)]
    off += [f'{pc}: score={b.get("score")}' for pc, _, b in rows
            if not isinstance(b.get('score'), (int, float)) or not (0.0 <= b['score'] <= 10.0)]
    check('every score is within 0-10', not off, '; '.join(off))

    # 6. Provenance must not credit a body that no longer supplies anything.
    #    The Home Office survived here for a day after crime moved to ONS.
    stale = [f'{pc}: {s}' for pc, _, b in rows
             for s in (b.get('sources') or []) if 'Home Office' in s]
    check('sources credit only current suppliers', not stale, '; '.join(stale))

    print()
    if failures:
        print('RESULT: FAIL')
        for name, detail in failures:
            print(f'  failed: {name}')
            if detail:
                print(f'          {detail}')
        print('\nA data load can break these without any code change. Check the '
              'loader and the table before assuming the Lambda is at fault.')
        return 1

    print(f'RESULT: PASS ({len(rows)} postcodes)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
