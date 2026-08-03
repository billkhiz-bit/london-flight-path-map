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
        'trend': -1.1,
        'schools': 'good',
        'crimeRate': 87.4,
        'p8': 0.45,
        'transport': 'good',
        'healthcare': 'good',
    },
    'Hillingdon': {
        'impact': 'severe',
        'avgPrice': 468000,
        'trend': 0.6,
        'schools': 'good',
        'crimeRate': 91.6,
        'p8': 0.24,
        'transport': 'good',
        'healthcare': 'good',
    },
    'Richmond upon Thames': {
        'impact': 'high',
        'avgPrice': 789000,
        'trend': -1.3,
        'schools': 'excellent',
        'crimeRate': 57.3,
        'p8': 0.4,
        'transport': 'good',
        'healthcare': 'good',
    },
    'Ealing': {
        'impact': 'high',
        'avgPrice': 569000,
        'trend': -0.3,
        'schools': 'good',
        'crimeRate': 80.5,
        'p8': 0.62,
        'transport': 'excellent',
        'healthcare': 'good',
    },
    'Wandsworth': {
        'impact': 'moderate',
        'avgPrice': 660000,
        'trend': -4.2,
        'schools': 'excellent',
        'crimeRate': 76.4,
        'p8': 0.33,
        'transport': 'excellent',
        'healthcare': 'good',
    },
    'Lambeth': {
        'impact': 'moderate',
        'avgPrice': 545000,
        'trend': -0.2,
        'schools': 'good',
        'crimeRate': 114.4,
        'p8': 0.01,
        'transport': 'excellent',
        'healthcare': 'good',
    },
    'Lewisham': {
        'impact': 'low-moderate',
        'avgPrice': 497000,
        'trend': 4.8,
        'schools': 'good',
        'crimeRate': 94.2,
        'p8': 0.0,
        'transport': 'good',
        'healthcare': 'good',
    },
    'Greenwich': {
        'impact': 'moderate',
        'avgPrice': 463000,
        'trend': 2.3,
        'schools': 'good',
        'crimeRate': 90.3,
        'p8': -0.01,
        'transport': 'good',
        'healthcare': 'good',
    },
    'Tower Hamlets': {
        'impact': 'low-moderate',
        'avgPrice': 444000,
        'trend': -11.0,
        'schools': 'good',
        'crimeRate': 106.6,
        'p8': 0.21,
        'transport': 'excellent',
        'healthcare': 'excellent',
    },
    'Camden': {
        'impact': 'low',
        'avgPrice': 806000,
        'trend': -3.9,
        'schools': 'excellent',
        'crimeRate': 173.3,
        'p8': -0.03,
        'transport': 'excellent',
        'healthcare': 'excellent',
    },
    'Islington': {
        'impact': 'low',
        'avgPrice': 670000,
        'trend': -4.4,
        'schools': 'good',
        'crimeRate': 131.2,
        'p8': -0.03,
        'transport': 'excellent',
        'healthcare': 'good',
    },
    'Hackney': {
        'impact': 'low',
        'avgPrice': 608000,
        'trend': 2.8,
        'schools': 'good',
        'crimeRate': 116.5,
        'p8': 0.34,
        'transport': 'excellent',
        'healthcare': 'good',
    },
    'Barnet': {
        'impact': 'low-moderate',
        'avgPrice': 591000,
        'trend': -2.4,
        'schools': 'excellent',
        'crimeRate': 67.8,
        'p8': 0.64,
        'transport': 'good',
        'healthcare': 'good',
    },
    'Croydon': {
        'impact': 'moderate',
        'avgPrice': 397000,
        'trend': 1.6,
        'schools': 'good',
        'crimeRate': 80.4,
        'p8': 0.01,
        'transport': 'good',
        'healthcare': 'good',
    },
    'Bromley': {
        'impact': 'low',
        'avgPrice': 525000,
        'trend': 1.5,
        'schools': 'excellent',
        'crimeRate': 69.1,
        'p8': 0.04,
        'transport': 'moderate',
        'healthcare': 'good',
    },
    'Newham': {
        'impact': 'moderate-high',
        'avgPrice': 405000,
        'trend': 1.2,
        'schools': 'good',
        'crimeRate': 104.0,
        'p8': 0.25,
        'transport': 'excellent',
        'healthcare': 'good',
    },
    'Southwark': {
        'impact': 'low-moderate',
        'avgPrice': 579000,
        'trend': 3.8,
        'schools': 'good',
        'crimeRate': 120.8,
        'p8': 0.38,
        'transport': 'excellent',
        'healthcare': 'excellent',
    },
    'Hammersmith and Fulham': {
        'impact': 'moderate-high',
        'avgPrice': 729000,
        'trend': -9.2,
        'schools': 'excellent',
        'crimeRate': 107.0,
        'p8': 0.47,
        'transport': 'excellent',
        'healthcare': 'good',
    },
    'Kensington and Chelsea': {
        'impact': 'moderate',
        'avgPrice': 1256000,
        'trend': -9.5,
        'schools': 'excellent',
        'crimeRate': 145.8,
        'p8': 0.3,
        'transport': 'excellent',
        'healthcare': 'excellent',
    },
    'Brent': {
        'impact': 'low-moderate',
        'avgPrice': 549000,
        'trend': -1.5,
        'schools': 'good',
        'crimeRate': 89.3,
        'p8': 0.61,
        'transport': 'good',
        'healthcare': 'good',
    },
    'Haringey': {
        'impact': 'low',
        'avgPrice': 634000,
        'trend': 4.8,
        'schools': 'good',
        'crimeRate': 104.6,
        'p8': 0.21,
        'transport': 'good',
        'healthcare': 'moderate',
    },
    'Waltham Forest': {
        'impact': 'low',
        'avgPrice': 524000,
        'trend': 5.0,
        'schools': 'good',
        'crimeRate': 80.2,
        'p8': -0.06,
        'transport': 'good',
        'healthcare': 'moderate',
    },
    'Merton': {
        'impact': 'low-moderate',
        'avgPrice': 597000,
        'trend': 0.5,
        'schools': 'good',
        'crimeRate': 59.3,
        'p8': 0.59,
        'transport': 'good',
        'healthcare': 'good',
    },
    'Redbridge': {
        'impact': 'low',
        'avgPrice': 496000,
        'trend': 4.0,
        'schools': 'excellent',
        'crimeRate': 74.3,
        'p8': 0.5,
        'transport': 'good',
        'healthcare': 'good',
    },
    'Enfield': {
        'impact': 'low',
        'avgPrice': 469000,
        'trend': 1.0,
        'schools': 'good',
        'crimeRate': 85.2,
        'p8': 0.21,
        'transport': 'moderate',
        'healthcare': 'moderate',
    },
    'Kingston upon Thames': {
        'impact': 'low-moderate',
        'avgPrice': 582000,
        'trend': 1.3,
        'schools': 'excellent',
        'crimeRate': 66.8,
        'p8': 0.58,
        'transport': 'good',
        'healthcare': 'good',
    },
    'Sutton': {
        'impact': 'low',
        'avgPrice': 445000,
        'trend': 2.3,
        'schools': 'excellent',
        'crimeRate': 60.3,
        'p8': 0.51,
        'transport': 'moderate',
        'healthcare': 'good',
    },
    'Westminster': {
        'impact': 'moderate',
        'avgPrice': 836000,
        'trend': -20.8,
        'schools': 'good',
        'crimeRate': 355.5,
        'p8': 0.48,
        'transport': 'excellent',
        'healthcare': 'excellent',
    },
    'City of London': {
        'impact': 'low-moderate',
        'avgPrice': 627000,
        'trend': -28.2,
        'schools': 'good',
        'crimeRate': 190,
        'transport': 'excellent',
        'healthcare': 'good',
    },
    'Barking and Dagenham': {
        'impact': 'low',
        'avgPrice': 361000,
        'trend': 0.9,
        'schools': 'good',
        'crimeRate': 84.2,
        'p8': 0.24,
        'transport': 'good',
        'healthcare': 'moderate',
    },
    'Havering': {
        'impact': 'low',
        'avgPrice': 453000,
        'trend': 3.3,
        'schools': 'good',
        'crimeRate': 68.3,
        'p8': -0.09,
        'transport': 'moderate',
        'healthcare': 'good',
    },
    'Bexley': {
        'impact': 'low',
        'avgPrice': 409000,
        'trend': 2.7,
        'schools': 'good',
        'crimeRate': 60.2,
        'p8': -0.06,
        'transport': 'moderate',
        'healthcare': 'good',
    },
    'Harrow': {
        'impact': 'low',
        'avgPrice': 530000,
        'trend': 2.3,
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
            (51.505, -0.25),
            (51.495, -0.32),
            (51.485, -0.38),
            (51.4775, -0.428),
        ],
    },
    {
        'name': 'Biggin Stack',
        'airport': 'LHR',
        'type': 'arrival',
        'coords': [
            (51.425, -0.22),
            (51.44, -0.28),
            (51.45, -0.34),
            (51.46, -0.39),
            (51.4644, -0.428),
        ],
    },
    {
        'name': 'Ockham Stack',
        'airport': 'LHR',
        'type': 'arrival',
        'coords': [
            (51.37, -0.435),
            (51.4, -0.435),
            (51.42, -0.435),
            (51.44, -0.435),
            (51.4644, -0.435),
        ],
    },
    {
        'name': 'Bovingdon Stack',
        'airport': 'LHR',
        'type': 'arrival',
        'coords': [
            (51.6, -0.49),
            (51.56, -0.48),
            (51.53, -0.47),
            (51.505, -0.46),
            (51.4775, -0.45),
        ],
    },
    {
        'name': 'Dep West',
        'airport': 'LHR',
        'type': 'departure',
        'coords': [
            (51.4775, -0.489),
            (51.48, -0.55),
            (51.485, -0.62),
            (51.49, -0.7),
        ],
    },
    {
        'name': 'Dep SE (Detling)',
        'airport': 'LHR',
        'type': 'departure',
        'coords': [
            (51.4775, -0.428),
            (51.47, -0.35),
            (51.46, -0.25),
            (51.445, -0.15),
        ],
    },
    {
        'name': 'Dep NE (BPK)',
        'airport': 'LHR',
        'type': 'departure',
        'coords': [
            (51.4775, -0.428),
            (51.49, -0.35),
            (51.51, -0.25),
            (51.53, -0.15),
        ],
    },
    {
        'name': 'Approach East',
        'airport': 'LCY',
        'type': 'arrival',
        'coords': [
            (51.48, 0.2),
            (51.485, 0.17),
            (51.488, 0.14),
            (51.492, 0.11),
            (51.497, 0.09),
            (51.502, 0.07),
            (51.5053, 0.0553),
        ],
    },
    {
        'name': 'Approach West',
        'airport': 'LCY',
        'type': 'arrival',
        'coords': [
            (51.52, -0.02),
            (51.517, -0.005),
            (51.513, 0.01),
            (51.51, 0.025),
            (51.508, 0.04),
            (51.5053, 0.0553),
        ],
    },
    {
        'name': 'Dep East',
        'airport': 'LCY',
        'type': 'departure',
        'coords': [
            (51.5053, 0.067),
            (51.505, 0.09),
            (51.503, 0.12),
            (51.498, 0.16),
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
            (40.60, -73.60),
            (40.61, -73.64),
            (40.62, -73.68),
            (40.63, -73.72),
            (40.64, -73.76),
            (40.6413, -73.7781),
        ],
    },
    {
        'name': 'JFK 13R Departure',
        'airport': 'JFK',
        'type': 'departure',
        'freq': 'high',
        'coords': [(40.6413, -73.7781), (40.62, -73.76), (40.60, -73.74), (40.58, -73.72), (40.56, -73.70)],
    },
    {
        'name': 'JFK 22L Arrival (ILS)',
        'airport': 'JFK',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [(40.70, -73.70), (40.69, -73.72), (40.68, -73.74), (40.66, -73.76), (40.6413, -73.7781)],
    },
    {
        'name': 'LGA 31 Arrival',
        'airport': 'LGA',
        'type': 'arrival',
        'freq': 'high',
        'coords': [(40.72, -73.80), (40.73, -73.82), (40.74, -73.84), (40.76, -73.86), (40.7769, -73.8740)],
    },
    {
        'name': 'LGA 4 Departure',
        'airport': 'LGA',
        'type': 'departure',
        'freq': 'high',
        'coords': [(40.7769, -73.8740), (40.79, -73.87), (40.81, -73.86), (40.83, -73.85), (40.86, -73.84)],
    },
    {
        'name': 'LGA Expressway Visual 31',
        'airport': 'LGA',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [(40.78, -73.95), (40.78, -73.93), (40.78, -73.91), (40.78, -73.89), (40.7769, -73.8740)],
    },
    {
        'name': 'EWR 4R Arrival',
        'airport': 'EWR',
        'type': 'arrival',
        'freq': 'high',
        'coords': [(40.62, -74.10), (40.64, -74.12), (40.66, -74.14), (40.68, -74.16), (40.6895, -74.1745)],
    },
    {
        'name': 'EWR 22L Departure',
        'airport': 'EWR',
        'type': 'departure',
        'freq': 'medium',
        'coords': [(40.6895, -74.1745), (40.68, -74.18), (40.66, -74.19), (40.64, -74.20), (40.62, -74.22)],
    },
]

