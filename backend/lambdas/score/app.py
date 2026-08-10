"""
Sky Score B2B API.

Endpoints:
  GET /v1/score, single-postcode/borough score
  POST /v1/score/batch, bulk lookup (up to 100 queries per call)
  OPTIONS for both, browser CORS preflight (open to any origin
                            since the GET/POST are API-key gated anyway)

Methodology: see METHODOLOGY.md at the project root. The scoring values and
formulas in this file are anchored to that document; any change to weights,
thresholds, or component formulas should bump METHODOLOGY_VERSION and be
documented in the methodology changelog.
"""

import json
import logging
import math
import os
import re
import threading
from collections import OrderedDict
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _make_lru(maxsize):
    """OrderedDict-backed LRU cache that does NOT cache None results.

    `functools.lru_cache` caches every return value including None, which
    means a transient outage of an upstream (postcodes.io, DDB) poisons
    the cache for the lifetime of the warm container (~15 min on AWS
    Lambda). This implementation only stores truthy values, so the next
    request after an outage retries upstream instead of serving None.

    Both accessors hold one lock (audit L6). `get` previously tested
    membership and then called move_to_end as separate bytecode sequences,
    so a concurrent `put` that evicted the LRU tail in between raised
    KeyError on the very key `get` had just found. /v1/score/batch runs
    BATCH_PARALLELISM threads over these shared caches, and the NSPL
    feature makes a sustained 100k-postcode backfill the expected
    workload — which keeps the cache permanently full and evicting on
    nearly every miss, i.e. holds that window open. The escaping KeyError
    turned 100 resolvable queries into one 500. The lock is held only for
    a few OrderedDict operations, so contention is negligible next to the
    DynamoDB and postcodes.io calls it guards.
    """
    cache = OrderedDict()
    lock = threading.Lock()

    def get(key):
        with lock:
            if key not in cache:
                return None
            cache.move_to_end(key)
            return cache[key]

    def put(key, value):
        if value is None:
            return  # Never cache misses / errors
        with lock:
            if key in cache:
                cache.move_to_end(key)
            cache[key] = value
            while len(cache) > maxsize:
                cache.popitem(last=False)

    return get, put


CORS_ORIGIN = os.environ.get('CORS_ORIGIN', '*')
METHODOLOGY_URL = 'https://github.com/billkhiz-bit/london-flight-path-map/blob/master/METHODOLOGY.md'
# v3.5 (2026-08-02): two liveability inputs changed source, and schools changed
# scale. Not a patch — a caller pinning a methodology version needs to know the
# schools sub-score is no longer drawn from a four-value vocabulary.
#
#   crime    Three boroughs had been compressed to fit crime_to_score's 50-200
#            band (Westminster carried 175 against an actual 355.5). Corrected
#            against ONS Crime in England and Wales, Police Force Area data
#            tables, YE March 2026, Table C4.
#
#            CORRECTED 2026-08-03: this comment used to end "The other 29
#            already agreed with that release within 10 per 1,000, so this is a
#            tail correction and NOT a vintage roll." That was generalised from
#            three spot checks and was wrong. Every London row of the workbook
#            was then compared: 29 of 33 disagreed with the cited release, seven
#            by more than 10 per 1,000 (Barking and Dagenham 105 vs 84.2,
#            Hillingdon 72 vs 91.6, Croydon 98 vs 80.4), and 17 boroughs carried
#            a crime sub-score wrong by more than 0.3. All 33 now hold published
#            figures. Never spot-check this again — run
#            scripts/refresh_crime_from_ons.py --check, which reads every row.
#
#   schools  Was an editorial band with no derivable rule: 'excellent' spanned
#            90.9-100% of schools Good-or-Outstanding and 'good' spanned
#            83.3-100%, so Westminster at 100% was 'good' and Richmond at 100%
#            was 'excellent'. Now DfE Key Stage 4 Progress 8 (2022/23), scored
#            continuously by school_score() on absolute anchors. London goes
#            from 2 distinct schools sub-scores to 25.
METHODOLOGY_VERSION = '3.5'
API_VERSION = '1.0'
MAX_BATCH_SIZE = 100
# Parallel workers for /v1/score/batch. Each query is mostly waiting on
# postcodes.io (network-bound), so ~10 workers gives near-linear speedup
# on the typical 30-50 postcode batch without saturating any upstream.
BATCH_PARALLELISM = int(os.environ.get('BATCH_PARALLELISM', '10'))

SCHOOL_SCORE = {'outstanding': 10, 'excellent': 9, 'good': 6, 'mixed': 3}
TRANSPORT_SCORE = {'excellent': 10, 'good': 7, 'moderate': 4, 'poor': 2}
HEALTH_SCORE = {'excellent': 10, 'good': 7, 'moderate': 4}
IMPACT_TO_QUIET = {
    'low': 10.0,
    'low-moderate': 7.5,
    'moderate': 5.0,
    'moderate-high': 3.0,
    'high': 1.5,
    'severe': 0.0,
}

# Methodology v3.3 (2026-07-30): growth is now weighted ONLY for the investor
# persona. Every other persona carries 0.00.
#
# The evidence: in the 2026-Q1 → Q2 refresh, growth accounted for **87% of all
# score movement** across the 33 boroughs. Excluding it, the largest change
# anywhere in London was 0.62 points. Nothing physical about those places had
# changed — same flight paths, same schools, same crime — yet headline scores
# moved by up to 1.6 because of one volatile market series.
#
# The other three factors describe durable attributes of a place. Price growth
# is a mean-reverting time-series about the market, it is revised, and past
# growth is a weak predictor of future growth. Averaging it in implied a
# commensurability that does not hold, and let market noise churn a score users
# read as a property's quality.
#
# It is retained at full weight for `investor`, where expected return is the
# actual question being asked. `renter` already carried 0.00 on the same
# reasoning (no selling event), which this generalises.
#
# Each persona's former growth weight was redistributed across its remaining
# three factors *in proportion*, so relative emphasis is unchanged.
PERSONAS = {
    'balanced': {'quiet': 0.38, 'afford': 0.31, 'growth': 0.00, 'live': 0.31},
    'family': {'quiet': 0.22, 'afford': 0.22, 'growth': 0.00, 'live': 0.56},
    # Investor: expected return IS the question, so growth keeps full weight.
    'investor': {'quiet': 0.10, 'afford': 0.30, 'growth': 0.40, 'live': 0.20},
    'firsttime': {'quiet': 0.19, 'afford': 0.50, 'growth': 0.00, 'live': 0.31},
    'quietlife': {'quiet': 0.56, 'afford': 0.22, 'growth': 0.00, 'live': 0.22},
    # Renter: no selling event so growth is irrelevant.
    'renter': {'quiet': 0.30, 'afford': 0.35, 'growth': 0.00, 'live': 0.35},
    # Commuter / young professional: transport-led, price-sensitive.
    'commuter': {'quiet': 0.24, 'afford': 0.35, 'growth': 0.00, 'live': 0.41},
    # Later-life buyer: cash buyer prioritising quiet + healthcare access.
    'laterlife': {'quiet': 0.44, 'afford': 0.17, 'growth': 0.00, 'live': 0.39},
}

# ---------------------------------------------------------------------------
# Vintage tracking (trends feature, 2026-07-24). Each quarterly refresh
# keeps the superseded price/trend values here so the API can answer
# "what changed?" (?compare=previous on /v1/score, and GET /v1/changes).
# Only price + trend move between quarterly vintages; schools / crime /
# transport / healthcare refresh annually and noise five-yearly, so the
# previous dataset is the current one overlaid with these two fields.
# ---------------------------------------------------------------------------
SNAPSHOT_VINTAGE = '2026-Q2'  # May 2026 UK HPI, applied 2026-07-24
PREVIOUS_VINTAGE = '2026-Q1'
SNAPSHOT_REFRESHED_AT = '2026-07-24'
# One-off caveat for this quarter's comparison: v3.2 also clamped the
# growth formula, so previous scores are recomputed under the CURRENT
# formula to isolate data movement from formula change.
# Interpolates METHODOLOGY_VERSION rather than hardcoding it. This string is
# rendered publicly on /changes, and the literal '(v3.2)' survived v3.3, v3.4 and
# v3.5 — so one public page displayed three different methodology versions at
# once. A version string that has to be remembered will eventually be forgotten.
COMPARISON_NOTE = (
    f'previousScore is recomputed under the current methodology (v{METHODOLOGY_VERSION}), '
    'so scoreChange isolates data movement between vintages, not formula changes.'
)

LONDON_PREVIOUS_PT = {
    'Barking and Dagenham': {'avgPrice': 340000, 'trend': 5.8},
    'Barnet': {'avgPrice': 560000, 'trend': 3.1},
    'Bexley': {'avgPrice': 380000, 'trend': 4.5},
    'Brent': {'avgPrice': 490000, 'trend': 4.0},
    'Bromley': {'avgPrice': 480000, 'trend': 3.8},
    'Camden': {'avgPrice': 780000, 'trend': 1.2},
    'City of London': {'avgPrice': 850000, 'trend': 1.0},
    'Croydon': {'avgPrice': 395000, 'trend': 4.5},
    'Ealing': {'avgPrice': 540000, 'trend': 4.1},
    'Enfield': {'avgPrice': 430000, 'trend': 4.3},
    'Greenwich': {'avgPrice': 430000, 'trend': 5.2},
    'Hackney': {'avgPrice': 590000, 'trend': 3.0},
    'Hammersmith and Fulham': {'avgPrice': 750000, 'trend': 1.0},
    'Haringey': {'avgPrice': 545000, 'trend': 3.5},
    'Harrow': {'avgPrice': 490000, 'trend': 3.2},
    'Havering': {'avgPrice': 400000, 'trend': 4.0},
    'Hillingdon': {'avgPrice': 480000, 'trend': 2.8},
    'Hounslow': {'avgPrice': 465000, 'trend': 3.2},
    'Islington': {'avgPrice': 720000, 'trend': 1.8},
    'Kensington and Chelsea': {'avgPrice': 1350000, 'trend': 0.5},
    'Kingston upon Thames': {'avgPrice': 550000, 'trend': 2.0},
    'Lambeth': {'avgPrice': 560000, 'trend': 3.5},
    'Lewisham': {'avgPrice': 445000, 'trend': 4.8},
    'Merton': {'avgPrice': 560000, 'trend': 2.8},
    'Newham': {'avgPrice': 410000, 'trend': 5.8},
    'Redbridge': {'avgPrice': 445000, 'trend': 3.9},
    'Richmond upon Thames': {'avgPrice': 825000, 'trend': 1.5},
    'Southwark': {'avgPrice': 530000, 'trend': 2.5},
    'Sutton': {'avgPrice': 415000, 'trend': 3.5},
    'Tower Hamlets': {'avgPrice': 495000, 'trend': 2.0},
    'Waltham Forest': {'avgPrice': 480000, 'trend': 4.2},
    'Wandsworth': {'avgPrice': 680000, 'trend': 2.1},
    'Westminster': {'avgPrice': 980000, 'trend': 0.8},
}


def previous_dataset(city):
    """The borough dataset as of PREVIOUS_VINTAGE, or None if the city had no
    presence in the dataset at that vintage.

    Three genuinely different cases, which this used to collapse into two:

      london      refreshed between vintages — current data overlaid with the
                  superseded price/trend pairs.
      nyc         existed at PREVIOUS_VINTAGE but had no quarterly refresh, so
                  its previous dataset legitimately equals the current one and
                  a comparison honestly reports zero change.
      manchester  did not exist at PREVIOUS_VINTAGE at all. Returning the current
                  set made ?compare=previous fabricate a *measured* zero change
                  for a city with no history — byte-identical to NYC's honest
                  zero, with nothing in the response letting a caller tell an
                  unchanged market from a city that was not being tracked yet.

    Returning None for the third case makes callers decline to compare instead of
    inventing a baseline.
    """
    cfg = CITIES[city]
    if not cfg.get('hasHistory', False):
        return None
    current = cfg['boroughs']
    if city != 'london':
        return current
    merged = {}
    for name, bd in current.items():
        prev = LONDON_PREVIOUS_PT.get(name)
        merged[name] = {**bd, **prev} if prev else dict(bd)
    return merged


def build_comparison(current, previous, city, name=None):
    """Assemble the ?compare=previous response block from two calc_score
    results computed under identical formula + weights.

    `name` is the resolved borough. Passing it is what lets the explanation say
    "Barking and Dagenham went from 1st to 17th" rather than "this area", and
    what enables the growth rank at all.
    """
    currency = 'avgPriceUsd' if CITIES[city]['currency'] == 'USD' else 'avgPriceGbp'
    cur_price = current['context'].get(currency)
    prev_price = previous['context'].get(currency)
    price_change = (
        round((cur_price - prev_price) / prev_price * 100, 1)
        if cur_price is not None and prev_price not in (None, 0)
        else None
    )
    # Computed once and shared: previously each of describe_change and build_why
    # rebuilt both benchmark sets, so a single request walked every borough four
    # times to produce the same two answers.
    prev_set = previous_dataset(city)
    cur_bm = benchmarks(CITIES[city]['boroughs'])
    prev_bm = benchmarks(prev_set)
    cur_ranks = growth_ranks(CITIES[city]['boroughs'])
    prev_ranks = growth_ranks(prev_set)
    why = build_why(
        current, previous, city, PERSONAS['balanced'], name, cur_bm, prev_bm, cur_ranks, prev_ranks
    )
    return {
        'currentVintage': SNAPSHOT_VINTAGE,
        'previousVintage': PREVIOUS_VINTAGE,
        'previousScore': previous['score'],
        'scoreChange': round(current['score'] - previous['score'], 1),
        'previousComponents': previous['components'],
        f'previous{currency[0].upper()}{currency[1:]}': prev_price,
        'priceChangePct': price_change,
        'previousTrendPct': previous['context'].get('priceTrendPct'),
        'note': COMPARISON_NOTE,
        'attribution': build_attribution(current, previous, PERSONAS['balanced']),
        'explanation': why['summary'],
        'why': why,
    }


COMPONENT_LABELS = {
    'quiet': 'Quiet Skies',
    'afford': 'Affordability',
    'growth': 'Growth',
    'live': 'Liveability',
}


def build_attribution(current, previous, weights):
    """Decompose a score change into per-factor contributions.

    The score is a weighted sum, so `delta_score == sum(w_i * delta_component_i)`
    exactly. That identity is what makes this an explanation rather than a
    narrative: the parts must add up to the whole, and a caller can check it.

    Contributions are derived from the same 1dp component values the API
    publishes, so the arithmetic a client can see reproduces these numbers
    exactly. The cost is that they reconcile against the published score only
    to within rounding, which `roundingResidual` reports rather than hides.
    """
    cur_c = current['components']
    prev_c = previous['components']
    factors = []
    for key, weight in weights.items():
        before = prev_c.get(key)
        after = cur_c.get(key)
        if before is None or after is None:
            continue
        # A zero-weight factor cannot drive anything, so listing it as a driver
        # contributing +0.00 is noise. It is reported separately as an
        # unweighted movement (see build_why) — since v3.3 put growth at 0.00
        # for every persona but investor, staying silent would leave "the market
        # moved but my score didn't" unexplained.
        if weight == 0:
            continue
        change = round(after - before, 1)
        contribution = round((after - before) * weight, 2)
        if change == 0 and contribution == 0:
            continue
        factors.append(
            {
                'factor': key,
                'label': COMPONENT_LABELS.get(key, key),
                'before': before,
                'after': after,
                'change': change,
                'weight': weight,
                'contribution': contribution,
            }
        )
    # Biggest mover first: the first entry is the answer to "why did it move?".
    factors.sort(key=lambda f: abs(f['contribution']), reverse=True)
    return factors


def _price_of(result, city):
    field = 'avgPriceUsd' if CITIES[city]['currency'] == 'USD' else 'avgPriceGbp'
    return result['context'].get(field)


def _money(value, city):
    """Compact currency for prose: 569000 -> '£569k'."""
    symbol = '$' if CITIES[city]['currency'] == 'USD' else '£'
    if value is None:
        return 'n/a'
    return f'{symbol}{round(value / 1000):,}k'


# One plain sentence per factor. The explanation used to name factors without
# ever saying what they measure, which assumes the reader already knows.
FACTOR_MEANINGS = {
    'quiet': 'How free this area is from aircraft noise.',
    'afford': 'How cheap this area is, ranked against every other London borough.',
    'growth': 'How fast property prices are rising here, ranked against every other London borough.',
    'live': 'Schools, crime and transport, combined.',
}


def _ordinal(n):
    """1 -> '1st'. Ranks read far more naturally than 'scored relative to'."""
    if n is None:
        return ''
    if 10 <= n % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f'{n}{suffix}'


def _fraction_words(share):
    """Describe a ratio the way a person would: 0.18 -> 'a fifth'.

    The point of the sentence this feeds is intuition, so 'about a fifth of
    that' lands where '0.18 of the maximum' does not.
    """
    if share is None or share <= 0:
        return 'none'
    if share >= 0.95:
        return 'effectively all'
    named = [
        (0.9, 'nine tenths'),
        (0.8, 'four fifths'),
        (0.75, 'three quarters'),
        (0.66, 'two thirds'),
        (0.6, 'three fifths'),
        (0.5, 'half'),
        (0.4, 'two fifths'),
        (0.33, 'a third'),
        (0.25, 'a quarter'),
        (0.2, 'a fifth'),
        (0.16, 'a sixth'),
        (0.125, 'an eighth'),
        (0.1, 'a tenth'),
    ]
    # Pick the closest named fraction rather than the nearest below, so 0.18
    # reads as "a fifth" instead of "a sixth".
    best = min(named, key=lambda pair: abs(share - pair[0]))
    return best[1]


def growth_ranks(boroughs):
    """Rank every area by price trend, 1 = fastest rising. Ties share a rank."""
    trends = {name: bd['trend'] for name, bd in boroughs.items()}
    ordered = sorted(trends.values(), reverse=True)
    return {name: ordered.index(t) + 1 for name, t in trends.items()}


def benchmarks(boroughs):
    """The yardsticks the relative components are measured against.

    Two of the four factors are *relative*, not absolute: growth is scored
    against the strongest-growing area and affordability against the cheapest
    and dearest. Naming those reference points is what turns "growth fell 8.2"
    from an assertion into something a reader can check — and it explains the
    amplification, since an area that IS the benchmark scores the maximum by
    definition, so it has nowhere to go but down.
    """
    trends = {name: bd['trend'] for name, bd in boroughs.items()}
    prices = {name: bd['avgPrice'] for name, bd in boroughs.items()}
    max_trend = max(trends.values())
    min_trend = min(trends.values())
    top = sorted(n for n, t in trends.items() if t == max_trend)
    # v3.4 scales each tail to its own extreme, so a falling area needs a bottom
    # yardstick just as a rising one needs the top. Under v3.2 every faller
    # scored 0 regardless, so only the top benchmark was ever needed.
    bottom = sorted(n for n, t in trends.items() if t == min_trend)
    dearest = max(prices, key=lambda n: prices[n])
    cheapest = min(prices, key=lambda n: prices[n])
    return {
        'strongestGrowthArea': top[0],
        'strongestGrowthAreas': top,
        'strongestGrowthTrendPct': max_trend,
        'steepestFallArea': bottom[0],
        'steepestFallAreas': bottom,
        'steepestFallTrendPct': min_trend,
        'dearestArea': dearest,
        'dearestAvgPrice': prices[dearest],
        'cheapestArea': cheapest,
        'cheapestAvgPrice': prices[cheapest],
    }


def market_context(current_boroughs, previous_boroughs):
    """City-wide movement, so an individual change is readable in context.

    The single most useful sentence about this vintage pair is not about any one
    borough: the mean trend fell from +3.2% to -1.6% and the number of areas with
    falling prices went from 0 to 14. Without that, 25 boroughs dropping looks
    like a scoring fault rather than the market it is describing.
    """
    cur = [bd['trend'] for bd in current_boroughs.values()]
    prev = [bd['trend'] for bd in previous_boroughs.values()]
    cur_bm = benchmarks(current_boroughs)
    prev_bm = benchmarks(previous_boroughs)
    return {
        'areas': len(cur),
        'meanTrendPct': round(sum(cur) / len(cur), 2),
        'previousMeanTrendPct': round(sum(prev) / len(prev), 2),
        'fallingAreas': sum(1 for t in cur if t < 0),
        'previousFallingAreas': sum(1 for t in prev if t < 0),
        'benchmarks': cur_bm,
        'previousBenchmarks': prev_bm,
        'summary': (
            f'Across the {len(cur)} London boroughs the average 12-month price trend moved from '
            f'{round(sum(prev) / len(prev), 1):+}% to {round(sum(cur) / len(cur), 1):+}%, and the number with '
            f'falling prices went from {sum(1 for t in prev if t < 0)} to {sum(1 for t in cur if t < 0)}. '
            f'Growth is scored relative to the strongest borough, which changed from '
            f'{prev_bm["strongestGrowthArea"]} ({prev_bm["strongestGrowthTrendPct"]:+}%) to '
            f'{cur_bm["strongestGrowthArea"]} ({cur_bm["strongestGrowthTrendPct"]:+}%). '
            'Most scores fell because the market fell, not because any one borough was reassessed.'
        ),
    }


def build_why(
    current, previous, city, weights, name=None, cur_bm=None, prev_bm=None, cur_ranks=None, prev_ranks=None
):
    """A structured account of why a score moved: headline, drivers, caveats.

    Deterministic and derived — no model in the loop. Every field traces to a
    component delta or a published input, which is the point: a reader asking
    "why" gets arithmetic they can redo, not a generated story.

    Structured rather than one long sentence because the earlier prose version
    answered "what moved" but not "why that was so big". A 4.9-point cooling in
    Barking's trend moved its growth score by 8.2, and nothing explained the
    amplification. Each driver now carries `workings` — the actual sum, with the
    benchmark named — so the leap is visible instead of surprising.
    """
    factors = build_attribution(current, previous, weights)
    score_change = round(current['score'] - previous['score'], 1)

    # Computed BEFORE the no-drivers early return. Since v3.3 set growth to 0.00
    # for every persona but investor, "no weighted driver moved" is now the
    # common case rather than the rare one — returning early without this left
    # the most interesting fact ("the market moved and your score did not")
    # unsaid, which is precisely the confusion this whole feature exists to fix.
    unweighted = []
    for key, weight in weights.items():
        if weight != 0:
            continue
        before = previous['components'].get(key)
        after = current['components'].get(key)
        if before is None or after is None or round(after - before, 1) == 0:
            continue
        label = COMPONENT_LABELS.get(key, key)
        unweighted.append(
            {
                'factor': key,
                'label': label,
                'before': before,
                'after': after,
                'change': round(after - before, 1),
                'note': (
                    f'{label} moved from {before} to {after} out of 10, but it carries no weight in this '
                    'view, so it did not change the score.'
                ),
            }
        )
    unweighted_caveat = None
    if unweighted:
        moved = ' and '.join(u['label'] for u in unweighted)
        unweighted_caveat = (
            f'{moved} moved this quarter but is not counted in this view — it is weighted only for the '
            'investor persona, because past price growth describes the market rather than the property.'
        )

    if not factors:
        if unweighted:
            headline = (
                f'Score unchanged at {current["score"]}, even though the market moved.'
            )
            summary = ' '.join(
                [headline] + [u['note'] for u in unweighted] + [unweighted_caveat]
            )
        else:
            headline = 'Score unchanged.'
            summary = (
                'Nothing that this view scores moved between these two quarters, so the score is '
                'unchanged.'
            )
        return {
            'headline': headline,
            'drivers': [],
            'unweighted': unweighted,
            'caveats': [unweighted_caveat] if unweighted_caveat else [],
            'summary': summary,
        }

    magnitude = abs(score_change)
    plural = '' if magnitude == 1 else 's'
    if score_change > 0:
        headline = f'Score rose {magnitude} point{plural}, from {previous["score"]} to {current["score"]}.'
    elif score_change < 0:
        headline = f'Score fell {magnitude} point{plural}, from {previous["score"]} to {current["score"]}.'
    else:
        headline = (
            f'Score held at {current["score"]}, but the factors underneath it moved and cancelled out.'
        )

    cur_price = _price_of(current, city)
    prev_price = _price_of(previous, city)
    cur_trend = current['context'].get('priceTrendPct')
    prev_trend = previous['context'].get('priceTrendPct')
    price_moved = cur_price is not None and prev_price not in (None, 0) and cur_price != prev_price

    # Name the place in the driver text itself. A post-hoc string replace on the
    # flattened summary left the structured drivers — the fields the page
    # actually renders — still saying "This area".
    subject = name or 'This area'
    subject_lower = name or 'this area'

    rank_now = cur_ranks.get(name) if (cur_ranks and name) else None
    rank_before = prev_ranks.get(name) if (prev_ranks and name) else None
    rank_of = len(cur_ranks) if cur_ranks else None

    drivers = []
    caveats = []
    for f in factors:
        pct_weight = int(round(f['weight'] * 100))
        driver = {
            'factor': f['factor'],
            'label': f['label'],
            'before': f['before'],
            'after': f['after'],
            'change': f['change'],
            'contribution': f['contribution'],
            # Units, stated. "Growth fell from 10.0 to 1.8" was read as a
            # percentage; it is a score out of 10 and has to say so.
            'title': f'{f["label"]} score: {f["before"]} → {f["after"]} out of 10',
            'meaning': FACTOR_MEANINGS.get(f['factor'], ''),
            'steps': [],
            'workings': '',
        }
        effect = (
            f'{f["label"]} is {pct_weight}% of the overall score, so this moved the total by '
            f'{f["contribution"]:+.2f}.'
        )

        if f['factor'] == 'growth' and cur_trend is not None and prev_trend is not None:
            # Step 1: what actually happened to prices, in words not scores.
            if cur_trend > 0 and prev_trend > 0:
                pace = (
                    f'Prices here were rising {prev_trend:+}% a year; now they are rising {cur_trend:+}% a year. '
                    'Still rising, just far more slowly.'
                )
            elif cur_trend < 0 <= prev_trend:
                pace = (
                    f'Prices here were rising {prev_trend:+}% a year; now they are falling ({cur_trend:+}% a year).'
                )
            elif cur_trend < 0 and prev_trend < 0:
                pace = f'Prices here were already falling ({prev_trend:+}% a year) and now fall {cur_trend:+}% a year.'
            else:
                pace = f'The 12-month price trend went from {prev_trend:+}% to {cur_trend:+}% a year.'
            driver['steps'].append(pace)

            # Step 2: rank. The single most intuitive statement available, and
            # the one the earlier wording talked around instead of saying.
            if rank_now and rank_before:
                driver['rank'] = rank_now
                driver['previousRank'] = rank_before
                driver['rankOf'] = rank_of
                driver['steps'].append(
                    f'Ranked against every London borough for price growth, {subject_lower} went from '
                    f'{_ordinal(rank_before)} of {rank_of} to {_ordinal(rank_now)} of {rank_of}.'
                )

            # Step 3: why that drops the SCORE so far — the league-table model.
            was_top = prev_bm and prev_trend >= prev_bm['strongestGrowthTrendPct']
            if cur_trend < 0:
                fall_note = (
                    'The growth score puts a flat market — prices neither rising nor falling — at 5 out of 10. '
                    'Falling prices score below 5, scaled against the steepest fall in the city: the borough '
                    'falling fastest scores 0, and every other falling borough sits between.'
                )
                if was_top:
                    fall_note += (
                        f' Last quarter {subject_lower} had the fastest-rising prices in London, so it held the '
                        'top score of 10 — which means it could only ever move down from there.'
                    )
                steepest_pct = cur_bm['steepestFallTrendPct'] if cur_bm else None
                if steepest_pct is not None and steepest_pct < 0:
                    fall_note += (
                        f' The steepest fall now is {cur_bm["steepestFallArea"]} at {steepest_pct:+}%, and '
                        f'{cur_trend:+}% is about {_fraction_words(cur_trend / steepest_pct)} of that — '
                        f'so {f["after"]} out of 10.'
                    )
                    driver['workings'] = (
                        f'5.0 − {cur_trend:+}% ÷ {steepest_pct:+}% '
                        f'({cur_bm["steepestFallArea"]}, steepest fall) × 5 = {f["after"]}'
                    )
                else:
                    driver['workings'] = f'{cur_trend:+}% against a flat-market anchor of 5.0 = {f["after"]}'
                driver['steps'].append(fall_note)
            elif cur_bm and cur_bm['strongestGrowthTrendPct'] > 0:
                share = cur_trend / cur_bm['strongestGrowthTrendPct']
                model = (
                    'The growth score puts a flat market — prices neither rising nor falling — at 5 out of 10. '
                    'Rising prices score above 5, scaled against the fastest riser in the city, which takes the '
                    'full 10.'
                )
                if was_top:
                    model += (
                        f' Last quarter that was {subject_lower} itself, at {prev_trend:+}% — so it took the full '
                        '10, and the only direction available was down.'
                    )
                model += (
                    f' The fastest now is {cur_bm["strongestGrowthArea"]} at {cur_bm["strongestGrowthTrendPct"]:+}%, '
                    f'and {cur_trend:+}% is about {_fraction_words(share)} of that — so {f["after"]} out of 10.'
                )
                driver['steps'].append(model)
                driver['workings'] = (
                    f'5.0 + {cur_trend:+}% ÷ {cur_bm["strongestGrowthTrendPct"]:+}% '
                    f'({cur_bm["strongestGrowthArea"]}, fastest) × 5 = {f["after"]}'
                )
                if rank_now and rank_before and rank_now > rank_before and cur_trend > 0:
                    caveats.append(
                        f'{subject} did not get worse in absolute terms — prices are still rising. It fell '
                        'because other boroughs are now rising faster.'
                    )
            # Rank can improve while the underlying number gets worse, if others
            # fall further. Silence there would look like an error.
            if rank_now and rank_before and rank_now < rank_before and cur_trend < prev_trend:
                caveats.append(
                    f'Oddly, {subject_lower} moved UP the growth table ({_ordinal(rank_before)} to '
                    f'{_ordinal(rank_now)}) even though its own prices did worse — other boroughs fell further.'
                )

        elif f['factor'] == 'afford':
            if price_moved:
                pct = round((cur_price - prev_price) / prev_price * 100, 1)
                moved = 'rose' if pct > 0 else 'fell'
                driver['steps'].append(
                    f'The average price here {moved} {abs(pct)}%, from {_money(prev_price, city)} to '
                    f'{_money(cur_price, city)}.'
                )
            else:
                driver['steps'].append(
                    f"The average price here did not change ({_money(cur_price, city)}). What moved was the rest "
                    'of London.'
                )
            if cur_bm:
                driver['steps'].append(
                    'Affordability is also a league table: the cheapest borough scores 10 and the dearest scores '
                    f'0, with everywhere else in between. Right now that runs from {cur_bm["cheapestArea"]} at '
                    f'{_money(cur_bm["cheapestAvgPrice"], city)} up to {cur_bm["dearestArea"]} at '
                    f'{_money(cur_bm["dearestAvgPrice"], city)}.'
                )
                driver['workings'] = (
                    f'({_money(cur_bm["dearestAvgPrice"], city)} − {_money(cur_price, city)}) ÷ '
                    f'({_money(cur_bm["dearestAvgPrice"], city)} − {_money(cur_bm["cheapestAvgPrice"], city)}) '
                    f'× 10 = {f["after"]}'
                )
        elif f['factor'] in ('quiet', 'live'):
            driver['steps'].append('The underlying data for this factor was refreshed this quarter.')

        driver['steps'].append(effect)
        drivers.append(driver)

    if unweighted_caveat:
        caveats.append(unweighted_caveat)

    explained = round(sum(f['contribution'] for f in factors), 2)
    residual = round(score_change - explained, 2)
    if abs(residual) >= 0.05:
        caveats.append(
            f'The drivers sum to {explained:+.2f} against a published change of {score_change:+.1f}; the '
            f'{abs(residual):.2f} difference is rounding in the per-factor values, not a missing driver.'
        )

    # The flattened summary must be self-contained: a caller reading only
    # `explanation` should not lose the workings or the caveats, or they would
    # miss things like growth being floored — the disclosure that explains why a
    # collapsing trend can barely move a score.
    # Self-contained by construction: title, every step, the workings AND the
    # caveats. A caller reading only `explanation` must not lose the floor
    # disclosure, which lives in `workings` — this has regressed once already.
    parts = [headline]
    parts.extend(u['note'] for u in unweighted)
    for d in drivers:
        parts.append(d['title'] + '.')
        parts.extend(d['steps'])
        if d['workings']:
            parts.append(f'({d["workings"]}.)')
    parts.extend(caveats)
    summary = ' '.join(parts)

    return {
        'headline': headline,
        'drivers': drivers,
        'unweighted': unweighted,
        'caveats': caveats,
        'summary': summary,
    }


