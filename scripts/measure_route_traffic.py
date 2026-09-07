#!/usr/bin/env python3
"""Measure real per-route request volume, so throttle limits can be derived.

WHY THIS EXISTS. `backend/template.yaml` sets a per-route throttle on every
unauthenticated route, and until 2026-09-07 five of them had none. The blocker
recorded against that work was that "the numbers must come from measured
traffic and flightmap-dev is denied the observability permissions" - true when
written, and no longer true since the deploy policy was restored on 2026-09-04.
This is the tool that turns the permission into a number, so the throttles in
that file are re-derivable rather than a comment nobody can check.

WHAT IT CAN AND CANNOT SEE. `/nhs`, `/sold-prices` and `/transport` each have
their OWN Lambda, so `Invocations` IS that route's request count. `/epc` is
measured beside them as a CALIBRATION ANCHOR: index.html fetches it on the same
postcode lookup, so its traffic is an upper bound on theirs, and it has run at
3 RPS / 6 burst since 2026-07-24 without a reported 429.

ScoreFunction serves SIX routes (/v1/score, /v1/score/batch, /v1/regions,
/badge, /v1/environment, /v1/changes). The template enables no per-resource API
Gateway metrics and no handler logs a path, so its total is a six-route ceiling
and nothing finer. It is printed as such. Do not divide it.

TWO CLOUDWATCH TRAPS, both hit while writing this, both silent:

  * RETENTION IS PER RESOLUTION. 60s data lives 15 days, 300s data 63 days,
    3600s data 455 days. A 60s query over 30 days returns the last 15 days
    only - and the first version of this script asked for a 60s peak inside a
    22-day-old hour, got an EMPTY list, and rendered `max(..., default=0)` as
    `0.000 RPS`. An empty index is not a zero reading; every cell here prints
    `n/a` when nothing came back, and the finest resolution is only ever asked
    for inside its own retention window.

  * 1,440 DATAPOINTS PER CALL, hard. 30 days at 300s asks for 8,640 and the
    API refuses the WHOLE request - so an unchunked reader does not return a
    short series, it returns nothing at all. `series()` chunks.

Needs `cloudwatch:GetMetricStatistics`, which `scripts/check_aws_permissions.py`
probes. Read-only; it makes no change to anything.
"""

import argparse
import datetime as dt
import sys

import boto3

REGION = 'eu-west-2'

# Physical names carry a CloudFormation suffix that CHANGES whenever the
# function is replaced, so they are resolved by prefix at run time rather than
# hardcoded - the same trap that produced a false "no log access" claim in
# OPERATIONS.md for five weeks.
ROUTES = [
    ('/nhs', 'NhsFunction'),
    ('/sold-prices', 'SoldPricesFunction'),
    ('/transport', 'TransportFunction'),
    ('/epc [anchor: 3 RPS since 24 Jul]', 'EpcFunction'),
    ('Score fn [6 routes: ceiling only]', 'ScoreFunction'),
]

STACK_PREFIX = 'london-flight-map-'
RETENTION_DAYS = {60: 15, 300: 63, 3600: 455}
MAX_DATAPOINTS = 1440


def resolve(lam, logical):
    """Physical function name for a logical id, by prefix."""
    paginator = lam.get_paginator('list_functions')
    want = f'{STACK_PREFIX}{logical}-'
    for page in paginator.paginate():
        for fn in page['Functions']:
            if fn['FunctionName'].startswith(want):
                return fn['FunctionName']
    return None


def series(cw, fn, start, end, period):
    """Sum-per-`period` datapoints, chunked under the 1,440 cap."""
    out = []
    span = dt.timedelta(seconds=period * MAX_DATAPOINTS)
    cur = start
    while cur < end:
        stop = min(cur + span, end)
        out.extend(
            cw.get_metric_statistics(
                Namespace='AWS/Lambda',
                MetricName='Invocations',
                Dimensions=[{'Name': 'FunctionName', 'Value': fn}],
                StartTime=cur,
                EndTime=stop,
                Period=period,
                Statistics=['Sum'],
            )['Datapoints']
        )
        cur = stop
    return sorted(out, key=lambda d: d['Timestamp'])


def peak(cw, fn, now, days, period):
    """Peak Sum per `period`, or None if the window returned NOTHING.

    None means UNMEASURED and must never render as 0. See the module docstring.
    """
    days = min(days, RETENTION_DAYS[period])
    pts = series(cw, fn, now - dt.timedelta(days=days), now, period)
    if not pts:
        return None, days, 0
    return int(max(d['Sum'] for d in pts)), days, len(pts)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--days', type=int, default=30, help='window (default 30)')
    ap.add_argument('--profile', default='flightmap')
    args = ap.parse_args()

    sess = boto3.Session(profile_name=args.profile, region_name=REGION)
    cw, lam = sess.client('cloudwatch'), sess.client('lambda')
    now = dt.datetime.now(dt.UTC).replace(microsecond=0)

    print(f'Per-route request volume, {args.days} days to {now.date()} (UTC)')
    print('=' * 68)
    hdr = (
        f'  {"route":36} {"total":>7} {"pk/hr":>6} '
        f'{"pk/5m":>6} {"pk/min":>7} {"pk RPS":>7}'
    )
    print(hdr)
    print('  ' + '-' * (len(hdr) - 2))

    resolved = 0
    notes = []
    for label, logical in ROUTES:
        fn = resolve(lam, logical)
        if fn is None:
            print(f'  {label:36} {"NOT FOUND":>7}')
            notes.append(f'{label}: no function matching {STACK_PREFIX}{logical}-')
            continue
        resolved += 1
        hourly = series(cw, fn, now - dt.timedelta(days=args.days), now, 3600)
        total = int(sum(d['Sum'] for d in hourly)) if hourly else None
        p_hr, _, _ = peak(cw, fn, now, args.days, 3600)
        p_5m, d5, n5 = peak(cw, fn, now, args.days, 300)
        p_1m, d1, n1 = peak(cw, fn, now, args.days, 60)

        def cell(v, w):
            return f'{"n/a":>{w}}' if v is None else f'{v:>{w}}'

        rps = f'{"n/a":>7}' if p_1m is None else f'{p_1m / 60.0:>7.3f}'
        print(
            f'  {label:36} {cell(total, 7)} {cell(p_hr, 6)} '
            f'{cell(p_5m, 6)} {cell(p_1m, 7)} {rps}'
        )
        notes.append(
            f'{label}: 5-min peak over {d5}d ({n5} datapoints), '
            f'1-min peak over {d1}d ({n1} datapoints)'
        )

    print()
    for n in notes:
        print(f'  {n}')

    print()
    print('  pk RPS is peak-minute/60 and is a FLOOR: a burst inside one minute')
    print('  is invisible at CloudWatch standard resolution. Burst limits must')
    print('  carry headroom over it.')

    if resolved == 0:
        print()
        print('FAIL: resolved 0 functions, so nothing was measured.')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