CITY_GEOMETRY = {
    'london': {
        'airports': AIRPORTS_LONDON,
        'paths': FLIGHT_PATHS_LONDON,
        'major_airport': 'LHR',
        'secondary_airport': None,
    },
    'nyc': {'airports': AIRPORTS_NYC, 'paths': FLIGHT_PATHS_NYC, 'major_airport': 'JFK', 'secondary_airport': 'LGA'},
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
# WHAT WOULD LET THIS BE LIFTED. Two things, and the nodata fix alone is not
# enough:
#   1. Rows reloaded (or read through the _RASTER_NODATA_FILL guard) so uncovered
#      postcodes fall through to Haversine rather than posing as raster hits.
#      Done in code; the table itself still holds the old fills.
#   2. lden_db_to_quiet's bands revisited. TW61AP has a GENUINE 58.2 dB sample,
#      and the bands map that to quiet 7.5 — an airport scoring "fairly quiet".
#      WHO's 2018 environmental noise guideline for aircraft is 45 dB Lden, well
#      below this scale's 55 dB top band, so the mapping is the open question,
#      not the data.
# scripts/check_score_sanity.py asserts an airport scores <= 3.0, so lifting the
# flag prematurely fails that check rather than silently shipping.
RASTER_TIER_QUARANTINED = True

# The legacy nodata fill written by scripts/load_defra_raster.py before
# 2026-08-03. Not a measurement — the raster's minimum real value is 40.0 dB.
_RASTER_NODATA_FILL = 35.0


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
    if value == _RASTER_NODATA_FILL:
        return None
    _raster_cache_put(postcode_clean, value)
    return value


def lden_db_to_quiet(lden):
    """Convert dB Lden to a 0-10 quiet score using the same band mapping
    documented in METHODOLOGY.md §4.1. Used by v3.1 raster path."""
    if lden is None:
        return None
    if lden < 55:
        return 10.0
    if lden < 60:
        return 7.5
    if lden < 65:
        return 5.0
    if lden < 70:
        return 3.0
    if lden < 75:
        return 1.5
    return 0.0


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

    # 1. Distance to nearest airport
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
            'Borough metadata: ONS (Crime in England and Wales, Police Force Area data tables, Table C4) and Department for Education (Key Stage 4 Progress 8), Open Government Licence v3.0',
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
}


