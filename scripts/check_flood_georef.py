#!/usr/bin/env python3
"""Assert each city's flood mosaic is georeferenced, against the EA's own service.

WHY THIS EXISTS
---------------
`build_borough_bands.py --check` re-derives every borough's flood percentage by
sampling the same GeoTIFF the figures were written from, so the two things it
compares are the file and itself. It reported agreement for weeks while the
mosaics were mis-georeferenced in 10 of 11 cities: `fetch_ea_flood_risk.py`
clipped edge tiles to the city bbox but requested every tile at 2000x2000 px
regardless, then mosaicked at a uniform 10 m/px, stretching clipped tiles up to
5x and dragging real flood polygons kilometres out of position.

A gate cannot catch that unless it crosses a source boundary. This one asks the
Environment Agency's own GetFeatureInfo what `risk_band` it publishes at a
British National Grid coordinate, and compares that to what our raster says at
the same coordinate. The answer comes from the service, not from our pixels.

WHAT IT TESTS, AND WHY THAT AND NOT THE BAND
--------------------------------------------
It tests the quantity we actually publish and score: MEDIUM-OR-HIGH, the EA's
1%-annual-chance line, which is `floodMediumOrHighPct` and 0.20 of the
`environment` component. Comparing the five-band code instead would red on a
correctly-placed mosaic every time a sample landed on a Low/Very-low boundary,
because a 50 m polygon edge is well inside our 10 m pixel's tolerance. The
binary is what the product claims, so the binary is what gets asserted.

Both directions are checked. Asserting only "where we say flood, the service
agrees" would pass a mosaic that had lost its flood polygons entirely.

SAMPLING IS THE WHOLE DESIGN
----------------------------
Naive uniform sampling makes this another check that cannot fail: 93.3% of
Manchester's mosaic is `none`, so a random point agrees on both sides whatever
the georeferencing. Points are therefore drawn from the ERODED INTERIOR of each
class - a pixel qualifies only if every probe around it at ~ERODE_M metres
shares its class - so a correctly-placed mosaic agrees robustly while a
displaced one lands in the wrong class rather than on a defensible edge.
"""

import argparse
import json
import random
import sys
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA = REPO_ROOT / 'data'
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fetch_ea_flood_risk import LAYER, NO_COVERAGE, WMS, fetch_bytes  # noqa: E402

# Codes 3 (Medium) and 4 (High) are the published Medium-or-High class.
MEDIUM_OR_HIGH = {3, 4}
# 0 none, 1 Very low, 2 Low are the confident NOT-medium-or-high class.
# 255 (Unavailable) is excluded from BOTH: it means the EA publishes no model
# there, so neither answer would be a claim about flood risk.
NOT_MOH = {0, 1, 2}
SERVICE_MOH = {'Medium', 'High'}

ERODE_M = 150      # a sample must sit this far inside a homogeneous region
# 10s, matched to the MEASURED refill of the host's token bucket (see the note
# above service_band). It was 0.8s with two workers - about 2.5 req/s against a
# service that sustains 0.1 - so roughly two thirds of every sample set was
# rejected 403 and thrown away. This is not politeness for its own sake: at
# this rate requests SUCCEED, and the same wall clock returns a full sample
# instead of one scraping MIN_COMPARED.
PAUSE_S = 10.0
MIN_AGREE = 0.80   # per city, per direction
# A class that reached the service only once or twice has not been tested, and
# must not report 'ok'. Throttling shrinks the sample silently - at three
# workers, half of one London class came back unreachable - so the floor is
# stated rather than left to whatever survived.
MIN_COMPARED = 3
# A FALLBACK now, not the normal path. The reasoning below still holds - a gate
# that reds because a free shared service rate-limited us is a gate that gets
# switched off, and then it protects nothing - but with PAUSE_S matched to the
# host's actual refill, samples SUCCEED and top-ups should almost never fire.
#
# Measured 2026-09-03, London at --per-class 4, after an idle period:
#   before (PAUSE_S 0.8, WORKERS 2):  3/3 and 5/5, FOUR samples lost to 403, 2m26
#   after  (PAUSE_S 10,  WORKERS 1):  4/4 and 4/4, ZERO lost,                1m25
# A full sample, no rejected requests, and faster - because the old run spent
# its time failing and recovering rather than asking at a rate it would be
# answered at.
#
# If top-ups start firing again, that is the signal that the host's limit has
# changed - raise PAUSE_S, and do not add workers. The pause is 30s to match the
# measured recovery: after 30s idle, three consecutive calls succeed.
TOPUP_ROUNDS = 2
TOPUP_PAUSE_S = 30.0
# SERIAL, and it must stay serial. The comment here used to read "a
# GetFeatureInfo takes ~8s, so the run is latency-bound, not politeness-bound"
# and concluded that concurrency was free. Measured 2026-09-03, a call that is
# ACCEPTED returns in 0.10s median - the 8s was the retry backoff around
# rejected calls being mistaken for service latency. The run is bound by the
# host's rate limit and nothing else, so a second worker does not halve the
# wall clock; it doubles the request rate against a bucket that is already the
# binding constraint, and every extra request comes back 403.
WORKERS = 1