def describe_change(
    current, previous, city, weights, name=None, cur_bm=None, prev_bm=None, cur_ranks=None, prev_ranks=None
):
    """Flattened prose form of build_why, kept for callers wanting one string."""
    return build_why(current, previous, city, weights, name, cur_bm, prev_bm, cur_ranks, prev_ranks)['summary']


# London borough dataset, sourced from index.html BOROUGH_DATA_RAW + BOROUGH_EXTRA.
# Schema: impact (DEFRA Lden band), avgPrice (GBP), trend (% YoY),
# schools/transport/healthcare (categorical), crimeRate (per 1,000 ONS).
LONDON_BOROUGHS = {
    'Hounslow': {
        'impact': 'severe',
        'avgPrice': 501000,
        'trend': -2.4,
        'schools': 'good',
        'crimeRate': 87.4,
        'p8': 0.45,
        'transport': 'good',
        'healthcare': 'good',
    },
    'Hillingdon': {
        'impact': 'severe',
        'avgPrice': 468000,
        'trend': -0.7,
        'schools': 'good',
        'crimeRate': 91.6,
        'p8': 0.24,
        'transport': 'good',
        'healthcare': 'good',
    },
    'Richmond upon Thames': {
        'impact': 'high',
        'avgPrice': 789000,
        'trend': -2.5,
        'schools': 'excellent',
        'crimeRate': 57.3,
        'p8': 0.4,
        'transport': 'good',
        'healthcare': 'good',
    },
    'Ealing': {
        'impact': 'high',
        'avgPrice': 569000,
        'trend': -2.5,
        'schools': 'good',
        'crimeRate': 80.5,
        'p8': 0.62,
        'transport': 'excellent',
        'healthcare': 'good',
    },
    'Wandsworth': {
        'impact': 'moderate',
        'avgPrice': 660000,
        'trend': -6.1,
        'schools': 'excellent',
        'crimeRate': 76.4,
        'p8': 0.33,
        'transport': 'excellent',
        'healthcare': 'good',
    },
    'Lambeth': {
        'impact': 'moderate',
        'avgPrice': 545000,
        'trend': -2.9,
        'schools': 'good',
        'crimeRate': 114.4,
        'p8': 0.01,
        'transport': 'excellent',
        'healthcare': 'good',
    },
    'Lewisham': {
        'impact': 'low-moderate',
        'avgPrice': 497000,
        'trend': 2.3,
        'schools': 'good',
        'crimeRate': 94.2,
        'p8': 0.0,
        'transport': 'good',
        'healthcare': 'good',
    },
    'Greenwich': {
        'impact': 'moderate',
        'avgPrice': 463000,
        'trend': 0.1,
        'schools': 'good',
        'crimeRate': 90.3,
        'p8': -0.01,
        'transport': 'good',
        'healthcare': 'good',
    },
    'Tower Hamlets': {
        'impact': 'low-moderate',
        'avgPrice': 444000,
        'trend': -14.5,
        'schools': 'good',
        'crimeRate': 106.6,
        'p8': 0.21,
        'transport': 'excellent',
        'healthcare': 'excellent',
    },
    'Camden': {
        'impact': 'low',
        'avgPrice': 806000,
        'trend': -6.2,
        'schools': 'excellent',
        'crimeRate': 173.3,
        'p8': -0.03,
        'transport': 'excellent',
        'healthcare': 'excellent',
    },
    'Islington': {
        'impact': 'low',
        'avgPrice': 670000,
        'trend': -6.4,
        'schools': 'good',
        'crimeRate': 131.2,
        'p8': -0.03,
        'transport': 'excellent',
        'healthcare': 'good',
    },
    'Hackney': {
        'impact': 'low',
        'avgPrice': 608000,
        'trend': 0.1,
        'schools': 'good',
        'crimeRate': 116.5,
        'p8': 0.34,
        'transport': 'excellent',
        'healthcare': 'good',
    },
    'Barnet': {
        'impact': 'low-moderate',
        'avgPrice': 591000,
        'trend': -4.3,
        'schools': 'excellent',
        'crimeRate': 67.8,
        'p8': 0.64,
        'transport': 'good',
        'healthcare': 'good',
    },
    'Croydon': {
        'impact': 'moderate',
        'avgPrice': 397000,
        'trend': -0.4,
        'schools': 'good',
        'crimeRate': 80.4,
        'p8': 0.01,
        'transport': 'good',
        'healthcare': 'good',
    },
    'Bromley': {
        'impact': 'low',
        'avgPrice': 525000,
        'trend': 0.2,
        'schools': 'excellent',
        'crimeRate': 69.1,
        'p8': 0.04,
        'transport': 'moderate',
        'healthcare': 'good',
    },
    'Newham': {
        'impact': 'moderate-high',
        'avgPrice': 405000,
        'trend': -1.4,
        'schools': 'good',
        'crimeRate': 104.0,
        'p8': 0.25,
        'transport': 'excellent',
        'healthcare': 'good',
    },
    'Southwark': {
        'impact': 'low-moderate',
        'avgPrice': 579000,
        'trend': 0.9,
        'schools': 'good',
        'crimeRate': 120.8,
        'p8': 0.38,
        'transport': 'excellent',
        'healthcare': 'excellent',
    },
    'Hammersmith and Fulham': {
        'impact': 'moderate-high',
        'avgPrice': 729000,
        'trend': -10.9,
        'schools': 'excellent',
        'crimeRate': 107.0,
        'p8': 0.47,
        'transport': 'excellent',
        'healthcare': 'good',
    },
    'Kensington and Chelsea': {
        'impact': 'moderate',
        'avgPrice': 1256000,
        'trend': -10.7,
        'schools': 'excellent',
        'crimeRate': 145.8,
        'p8': 0.3,
        'transport': 'excellent',
        'healthcare': 'excellent',
    },
    'Brent': {
        'impact': 'low-moderate',
        'avgPrice': 549000,
        'trend': -3.3,
        'schools': 'good',
        'crimeRate': 89.3,
        'p8': 0.61,
        'transport': 'good',
        'healthcare': 'good',
    },
    'Haringey': {
        'impact': 'low',
        'avgPrice': 634000,
        'trend': 2.4,
        'schools': 'good',
        'crimeRate': 104.6,
        'p8': 0.21,
        'transport': 'good',
        'healthcare': 'moderate',
    },
    'Waltham Forest': {
        'impact': 'low',
        'avgPrice': 524000,
        'trend': 3.1,
        'schools': 'good',
        'crimeRate': 80.2,
        'p8': -0.06,
        'transport': 'good',
        'healthcare': 'moderate',
    },
    'Merton': {
        'impact': 'low-moderate',
        'avgPrice': 597000,
        'trend': -1.3,
        'schools': 'good',
        'crimeRate': 59.3,
        'p8': 0.59,
        'transport': 'good',
        'healthcare': 'good',
    },
    'Redbridge': {
        'impact': 'low',
        'avgPrice': 496000,
        'trend': 2.4,
        'schools': 'excellent',
        'crimeRate': 74.3,
        'p8': 0.5,
        'transport': 'good',
        'healthcare': 'good',
    },
    'Enfield': {
        'impact': 'low',
        'avgPrice': 469000,
        'trend': -0.7,
        'schools': 'good',
        'crimeRate': 85.2,
        'p8': 0.21,
        'transport': 'moderate',
        'healthcare': 'moderate',
    },
    'Kingston upon Thames': {
        'impact': 'low-moderate',
        'avgPrice': 582000,
        'trend': 0.0,
        'schools': 'excellent',
        'crimeRate': 66.8,
        'p8': 0.58,
        'transport': 'good',
        'healthcare': 'good',
    },
    'Sutton': {
        'impact': 'low',
        'avgPrice': 445000,
        'trend': 0.9,
        'schools': 'excellent',
        'crimeRate': 60.3,
        'p8': 0.51,
        'transport': 'moderate',
        'healthcare': 'good',
    },
    'Westminster': {
        'impact': 'moderate',
        'avgPrice': 836000,
        'trend': -22.8,
        'schools': 'good',
        'crimeRate': 355.5,
        'p8': 0.48,
        'transport': 'excellent',
        'healthcare': 'excellent',
    },
    'City of London': {
        # ONS declines to publish a recorded-crime rate here (Table C4 note 8,
        # small resident population), so the 190 below is Sky Score's own
        # estimate and must never be attributed to them. Flagged in the data
        # rather than in a name list so the fact travels with the row.
        # METHODOLOGY 11 records it as an open decision.
        'crimeEstimated': True,
        'impact': 'low-moderate',
        'avgPrice': 627000,
        'trend': -28.1,
        'schools': 'good',
        'crimeRate': 190,
        'transport': 'excellent',
        'healthcare': 'good',
    },
    'Barking and Dagenham': {
        'impact': 'low',
        'avgPrice': 361000,
        'trend': -0.2,
        'schools': 'good',
        'crimeRate': 84.2,
        'p8': 0.24,
        'transport': 'good',
        'healthcare': 'moderate',
    },
    'Havering': {
        'impact': 'low',
        'avgPrice': 453000,
        'trend': 2.8,
        'schools': 'good',
        'crimeRate': 68.3,
        'p8': -0.09,
        'transport': 'moderate',
        'healthcare': 'good',
    },
    'Bexley': {
        'impact': 'low',
        'avgPrice': 409000,
        'trend': 2.2,
        'schools': 'good',
        'crimeRate': 60.2,
        'p8': -0.06,
        'transport': 'moderate',
        'healthcare': 'good',
    },
    'Harrow': {
        'impact': 'low',
        'avgPrice': 530000,
        'trend': 0.4,
        'schools': 'excellent',
        'crimeRate': 59.5,
        'p8': 0.45,
        'transport': 'good',
        'healthcare': 'good',
    },
}

# NYC borough dataset, sourced from index.html NYC_BOROUGH_DATA_RAW + NYC_BOROUGH_EXTRA.
# avgPrice in USD (not GBP). Crime rates use the same per-1,000 convention but
# are derived from NYPD CompStat / NYC ONS-equivalent denominators; cross-city
# comparison should be approached with caution (different methodologies).
NYC_BOROUGHS = {
    'Queens': {
        'impact': 'severe',
        'avgPrice': 620000,
        'trend': 4.5,
        'schools': 'good',
        'crimeRate': 78,
        'transport': 'excellent',
        'healthcare': 'good',
    },
    'Brooklyn': {
        'impact': 'high',
        'avgPrice': 850000,
        'trend': 3.8,
        'schools': 'good',
        'crimeRate': 82,
        'transport': 'excellent',
        'healthcare': 'excellent',
    },
    'Manhattan': {
        'impact': 'moderate',
        'avgPrice': 1200000,
        'trend': 2.0,
        'schools': 'excellent',
        'crimeRate': 95,
        'transport': 'excellent',
        'healthcare': 'excellent',
    },
    'Bronx': {
        'impact': 'low-moderate',
        'avgPrice': 420000,
        'trend': 5.5,
        'schools': 'good',
        'crimeRate': 110,
        'transport': 'good',
        'healthcare': 'good',
    },
    'Staten Island': {
        'impact': 'low',
        'avgPrice': 550000,
        'trend': 3.0,
        'schools': 'good',
        'crimeRate': 52,
        'transport': 'poor',
        'healthcare': 'moderate',
    },
}

# --- Greater Manchester ------------------------------------------------------
#
# The ten metropolitan boroughs, modelled exactly like London's 33: a
# city-region whose constituent local authorities play the role "borough" plays
# in London. No new concept, same schema, same scoring path.
#
# PROVENANCE, read this before trusting any number here. Every figure below was
# re-verified on 2026-08-09 rather than taken on the word of the commit that
# added it, because that commit's own header comment described a DIFFERENT set
# of fields to the ones it shipped.
#
#   avgPrice / trend  REAL. HM Land Registry UK House Price Index, May 2026
#                     vintage - the same vintage as LONDON_BOROUGHS, so the two
#                     cohorts are directly comparable.
#
#   crimeRate         REAL. ONS Crime in England and Wales, Police Force Area
#                     data tables, Table C4, year ending March 2026 - the same
#                     release and period as London. VERIFIED: all ten match the
#                     published workbook exactly.
#
#                     These predate scripts/refresh_crime_from_ons.py, which was
#                     written after that script's London run found 29 of 33
#                     borough rates wrong, so "same source as London" was not on
#                     its own sufficient assurance. They were checked directly.
#
#                     Greater Manchester Police is ONE force across all ten
#                     boroughs, so force-level data cannot separate them. Table
#                     C4 also carries COMMUNITY SAFETY PARTNERSHIP rows, which
#                     are local-authority level, and that is what these are.
#                     Note GM returns ELEVEN CSP rows: `Manchester Airport` is
#                     its own partnership and is not a borough.
#
#   p8                REAL. DfE Key Stage 4 Progress 8, 2022/23, local-authority
#                     level - the same release London uses. VERIFIED by a
#                     different route: all 32 of London's p8 values are
#                     byte-identical between this data's source commit and
#                     master, so the same extraction produced both and this
#                     inherits London's standing.
#
#   impact            ESTIMATE, from runway geometry - see FLIGHT_PATHS_MANCHESTER.
#                     NOT DEFRA. The Round 4 raster has not been sampled for
#                     Greater Manchester, so METHODOLOGY section 3's dB Lden
#                     thresholds are not evidenced here. CITY_PROVENANCE says so
#                     in every response; do not let this become a measurement by
#                     omission.
#
#   transport         NOT SOURCED. Absent, not defaulted. Since 2026-08-09 an
#   healthcare        absent liveability input has its weight redistributed
#                     across the ones that exist rather than filled with a 5.0
#                     placeholder, so these two being missing costs Manchester
#                     nothing it has not earned - it is scored on schools and
#                     crime, and context.liveResolution reports "partial - 2/4".
#                     Before that change a partial city scored WORSE than an
#                     empty one, which is why this data sat unported for a week.
MANCHESTER_BOROUGHS = {
    'Manchester': {'impact': 'severe', 'avgPrice': 247469, 'trend': 0.5, 'p8': -0.02, 'crimeRate': 142.7},
    'Salford': {'impact': 'low-moderate', 'avgPrice': 231153, 'trend': -6.1, 'p8': -0.49, 'crimeRate': 105.8},
    'Stockport': {'impact': 'high', 'avgPrice': 318163, 'trend': 5.4, 'p8': -0.04, 'crimeRate': 74.8},
    'Trafford': {'impact': 'moderate', 'avgPrice': 393244, 'trend': 6.2, 'p8': 0.24, 'crimeRate': 74.9},
    'Tameside': {'impact': 'moderate', 'avgPrice': 209691, 'trend': 2.3, 'p8': -0.21, 'crimeRate': 96.4},
    'Oldham': {'impact': 'low', 'avgPrice': 212997, 'trend': 3.0, 'p8': -0.18, 'crimeRate': 106.6},
    'Rochdale': {'impact': 'low', 'avgPrice': 208286, 'trend': 4.3, 'p8': -0.28, 'crimeRate': 104.6},
    'Bury': {'impact': 'low', 'avgPrice': 238266, 'trend': 3.0, 'p8': -0.14, 'crimeRate': 92.1},
    'Bolton': {'impact': 'low', 'avgPrice': 200126, 'trend': 3.3, 'p8': -0.08, 'crimeRate': 98.0},
    'Wigan': {'impact': 'low', 'avgPrice': 194494, 'trend': 5.4, 'p8': -0.39, 'crimeRate': 91.0},
}

# West Midlands, the fourth city, 2026-08-10. Every field is generated, not
# authored, and each has a script that re-derives it:
#
#   avgPrice / trend  REAL. HM Land Registry UK HPI, May 2026 vintage - the same
#                     release London and Greater Manchester use, so the three
#                     cohorts are on one vintage. `scripts/build_hpi_prices.py
#                     --check --city westmidlands` is a blocking preflight stage.
#
#   crimeRate         REAL. ONS Crime in England and Wales, Police Force Area
#                     tables, Table C4, year ending March 2026 - Community
#                     Safety Partnership rows, which are local-authority level.
#                     West Midlands Police is one force across all seven, and
#                     all seven matched. Same release and period as London.
#
#   impact            ESTIMATE from Birmingham Airport's runway 15/33 geometry,
#                     NOT DEFRA - `scripts/build_aircraft_bands.py`. The Round 4
#                     raster has not been sampled here, so METHODOLOGY section 3's
#                     dB Lden thresholds are not evidenced for this city and the
#                     legend says ESTIMATED rather than naming a regulator.
#
#   schools (p8)      NOT SOURCED, for any city added after Greater Manchester -
#   transport         there is no Progress 8 pipeline in this repo at all. With
#   healthcare        crime as the only liveability input, `live` falls below its
#                     two-input floor and is DROPPED, its weight redistributed
#                     across quiet/afford/growth rather than filled with a 5.0
#                     placeholder. context.liveResolution reports that per
#                     response. This city is thinner than Greater Manchester and
#                     says so.
WESTMIDLANDS_BOROUGHS = {
    'Birmingham': {'impact': 'severe', 'avgPrice': 232657, 'trend': -0.3, 'crimeRate': 114.2, 'p8': 0.03},
    'Coventry': {'impact': 'low-moderate', 'avgPrice': 220410, 'trend': 1.3, 'crimeRate': 88.4, 'p8': -0.05},
    'Dudley': {'impact': 'low-moderate', 'avgPrice': 229616, 'trend': 4.5, 'crimeRate': 74.5, 'p8': -0.11},
    'Sandwell': {'impact': 'low-moderate', 'avgPrice': 209354, 'trend': 2.9, 'crimeRate': 95.9, 'p8': -0.07},
    'Solihull': {'impact': 'severe', 'avgPrice': 336572, 'trend': 4.0, 'crimeRate': 79.5, 'p8': -0.11},
    'Walsall': {'impact': 'moderate', 'avgPrice': 214032, 'trend': 1.6, 'crimeRate': 92.9, 'p8': -0.2},
    'Wolverhampton': {'impact': 'low', 'avgPrice': 216339, 'trend': 8.0, 'crimeRate': 92.0, 'p8': -0.02},
}

WESTYORKSHIRE_BOROUGHS = {
    'Bradford': {'impact': 'moderate', 'avgPrice': 187452, 'trend': 5.6, 'crimeRate': 117.0, 'p8': -0.26},
    'Calderdale': {'impact': 'low', 'avgPrice': 189509, 'trend': 5.1, 'crimeRate': 103.4, 'p8': -0.03},
    'Kirklees': {'impact': 'low', 'avgPrice': 205971, 'trend': 4.1, 'crimeRate': 87.6, 'p8': 0.11},
    'Leeds': {'impact': 'moderate-high', 'avgPrice': 246699, 'trend': 3.7, 'crimeRate': 114.6, 'p8': 0.12},
    'Wakefield': {'impact': 'low', 'avgPrice': 197140, 'trend': 2.7, 'crimeRate': 105.8, 'p8': 0.12},
}

SOUTHYORKSHIRE_BOROUGHS = {
    'Barnsley': {'impact': 'low', 'avgPrice': 173077, 'trend': 3.8, 'crimeRate': 95.1, 'p8': -0.16},
    'Doncaster': {'impact': 'low', 'avgPrice': 172857, 'trend': 4.1, 'crimeRate': 117.3, 'p8': 0.01},
    'Rotherham': {'impact': 'low', 'avgPrice': 192309, 'trend': 2.9, 'crimeRate': 93.1, 'p8': -0.15},
    'Sheffield': {'impact': 'low', 'avgPrice': 220804, 'trend': 3.5, 'crimeRate': 96.9, 'p8': -0.09},
}

MERSEYSIDE_BOROUGHS = {
    'Knowsley': {'impact': 'moderate', 'avgPrice': 188727, 'trend': 3.0, 'crimeRate': 81.8, 'p8': -0.9},
    'Liverpool': {'impact': 'high', 'avgPrice': 184670, 'trend': 4.8, 'crimeRate': 124.1, 'p8': -0.43},
    'St Helens': {'impact': 'low-moderate', 'avgPrice': 182923, 'trend': 8.8, 'crimeRate': 86.4, 'p8': -0.35},
    'Sefton': {'impact': 'low', 'avgPrice': 222406, 'trend': 3.5, 'crimeRate': 75.5, 'p8': -0.48},
    'Wirral': {'impact': 'moderate-high', 'avgPrice': 217407, 'trend': 6.5, 'crimeRate': 71.1, 'p8': -0.11},
}

TYNEANDWEAR_BOROUGHS = {
    'Gateshead': {'impact': 'moderate', 'avgPrice': 158765, 'trend': 6.3, 'crimeRate': 87.8, 'p8': -0.11},
    'Newcastle upon Tyne': {'impact': 'severe', 'avgPrice': 207029, 'trend': 3.7, 'crimeRate': 107.4, 'p8': -0.4},
    'North Tyneside': {'impact': 'moderate', 'avgPrice': 200392, 'trend': 3.8, 'crimeRate': 81.8, 'p8': -0.09},
    'South Tyneside': {'impact': 'low-moderate', 'avgPrice': 159318, 'trend': 3.8, 'crimeRate': 96.6, 'p8': -0.27},
    'Sunderland': {'impact': 'low-moderate', 'avgPrice': 145921, 'trend': 6.9, 'crimeRate': 93.6, 'p8': -0.5},
}

BRISTOL_BOROUGHS = {
    'City of Bristol': {'impact': 'moderate', 'avgPrice': 354924, 'trend': 2.2, 'crimeRate': 131.0, 'p8': -0.03},
    'Bath and North East Somerset': {'impact': 'moderate', 'avgPrice': 406169, 'trend': 0.9, 'crimeRate': 79.0, 'p8': 0.26},
    'North Somerset': {'impact': 'severe', 'avgPrice': 312303, 'trend': 6.4, 'crimeRate': 81.8, 'p8': -0.02},
    'South Gloucestershire': {'impact': 'low', 'avgPrice': 340401, 'trend': 2.1, 'crimeRate': 73.8, 'p8': 0.02},
}

CARDIFF_BOROUGHS = {
    'Cardiff': {'impact': 'moderate', 'avgPrice': 272866, 'trend': 2.9, 'crimeRate': 93.8},
    'Vale of Glamorgan': {'impact': 'severe', 'avgPrice': 292677, 'trend': 2.9, 'crimeRate': 60.8},
    'Newport': {'impact': 'low', 'avgPrice': 231830, 'trend': 5.8, 'crimeRate': 109.4},
    'Caerphilly': {'impact': 'low', 'avgPrice': 198809, 'trend': 9.2, 'crimeRate': 85.3},
}


# Nottingham (Greater Nottingham: the city plus the three boroughs of its
# conurbation, so the cohort is not a single authority scoring afford 5.0 flat).
#
# crimeRate is present for the CITY ONLY, and its absence elsewhere is the
# honest reading rather than a gap to fill. ONS Table C4 publishes `Nottingham`
# and `South Nottinghamshire`; Broxtowe, Gedling and Rushcliffe sit inside that
# one combined partnership row and are not published separately. Spreading the
# combined rate across the three would render ONE measurement as THREE, which is
# the defect class the crime checker exists to prevent.
#
# It costs nothing today: get_live_score returns None below two inputs, and with
# no Progress 8 pipeline every city added after Greater Manchester has crime as
# its ONLY liveability input, so `live` is dropped for all of them regardless.
# When p8 lands, these three need a decision before `live` can be published
# here - the omission is what forces that rather than letting a shared rate
# become three measurements by default.
NOTTINGHAM_BOROUGHS = {
    'City of Nottingham': {'impact': 'low-moderate', 'avgPrice': 190806, 'trend': -0.7, 'crimeRate': 124.9, 'p8': -0.23},
    'Broxtowe': {'impact': 'low-moderate', 'avgPrice': 253567, 'trend': 1.9},
    'Gedling': {'impact': 'low', 'avgPrice': 246120, 'trend': 3.1},
    'Rushcliffe': {'impact': 'low-moderate', 'avgPrice': 338301, 'trend': 3.5},
}

CITIES = {
    'london': {
        'boroughs': LONDON_BOROUGHS,
        'currency': 'GBP',
        'name': 'London',
        'country': 'United Kingdom',
        'postcodeFormat': 'UK postcode (e.g. SW11 1AA)',
        # Keyed on what has actually SERVED, exactly as build_sources is — not
        # on POSTCODE_TABLE being set. Keying it on config let /v1/regions claim
        # ONS NSPL while every /v1/score response in the same window credited
        # postcodes.io: two endpoints of one API contradicting each other on
        # machine-readable provenance.
        'postcodeResolver': lambda: (
            'ONS NSPL local table, postcodes.io fallback'
            if _LOCAL_POSTCODE_SERVED
            else 'postcodes.io'
        ),
        # Present in the dataset at PREVIOUS_VINTAGE, so ?compare=previous has a
        # real baseline. Absent/False means the city postdates that vintage and
        # must decline to compare — see previous_dataset(). Defaulting to False
        # makes a newly added city safe rather than silently fabricating history.
        'hasHistory': True,
    },
    'nyc': {
        'boroughs': NYC_BOROUGHS,
        'currency': 'USD',
        'name': 'New York City',
        'country': 'United States',
        'postcodeFormat': '5-digit US ZIP (e.g. 10001), with optional +4 suffix',
        'postcodeResolver': lambda: 'static ZIP-to-borough lookup',
        'extra': lambda: {'supportedZipCount': len(NYC_ZIP_TO_BOROUGH)},
        # Existed at PREVIOUS_VINTAGE but had no quarterly refresh, so its
        # zero-change comparison is an honest measurement, not a placeholder.
        'hasHistory': True,
    },
    'westmidlands': {
        'boroughs': WESTMIDLANDS_BOROUGHS,
        'currency': 'GBP',
        'name': 'West Midlands',
        'country': 'United Kingdom',
        'postcodeFormat': 'UK postcode (e.g. B1 1AA)',
        # Same two blockers as Greater Manchester, stated the same way:
        # resolve_query() gates UK postcode lookup to London, and load_nspl.py
        # writes the borough attribute for London LADs alone.
        # Keyed on what has actually SERVED, exactly as London is. A static
        # string here claimed the NSPL table even when it had not answered -
        # the "credit a source on configuration rather than on what answered"
        # defect CITY_PROVENANCE exists to prevent. The test that flips
        # _LOCAL_POSTCODE_SERVED caught it on the first run.
        'postcodeResolver': lambda: (
            'ONS NSPL local table by LAD code, postcodes.io fallback'
            if _LOCAL_POSTCODE_SERVED
            else 'postcodes.io'
        ),
        # Omitted, so False: this city did not exist at PREVIOUS_VINTAGE and
        # ?compare=previous must decline rather than report a fabricated zero.
        # 'hasHistory': False,
    },
    'westyorkshire': {
        'boroughs': WESTYORKSHIRE_BOROUGHS,
        'currency': 'GBP',
        'name': 'West Yorkshire',
        'country': 'United Kingdom',
        'postcodeFormat': 'UK postcode (e.g. LS1 1AA)',
        # Keyed on what has actually SERVED, exactly as London is. A static
        # string here claimed the NSPL table even when it had not answered -
        # the "credit a source on configuration rather than on what answered"
        # defect CITY_PROVENANCE exists to prevent. The test that flips
        # _LOCAL_POSTCODE_SERVED caught it on the first run.
        'postcodeResolver': lambda: (
            'ONS NSPL local table by LAD code, postcodes.io fallback'
            if _LOCAL_POSTCODE_SERVED
            else 'postcodes.io'
        ),
        # Omitted, so False: postdates PREVIOUS_VINTAGE, so ?compare=previous
        # must decline rather than report a fabricated zero change.
    },
    'southyorkshire': {
        'boroughs': SOUTHYORKSHIRE_BOROUGHS,
        'currency': 'GBP',
        'name': 'South Yorkshire',
        'country': 'United Kingdom',
        'postcodeFormat': 'UK postcode (e.g. S1 1AA)',
        # Keyed on what has actually SERVED, exactly as London is. A static
        # string here claimed the NSPL table even when it had not answered -
        # the "credit a source on configuration rather than on what answered"
        # defect CITY_PROVENANCE exists to prevent. The test that flips
        # _LOCAL_POSTCODE_SERVED caught it on the first run.
        'postcodeResolver': lambda: (
            'ONS NSPL local table by LAD code, postcodes.io fallback'
            if _LOCAL_POSTCODE_SERVED
            else 'postcodes.io'
        ),
        # Omitted, so False: postdates PREVIOUS_VINTAGE, so ?compare=previous
        # must decline rather than report a fabricated zero change.
    },
    'merseyside': {
        'boroughs': MERSEYSIDE_BOROUGHS,
        'currency': 'GBP',
        'name': 'Merseyside',
        'country': 'United Kingdom',
        'postcodeFormat': 'UK postcode (e.g. L1 1AA)',
        # Keyed on what has actually SERVED, exactly as London is. A static
        # string here claimed the NSPL table even when it had not answered -
        # the "credit a source on configuration rather than on what answered"
        # defect CITY_PROVENANCE exists to prevent. The test that flips
        # _LOCAL_POSTCODE_SERVED caught it on the first run.
        'postcodeResolver': lambda: (
            'ONS NSPL local table by LAD code, postcodes.io fallback'
            if _LOCAL_POSTCODE_SERVED
            else 'postcodes.io'
        ),
        # Omitted, so False: postdates PREVIOUS_VINTAGE, so ?compare=previous
        # must decline rather than report a fabricated zero change.
    },
    'tyneandwear': {
        'boroughs': TYNEANDWEAR_BOROUGHS,
        'currency': 'GBP',
        'name': 'Tyne and Wear',
        'country': 'United Kingdom',
        'postcodeFormat': 'UK postcode (e.g. NE1 1AA)',
        # Keyed on what has actually SERVED, exactly as London is. A static
        # string here claimed the NSPL table even when it had not answered -
        # the "credit a source on configuration rather than on what answered"
        # defect CITY_PROVENANCE exists to prevent. The test that flips
        # _LOCAL_POSTCODE_SERVED caught it on the first run.
        'postcodeResolver': lambda: (
            'ONS NSPL local table by LAD code, postcodes.io fallback'
            if _LOCAL_POSTCODE_SERVED
            else 'postcodes.io'
        ),
        # Omitted, so False: postdates PREVIOUS_VINTAGE, so ?compare=previous
        # must decline rather than report a fabricated zero change.
    },
    'bristol': {
        'boroughs': BRISTOL_BOROUGHS,
        'currency': 'GBP',
        'name': 'Bristol',
        'country': 'United Kingdom',
        'postcodeFormat': 'UK postcode (e.g. BS1 1AA)',
        # Keyed on what has actually SERVED, exactly as London is. A static
        # string here claimed the NSPL table even when it had not answered -
        # the "credit a source on configuration rather than on what answered"
        # defect CITY_PROVENANCE exists to prevent. The test that flips
        # _LOCAL_POSTCODE_SERVED caught it on the first run.
        'postcodeResolver': lambda: (
            'ONS NSPL local table by LAD code, postcodes.io fallback'
            if _LOCAL_POSTCODE_SERVED
            else 'postcodes.io'
        ),
        # Omitted, so False: postdates PREVIOUS_VINTAGE, so ?compare=previous
        # must decline rather than report a fabricated zero change.
    },
    'cardiff': {
        'boroughs': CARDIFF_BOROUGHS,
        'currency': 'GBP',
        'name': 'Cardiff',
        'country': 'United Kingdom',
        'postcodeFormat': 'UK postcode (e.g. CF10 1AA)',
        # Keyed on what has actually SERVED, exactly as London is. A static
        # string here claimed the NSPL table even when it had not answered -
        # the "credit a source on configuration rather than on what answered"
        # defect CITY_PROVENANCE exists to prevent. The test that flips
        # _LOCAL_POSTCODE_SERVED caught it on the first run.
        'postcodeResolver': lambda: (
            'ONS NSPL local table by LAD code, postcodes.io fallback'
            if _LOCAL_POSTCODE_SERVED
            else 'postcodes.io'
        ),
        # Omitted, so False: postdates PREVIOUS_VINTAGE, so ?compare=previous
        # must decline rather than report a fabricated zero change.
    },
    'nottingham': {
        'boroughs': NOTTINGHAM_BOROUGHS,
        'currency': 'GBP',
        'name': 'Nottingham',
        'country': 'United Kingdom',
        'postcodeFormat': 'UK postcode (e.g. NG1 1AA)',
        # Keyed on what has actually SERVED, exactly as London is. A static
        # string here claimed the NSPL table even when it had not answered -
        # the "credit a source on configuration rather than on what answered"
        # defect CITY_PROVENANCE exists to prevent. The test that flips
        # _LOCAL_POSTCODE_SERVED caught it on the first run.
        'postcodeResolver': lambda: (
            'ONS NSPL local table by LAD code, postcodes.io fallback'
            if _LOCAL_POSTCODE_SERVED
            else 'postcodes.io'
        ),
    },
    'manchester': {
        'boroughs': MANCHESTER_BOROUGHS,
        'currency': 'GBP',
        'name': 'Greater Manchester',
        'country': 'United Kingdom',
        'postcodeFormat': 'UK postcode (e.g. M1 1AE)',
        # Honest rather than aspirational: resolve_query() hard-gates UK
        # postcode lookup to London, AND scripts/load_nspl.py writes the borough
        # attribute for London LADs only, so a Manchester postcode does not
        # resolve today. Two blockers, not one. An integrator should learn that
        # here rather than by sending a request and getting an unhelpful miss.
        # Keyed on what has actually SERVED, exactly as London is. A static
        # string here claimed the NSPL table even when it had not answered -
        # the "credit a source on configuration rather than on what answered"
        # defect CITY_PROVENANCE exists to prevent. The test that flips
        # _LOCAL_POSTCODE_SERVED caught it on the first run.
        'postcodeResolver': lambda: (
            'ONS NSPL local table by LAD code, postcodes.io fallback'
            if _LOCAL_POSTCODE_SERVED
            else 'postcodes.io'
        ),
        # Omitted deliberately, which means False: Greater Manchester did not
        # exist at PREVIOUS_VINTAGE, so ?compare=previous must DECLINE rather
        # than return the current set and present a fabricated zero change.
        # 'hasHistory': False,
    },
}