def build_sources(city='london'):
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
    return [line() if callable(line) else line for line in prov['sources']]


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


def get_live_score(bd):
    """Liveability composite: schools 35%, crime 30%, transport 25%, health 10%.

    Each absent input falls back to 5.0, and **5.0 is not neutral**. London's
    computed live scores span 5.5-8.8, so the fallback sits below the entire
    observed range: a borough with no liveability data scores worse than the
    weakest borough that has some, and filling in a single below-average field
    can push it lower still. Partial data is worse than none.

    The fallback is retained because a live API must answer, but the number it
    produces is structural rather than a claim about the place. live_resolution()
    is what lets a caller tell those two apart, and the response carries it.
    """
    # Progress 8 where it exists (English LAs), the legacy categorical band
    # otherwise. New York has neither Ofsted nor DfE, so it keeps the curated
    # tier — declared in CITY_PROVENANCE rather than passed off as DfE.
    p8 = bd.get('p8')
    sch = school_score(p8) if p8 is not None else SCHOOL_SCORE.get(bd.get('schools'), 5)
    crm = crime_to_score(bd.get('crimeRate'))
    trn = TRANSPORT_SCORE.get(bd.get('transport'), 5)
    hlt = HEALTH_SCORE.get(bd.get('healthcare'), 5)
    return round((sch * 0.35 + crm * 0.30 + trn * 0.25 + hlt * 0.10) * 10) / 10