# Erosion runs on a DECIMATED view, one cell per DECIMATE pixels. The full
# mosaic is up to 6900x7100, and eroding it directly meant sixteen full-array
# np.roll copies - 815 MB resident and minutes per city, which is not a shape a
# preflight stage may have. Decimating by 5 (50 m cells) cuts that ~25x and
# loses nothing: the output is only used to CHOOSE sample points, and a point
# 50 m from the ideal one is still deep inside a homogeneous region.
DECIMATE = 5


def eroded(mask, radius_px):
    """Decimated pixels whose neighbourhood at +/- radius all share the mask.

    Returns (interior, step): a boolean array in DECIMATED space and the factor
    to multiply indices by to get back to mosaic pixels. Shifts are done with
    slicing rather than np.roll so nothing wraps and no full-size temporary is
    built per direction.
    """
    import numpy as np

    small = mask[::DECIMATE, ::DECIMATE]
    r = max(1, radius_px // DECIMATE)
    out = small.copy()
    h, w = small.shape
    if h <= 2 * r or w <= 2 * r:
        return np.zeros_like(small), DECIMATE
    for dy, dx in ((-r, 0), (r, 0), (0, -r), (0, r), (-r, -r), (-r, r), (r, -r), (r, r)):
        ys0, ys1 = max(0, dy), h + min(0, dy)
        xs0, xs1 = max(0, dx), w + min(0, dx)
        shifted = np.zeros_like(small)
        shifted[ys0 - dy : ys1 - dy, xs0 - dx : xs1 - dx] = small[ys0:ys1, xs0:xs1]
        out &= shifted
    # The border cannot be judged, so it is never sampled.
    out[:r, :] = False
    out[-r:, :] = False
    out[:, :r] = False
    out[:, -r:] = False
    return out, DECIMATE


def contains(ring, x, y):
    """Ray-cast point-in-polygon.

    NOT features[0]. A GetFeatureInfo query box spans several 50 m polygons, so
    the first feature returned is arbitrary - the mistake that made High and
    Medium look interchangeable when the colour mapping was first verified.
    """
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][:2]
        x2, y2 = ring[(i + 1) % n][:2]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


# Why a sample was unreachable, tallied across the whole run. The bare
# `except Exception` this replaced returned None for a 403, a timeout, a DNS
# failure and a malformed body alike, so the run could report "2 unreachable"
# eleven times and never say what was wrong.
#
# It hid a real finding for as long as it existed. Measured 2026-09-03: the EA
# host answers **HTTP 403 from Microsoft-Azure-Application-Gateway/v2**, in
# ~0.09s, for the majority of requests at this file's old pacing - 65% blocked
# at PAUSE_S 0.8 with two workers.
#
# It IS a rate limit, but not the shape the retry design assumed, and the
# distinction is the whole finding:
#
#   * It is returned as 403, not 429, so nothing in the stack recognised it.
#   * It is a TOKEN BUCKET, not a per-request delay. Slowing to a 2.5s pause
#     made it WORSE (75% blocked), because a steady 0.4 req/s still outruns the
#     refill. Measured recovery: after 30s idle, three consecutive calls
#     succeed, and again after a further 60s idle.
#   * So the sustainable rate is about ONE REQUEST PER 10 SECONDS, and the only
#     thing that buys throughput is idling - not pausing between bursts.
#
# The consequence for this gate's old numbers: 88 requests at 0.1 req/s is
# ~15 minutes, which is exactly the 15m46s that was observed and attributed to
# waste. The runtime was never the defect. The defect was that most of those
# 15 minutes were spent FAILING and recovering rather than succeeding, so each
# class scraped MIN_COMPARED instead of comparing every point it drew. Pacing
# deliberately costs the same wall time and returns a full sample.
FAILURE_CAUSES = {}