# Guard against the silent-typo class. Every categorical liveability field is
# read with `.get(value, 5)`, so an unrecognised token does not raise — it scores
# a middling 5.0. For schools that is BETTER than the genuine worst band ('mixed'
# = 3), and for healthcare better than 'moderate' (4). So writing
# `'schools': 'poor'` — the obvious thing to write, and a valid token in the
# adjacent TRANSPORT_SCORE table — makes a borough look better than the data
# says, with no error raised anywhere.
#
# Validating at import means a bad token fails pytest and the SAM build rather
# than being served as a fact under an OGL attribution. The check is written to
# be *able* to go red; test_score.py feeds it a deliberately bad value and
# asserts it raises.
_CATEGORICAL_FIELDS = {
    # 'impact' added 2026-08-04 (audit finding 28). It was the one categorical
    # field this guard did not cover, and the most consequential to miss: it
    # feeds IMPACT_TO_QUIET.get(bd['impact'], 5.0), so a typo like 'sever' does
    # not raise — it silently upgrades a severe-noise borough to a middling 5.0
    # on the product's headline component. Every other categorical field was
    # already guarded precisely against that failure mode.
    'impact': IMPACT_TO_QUIET,
    # NOTE: 'schools' is vestigial. Boroughs still carry the retired Ofsted
    # vocabulary alongside 'p8', but the score has been driven by Progress 8
    # since v3.5, so this entry now validates a field nothing reads. Kept
    # because the values are still rendered in prose on the consumer site
    # (audit finding 35), which is a separate cleanup.
    'schools': SCHOOL_SCORE,
    'transport': TRANSPORT_SCORE,
    'healthcare': HEALTH_SCORE,
}


def validate_borough_vocabulary(cities):
    """Raise if any borough carries a categorical value its lookup table lacks.

    An ABSENT field is allowed: a city part-way through being sourced is a known,
    handled state (see get_live_score and live_resolution). A field that is
    present but unrecognised is not — it is always a mistake, and always one that
    scores 5.0 rather than failing.
    """
    problems = []
    for city_id, cfg in cities.items():
        for name, bd in cfg['boroughs'].items():
            for field, table in _CATEGORICAL_FIELDS.items():
                value = bd.get(field)
                if value is not None and value not in table:
                    problems.append(
                        f'{city_id}/{name}: {field}={value!r} is not one of {sorted(table)}'
                    )
    if problems:
        raise ValueError(
            'Borough data carries values no scoring table recognises. Each would '
            'silently score 5.0 instead of raising:\n  ' + '\n  '.join(problems)
        )


validate_borough_vocabulary(CITIES)


# NYC ZIP-to-borough mapping. ZIPs grouped per borough and flattened into a
# dict for O(1) lookup. Sourced from NYC OpenData ZCTA boundaries + USPS.
# Covers ~230 ZIPs across the 5 boroughs (residential + general use ZIPs;
# excludes some PO Box / single-building ZIPs that wouldn't be typed by a
# user). 9-digit ZIP+4 inputs are reduced to first 5 digits before lookup.
_NYC_ZIPS_BY_BOROUGH = {
    'Manhattan': [
        '10001',
        '10002',
        '10003',
        '10004',
        '10005',
        '10006',
        '10007',
        '10009',
        '10010',
        '10011',
        '10012',
        '10013',
        '10014',
        '10016',
        '10017',
        '10018',
        '10019',
        '10020',
        '10021',
        '10022',
        '10023',
        '10024',
        '10025',
        '10026',
        '10027',
        '10028',
        '10029',
        '10030',
        '10031',
        '10032',
        '10033',
        '10034',
        '10035',
        '10036',
        '10037',
        '10038',
        '10039',
        '10040',
        '10044',
        '10065',
        '10069',
        '10075',
        '10128',
        '10280',
        '10282',
    ],
    'Bronx': [
        '10451',
        '10452',
        '10453',
        '10454',
        '10455',
        '10456',
        '10457',
        '10458',
        '10459',
        '10460',
        '10461',
        '10462',
        '10463',
        '10464',
        '10465',
        '10466',
        '10467',
        '10468',
        '10469',
        '10470',
        '10471',
        '10472',
        '10473',
        '10474',
        '10475',
    ],
    'Staten Island': [
        '10301',
        '10302',
        '10303',
        '10304',
        '10305',
        '10306',
        '10307',
        '10308',
        '10309',
        '10310',
        '10311',
        '10312',
        '10314',
    ],
    'Brooklyn': [
        '11201',
        '11203',
        '11204',
        '11205',
        '11206',
        '11207',
        '11208',
        '11209',
        '11210',
        '11211',
        '11212',
        '11213',
        '11214',
        '11215',
        '11216',
        '11217',
        '11218',
        '11219',
        '11220',
        '11221',
        '11222',
        '11223',
        '11224',
        '11225',
        '11226',
        '11228',
        '11229',
        '11230',
        '11231',
        '11232',
        '11233',
        '11234',
        '11235',
        '11236',
        '11237',
        '11238',
        '11239',
        '11249',
    ],
    'Queens': [
        '11004',
        '11005',
        '11101',
        '11102',
        '11103',
        '11104',
        '11105',
        '11106',
        '11109',
        '11354',
        '11355',
        '11356',
        '11357',
        '11358',
        '11359',
        '11360',
        '11361',
        '11362',
        '11363',
        '11364',
        '11365',
        '11366',
        '11367',
        '11368',
        '11369',
        '11370',
        '11372',
        '11373',
        '11374',
        '11375',
        '11377',
        '11378',
        '11379',
        '11385',
        '11411',
        '11412',
        '11413',
        '11414',
        '11415',
        '11416',
        '11417',
        '11418',
        '11419',
        '11420',
        '11421',
        '11422',
        '11423',
        '11426',
        '11427',
        '11428',
        '11429',
        '11432',
        '11433',
        '11434',
        '11435',
        '11436',
        '11691',
        '11692',
        '11693',
        '11694',
        '11697',
    ],
}
NYC_ZIP_TO_BOROUGH = {zip5: borough for borough, zips in _NYC_ZIPS_BY_BOROUGH.items() for zip5 in zips}

US_ZIP_PATTERN = re.compile(r'^\d{5}(-\d{4})?$')

# ---------------------------------------------------------------------------
# Airports + flight paths for per-postcode quiet calculation.
#
# Sourced verbatim from the consumer site (`index.html`) which has been
# scoring 290+ neighbourhoods in production for months. Lat/lon stored as
# (lat, lon) tuples for clean Haversine calls. Coordinates in the consumer
# site are [lon, lat] (GeoJSON convention); we transpose at port time so the
# Python code can call haversine_km(lat1, lon1, lat2, lon2) directly.
# ---------------------------------------------------------------------------

AIRPORTS_LONDON = [
    {'code': 'LHR', 'name': 'Heathrow', 'lat': 51.4700, 'lon': -0.4543},
    {'code': 'LGW', 'name': 'Gatwick', 'lat': 51.1537, 'lon': -0.1821},
    {'code': 'LCY', 'name': 'London City', 'lat': 51.5053, 'lon': 0.0553},
    {'code': 'STN', 'name': 'Stansted', 'lat': 51.8860, 'lon': 0.2389},
    {'code': 'LTN', 'name': 'Luton', 'lat': 51.8747, 'lon': -0.3684},
]


# Rotary-noise sites, ported from index.html on 2026-08-03.
#
# The consumer site has scored these since the heliport term existed; this module
# never did, so site and API disagreed on `quiet` within 5 km of any of them -
# 14.1% of Greater London. That was the last remaining divergence between the two
# after the flight-path geometry was trimmed to match earlier the same day.
#
# `bands` is [within 3 km, within 5 km], added to noise_score. The tiers are
# derived, not chosen: sound energy sums logarithmically, so annual movements
# contribute 10*log10(N) - the same basis as Lden under END 2002/49/EC that
# METHODOLOGY 4.1 already cites. Battersea (12,000, a Wandsworth planning cap) and
# Elstree (12,367 rotary in 2016, Elstree Aerodrome Consultative Committee Guide)
# sit 0.13 dB apart and share the top tier. The two air-ambulance pads at ~1,600
# and ~800 movements sit ~8.75 dB lower, which is nearly two bands on the 4.1
# scale; they are dropped ONE, deliberately conservative - erring toward keeping a
# noise penalty rather than removing one.
#
# Denham has no published movement figure and its weight is an editorial
# assignment by analogy to Elstree, declared in METHODOLOGY 11. It is the weakest
# entry here and affects 1.50% of London.
#
# Kept identical to index.html by test_heliports_match_the_site.
HELIPORTS_LONDON = [
    {
        'code': 'BHL',
        'name': 'London Heliport (Battersea)',
        'lat': 51.47, 'lon': -0.178,
        'movementsPerYear': 12000,  # 12,000/yr
        'bands': (2, 1),
    },
    {
        'code': 'ELS',
        'name': 'Elstree Aerodrome',
        'lat': 51.6558, 'lon': -0.3258,
        'movementsPerYear': 12367,  # 12,367/yr
        'bands': (2, 1),
    },
    {
        'code': 'DEN',
        'name': 'Denham Aerodrome',
        'lat': 51.5789, 'lon': -0.5133,
        'movementsPerYear': None,  # None (not published, editorial - see METHODOLOGY 11)
        'bands': (2, 1),
    },
    {
        'code': 'HEMS',
        'name': 'Royal London Hospital Helipad',
        'lat': 51.5178, 'lon': -0.0593,
        'movementsPerYear': 1600,  # 1,600/yr
        'bands': (1, 0),
    },
    {
        'code': 'KING',
        'name': "King's College Hosp Helipad",
        'lat': 51.4688, 'lon': -0.0941,
        'movementsPerYear': 800,  # 800/yr
        'bands': (1, 0),
    },
]

AIRPORTS_NYC = [
    {'code': 'JFK', 'name': 'John F. Kennedy', 'lat': 40.6413, 'lon': -73.7781},
    {'code': 'LGA', 'name': 'LaGuardia', 'lat': 40.7769, 'lon': -73.8740},
    {'code': 'EWR', 'name': 'Newark Liberty', 'lat': 40.6895, 'lon': -74.1745},
    {'code': 'TEB', 'name': 'Teterboro', 'lat': 40.8501, 'lon': -74.0608},
]

# Flight path geometry: list of paths, each with a sequence of (lat, lon)
# waypoints. Distance to nearest waypoint is used as proxy for distance to
# the corridor, same approach as the consumer site.
# Trimmed to match index.html on 2026-08-03.
#
# METHODOLOGY records that on 2026-05-07 the London corridors were scoped to
# their noise-relevant final-approach / initial-departure portions only, audited
# against the DEFRA Lden raster by scripts/audit_flight_paths.py. That trim was
# applied to index.html and to the audit script. It was never applied HERE, so
# for three months the API carried 85 waypoints across 12 corridors while the
# site carried 50 across 10 - including two whole corridors, Approach N and
# Approach S, that the audit removed.
#
# More waypoints means more chances to sit near one, so the API scored noisier
# than the site wherever they differed. Measured over 7,239 live London
# postcodes: quiet disagreed for 2,503 of them, 34.6%, and the API was the
# noisier side in 100% of those. Correcting it raises quiet by 1.0 to 4.0 for
# exactly that 34.6%; nothing moves down, because the extra geometry could only
# ever add noise.
#
# This literal is now asserted identical to index.html's FLIGHT_PATHS by
# test_flight_path_geometry_matches_the_site, so the two cannot drift again.
# Regenerate BOTH, and re-run scripts/audit_flight_paths.py, if corridors change.
FLIGHT_PATHS_LONDON = [
    {
        'name': 'Lambourne Stack',
        'airport': 'LHR',
        'type': 'arrival',
        'coords': [
            (51.52, -0.18),
            (51.5175, -0.1917),
            (51.515, -0.2033),
            (51.5125, -0.215),
            (51.51, -0.2267),
            (51.5075, -0.2383),
            (51.505, -0.25),
            (51.503, -0.264),
            (51.501, -0.278),
            (51.499, -0.292),
            (51.497, -0.306),
            (51.495, -0.32),
            (51.493, -0.332),
            (51.491, -0.344),
            (51.489, -0.356),
            (51.487, -0.368),
            (51.485, -0.38),
            (51.4831, -0.392),
            (51.4813, -0.404),
            (51.4794, -0.416),
            (51.4775, -0.428),
        ],
    },
    {
        'name': 'Biggin Stack',
        'airport': 'LHR',
        'type': 'arrival',
        'coords': [
            (51.425, -0.22),
            (51.428, -0.232),
            (51.431, -0.244),
            (51.434, -0.256),
            (51.437, -0.268),
            (51.44, -0.28),
            (51.442, -0.292),
            (51.444, -0.304),
            (51.446, -0.316),
            (51.448, -0.328),
            (51.45, -0.34),
            (51.4525, -0.3525),
            (51.455, -0.365),
            (51.4575, -0.3775),
            (51.46, -0.39),
            (51.4615, -0.4027),
            (51.4629, -0.4153),
            (51.4644, -0.428),
        ],
    },
    {
        'name': 'Ockham Stack',
        'airport': 'LHR',
        'type': 'arrival',
        'coords': [
            (51.37, -0.435),
            (51.3775, -0.435),
            (51.385, -0.435),
            (51.3925, -0.435),
            (51.4, -0.435),
            (51.4067, -0.435),
            (51.4133, -0.435),
            (51.42, -0.435),
            (51.4267, -0.435),
            (51.4333, -0.435),
            (51.44, -0.435),
            (51.4481, -0.435),
            (51.4563, -0.435),
            (51.4644, -0.435),
        ],
    },
    {
        'name': 'Bovingdon Stack',
        'airport': 'LHR',
        'type': 'arrival',
        'coords': [
            (51.6, -0.49),
            (51.592, -0.488),
            (51.584, -0.486),
            (51.576, -0.484),
            (51.568, -0.482),
            (51.56, -0.48),
            (51.5525, -0.4775),
            (51.545, -0.475),
            (51.5375, -0.4725),
            (51.53, -0.47),
            (51.5217, -0.4667),
            (51.5133, -0.4633),
            (51.505, -0.46),
            (51.4981, -0.4575),
            (51.4913, -0.455),
            (51.4844, -0.4525),
            (51.4775, -0.45),
        ],
    },
    {
        'name': 'Dep West',
        'airport': 'LHR',
        'type': 'departure',
        'coords': [
            (51.4775, -0.489),
            (51.478, -0.5012),
            (51.4785, -0.5134),
            (51.479, -0.5256),
            (51.4795, -0.5378),
            (51.48, -0.55),
            (51.481, -0.564),
            (51.482, -0.578),
            (51.483, -0.592),
            (51.484, -0.606),
            (51.485, -0.62),
            (51.4858, -0.6333),
            (51.4867, -0.6467),
            (51.4875, -0.66),
            (51.4883, -0.6733),
            (51.4892, -0.6867),
            (51.49, -0.7),
        ],
    },
    {
        'name': 'Dep SE (Detling)',
        'airport': 'LHR',
        'type': 'departure',
        'coords': [
            (51.4775, -0.428),
            (51.4763, -0.415),
            (51.475, -0.402),
            (51.4737, -0.389),
            (51.4725, -0.376),
            (51.4712, -0.363),
            (51.47, -0.35),
            (51.4688, -0.3375),
            (51.4675, -0.325),
            (51.4663, -0.3125),
            (51.465, -0.3),
            (51.4637, -0.2875),
            (51.4625, -0.275),
            (51.4612, -0.2625),
            (51.46, -0.25),
            (51.4581, -0.2375),
            (51.4562, -0.225),
            (51.4544, -0.2125),
            (51.4525, -0.2),
            (51.4506, -0.1875),
            (51.4488, -0.175),
            (51.4469, -0.1625),
            (51.445, -0.15),
        ],
    },
    {
        'name': 'Dep NE (BPK)',
        'airport': 'LHR',
        'type': 'departure',
        'coords': [
            (51.4775, -0.428),
            (51.4796, -0.415),
            (51.4817, -0.402),
            (51.4838, -0.389),
            (51.4858, -0.376),
            (51.4879, -0.363),
            (51.49, -0.35),
            (51.4925, -0.3375),
            (51.495, -0.325),
            (51.4975, -0.3125),
            (51.5, -0.3),
            (51.5025, -0.2875),
            (51.505, -0.275),
            (51.5075, -0.2625),
            (51.51, -0.25),
            (51.5125, -0.2375),
            (51.515, -0.225),
            (51.5175, -0.2125),
            (51.52, -0.2),
            (51.5225, -0.1875),
            (51.525, -0.175),
            (51.5275, -0.1625),
            (51.53, -0.15),
        ],
    },
    {
        'name': 'Approach East',
        'airport': 'LCY',
        'type': 'arrival',
        'coords': [
            (51.48, 0.2),
            (51.4817, 0.19),
            (51.4833, 0.18),
            (51.485, 0.17),
            (51.486, 0.16),
            (51.487, 0.15),
            (51.488, 0.14),
            (51.4893, 0.13),
            (51.4907, 0.12),
            (51.492, 0.11),
            (51.4945, 0.1),
            (51.497, 0.09),
            (51.4995, 0.08),
            (51.502, 0.07),
            (51.5037, 0.0627),
            (51.5053, 0.0553),
        ],
    },
    {
        'name': 'Approach West',
        'airport': 'LCY',
        'type': 'arrival',
        'coords': [
            (51.52, -0.02),
            (51.5185, -0.0125),
            (51.517, -0.005),
            (51.515, 0.0025),
            (51.513, 0.01),
            (51.5115, 0.0175),
            (51.51, 0.025),
            (51.509, 0.0325),
            (51.508, 0.04),
            (51.5067, 0.0476),
            (51.5053, 0.0553),
        ],
    },
    {
        'name': 'Dep East',
        'airport': 'LCY',
        'type': 'departure',
        'coords': [
            (51.5053, 0.067),
            (51.5052, 0.0785),
            (51.505, 0.09),
            (51.5043, 0.1),
            (51.5037, 0.11),
            (51.503, 0.12),
            (51.5013, 0.1333),
            (51.4997, 0.1467),
            (51.498, 0.16),
            (51.496, 0.1725),
            (51.494, 0.185),
            (51.492, 0.1975),
            (51.49, 0.21),
        ],
    },
]

FLIGHT_PATHS_NYC = [
    {
        'name': 'JFK 31L Arrival',
        'airport': 'JFK',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (40.6, -73.6),
            (40.6025, -73.61),
            (40.605, -73.62),
            (40.6075, -73.63),
            (40.61, -73.64),
            (40.6125, -73.65),
            (40.615, -73.66),
            (40.6175, -73.67),
            (40.62, -73.68),
            (40.6225, -73.69),
            (40.625, -73.7),
            (40.6275, -73.71),
            (40.63, -73.72),
            (40.6325, -73.73),
            (40.635, -73.74),
            (40.6375, -73.75),
            (40.64, -73.76),
            (40.6407, -73.769),
            (40.6413, -73.7781),
        ],
    },
    {
        'name': 'JFK 13R Departure',
        'airport': 'JFK',
        'type': 'departure',
        'freq': 'high',
        'coords': [
            (40.6413, -73.7781),
            (40.6342, -73.7721),
            (40.6271, -73.766),
            (40.62, -73.76),
            (40.6133, -73.7533),
            (40.6067, -73.7467),
            (40.6, -73.74),
            (40.5933, -73.7333),
            (40.5867, -73.7267),
            (40.58, -73.72),
            (40.5733, -73.7133),
            (40.5667, -73.7067),
            (40.56, -73.7),
        ],
    },
    {
        'name': 'JFK 22L Arrival (ILS)',
        'airport': 'JFK',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [
            (40.7, -73.7),
            (40.6967, -73.7067),
            (40.6933, -73.7133),
            (40.69, -73.72),
            (40.6867, -73.7267),
            (40.6833, -73.7333),
            (40.68, -73.74),
            (40.6733, -73.7467),
            (40.6667, -73.7533),
            (40.66, -73.76),
            (40.6538, -73.766),
            (40.6475, -73.7721),
            (40.6413, -73.7781),
        ],
    },
    {
        'name': 'LGA 31 Arrival',
        'airport': 'LGA',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (40.72, -73.8),
            (40.7233, -73.8067),
            (40.7267, -73.8133),
            (40.73, -73.82),
            (40.7333, -73.8267),
            (40.7367, -73.8333),
            (40.74, -73.84),
            (40.7467, -73.8467),
            (40.7533, -73.8533),
            (40.76, -73.86),
            (40.7656, -73.8647),
            (40.7713, -73.8693),
            (40.7769, -73.874),
        ],
    },
    {
        'name': 'LGA 4 Departure',
        'airport': 'LGA',
        'type': 'departure',
        'freq': 'high',
        'coords': [
            (40.7769, -73.874),
            (40.7835, -73.872),
            (40.79, -73.87),
            (40.7967, -73.8667),
            (40.8033, -73.8633),
            (40.81, -73.86),
            (40.8167, -73.8567),
            (40.8233, -73.8533),
            (40.83, -73.85),
            (40.8375, -73.8475),
            (40.845, -73.845),
            (40.8525, -73.8425),
            (40.86, -73.84),
        ],
    },
    {
        'name': 'LGA Expressway Visual 31',
        'airport': 'LGA',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [
            (40.78, -73.95),
            (40.78, -73.94),
            (40.78, -73.93),
            (40.78, -73.92),
            (40.78, -73.91),
            (40.78, -73.9),
            (40.78, -73.89),
            (40.7784, -73.882),
            (40.7769, -73.874),
        ],
    },
    {
        'name': 'EWR 4R Arrival',
        'airport': 'EWR',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (40.62, -74.1),
            (40.6267, -74.1067),
            (40.6333, -74.1133),
            (40.64, -74.12),
            (40.6467, -74.1267),
            (40.6533, -74.1333),
            (40.66, -74.14),
            (40.6667, -74.1467),
            (40.6733, -74.1533),
            (40.68, -74.16),
            (40.6848, -74.1672),
            (40.6895, -74.1745),
        ],
    },
    {
        'name': 'EWR 22L Departure',
        'airport': 'EWR',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (40.6895, -74.1745),
            (40.6848, -74.1773),
            (40.68, -74.18),
            (40.6733, -74.1833),
            (40.6667, -74.1867),
            (40.66, -74.19),
            (40.6533, -74.1933),
            (40.6467, -74.1967),
            (40.64, -74.2),
            (40.6333, -74.2067),
            (40.6267, -74.2133),
            (40.62, -74.22),
        ],
    },
]

AIRPORTS_MANCHESTER = [
    {'code': 'MAN', 'name': 'Manchester', 'lat': 53.3537, 'lon': -2.2750},
]

# Manchester's two parallel runways (05L/23R, 05R/23L) share one alignment of
# roughly 052/232 degrees, so both approach corridors lie on a single axis
# through the airport. Southwesterlies prevail, so the 23 configuration -
# arrivals tracking in from the northeast - is the usual one, and it runs
# straight over Stockport. The 05 corridor points the other way into Cheshire,
# outside the city-region entirely, which is why Greater Manchester's noise
# burden concentrates on one side.
#
# THESE ARE GEOMETRY, NOT MEASUREMENTS. The waypoints are derived from runway
# alignment, so the `impact` bands in MANCHESTER_BOROUGHS are an estimate of the
# same kind London used before the DEFRA raster landed. CITY_PROVENANCE labels
# them as such in every response. Replacing them means sampling DEFRA Round 4
# for Greater Manchester - scripts/load_defra_raster.py takes --geotiff with a
# per-raster checkpoint, so it needs the export, not new code.
#
# RESAMPLED to a common 1 km interval on 2026-08-10, so corridor distances ARE
# now comparable between cities. This note used to say Manchester was ~5 km
# against London's ~1 km; the second half was wrong - London measured 3.34 km
# median, not 1 km - so the disparity was smaller than recorded, though real.
# Corridor distance is measured to the nearest waypoint, so a coarser polyline
# reads as further from the corridor and therefore QUIETER. Regenerate with the
# same 1 km densification if these are ever re-derived.
FLIGHT_PATHS_MANCHESTER = [
    {
        'name': '23 Approach',
        'airport': 'MAN',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (53.492, -1.9783),
            (53.4865, -1.9902),
            (53.4809, -2.002),
            (53.4754, -2.0139),
            (53.4698, -2.0257),
            (53.4643, -2.0376),
            (53.4588, -2.0495),
            (53.4533, -2.0614),
            (53.4477, -2.0732),
            (53.4422, -2.0851),
            (53.4367, -2.097),
            (53.4312, -2.1089),
            (53.4256, -2.1207),
            (53.4201, -2.1326),
            (53.4145, -2.1444),
            (53.409, -2.1563),
            (53.4035, -2.1682),
            (53.398, -2.1801),
            (53.3924, -2.1919),
            (53.3869, -2.2038),
            (53.3814, -2.2157),
            (53.3759, -2.2276),
            (53.3703, -2.2394),
            (53.3648, -2.2513),
            (53.3592, -2.2631),
            (53.3537, -2.275),
        ],
    },
    {
        'name': '05 Approach',
        'airport': 'MAN',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [
            (53.2707, -2.453),
            (53.2753, -2.4431),
            (53.2799, -2.4332),
            (53.2845, -2.4234),
            (53.2892, -2.4135),
            (53.2938, -2.4036),
            (53.2984, -2.3937),
            (53.3039, -2.3818),
            (53.3094, -2.3699),
            (53.315, -2.3581),
            (53.3205, -2.3462),
            (53.326, -2.3343),
            (53.3315, -2.3224),
            (53.3371, -2.3106),
            (53.3426, -2.2987),
            (53.3482, -2.2869),
            (53.3537, -2.275),
        ],
    },
]

AIRPORTS_WESTMIDLANDS = [
    {'code': 'BHX', 'name': 'Birmingham', 'lat': 52.4539, 'lon': -1.7480},
]