def live_resolution(bd):
    """How much of the liveability composite is measured rather than defaulted.

    Mirrors quietResolution: the response states how an answer was reached, not
    only what it was. 'unavailable' means every input hit the 5.0 placeholder, so
    the component says nothing about the location — the distinction that made
    Greater Manchester's uniform 5.0 read as a finding rather than a gap.
    """
    # 'p8' satisfies the schools slot on its own — an English borough carrying
    # Progress 8 has a *better* schools input than one carrying the legacy band,
    # so counting only the categorical field would under-report resolution.
    present = sum(
        1 for f in _LIVE_FIELDS
        if bd.get(f) is not None or (f == 'schools' and bd.get('p8') is not None)
    )
    if present == len(_LIVE_FIELDS):
        return 'measured'
    if present == 0:
        return 'unavailable — all inputs defaulted to 5.0 placeholder'
    return f'partial — {present}/{len(_LIVE_FIELDS)} inputs measured, rest defaulted to 5.0'


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

    if lat is not None and lon is not None:
        # Try raster first (v3.1), Haversine second (v3.0), borough last
        raster_lden = _lookup_lden_raster(postcode_clean) if postcode_clean else None
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

    live = get_live_score(bd)

    total = quiet * weights['quiet'] + afford * weights['afford'] + growth * weights['growth'] + live * weights['live']

    currency_field = 'avgPriceUsd' if CITIES[city]['currency'] == 'USD' else 'avgPriceGbp'

    return {
        'score': round(total * 10) / 10,
        'components': {
            'quiet': round(quiet * 10) / 10,
            'afford': round(afford * 10) / 10,
            'growth': round(growth * 10) / 10,
            'live': round(live * 10) / 10,
        },
        'context': {
            currency_field: bd['avgPrice'],
            'priceTrendPct': bd['trend'],
            'noiseImpactBand': bd['impact'],
            'quietResolution': quiet_source,
            'liveResolution': live_resolution(bd),
        },
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
        'admin_district': item.get('b', {}).get('S'),
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
            if city != 'london':
                return {
                    'error': f'Postcode resolution is UK-only for non-NYC ZIPs. For {city} use ?borough=, or pass a 5-digit US ZIP for NYC auto-detection.',
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
        'sources': build_sources(city),
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


def handle_get(event):
    path = (event.get('path') or '').rstrip('/')
    if path.endswith('/regions'):
        return handle_regions(event)
    if path.endswith('/changes'):
        return handle_changes(event)
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