def _note_failure(cause):
    FAILURE_CAUSES[cause] = FAILURE_CAUSES.get(cause, 0) + 1


def service_band(e, n, retries=4):
    """The band the EA publishes at this BNG coordinate, or None if unreachable."""
    url = (
        f'{WMS}?service=WMS&version=1.1.1&request=GetFeatureInfo&layers={LAYER}'
        f'&query_layers={LAYER}&srs=EPSG:27700'
        f'&bbox={e - 100},{n - 100},{e + 100},{n + 100}'
        f'&width=101&height=101&x=50&y=50&info_format=application/json&feature_count=25'
    )
    cause = 'unknown'
    for attempt in range(retries):
        try:
            doc = json.loads(fetch_bytes(url, 120))
            break
        except urllib.error.HTTPError as ex:
            cause = f'HTTP {ex.code}'
            # A 403 from the WAF is not a rate limit and does not clear inside
            # this loop's backoff - measured. Retrying it four times buys
            # nothing and costs 30s per sample; give up on this point and let
            # the caller draw a different one.
            if ex.code == 403:
                _note_failure(cause)
                return None
            time.sleep(3.0 * (attempt + 1))
        except urllib.error.URLError as ex:
            cause = f'URLError {type(ex.reason).__name__}'
            time.sleep(3.0 * (attempt + 1))
        except ValueError as ex:
            # json.loads on a body that is not JSON - an HTML error page slipped
            # through with a 200, which is how a WAF sometimes answers.
            cause = f'bad body ({type(ex).__name__})'
            time.sleep(3.0 * (attempt + 1))
        except Exception as ex:  # noqa: BLE001 - classify, never swallow
            cause = type(ex).__name__
            time.sleep(3.0 * (attempt + 1))
    else:
        _note_failure(cause)
        return None
    for feature in doc.get('features', []):
        geom = feature.get('geometry') or {}
        polys = (
            geom.get('coordinates', [])
            if geom.get('type') == 'MultiPolygon'
            else [geom.get('coordinates', [])]
        )
        for poly in polys:
            if poly and contains(poly[0], e, n):
                return feature['properties'].get('risk_band')
    return 'none'


GRID = 4  # mosaic is divided GRID x GRID; cities are 4-16 tiles