# Birmingham has ONE runway, 15/33, on a 148/328 alignment - verified against
# OurAirports runway data rather than recalled, the same source that confirmed
# Manchester's 051 heading matches the geometry already shipped here.
#
# GEOMETRY, NOT MEASUREMENT, exactly as Greater Manchester's is. Waypoints are
# resampled to 1 km on 2026-08-10, the same interval as every other city, so
# corridor distances are comparable. They were generated at ~4 km.
FLIGHT_PATHS_WESTMIDLANDS = [
    {
        'name': '33 Approach',
        'airport': 'BHX',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (52.6142, -1.9267),
            (52.6068, -1.9184),
            (52.5994, -1.9102),
            (52.5919, -1.9019),
            (52.5845, -1.8936),
            (52.5771, -1.8853),
            (52.5696, -1.8771),
            (52.5622, -1.8688),
            (52.5548, -1.8605),
            (52.5474, -1.8522),
            (52.54, -1.8439),
            (52.5325, -1.8356),
            (52.5251, -1.8273),
            (52.5177, -1.819),
            (52.5102, -1.8108),
            (52.5027, -1.8025),
            (52.4953, -1.7942),
            (52.4884, -1.7865),
            (52.4815, -1.7788),
            (52.4746, -1.7711),
            (52.4677, -1.7634),
            (52.4608, -1.7557),
            (52.4539, -1.748),
        ],
    },
    {
        'name': '15 Approach',
        'airport': 'BHX',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [
            (52.2943, -1.5703),
            (52.3017, -1.5786),
            (52.3092, -1.5869),
            (52.3166, -1.5951),
            (52.324, -1.6034),
            (52.33, -1.61),
            (52.3359, -1.6166),
            (52.3419, -1.6233),
            (52.3478, -1.6299),
            (52.3538, -1.6365),
            (52.3612, -1.6448),
            (52.3687, -1.6531),
            (52.3761, -1.6614),
            (52.3835, -1.6697),
            (52.3909, -1.678),
            (52.3984, -1.6863),
            (52.4058, -1.6945),
            (52.4132, -1.7028),
            (52.42, -1.7103),
            (52.4268, -1.7179),
            (52.4335, -1.7254),
            (52.4403, -1.7329),
            (52.4471, -1.7405),
            (52.4539, -1.748),
        ],
    },
]

AIRPORTS_WESTYORKSHIRE = [
    {'code': 'LBA', 'name': 'Leeds Bradford', 'lat': 53.8659, 'lon': -1.6606},
]

# Leeds Bradford runway 14/32, from OurAirports. Geometry, not measurement.
FLIGHT_PATHS_WESTYORKSHIRE = [
    {
        'name': '32 Approach',
        'airport': 'LBA',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (54.0067, -1.8764),
            (54.0, -1.8662),
            (53.9933, -1.8559),
            (53.9867, -1.8457),
            (53.98, -1.8355),
            (53.9733, -1.8253),
            (53.9667, -1.8151),
            (53.9601, -1.8049),
            (53.9534, -1.7947),
            (53.9467, -1.7845),
            (53.94, -1.7742),
            (53.9334, -1.764),
            (53.9267, -1.7538),
            (53.92, -1.7436),
            (53.9134, -1.7334),
            (53.9068, -1.7231),
            (53.9001, -1.7129),
            (53.8944, -1.7042),
            (53.8887, -1.6955),
            (53.883, -1.6867),
            (53.8773, -1.678),
            (53.8716, -1.6693),
            (53.8659, -1.6606),
        ],
    },
    {
        'name': '14 Approach',
        'airport': 'LBA',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [
            (53.7251, -1.4448),
            (53.7304, -1.453),
            (53.7358, -1.4611),
            (53.7411, -1.4693),
            (53.7465, -1.4774),
            (53.7518, -1.4856),
            (53.7585, -1.4958),
            (53.7651, -1.5061),
            (53.7717, -1.5163),
            (53.7784, -1.5265),
            (53.7851, -1.5367),
            (53.7918, -1.5469),
            (53.7984, -1.5571),
            (53.8051, -1.5673),
            (53.8118, -1.5775),
            (53.8184, -1.5877),
            (53.825, -1.598),
            (53.8317, -1.6082),
            (53.8374, -1.6169),
            (53.8431, -1.6257),
            (53.8488, -1.6344),
            (53.8545, -1.6431),
            (53.8602, -1.6519),
            (53.8659, -1.6606),
        ],
    },
]

AIRPORTS_MERSEYSIDE = [
    {'code': 'LPL', 'name': 'Liverpool John Lennon', 'lat': 53.3349, 'lon': -2.8496},
]

# Liverpool John Lennon runway 09/27, from OurAirports. Geometry, not measurement.
FLIGHT_PATHS_MERSEYSIDE = [
    {
        'name': '27 Approach',
        'airport': 'LPL',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (53.319, -3.1669),
            (53.3197, -3.1519),
            (53.3204, -3.1369),
            (53.3211, -3.1219),
            (53.3218, -3.1069),
            (53.3225, -3.0919),
            (53.3232, -3.0769),
            (53.3239, -3.0619),
            (53.3246, -3.0469),
            (53.3253, -3.0319),
            (53.3259, -3.0169),
            (53.3266, -3.0019),
            (53.3273, -2.9869),
            (53.328, -2.9719),
            (53.3287, -2.9569),
            (53.3294, -2.9419),
            (53.3301, -2.9269),
            (53.3309, -2.914),
            (53.3317, -2.9011),
            (53.3325, -2.8883),
            (53.3333, -2.8754),
            (53.3341, -2.8625),
            (53.3349, -2.8496),
        ],
    },
    {
        'name': '09 Approach',
        'airport': 'LPL',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [
            (53.3482, -2.5327),
            (53.3475, -2.5477),
            (53.3469, -2.5627),
            (53.3462, -2.5777),
            (53.3455, -2.5927),
            (53.3448, -2.6077),
            (53.3441, -2.6227),
            (53.3434, -2.6377),
            (53.3427, -2.6527),
            (53.342, -2.6677),
            (53.3413, -2.6827),
            (53.3406, -2.6977),
            (53.3399, -2.7127),
            (53.3392, -2.7277),
            (53.3385, -2.7427),
            (53.3379, -2.7577),
            (53.3372, -2.7727),
            (53.3368, -2.7855),
            (53.3364, -2.7983),
            (53.3361, -2.8112),
            (53.3357, -2.824),
            (53.3353, -2.8368),
            (53.3349, -2.8496),
        ],
    },
]

AIRPORTS_TYNEANDWEAR = [
    {'code': 'NCL', 'name': 'Newcastle', 'lat': 55.0380, 'lon': -1.6896},
]

# Newcastle runway 07/25, from OurAirports. Geometry, not measurement.
FLIGHT_PATHS_TYNEANDWEAR = [
    {
        'name': '25 Approach',
        'airport': 'NCL',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (54.9578, -1.9907),
            (54.9608, -1.9793),
            (54.9639, -1.9679),
            (54.9669, -1.9566),
            (54.97, -1.9452),
            (54.973, -1.9338),
            (54.9768, -1.9196),
            (54.9806, -1.9054),
            (54.9843, -1.8912),
            (54.9881, -1.877),
            (54.9919, -1.8628),
            (54.9956, -1.8485),
            (54.9994, -1.8343),
            (55.0032, -1.8201),
            (55.0062, -1.8087),
            (55.0093, -1.7973),
            (55.0123, -1.786),
            (55.0154, -1.7746),
            (55.0184, -1.7632),
            (55.0217, -1.7509),
            (55.0249, -1.7387),
            (55.0282, -1.7264),
            (55.0315, -1.7141),
            (55.0347, -1.7019),
            (55.038, -1.6896),
        ],
    },
    {
        'name': '07 Approach',
        'airport': 'NCL',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [
            (55.118, -1.3889),
            (55.1142, -1.4031),
            (55.1104, -1.4173),
            (55.1066, -1.4316),
            (55.1028, -1.4458),
            (55.099, -1.46),
            (55.0953, -1.4743),
            (55.0915, -1.4885),
            (55.0877, -1.5027),
            (55.0839, -1.5169),
            (55.0802, -1.5311),
            (55.0764, -1.5453),
            (55.0726, -1.5595),
            (55.0688, -1.5737),
            (55.065, -1.588),
            (55.0612, -1.6022),
            (55.0574, -1.6164),
            (55.0542, -1.6286),
            (55.0509, -1.6408),
            (55.0477, -1.653),
            (55.0445, -1.6652),
            (55.0412, -1.6774),
            (55.038, -1.6896),
        ],
    },
]

AIRPORTS_BRISTOL = [
    {'code': 'BRS', 'name': 'Bristol', 'lat': 51.3823, 'lon': -2.7165},
]

# Bristol runway 09/27, from OurAirports. Geometry, not measurement.
FLIGHT_PATHS_BRISTOL = [
    {
        'name': '27 Approach',
        'airport': 'BRS',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (51.3711, -3.0208),
            (51.3717, -3.0065),
            (51.3722, -2.9921),
            (51.3727, -2.9777),
            (51.3733, -2.9634),
            (51.3739, -2.949),
            (51.3744, -2.9346),
            (51.3749, -2.9203),
            (51.3755, -2.9059),
            (51.376, -2.8915),
            (51.3766, -2.8771),
            (51.3772, -2.8628),
            (51.3777, -2.8484),
            (51.3782, -2.834),
            (51.3788, -2.8197),
            (51.3794, -2.8053),
            (51.3799, -2.791),
            (51.3803, -2.7786),
            (51.3807, -2.7662),
            (51.3811, -2.7538),
            (51.3815, -2.7413),
            (51.3819, -2.7289),
            (51.3823, -2.7165),
        ],
    },
    {
        'name': '09 Approach',
        'airport': 'BRS',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [
            (51.3942, -2.4173),
            (51.3937, -2.4317),
            (51.3931, -2.4461),
            (51.3925, -2.4604),
            (51.392, -2.4748),
            (51.3915, -2.4892),
            (51.3909, -2.5036),
            (51.3903, -2.5179),
            (51.3898, -2.5323),
            (51.3893, -2.5467),
            (51.3887, -2.561),
            (51.3881, -2.5754),
            (51.3876, -2.5897),
            (51.3871, -2.6041),
            (51.3865, -2.6185),
            (51.3859, -2.6328),
            (51.3854, -2.6472),
            (51.3848, -2.6611),
            (51.3842, -2.6749),
            (51.3835, -2.6888),
            (51.3829, -2.7026),
            (51.3823, -2.7165),
        ],
    },
]

AIRPORTS_CARDIFF = [
    {'code': 'CWL', 'name': 'Cardiff', 'lat': 51.3967, 'lon': -3.3433},
]

# Cardiff runway 12/30, from OurAirports. Geometry, not measurement.
FLIGHT_PATHS_CARDIFF = [
    {
        'name': '30 Approach',
        'airport': 'CWL',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (51.4827, -3.6156),
            (51.4787, -3.6028),
            (51.4746, -3.5899),
            (51.4706, -3.577),
            (51.4665, -3.5642),
            (51.4624, -3.5514),
            (51.4584, -3.5385),
            (51.4543, -3.5256),
            (51.4502, -3.5128),
            (51.4462, -3.5),
            (51.4421, -3.4871),
            (51.438, -3.4742),
            (51.434, -3.4614),
            (51.4299, -3.4486),
            (51.4258, -3.4357),
            (51.4218, -3.4229),
            (51.4177, -3.4101),
            (51.4142, -3.399),
            (51.4107, -3.3878),
            (51.4072, -3.3767),
            (51.4037, -3.3656),
            (51.4002, -3.3544),
            (51.3967, -3.3433),
        ],
    },
    {
        'name': '12 Approach',
        'airport': 'CWL',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [
            (51.3106, -3.0711),
            (51.3138, -3.0814),
            (51.3171, -3.0917),
            (51.3203, -3.1019),
            (51.3236, -3.1122),
            (51.3268, -3.1225),
            (51.3301, -3.1328),
            (51.3333, -3.1431),
            (51.3366, -3.1533),
            (51.3398, -3.1636),
            (51.3431, -3.1739),
            (51.3471, -3.1867),
            (51.3512, -3.1996),
            (51.3552, -3.2124),
            (51.3593, -3.2252),
            (51.3626, -3.2355),
            (51.3658, -3.2458),
            (51.3691, -3.256),
            (51.3723, -3.2663),
            (51.3756, -3.2766),
            (51.3791, -3.2877),
            (51.3826, -3.2988),
            (51.3862, -3.31),
            (51.3897, -3.3211),
            (51.3932, -3.3322),
            (51.3967, -3.3433),
        ],
    },
]


AIRPORTS_NOTTINGHAM = [
    {'code': 'EMA', 'name': 'East Midlands', 'lat': 52.8311, 'lon': -1.3281},
]

# East Midlands runway 09/27, from OurAirports. Geometry, not measurement.
# The airport sits in Leicestershire, outside the city region.
FLIGHT_PATHS_NOTTINGHAM = [
    {
        'name': '27 Approach',
        'airport': 'EMA',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (52.8251, -1.6468),
            (52.8254, -1.632),
            (52.8256, -1.6171),
            (52.8259, -1.6022),
            (52.8262, -1.5874),
            (52.8265, -1.5725),
            (52.8268, -1.5576),
            (52.827, -1.5428),
            (52.8273, -1.5279),
            (52.8276, -1.5131),
            (52.8278, -1.4982),
            (52.8281, -1.4833),
            (52.8284, -1.4685),
            (52.8287, -1.4536),
            (52.829, -1.4387),
            (52.8292, -1.4239),
            (52.8295, -1.409),
            (52.8298, -1.3955),
            (52.83, -1.382),
            (52.8303, -1.3685),
            (52.8306, -1.3551),
            (52.8308, -1.3416),
            (52.8311, -1.3281),
        ],
    },
    {
        'name': '09 Approach',
        'airport': 'EMA',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [
            (52.837, -1.0094),
            (52.8367, -1.0243),
            (52.8364, -1.0392),
            (52.8361, -1.054),
            (52.8358, -1.0689),
            (52.8355, -1.0837),
            (52.8353, -1.0986),
            (52.835, -1.1135),
            (52.8347, -1.1283),
            (52.8344, -1.1432),
            (52.8341, -1.1581),
            (52.8339, -1.1729),
            (52.8336, -1.1878),
            (52.8333, -1.2026),
            (52.8331, -1.2175),
            (52.8328, -1.2324),
            (52.8325, -1.2472),
            (52.8323, -1.2607),
            (52.832, -1.2742),
            (52.8318, -1.2877),
            (52.8316, -1.3011),
            (52.8313, -1.3146),
            (52.8311, -1.3281),
        ],
    },
]

CITY_GEOMETRY = {
    'london': {
        'airports': AIRPORTS_LONDON,
        'paths': FLIGHT_PATHS_LONDON,
        'heliports': HELIPORTS_LONDON,
        'major_airport': 'LHR',
        'secondary_airport': None,
    },
    # New York gets an explicit empty list rather than a missing key, so a future
    # city that genuinely has rotary sites fails loudly on a typo instead of
    # silently scoring as though it has none.
    'nyc': {
        'airports': AIRPORTS_NYC,
        'paths': FLIGHT_PATHS_NYC,
        'heliports': [],
        'major_airport': 'JFK',
        'secondary_airport': 'LGA',
    },
    'westmidlands': {
        'airports': AIRPORTS_WESTMIDLANDS,
        'paths': FLIGHT_PATHS_WESTMIDLANDS,
        # Explicit empty list rather than a missing key, per the NYC note above.
        'heliports': [],
        'major_airport': 'BHX',
        # One airport, so no secondary. Note the airport term is DISTANCE-ONLY
        # and calibrated on Heathrow: BHX handles a fraction of LHR's movements,
        # so the ladder reaches further than this airport really does and the
        # result is PESSIMISTIC. That is the survivable direction - the DEFRA
        # raster incident is on record for erring the other way. Core Cities
        # finding 7 covers the same overstatement for Manchester.
        'secondary_airport': None,
    },
    'westyorkshire': {
        'airports': AIRPORTS_WESTYORKSHIRE,
        'paths': FLIGHT_PATHS_WESTYORKSHIRE,
        'heliports': [],
        'major_airport': 'LBA',
        # Distance ladder calibrated on Heathrow, so it reaches further than
        # this airport does: the estimate is PESSIMISTIC. See the West Midlands
        # note above and Core Cities finding 7.
        'secondary_airport': None,
    },
    # South Yorkshire has NO operating commercial airport: Doncaster Sheffield is listed
    # `type=closed` by OurAirports, commercial flights having ceased in 2022. An
    # empty airport list is a MEASURED ABSENCE of a noise source, not a missing
    # measurement, and CITY_PROVENANCE says which.
    'southyorkshire': {
        'airports': [],
        'paths': [],
        'heliports': [],
        'major_airport': None,
        'secondary_airport': None,
    },
    'merseyside': {
        'airports': AIRPORTS_MERSEYSIDE,
        'paths': FLIGHT_PATHS_MERSEYSIDE,
        'heliports': [],
        'major_airport': 'LPL',
        # Distance ladder calibrated on Heathrow, so it reaches further than
        # this airport does: the estimate is PESSIMISTIC. See the West Midlands
        # note above and Core Cities finding 7.
        'secondary_airport': None,
    },
    'tyneandwear': {
        'airports': AIRPORTS_TYNEANDWEAR,
        'paths': FLIGHT_PATHS_TYNEANDWEAR,
        'heliports': [],
        'major_airport': 'NCL',
        # Distance ladder calibrated on Heathrow, so it reaches further than
        # this airport does: the estimate is PESSIMISTIC. See the West Midlands
        # note above and Core Cities finding 7.
        'secondary_airport': None,
    },
    'bristol': {
        'airports': AIRPORTS_BRISTOL,
        'paths': FLIGHT_PATHS_BRISTOL,
        'heliports': [],
        'major_airport': 'BRS',
        # Distance ladder calibrated on Heathrow, so it reaches further than
        # this airport does: the estimate is PESSIMISTIC. See the West Midlands
        # note above and Core Cities finding 7.
        'secondary_airport': None,
    },
    'cardiff': {
        'airports': AIRPORTS_CARDIFF,
        'paths': FLIGHT_PATHS_CARDIFF,
        'heliports': [],
        'major_airport': 'CWL',
        # Distance ladder calibrated on Heathrow, so it reaches further than
        # this airport does: the estimate is PESSIMISTIC. See the West Midlands
        # note above and Core Cities finding 7.
        'secondary_airport': None,
    },
    'nottingham': {
        'airports': AIRPORTS_NOTTINGHAM,
        'paths': FLIGHT_PATHS_NOTTINGHAM,
        'heliports': [],
        # East Midlands Airport is OUTSIDE the city region, in Leicestershire,
        # which is why no Nottingham borough is nearer than 16 km and none is
        # banded above low-moderate. Named here so a future reader does not
        # "correct" an airport that looks misplaced.
        'major_airport': 'EMA',
        'secondary_airport': None,
    },
    'manchester': {
        'airports': AIRPORTS_MANCHESTER,
        'paths': FLIGHT_PATHS_MANCHESTER,
        # Barton (City Airport Manchester) exists but has no scheduled rotary
        # traffic of the kind the London heliport term models, so an explicit
        # empty list rather than a missing key - see the NYC note above.
        'heliports': [],
        'major_airport': 'MAN',
        # One airport, so no secondary. The airport term takes min(distance)
        # across the list, which for a single-airport city is simply distance
        # to MAN. Note that term is DISTANCE-ONLY and calibrated on Heathrow:
        # MAN handles roughly a third of LHR's movements, so the same ladder
        # overstates its reach. Tracked as Core Cities finding 7.
        'secondary_airport': None,
    },
}

# NYC ZIP-to-centroid lookup. Sourced from index.html NYC_AREA_MAP, first
# neighbourhood per ZIP used as a representative centroid. Where multiple
# neighbourhoods share a ZIP (e.g. 10012 SoHo / NoHo / Nolita), we keep the
# first encountered and accept ~1km of within-ZIP imprecision.
# Coverage: ~110 ZIPs across the 5 NYC boroughs. ZIPs in NYC_ZIP_TO_BOROUGH
# that aren't here fall back to borough-aggregate scoring.
NYC_ZIP_CENTROIDS = {
    # Queens
    '11102': (40.7724, -73.9234),
    '11101': (40.7443, -73.9249),
    '11354': (40.7596, -73.8303),
    '11372': (40.7465, -73.8915),
    '11375': (40.7185, -73.8448),
    '11432': (40.7028, -73.7925),
    '11104': (40.7434, -73.9126),
    '11377': (40.7454, -73.9028),
    '11373': (40.7360, -73.8780),
    '11368': (40.7465, -73.8623),
    '11374': (40.7263, -73.8616),
    '11415': (40.7084, -73.8272),
    '11361': (40.7621, -73.7716),
    '11365': (40.7348, -73.7911),
    '11357': (40.7927, -73.8085),
    '11356': (40.7862, -73.8398),
    '11385': (40.7043, -73.8963),
    '11378': (40.7233, -73.9126),
    '11379': (40.7176, -73.8811),
    '11414': (40.6571, -73.8430),
    '11416': (40.6844, -73.8464),
    '11420': (40.6748, -73.8120),
    '11418': (40.6995, -73.8313),
    '11421': (40.6888, -73.8564),
    '11435': (40.7088, -73.8151),
    '11362': (40.7663, -73.7498),
    '11363': (40.7637, -73.7327),
    '11693': (40.5864, -73.8158),
    '11691': (40.6027, -73.7551),
    '11423': (40.7118, -73.7617),
    '11412': (40.6896, -73.7610),
    '11422': (40.6605, -73.7358),
    '11105': (40.7780, -73.9112),
    # Brooklyn
    '11211': (40.7128, -73.9530),
    '11215': (40.6710, -73.9777),
    '11201': (40.7033, -73.9887),
    '11221': (40.6905, -73.9252),
    '11231': (40.6734, -73.9999),
    '11216': (40.6810, -73.9418),
    '11213': (40.6694, -73.9340),
    '11238': (40.6773, -73.9650),
    '11217': (40.6848, -73.9835),
    '11205': (40.6897, -73.9625),
    '11222': (40.7274, -73.9510),
    '11209': (40.6340, -74.0286),
    '11220': (40.6454, -74.0104),
    '11214': (40.6025, -73.9939),
    '11219': (40.6341, -73.9916),
    '11226': (40.6453, -73.9597),
    '11218': (40.6385, -73.9722),
    '11235': (40.5912, -73.9445),
    '11224': (40.5755, -73.9707),
    '11234': (40.6177, -73.9210),
    '11236': (40.6388, -73.8968),
    '11207': (40.6594, -73.8827),
    '11225': (40.6592, -73.9518),
    '11230': (40.6209, -73.9600),
    '11228': (40.6215, -74.0093),
    # Manhattan
    '10027': (40.8116, -73.9465),
    '10021': (40.7694, -73.9595),
    '10011': (40.7418, -74.0002),
    '10014': (40.7336, -74.0027),
    '10012': (40.7233, -73.9985),
    '10013': (40.7163, -74.0086),
    '10003': (40.7265, -73.9815),
    '10002': (40.7157, -73.9863),
    '10019': (40.7644, -73.9835),
    '10024': (40.7870, -73.9754),
    '10033': (40.8472, -73.9377),
    '10034': (40.8677, -73.9212),
    '10005': (40.7075, -74.0089),
    '10280': (40.7112, -74.0155),
    '10010': (40.7367, -73.9844),
    '10016': (40.7416, -73.9783),
    '10025': (40.8100, -73.9626),
    '10031': (40.8253, -73.9476),
    '10029': (40.7918, -73.9432),
    '10028': (40.7765, -73.9504),
    '10001': (40.7542, -74.0005),
    # Bronx
    '10471': (40.8968, -73.9094),
    '10454': (40.8057, -73.9176),
    '10458': (40.8615, -73.8885),
    '10461': (40.8527, -73.8332),
    '10451': (40.8202, -73.9231),
    '10474': (40.8093, -73.8817),
    '10452': (40.8366, -73.9271),
    '10453': (40.8535, -73.9199),
    '10463': (40.8788, -73.9037),
    '10468': (40.8712, -73.8886),
    '10470': (40.8959, -73.8674),
    '10466': (40.8938, -73.8551),
    '10475': (40.8743, -73.8273),
    '10465': (40.8228, -73.8209),
    '10462': (40.8524, -73.8546),
    '10473': (40.8265, -73.8568),
    '10457': (40.8468, -73.9006),
    '10464': (40.8469, -73.7868),
    # Staten Island
    '10301': (40.6433, -74.0764),
    '10314': (40.6016, -74.1132),
    '10306': (40.5734, -74.1162),
    '10308': (40.5545, -74.1516),
    '10307': (40.5078, -74.2382),
    '10304': (40.6266, -74.0794),
    '10302': (40.6343, -74.1361),
    '10310': (40.6270, -74.1165),
    '10312': (40.5450, -74.1644),
    '10305': (40.6028, -74.0841),
}

# DynamoDB table for v3.1 DEFRA Lden raster samples. When populated by the
# offline data-loader script (see scripts/load_defra_raster.py, to add),
# the calc_score path checks this table first for postcode-level Lden values
# sampled directly from DEFRA's GeoTIFF. If the DynamoDB lookup misses or the
# table isn't yet populated, falls back to v3.0 Haversine. This means the
# Lambda code path is forward-compatible: it works with or without the
# raster data loaded, and silently upgrades when the data lands.
NOISE_RASTER_TABLE = os.environ.get('NOISE_RASTER_TABLE', '')

# DynamoDB table for the ONS NSPL postcode index (postcode -> LAD + lat/lon,
# Open Government Licence v3.0). Populated offline by scripts/load_nspl.py.
# When present, lookup_postcode resolves UK postcodes from this table in a
# few milliseconds instead of calling postcodes.io over the network — which
# matters because postcodes.io is a free community service and a customer
# backfilling 100k distinct postcodes is not fair use of it. postcodes.io
# remains the fallback for anything the table cannot answer: postcodes
# introduced after this table's NSPL vintage, rows the loader excluded, and
# terminated postcodes when the caller has not opted in.
# Forward-compatible, same contract as NOISE_RASTER_TABLE: an unset env var
# or a missing item is a silent no-op and the postcodes.io path serves the
# request exactly as it did before this table existed.
POSTCODE_TABLE = os.environ.get('POSTCODE_TABLE', '')