def spread_samples(ys, xs, shape, n, rng):
    """Pick n sample pixels spread across the mosaic, PERIPHERY FIRST.

    THIS IS THE PART THAT MAKES THE GATE ABLE TO FAIL, and the first version
    did not have it. Uniform random sampling passed the known-bad London
    mosaic 9/9, because the defect is confined to CLIPPED EDGE TILES: measured
    against the pre-fix file, the six interior tile blocks were byte-identical
    and only the top row and right column had moved. Half the mosaic was
    correct, so half the samples proved nothing and the rest never fired.

    So samples are drawn one per grid cell, cells ordered by distance from the
    centre outward. A tiling error accumulates at the edges by construction -
    that is where the clipped tiles are - so the periphery is where a sample
    buys the most information. Spreading also catches a localised displacement
    anywhere, without this gate needing to know the tile geometry.
    """
    h, w = shape
    ch, cw = h / GRID, w / GRID
    cells = {}
    for i, (y, x) in enumerate(zip(ys, xs, strict=True)):
        key = (min(int(y // ch), GRID - 1), min(int(x // cw), GRID - 1))
        cells.setdefault(key, []).append(i)

    mid = (GRID - 1) / 2
    order = sorted(cells, key=lambda c: (-max(abs(c[0] - mid), abs(c[1] - mid)), c))

    picks = []
    while len(picks) < n and order:
        for key in order:
            if len(picks) >= n:
                break
            bucket = cells[key]
            picks.append(bucket[rng.randrange(len(bucket))])
        if len(picks) < n and all(len(cells[k]) for k in order):
            continue  # cycle the cells again
        break
    return picks


def check_city(city, mosaic_dir, per_class, seed):
    import numpy as np
    import rasterio

    tif = mosaic_dir / f'ea_flood_risk_{city}.tif'
    if not tif.exists():
        print(f'{city:<16} NO MOSAIC - NOT VERIFIED (fetch it, or this city is unchecked)')
        return None

    with rasterio.open(tif) as src:
        arr = src.read(1)
        transform = src.transform

    radius_px = max(1, int(ERODE_M / abs(transform.a)))
    # Seeded on purpose: the same points every run, so a change in the result
    # is a change in the data and never in the sample. noqa - not cryptographic.
    rng = random.Random(seed)  # noqa: S311
    results = {}

    for label, codes, want_moh in (
        ('medium-or-high', MEDIUM_OR_HIGH, True),
        ('not-moh', NOT_MOH, False),
    ):
        mask = np.isin(arr, list(codes))
        interior, step = eroded(mask, radius_px)
        ys, xs = np.nonzero(interior)
        ys, xs = ys * step, xs * step  # back to mosaic pixel coordinates
        if len(ys) == 0:
            print(f'{city:<16} {label:<15} NO ERODED INTERIOR - cannot sample')
            results[label] = None
            continue

        picks = spread_samples(ys, xs, arr.shape, min(per_class, len(ys)), rng)
        cells_used = len({(int(ys[i] // (arr.shape[0] / GRID)), int(xs[i] // (arr.shape[1] / GRID))) for i in picks})

        # ys/xs/want_moh are bound as defaults, not captured: the closure is
        # redefined each pass of the enclosing loop, and a late-binding capture
        # would have every thread read the LAST class's arrays.
        def probe(i, ys=ys, xs=xs, pause=PAUSE_S):
            row, col = int(ys[i]), int(xs[i])
            # Pixel centre in the raster's own CRS.
            e, n = transform * (col + 0.5, row + 0.5)
            time.sleep(pause)
            return service_band(int(e), int(n))

        tally = {'agree': 0, 'disagree': 0, 'unreachable': 0}

        def run(batch, workers, want=want_moh, t=tally, pr=probe):
            if workers > 1:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    got = list(pool.map(pr, batch))
            else:
                got = [pr(i) for i in batch]
            for g in got:
                if g is None:
                    t['unreachable'] += 1
                elif (g in SERVICE_MOH) == want:
                    t['agree'] += 1
                else:
                    t['disagree'] += 1

        run(picks, WORKERS)

        used = set(picks)
        for _ in range(TOPUP_ROUNDS):
            if tally['agree'] + tally['disagree'] >= MIN_COMPARED:
                break
            spare = [i for i in range(len(ys)) if i not in used]
            if not spare:
                break
            extra = rng.sample(spare, min(per_class, len(spare)))
            used.update(extra)
            time.sleep(TOPUP_PAUSE_S)
            run(extra, 1)  # serial: we are being throttled, so stop rushing

        agree, disagree, unreachable = tally['agree'], tally['disagree'], tally['unreachable']
        compared = agree + disagree
        rate = agree / compared if compared else 0.0
        results[label] = (agree, compared, unreachable, rate)
        if compared < MIN_COMPARED:
            flag = 'INCONCLUSIVE'
        elif rate >= MIN_AGREE:
            flag = 'ok'
        else:
            flag = 'FAIL'
        print(
            f'{city:<16} {label:<15} {agree}/{compared} agree '
            f'({rate:5.0%}) {unreachable} unreachable  {cells_used} cells  {flag}'
        )
    return results


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument('--city')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--per-class', type=int, default=6, help='samples per class per city')
    ap.add_argument('--seed', type=int, default=11)
    ap.add_argument(
        '--mosaic-dir',
        default=str(DATA),
        help='where the ea_flood_risk_*.tif live. Point it at a backup to prove this gate red.',
    )
    args = ap.parse_args()

    mosaic_dir = Path(args.mosaic_dir)
    if args.all:
        cities = sorted(p.name.replace('-boroughs.json', '') for p in DATA.glob('*-boroughs.json'))
        cities = [c for c in cities if c not in NO_COVERAGE]
    elif args.city:
        cities = [args.city]
    else:
        ap.error('pass --city <key> or --all')

    print(f'mosaics: {mosaic_dir}')
    print(f'{"city":<16} {"class":<15} agreement')
    checked, failed = 0, []
    for city in cities:
        res = check_city(city, mosaic_dir, args.per_class, args.seed)
        if res is None:
            # A MISSING MOSAIC IS A FAILURE, NOT A SKIP (2026-08-31).
            #
            # This was `continue`, and the only floor below is the GLOBAL
            # `if not checked` - so with ten of the eleven mosaics absent this
            # printed "verified against the EA service for 1 cities" and exited
            # 0. Proven by pointing --mosaic-dir at a directory holding London
            # alone. `data/*.tif` is gitignored and restored only by its own
            # fetch script, so "the raster was never fetched for that city" is
            # not hypothetical - it is exactly the Leicester/Teesside incident
            # CLAUDE.md records, here applied to the gate itself.
            #
            # The city list comes from the CHECKED-IN boundary files, so the
            # expected set is stable and this cannot fail for a city that does
            # not exist.
            failed.append(f'{city} NO MOSAIC - not verified')
            continue
        city_compared = 0
        for label, r in res.items():
            if r is None:
                # A CLASS WITH NO INTERIOR IS UNTESTED, NOT AGREED.
                #
                # Also `continue` until 2026-08-31, and this is the sharper of
                # the two: erase every medium-or-high pixel from a mosaic and
                # that class has no eroded interior, so it was dropped and the
                # city passed on the not-MoH direction ALONE. Proven - zeroing
                # London's 1,215,784 MoH pixels (3.72% of the city) printed
                # "medium-or-high NO ERODED INTERIOR" and exited 0, on a mosaic
                # that would drive floodMediumOrHighPct to 0.0 for all 33
                # boroughs of a SCORED input.
                #
                # The docstring at the top of this file promises both directions
                # are checked precisely because asserting only "where we say
                # flood, the service agrees" passes a mosaic that has lost its
                # polygons entirely. That promise was not kept by the code.
                failed.append(f'{city}/{label} NO INTERIOR - cannot be tested')
                continue
            _agree, compared, _unreach, rate = r
            city_compared += compared
            if compared < MIN_COMPARED:
                failed.append(f'{city}/{label} INCONCLUSIVE ({compared} reached)')
            elif rate < MIN_AGREE:
                failed.append(f'{city}/{label} {rate:.0%}')
        # PER-CITY FLOOR. A city that compared nothing is not a city that
        # agreed. This repo has shipped that exact pass five times.
        if city_compared == 0:
            failed.append(f'{city} COMPARED NOTHING')
        else:
            checked += 1

    print()
    # Say WHY samples were lost. Without this the run reports "2 unreachable"
    # eleven times over and the cause is unknowable - which is how a 403 rate
    # limit was diagnosed as service latency and answered with a 20s sleep.
    if FAILURE_CAUSES:
        total = sum(FAILURE_CAUSES.values())
        causes = ', '.join(f'{v}x {k}' for k, v in
                           sorted(FAILURE_CAUSES.items(), key=lambda kv: -kv[1]))
        print(f'{total} sample(s) unreachable: {causes}')
        if any(k == 'HTTP 403' for k in FAILURE_CAUSES):
            print('  HTTP 403 here is the host\'s RATE LIMIT, not a block on us:')
            print('  a token bucket that refills at about one request per 10s.')
            print('  If this is a large share, raise PAUSE_S - do not add workers.')
        print()
    if not checked:
        print('FAIL: no city was compared. A gate that compares nothing cannot go red.')
        print(f'  expected {len(cities)} cities: {", ".join(cities)}')
        print('  if the mosaics are simply absent, fetch them:')
        print('    python scripts/fetch_ea_flood_risk.py --all')
        return 1
    if failed:
        untested = [f for f in failed if 'NO MOSAIC' in f or 'NO INTERIOR' in f or 'INCONCLUSIVE' in f]
        disagreed = [f for f in failed if f not in untested]
        print(f'FAIL: {len(failed)} check(s) - {len(disagreed)} disagree, {len(untested)} untested')
        for f in failed:
            print(f'  - {f}')
        if disagreed:
            print('The mosaic disagrees with the Environment Agency about where flood risk is.')
        if untested:
            print('An untested class is not an agreeing one: these were never compared.')
        return 1
    print(f'flood georeferencing verified against the EA service for {checked} cities')
    return 0


if __name__ == '__main__':
    sys.exit(main())