# Set the first time the local NSPL tier actually answers a lookup in this
# container. Drives the `sources` attribution — see _postcode_source_line.
# Plain module global, no lock: worst case under the batch worker pool is
# two threads writing True concurrently, which is idempotent.
_LOCAL_POSTCODE_SERVED = False


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two (lat, lon) points in kilometres.
    Standard Haversine formula; used for airport and flight-path proximity."""
    r = 6371.0
    p = math.pi / 180.0
    a = (
        0.5
        - math.cos((lat2 - lat1) * p) / 2
        + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    )
    return r * 2 * math.asin(math.sqrt(a))


_raster_cache_get, _raster_cache_put = _make_lru(2048)

# Module-level DynamoDB client, shared by the raster lookup and the NSPL
# postcode lookup. Hoisted out of _lookup_lden_raster (audit M-N1):
# boto3.client construction is ~50ms per call on cold start; with the LRU
# above it would only re-fire on cache misses, but those are exactly the
# slowest path. Lazy-imported so this module loads cleanly in test
# environments without boto3.
_DDB_CLIENT = None
_DDB_IMPORT_FAILED = False
# Serialises construction (audit L2). /v1/score/batch launches
# BATCH_PARALLELISM workers that now all reach _get_ddb_client() on a cold
# container with no preceding I/O to stagger them — the NSPL lookup is the
# first thing each worker does, unlike the raster lookup which sat behind a
# ~200ms postcodes.io round trip. boto3's module-level default session is
# documented as not thread-safe, so building the client under a lock (with
# a double-check so the warm path stays lock-free) is the cheap fix.
_DDB_CLIENT_LOCK = threading.Lock()

# Explicit timeouts (audit L3). botocore defaults are 60s connect and 60s
# read, inside a function whose Lambda Timeout is 28s (backend/template.yaml).
# A DynamoDB stall or a throttle storm — expected while a fresh
# PAY_PER_REQUEST table ramps under the loader's write workers — would
# therefore block past the function timeout, so API Gateway returns 502 and
# the `except (BotoCoreError, ClientError)` degrade-to-None never runs. That
# breaks the whole feature's promise that a DDB failure quietly defers to
# postcodes.io, and for a batch it fails all 100 queries at once.
#
# 1s connect / 2s read are generous for same-region DynamoDB (single-digit
# ms p99); total_max_attempts=2 (initial + one retry) is stated as a total so
# the bound is unambiguous across botocore retry modes. Worst case is
# 2 x (1 + 2) = 6s plus a sub-second backoff, comfortably inside 28s even
# stacked with the 5s postcodes.io fallback that follows a DDB failure.
#
# Shared with the pre-existing raster path, deliberately: that path makes the
# same degrade-to-None promise, so a bounded failure is strictly better for
# it too — it fails fast to the Haversine tier instead of hanging the request.
#
# WHY ONLY 2 ATTEMPTS, when botocore's DynamoDB default is 10. This is a
# deliberate reduction and it is the binding constraint, so do not raise it
# without redoing this arithmetic. The two DDB lookups are SEQUENTIAL on a
# UK postcode request — postcode resolution first, then the raster sample —
# and a postcode failure is followed by the 5s postcodes.io fallback. Worst
# case at 2 attempts, with botocore standard-mode backoff:
#     postcode  2 x (1s connect + 2s read) + ~2s backoff  =  ~8s
#     raster    2 x (1s connect + 2s read) + ~2s backoff  =  ~8s
#     postcodes.io fallback                               =   5s
#                                                          -----
#                                                          ~21s   (limit 28s)
# A third attempt on the raster leg alone adds 3s of timeout plus up to 4s
# of backoff and takes the stack to ~28s — i.e. straight into the Lambda
# timeout, which turns a graceful degrade into a 502 for the whole request
# (or, on /v1/score/batch, for all 100 queries). Fewer, faster attempts is
# genuinely the safer trade here.
#
# The residual risk that buys is real and is handled elsewhere rather than
# by retrying harder: a throttle that outlives 2 attempts drops the raster
# tier and silently changes the score. That path now emits a structured
# [SCORE_RASTER_DEGRADED] warning (see _lookup_lden_raster) precisely so the
# degradation is alarm-able instead of invisible. If those alarms ever fire
# in volume, the fix is a SECOND client for the raster leg with its own
# larger attempt budget — not a bigger shared budget, which would blow the
# stacked wall clock above.
_DDB_TIMEOUT_CONFIG = {
    'connect_timeout': 1,
    'read_timeout': 2,
    'retries': {'total_max_attempts': 2, 'mode': 'standard'},
}


def _get_ddb_client():
    """Return the shared DynamoDB client, or None if it cannot be built.

    Never raises: callers treat None as "no table available" and fall back.
    """
    global _DDB_CLIENT, _DDB_IMPORT_FAILED
    if _DDB_IMPORT_FAILED:
        return None
    if _DDB_CLIENT is not None:
        return _DDB_CLIENT
    with _DDB_CLIENT_LOCK:
        # Re-check under the lock, every waiting worker arrives here having
        # already lost the fast-path check above.
        if _DDB_IMPORT_FAILED:
            return None
        if _DDB_CLIENT is not None:
            return _DDB_CLIENT
        try:
            import boto3
            from botocore.config import Config
        except ImportError:
            _DDB_IMPORT_FAILED = True
            return None
        try:
            _DDB_CLIENT = boto3.client(
                'dynamodb',
                region_name=os.environ.get('AWS_REGION', 'eu-west-2'),
                config=Config(**_DDB_TIMEOUT_CONFIG),
            )
        except Exception as exc:  # noqa: BLE001 — construction must not escape
            # NoRegionError, a malformed endpoint override, a broken shared
            # config file: all raise here, outside any botocore except clause
            # the lookup functions have. Not latched like the ImportError
            # above, so a transient environment problem can recover on the
            # next request rather than disabling both tables for the life of
            # the container.
            logger.warning('DynamoDB client construction failed: %s', exc)
            return None
    return _DDB_CLIENT


# --- Raster tier quarantined 2026-08-03 -------------------------------------
# READ THIS BEFORE HUNTING FOR A LOADER BUG. There isn't one. An earlier version
# of this comment claimed the table held values that "cannot be right" and blamed
# a CRS mismatch. That was wrong, and it was concluded from a sample of eight
# postcodes. Verified against data/defra_lden_2022.tif directly:
#
#   * the raster is the genuine DEFRA aircraft Lden map — EPSG:27700, 10 m
#     resolution, values to 88.9 dB, 34,414 distinct values, and its loudest
#     cells sit exactly on Heathrow's two runway centrelines and London City;
#   * sampling it at correctly projected coordinates returns 58.2 for TW61AP,
#     identical to the stored value. The projection is correct and the stored
#     numbers are faithful samples;
#   * the 35.0 values are a deliberate nodata fill (see _RASTER_NODATA_FILL),
#     not corruption.
#
# The defect is COVERAGE, not correctness. Measured over 22,622 live London
# postcodes: 89.5% fall outside DEFRA's aircraft contours entirely, because those
# contours are localised lobes — the raster carries data for 6.2% of its own
# grid. Filling all of that as 35.0 dB rendered "not measured" as "perfectly
# quiet" and put 98% of London on a single quiet value of 10.0. A component that
# is 10.0 for 98% of the city cannot support the claim that Lden varies 10-15 dB
# within a borough, which is the product's headline differentiator.
#
# Bypassing drops the chain to its Haversine tier, which discriminates properly
# — Heathrow 0.0, Hounslow 1.0, Finsbury Park 6.0 — and is what the consumer
# site has computed all along, so this also closes the site/API divergence.
#
# WHAT WOULD LET THIS BE LIFTED. This list said "two things" until 2026-08-04.
# It was wrong: there is a third, and it is the one now blocking.
#   1. DONE (code). Rows reloaded, or read through the plausibility guard, so
#      uncovered postcodes fall through to Haversine rather than posing as
#      raster hits. The table itself still holds the old 35.0 fills; the
#      read-side guard neutralises them, so a reload is tidiness, not a gate.
#   2. DONE 2026-08-04. lden_db_to_quiet's bands re-derived — see that function.
#      The old table scored TW6 1AP's genuine 58.2 dB sample at 7.5, an airport
#      reading as "fairly quiet"; it now returns 2.7, inside the <= 3.0 that
#      scripts/check_score_sanity.py enforces.
#   3. OPEN, and newly identified. The consumer site computes quiet from
#      Haversine geometry in index.html (~line 5985) and has no access to the
#      raster. Lifting this flag therefore makes the API answer from the raster
#      for the 10.4% of London postcodes DEFRA covers while the site keeps
#      answering from geometry — re-opening, for 18,862 postcodes, exactly the
#      site/API divergence closed on 2026-08-03.
#
#      SiteApiGeometryParityTests will NOT catch this. It compares FLIGHT_PATHS
#      waypoints, and those would still match; the API would simply stop
#      consulting them wherever a raster sample exists. Both halves stay
#      self-consistent, which is the same shape as the three-month defect that
#      test was written for.
#
#      Resolving it means picking one: serve the site's quiet from /v1/score,
#      ship the raster samples to the client, or accept and document the
#      divergence. That is a product decision, not a data one.
#
#      MEASURED 2026-08-06, and it reorders those three options.
#
#      "Serve the site's quiet from /v1/score" reads as the clean answer and was
#      recommended as such. It has a cost that recommendation missed: /v1/score
#      is API-key gated (template.yaml, ApiKeyRequired on all three routes), so
#      the consumer site would have to embed a key and meter every visitor
#      against a usage plan. The site currently makes no authenticated calls at
#      all.
#
#      "Ship the raster samples to the client" turns out to be cheap, because
#      DEFRA's coverage is so sparse. Sampling data/defra_lden_2022.tif at every
#      NSPL centroid inside the London bbox: 393,942 postcodes, of which 35,352
#      (9.0%) carry a real reading. As postcode->dB JSON that is ~483 KB, the
#      same order as the data files index.html already fetches, and it needs no
#      key, no request per visitor and no new route.
#
#      Watch the nodata sentinel when regenerating it. This GeoTIFF declares
#      nodata as 3.4e38 (float32 max), NOT the 35.0 the loader wrote into
#      DynamoDB. A `>= 40.0` plausibility test passes 3.4e38 unharmed — that
#      mistake reported 100% coverage on the first attempt at this measurement,
#      which is the same "absence read as measurement" defect the quarantine
#      exists for, reproduced while measuring the quarantine.
# LIFTED 2026-08-06. Condition 3 above — the site computing quiet from geometry
# with no access to the raster — is resolved: data/aircraft-quiet-london.json
# ships the same 35,352 measured postcodes to index.html, carrying the COMPUTED
# quiet score rather than decibels so neither side reimplements the ramp. Both
# halves now answer from the same measurements, so lifting this no longer
# reopens the divergence.
#
# Conditions 1 and 2 were already done: the read-side plausibility guard
# neutralises the legacy 35.0 nodata fill, and lden_db_to_quiet was re-derived
# on 2026-08-04 so Heathrow's 58.20 dB scores 2.6 rather than 7.5 — inside the
# <= 3.0 that scripts/check_score_sanity.py enforces.
#
# To re-quarantine, set this True AND remove the fetch in index.html. Leaving
# the client dataset in place while the API falls back to geometry recreates the
# same divergence from the opposite side.
RASTER_TIER_QUARANTINED = False

# The legacy nodata fill written by scripts/load_defra_raster.py before
# 2026-08-03. Not a measurement — the raster's minimum real value is 40.0 dB.
_RASTER_NODATA_FILL = 35.0

# The DEFRA London raster's true minimum, measured off the GeoTIFF on
# 2026-08-04 (min 40.0, max 88.9, 2,359,172 valid cells). Anything below this
# is a sentinel or a corrupt row, never a reading.
_RASTER_MIN_PLAUSIBLE_DB = 40.0


def _lookup_lden_raster(postcode_clean):
    """v3.1, Look up DEFRA Lden raster sample for a postcode in DynamoDB.

    Returns the Lden value (in dB) if the table is populated and contains
    this postcode; returns None otherwise. The table is populated by an
    offline data-loader script that samples the DEFRA GeoTIFF at every UK
    postcode centroid (one-time batch, ~1.7M postcodes, runs overnight).

    Negative results (no NOISE_RASTER_TABLE configured, item missing,
    DDB error) are NOT cached, see _make_lru. Positive results live for
    the warm-container lifetime (~15 min) up to 2048 entries LRU.
    """
    # Deliberate bypass, so it returns before the [SCORE_RASTER_DEGRADED] paths
    # below: those exist to alarm on the tier dropping *unexpectedly*, and firing
    # them on every request for a known, chosen quarantine is how an alarm stops
    # meaning anything.
    if RASTER_TIER_QUARANTINED:
        return None
    if not NOISE_RASTER_TABLE or not postcode_clean:
        return None
    cached = _raster_cache_get(postcode_clean)
    if cached is not None:
        return cached

    ddb = _get_ddb_client()
    if ddb is None:
        # Same consequence as a failed GetItem — the raster tier drops and the
        # returned score silently changes — so it carries the same alarmable
        # prefix. _get_ddb_client has already logged the specific cause.
        logger.warning('[SCORE_RASTER_DEGRADED] postcode=%s err=no-ddb-client', postcode_clean)
        return None

    try:
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        logger.warning('[SCORE_RASTER_DEGRADED] postcode=%s err=botocore-import-failed', postcode_clean)
        return None

    try:
        result = ddb.get_item(
            TableName=NOISE_RASTER_TABLE,
            Key={'postcode': {'S': postcode_clean}},
            ProjectionExpression='ldenDb',
        )
    except (BotoCoreError, ClientError) as exc:
        # [SCORE_RASTER_DEGRADED] is a structured, alarm-able prefix, in the
        # same style as signup's [SIGNUP_ORPHAN_KEY]. It matters more than a
        # plain warning reads: when this fires the request still returns
        # HTTP 200, but calc_score falls through to the Haversine tier and
        # the response carries a DIFFERENT NUMERIC SCORE with
        # context.quietResolution flipped from 'raster' to 'postcode'. A
        # silently wrong number is the worst failure this API can produce,
        # so it must be visible in logs even though the caller sees success.
        # Alarm on it:
        #   fields @timestamp, @message
        #   | filter @message like /\[SCORE_RASTER_DEGRADED\]/
        logger.warning('[SCORE_RASTER_DEGRADED] postcode=%s err=%r', postcode_clean, exc)
        return None

    item = result.get('Item') or {}
    lden = item.get('ldenDb', {}).get('N')
    if not lden:
        return None
    try:
        value = float(lden)
    except (TypeError, ValueError):
        return None
    # Rows written before 2026-08-03 carry a literal 35.0 wherever the raster had
    # no data, because the loader filled nodata rather than skipping it. Treat
    # that as a miss so the postcode falls through to Haversine, which is the
    # chain §4.5 documents and which the fill silently defeated by making every
    # uncovered postcode look like a successful raster hit.
    #
    # Safe as a sentinel, not a guess: the London raster's minimum real value is
    # 40.0 dB (DEFRA publishes contours only down to that), so 35.0 cannot be a
    # genuine sample and no true reading is discarded here. The loader no longer
    # writes it, so this only matters until the table is reloaded — but 89.5% of
    # London currently holds this value, so it matters a lot until then.
    #
    # Widened 2026-08-04 from `== 35.0` to a plausibility floor. Confirmed by
    # reading the GeoTIFF directly rather than from the docs: min 40.0, max 88.9
    # over 2,359,172 valid cells. The equality test only caught the one fill we
    # happened to have written; any future loader writing a different sentinel
    # (0, -1, -9999) would have sailed through and, under the pre-v3.6 bands,
    # scored a perfect 10.0. That is this project's most-repeated defect —
    # absence of measurement rendered as a favourable measurement, logged four
    # times on 2026-08-03 alone — so the guard is now a range, not a value.
    # Logged, not silent: an unexpected sentinel should surface, and the
    # [SCORE_RASTER_DEGRADED] prefix is what the tier's alarms already key on.
    # REVISIT when the raster vintage rolls: if DEFRA Round 5 maps below 40 dB,
    # this floor would discard genuine quiet samples.
    if value < _RASTER_MIN_PLAUSIBLE_DB:
        if value != _RASTER_NODATA_FILL:
            logger.warning(
                '[SCORE_RASTER_DEGRADED] postcode=%s err=implausible-lden value=%s',
                postcode_clean, value)
        return None
    _raster_cache_put(postcode_clean, value)
    return value


# --- Road noise (2026-08-06) ------------------------------------------------
#
# Shares the noise-raster table with aircraft Lden, under `roadLdenDb`. Loaded
# by scripts/load_defra_raster.py with --attribute roadLdenDb, which writes
# through UpdateItem so the two metrics coexist on one row per postcode.
#
# NOT SUBJECT TO RASTER_TIER_QUARANTINED, and that is deliberate rather than an
# oversight. The aircraft tier is quarantined because DEFRA's aircraft contours
# are localised lobes around airports: measured over the source GeoTIFF, only
# 6.2% of its grid carries data, so 89.5% of London postcodes have no reading
# and filling them as quiet flattened the component. The road raster is a
# different dataset with a different shape — 92.2% of its grid carries data,
# because roads are everywhere. Measured 2026-08-06: range 40.0-92.7 dB, median
# 51.7, Hyde Park Corner 70.1. The defect that blocks aircraft does not exist
# here.
#
# REPORTED, NOT SCORED. This value is surfaced in the response and does not
# enter the weighted total. Adding a component would redistribute the existing
# weights and change every score the API has ever returned — a breaking change
# for B2B integrators, which METHODOLOGY §7 says gets a version bump and 14
# days' notice. That is a product decision, not one to make in passing while
# wiring up a data source.
_ROAD_MIN_PLAUSIBLE_DB = 40.0


_road_cache_get, _road_cache_put = _make_lru(2048)


def _lookup_noise_row(postcode_clean):
    """One GetItem returning every noise metric on this postcode's row.

    ONE ROUND-TRIP, SHARED. Aircraft and road Lden live on the same row, and
    IndependentReviewRegressionTests holds the line at one GetItem per score
    (two for ?compare=previous) because duplicate lookups once pushed a
    ?compare=previous request past the 28s Lambda timeout into a 502. Fetching
    road separately doubled the count and that test caught it immediately, which
    is why this exists rather than two independent readers.

    Returns {'lden': float|None, 'roadLden': float|None}, or None if the table
    is unavailable. Callers apply their own plausibility rules — the aircraft
    tier has a quarantine and a nodata sentinel the road tier does not share.
    """
    if not NOISE_RASTER_TABLE or not postcode_clean:
        return None

    ddb = _get_ddb_client()
    if ddb is None:
        return None

    try:
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        return None

    try:
        result = ddb.get_item(
            TableName=NOISE_RASTER_TABLE,
            Key={'postcode': {'S': postcode_clean}},
            ProjectionExpression='ldenDb, roadLdenDb, no2Ugm3, pm25Ugm3',
        )
    except (BotoCoreError, ClientError) as exc:
        logger.warning('[SCORE_RASTER_DEGRADED] postcode=%s err=%r', postcode_clean, exc)
        return None

    item = result.get('Item') or {}

    def _num(key):
        raw = item.get(key, {}).get('N')
        if not raw:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    return {
        'lden': _num('ldenDb'),
        'roadLden': _num('roadLdenDb'),
        'no2': _num('no2Ugm3'),
        'pm25': _num('pm25Ugm3'),
    }


def lden_from_row(row, postcode_clean=''):
    """Apply the aircraft plausibility floor to a pre-fetched row.

    Mirrors the tail of _lookup_lden_raster, which still exists for
    calc_postcode_quiet's own sentinel-driven path. Rows written before
    2026-08-03 carry a literal 35.0 wherever the raster had no data, and 89.5%
    of London holds that value — treating it as a reading is what made every
    uncovered postcode look like a successful hit.
    """
    value = (row or {}).get('lden')
    if value is None:
        return None
    if value < _RASTER_MIN_PLAUSIBLE_DB:
        if value != _RASTER_NODATA_FILL:
            logger.warning(
                '[SCORE_RASTER_DEGRADED] postcode=%s err=implausible-lden value=%s',
                postcode_clean, value)
        return None
    return value


def road_lden_from_row(row, postcode_clean=''):
    """Apply the road plausibility floor to a pre-fetched row."""
    value = (row or {}).get('roadLden')
    if value is None:
        return None
    # Same reasoning as the aircraft floor: a sentinel that sailed through would
    # read as an implausibly quiet street.
    if value < _ROAD_MIN_PLAUSIBLE_DB:
        logger.warning(
            '[SCORE_ROAD_DEGRADED] postcode=%s err=implausible-lden value=%s',
            postcode_clean, value)
        return None
    return value


def _lookup_road_lden(postcode_clean):
    """Road Lden sample for a postcode, or None.

    Same table and same failure posture as _lookup_lden_raster: every negative
    result returns None so the caller simply omits the figure. A missing road
    reading must never become a favourable one — that substitution is this
    project's most-repeated defect.

    ONE ROUND-TRIP PER SCORE. This projects `roadLdenDb` from the same row the
    aircraft tier reads, and memoises per warm container, because
    IndependentReviewRegressionTests counts GetItems against the noise table and
    holds the line at one per score, two for ?compare=previous. That guard was
    written after duplicate lookups pushed a ?compare=previous request past the
    28s Lambda timeout into a 502 — adding a second unconditional GetItem here
    would walk straight back into it, and the test caught exactly that on the
    first run of this function.
    """
    if not NOISE_RASTER_TABLE or not postcode_clean:
        return None

    cached = _road_cache_get(postcode_clean)
    if cached is not None:
        return cached

    ddb = _get_ddb_client()
    if ddb is None:
        return None

    try:
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        return None

    try:
        result = ddb.get_item(
            TableName=NOISE_RASTER_TABLE,
            Key={'postcode': {'S': postcode_clean}},
            ProjectionExpression='roadLdenDb',
        )
    except (BotoCoreError, ClientError) as exc:
        logger.warning('[SCORE_ROAD_DEGRADED] postcode=%s err=%r', postcode_clean, exc)
        return None

    raw = (result.get('Item') or {}).get('roadLdenDb', {}).get('N')
    if not raw:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None

    # Same plausibility floor as aircraft, same reasoning: a sentinel that
    # sailed through would read as an implausibly quiet street.
    if value < _ROAD_MIN_PLAUSIBLE_DB:
        logger.warning(
            '[SCORE_ROAD_DEGRADED] postcode=%s err=implausible-lden value=%s',
            postcode_clean, value)
        return None
    _road_cache_put(postcode_clean, value)
    return value


# Ceiling: WHO Environmental Noise Guidelines for the European Region (2018)
# strongly recommends aircraft noise below 45 dB Lden. At or under it, 10.0.
# This replaces DEFRA's 55 dB, which is a *reporting* threshold under END
# 2002/49/EC (the level above which member states must publish strategic maps)
# and was never a health claim.
_QUIET_CEILING_DB = 45.0

# Floor: the UK's 57 dB LAeq,16h "onset of significant community annoyance"
# contour, re-expressed in Lden. Lden carries +5 dB evening and +10 dB night
# weighting, which puts 57 LAeq,16h at roughly 63 Lden for typical Heathrow
# operations. At or above it, 0.0.
_QUIET_FLOOR_DB = 63.0


def lden_db_to_quiet(lden):
    """Convert dB Lden to a 0-10 quiet score. Used by the v3.1 raster path.

    THE BANDS BELOW ARE THE REASON THE RASTER TIER IS QUARANTINED, and they
    are wrong for a reason neither AUDIT_REPORT.md nor BAND_MAPPING_ANALYSIS.md
    stated correctly. Both documents claimed the 40-55 dB range is unmeasured:
    the audit as "every DEFRA value is above 55 dB", the analysis as "there is
    no 45-55 dB contour to score against". Measured against the GeoTIFF at all
    180,983 live London postcode centroids on 2026-08-04, both are false.

    What the raster actually holds (data/defra_lden_2022.tif, 10 m, EPSG:27700):

      covered London postcodes   18,862 (10.4%; the rest are nodata -> Haversine)
      range at those postcodes   40.0 - 73.0 dB, median 51.0
      scored 10.0 by this table  15,173 = 80.4% OF EVERY MEASUREMENT WE HOLD
      of that bucket, > WHO 45   13,166 = 86.8%

    DEFRA's *published reporting bands* begin at 55 dB. The *raster* does not;
    it begins at 40.0. This table was derived for the former and applied to the
    latter, so its top bucket spans 40.0-55.0 dB - about 15 dB, roughly a
    tripling of perceived loudness - and flattens all of it to a perfect 10.0.
    That is the same "absence of measurement rendered as a favourable
    measurement" defect logged four times on 2026-08-03, except here the
    measurement is present and is being discarded.

    Anchors to calibrate against (all verified samples, not estimates):

      TW6 1AP  Heathrow Airport        58.20 dB   <- check_score_sanity.py
                                                     requires quiet <= 3.0
      TW3 4DX  Hounslow, under approach 59.29 dB
      TW14 9QP Bedfont, runway threshold 72.97 dB  <- loudest in London
      TW9 1AA  Kew                      55.96 dB
      SW13 9AA Barnes                   52.46 dB

    Nothing in London reaches 75 dB, so a >= 75 band is unreachable here and
    the 70-75 band catches 4 postcodes.

    Evidence for where the ceiling belongs: WHO's 2018 Environmental Noise
    Guidelines strongly recommend aircraft Lden below 45 dB. DEFRA's 55 dB is a
    *reporting* threshold under END 2002/49/EC - the level above which member
    states must publish maps - not a health threshold. Conflating the two is
    what put the ceiling at 55.

    Caution on the loud end: the UK's familiar 57 dB "onset of significant
    community annoyance" contour is LAeq,16h, NOT Lden. Lden adds +5 dB evening
    and +10 dB night weighting, so 57 dB LAeq,16h is roughly 63 dB Lden for
    typical Heathrow operations. Do not read a 57 here as that 57.

    RESOLVED 2026-08-04, v3.6: a continuous ramp between two cited thresholds,
    replacing the six-value ladder. Continuous because resolution is the whole
    reason this tier exists - re-banding a 33 dB continuous measurement into six
    buckets discards the precision we sampled the raster to obtain.

    Why the floor is 63 and not a rounder number: the gate in
    scripts/check_score_sanity.py requires Heathrow (58.20 dB) to score <= 3.0.
    Anchoring 10.0 at WHO's 45 dB then forces any linear ramp to reach 0.0 by
    ~64 dB. 63 is therefore not a free parameter - it is the only point in this
    family that is both defensible and compatible with the gate.

    KNOWN LIMITATION, disclosed in METHODOLOGY.md §4.6: everything at or above
    63 dB saturates at 0.0, so the loudest covered postcodes lose discrimination
    between each other - Bedfont at 72.97 dB and a postcode at 63.1 dB both read
    0.0. This is the mirror of the defect being fixed, at the other end and
    affecting under 2% rather than 80.4%, and every one of them is already in
    the worst category. Accepted rather than hidden: erring loud is the safe
    direction for a noise product.

    THE COUNT IS 348, NOT 334, AND THE DIFFERENCE IS INSTRUCTIVE. Re-measured
    2026-08-04 after a review flagged this docstring and METHODOLOGY §4.6 giving
    two different figures. Both were real measurements of different questions:
    **334** postcodes sit at or above the 63 dB floor, but **348** actually
    return 0.0, because the `round(..., 1)` below pulls anything from about
    62.91 dB upward down to 0.0. So 14 postcodes read 0.0 without being at the
    floor. The claim here is about which postcodes cannot be told apart, and
    that is what a caller sees, so 348 is the figure that belongs: **1.8% of
    covered, 0.19% of London** (0.18% was the proportion for 334).
    """
    if lden is None:
        return None
    if lden <= _QUIET_CEILING_DB:
        return 10.0
    if lden >= _QUIET_FLOOR_DB:
        return 0.0
    span = _QUIET_FLOOR_DB - _QUIET_CEILING_DB
    return round(10.0 * (_QUIET_FLOOR_DB - lden) / span, 1)


_RASTER_UNKNOWN = object()


def calc_postcode_quiet(lat, lon, city, postcode_clean=None, raster_lden=_RASTER_UNKNOWN):
    """Per-postcode quiet score (0-10).

    Resolution chain (highest to lowest precision):
      1. v3.1 DEFRA raster sample from DynamoDB (when table populated)
      2. v3.0 Haversine to airports + flight-path geometry
      3. Borough-aggregate Lden band (caller's fallback if this returns None)

    Returns the quiet score as a float, or None if the city has no
    geometry data. The caller (calc_score) uses the borough-aggregate as
    final fallback when this returns None.
    """
    # v3.1 first: direct raster sample if available.
    #
    # A caller that has ALREADY resolved the raster passes it in — calc_score
    # does exactly that. Without it this re-queries DynamoDB for a postcode
    # the caller just looked up, and because _make_lru deliberately never
    # caches a negative, a miss genuinely hits the network twice. That
    # doubling is not a tidiness point: on a DynamoDB stall it is what pushes
    # a ?compare=previous request (which runs calc_score twice) past the 28s
    # Lambda timeout into a 502 — see the wall-clock note on
    # _DDB_TIMEOUT_CONFIG. Passing None explicitly means "already checked,
    # it missed"; the sentinel means "not checked yet".
    if raster_lden is _RASTER_UNKNOWN:
        raster_lden = _lookup_lden_raster(postcode_clean) if postcode_clean else None
    if raster_lden is not None:
        return lden_db_to_quiet(raster_lden)

    # v3.0: Haversine to airports + flight paths
    geo = CITY_GEOMETRY.get(city)
    if not geo:
        return None

    # 1. Distance to nearest airport.
    #
    # A city can legitimately have NO airports: South Yorkshire has none, since
    # Doncaster Sheffield closed to commercial flights in 2022. Before
    # 2026-08-10 that was unreachable because postcode resolution was gated to
    # London; un-gating it made `min()` raise on an empty sequence and turned
    # every South Yorkshire postcode into a 500. Returning None falls back to
    # the borough-aggregate band, which for that city is the measured `low`
    # everywhere - the honest answer, not a crash and not a fabricated 10.
    if not geo['airports']:
        return None

    airport_dists = [(ap['code'], haversine_km(lat, lon, ap['lat'], ap['lon'])) for ap in geo['airports']]
    nearest_ap_dist = min(d for _, d in airport_dists)

    noise_score = 0.0
    if nearest_ap_dist < 3:
        noise_score += 5
    elif nearest_ap_dist < 6:
        noise_score += 4
    elif nearest_ap_dist < 10:
        noise_score += 3
    elif nearest_ap_dist < 15:
        noise_score += 2
    elif nearest_ap_dist < 20:
        noise_score += 1

    # 2. Distance to nearest flight path waypoint
    min_path_dist = float('inf')
    for path in geo['paths']:
        for plat, plon in path['coords']:
            d = haversine_km(lat, lon, plat, plon)
            if d < min_path_dist:
                min_path_dist = d

    if min_path_dist < 1:
        noise_score += 4
    elif min_path_dist < 2:
        noise_score += 3
    elif min_path_dist < 4:
        noise_score += 2
    elif min_path_dist < 6:
        noise_score += 1

    # 3. Major-airport bonus (matches consumer site)
    major_dist = next((d for code, d in airport_dists if code == geo['major_airport']), None)
    if major_dist is not None and major_dist < 15:
        noise_score += 2

    secondary = geo.get('secondary_airport')
    if secondary:
        secondary_dist = next((d for code, d in airport_dists if code == secondary), None)
        if secondary_dist is not None and secondary_dist < 10:
            noise_score += 1

    # 4. Rotary noise. Ported from the consumer site 2026-08-03; until then the
    #    site scored heliports and this did not, which was the last remaining
    #    site/API divergence and covered 14.1% of Greater London.
    #
    #    Takes the LOUDEST contribution, not the nearest site. Under the old
    #    uniform weighting those were the same thing; with per-site tiers they are
    #    not, and scoring off the closest pad would let a quiet air-ambulance
    #    helipad mask a busier commercial heliport slightly further out.
    #    Contributions are not summed, matching the airport and flight-path terms
    #    above, which also take a single nearest source.
    heli_bonus = 0
    for hp in geo.get('heliports', []):
        hd = haversine_km(lat, lon, hp['lat'], hp['lon'])
        contribution = hp['bands'][0] if hd < 3 else hp['bands'][1] if hd < 5 else 0
        heli_bonus = max(heli_bonus, contribution)
    noise_score += heli_bonus

    quiet = max(0.0, min(10.0, 10.0 - noise_score))
    return quiet


# Aliases for boroughs whose canonical name differs from postcodes.io's
# admin_district output, or common variants. We keep both the bare alias and
# explicit 'Royal Borough of…' / 'London Borough of…' / 'City of…' prefixed
# variants because partner address data (Land Registry exports, EPC bulk CSVs,
# OS AddressBase) uses these inconsistently. M-N2 fix.
BOROUGH_ALIASES = {
    # Bare-name shorteners
    'Barking': 'Barking and Dagenham',
    'Westminster City': 'Westminster',
    'City of Westminster': 'Westminster',
    'City of London Corporation': 'City of London',
    'Corporation of London': 'City of London',
    # Ampersand variants (some sources use & instead of "and")
    'Hammersmith & Fulham': 'Hammersmith and Fulham',
    'Kensington & Chelsea': 'Kensington and Chelsea',
    'Barking & Dagenham': 'Barking and Dagenham',
    # Royal borough prefixed forms (postcodes.io occasionally returns these)
    'Royal Borough of Kensington and Chelsea': 'Kensington and Chelsea',
    'Royal Borough of Kingston upon Thames': 'Kingston upon Thames',
    'Royal Borough of Greenwich': 'Greenwich',
    'Royal Borough of Kensington & Chelsea': 'Kensington and Chelsea',
    # London Borough prefixed forms (rare but seen in OS AddressBase)
    'London Borough of Tower Hamlets': 'Tower Hamlets',
    'London Borough of Hackney': 'Hackney',
    'London Borough of Newham': 'Newham',
    'London Borough of Camden': 'Camden',
    'London Borough of Islington': 'Islington',
    'London Borough of Southwark': 'Southwark',
    'London Borough of Lambeth': 'Lambeth',
    'London Borough of Wandsworth': 'Wandsworth',
    'London Borough of Lewisham': 'Lewisham',
    'London Borough of Hounslow': 'Hounslow',
    'London Borough of Hillingdon': 'Hillingdon',
    'London Borough of Ealing': 'Ealing',
    # Common spelling slips
    'Richmond Upon Thames': 'Richmond upon Thames',
    'Kingston Upon Thames': 'Kingston upon Thames',
    'Walthamforest': 'Waltham Forest',
    'Towerhamlets': 'Tower Hamlets',
    # Short forms used by some property portals
    'K&C': 'Kensington and Chelsea',
    'H&F': 'Hammersmith and Fulham',
}


def _postcode_source_line(local_served):
    """Attribution for the postcode-resolution tier.

    Keyed on whether the local NSPL tier has actually SERVED a lookup in
    this container — deliberately not on POSTCODE_TABLE being set.

    `sam deploy` wires the env var and creates the table in a single change
    set, so for the whole window between deploying and finishing the ~40
    minute load the table exists, the var is set, and every lookup is still
    answered by postcodes.io. Crediting ONS on configuration alone would put
    a false provenance claim in the machine-readable `sources` array that a
    B2B customer audits — and being straight about provenance is the thing
    this product sells. Credit what actually answered.
    """
    if local_served:
        return (
            'Postcode resolution: ONS National Statistics Postcode Lookup (Open Government '
            'Licence v3.0), with postcodes.io (Open Government Licence v3.0) as fallback'
        )
    return 'Postcode resolution: postcodes.io (Open Government Licence v3.0)'


# Per-city data lineage. Auditable provenance for each scoring input — B2B audit
# teams ask "where did this number come from" component-by-component, and this
# surfaces the answer at the response level.
#
# Per-city since 2026-07-31, and the reason is a defect this replaced. Note this
# deliberately does NOT bump METHODOLOGY_VERSION: no weight, threshold or formula
# changed and every score is byte-identical, so a version bump would tell
# integrators to re-run and find nothing moved. Both the sources
# list and the per-component breakdown used to be single globals, emitted
# unconditionally on every response. That credited MHCLG, HM Land Registry, ONS,
# the Home Office, DfE, TfL, NHS and DEFRA — under Open Government Licence v3.0
# — for NEW YORK scores, where not one of those bodies has a remit and OGL, a UK
# Crown-copyright licence, does not apply to the data at all. It is the same
# error _postcode_source_line() exists to prevent, one function up: crediting a
# source on configuration rather than on what actually answered.
#
# Resolved per borough by _london_borough_metadata_line(); a plain callable cannot
# see which borough is being scored.
_BOROUGH_METADATA_SENTINEL = object()

# Entries may be callables where the line depends on runtime state.
CITY_PROVENANCE = {
    'london': {
        'sources': [
            'EPC data: MHCLG, Open Government Licence v3.0',
            'Sold prices: HM Land Registry, Open Government Licence v3.0',
            # Index 2 by contract — two tests assert the postcode line's position.
            lambda: _postcode_source_line(_LOCAL_POSTCODE_SERVED),
            # The Home Office was dropped here on 2026-08-03. v3.5 moved the crime
            # rate to ONS Table C4, which left the Home Office credited in every
            # London response while answering for nothing — the same "crediting on
            # configuration rather than on what actually answered" this whole
            # registry exists to prevent. The breakdown below already named the
            # real sources; only this coarse line lagged.
            _BOROUGH_METADATA_SENTINEL,
            'Aviation noise context: DEFRA strategic noise mapping, Open Government Licence v3.0',
        ],
        'breakdown': {
            'quiet': 'DEFRA Strategic Noise Mapping (Round 4, 2022). Resolution chain: v3.1 direct raster sample at postcode centroid (when populated) → v3.0 Haversine to airports + flight-path geometry → v2.x borough-aggregate Lden band. The chosen resolution is reported in context.quietResolution.',
            'afford': 'HM Land Registry House Price Index (HPI), borough cohort min-max scaling',
            'growth': 'HM Land Registry House Price Index (HPI), annualised price trend, cohort-relative',
            'live': 'Composite weighted (schools 35% + crime 30% + transport 25% + healthcare 10%). Schools: DfE Key Stage 4 Progress 8, 2022/23, local-authority level — Progress 8 cannot be calculated for 2023/24 onwards because the KS2 baseline was lost to the 2020 and 2021 test cancellations, and DfE announced no replacement. Crime: ONS Crime in England and Wales, Police Force Area data tables, year ending March 2026, Table C4, offences per 1,000 residents on mid-2024 population. Transport and healthcare: curated tiers. Methodologically aligned with English Indices of Deprivation domains.',
        },
    },
    'nyc': {
        'sources': [
            'Borough metadata: curated from public New York City sources',
            'Crime: NYPD CompStat-derived offence rates per 1,000, against New York City population denominators',
            'Prices: curated New York borough median sale prices, in USD',
            'Aviation noise context: JFK and LaGuardia approach geometry, curated borough-aggregate bands',
            'Licence note: Open Government Licence v3.0 covers UK Crown copyright and does NOT apply to any data in this response',
        ],
        'breakdown': {
            'quiet': 'Curated borough-aggregate aircraft-noise bands derived from JFK and LaGuardia approach geometry. NOT DEFRA — no published Lden survey covers New York, so the dB thresholds in METHODOLOGY §3 are not directly applicable. The chosen resolution is reported in context.quietResolution.',
            'afford': 'Curated New York borough median sale prices (USD), borough cohort min-max scaling. NOT HM Land Registry, which holds England and Wales only.',
            'growth': 'Curated New York borough annualised price trend. NOT HM Land Registry HPI.',
            'live': 'NYPD CompStat-derived crime rates with New York population denominators, plus curated school / transport / healthcare tiers. NOT ONS, Home Office, DfE, TfL or NHS — none has a New York remit. Cross-city comparison against UK boroughs should be approached with caution: different collection methodologies.',
        },
    },
    'westmidlands': {
        'sources': [
            'Prices: HM Land Registry UK House Price Index, May 2026 vintage, Open Government Licence v3.0',
            'Aviation noise context: ESTIMATED from Birmingham Airport runway geometry, NOT sampled from DEFRA strategic noise mapping',
            'Crime: ONS Crime in England and Wales, Police Force Area data tables, year ending March 2026, Open Government Licence v3.0',
            'Schools, transport and healthcare: not sourced. Their weight is redistributed, not defaulted, see sourceBreakdown.live',
        ],
        'breakdown': {
            'quiet': 'PROVISIONAL ESTIMATE derived from Birmingham Airport (BHX) runway 15/33 alignment and its extended approach centreline. NOT sampled from the DEFRA Round 4 raster. DEFRA HAS published a Round 4 Lden surface for this airport; we have not yet sampled it, so the gap is in our pipeline and not in the coverage published by the regulator. So the dB Lden thresholds in METHODOLOGY section 3 are not evidenced for this city. The distance ladder is calibrated on Heathrow, which is several times Birmingham\'s size, so these bands reach further than the airport really does and are PESSIMISTIC rather than optimistic. Corridor waypoints are on a common 1 km interval across all cities, so corridor distances are comparable. Treat as indicative only.',
            'afford': 'HM Land Registry UK House Price Index, May 2026 vintage, borough cohort min-max scaling. Same vintage and source as London and Greater Manchester, but scaled WITHIN the West Midlands cohort, so the numbers are not comparable across cities: the priciest borough in any cohort scores 0.0 whatever it costs. Compare boroughs to boroughs of the same city, or compare context.avgPriceGbp directly.',
            'growth': 'HM Land Registry UK House Price Index, May 2026 vintage, annualised price trend, cohort-relative. The West Midlands has no previous vintage, so ?compare=previous declines rather than reporting zero change.',
            'live': 'UNAVAILABLE, 1 of 4 inputs measured, and context.liveResolution says so per response. Crime: ONS Crime in England and Wales, Police Force Area data tables, year ending March 2026, Table C4 Community Safety Partnership rows, all seven matched, same release and period as London. Schools, transport and healthcare are NOT sourced - there is no Progress 8 pipeline in this codebase for any city, so unlike Greater Manchester this city cannot reach the two-input floor. The component is therefore DROPPED and its weight redistributed across quiet, afford and growth rather than filled with a placeholder. This city is thinner than Greater Manchester and the response says so rather than implying parity.',
        },
    },
    'westyorkshire': {
        'sources': [
            'Prices: HM Land Registry UK House Price Index, May 2026 vintage, Open Government Licence v3.0',
            'Aviation noise context: ESTIMATED from Leeds Bradford Airport (LBA) runway 14/32 geometry, NOT sampled from DEFRA strategic noise mapping',
            'Crime: ONS Crime in England and Wales, Police Force Area data tables, year ending March 2026, Open Government Licence v3.0',
            'Schools, transport and healthcare: not sourced. Their weight is redistributed, not defaulted, see sourceBreakdown.live',
        ],
        'breakdown': {
            'quiet': "PROVISIONAL ESTIMATE derived from Leeds Bradford Airport (LBA) runway 14/32 alignment and its extended approach centreline. NOT sampled from the DEFRA Round 4 raster. DEFRA HAS published a Round 4 Lden surface for this airport; we have not yet sampled it, so the gap is in our pipeline and not in the coverage published by the regulator. So the dB Lden thresholds in METHODOLOGY section 3 are not evidenced here. The distance ladder is calibrated on Heathrow, which is several times this airport's size, so the bands reach further than it really does and are PESSIMISTIC rather than optimistic. Corridor waypoints are on a common 1 km interval across all cities, so corridor distances are comparable. Indicative only.",
            'afford': 'HM Land Registry UK House Price Index, May 2026 vintage, borough cohort min-max scaling. Same vintage and source as London, but scaled WITHIN this city cohort, so the numbers are not comparable across cities: the priciest borough in any cohort scores 0.0 whatever it costs. Compare boroughs of the same city, or compare context.avgPriceGbp directly.',
            'growth': 'HM Land Registry UK House Price Index, May 2026 vintage, annualised price trend, cohort-relative. This city has no previous vintage, so ?compare=previous declines rather than reporting zero change.',
            'live': 'UNAVAILABLE, 1 of 4 inputs measured, and context.liveResolution says so per response. Crime: ONS Crime in England and Wales, Table C4 Community Safety Partnership rows from West Yorkshire Police, all 5 matched, same release and period as London. Schools, transport and healthcare are NOT sourced: this repo has no Progress 8 pipeline for any city, so unlike Greater Manchester this city cannot reach the two-input floor. The component is DROPPED and its weight redistributed rather than filled with a placeholder. Thinner than Greater Manchester, and the response says so rather than implying parity.',
        },
    },
    'southyorkshire': {
        'sources': [
            'Prices: HM Land Registry UK House Price Index, May 2026 vintage, Open Government Licence v3.0',
            'Aviation noise context: NO operating commercial airport in the city region; Doncaster Sheffield closed to commercial flights in 2022',
            'Crime: ONS Crime in England and Wales, Police Force Area data tables, year ending March 2026, Open Government Licence v3.0',
            'Schools, transport and healthcare: not sourced. Their weight is redistributed, not defaulted, see sourceBreakdown.live',
        ],
        'breakdown': {
            'quiet': "NO OPERATING COMMERCIAL AIRPORT. Doncaster Sheffield Airport is listed `type=closed` by OurAirports, commercial flights having ceased in 2022, and the nearest large airports are Leeds Bradford and Manchester at roughly 50-60 km. Every borough is therefore banded `low`. That is a MEASURED ABSENCE of a noise source rather than an unmeasured city, and it is stated so that a flat band cannot be read as a survey result. NOT a DEFRA sample.",
            'afford': 'HM Land Registry UK House Price Index, May 2026 vintage, borough cohort min-max scaling. Same vintage and source as London, but scaled WITHIN this city cohort, so the numbers are not comparable across cities: the priciest borough in any cohort scores 0.0 whatever it costs. Compare boroughs of the same city, or compare context.avgPriceGbp directly.',
            'growth': 'HM Land Registry UK House Price Index, May 2026 vintage, annualised price trend, cohort-relative. This city has no previous vintage, so ?compare=previous declines rather than reporting zero change.',
            'live': 'UNAVAILABLE, 1 of 4 inputs measured, and context.liveResolution says so per response. Crime: ONS Crime in England and Wales, Table C4 Community Safety Partnership rows from South Yorkshire Police, all 4 matched, same release and period as London. Schools, transport and healthcare are NOT sourced: this repo has no Progress 8 pipeline for any city, so unlike Greater Manchester this city cannot reach the two-input floor. The component is DROPPED and its weight redistributed rather than filled with a placeholder. Thinner than Greater Manchester, and the response says so rather than implying parity.',
        },
    },
    'merseyside': {
        'sources': [
            'Prices: HM Land Registry UK House Price Index, May 2026 vintage, Open Government Licence v3.0',
            'Aviation noise context: ESTIMATED from Liverpool John Lennon Airport (LPL) runway 09/27 geometry, NOT sampled from DEFRA strategic noise mapping',
            'Crime: ONS Crime in England and Wales, Police Force Area data tables, year ending March 2026, Open Government Licence v3.0',
            'Schools, transport and healthcare: not sourced. Their weight is redistributed, not defaulted, see sourceBreakdown.live',
        ],
        'breakdown': {
            'quiet': "PROVISIONAL ESTIMATE derived from Liverpool John Lennon Airport (LPL) runway 09/27 alignment and its extended approach centreline. NOT sampled from the DEFRA Round 4 raster. DEFRA HAS published a Round 4 Lden surface for this airport; we have not yet sampled it, so the gap is in our pipeline and not in the coverage published by the regulator. So the dB Lden thresholds in METHODOLOGY section 3 are not evidenced here. The distance ladder is calibrated on Heathrow, which is several times this airport's size, so the bands reach further than it really does and are PESSIMISTIC rather than optimistic. Corridor waypoints are on a common 1 km interval across all cities, so corridor distances are comparable. Indicative only.",
            'afford': 'HM Land Registry UK House Price Index, May 2026 vintage, borough cohort min-max scaling. Same vintage and source as London, but scaled WITHIN this city cohort, so the numbers are not comparable across cities: the priciest borough in any cohort scores 0.0 whatever it costs. Compare boroughs of the same city, or compare context.avgPriceGbp directly.',
            'growth': 'HM Land Registry UK House Price Index, May 2026 vintage, annualised price trend, cohort-relative. This city has no previous vintage, so ?compare=previous declines rather than reporting zero change.',
            'live': 'UNAVAILABLE, 1 of 4 inputs measured, and context.liveResolution says so per response. Crime: ONS Crime in England and Wales, Table C4 Community Safety Partnership rows from Merseyside Police, all 5 matched, same release and period as London. Schools, transport and healthcare are NOT sourced: this repo has no Progress 8 pipeline for any city, so unlike Greater Manchester this city cannot reach the two-input floor. The component is DROPPED and its weight redistributed rather than filled with a placeholder. Thinner than Greater Manchester, and the response says so rather than implying parity.',
        },
    },
    'tyneandwear': {
        'sources': [
            'Prices: HM Land Registry UK House Price Index, May 2026 vintage, Open Government Licence v3.0',
            'Aviation noise context: ESTIMATED from Newcastle Airport (NCL) runway 07/25 geometry, NOT sampled from DEFRA strategic noise mapping',
            'Crime: ONS Crime in England and Wales, Police Force Area data tables, year ending March 2026, Open Government Licence v3.0',
            'Schools, transport and healthcare: not sourced. Their weight is redistributed, not defaulted, see sourceBreakdown.live',
        ],
        'breakdown': {
            'quiet': "PROVISIONAL ESTIMATE derived from Newcastle Airport (NCL) runway 07/25 alignment and its extended approach centreline. NOT sampled from the DEFRA Round 4 raster. DEFRA HAS published a Round 4 Lden surface for this airport; we have not yet sampled it, so the gap is in our pipeline and not in the coverage published by the regulator. So the dB Lden thresholds in METHODOLOGY section 3 are not evidenced here. The distance ladder is calibrated on Heathrow, which is several times this airport's size, so the bands reach further than it really does and are PESSIMISTIC rather than optimistic. Corridor waypoints are on a common 1 km interval across all cities, so corridor distances are comparable. Indicative only.",
            'afford': 'HM Land Registry UK House Price Index, May 2026 vintage, borough cohort min-max scaling. Same vintage and source as London, but scaled WITHIN this city cohort, so the numbers are not comparable across cities: the priciest borough in any cohort scores 0.0 whatever it costs. Compare boroughs of the same city, or compare context.avgPriceGbp directly.',
            'growth': 'HM Land Registry UK House Price Index, May 2026 vintage, annualised price trend, cohort-relative. This city has no previous vintage, so ?compare=previous declines rather than reporting zero change.',
            'live': 'UNAVAILABLE, 1 of 4 inputs measured, and context.liveResolution says so per response. Crime: ONS Crime in England and Wales, Table C4 Community Safety Partnership rows from Northumbria Police, filtered to the five Tyne and Wear partnerships, all 5 matched, same release and period as London. Schools, transport and healthcare are NOT sourced: this repo has no Progress 8 pipeline for any city, so unlike Greater Manchester this city cannot reach the two-input floor. The component is DROPPED and its weight redistributed rather than filled with a placeholder. Thinner than Greater Manchester, and the response says so rather than implying parity.',
        },
    },
    'bristol': {
        'sources': [
            'Prices: HM Land Registry UK House Price Index, May 2026 vintage, Open Government Licence v3.0',
            'Aviation noise context: ESTIMATED from Bristol Airport (BRS) runway 09/27 geometry, NOT sampled from DEFRA strategic noise mapping',
            'Crime: ONS Crime in England and Wales, Police Force Area data tables, year ending March 2026, Open Government Licence v3.0',
            'Schools, transport and healthcare: not sourced. Their weight is redistributed, not defaulted, see sourceBreakdown.live',
        ],
        'breakdown': {
            'quiet': "PROVISIONAL ESTIMATE derived from Bristol Airport (BRS) runway 09/27 alignment and its extended approach centreline. NOT sampled from the DEFRA Round 4 raster. DEFRA HAS published a Round 4 Lden surface for this airport; we have not yet sampled it, so the gap is in our pipeline and not in the coverage published by the regulator. So the dB Lden thresholds in METHODOLOGY section 3 are not evidenced here. The distance ladder is calibrated on Heathrow, which is several times this airport's size, so the bands reach further than it really does and are PESSIMISTIC rather than optimistic. Corridor waypoints are on a common 1 km interval across all cities, so corridor distances are comparable. Indicative only.",
            'afford': 'HM Land Registry UK House Price Index, May 2026 vintage, borough cohort min-max scaling. Same vintage and source as London, but scaled WITHIN this city cohort, so the numbers are not comparable across cities: the priciest borough in any cohort scores 0.0 whatever it costs. Compare boroughs of the same city, or compare context.avgPriceGbp directly.',
            'growth': 'HM Land Registry UK House Price Index, May 2026 vintage, annualised price trend, cohort-relative. This city has no previous vintage, so ?compare=previous declines rather than reporting zero change.',
            'live': 'UNAVAILABLE, 1 of 4 inputs measured, and context.liveResolution says so per response. Crime: ONS Crime in England and Wales, Table C4 Community Safety Partnership rows from Avon and Somerset Police, filtered to the four West of England partnerships, all 4 matched, same release and period as London. Schools, transport and healthcare are NOT sourced: this repo has no Progress 8 pipeline for any city, so unlike Greater Manchester this city cannot reach the two-input floor. The component is DROPPED and its weight redistributed rather than filled with a placeholder. Thinner than Greater Manchester, and the response says so rather than implying parity.',
        },
    },
    'cardiff': {
        'sources': [
            'Prices: HM Land Registry UK House Price Index, May 2026 vintage, Open Government Licence v3.0',
            'Aviation noise context: ESTIMATED from Cardiff Airport (CWL) runway 12/30 geometry, NOT sampled from DEFRA strategic noise mapping',
            'Crime: ONS Crime in England and Wales, Police Force Area data tables, year ending March 2026, Open Government Licence v3.0',
            'Schools, transport and healthcare: not sourced. Their weight is redistributed, not defaulted, see sourceBreakdown.live',
        ],
        'breakdown': {
            'quiet': "PROVISIONAL ESTIMATE derived from Cardiff Airport (CWL) runway 12/30 alignment and its extended approach centreline. NOT sampled from the DEFRA Round 4 raster. DEFRA HAS published a Round 4 Lden surface for this airport; we have not yet sampled it, so the gap is in our pipeline and not in the coverage published by the regulator. So the dB Lden thresholds in METHODOLOGY section 3 are not evidenced here. The distance ladder is calibrated on Heathrow, which is several times this airport's size, so the bands reach further than it really does and are PESSIMISTIC rather than optimistic. Corridor waypoints are on a common 1 km interval across all cities, so corridor distances are comparable. Indicative only.",
            'afford': 'HM Land Registry UK House Price Index, May 2026 vintage, borough cohort min-max scaling. Same vintage and source as London, but scaled WITHIN this city cohort, so the numbers are not comparable across cities: the priciest borough in any cohort scores 0.0 whatever it costs. Compare boroughs of the same city, or compare context.avgPriceGbp directly.',
            'growth': 'HM Land Registry UK House Price Index, May 2026 vintage, annualised price trend, cohort-relative. This city has no previous vintage, so ?compare=previous declines rather than reporting zero change.',
            'live': 'UNAVAILABLE, 1 of 4 inputs measured, and context.liveResolution says so per response. Crime: ONS Crime in England and Wales, Table C4 Community Safety Partnership rows from South Wales Police and Gwent Police, filtered to the four partnerships of the city region, all 4 matched, same release and period as London. Schools, transport and healthcare are NOT sourced: this repo has no Progress 8 pipeline for any city, so unlike Greater Manchester this city cannot reach the two-input floor. The component is DROPPED and its weight redistributed rather than filled with a placeholder. Thinner than Greater Manchester, and the response says so rather than implying parity.',
        },
    },
    'nottingham': {
        'sources': [
            'Prices: HM Land Registry UK House Price Index, May 2026 vintage, Open Government Licence v3.0',
            'Aviation noise context: ESTIMATED from East Midlands Airport (EMA) runway 09/27 geometry, NOT sampled from DEFRA strategic noise mapping',
            'Crime: ONS Crime in England and Wales, Police Force Area data tables, year ending March 2026, CITY OF NOTTINGHAM ONLY, Open Government Licence v3.0',
            'Schools, transport and healthcare: not sourced. Their weight is redistributed, not defaulted, see sourceBreakdown.live',
        ],
        'breakdown': {
            'quiet': "PROVISIONAL ESTIMATE derived from East Midlands Airport (EMA) runway 09/27 alignment and its extended approach centreline. The airport lies OUTSIDE the city region, in Leicestershire, so no borough here is nearer than 16 km and none is banded above low-moderate. NOT sampled from the DEFRA Round 4 raster, so the dB Lden thresholds in METHODOLOGY section 3 are not evidenced here. The ladder is calibrated on Heathrow and is therefore PESSIMISTIC rather than optimistic. Indicative only.",
            'afford': 'HM Land Registry UK House Price Index, May 2026 vintage, borough cohort min-max scaling across Greater Nottingham (the city plus Broxtowe, Gedling and Rushcliffe). Scaled WITHIN this cohort, so figures are not comparable across cities; compare context.avgPriceGbp directly.',
            'growth': 'HM Land Registry UK House Price Index, May 2026 vintage, annualised price trend, cohort-relative. No previous vintage exists for this city, so ?compare=previous declines rather than reporting zero change.',
            'live': 'UNAVAILABLE, and doubly so. Crime is published by ONS for the CITY OF NOTTINGHAM ONLY: Table C4 carries `Nottingham` and `South Nottinghamshire`, and Broxtowe, Gedling and Rushcliffe sit inside that one combined partnership row rather than being published separately. Their crimeRate is therefore ABSENT rather than filled with the combined figure, which would render one measurement as three. Schools, transport and healthcare are not sourced for any city added after Greater Manchester. With at most one input, `live` falls below its two-input floor and is DROPPED with its weight redistributed. The thinnest city in the registry, and the response says so.',
        },
    },
    'manchester': {
        'sources': [
            'Prices: HM Land Registry UK House Price Index, May 2026 vintage, Open Government Licence v3.0',
            'Aviation noise context: ESTIMATED from Manchester Airport runway geometry, NOT sampled from DEFRA strategic noise mapping',
            'Schools: Department for Education, Key Stage 4 Progress 8, 2022/23, Open Government Licence v3.0',
            'Crime: ONS Crime in England and Wales, Police Force Area data tables, year ending March 2026, Open Government Licence v3.0',
            'Transport and healthcare: not sourced. Their weight is redistributed, not defaulted, see sourceBreakdown.live',
        ],
        'breakdown': {
            'quiet': 'PROVISIONAL ESTIMATE derived from Manchester Airport (MAN) runway alignment and approach geometry. NOT sampled from the DEFRA Round 4 raster. DEFRA HAS published a Round 4 Lden surface for this airport; we have not yet sampled it, so the gap is in our pipeline and not in the coverage published by the regulator. So the dB Lden thresholds in METHODOLOGY §3 are not evidenced for this city. Corridor waypoints are on a common 1 km interval across all cities, so corridor distances are comparable. Treat as indicative only.',
            'afford': 'HM Land Registry UK House Price Index, May 2026 vintage, borough cohort min-max scaling. Same vintage and source as London, but scaled WITHIN the Greater Manchester cohort, so the numbers are not comparable across cities: the priciest borough in any cohort scores 0.0 whatever it costs, and Trafford at GBP 393k scores as London\'s most expensive borough does at several times that. Compare boroughs to boroughs of the same city, or compare context.avgPriceGbp directly.',
            'growth': 'HM Land Registry UK House Price Index, May 2026 vintage, annualised price trend, cohort-relative. Greater Manchester has no previous vintage, so ?compare=previous declines rather than reporting zero change.',
            'live': 'PARTIAL, 2 of 4 inputs measured, and context.liveResolution says so per response. Schools: DfE Key Stage 4 Progress 8, 2022/23, same release and year as London. Crime: ONS Crime in England and Wales, Police Force Area data tables, year ending March 2026, Table C4 Community Safety Partnership rows, same release and period as London. Transport and healthcare are NOT sourced; since 2026-08-09 their weight is REDISTRIBUTED across schools and crime in proportion rather than filled with a placeholder, so their absence does not depress the score. It does mean liveability here rests on two inputs where London rests on four.',
        },
    },
}


def _borough_record(city, borough):
    """The borough's data row, or None if it cannot be resolved.

    Only used to decide provenance, so an unresolved borough must return None
    and get the generic line rather than raise - a lookup miss should never turn
    a scoring request into a 500.
    """
    try:
        table = (CITIES.get(city) or {}).get('boroughs') or {}
        return table.get(borough)
    except Exception:  # noqa: BLE001 - provenance must never break a response
        return None


def _london_borough_metadata_line(bd=None):
    """Credit only the bodies that actually supplied this borough's metadata.

    Added 2026-08-03. This line named ONS Table C4 and DfE Progress 8
    unconditionally, which is false for the City of London: ONS explicitly
    declines to publish a recorded-crime rate for it (Table C4 note 8, small
    resident population) and DfE has no Progress 8 figure for it either. So the
    one borough where both credits are wrong was the one asserting them hardest.

    Same defect as the Home Office line and the NYC/OGL bug before it: crediting
    on configuration rather than on what answered. CITY_PROVENANCE exists to stop
    that at city granularity; this does it at borough granularity.
    """
    crime_is_ons = bd is None or not bd.get('crimeEstimated')
    schools_is_dfe = bool(bd is None or bd.get('p8') is not None)
    parts = []
    if crime_is_ons:
        parts.append('ONS (Crime in England and Wales, Police Force Area data tables, Table C4)')
    else:
        parts.append(
            'crime rate is a Sky Score estimate - ONS publishes no rate for this area '
            'and it must not be attributed to them'
        )
    if schools_is_dfe:
        parts.append('Department for Education (Key Stage 4 Progress 8)')
    else:
        parts.append('no Progress 8 figure published for this area; schools falls back to a curated band')
    suffix = ', Open Government Licence v3.0' if (crime_is_ons or schools_is_dfe) else ''
    return 'Borough metadata: ' + ' and '.join(parts) + suffix


def build_sources(city='london', bd=None):
    """The response `sources` array, built per request and per city.

    Deliberately a function, not the import-time constant it replaced: the
    postcode line depends on runtime state (see _postcode_source_line), and
    a constant snapshot taken at cold start would keep claiming postcodes.io
    for the life of a container that had since started resolving locally.

    An unknown city says so rather than falling back to London's list — a
    silent default is how the original defect published UK provenance over
    New York data.
    """
    prov = CITY_PROVENANCE.get(city)
    if prov is None:
        return [f'Provenance not recorded for city {city!r}']
    out = []
    for line in prov['sources']:
        if callable(line):
            out.append(line())
        elif line is _BOROUGH_METADATA_SENTINEL:
            out.append(_london_borough_metadata_line(bd))
        else:
            out.append(line)
    return out


def build_source_breakdown(city='london'):
    """Per-component lineage for `city`. See build_sources() for why per-city."""
    prov = CITY_PROVENANCE.get(city)
    if prov is None:
        return {}
    return dict(prov['breakdown'])


def build_batch_sources(cities):
    """Sources for a batch response, which may span several cities.

    One response covers many queries, so any single city's list would be a
    false claim for every result drawn from another city. With one city the
    list is exact; with several, each line carries the city it belongs to so
    nothing is credited to a city that never used it.
    """
    seen = sorted({c for c in cities if c})
    if not seen:
        return []
    if len(seen) == 1:
        return build_sources(seen[0])
    return [f'[{c}] {line}' for c in seen for line in build_sources(c)]


def crime_to_score(rate):
    if rate is None:
        return 5.0
    return max(0.0, min(10.0, 10.0 - (rate - 50) / 15.0))


def school_score(p8):
    """DfE Progress 8 -> 0-10, anchored on absolute constants.

    Progress 8 measures the grades a cohort achieves against pupils with the
    same KS2 starting point nationally, so it is defined such that the national
    average is ~0.0 and +/-1.0 means a full grade per subject better or worse
    than similar pupils. Both are real-world quantities, not cohort artefacts,
    so the mapping needs no reference to which cities happen to be loaded:

        0.0 -> 5.0     national average
       +1.0 -> 10.0    a grade per subject above similar pupils
       -1.0 ->  0.0    a grade per subject below

    That is the v3.4 dual-anchor idea with the tails pinned to an external
    constant instead of the loaded cohort's extremes, which is what makes it
    comparable across cities AND across vintages. Observed LA scores span -0.90
    to +0.73 nationally, so nothing clamps in practice.

    This replaces the Ofsted-grade lookup for English boroughs. Ofsted abolished
    single-word overall-effectiveness grades in September 2024; only ~44% of
    schools still carry one, that residue is precisely the not-yet-reinspected,
    and 87.2% of it is Good or Outstanding, so the measure barely discriminated.
    Progress 8 is intake-adjusted, which also stops school quality quietly
    re-importing the affluence already priced into the `afford` component.
    """
    return max(0.0, min(10.0, 5.0 + 5.0 * p8))


_LIVE_FIELDS = ('schools', 'crimeRate', 'transport', 'healthcare')

# Declared weights, summing to 1.0. Previously these were four literals inside
# get_live_score; naming them is what lets an absent input be redistributed
# rather than filled with a placeholder.
_LIVE_WEIGHTS = {
    'schools': 0.35,
    'crimeRate': 0.30,
    'transport': 0.25,
    'healthcare': 0.10,
}

# Minimum inputs before `live` is published at all. See live_weights_for.
_LIVE_MIN_FIELDS = 2


def live_weights_for(present):
    """Weights to apply given the subset of liveability inputs that exist.

    `present` is the set of _LIVE_FIELDS with real data for this borough.
    Returns a dict over exactly those fields. Returning an empty dict means the
    caller must decline to score `live` at all rather than invent one.

    WHY THIS IS NOT JUST get(field, 5.0), which is what it replaced. A missing
    input used to score 5.0, and 5.0 is NOT neutral: London's computed live
    scores span 5.5-8.4, so the placeholder sat below every real borough and
    filling one of four fields could make a place score WORSE. That is what
    forced Greater Manchester to be all four fields or none - a constraint this
    function LIFTS, so GM can now be sourced one field at a time. City of London
    was the live example in the other direction: it has no Progress 8 because it
    has no state secondary provision, so 35% of its 5.5 was a number about
    nothing. It now scores 5.2 from what is actually known about it.

    The precedent is methodology v3.4/v3.3, which dropped `growth` for
    non-investor personas and redistributed its weight across the remaining
    components IN PROPORTION, so relative emphasis was preserved and every
    persona still summed to 1.0.

    TODO(bill): implement the redistribution. Roughly 5 lines. The decisions
    that matter, and why they are yours rather than mine:

      - PROPORTIONAL vs EQUAL. Proportional keeps crime dominant over
        healthcare when schools drops out; equal treats the remaining inputs as
        interchangeable. Proportional matches v3.3; equal is defensible if you
        think the declared ratios only ever meant anything as a complete set.
      - A FLOOR. Should one surviving input be allowed to carry 100% of
        liveability? A borough with only `healthcare` would score `live` purely
        on a 10%-weighted field promoted to the whole thing. Refusing below
        some coverage (return {}) is honest but means some places have no live
        score at all.

    PROPORTIONAL, not equal, so the declared ratios keep their meaning: when
    schools drops out, crime stays three times healthcare exactly as it was.
    Equal shares would silently promote healthcare from a 10% input to a 25%
    one, which is a different opinion about the place, not the same one with a
    gap in it.

    FLOOR AT TWO of the four. One surviving input scaled to 1.0 is a stronger
    claim than the data supports - a borough known only by its healthcare tier
    would have `live` mean "healthcare", under a label that promises four
    things. Below the floor the caller declines to score rather than publishing
    a number it would have to caveat away.
    """
    present = [f for f in _LIVE_FIELDS if f in present]
    if len(present) < _LIVE_MIN_FIELDS:
        return {}
    total = sum(_LIVE_WEIGHTS[f] for f in present)
    return {f: _LIVE_WEIGHTS[f] / total for f in present}


def live_component_scores(bd, english=True):
    """Score each liveability input that this borough actually has.

    A field the borough lacks is ABSENT from the result, never present with a
    stand-in value. That is the whole point: the previous version defaulted each
    missing input to 5.0, and 5.0 is not neutral - London's computed live scores
    span 5.5-8.4 (measured 2026-08-09; "8.8" was carried in this docstring for
    months and was never right), so the placeholder sat below every real borough
    and made a gap
    read as a bad place.

    Indexing is direct (`TRANSPORT_SCORE[...]`) rather than `.get(..., 5)`,
    which is safe because validate_borough_vocabulary() runs at import and
    raises on any value its table lacks. A KeyError here would mean that guard
    was bypassed, and raising beats resurrecting the silent 5.0 it replaced.
    """
    scores = {}
    # Progress 8 where it exists (English LAs), the curated tier otherwise. New
    # York has neither Ofsted nor DfE, so the tier IS its schools input, and is
    # declared as such in CITY_PROVENANCE rather than passed off as DfE. For an
    # English borough the retired Ofsted band is NOT a fallback - v3.5 removed
    # it as editorial, so a borough carrying only the band has no schools input.
    if english:
        if bd.get('p8') is not None:
            scores['schools'] = school_score(bd['p8'])
    elif bd.get('schools') is not None:
        scores['schools'] = SCHOOL_SCORE[bd['schools']]

    if bd.get('crimeRate') is not None:
        scores['crimeRate'] = crime_to_score(bd['crimeRate'])
    if bd.get('transport') is not None:
        scores['transport'] = TRANSPORT_SCORE[bd['transport']]
    if bd.get('healthcare') is not None:
        scores['healthcare'] = HEALTH_SCORE[bd['healthcare']]
    return scores


def get_live_score(bd, english=True):
    """Liveability composite over the inputs that exist, or None if too few.

    Declared weights are schools 35%, crime 30%, transport 25%, health 10%; an
    absent input has its weight redistributed across the rest in proportion
    (live_weights_for) rather than filled with a placeholder.

    Returns None when fewer than two inputs are present, meaning `live` cannot
    be published for this borough at all. Callers must handle that rather than
    substituting a number - see calc_scores, which drops the component and
    rescales the composite the way v3.3 dropped growth.
    """
    scores = live_component_scores(bd, english)
    weights = live_weights_for(scores)
    if not weights:
        return None
    return round(sum(scores[f] * w for f, w in weights.items()) * 10) / 10


# Human-readable coverage notices. Added 2026-08-06.
#
# WHY THIS EXISTS. `context.quietResolution` has always said HOW an answer was
# reached, but only in machine terms ('raster' | 'postcode' | 'borough'), and
# only an integrator reading the docs would know that 'postcode' means "DEFRA
# never measured here, this is geometry". A consumer sees a number.
#
# That gap is the entire reason the raster tier is quarantined: 89.5% of London
# sits outside DEFRA's aircraft contours, and rendering "not measured" as a
# confident score is the defect. A short, plain notice converts an unstated
# limitation into a stated one — the same move as the extension's non-London
# caveat, and the same principle as the Core Cities finding that partial data
# presented as complete is worse than no data.
#
# Keyed by component so airQuality and roadNoise slot in unchanged when their
# rasters land. Both are declared in plannedComponents today; neither has data
# in this repo yet, so neither appears here.
_COVERAGE_NOTICES = {
    'raster': None,  # measured at this location — nothing to disclose
    'postcode': (
        'Aircraft noise here is estimated from distance to airports and '
        'flight-path geometry, not measured. DEFRA publishes contours for '
        'about 10% of London postcodes and this one falls outside them.'
    ),
    'borough': (
        'Aircraft noise here is a borough-wide average, not a figure for this '
        'address. Expect real variation of 10-15 dB within a borough.'
    ),
}

_LIVE_UNAVAILABLE_NOTICE = (
    'Liveability inputs are unavailable for this area, so that component is a '
    'neutral placeholder rather than a measurement. Do not read it as average.'
)


def build_environment(noise_row, postcode_clean=''):
    """Measured environmental readings for a postcode, omitting what is absent.

    Returns a dict to be spliced into `context`. An absent measurement means an
    ABSENT KEY — never null, never a default. A numeric field carrying a
    placeholder is precisely how "we did not measure here" becomes "we measured
    here and it was fine", which is the defect that quarantined the aircraft
    raster and the one this codebase has repeated most often.

    Road Lden is reported, not scored. Folding it into the weighted total would
    change every score the API has ever returned, which METHODOLOGY §7 treats as
    a version bump with 14 days' notice to integrators — a product decision, not
    a side effect of adding a data source.
    """
    env = {}

    road_lden = road_lden_from_row(noise_row, postcode_clean)
    if road_lden is not None:
        env['roadNoiseLdenDb'] = round(road_lden, 1)
        # WHO Environmental Noise Guidelines for the European Region (2018)
        # strongly recommends road traffic below 53 dB Lden. The same document
        # gives the 45 dB aircraft anchor already used by _QUIET_CEILING_DB, so
        # this is a figure this codebase already relies on, not a new source.
        #
        # Carried alongside the value for the same reason the air-quality rows
        # carry theirs: "69.6 dB Lden" means nothing to a reader, and leaving it
        # bare invites interpretation against whatever they happen to assume.
        # Stating the reference is not editorialising; omitting it is.
        env['roadNoiseWhoGuidelineDb'] = 53
        # Same vintage caveat as aircraft, and it applies to road traffic too -
        # 2021 road volumes were also depressed, though less sharply than
        # aviation. See METHODOLOGY.md section 4.6.
        env['roadNoiseSource'] = (
            'DEFRA Strategic Noise Mapping Round 4, road Lden. '
            'Published 2022, maps 2021 - a COVID-affected year, so readings err quiet.'
        )

    # Air quality: DEFRA PCM background maps, annual mean, 2022, 1 km grid.
    #
    # NOT the Daily Air Quality Index that plannedComponents still names. DAQI
    # is a daily index at monitoring stations — sparse, and as much about
    # today's weather as about the address. Annual mean concentration on a
    # modelled grid is the measure a property decision wants, and the one the
    # WHO guidelines below are expressed against.
    #
    # The guideline is carried alongside the value because a bare "13.3" means
    # nothing to a reader. WHO 2021: NO2 10 ug/m3, PM2.5 5 ug/m3 annual mean.
    # Stating the reference is not editorialising — omitting it would leave the
    # number to be interpreted against whatever the reader assumes.
    no2 = (noise_row or {}).get('no2')
    if no2 is not None and no2 >= 0:
        env['no2AnnualMeanUgm3'] = round(no2, 1)
        env['no2WhoGuidelineUgm3'] = 10

    pm25 = (noise_row or {}).get('pm25')
    if pm25 is not None and pm25 >= 0:
        env['pm25AnnualMeanUgm3'] = round(pm25, 1)
        env['pm25WhoGuidelineUgm3'] = 5

    if no2 is not None or pm25 is not None:
        env['airQualitySource'] = (
            'DEFRA background pollution maps (PCM), annual mean 2022, 1 km grid'
        )

    return env


def build_coverage(quiet_source, live_source):
    """Per-component coverage statements plus any plain-English notices.

    Returned on every response, not only degraded ones: a field that appears
    only when something is wrong trains readers to ignore its absence, and
    'measured' is itself worth stating. `notices` is empty when everything is
    measured at the queried location.
    """
    notices = []

    quiet_notice = _COVERAGE_NOTICES.get(quiet_source)
    if quiet_notice:
        notices.append(quiet_notice)

    # 'unavailable' is live_resolution's way of saying no input was measured.
    # It used to mean every one of them hit a 5.0 placeholder, which is how a
    # uniform Greater Manchester 5.0 read as a finding rather than a gap; the
    # component is now omitted outright rather than defaulted, and this notice
    # is what says so in plain English.
    if live_source == 'unavailable':
        notices.append(_LIVE_UNAVAILABLE_NOTICE)

    return {
        'quiet': {
            'basis': quiet_source,
            'measuredAtLocation': quiet_source == 'raster',
        },
        'live': {
            'basis': live_source,
            'measuredAtLocation': live_source == 'measured',
        },
        'notices': notices,
    }


def live_resolution(bd, english=True):
    """How much of the liveability composite is measured rather than defaulted.

    Mirrors quietResolution: the response states how an answer was reached, not
    only what it was. 'unavailable' means every input hit the 5.0 placeholder, so
    the component says nothing about the location — the distinction that made
    Greater Manchester's uniform 5.0 read as a finding rather than a gap.
    """
    # Schools is city-dependent, and getting this wrong is what made the City of
    # London report 'measured' while its schools input was the retired Ofsted band
    # and its crime rate was our own estimate.
    #
    # For an English borough, Progress 8 IS the schools input (METHODOLOGY 4.4);
    # the legacy categorical band is the fallback that v3.5 removed as editorial
    # and unreproducible, so a borough carrying only the band is DEFAULTED, not
    # measured. Counting it as measured made this field claim the opposite of what
    # 4.4 says it exists to disclose.
    #
    # New York is the reverse: it has neither Ofsted nor DfE, so its curated tier
    # is the real source and satisfies the slot on its own.
    def _slot_present(f):
        if f != 'schools':
            return bd.get(f) is not None
        if english:
            return bd.get('p8') is not None
        return bd.get('schools') is not None

    present = sum(1 for f in _LIVE_FIELDS if _slot_present(f))
    total = len(_LIVE_FIELDS)
    if present == total:
        return 'measured'
    # Wording corrected 2026-08-09. These strings said "defaulted to 5.0" and
    # "5.0 placeholder", which described the behaviour get_live_score() had that
    # morning and stopped having that afternoon. They are SERVED - in
    # context.liveResolution and in coverage.live.basis - so a stale one is a
    # public claim about how a number was reached, not an internal comment.
    if present < _LIVE_MIN_FIELDS:
        return (
            f'unavailable — {present}/{total} inputs measured, too few to publish; '
            'the component is omitted and its weight redistributed'
        )
    return (
        f'partial — {present}/{total} inputs measured; the absent inputs are not '
        'estimated, their weight is redistributed across the measured ones'
    )


def growth_score(trend, max_trend, min_trend):
    """Methodology v3.4: dual-anchor growth on a 0-10 scale.

    A flat market (0% trend) anchors at **5.0**. Rising places spread across
    5-10 against the fastest riser in the cohort; falling places spread across
    5-0 against the steepest faller. Each side is scaled to its own extreme,
    which is what keeps both tails legible.

    Replaces the v3.2/v3.3 formula `(trend / max_trend) * 10` clamped to 0-10.
    That scaled everything against the fastest riser alone, so every falling
    place collapsed onto 0.0: 14 of the 33 London boroughs shared one value,
    and Ealing (-0.3%) read identically to the City of London (-28.2%). The
    component carried no signal for 42% of the map.

    Scaling each tail separately is deliberate. London's trends run -28.2% to
    +5.0%, so a single symmetric map across that range would squash every
    rising borough into the top sixth of the scale and make +5.0% almost
    indistinguishable from +0.4%.

    The 5.0 anchor is absolute (0% growth), while each tail's extreme is
    relative to the cohort — so scores stay comparable across a vintage
    refresh at the midpoint even as the extremes move.
    """
    if trend > 0:
        score = 5.0 + (trend / max_trend) * 5.0 if max_trend > 0 else 5.0
    elif trend < 0:
        score = 5.0 - (trend / min_trend) * 5.0 if min_trend < 0 else 5.0
    else:
        score = 5.0
    return max(0.0, min(10.0, score))


def calc_score(borough_name, city, weights, lat=None, lon=None, postcode_clean=None, boroughs_override=None):
    """Compute Sky Score for a borough/postcode.

    Resolution chain for the quiet component:
      v3.1, DEFRA raster sample at postcode centroid (if table populated)
      v3.0, Haversine to airports + flight-path geometry (if lat/lon given)
      v2.x, Borough-aggregate Lden band lookup (always available as fallback)

    boroughs_override swaps the price/trend dataset (used by the trends
    feature to score against a previous vintage); cohort bounds are taken
    from the override so affordability/growth stay internally consistent.
    Noise inputs are vintage-independent (DEFRA refreshes five-yearly).

    See METHODOLOGY.md §4.1 (borough), §4.5 (postcode Haversine), §4.6 (raster).
    """
    boroughs = boroughs_override if boroughs_override is not None else CITIES[city]['boroughs']
    bd = boroughs[borough_name]

    borough_quiet = IMPACT_TO_QUIET.get(bd['impact'], 5.0)
    quiet_source = 'borough'
    # Initialised here, not inside the lat/lon branch below: a borough-only
    # query never enters that branch, and build_environment reads this when
    # assembling the response regardless.
    noise_row = None

    if lat is not None and lon is not None:
        # Try raster first (v3.1), Haversine second (v3.0), borough last
        # ONE GetItem, shared by both metrics. Aircraft and road Lden live on
        # the same row, and a second reader doubled the lookups per score —
        # caught immediately by the regression guard written after duplicate
        # lookups pushed a ?compare=previous request into a 502.
        noise_row = _lookup_noise_row(postcode_clean) if postcode_clean else None
        raster_lden = (
            None if RASTER_TIER_QUARANTINED else lden_from_row(noise_row, postcode_clean)
        )
        if raster_lden is not None:
            quiet = lden_db_to_quiet(raster_lden)
            quiet_source = 'raster'
        else:
            # raster_lden is None here by construction — hand it over so
            # calc_postcode_quiet does not repeat the GetItem we just made.
            postcode_quiet = calc_postcode_quiet(lat, lon, city, postcode_clean, raster_lden=raster_lden)
            if postcode_quiet is not None:
                quiet = postcode_quiet
                quiet_source = 'postcode'
            else:
                quiet = borough_quiet
    else:
        quiet = borough_quiet

    prices = [b['avgPrice'] for b in boroughs.values()]
    max_price, min_price = max(prices), min(prices)
    if max_price == min_price:
        afford = 5.0
    else:
        afford = ((max_price - bd['avgPrice']) / (max_price - min_price)) * 10

    trends = [b['trend'] for b in boroughs.values()]
    max_trend, min_trend = max(trends), min(trends)
    # Methodology v3.4: dual-anchor — 0% growth sits at 5.0, each tail scaled
    # to its own extreme. See growth_score() for why the v3.2 single-anchor
    # formula collapsed 14 of 33 boroughs onto one value.
    growth = growth_score(bd['trend'], max_trend, min_trend)

    live = get_live_score(bd, english=(city != 'nyc'))

    # `live` is None when fewer than two of its four inputs exist, so the
    # component would say nothing about this place. Drop it and rescale the
    # remaining weights in proportion - the same move v3.3 made when it dropped
    # `growth` for non-investor personas. The alternative it replaced, a 5.0
    # placeholder, sat below every real London live score and so penalised a
    # city for the gap - which is what made Greater Manchester all-or-nothing.
    parts = {'quiet': quiet, 'afford': afford, 'growth': growth}
    effective = {k: weights[k] for k in parts}
    if live is not None:
        parts['live'] = live
        effective['live'] = weights['live']
    else:
        scale = sum(effective.values())
        if scale > 0:
            effective = {k: v / scale for k, v in effective.items()}

    total = sum(parts[k] * effective[k] for k in parts)

    currency_field = 'avgPriceUsd' if CITIES[city]['currency'] == 'USD' else 'avgPriceGbp'

    return {
        'score': round(total * 10) / 10,
        # `live` is OMITTED, not null and not defaulted, when it could not be
        # computed - the same convention build_environment uses below and for
        # the same reason: a placeholder in a numeric field is how "not
        # measured" becomes "measured as fine". liveResolution says why.
        'components': {
            'quiet': round(quiet * 10) / 10,
            'afford': round(afford * 10) / 10,
            'growth': round(growth * 10) / 10,
            **({'live': round(live * 10) / 10} if live is not None else {}),
        },
        'context': {
            currency_field: bd['avgPrice'],
            'priceTrendPct': bd['trend'],
            'noiseImpactBand': bd['impact'],
            'quietResolution': quiet_source,
            'liveResolution': live_resolution(bd, english=(city != 'nyc')),
            # Measured environmental readings at this postcode, REPORTED AND
            # NOT SCORED. Present only where a real sample exists; the key is
            # absent rather than null or a default when it does not, because a
            # placeholder in a numeric field is how "not measured" becomes
            # "measured as fine". See build_environment.
            **build_environment(noise_row, postcode_clean),
        },
        # Plain-English restatement of the two *Resolution fields above, so a
        # consumer surface can show a limitation without having to know what
        # 'postcode' means. See build_coverage.
        'coverage': build_coverage(
            quiet_source, live_resolution(bd, english=(city != 'nyc'))
        ),
    }


_postcode_cache_get, _postcode_cache_put = _make_lru(512)

# Third return state for _lookup_postcode_local, distinct from both a result
# dict and None (audit L4). None means "unknown, ask postcodes.io"; this
# means "the NSPL table positively knows this postcode is terminated and the
# caller did not opt in". postcodes.io 404s every terminated postcode, so the
# fallback call is a guaranteed miss: it burns a 5s urlopen timeout budget
# per query, is never cached, and repeats on every request. 904,453 of the
# 2,699,393 loaded rows (33.5%) carry a termination date, so on a
# terminated-heavy backfill the feature would remove none of the postcodes.io
# load it exists to remove, and 10 workers x up to 5s x 10 waves would blow
# the 28s function timeout for the whole batch.
#
# Module-private on purpose: lookup_postcode converts it back to None before
# returning, so it never reaches resolve_query, the LRU, or a response body.
POSTCODE_TERMINATED = object()


def _lookup_postcode_local(clean, include_terminated=False):
    """Resolve a UK postcode from the local ONS NSPL table in DynamoDB.

    Returns one of three things:
      * a dict shaped like the postcodes.io `result` object — the keys
        resolve_query consumes (postcode, admin_district, latitude,
        longitude, region) plus `_`-prefixed private metadata;
      * POSTCODE_TERMINATED, when the row exists but is terminated and the
        caller did not opt in — a definitive "postcodes.io cannot serve this
        either", so the caller should skip the fallback entirely;
      * None, to defer to the postcodes.io fallback.

    Returns None (defer, never 404) when the table is not configured, the
    item is missing, or the centroid is unusable. Nothing here raises: every
    botocore and parse failure degrades to None so the network fallback still
    serves the request. Callers must treat None as "unknown", not "not found".
    """
    if not POSTCODE_TABLE or not clean:
        return None

    ddb = _get_ddb_client()
    if ddb is None:
        return None

    try:
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        return None

    try:
        # No ProjectionExpression, deliberately. The item is ~60 bytes, far
        # below the 4 KB read-unit boundary, so projection saves nothing —
        # and a reserved-word ValidationException would be caught as a
        # ClientError below and swallowed to None, silently disabling the
        # table forever while the API kept working via the fallback. That is
        # the one failure mode the forward-compatible design makes invisible.
        result = ddb.get_item(TableName=POSTCODE_TABLE, Key={'postcode': {'S': clean}})
    except (BotoCoreError, ClientError) as exc:
        logger.warning('DDB postcode lookup failed for %s: %s', clean, exc)
        return None

    item = result.get('Item') or {}
    if not item:
        return None

    try:
        latitude = float(item['lat']['N'])
        longitude = float(item['lon']['N'])
    except (KeyError, TypeError, ValueError):
        # A row without a usable centroid is worse than no row at all: it
        # would resolve the borough but silently downgrade the quiet score
        # to the borough-aggregate band. Defer to postcodes.io instead.
        return None

    doterm = item.get('dt', {}).get('S')
    if doterm and not include_terminated:
        # Not None: we positively know postcodes.io cannot serve this, so the
        # caller short-circuits to its not-found path instead of paying for a
        # guaranteed-404 round trip. See POSTCODE_TERMINATED above.
        return POSTCODE_TERMINATED

    try:
        grid_ind = int(item['q']['N'])
    except (KeyError, TypeError, ValueError):
        grid_ind = 1  # attribute omitted == building-level precision

    # We are about to return a real local hit, so ONS NSPL has genuinely
    # served a lookup in this container and may now be credited in the
    # `sources` array. Set only on this path — a miss, a terminated row or
    # any error leaves it alone, because none of those were answered locally.
    global _LOCAL_POSTCODE_SERVED
    _LOCAL_POSTCODE_SERVED = True

    return {
        # Canonical spaced form, derived rather than stored. The inward code
        # is always the final three characters — verified across all
        # 2,723,596 rows of the loaded NSPL edition with zero exceptions, and
        # re-checked on every loader run (scripts/load_nspl.py warns loudly
        # if a future edition ever breaks it).
        'postcode': f'{clean[:-3]} {clean[-3:]}' if len(clean) > 3 else clean,
        # None for any UK postcode outside the 33 London boroughs. This is
        # intentional: normalise_borough(None) -> None -> the existing
        # "Borough not currently supported in london." 404, byte-identical
        # to what postcodes.io produces today for e.g. a Manchester postcode.
        # Falls back to the LAD code when the stored name is absent, which it
        # is for every postcode outside the 33 London boroughs. Before
        # 2026-08-10 this was None there and the caller 404'd; the code was
        # sitting in the same row the whole time.
        'admin_district': (
            item.get('b', {}).get('S')
            or (LAD_TO_BOROUGH.get(item.get('lad', {}).get('S')) or (None, None))[1]
        ),
        'latitude': latitude,
        'longitude': longitude,
        'region': item.get('rgn', {}).get('S'),
        '_ladCode': item.get('lad', {}).get('S'),
        '_terminated': bool(doterm),
        '_dotermMonth': f'{doterm[:4]}-{doterm[4:6]}' if doterm and len(doterm) >= 6 else None,
        '_gridInd': grid_ind,
        '_resolver': 'nspl',
    }


def _fetch_postcode(clean):
    """Fetch from postcodes.io, no caching, no normalisation. Returns
    parsed result dict on success, None on transient/permanent failure."""
    if not clean:
        return None
    url = f'https://api.postcodes.io/postcodes/{quote(clean)}'
    req = Request(url, headers={'Accept': 'application/json'})
    try:
        with urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read().decode())
    except (HTTPError, URLError, TimeoutError) as exc:
        logger.warning('postcodes.io lookup failed for %s: %s', clean, exc)
        return None
    except json.JSONDecodeError as exc:
        logger.warning('postcodes.io returned non-JSON for %s: %s', clean, exc)
        return None
    if payload.get('status') != 200:
        return None
    return payload.get('result')


_reverse_cache_get, _reverse_cache_put = _make_lru(1024)


def reverse_geocode(lat, lon):
    """Nearest UK postcode to a coordinate, or None.

    The one thing the browser extension cannot do for itself. A property
    listing yields coordinates; every environmental dataset here is keyed by
    postcode, so without this none of it can reach a listing page.

    postcodes.io rather than the local NSPL table, deliberately: that table is
    keyed BY postcode, and DynamoDB has no geospatial query, so reverse lookup
    would mean a full scan of 2.7M rows. postcodes.io is already a hard
    dependency of the forward path a few lines below, so this adds a new use of
    an existing dependency rather than a new dependency.

    Cached per warm container on a rounded coordinate. 4 dp is ~11 m, far below
    the 1 km air-quality grid and comparable to the 10 m noise rasters, so the
    rounding cannot move an answer to a different postcode in any way that
    matters — and listing pages cluster, so the cache earns its keep.
    """
    key = f'{lat:.4f},{lon:.4f}'
    cached = _reverse_cache_get(key)
    if cached is not None:
        return cached

    url = f'https://api.postcodes.io/postcodes?lat={lat}&lon={lon}&limit=1'
    req = Request(url, headers={'Accept': 'application/json'})
    try:
        with urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read().decode())
    except (HTTPError, URLError, TimeoutError) as exc:
        logger.warning('postcodes.io reverse lookup failed for %s: %s', key, exc)
        return None
    except json.JSONDecodeError as exc:
        logger.warning('postcodes.io returned non-JSON for %s: %s', key, exc)
        return None

    # A coordinate in the sea returns status 200 with result: null. That is a
    # legitimate "no postcode here", not an error, and must not be cached as
    # one — _make_lru does not cache negatives, so returning None is enough.
    results = payload.get('result') or []
    if not results:
        return None

    postcode = (results[0] or {}).get('postcode')
    if postcode:
        _reverse_cache_put(key, postcode)
    return postcode


# LAD code -> (city id, borough name as CITIES holds it).
#
# GENERATED from CITY_LADS in scripts/build_hpi_prices.py, the one place the
# code-to-borough mapping lives - the same registry the price and boundary
# loaders read - so a city cannot resolve postcodes to a borough set it does
# not score.
#
# This is what un-gated postcode lookup beyond London, and it needed NO reload.
# The NSPL table already stores `lad` for all 2.7M rows; only the borough NAME
# (`b`) was written for London LADs alone. Verified against the LIVE table:
# M1 1AE carries lad=E08000003 with b absent, B1 1AA lad=E08000025, LS1 1AA
# lad=E08000035. The gap was a lookup, not missing data, so the two blockers
# recorded in CITY_PROVENANCE were really one.
LAD_TO_BOROUGH = {
    'E09000018': ('london', 'Hounslow'),
    'E09000017': ('london', 'Hillingdon'),
    'E09000027': ('london', 'Richmond upon Thames'),
    'E09000009': ('london', 'Ealing'),
    'E09000032': ('london', 'Wandsworth'),
    'E09000022': ('london', 'Lambeth'),
    'E09000023': ('london', 'Lewisham'),
    'E09000011': ('london', 'Greenwich'),
    'E09000030': ('london', 'Tower Hamlets'),
    'E09000007': ('london', 'Camden'),
    'E09000019': ('london', 'Islington'),
    'E09000012': ('london', 'Hackney'),
    'E09000003': ('london', 'Barnet'),
    'E09000008': ('london', 'Croydon'),
    'E09000006': ('london', 'Bromley'),
    'E09000025': ('london', 'Newham'),
    'E09000028': ('london', 'Southwark'),
    'E09000013': ('london', 'Hammersmith and Fulham'),
    'E09000020': ('london', 'Kensington and Chelsea'),
    'E09000005': ('london', 'Brent'),
    'E09000014': ('london', 'Haringey'),
    'E09000031': ('london', 'Waltham Forest'),
    'E09000024': ('london', 'Merton'),
    'E09000026': ('london', 'Redbridge'),
    'E09000010': ('london', 'Enfield'),
    'E09000021': ('london', 'Kingston upon Thames'),
    'E09000029': ('london', 'Sutton'),
    'E09000033': ('london', 'Westminster'),
    'E09000001': ('london', 'City of London'),
    'E09000002': ('london', 'Barking and Dagenham'),
    'E09000016': ('london', 'Havering'),
    'E09000004': ('london', 'Bexley'),
    'E09000015': ('london', 'Harrow'),
    'E08000003': ('manchester', 'Manchester'),
    'E08000006': ('manchester', 'Salford'),
    'E08000007': ('manchester', 'Stockport'),
    'E08000009': ('manchester', 'Trafford'),
    'E08000008': ('manchester', 'Tameside'),
    'E08000004': ('manchester', 'Oldham'),
    'E08000005': ('manchester', 'Rochdale'),
    'E08000002': ('manchester', 'Bury'),
    'E08000001': ('manchester', 'Bolton'),
    'E08000010': ('manchester', 'Wigan'),
    'E08000025': ('westmidlands', 'Birmingham'),
    'E08000026': ('westmidlands', 'Coventry'),
    'E08000027': ('westmidlands', 'Dudley'),
    'E08000028': ('westmidlands', 'Sandwell'),
    'E08000029': ('westmidlands', 'Solihull'),
    'E08000030': ('westmidlands', 'Walsall'),
    'E08000031': ('westmidlands', 'Wolverhampton'),
    'E08000032': ('westyorkshire', 'Bradford'),
    'E08000033': ('westyorkshire', 'Calderdale'),
    'E08000034': ('westyorkshire', 'Kirklees'),
    'E08000035': ('westyorkshire', 'Leeds'),
    'E08000036': ('westyorkshire', 'Wakefield'),
    'E08000038': ('southyorkshire', 'Barnsley'),
    'E08000017': ('southyorkshire', 'Doncaster'),
    'E08000018': ('southyorkshire', 'Rotherham'),
    'E08000039': ('southyorkshire', 'Sheffield'),
    'E08000011': ('merseyside', 'Knowsley'),
    'E08000012': ('merseyside', 'Liverpool'),
    'E08000013': ('merseyside', 'St Helens'),
    'E08000014': ('merseyside', 'Sefton'),
    'E08000015': ('merseyside', 'Wirral'),
    'E08000037': ('tyneandwear', 'Gateshead'),
    'E08000021': ('tyneandwear', 'Newcastle upon Tyne'),
    'E08000022': ('tyneandwear', 'North Tyneside'),
    'E08000023': ('tyneandwear', 'South Tyneside'),
    'E08000024': ('tyneandwear', 'Sunderland'),
    'E06000023': ('bristol', 'City of Bristol'),
    'E06000022': ('bristol', 'Bath and North East Somerset'),
    'E06000024': ('bristol', 'North Somerset'),
    'E06000025': ('bristol', 'South Gloucestershire'),
    'E06000018': ('nottingham', 'City of Nottingham'),
    'E07000172': ('nottingham', 'Broxtowe'),
    'E07000173': ('nottingham', 'Gedling'),
    'E07000176': ('nottingham', 'Rushcliffe'),
    'W06000015': ('cardiff', 'Cardiff'),
    'W06000014': ('cardiff', 'Vale of Glamorgan'),
    'W06000022': ('cardiff', 'Newport'),
    'W06000018': ('cardiff', 'Caerphilly'),
}

def lookup_postcode(postcode, include_terminated=False):
    """Resolve a UK postcode to a postcodes.io-shaped result dict.

    Tier 1: the local ONS NSPL table in DynamoDB (POSTCODE_TABLE), ~5ms.
    Tier 2: postcodes.io over the network, ~100-500ms p95.

    Tier 1 returns None for anything it cannot answer confidently, so
    behaviour is identical to the pre-table implementation whenever the
    table is unset, empty, or partially loaded — a table miss is never a
    404, it is a deferral.

    Tier 1 can also answer POSTCODE_TERMINATED, meaning "known terminated,
    caller did not opt in". That is converted to None here — same 404, same
    body as before — but without the guaranteed-miss postcodes.io call that
    a bare None would trigger. The sentinel never escapes this function.

    Cached per warm container (~15 min) in one LRU shared by both tiers,
    since they return the same shape. Misses and errors are NOT cached (see
    _make_lru), so a transient DDB or postcodes.io outage does not poison
    the cache. Terminated rows are not cached either: the cache key is the
    postcode alone, so caching one would leak an opt-in result to a later
    caller that did not opt in.
    """
    clean = postcode.strip().replace(' ', '').upper()
    if not clean:
        return None
    cached = _postcode_cache_get(clean)
    if cached is not None:
        return cached
    result = _lookup_postcode_local(clean, include_terminated=include_terminated)
    if result is POSTCODE_TERMINATED:
        return None
    if result is None:
        result = _fetch_postcode(clean)
    if result is not None and not result.get('_terminated'):
        _postcode_cache_put(clean, result)
    return result


def normalise_borough(name, city):
    if not name:
        return None
    boroughs = CITIES[city]['boroughs']
    if name in boroughs:
        return name
    aliased = BOROUGH_ALIASES.get(name)
    if aliased and aliased in boroughs:
        return aliased
    return None


def parse_weights(raw):
    """Parse '?weights=quiet:0.5,afford:0.2,growth:0.1,live:0.2'.

    Returns dict, or None if unparsable. Sum must be ~1 (within 1%).
    """
    if not raw:
        return None
    if isinstance(raw, dict):
        result = raw
    else:
        try:
            parts = raw.split(',')
            result = {}
            for part in parts:
                key, value = part.split(':')
                result[key.strip()] = float(value.strip())
        except (ValueError, AttributeError):
            return None

    if set(result.keys()) != {'quiet', 'afford', 'growth', 'live'}:
        return None
    try:
        result = {k: float(v) for k, v in result.items()}
    except (ValueError, TypeError):
        return None
    # Each weight must be a sane fraction on its own — a sum-only check
    # accepted pathological inputs like {quiet: -1, afford: 2} (A-0724-M11).
    if any(not (0.0 <= v <= 1.0) for v in result.values()):
        return None
    total = sum(result.values())
    if not (0.99 <= total <= 1.01):
        return None
    return result


RESPONSE_FIELDS = {
    'score',
    'components',
    'comparison',
    'comparisonUnavailable',
    'context',
    'location',
    'persona',
    'weights',
    'methodologyVersion',
    'methodologyUrl',
    'apiVersion',
    'generatedAt',
    'sources',
    'sourceBreakdown',
    'plannedComponents',
}


def parse_include(raw):
    """Parse `?include=score,components,context` into a set of allowed
    response fields. Returns None when no filter (full response). Unknown
    fields are ignored silently. Always-included meta fields stay regardless."""
    if not raw:
        return None
    # A GET query string forces the comma-separated form, but a batch POST
    # body expresses a list parameter as a JSON array — so `raw` may be a
    # list, or anything else. Never call .split on it unguarded: before this,
    # {"include": ["score"]} raised AttributeError, which the per-query batch
    # guard then turned into an opaque 500 for that one query.
    if isinstance(raw, (list, tuple, set)):
        requested = {str(p).strip() for p in raw if str(p).strip()}
    elif isinstance(raw, str):
        requested = {p.strip() for p in raw.split(',') if p.strip()}
    else:
        return None
    if not requested:
        return None
    return requested & RESPONSE_FIELDS


def filter_response(body, include):
    """Apply an include-filter to a response body. Always retains meta
    fields (apiVersion, methodologyVersion, generatedAt, sources)."""
    if not include:
        return body
    always = {'apiVersion', 'methodologyVersion', 'methodologyUrl', 'generatedAt', 'sources'}
    keep = include | always
    # Asking for the comparison should also get you the reason there isn't one.
    # Otherwise ?include=comparison on a city with no prior vintage returns a
    # body with no comparison and no explanation — indistinguishable from the
    # parameter having been ignored.
    if 'comparison' in keep:
        keep = keep | {'comparisonUnavailable'}
    return {k: v for k, v in body.items() if k in keep}


TRUTHY_FLAGS = frozenset({'1', 'true', 'yes', 'y', 'on'})


def parse_bool_flag(raw):
    """Coerce a boolean-ish query value to True/False, from any JSON type.

    A single query dict reaches resolve_query from two very different
    places: API Gateway's query-string map, where every value is a string
    ('true', '1'), and a JSON POST body, where a boolean-named parameter
    is naturally written as a JSON boolean (true) or 0/1. Both must work.

    Liberal in what it accepts, and it never calls a string method on an
    unvalidated value: an unexpected type (dict, list, None) is simply
    falsey rather than an AttributeError. That matters because this runs
    per query inside /v1/score/batch, where a raised exception used to
    escape the worker and 500 the whole 100-query batch (audit L1).
    """
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in TRUTHY_FLAGS
    if isinstance(raw, (int, float)):
        return raw != 0
    return False


def parse_str_param(raw, default=''):
    """Coerce a text query value to a stripped string, from any JSON type.

    The text sibling of parse_bool_flag, and it exists for the same reason.
    A GET query string always delivers strings, but a batch POST body can
    deliver a number — and this API documents exactly that case: "pass a
    5-digit US ZIP for NYC auto-detection". So {"postcode": 10001} is a
    DOCUMENTED input, not a malformed one, and it must score identically to
    {"postcode": "10001"}.

    Falsey input returns `default`, matching the `(x or default).strip()`
    idiom this replaces, so empty and missing values behave exactly as
    before. Anything else that is not a string or a number — a dict, a
    list, True — also returns the default, which leaves the caller's
    existing "Provide either postcode or borough" guard to answer with a
    clean per-query 400 rather than raising.

    Never calls a string method on an unvalidated value. Before the audit
    L1 per-query guard, a raise here 500'd the whole 100-query batch; after
    it, the same raise silently degraded that one query to an opaque
    internal error. Neither is an acceptable answer for input the published
    contract says is valid.
    """
    if not raw:
        return default
    if isinstance(raw, str):
        return raw.strip()
    # bool is a subclass of int, so it must be tested first — 'True' is
    # never a meaningful postcode, borough, city or persona.
    if isinstance(raw, bool):
        return default
    if isinstance(raw, int):
        return str(raw)
    if isinstance(raw, float):
        # 10001.0 -> '10001'. Anything genuinely fractional is not a
        # postcode, ZIP, borough or persona, so it falls to the default.
        return str(int(raw)) if raw.is_integer() else default
    return default


def resolve_query(query):
    """Run a single score query. Returns the response body or an error dict."""
    postcode = parse_str_param(query.get('postcode'))
    borough_input = parse_str_param(query.get('borough'))
    city = parse_str_param(query.get('city'), 'london').lower()
    persona = parse_str_param(query.get('persona'), 'balanced').lower()
    weights_override = parse_weights(query.get('weights'))
    include = parse_include(query.get('include'))
    # Opt-in to terminated (retired) postcodes, which only the local NSPL
    # tier can serve — postcodes.io 404s them. Off by default, so a
    # terminated row stays a local miss and the response is unchanged.
    # Coerced via parse_bool_flag, not `.strip()`, because a JSON POST body
    # carries this as a native boolean while a GET query string carries it
    # as 'true'/'1'. Both are valid; neither may raise.
    include_terminated = parse_bool_flag(query.get('includeTerminated'))

    if city not in CITIES:
        return {
            'error': f'Unsupported city: {city}',
            'supportedCities': sorted(CITIES.keys()),
        }, 400

    if not postcode and not borough_input:
        return {
            'error': 'Provide either postcode or borough.',
            'example': '/v1/score?postcode=SW11+1AA',
        }, 400

    location_meta = {'city': city}
    if postcode:
        # US ZIP auto-detection, 5 digits with optional +4 suffix.
        # If detected and in the NYC map, override city to 'nyc' and use
        # the static lookup (skipping the UK-only postcodes.io call).
        if US_ZIP_PATTERN.match(postcode):
            zip5 = postcode[:5]
            if zip5 in NYC_ZIP_TO_BOROUGH:
                city = 'nyc'
                borough = NYC_ZIP_TO_BOROUGH[zip5]
                location_meta = {
                    'city': 'nyc',
                    'postcode': postcode,
                    'borough': borough,
                    'region': 'New York City',
                }
                # v3.1, if we have a centroid for this ZIP, surface lat/lon
                # so the per-postcode Haversine layer kicks in for NYC too.
                centroid = NYC_ZIP_CENTROIDS.get(zip5)
                if centroid:
                    location_meta['latitude'] = centroid[0]
                    location_meta['longitude'] = centroid[1]
            else:
                return {
                    'error': f'ZIP not currently supported: {postcode}',
                    'note': 'Sky Score supports NYC ZIPs only at present (Manhattan, Brooklyn, Queens, Bronx, Staten Island).',
                    'supportedNycBoroughs': sorted(NYC_BOROUGHS.keys()),
                }, 404
        else:
            # UK postcode path, the local NSPL table then postcodes.io
            # resolve to a London borough.
            # Un-gated 2026-08-10. This was `if city != 'london': return 400`,
            # and the reason given was that NSPL wrote the borough attribute for
            # London LADs alone. It writes the LAD CODE for all 2.7M rows, so
            # LAD_TO_BOROUGH resolves the rest without a reload - see the note
            # on that map. A postcode in a city we do not score still 404s
            # below, on the borough lookup, which is the honest place for it.
            if city not in CITIES:
                return {
                    'error': f'Unsupported city: {city}',
                }, 400
            pc = lookup_postcode(postcode, include_terminated=include_terminated)
            if not pc:
                # Wording deliberately unchanged (audit L5). This string is a
                # public API surface — it is what score-demo/openapi.yaml
                # documents for 404 — and the whole NSPL feature is built on
                # the promise that an unset POSTCODE_TABLE leaves behaviour
                # byte-identical. Changing it would break that promise
                # unconditionally, before the table even exists. It also stays
                # factually true once the table is live: a 404 means the NSPL
                # tier deferred and postcodes.io then missed, and postcodes.io
                # 404s terminated postcodes too, so the short-circuited
                # known-terminated case is covered by the same sentence.
                # Revisit only alongside score-demo/openapi.yaml.
                return {
                    'error': f'Postcode not recognised by postcodes.io: {postcode}',
                }, 404
            borough = normalise_borough(pc.get('admin_district'), city)
            location_meta.update(
                {
                    'postcode': pc.get('postcode'),
                    'borough': borough,
                    'longitude': pc.get('longitude'),
                    'latitude': pc.get('latitude'),
                    'region': pc.get('region'),
                }
            )
            if pc.get('_terminated'):
                # Only reachable via ?includeTerminated=true. Every postcode
                # that returns 200 without the flag is live, so no existing
                # response shape changes — these keys appear only on
                # newly-servable queries.
                location_meta['postcodeStatus'] = 'terminated'
                location_meta['postcodeTerminatedDate'] = pc.get('_dotermMonth')
                if pc.get('_gridInd') in (5, 6, 8):
                    # 36.9% of terminated London postcodes carry an imputed,
                    # sector-mean or pre-Gridlink centroid (vs 0.3% of live
                    # ones), which can sit far enough out to cross a noise
                    # contour band.
                    location_meta['positionQuality'] = 'approximate'
    else:
        borough = normalise_borough(borough_input, city)
        location_meta['borough'] = borough

    if not borough or borough not in CITIES[city]['boroughs']:
        return {
            'error': f'Borough not currently supported in {city}.',
            'attemptedBorough': borough_input or location_meta.get('borough'),
            'supportedBoroughs': sorted(CITIES[city]['boroughs'].keys()),
        }, 404

    if weights_override:
        weights = weights_override
        persona_label = 'custom'
    elif persona in PERSONAS:
        weights = PERSONAS[persona]
        persona_label = persona
    else:
        weights = PERSONAS['balanced']
        persona_label = 'balanced'

    # Per-postcode quiet uses the resolved lat/lon when available
    # (postcodes.io for UK postcodes, NYC_ZIP_CENTROIDS for NYC ZIPs).
    lat = location_meta.get('latitude')
    lon = location_meta.get('longitude')
    # postcode_clean is used by the v3.1 raster lookup as the DynamoDB key
    pc_clean = (location_meta.get('postcode') or postcode or '').strip().upper().replace(' ', '')
    score_data = calc_score(borough, city, weights, lat=lat, lon=lon, postcode_clean=pc_clean)

    comparison = None
    comparison_unavailable = None
    if parse_str_param(query.get('compare')).lower() == 'previous':
        prev_set = previous_dataset(city)
        if prev_set is None:
            # Saying nothing would leave the caller assuming the parameter was
            # ignored; reporting zero change would assert a measurement nobody
            # took. Neither is acceptable, so the response says why explicitly.
            comparison_unavailable = (
                f'{CITIES[city]["name"]} entered the dataset after {PREVIOUS_VINTAGE}, '
                'so no prior vintage exists to compare against. Reporting zero '
                'change here would imply a measurement that was never taken.'
            )
        else:
            prev_data = calc_score(
                borough,
                city,
                weights,
                lat=lat,
                lon=lon,
                postcode_clean=pc_clean,
                boroughs_override=prev_set,
            )
            comparison = build_comparison(score_data, prev_data, city, borough)

    body = {
        **score_data,
        **({'comparison': comparison} if comparison is not None else {}),
        **({'comparisonUnavailable': comparison_unavailable} if comparison_unavailable else {}),
        'location': location_meta,
        'persona': persona_label,
        'weights': weights,
        'methodologyVersion': METHODOLOGY_VERSION,
        'methodologyUrl': METHODOLOGY_URL,
        'apiVersion': API_VERSION,
        'generatedAt': datetime.now(UTC).isoformat(),
        'sources': build_sources(city, bd=_borough_record(city, borough)),
        'sourceBreakdown': build_source_breakdown(city),
    }
    # Roadmap-visible placeholder components, let prospects see what's planned
    # before they ask. Each entry has a status flag so integrators don't try
    # to consume placeholder data as if it were live.
    body['plannedComponents'] = {
        'flood': {
            'status': 'planned',
            'source': 'Environment Agency Flood Map for Planning (planned, OGL v3.0)',
            'eta': 'roadmap',
        },
        'airQuality': {
            'status': 'planned',
            'source': 'DEFRA Daily Air Quality Index (planned, OGL v3.0)',
            'eta': 'roadmap',
        },
        'epcDistribution': {
            'status': 'planned',
            'source': 'MHCLG Get Energy Performance Data (currently in /epc; planned in /v1/score)',
            'eta': 'roadmap',
        },
        'crimeBreakdown': {
            'status': 'planned',
            'source': 'ONS LSOA-level crime by category (planned, OGL v3.0)',
            'eta': 'roadmap',
        },
    }
    return filter_response(body, include), 200


def handle_options():
    """CORS preflight response. Open to any origin, the GET/POST are
    API-key gated, so origin restriction adds no security."""
    return {
        'statusCode': 200,
        'headers': cors_headers(),
        'body': '',
    }


def handle_regions(event):
    """GET /v1/regions, discovery endpoint listing supported geographies.
    Used by integrators to know what's queryable without scraping responses.

    Built by iterating CITIES. This was previously a hand-written literal naming
    London and NYC only, so adding Greater Manchester to CITIES produced an API
    that would score a city it refused to admit supporting — the discovery
    endpoint denying a geography /v1/score answers on. Deriving it means the
    failure mode cannot recur: a city is discoverable because it is scoreable,
    not because someone remembered to add it twice.

    Iteration order is CITIES' declaration order, not sorted, so adding a city
    appends rather than reshuffling an existing integrator's list.
    """
    cities = []
    for city_id, cfg in CITIES.items():
        entry = {
            'id': city_id,
            'name': cfg['name'],
            'country': cfg['country'],
            'currency': cfg['currency'],
            'postcodeFormat': cfg['postcodeFormat'],
            'postcodeResolver': cfg['postcodeResolver'](),
            'boroughCount': len(cfg['boroughs']),
            'boroughs': sorted(cfg['boroughs'].keys()),
        }
        if 'extra' in cfg:
            entry.update(cfg['extra']())
        cities.append(entry)
    return response(
        200,
        {
            'cities': cities,
            'apiVersion': API_VERSION,
            'methodologyVersion': METHODOLOGY_VERSION,
            'methodologyUrl': METHODOLOGY_URL,
            'generatedAt': datetime.now(UTC).isoformat(),
        },
    )


def handle_changes(event):
    """GET /v1/changes — quarter-over-quarter movement for every London
    borough under balanced weights.

    Public (no API key): the underlying tables are already public via the
    consumer site, and this is the shareable 'what moved this quarter'
    surface. Note this is the ONLY key-free route on this function —
    /v1/regions carries `ApiKeyRequired: true` in template.yaml despite an
    earlier version of this docstring citing it as a fellow public endpoint.

    Each borough carries an `attribution` breakdown and a derived
    `explanation`, so "why did this move?" is answerable from the response
    without a second call."""
    bal = PERSONAS['balanced']
    prev_set = previous_dataset('london')
    cur_bm = benchmarks(CITIES['london']['boroughs'])
    prev_bm = benchmarks(prev_set)
    cur_ranks = growth_ranks(CITIES['london']['boroughs'])
    prev_ranks = growth_ranks(prev_set)
    market = market_context(CITIES['london']['boroughs'], prev_set)
    changes = []
    for name in CITIES['london']['boroughs']:
        cur = calc_score(name, 'london', bal)
        prev = calc_score(name, 'london', bal, boroughs_override=prev_set)
        attribution = build_attribution(cur, prev, bal)
        attribution_sum = round(sum(f['contribution'] for f in attribution), 2)
        score_change = round(cur['score'] - prev['score'], 1)
        changes.append(
            {
                'borough': name,
                'score': cur['score'],
                'previousScore': prev['score'],
                'scoreChange': round(cur['score'] - prev['score'], 1),
                'avgPriceGbp': cur['context']['avgPriceGbp'],
                'previousAvgPriceGbp': prev['context']['avgPriceGbp'],
                'priceChangePct': round(
                    (cur['context']['avgPriceGbp'] - prev['context']['avgPriceGbp'])
                    / prev['context']['avgPriceGbp']
                    * 100,
                    1,
                ),
                'trendPct': cur['context']['priceTrendPct'],
                'previousTrendPct': prev['context']['priceTrendPct'],
                'components': cur['components'],
                'previousComponents': prev['components'],
                # Why the score moved, decomposed. Contributions sum to
                # scoreChange (to rounding), so a reader can check the claim
                # rather than take it.
                'attribution': attribution,
                # Stated rather than left for the reader to discover: the
                # contributions are built from published 1dp components, so
                # they reconcile against scoreChange only to within rounding.
                # Publishing both numbers makes the gap auditable instead of
                # looking like an arithmetic error.
                'attributionSum': attribution_sum,
                'roundingResidual': round(score_change - attribution_sum, 2),
                'explanation': describe_change(
                    cur, prev, 'london', bal, name, cur_bm, prev_bm, cur_ranks, prev_ranks
                ),
                'why': build_why(cur, prev, 'london', bal, name, cur_bm, prev_bm, cur_ranks, prev_ranks),
            }
        )
    changes.sort(key=lambda c: abs(c['scoreChange']), reverse=True)
    moved = [c for c in changes if abs(c['scoreChange']) > 0.5]
    risers = [c for c in changes if c['scoreChange'] > 0]
    fallers = [c for c in changes if c['scoreChange'] < 0]
    return response(
        200,
        {
            'city': 'london',
            'persona': 'balanced',
            'currentVintage': SNAPSHOT_VINTAGE,
            'previousVintage': PREVIOUS_VINTAGE,
            'refreshedAt': SNAPSHOT_REFRESHED_AT,
            'note': COMPARISON_NOTE,
            # Published so a caller can reproduce every `attribution`
            # contribution as weight x component change, and verify the parts
            # sum to scoreChange.
            'weights': bal,
            # The city-wide picture, so a reader can see that most boroughs fell
            # because the market fell — without it, 25 of 33 dropping reads as a
            # scoring fault rather than a description of the quarter.
            'marketContext': market,
            'attributionNote': (
                'Each attribution contribution is the factor weight multiplied by the change in that '
                'factor, so contributions sum to scoreChange to within rounding of the 1dp component '
                'values. Only price and trend move between quarterly vintages, so Affordability and '
                'Growth are the only factors that can appear.'
            ),
            'summary': {
                'boroughs': len(changes),
                'movedOverHalfPoint': len(moved),
                'risers': len(risers),
                'fallers': len(fallers),
                'largestRise': max(changes, key=lambda c: c['scoreChange'])['borough'],
                'largestFall': min(changes, key=lambda c: c['scoreChange'])['borough'],
            },
            'changes': changes,
            'methodologyVersion': METHODOLOGY_VERSION,
            'methodologyUrl': METHODOLOGY_URL,
            'apiVersion': API_VERSION,
            'generatedAt': datetime.now(UTC).isoformat(),
            # /v1/changes covers the London cohort only — previous_dataset() has
            # no vintage for any other city — so London's provenance is the
            # accurate claim here rather than a default that happens to fit.
            'sources': build_sources('london'),
        },
    )


def handle_environment(event):
    """GET /v1/environment?lat=&lon= — measured readings for a coordinate.

    WHY THIS EXISTS. The browser extension reads a property listing and gets
    COORDINATES. /v1/score, /epc and /sold-prices are all postcode-keyed, so
    none of today's environmental data could reach a listing page. This closes
    that with the one thing the extension cannot do for itself: turn a point
    into a postcode.

    UNAUTHENTICATED, like /transport and /nhs and unlike /v1/score. The
    extension is a public artefact — anything bundled in it is readable by
    anyone who unzips the .crx — so a key-gated route is unusable there. This
    returns measurements, not the scoring engine's output: no weights, no
    persona, no total. The product remains behind the key.

    It reuses _lookup_noise_row and build_environment, so a reading here cannot
    disagree with the same reading inside a /v1/score response.
    """
    params = event.get('queryStringParameters') or {}
    try:
        lat = float(params.get('lat'))
        lon = float(params.get('lon'))
    except (TypeError, ValueError):
        return response(400, {'error': 'lat and lon are required and must be numbers.'})

    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return response(400, {'error': 'lat/lon out of range.'})

    pc = reverse_geocode(lat, lon)
    if not pc:
        return response(
            404,
            {
                'error': 'No UK postcode found near those coordinates.',
                'location': {'lat': lat, 'lon': lon},
            },
        )

    postcode_clean = pc.replace(' ', '').upper()
    noise_row = _lookup_noise_row(postcode_clean)
    env = build_environment(noise_row, postcode_clean)

    # Aircraft quiet is derived rather than stored, so it is computed here
    # through the same ramp /v1/score uses. Absent when DEFRA did not measure
    # this postcode — 91% of London — and absent means the key is missing, not
    # null or a default.
    aircraft_lden = lden_from_row(noise_row, postcode_clean)
    if aircraft_lden is not None:
        env['aircraftNoiseLdenDb'] = round(aircraft_lden, 1)
        env['aircraftQuiet'] = lden_db_to_quiet(aircraft_lden)
        # Same WHO 2018 document as the road figure above; this is the value
        # _QUIET_CEILING_DB is already anchored on, restated so a consumer does
        # not have to know the scoring internals to read the decibels.
        env['aircraftNoiseWhoGuidelineDb'] = 45
        # "Round 4 (2022)" reads as 2022 DATA. It is not: Round 4 was published
        # in 2022 and maps 2021, which DEFRA's own documentation calls "a highly
        # anomalous situation" because of COVID travel restrictions. Naming the
        # publication year alone implies a representative year and understates
        # nothing visibly - the reader simply believes a wrong thing.
        env['aircraftNoiseSource'] = (
            'DEFRA Strategic Noise Mapping Round 4, aircraft Lden. '
            'Published 2022, maps 2021 - a COVID-affected year, so readings err quiet.'
        )

    notices = []
    if aircraft_lden is None:
        # DEFRA measures about 9% of London postcodes, so this branch is the
        # common one — roughly 91% of lookups. Returning nothing but an apology
        # made the section empty for almost everyone, and a notice that nearly
        # every user always sees stops being read.
        #
        # /v1/score already computes a geometric estimate for exactly these
        # postcodes (quietResolution 'postcode'), from distance to airports and
        # flight-path geometry. Surfacing it, clearly labelled as an estimate,
        # is more useful than silence and still not a claim to have measured.
        # Same function the score uses, so the two cannot disagree.
        estimated = calc_postcode_quiet(lat, lon, 'london', postcode_clean)
        if estimated is not None:
            env['aircraftQuietEstimated'] = estimated
            env['aircraftQuietBasis'] = 'flight-path geometry, not measured'
        notices.append(_COVERAGE_NOTICES['postcode'])
    if 'roadNoiseLdenDb' not in env:
        notices.append(
            'Road noise has not been measured for this postcode, or is still '
            'being loaded. No figure is shown rather than an assumed one.'
        )

    return response(
        200,
        {
            'location': {'lat': lat, 'lon': lon, 'postcode': pc},
            'environment': env,
            'notices': notices,
            'apiVersion': API_VERSION,
            'methodologyVersion': METHODOLOGY_VERSION,
        },
    )


def handle_get(event):
    path = (event.get('path') or '').rstrip('/')
    if path.endswith('/regions'):
        return handle_regions(event)
    if path.endswith('/changes'):
        return handle_changes(event)
    if path.endswith('/environment'):
        return handle_environment(event)
    params = event.get('queryStringParameters') or {}
    body, status = resolve_query(params)
    return response(status, body)


def handle_batch(event):
    raw_body = event.get('body') or ''
    if event.get('isBase64Encoded'):
        import base64

        try:
            raw_body = base64.b64decode(raw_body).decode()
        except (ValueError, UnicodeDecodeError) as exc:
            logger.warning('Invalid base64 body: %s', exc)
            return response(400, {'error': 'Invalid base64-encoded body'})

    try:
        payload = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError:
        return response(400, {'error': 'Invalid JSON body'})

    queries = payload.get('queries')
    if not isinstance(queries, list):
        return response(
            400,
            {
                'error': 'Body must contain a "queries" array.',
                'example': {
                    'queries': [
                        {'postcode': 'SW11 1AA', 'persona': 'balanced'},
                        {'postcode': 'TW3 4DX', 'persona': 'family'},
                        {
                            'borough': 'Hackney',
                            'city': 'london',
                            'weights': {'quiet': 0.5, 'afford': 0.2, 'growth': 0.1, 'live': 0.2},
                        },
                    ],
                },
            },
        )

    if len(queries) == 0:
        return response(400, {'error': 'queries array is empty.'})

    if len(queries) > MAX_BATCH_SIZE:
        return response(
            400,
            {
                'error': f'Batch size exceeds limit of {MAX_BATCH_SIZE} queries.',
                'submitted': len(queries),
                'limit': MAX_BATCH_SIZE,
            },
        )

    # Parallel resolution. Each `resolve_query` call hits postcodes.io
    # (network-bound, ~100-500 ms p95). Sequential at MAX_BATCH_SIZE=100
    # would blow the 10s Lambda timeout above ~30 unique postcodes.
    # ThreadPoolExecutor with bounded workers gives us request-level
    # concurrency without overwhelming postcodes.io (which is generous
    # but unspecified on per-IP limits) or hitting Python GIL pressure.
    from concurrent.futures import ThreadPoolExecutor

    indexed_queries = list(enumerate(queries))

    def run_one(item):
        idx, query = item
        if not isinstance(query, dict):
            return idx, ({'error': 'Query must be an object.'}, 400)
        try:
            return idx, resolve_query(query)
        except Exception as exc:  # noqa: BLE001 — per-query blast radius containment
            # The batch contract (score-demo/openapi.yaml) promises "failures
            # do not abort the batch". Without this guard any exception from
            # one query escapes ex.map(), unwinds handle_batch, and the
            # handler's catch-all 500s all 100 queries — 99 of which were
            # perfectly resolvable (audit L1). Report this query's slot as a
            # per-item error in the shape the loop below already consumes and
            # let its siblings through.
            logger.exception('Batch query %s failed: %s', idx, exc)
            return idx, ({'error': 'Internal server error'}, 500)

    with ThreadPoolExecutor(max_workers=BATCH_PARALLELISM) as ex:
        outcomes = list(ex.map(run_one, indexed_queries))

    # Restore original order, ex.map preserves order so we don't strictly
    # need this, but being explicit makes future refactors safer.
    outcomes.sort(key=lambda kv: kv[0])

    results = []
    success = 0
    error = 0
    for idx, (body, status) in outcomes:
        result = {'queryIndex': idx, 'status': status}
        if status == 200:
            result.update(body)
            success += 1
        else:
            result['error'] = body.get('error', 'Unknown error')
            for k in ('attemptedBorough', 'supportedBoroughs', 'supportedCities', 'example'):
                if k in body:
                    result[k] = body[k]
            error += 1
        results.append(result)

    return response(
        200,
        {
            'totalQueries': len(queries),
            'successCount': success,
            'errorCount': error,
            'apiVersion': API_VERSION,
            'methodologyVersion': METHODOLOGY_VERSION,
            'generatedAt': datetime.now(UTC).isoformat(),
            # A batch may span cities; credit only those that actually answered.
            'sources': build_batch_sources(
                r.get('location', {}).get('city') for r in results
            ),
            'results': results,
        },
    )


def handler(event, context):
    method = (event.get('httpMethod') or 'GET').upper()
    try:
        if method == 'OPTIONS':
            return handle_options()
        if method == 'POST':
            return handle_batch(event)
        return handle_get(event)
    except Exception as exc:  # final guard, never let internals leak
        logger.exception('Unhandled exception in score handler: %s', exc)
        return response(500, {'error': 'Internal server error'})


def cors_headers():
    return {
        'Access-Control-Allow-Origin': CORS_ORIGIN,
        'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type,X-Api-Key',
        'Access-Control-Max-Age': '86400',
    }


def response(status, body):
    return {
        'statusCode': status,
        'headers': {
            'Content-Type': 'application/json',
            **cors_headers(),
        },
        'body': json.dumps(body),
    }
