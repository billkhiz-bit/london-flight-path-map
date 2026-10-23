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

import inspect
import json
import logging
import math
import os
import re
import threading
import time
from collections import OrderedDict
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _log_district(postcode):
    """The postcode DISTRICT for log lines ('SW11 1AA' -> 'SW11'), never the full
    postcode. A full postcode averages ~15 homes and can point at one, and
    privacy.html s2d promises logs hold the district only. Each Lambda deploys
    alone, so each carries this copy; backend/tests/test_log_privacy.py holds
    all of them to the same rule.
    """
    clean = re.sub(r'\s', '', str(postcode or '')).upper()
    # A postcode's SHAPE or nothing: on a free-text input the old rule (drop the
    # last three characters) logged '10DOWNINGSTREET,LONDONSW1A' (audit
    # 2026-10-05 M-2).
    if not re.fullmatch(r'[A-Z]{1,2}[0-9][A-Z0-9]?[0-9][A-Z]{2}', clean):
        return '?'
    return clean[:-3]


def _log_coarse(lat, lon):
    """Coordinates for log lines at 2 dp (~1 km, district-sized), never full
    precision: 4 dp is ~11 m, finer than a postcode. privacy.html s2d promises
    this; backend/tests/test_log_privacy.py holds every Lambda to it.
    """
    try:
        return f'{float(lat):.2f},{float(lon):.2f}'
    except (TypeError, ValueError):
        return '?'


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
#            was 'excellent'. Now DfE Key Stage 4 Progress 8 (2023/24), scored
#            continuously by school_score() on absolute anchors. London goes
#            from 2 distinct schools sub-scores to 25.
#
#   growth   v5.1 (2026-09-15): scored on the REAL-terms 12-month trend, the
#            nominal HPI change deflated by ONS CPIH for the same month, where
#            a national inflation series is held (every sterling city). The
#            5.0 anchor now means "holding its value against prices in
#            general", not "not falling in cash terms". Costed before deciding
#            (scripts/cost_real_growth.py): at CPIH 2.8%, 26 of the 77
#            boroughs the product called "rising" fall in real terms. `trend`
#            stays nominal - it is a published field integrators read - and
#            `trendReal` sits beside it. New York keeps NOMINAL growth: no US
#            inflation series is held, and deflating dollars by a UK index
#            would be a number nobody measured. See real_trend_pct().
#
#   quiet    v5.3 (2026-09-26): corridor geometry DERIVED FROM THE UK AIP and
#            the corridor penalty FITTED. London's corridors were hand-drawn -
#            Ockham and Bovingdon ran due north-south into east-west runways -
#            and are now each runway's published final approach plus the
#            published departure routes (scripts/build_flight_paths.py). The
#            4/3/2/1 corridor ladder is scaled by CORRIDOR_WEIGHT = 0.3, fitted
#            on half of DEFRA's measured postcodes and tested on the other half
#            (scripts/fit_corridor_weight.py): at 1.0 the airport and corridor
#            terms double-counted near every runway. London's geometry-tier
#            error against DEFRA falls 1.879 -> 1.320; held-out, every city
#            with enough measured postcodes improves. DEFRA-measured postcodes
#            and borough bands are unaffected.
#
#   quiet    v5.4 (2026-09-26): the same derivation for the NINE other UK
#            airports. Every runway's final approach from AD 2.12 + AD 2.19 (MAN
#            23L and CWL 12 have no ILS, so their RNP charts' published 3.0 deg
#            VPA), and departures from the SID coding tables where they exist -
#            Birmingham and Newcastle only; the other six publish conventional
#            SIDs whose charts do not extract, and Teesside publishes none. They
#            replace two hand-placed centreline lines per city. Measured before
#            deciding: held-out error against DEFRA 1.431 -> 1.431, fitted
#            weight still 0.30 (DEFRA sees only the runway strip, where old and
#            new coincide); 5.2% of sampled geometry-tier postcodes move, mean
#            -0.02, 0.3% by a point or more, nearly all under the new BHX and
#            NCL departures. Borough bands and area pages are unaffected.
#
#   quiet    v5.5 (2026-10-01): the AIRPORT term is RUNWAY-SHAPED, not a
#            circle. Distance across each airport's runway axis counts
#            AIRPORT_SHAPE_K = 4 times over (see airport_distance_km), because
#            aircraft noise lies in a strip along the runway: measured 3-15 km
#            out, the circle read 3.7 points too LOUD at 30-60 deg off the
#            axis. Fitted with the corridor weight, which refits 0.3 -> 0.5,
#            by scripts/fit_airport_shape.py against DEFRA's strip AND the
#            ground beside it (a blank raster cell inside a DEFRA box is below
#            that raster's floor), under a PER-CITY rule that no city may come
#            to read quieter than DEFRA. Held-out error on the strip 1.431 ->
#            1.141, beside it 1.226 -> 0.770, every city better on both, no
#            city crossing, and fewer readings over a point quieter than DEFRA
#            (23.3% -> 15.8%). k = 6 was more accurate and read quieter than
#            DEFRA in five cities; the pooled figures had hidden that. Borough
#            bands and area pages are unaffected.
#
#   quiet    v5.6 (2026-10-16): NEW YORK'S estimate is FITTED to the Port
#            Authority's noise monitors, like the Bay Area's (Bill's ruling): the
#            FAA's coded routes of the runway directions flown 10%+ of the time
#            (counted from adsb.lol tracks, July-August 2026), runway lobes,
#            fitted sizes (JFK 1.8, LGA 1.35, EWR 1.0, TEB 0.3) and route weight
#            1.0, every airport a major one (see US-QUIET-NYC). The hand-drawn
#            corridors and Heathrow-sized circles read 15 of 17 JFK monitors
#            quieter than measured; the fit reads louder than the monitors on
#            average at all four airports (nested leave-one-out MAE JFK 1.28,
#            LGA 1.25, TEB 1.70; EWR 3.40 on two monitors). The borough bands
#            are derived from it, population-weighted by ZIP area
#            (scripts/build_nyc_impact.py), rounded to the louder band: Queens
#            severe -> high, Brooklyn high -> moderate-high, the Bronx low-moderate
#            -> moderate, Staten Island low -> low-moderate. No UK value moves.
#
#   quiet    v5.7 (2026-10-17): New York's runway use is counted over January-July
#            2026 (every third day, 71 days), the months its monitors cover, not
#            July-August, and a US runway lobe runs RUNWAY_LOBE_KM (15 km) straight
#            out, not endlessly (Bill's ruling). Winter flow adds JFK 31L departures,
#            whose endless line read Lower Manhattan 3-4 points louder where US
#            DOT's 2022 map paints nothing. JFK's north-west monitors (Howard Beach,
#            150th and 165th Avenues) go from 2-3 points quieter than measured to
#            0.0, 0.0 and +1.0; nested leave-one-out MAE JFK 1.28 -> 1.04, sizes
#            JFK 2.05, LGA 1.35, EWR 1.0, TEB 0.3. Queens 1.44 rounds to the louder
#            band, high -> severe; the other four keep theirs. The Bay Area's fit is
#            unchanged. No UK value moves.
METHODOLOGY_VERSION = '5.7'
API_VERSION = '1.0'
MAX_BATCH_SIZE = 100
# Parallel workers for /v1/score/batch. Each query is mostly waiting on
# postcodes.io (network-bound), so ~10 workers gives near-linear speedup
# on the typical 30-50 postcode batch without saturating any upstream.
BATCH_PARALLELISM = int(os.environ.get('BATCH_PARALLELISM', '10'))
# Seconds held back from the invocation deadline before run_one refuses to
# START another batch item. 6 = one worst-case postcodes.io urlopen (5s, the
# timeout every worker may already have in flight when the cutoff lands) plus
# assembly and serialisation of up to 100 results. Without this, a stalled
# postcodes.io made a full batch 100 queries x 5s / 10 workers = 50s of wall
# clock against a 28s Lambda ceiling, and ALL the answers - including the
# ones already computed - were thrown away as a raw 504. The margin only ever
# bites when the batch is already doomed to overrun; a healthy batch finishes
# in single-digit seconds and never reaches it.
_BATCH_DEADLINE_MARGIN_S = 6.0

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

# Methodology v3.8 (2026-08-11). Each airport's noise footprint relative to
# Heathrow's, as an equivalent radius: sqrt(area above 55 dB Lden / pi) taken
# from that airport's own DEFRA Round 4 surface and divided by Heathrow's
# 4.91 km. Heathrow is 1.000 by construction.
#
# The DISTANCE RAMPS in calc_postcode_quiet are calibrated on Heathrow, exactly
# as the borough band ladder was, and applying them unweighted asserted that
# every airport was Heathrow-sized. Scaling the borough ladder alone would have
# left the two tiers contradicting each other by up to 4.0 points - the postcode
# tier OVERRIDES the borough band, so Stockton-on-Tees would have read `moderate`
# as a borough and 1.0 (worse than `high`) at every postcode inside it.
#
# THIS TABLE IS DUPLICATED in scripts/build_aircraft_bands.py, which is where it
# was measured. `test_airport_noise_scale_matches_the_generator` compares them,
# because a Lambda cannot import from scripts/ and two silently drifting copies
# is the two-holder failure this repo keeps rediscovering.
AIRPORT_NOISE_SCALE = {
    'LHR': 1.000, 'STN': 0.741, 'EMA': 0.705, 'MAN': 0.589, 'LTN': 0.547,
    'LGW': 0.475, 'BHX': 0.449, 'BRS': 0.365, 'NCL': 0.346, 'LPL': 0.312,
    'LBA': 0.275, 'LCY': 0.190,
}
# US airports have no DEFRA footprint to scale by, and the UK unmapped default
# below means "smaller than the smallest DEFRA-mapped airport" - true of CWL
# and MME, absurd for JFK. The site has exempted every NYC airport at 1.0
# (Heathrow-equivalent, the pessimistic direction) since 2026-08-11; this is
# the Lambda's half of that same decision, added 2026-08-25 after the two
# holders were caught publishing quiet 10.0 beside impact "severe" for Howard
# Beach. Keep the two exemption lists in step with AIRPORTS_NYC_FITTED.
# An airport DEFRA does not map is below the threshold at which the mapping duty
# applies, so it is smaller than the smallest mapped one. This takes London
# City's value rather than extrapolating below it - pessimistic, and not a
# number pretending to be a measurement. Covers CWL, MME and NWI today; US airports
# are exempted in airport_noise_scale below, never defaulted here.
UNMAPPED_AIRPORT_SCALE = 0.190


# The exemption list is its own constant rather than a read of AIRPORTS_NYC_FITTED
# because airport_noise_scale is called DURING module load, before the
# AIRPORTS_NYC_FITTED literal at the foot of the data section has executed - the
# first version of this exemption NameError'd every import. A drift guard in
# SiteApiGeometryParityTests asserts this set equals AIRPORTS_NYC_FITTED's codes.
_US_AIRPORT_CODES = frozenset({'JFK', 'LGA', 'EWR', 'TEB'})


def airport_noise_scale(code):
    # NYC airports take the site's exemption: 1.0, Heathrow-equivalent. The
    # exemption lives HERE and not in the table, mirroring the site's
    # airportNoiseScale() exactly - SiteApiGeometryParityTests compares the
    # TABLES, so an exemption in one holder's table and the other's function
    # reads as drift.
    if code in _US_AIRPORT_CODES:
        return 1.0
    return AIRPORT_NOISE_SCALE.get(code, UNMAPPED_AIRPORT_SCALE)


# How many points of the corridor ladder (4/3/2/1 at <1/<2/<4/<6 effective km)
# actually reach the quiet score. v5.3, 2026-09-26; before it the whole ladder
# applied, which is 1.0.
#
# FITTED, NOT CHOSEN: scripts/fit_corridor_weight.py picks it on half of the
# DEFRA-measured postcodes (every city with a loaded raster) and reports the
# error on the other half. At 1.0 the estimate double-counted: a postcode near
# a runway is penalised for the airport AND for the corridor that runs out of
# it, and read a mean 1.8 points LOUDER than DEFRA measured across London.
# Mirrored as CORRIDOR_WEIGHT in index.html; SiteApiGeometryParityTests
# compares the two.
# PROVISIONAL (2026-09-26): fitted against DEFRA Round 4, which maps 2021 - and
# measured at Heathrow that map is about HALF a normal year's footprint (55 dB
# Lden 75.6 km2 against the CAA's 2024 148.4 km2; data/covid-understatement.json).
# The fit inherits that understatement. Refit when a normal-year yardstick lands.
#
# 0.3 -> 0.5 at v5.5 (2026-10-01), REFITTED with the runway-shaped airport term
# below and never chosen apart from it: the two trade off. A narrower strip
# takes noise away beside the runway, and the refit gives some back under the
# corridors. It is fitted UNDER the per-city rule (no city may come to read
# quieter than DEFRA), which is why it is 0.5 and not the unconstrained 0.35:
# scripts/fit_airport_shape.py --check holds the pair together, and is the
# gate for this constant since v5.5 (fit_corridor_weight.py's was retired).
CORRIDOR_WEIGHT = 0.5

# How much more a kilometre ACROSS a runway counts than one along it, in the
# airport term (v5.5, 2026-10-01). Aircraft noise lies in a strip along the
# runway axis, because every arrival and departure flies down that line, so a
# circle - which this term was until v5.5 - reads beside-the-runway postcodes
# far too loud. 1 would be the circle.
#
# FITTED, with CORRIDOR_WEIGHT, by scripts/fit_airport_shape.py, against TWO
# yardsticks because one is biased: DEFRA's measured strip alone rewards ever
# narrower shapes, so the ground beside it - blank cells inside each DEFRA
# raster's box, read as below that raster's measured floor - is scored too.
# The pick is a rule (recommend() in that script): no city may come to read
# quieter than DEFRA, judged PER CITY because London is 72% of the strip and
# pooled it hid five cities crossing at k = 6; then the lowest error on both
# yardsticks together. Mirrored as AIRPORT_SHAPE_K in index.html;
# SiteApiGeometryParityTests compares the two. PROVISIONAL for the same 2021
# reason as CORRIDOR_WEIGHT above.
AIRPORT_SHAPE_K = 4.0

# How far a US runway lobe runs straight out from its airport, km (v5.7, 2026-10-17).
# runway_lobe_km treated a lobe as an endless half-line; the Jan-Jul runway count added
# JFK's 31L departures, whose straight line points at Lower Manhattan 19 km out, and read
# 10002-10038 3-4 points louder where US DOT's 2022 map paints nothing (the FAA's coded
# climb-out turns away). 15 km is where a 3-degree glide reaches about 2,600 ft (the UK's
# drawn finals stop at 3,000 ft) and the radius of the major-airport term; of the lengths
# tried (8-20 km and none) it is the one that holds both regions' monitors under the
# per-city rule with the Bay Area's fit unchanged (measured 2026-10-17). Mirrored as
# RUNWAY_LOBE_KM in index.html; tests/test_us_quiet.py compares the two.
RUNWAY_LOBE_KM = 15.0

# Each airport's runway axis, degrees true: the doubled-angle mean of its AD
# 2.12 runway bearings, generated from data/flight-procedures.json beside the
# corridors. An airport absent from it - New York's four - keeps a circle.
# RUNWAY-AXES:START (generated by scripts/build_flight_paths.py --write; do not hand-edit)
RUNWAY_AXIS_DEG = {
    'BHX': 145.81,
    'BRS': 86.44,
    'CWL': 116.77,
    'EMA': 88.28,
    'LBA': 137.74,
    'LCY': 92.88,
    'LGW': 77.64,
    'LHR': 89.7,
    'LPL': 85.61,
    'LTN': 74.39,
    'MAN': 51.06,
    'MME': 47.45,
    'NCL': 65.2,
    'NWI': 89.29,
    'STN': 42.88,
}
# RUNWAY-AXES:END

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
# METHODOLOGY v3.9, 2026-08-26: `env` added at 0.14 in every persona.
# METHODOLOGY v4.0, 2026-08-29: road noise added INSIDE `env`. The persona
# weights below are UNCHANGED - v4.0 re-composes the environment component from
# two inputs to three and does not re-cut the top-level split, so nothing in
# this table moves and no persona's relative emphasis changes.
#
# HOW THE 0.14 WAS TAKEN. Every other weight was multiplied by 0.86 and rounded
# to 2dp, so each persona's REMAINING weights keep their exact relative
# emphasis - the same redistribution v3.3 used when it dropped `growth` for
# non-investor personas, and the same one live_weights_for() uses for a missing
# liveability input. Where rounding left a persona at 1.01 the single weight
# closest to its rounding boundary was taken down by 0.01 (balanced: quiet
# 0.33 -> 0.32; laterlife: live 0.34 -> 0.33). Every row sums to exactly 1.00.
#
# WHY 0.14 AS THE BASELINE. Environment is two measured inputs against three or
# four in `live`, and it is a NEW claim rather than a re-weighting of an
# existing one, so it enters modestly.
#
# WHY `family` AND `laterlife` CARRY 0.18 INSTEAD, AND NOTHING ELSE DOES. This
# is the one place a persona weight is anchored on an EXTERNAL health source
# rather than on buyer-priority research. WHO and COMEAP both identify specific
# air-pollution sensitivity groups - children, older adults, pregnant women, and
# people with asthma or heart and lung conditions. Two personas map onto that
# list without interpretation: `family` (children, whose lung development is
# affected) and `laterlife` (older adults). The other six have no
# group-specific basis, so they stay at the baseline rather than being nudged
# on a hunch.
#
# The extra 0.04 was taken from each of those two personas' OWN remaining
# weights in proportion, so their internal emphasis is unchanged: `family` stays
# liveability-led (0.46 of 0.82) and `laterlife` stays quiet-led (0.36 of 0.82).
#
# This deliberately does NOT vary by persona anywhere else. "Everyone breathes
# the same air" is a sound default, and a weight that differs without a
# published group behind it is an opinion wearing a number.
#
# THIS MOVES EVERY PUBLISHED SCORE. Measured spread of the env component is
# 4.60-9.00 across 86 boroughs, so at 0.14 it introduces ~0.62 points of
# total-score range - over the 0.5 threshold METHODOLOGY sets for a material
# change, so the 14-day integrator notice is REQUIRED, not optional.
PERSONAS = {
    'balanced': {'quiet': 0.32, 'afford': 0.27, 'growth': 0.00, 'live': 0.27, 'env': 0.14},
    # 0.18 env: children are a WHO/COMEAP air-quality sensitivity group.
    'family': {'quiet': 0.18, 'afford': 0.18, 'growth': 0.00, 'live': 0.46, 'env': 0.18},
    # Investor: expected return IS the question, so growth keeps full weight.
    'investor': {'quiet': 0.09, 'afford': 0.26, 'growth': 0.34, 'live': 0.17, 'env': 0.14},
    'firsttime': {'quiet': 0.16, 'afford': 0.43, 'growth': 0.00, 'live': 0.27, 'env': 0.14},
    'quietlife': {'quiet': 0.48, 'afford': 0.19, 'growth': 0.00, 'live': 0.19, 'env': 0.14},
    # Renter: no selling event so growth is irrelevant.
    'renter': {'quiet': 0.26, 'afford': 0.30, 'growth': 0.00, 'live': 0.30, 'env': 0.14},
    # Commuter / young professional: transport-led, price-sensitive.
    'commuter': {'quiet': 0.21, 'afford': 0.30, 'growth': 0.00, 'live': 0.35, 'env': 0.14},
    # Later-life buyer: cash buyer prioritising quiet + healthcare access.
    # 0.18 env: older adults are the other WHO/COMEAP sensitivity group.
    'laterlife': {'quiet': 0.36, 'afford': 0.14, 'growth': 0.00, 'live': 0.32, 'env': 0.18},
}

# ---------------------------------------------------------------------------
# Vintage tracking (trends feature, 2026-07-24). Each quarterly refresh
# keeps the superseded price/trend values here so the API can answer
# "what changed?" (?compare=previous on /v1/score, and GET /v1/changes).
# Only price + trend move between quarterly vintages; schools / crime /
# transport / healthcare refresh annually and noise five-yearly, so the
# previous dataset is the current one overlaid with these two fields.
# ---------------------------------------------------------------------------
SNAPSHOT_VINTAGE = '2026-Q3'  # August 2026 UK HPI, applied 2026-10-22 (July was applied 2026-09-16)
# The KEY is the quarter, the LABEL is the month, and they move at different
# rates - decided 2026-09-16, the first roll where they differed. HMLR
# publishes monthly; `/v1/changes` is a QUARTERLY comparison. A monthly roll
# inside a quarter refreshes the numbers under the same key (June -> July, both
# 2026-Q3) and moves the label alone, so `?compare=previous` keeps comparing
# against Q2 and "this quarter" stays true. Treating every month as a snapshot
# roll would have made the comparison month-on-month under a label saying
# quarter. When the key next moves (an October-or-later HPI, 2026-Q4), the
# current values are copied into the *_PREVIOUS_PT tables and PREVIOUS_VINTAGE
# follows - the three-step roll in memory/project-trends-feature.md.
#
# The label in the words a customer reads. It was written out by hand in
# THIRTEEN provenance strings until 2026-09-09, one per city, so a roll had to
# remember all thirteen - and the Progress 8 roll has already been caught
# updating London's and leaving a sibling eleven cities down saying the old
# year. Rolling the month means changing this line and CPIH_12M_PCT below.
SNAPSHOT_VINTAGE_LABEL = 'August 2026'
# The ONS recorded-crime edition every crime credit line names (and, on this branch, provenance's period).
# refresh_crime_from_ons.edition_label() derives it from that script's EDITION; tests/test_provenance_periods.py
# holds the two equal, so a roll cannot leave thirteen cities crediting the previous quarter (2026-10-23).
CRIME_EDITION_LABEL = 'year ending June 2026'
PREVIOUS_VINTAGE = '2026-Q2'
SNAPSHOT_REFRESHED_AT = '2026-10-22'
# v5.1: the inflation each vintage's trend is deflated by. ONS CPIH 12-month
# rate, all items (series L55O, dataset MM23), for the HPI MONTH the vintage
# carries - August 2026 for 2026-Q3, May 2026 for 2026-Q2 - because a 12-month
# price change and a 12-month price-level change over the SAME window is the
# only pairing that means "real". Both vintages need an entry: ?compare=previous
# recomputes the previous score under the current formula, and deflating May's
# trend by July's inflation would manufacture movement that never happened.
# Rolling the month means moving the current entry with the label (the key
# stays); rolling the quarter means adding a new one. `build_hpi_prices.py
# --check` compares the current entry against the ONS series for the LABEL's
# month and fails on a vintage this table does not know. Sterling only: New
# York's five boroughs carry a curated trend and no US series is held, so they
# score nominal.
CPIH_12M_PCT = {
    '2026-Q3': 3.3,  # CPIH, August 2026 (was 3.1 for July, rolled 2026-10-22)
    '2026-Q2': 3.0,  # CPIH, May 2026
}


def real_trend_pct(nominal_pct, inflation_pct):
    """The 12-month price change after inflation, to 1dp.

    ((1 + n) / (1 + i) - 1), not n - i: the difference is a few hundredths of
    a point at these rates and the exact form costs nothing. Rounded ONCE
    here and then used as an INPUT - published as `trendReal` and scored from
    the same rounded value - so a reader reproducing growth_score() from the
    response gets the engine's number, not one a rounding step away from it.
    """
    # The SAME tie rule as round_1dp() (halves toward +infinity, exactly the
    # site's Math.round: -2.25 -> -2.2, NOT away from zero, which this comment
    # wrongly said until 2026-09-25) rather than Python's round(): this value has a JS
    # holder, and two languages' defaults disagree on an exact .x5 tie.
    # Inlined because round_1dp is defined below the import-time call.
    return math.floor(((1 + nominal_pct / 100.0) / (1 + inflation_pct / 100.0) - 1) * 1000.0 + 0.5) / 10


def with_real_trends(boroughs, vintage, currency):
    """A copy of `boroughs` with `trendReal` on every record, deflated by the
    CPIH entry for `vintage`. Returns the records UNCHANGED (no `trendReal`)
    for a currency the series does not describe, or a vintage the table does
    not know, so a city with no inflation series scores nominal by
    construction rather than by a special case downstream."""
    inflation = CPIH_12M_PCT.get(vintage) if currency == 'GBP' else None
    if inflation is None:
        return {name: dict(bd) for name, bd in boroughs.items()}
    return {
        name: {**bd, 'trendReal': real_trend_pct(bd['trend'], inflation)}
        for name, bd in boroughs.items()
    }


def scored_trend(bd):
    """The trend growth_score() reads: real where it exists, else nominal."""
    return bd.get('trendReal', bd['trend'])
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
    'Barking and Dagenham': {'avgPrice': 361000, 'trend': -0.2},
    'Barnet': {'avgPrice': 591000, 'trend': -4.3},
    'Bexley': {'avgPrice': 409000, 'trend': 2.2},
    'Brent': {'avgPrice': 549000, 'trend': -3.3},
    'Bromley': {'avgPrice': 525000, 'trend': 0.2},
    'Camden': {'avgPrice': 806000, 'trend': -6.2},
    'City of London': {'avgPrice': 627000, 'trend': -28.1},
    'Croydon': {'avgPrice': 397000, 'trend': -0.4},
    'Ealing': {'avgPrice': 569000, 'trend': -2.5},
    'Enfield': {'avgPrice': 469000, 'trend': -0.7},
    'Greenwich': {'avgPrice': 463000, 'trend': 0.1},
    'Hackney': {'avgPrice': 608000, 'trend': 0.1},
    'Hammersmith and Fulham': {'avgPrice': 729000, 'trend': -10.9},
    'Haringey': {'avgPrice': 634000, 'trend': 2.4},
    'Harrow': {'avgPrice': 530000, 'trend': 0.4},
    'Havering': {'avgPrice': 453000, 'trend': 2.8},
    'Hillingdon': {'avgPrice': 468000, 'trend': -0.7},
    'Hounslow': {'avgPrice': 501000, 'trend': -2.4},
    'Islington': {'avgPrice': 670000, 'trend': -6.4},
    'Kensington and Chelsea': {'avgPrice': 1256000, 'trend': -10.7},
    'Kingston upon Thames': {'avgPrice': 582000, 'trend': 0.0},
    'Lambeth': {'avgPrice': 545000, 'trend': -2.9},
    'Lewisham': {'avgPrice': 497000, 'trend': 2.3},
    'Merton': {'avgPrice': 597000, 'trend': -1.3},
    'Newham': {'avgPrice': 405000, 'trend': -1.4},
    'Redbridge': {'avgPrice': 496000, 'trend': 2.4},
    'Richmond upon Thames': {'avgPrice': 789000, 'trend': -2.5},
    'Southwark': {'avgPrice': 579000, 'trend': 0.9},
    'Sutton': {'avgPrice': 445000, 'trend': 0.9},
    'Tower Hamlets': {'avgPrice': 444000, 'trend': -14.5},
    'Waltham Forest': {'avgPrice': 524000, 'trend': 3.1},
    'Wandsworth': {'avgPrice': 660000, 'trend': -6.1},
    'Westminster': {'avgPrice': 836000, 'trend': -22.8},
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
    # v5.1: the overlay above replaces `trend` and leaves the CURRENT vintage's
    # `trendReal` in place, which would score May's prices against June's
    # inflation. Re-derive it from the previous vintage's own CPIH entry.
    return with_real_trends(merged, PREVIOUS_VINTAGE, cfg['currency'])


def build_comparison(current, previous, city, weights, name=None):
    """Assemble the ?compare=previous response block from two calc_score
    results computed under identical formula + weights.

    `name` is the resolved borough. Passing it is what lets the explanation say
    "Barking and Dagenham went from 1st to 17th" rather than "this area", and
    what enables the growth rank at all.

    `weights` MUST be the weights the two results were scored under (audit
    I26/F8). Until 2026-09-01 this function passed `PERSONAS['balanced']` to
    both build_why and build_attribution while `scoreChange` came from the
    caller's own persona - so an `investor` request got an explanation of a
    different number than the one printed beside it. build_attribution's
    docstring calls the identity `delta_score == sum(w_i * delta_component_i)`
    the thing that makes it an explanation rather than a narrative; under a
    mismatched persona the parts cannot add up to the whole. Growth is 0.00 for
    every persona but investor, so an investor's biggest driver was being
    dropped from its own explanation as a zero-weight factor.

    It is required and positional on purpose. A default would let the next
    caller silently reinstate `balanced`, which is the defect itself.
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
    cur_bm = benchmarks(CITIES[city]['boroughs'], city)
    prev_bm = benchmarks(prev_set, city, previous=True)
    cur_ranks = growth_ranks(CITIES[city]['boroughs'])
    prev_ranks = growth_ranks(prev_set)
    why = build_why(
        current, previous, city, weights, name, cur_bm, prev_bm, cur_ranks, prev_ranks
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
        # v5.1: present only where the previous vintage was deflated too.
        **({'previousTrendRealPct': previous['context']['priceTrendRealPct']}
           if 'priceTrendRealPct' in previous['context'] else {}),
        'note': COMPARISON_NOTE,
        'attribution': build_attribution(current, previous, weights),
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
    # v5.0: affordability is NATIONAL now, so "against every other London
    # borough" stopped being true - and it had only ever been true of London
    # anyway, in a dict served to thirteen cities. Growth below is still
    # cohort-relative, so it keeps its comparison and gains the city it is
    # actually relative to.
    'afford': 'How cheap this area is, against borough prices across the whole country.',
    'growth': 'How fast property prices are rising here after inflation, against every borough Sky Score covers in this currency.',
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
    """Rank every area by the trend growth is SCORED on (real terms where held,
    v5.1), 1 = fastest rising. Ties share a rank."""
    trends = {name: scored_trend(bd) for name, bd in boroughs.items()}
    ordered = sorted(trends.values(), reverse=True)
    return {name: ordered.index(t) + 1 for name, t in trends.items()}


def benchmarks(boroughs, city='london', previous=False):
    """The yardsticks a vintage comparison is read against.

    Growth is *relative*: scored against the strongest-growing (and, since
    v3.4, the steepest-falling) area - of the same city until v5.2, of the
    whole CURRENCY POOL since (2026-09-16, see national_trend_bounds). Naming
    those reference points is what turns "growth fell 8.2" from an assertion
    into something a reader can check — and it explains the amplification,
    since an area that IS the benchmark scores the maximum by definition, so
    it has nowhere to go but down.

    `city` says whose slice `boroughs` is, so the pool can be assembled with
    that slice standing in (a previous vintage) and so a yardstick outside the
    city is labelled with its city - the London comparison may now name
    "Trafford (Greater Manchester)" as the fastest riser. It defaults to
    London because every caller that existed when the parameter was added was
    London's; a new caller must pass its own.

    Affordability is NOT relative to these any more (audit M9, corrected
    2026-09-14): since methodology v5.0 it is anchored on the national
    5th-95th percentile band, `national_price_bounds`, and this docstring
    said "against the cheapest and dearest" for five days after that changed.
    `cheapestArea`/`dearestArea` are still published, as the city's price
    RANGE for context, not as the affordability anchor - see
    `_afford_breakdown_line` for the anchor a response actually names.

    `previous=True` marks the set as a PREVIOUS vintage (2026-09-25 audit
    I-1). Only London's slice is held at that vintage (previous_dataset), so
    every other city enters the pool at its CURRENT figures - and a yardstick
    drawn from one of them is a current number standing in for a previous
    one. `strongestGrowthStandIn` / `steepestFallStandIn` say so. Without
    them `/v1/changes` published "changed from Trafford (+6.3%) to Trafford
    (+6.3%)": the same July figure on both sides, called a change.
    """
    # The trend growth is SCORED on - real terms where an inflation series is
    # held (v5.1), nominal otherwise - because a yardstick in a different unit
    # from the score it explains is not a yardstick. v5.2: over the POOL, with
    # `boroughs` standing in for this city's slice; the price range below stays
    # the city's, because it is published as context and not as an anchor.
    pool = national_trend_pool(city, boroughs, pool_of(city))
    prices = {name: bd['avgPrice'] for name, bd in boroughs.items()}
    max_trend = max(t for _, t in pool)
    min_trend = min(t for _, t in pool)
    top = sorted(label for label, t in pool if t == max_trend)
    # v3.4 scales each tail to its own extreme, so a falling area needs a bottom
    # yardstick just as a rising one needs the top. Under v3.2 every faller
    # scored 0 regardless, so only the top benchmark was ever needed.
    bottom = sorted(label for label, t in pool if t == min_trend)
    dearest = max(prices, key=lambda n: prices[n])
    cheapest = min(prices, key=lambda n: prices[n])
    # A tie that includes one of this city's own boroughs is a measured
    # yardstick: its figure IS held at this vintage.
    own = set(boroughs)
    return {
        'strongestGrowthArea': top[0],
        'strongestGrowthAreas': top,
        'strongestGrowthTrendPct': max_trend,
        'strongestGrowthStandIn': previous and not any(label in own for label in top),
        'steepestFallArea': bottom[0],
        'steepestFallAreas': bottom,
        'steepestFallTrendPct': min_trend,
        'steepestFallStandIn': previous and not any(label in own for label in bottom),
        # v5.1: which unit the two trend yardsticks above are in.
        'growthBasis': 'real' if any('trendReal' in bd for bd in boroughs.values()) else 'nominal',
        'dearestArea': dearest,
        'dearestAvgPrice': prices[dearest],
        'cheapestArea': cheapest,
        'cheapestAvgPrice': prices[cheapest],
    }


def market_context(current_boroughs, previous_boroughs, score_changes=None):
    """City-wide movement, so an individual change is readable in context.

    The single most useful sentence about this vintage pair is not about any one
    borough: the mean trend fell from +3.2% to -1.6% and the number of areas with
    falling prices went from 0 to 14. Without that, 25 boroughs dropping looks
    like a scoring fault rather than the market it is describing.

    `score_changes` is the per-borough scoreChange list the caller has already
    computed, and the closing sentence is DERIVED from it. Until the July 2026
    roll (2026-09-16) that sentence read the direction of the SCORES off the
    direction of the TREND: "Most scores fell because the market fell" whenever
    the mean trend fell. But `balanced` weights growth at 0.00, so a balanced
    score cannot move on the trend at all - between vintages it moves on
    affordability alone, a borough's price LEVEL against the national p5-p95
    band (v5.0) - and the two quantities have no fixed sign relationship. July
    was the first pair where they pointed opposite ways: the mean trend fell
    -3.35% -> -3.42% while 14 of 33 scores ROSE and one fell, and the endpoint
    published "most scores fell" three lines above a `summary` counting 14
    risers. The 2026-08-25 fix made the tail direction-aware; it was aware of
    the wrong direction.
    """
    # NOMINAL, deliberately, and unlike benchmarks(): this block describes
    # what PRICES did ("the mean trend fell from +3.2% to -1.6%"), and a
    # sentence about prices should be in the unit prices are quoted in. The
    # score's own yardsticks are real-terms since v5.1 and say so.
    cur = [bd['trend'] for bd in current_boroughs.values()]
    prev = [bd['trend'] for bd in previous_boroughs.values()]
    cur_bm = benchmarks(current_boroughs, 'london')
    prev_bm = benchmarks(previous_boroughs, 'london', previous=True)
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
            + _yardstick_sentence(cur_bm, prev_bm)
            # What the SCORES did, counted from the caller's tally - never
            # inferred from the trend's sign (see the docstring). The mechanism
            # is named because it is not obvious: only price and trend move
            # between vintages, balanced does not weight trend, so the whole of
            # a balanced score change is affordability against the national
            # price band. Without the tally the neutral claim stands alone.
            + _score_movement_sentence(score_changes)
        ),
    }


def _yardstick_sentence(cur_bm, prev_bm):
    """The growth-yardstick sentence of marketContext.summary (audit I-1).

    Three cases, because the old single template ("changed from X to Y")
    published "changed from Trafford (+6.3%) to Trafford (+6.3%)" - a July
    figure on both sides - once v5.2 moved the yardstick outside London.
    """
    now = f'{cur_bm["strongestGrowthArea"]} ({cur_bm["strongestGrowthTrendPct"]:+}%)'
    lead = 'Growth is scored against the strongest real-terms riser in the sterling pool'
    if prev_bm.get('strongestGrowthStandIn'):
        return (
            f'{lead}, now {now}. Sky Score holds the earlier vintage for London only, so the '
            'comparison reads boroughs outside London at their current figures and cannot say '
            'whether that yardstick moved. '
        )
    was = f'{prev_bm["strongestGrowthArea"]} ({prev_bm["strongestGrowthTrendPct"]:+}%)'
    if was == now:
        return f'{lead}, {now} in both vintages. '
    return f'{lead}, which changed from {was} to {now}. '


def _score_movement_sentence(score_changes):
    """The closing sentence of marketContext.summary, derived from the tally."""
    mechanism = (
        'Score movement between vintages comes from each borough\'s price against the '
        'national price band, not from any one borough being reassessed.'
    )
    if not score_changes:
        return mechanism
    risers = sum(1 for c in score_changes if c > 0)
    fallers = sum(1 for c in score_changes if c < 0)
    unchanged = len(score_changes) - risers - fallers
    return (
        f'Of {len(score_changes)} borough scores, {risers} rose, {fallers} fell and '
        f'{unchanged} did not move at one decimal place. {mechanism}'
    )


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
        # THE JUSTIFICATION IS PER-COMPONENT, not a fixed sentence (2026-09-11,
        # audit I2). `unweighted` is built generically over EVERY zero-weight
        # component, but the caveat hardcoded growth's reason - "weighted only
        # for the investor persona, because past price growth describes the
        # market rather than the property". A caller passing ?weights=afford:0.0
        # (documented in METHODOLOGY s5.3 and sold on pricing.html and
        # api/index.html) got that sentence about AFFORDABILITY, where both
        # clauses are false: every persona weights it, and it is not price
        # growth. Verified live on 22 of 33 London boroughs before the fix.
        #
        # Growth keeps its explanation, because for seven of the eight personas
        # a zero weight on growth is the PRODUCT's decision and deserves a
        # reason. Anything else is zero because the CALLER set it so, and the
        # honest sentence says that rather than inventing a rationale.
        labels = [u['label'] for u in unweighted]
        moved = ' and '.join(labels)
        # 'is'/'are' was always 'is', so two zero-weight components produced
        # "Affordability and Growth moved ... but is not counted".
        verb = 'is' if len(labels) == 1 else 'are'
        them = 'it' if len(labels) == 1 else 'them'
        if labels == ['Growth']:
            because = (
                ' — it is weighted only for the investor persona, because past price growth '
                'describes the market rather than the property.'
            )
        else:
            because = f' — the weights supplied with this request give {them} no weight.'
        unweighted_caveat = (
            f'{moved} moved this quarter but {verb} not counted in this view{because}'
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
    # v5.1: what growth was SCORED on. Real terms where the response carries it
    # (sterling cities), else the nominal trend - and the yardsticks in cur_bm /
    # prev_bm are in the same unit, so step 3 below compares like with like.
    # Step 1 keeps the nominal figures on purpose: it describes what PRICES did.
    cur_scored = current['context'].get('priceTrendRealPct', cur_trend)
    prev_scored = previous['context'].get('priceTrendRealPct', prev_trend)
    inflation_pct = current['context'].get('inflationPct')
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

            # Step 2b (v5.1): name the deflation, so the figure step 3 works from
            # is not a surprise next to the cash figure step 1 quoted.
            if inflation_pct is not None and cur_scored is not None:
                driver['steps'].append(
                    f'Growth is scored in real terms (methodology v5.1): the cash trend of {cur_trend:+}% '
                    f'less CPIH inflation of {inflation_pct}% over the same twelve months is {cur_scored:+}% '
                    'after inflation, and that is the figure the score is built from.'
                )

            # Step 3: why that drops the SCORE so far — the league-table model.
            # v5.1: every 'rising'/'falling' in this step is about the REAL-terms
            # figure where one exists, and says so - step 1 has just said 'still
            # rising' in cash terms, and a sentence that then calls the same place
            # falling has to name the difference.
            rt = ' in real terms' if inflation_pct is not None else ''
            was_top = prev_bm and prev_scored >= prev_bm['strongestGrowthTrendPct']
            if cur_scored < 0:
                fall_note = (
                    f'The growth score puts a flat market — prices neither rising nor falling{rt} — at 5 out of 10. '
                    f'Prices falling{rt} score below 5, scaled against the steepest fall among every borough Sky Score '
                    'covers in this currency: the borough falling fastest scores 0, and every other falling borough sits between.'
                )
                if was_top:
                    fall_note += (
                        f' Last quarter {subject_lower} had the fastest-rising prices{rt} of any covered borough, so it held the '
                        'top score of 10 — which means it could only ever move down from there.'
                    )
                steepest_pct = cur_bm['steepestFallTrendPct'] if cur_bm else None
                if steepest_pct is not None and steepest_pct < 0:
                    fall_note += (
                        f' The steepest fall now is {cur_bm["steepestFallArea"]} at {steepest_pct:+}%, and '
                        f'{cur_scored:+}% is about {_fraction_words(cur_scored / steepest_pct)} of that — '
                        f'so {f["after"]} out of 10.'
                    )
                    driver['workings'] = (
                        f'5.0 − {cur_scored:+}% ÷ {steepest_pct:+}% '
                        f'({cur_bm["steepestFallArea"]}, steepest fall) × 5 = {f["after"]}'
                    )
                else:
                    driver['workings'] = f'{cur_scored:+}% against a flat-market anchor of 5.0 = {f["after"]}'
                driver['steps'].append(fall_note)
            elif cur_bm and cur_bm['strongestGrowthTrendPct'] > 0:
                share = cur_scored / cur_bm['strongestGrowthTrendPct']
                model = (
                    f'The growth score puts a flat market — prices neither rising nor falling{rt} — at 5 out of 10. '
                    f'Prices rising{rt} score above 5, scaled against the fastest riser among every borough Sky Score '
                    'covers in this currency, which takes the full 10.'
                )
                if was_top:
                    model += (
                        f' Last quarter that was {subject_lower} itself, at {prev_scored:+}% — so it took the full '
                        '10, and the only direction available was down.'
                    )
                model += (
                    f' The fastest now is {cur_bm["strongestGrowthArea"]} at {cur_bm["strongestGrowthTrendPct"]:+}%, '
                    f'and {cur_scored:+}% is about {_fraction_words(share)} of that — so {f["after"]} out of 10.'
                )
                driver['steps'].append(model)
                driver['workings'] = (
                    f'5.0 + {cur_scored:+}% ÷ {cur_bm["strongestGrowthTrendPct"]:+}% '
                    f'({cur_bm["strongestGrowthArea"]}, fastest) × 5 = {f["after"]}'
                )
                if rank_now and rank_before and rank_now > rank_before and cur_scored > 0:
                    caveats.append(
                        f'{subject} did not get worse in absolute terms — prices are still rising in real terms. It fell '
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
            # v5.0. This used to say affordability was "a league table: the
            # cheapest borough scores 10 and the dearest scores 0", and show the
            # min-max sum over the CITY cohort. Both became false when the
            # anchor went national, and the workings became false in the worst
            # way available: the printed arithmetic no longer equalled the
            # printed result, because the value beside it was already coming
            # from the new formula. A shown sum that does not reach its own
            # answer is worse than no sum, so this reproduces the real one.
            afford_p5, afford_p95 = national_price_bounds(
                city, CITIES[city]['boroughs'], pool_of(city)
            )
            driver['steps'].append(
                'Affordability is measured against borough prices across the whole country, not just this '
                f'city: {_money(afford_p5, city)} or less scores 10, {_money(afford_p95, city)} or more '
                'scores 0, and the scale between them is logarithmic because prices are bunched at the '
                'cheap end and stretched at the dear end.'
            )
            if cur_bm:
                driver['steps'].append(
                    f'For local context, the cheapest borough in this city is {cur_bm["cheapestArea"]} at '
                    f'{_money(cur_bm["cheapestAvgPrice"], city)} and the dearest is {cur_bm["dearestArea"]} '
                    f'at {_money(cur_bm["dearestAvgPrice"], city)}; context.priceRankInCity says where this '
                    'borough sits in that list. That local range no longer sets the score - it is context.'
                )
            driver['workings'] = (
                f'log({_money(afford_p95, city)} ÷ {_money(cur_price, city)}) ÷ '
                f'log({_money(afford_p95, city)} ÷ {_money(afford_p5, city)}) × 10 = {f["after"]}'
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
        'avgPrice': 528051,
        'trend': -1.5,
        'schools': 'good',
        'crimeRate': 87.6,
        'p8': 0.45,
        'transport': 'good',
        'healthcare': 'good',
        'airQualityWhoRatio': 1.81,
        'floodMediumOrHighPct': 0.33,
        'roadNoiseAboveWhoPct': 62.7,
    },
    'Hillingdon': {
        'impact': 'severe',
        'avgPrice': 482137,
        'trend': 0.0,
        'schools': 'good',
        'crimeRate': 92.6,
        'p8': 0.24,
        'transport': 'moderate',
        'healthcare': 'moderate',
        'airQualityWhoRatio': 1.63,
        'floodMediumOrHighPct': 0.91,
        'roadNoiseAboveWhoPct': 51.4,
    },
    'Richmond upon Thames': {
        'impact': 'high',
        'avgPrice': 813931,
        'trend': 0.0,
        'schools': 'excellent',
        'crimeRate': 56.5,
        'p8': 0.43,
        'transport': 'good',
        'healthcare': 'good',
        'airQualityWhoRatio': 1.67,
        'floodMediumOrHighPct': 1.72,
        'roadNoiseAboveWhoPct': 56.3,
    },
    'Ealing': {
        'impact': 'high',
        'avgPrice': 589875,
        'trend': 1.8,
        'schools': 'good',
        'crimeRate': 81.9,
        'p8': 0.56,
        'transport': 'good',
        'healthcare': 'good',
        'airQualityWhoRatio': 1.77,
        'floodMediumOrHighPct': 0.5,
        'roadNoiseAboveWhoPct': 54.4,
    },
    'Wandsworth': {
        'impact': 'moderate',
        'avgPrice': 694210,
        'trend': -5.3,
        'schools': 'excellent',
        'crimeRate': 76.6,
        'p8': 0.49,
        'transport': 'good',
        'healthcare': 'excellent',
        'airQualityWhoRatio': 1.89,
        'floodMediumOrHighPct': 2.08,
        'roadNoiseAboveWhoPct': 58.3,
    },
    'Lambeth': {
        'impact': 'moderate',
        'avgPrice': 540198,
        'trend': -6.5,
        'schools': 'good',
        'crimeRate': 116.5,
        'p8': 0.0,
        'transport': 'excellent',
        'healthcare': 'excellent',
        'airQualityWhoRatio': 2.05,
        'floodMediumOrHighPct': 0.28,
        'roadNoiseAboveWhoPct': 55.9,
    },
    'Lewisham': {
        'impact': 'low-moderate',
        'avgPrice': 486416,
        'trend': -1.6,
        'schools': 'good',
        'crimeRate': 96.8,
        'p8': 0.1,
        'transport': 'excellent',
        'healthcare': 'good',
        'airQualityWhoRatio': 1.8,
        'floodMediumOrHighPct': 2.31,
        'roadNoiseAboveWhoPct': 50.6,
    },
    'Greenwich': {
        'impact': 'moderate',
        'avgPrice': 462589,
        'trend': -2.2,
        'schools': 'good',
        'crimeRate': 90.2,
        'p8': -0.01,
        'transport': 'good',
        'healthcare': 'good',
        'airQualityWhoRatio': 1.81,
        'floodMediumOrHighPct': 1.17,
        'roadNoiseAboveWhoPct': 54.7,
    },
    'Tower Hamlets': {
        'impact': 'low-moderate',
        'avgPrice': 447796,
        'trend': -13.3,
        'schools': 'good',
        'crimeRate': 109.3,
        'p8': 0.13,
        'transport': 'excellent',
        'healthcare': 'excellent',
        'airQualityWhoRatio': 2.42,
        'floodMediumOrHighPct': 0.71,
        'roadNoiseAboveWhoPct': 74.5,
    },
    'Camden': {
        'impact': 'low',
        'avgPrice': 798486,
        'trend': -10.6,
        'schools': 'excellent',
        'crimeRate': 173.5,
        'p8': -0.14,
        'transport': 'excellent',
        'healthcare': 'excellent',
        'airQualityWhoRatio': 2.66,
        'floodMediumOrHighPct': 0.0,
        'roadNoiseAboveWhoPct': 73.7,
    },
    'Islington': {
        'impact': 'low',
        'avgPrice': 654286,
        'trend': -8.6,
        'schools': 'good',
        'crimeRate': 133.9,
        'p8': 0.15,
        'transport': 'excellent',
        'healthcare': 'excellent',
        'airQualityWhoRatio': 2.55,
        'floodMediumOrHighPct': 0.0,
        'roadNoiseAboveWhoPct': 65.4,
    },
    'Hackney': {
        'impact': 'low',
        'avgPrice': 619408,
        'trend': -1.6,
        'schools': 'good',
        'crimeRate': 117.5,
        'p8': 0.51,
        'transport': 'excellent',
        'healthcare': 'excellent',
        'airQualityWhoRatio': 2.27,
        'floodMediumOrHighPct': 1.19,
        'roadNoiseAboveWhoPct': 65.6,
    },
    'Barnet': {
        'impact': 'low-moderate',
        'avgPrice': 592892,
        'trend': -4.4,
        'schools': 'excellent',
        'crimeRate': 69.4,
        'p8': 0.61,
        'transport': 'good',
        'healthcare': 'good',
        'airQualityWhoRatio': 1.7,
        'floodMediumOrHighPct': 0.76,
        'roadNoiseAboveWhoPct': 56.5,
    },
    'Croydon': {
        'impact': 'moderate',
        'avgPrice': 396718,
        'trend': -1.5,
        'schools': 'good',
        'crimeRate': 81.6,
        'p8': -0.04,
        'transport': 'good',
        'healthcare': 'good',
        'airQualityWhoRatio': 1.67,
        'floodMediumOrHighPct': 1.51,
        'roadNoiseAboveWhoPct': 47.6,
    },
    'Bromley': {
        'impact': 'low',
        'avgPrice': 520253,
        'trend': -0.5,
        'schools': 'excellent',
        'crimeRate': 69.8,
        'p8': 0.05,
        'transport': 'good',
        'healthcare': 'moderate',
        'airQualityWhoRatio': 1.63,
        'floodMediumOrHighPct': 1.28,
        'roadNoiseAboveWhoPct': 46.3,
    },
    'Newham': {
        'impact': 'moderate-high',
        'avgPrice': 388045,
        'trend': -4.7,
        'schools': 'good',
        'crimeRate': 106.3,
        'p8': 0.28,
        'transport': 'excellent',
        'healthcare': 'good',
        'airQualityWhoRatio': 2.04,
        'floodMediumOrHighPct': 0.0,
        'roadNoiseAboveWhoPct': 67.5,
    },
    'Southwark': {
        'impact': 'low-moderate',
        'avgPrice': 569160,
        'trend': -2.1,
        'schools': 'good',
        'crimeRate': 122.7,
        'p8': 0.46,
        'transport': 'good',
        'healthcare': 'excellent',
        'airQualityWhoRatio': 2.28,
        'floodMediumOrHighPct': 0.01,
        'roadNoiseAboveWhoPct': 56.1,
    },
    'Hammersmith and Fulham': {
        'impact': 'moderate-high',
        'avgPrice': 754825,
        'trend': -5.1,
        'schools': 'excellent',
        'crimeRate': 106.8,
        'p8': 0.52,
        'transport': 'excellent',
        'healthcare': 'excellent',
        'airQualityWhoRatio': 2.04,
        'floodMediumOrHighPct': 0.0,
        'roadNoiseAboveWhoPct': 68.6,
    },
    'Kensington and Chelsea': {
        'impact': 'moderate',
        'avgPrice': 1204072,
        'trend': -13.8,
        'schools': 'excellent',
        'crimeRate': 142.4,
        'p8': 0.3,
        'transport': 'excellent',
        'healthcare': 'excellent',
        'airQualityWhoRatio': 2.36,
        'floodMediumOrHighPct': 0.02,
        'roadNoiseAboveWhoPct': 75.0,
    },
    'Brent': {
        'impact': 'low-moderate',
        'avgPrice': 555687,
        'trend': -0.3,
        'schools': 'good',
        'crimeRate': 91.3,
        'p8': 0.58,
        'transport': 'excellent',
        'healthcare': 'good',
        'airQualityWhoRatio': 1.8,
        'floodMediumOrHighPct': 1.31,
        'roadNoiseAboveWhoPct': 60.2,
    },
    'Haringey': {
        'impact': 'low',
        'avgPrice': 633221,
        'trend': -1.4,
        'schools': 'good',
        'crimeRate': 103.4,
        'p8': 0.3,
        'transport': 'good',
        'healthcare': 'good',
        'airQualityWhoRatio': 1.79,
        'floodMediumOrHighPct': 0.68,
        'roadNoiseAboveWhoPct': 57.8,
    },
    'Waltham Forest': {
        'impact': 'low',
        'avgPrice': 532212,
        'trend': 0.7,
        'schools': 'good',
        'crimeRate': 80.1,
        'p8': -0.1,
        'transport': 'good',
        'healthcare': 'good',
        'airQualityWhoRatio': 1.82,
        'floodMediumOrHighPct': 1.3,
        'roadNoiseAboveWhoPct': 58.3,
    },
    'Merton': {
        'impact': 'low-moderate',
        'avgPrice': 623791,
        'trend': 0.1,
        'schools': 'good',
        'crimeRate': 59.1,
        'p8': 0.61,
        'transport': 'excellent',
        'healthcare': 'good',
        'airQualityWhoRatio': 1.72,
        'floodMediumOrHighPct': 1.33,
        'roadNoiseAboveWhoPct': 54.7,
    },
    'Redbridge': {
        'impact': 'low',
        'avgPrice': 484378,
        'trend': -2.8,
        'schools': 'excellent',
        'crimeRate': 75.6,
        'p8': 0.52,
        'transport': 'good',
        'healthcare': 'good',
        'airQualityWhoRatio': 1.79,
        'floodMediumOrHighPct': 1.06,
        'roadNoiseAboveWhoPct': 62.0,
    },
    'Enfield': {
        'impact': 'low',
        'avgPrice': 474855,
        'trend': 0.8,
        'schools': 'good',
        'crimeRate': 87.0,
        'p8': 0.09,
        'transport': 'good',
        'healthcare': 'moderate',
        'airQualityWhoRatio': 1.7,
        'floodMediumOrHighPct': 0.81,
        'roadNoiseAboveWhoPct': 61.3,
    },
    'Kingston upon Thames': {
        'impact': 'low-moderate',
        'avgPrice': 597587,
        'trend': 4.9,
        'schools': 'excellent',
        'crimeRate': 67.1,
        'p8': 0.65,
        'transport': 'good',
        'healthcare': 'good',
        'airQualityWhoRatio': 1.65,
        'floodMediumOrHighPct': 5.66,
        'roadNoiseAboveWhoPct': 53.6,
    },
    'Sutton': {
        'impact': 'low',
        'avgPrice': 458954,
        'trend': 1.5,
        'schools': 'excellent',
        'crimeRate': 61.3,
        'p8': 0.45,
        'transport': 'good',
        'healthcare': 'moderate',
        'airQualityWhoRatio': 1.64,
        'floodMediumOrHighPct': 0.29,
        'roadNoiseAboveWhoPct': 48.5,
    },
    'Westminster': {
        'impact': 'moderate',
        'avgPrice': 887206,
        'trend': -14.3,
        'schools': 'good',
        'crimeRate': 342.1,
        'p8': 0.47,
        'transport': 'excellent',
        'healthcare': 'excellent',
        'airQualityWhoRatio': 2.84,
        'floodMediumOrHighPct': 0.02,
        'roadNoiseAboveWhoPct': 87.8,
    },
    'City of London': {
        # ONS declines to publish a recorded-crime rate here (Table C4 note 8,
        # small resident population), so the 190 below is Sky Score's own
        # estimate and must never be attributed to them. Flagged in the data
        # rather than in a name list so the fact travels with the row.
        # METHODOLOGY 11 records it as an open decision.
        'crimeEstimated': True,
        'impact': 'low-moderate',
        'avgPrice': 726633,
        'trend': -14.6,
        'schools': 'good',
        'crimeRate': 190,
        'transport': 'excellent',
        'healthcare': 'moderate',
        'airQualityWhoRatio': 3.25,
        'floodMediumOrHighPct': 0.0,
        'roadNoiseAboveWhoPct': 95.0,
    },
    'Barking and Dagenham': {
        'impact': 'low',
        'avgPrice': 369881,
        'trend': 4.7,
        'schools': 'good',
        'crimeRate': 84.7,
        'p8': 0.24,
        'transport': 'moderate',
        'healthcare': 'excellent',
        'airQualityWhoRatio': 1.83,
        'floodMediumOrHighPct': 0.97,
        'roadNoiseAboveWhoPct': 61.0,
    },
    'Havering': {
        'impact': 'low',
        'avgPrice': 444572,
        'trend': 1.1,
        'schools': 'good',
        'crimeRate': 68.9,
        'p8': 0.11,
        'transport': 'moderate',
        'healthcare': 'moderate',
        'airQualityWhoRatio': 1.65,
        'floodMediumOrHighPct': 0.18,
        'roadNoiseAboveWhoPct': 49.1,
    },
    'Bexley': {
        'impact': 'low',
        'avgPrice': 414833,
        'trend': 1.9,
        'schools': 'good',
        'crimeRate': 60.9,
        'p8': -0.02,
        'transport': 'moderate',
        'healthcare': 'good',
        'airQualityWhoRatio': 1.7,
        'floodMediumOrHighPct': 0.55,
        'roadNoiseAboveWhoPct': 53.7,
    },
    'Harrow': {
        'impact': 'low',
        'avgPrice': 532173,
        'trend': -2.5,
        'schools': 'excellent',
        'crimeRate': 60.6,
        'p8': 0.46,
        'transport': 'good',
        'healthcare': 'good',
        'airQualityWhoRatio': 1.64,
        'floodMediumOrHighPct': 0.91,
        'roadNoiseAboveWhoPct': 44.0,
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
        'impact': 'moderate-high',
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
        'impact': 'moderate',
        'avgPrice': 420000,
        'trend': 5.5,
        'schools': 'good',
        'crimeRate': 110,
        'transport': 'good',
        'healthcare': 'good',
    },
    'Staten Island': {
        'impact': 'low-moderate',
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
#                     data tables, Table C4, CRIME_EDITION_LABEL (year ending March 2026 until the
#                     2026-10-23 roll, written by refresh_crime_from_ons.py --write-lambda) - the same
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
#   p8                REAL. DfE Key Stage 4 Progress 8, 2023/24, local-authority
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
    'Manchester': {'impact': 'moderate', 'avgPrice': 256760, 'trend': 2.1, 'p8': 0.07, 'crimeRate': 143.0, 'transport': 'good', 'healthcare': 'good', 'airQualityWhoRatio': 1.6, 'floodMediumOrHighPct': 1.2, 'roadNoiseAboveWhoPct': 57.2},
    'Salford': {'impact': 'low', 'avgPrice': 223323, 'trend': -1.7, 'p8': -0.35, 'crimeRate': 105.6, 'transport': 'moderate', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.5, 'floodMediumOrHighPct': 0.73, 'roadNoiseAboveWhoPct': 64.2},
    'Stockport': {'impact': 'moderate-high', 'avgPrice': 319016, 'trend': 3.9, 'p8': 0.09, 'crimeRate': 74.4, 'transport': 'moderate', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.46, 'floodMediumOrHighPct': 0.45, 'roadNoiseAboveWhoPct': 44.9},
    'Trafford': {'impact': 'moderate', 'avgPrice': 393897, 'trend': 6.4, 'p8': 0.35, 'crimeRate': 74.1, 'transport': 'good', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.41, 'floodMediumOrHighPct': 0.33, 'roadNoiseAboveWhoPct': 52.2},
    'Tameside': {'impact': 'low', 'avgPrice': 213026, 'trend': 1.4, 'p8': -0.21, 'crimeRate': 96.2, 'transport': 'moderate', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.53, 'floodMediumOrHighPct': 0.38, 'roadNoiseAboveWhoPct': 55.1},
    'Oldham': {'impact': 'low', 'avgPrice': 217171, 'trend': 4.6, 'p8': -0.2, 'crimeRate': 105.5, 'transport': 'moderate', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.49, 'floodMediumOrHighPct': 0.53, 'roadNoiseAboveWhoPct': 53.5},
    'Rochdale': {'impact': 'low', 'avgPrice': 211022, 'trend': 3.3, 'p8': -0.3, 'crimeRate': 103.3, 'transport': 'moderate', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.41, 'floodMediumOrHighPct': 1.16, 'roadNoiseAboveWhoPct': 54.0},
    'Bury': {'impact': 'low', 'avgPrice': 243107, 'trend': 2.8, 'p8': -0.09, 'crimeRate': 93.8, 'transport': 'moderate', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.42, 'floodMediumOrHighPct': 0.98, 'roadNoiseAboveWhoPct': 55.8},
    'Bolton': {'impact': 'low', 'avgPrice': 204379, 'trend': 4.8, 'p8': 0.05, 'crimeRate': 97.4, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.37, 'floodMediumOrHighPct': 0.66, 'roadNoiseAboveWhoPct': 54.4},
    'Wigan': {'impact': 'low', 'avgPrice': 194551, 'trend': 2.8, 'p8': -0.32, 'crimeRate': 90.1, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.34, 'floodMediumOrHighPct': 1.32, 'roadNoiseAboveWhoPct': 47.0},
}

# West Midlands, the fourth city, 2026-08-10. Every field is generated, not
# authored, and each has a script that re-derives it:
#
#   avgPrice / trend  REAL. HM Land Registry UK HPI, the vintage named by
#                     SNAPSHOT_VINTAGE_LABEL - the same release London and
#                     Greater Manchester use, so the three cohorts are on one
#                     vintage. (This line named the June 2026 release until
#                     the July roll; a month in a comment is a claim nothing
#                     rolls.)
#                     `scripts/build_hpi_prices.py --check --city westmidlands`
#                     is a blocking preflight stage.
#
#   crimeRate         REAL. ONS Crime in England and Wales, Police Force Area
#                     tables, Table C4, CRIME_EDITION_LABEL (March 2026 until the 2026-10-23 roll) - Community
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
    'Birmingham': {'impact': 'moderate-high', 'avgPrice': 234867, 'trend': 1.5, 'crimeRate': 115.7, 'p8': 0.06, 'transport': 'moderate', 'healthcare': 'good', 'airQualityWhoRatio': 1.58, 'floodMediumOrHighPct': 1.18, 'roadNoiseAboveWhoPct': 46.9},
    'Coventry': {'impact': 'low', 'avgPrice': 227679, 'trend': 3.8, 'crimeRate': 88.7, 'p8': 0.01, 'transport': 'poor', 'healthcare': 'good', 'airQualityWhoRatio': 1.5, 'floodMediumOrHighPct': 0.17, 'roadNoiseAboveWhoPct': 52.2},
    'Dudley': {'impact': 'low', 'avgPrice': 233819, 'trend': 3.4, 'crimeRate': 74.7, 'p8': -0.12, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.47, 'floodMediumOrHighPct': 0.15, 'roadNoiseAboveWhoPct': 49.9},
    'Sandwell': {'impact': 'low', 'avgPrice': 207065, 'trend': 0.0, 'crimeRate': 95.9, 'p8': -0.16, 'transport': 'moderate', 'healthcare': 'good', 'airQualityWhoRatio': 1.61, 'floodMediumOrHighPct': 0.41, 'roadNoiseAboveWhoPct': 59.2},
    'Solihull': {'impact': 'moderate-high', 'avgPrice': 332022, 'trend': 0.2, 'crimeRate': 80.7, 'p8': -0.06, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.46, 'floodMediumOrHighPct': 0.26, 'roadNoiseAboveWhoPct': 40.4},
    'Walsall': {'impact': 'low', 'avgPrice': 216878, 'trend': 2.6, 'crimeRate': 95.6, 'p8': -0.22, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.61, 'floodMediumOrHighPct': 1.06, 'roadNoiseAboveWhoPct': 54.7},
    'Wolverhampton': {'impact': 'low', 'avgPrice': 215801, 'trend': 2.7, 'crimeRate': 92.4, 'p8': -0.05, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.49, 'floodMediumOrHighPct': 0.16, 'roadNoiseAboveWhoPct': 44.9},
}

WESTYORKSHIRE_BOROUGHS = {
    'Bradford': {'impact': 'low', 'avgPrice': 185297, 'trend': 2.1, 'crimeRate': 116.0, 'p8': -0.28, 'transport': 'moderate', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.36, 'floodMediumOrHighPct': 1.54, 'roadNoiseAboveWhoPct': 50.0},
    'Calderdale': {'impact': 'low', 'avgPrice': 197651, 'trend': 7.8, 'crimeRate': 102.1, 'p8': 0.02, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.3, 'floodMediumOrHighPct': 4.16, 'roadNoiseAboveWhoPct': 58.7},
    'Kirklees': {'impact': 'low', 'avgPrice': 208427, 'trend': 5.1, 'crimeRate': 86.1, 'p8': 0.07, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.4, 'floodMediumOrHighPct': 1.48, 'roadNoiseAboveWhoPct': 51.6},
    'Leeds': {'impact': 'moderate', 'avgPrice': 246385, 'trend': 2.4, 'crimeRate': 113.1, 'p8': 0.1, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.46, 'floodMediumOrHighPct': 0.87, 'roadNoiseAboveWhoPct': 50.9},
    'Wakefield': {'impact': 'low', 'avgPrice': 199347, 'trend': 2.9, 'crimeRate': 103.1, 'p8': 0.04, 'transport': 'moderate', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.43, 'floodMediumOrHighPct': 1.07, 'roadNoiseAboveWhoPct': 48.8},
}

SOUTHYORKSHIRE_BOROUGHS = {
    'Barnsley': {'impact': 'low', 'avgPrice': 173053, 'trend': 2.0, 'crimeRate': 94.2, 'p8': -0.32, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.41, 'floodMediumOrHighPct': 0.93, 'roadNoiseAboveWhoPct': 44.0},
    'Doncaster': {'impact': 'low', 'avgPrice': 172305, 'trend': 3.8, 'crimeRate': 116.7, 'p8': 0.0, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.47, 'floodMediumOrHighPct': 7.46, 'roadNoiseAboveWhoPct': 38.9},
    'Rotherham': {'impact': 'low', 'avgPrice': 191496, 'trend': 0.7, 'crimeRate': 96.4, 'p8': -0.18, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.5, 'floodMediumOrHighPct': 1.12, 'roadNoiseAboveWhoPct': 40.9},
    'Sheffield': {'impact': 'low', 'avgPrice': 217603, 'trend': 0.6, 'crimeRate': 97.3, 'p8': -0.16, 'transport': 'moderate', 'healthcare': 'good', 'airQualityWhoRatio': 1.47, 'floodMediumOrHighPct': 0.9, 'roadNoiseAboveWhoPct': 46.7},
}

MERSEYSIDE_BOROUGHS = {
    'Knowsley': {'impact': 'low', 'avgPrice': 191550, 'trend': 1.6, 'crimeRate': 81.5, 'p8': -0.9, 'transport': 'moderate', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.36, 'floodMediumOrHighPct': 0.18, 'roadNoiseAboveWhoPct': 46.1},
    'Liverpool': {'impact': 'moderate', 'avgPrice': 188427, 'trend': 4.7, 'crimeRate': 123.0, 'p8': -0.48, 'transport': 'moderate', 'healthcare': 'good', 'airQualityWhoRatio': 1.34, 'floodMediumOrHighPct': 0.27, 'roadNoiseAboveWhoPct': 51.1},
    'St Helens': {'impact': 'low', 'avgPrice': 186445, 'trend': 5.1, 'crimeRate': 85.7, 'p8': -0.32, 'transport': 'moderate', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.35, 'floodMediumOrHighPct': 0.29, 'roadNoiseAboveWhoPct': 46.2},
    'Sefton': {'impact': 'low', 'avgPrice': 221105, 'trend': 2.0, 'crimeRate': 75.3, 'p8': -0.41, 'transport': 'moderate', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.21, 'floodMediumOrHighPct': 0.26, 'roadNoiseAboveWhoPct': 40.8},
    'Wirral': {'impact': 'low', 'avgPrice': 221849, 'trend': 5.8, 'crimeRate': 70.2, 'p8': -0.16, 'transport': 'moderate', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.18, 'floodMediumOrHighPct': 0.54, 'roadNoiseAboveWhoPct': 50.4},
}

TYNEANDWEAR_BOROUGHS = {
    'Gateshead': {'impact': 'low', 'avgPrice': 155550, 'trend': 4.4, 'crimeRate': 88.7, 'p8': -0.14, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.19, 'floodMediumOrHighPct': 1.0, 'roadNoiseAboveWhoPct': 59.6},
    'Newcastle upon Tyne': {'impact': 'moderate-high', 'avgPrice': 211255, 'trend': 5.8, 'crimeRate': 108.8, 'p8': -0.28, 'transport': 'moderate', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.24, 'floodMediumOrHighPct': 0.13, 'roadNoiseAboveWhoPct': 59.8},
    'North Tyneside': {'impact': 'moderate', 'avgPrice': 205744, 'trend': 3.7, 'crimeRate': 82.0, 'p8': -0.15, 'transport': 'moderate', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.24, 'floodMediumOrHighPct': 0.16, 'roadNoiseAboveWhoPct': 58.7},
    'South Tyneside': {'impact': 'low', 'avgPrice': 160518, 'trend': 2.5, 'crimeRate': 95.5, 'p8': -0.39, 'transport': 'moderate', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.24, 'floodMediumOrHighPct': 0.0, 'roadNoiseAboveWhoPct': 56.0},
    'Sunderland': {'impact': 'low', 'avgPrice': 147763, 'trend': 4.6, 'crimeRate': 93.6, 'p8': -0.31, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.2, 'floodMediumOrHighPct': 0.15, 'roadNoiseAboveWhoPct': 55.6},
}

BRISTOL_BOROUGHS = {
    'City of Bristol': {'impact': 'low', 'avgPrice': 353596, 'trend': 0.9, 'crimeRate': 127.6, 'p8': -0.01, 'transport': 'moderate', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.32, 'floodMediumOrHighPct': 0.95, 'roadNoiseAboveWhoPct': 34.8},
    'Bath and North East Somerset': {'impact': 'moderate', 'avgPrice': 406084, 'trend': -1.8, 'crimeRate': 78.2, 'p8': 0.16, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.21, 'floodMediumOrHighPct': 2.39, 'roadNoiseAboveWhoPct': 33.7},
    'North Somerset': {'impact': 'moderate-high', 'avgPrice': 314307, 'trend': 3.6, 'crimeRate': 79.5, 'p8': -0.05, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.11, 'floodMediumOrHighPct': 1.29, 'roadNoiseAboveWhoPct': 26.6},
    'South Gloucestershire': {'impact': 'low', 'avgPrice': 335572, 'trend': 1.0, 'crimeRate': 71.8, 'p8': -0.16, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.31, 'floodMediumOrHighPct': 0.32, 'roadNoiseAboveWhoPct': 31.2},
}

CARDIFF_BOROUGHS = {
    'Cardiff': {'impact': 'low', 'avgPrice': 272252, 'trend': 2.1, 'crimeRate': 94.7, 'transport': 'moderate', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.22},
    'Vale of Glamorgan': {'impact': 'moderate', 'avgPrice': 300358, 'trend': 3.2, 'crimeRate': 62.8, 'transport': 'moderate', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.01},
    'Newport': {'impact': 'low', 'avgPrice': 225702, 'trend': -0.1, 'crimeRate': 112.4, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.19},
    'Caerphilly': {'impact': 'low', 'avgPrice': 198545, 'trend': 4.4, 'crimeRate': 87.0, 'transport': 'moderate', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.09},
}


# Leicester and Leicestershire: the city plus all seven county districts.
# The whole county rather than the three contiguous boroughs, because a
# four-authority cohort spans only 230k-281k and min-max scaling over a narrow
# cohort manufactures spread it has not measured.
#
# p8 is present for the CITY ONLY, and that is structural rather than a gap to
# fill: education is an UPPER-TIER function, so DfE publishes Progress 8 for
# Leicestershire, not for Blaby or Charnwood. crimeRate IS present for all
# eight - unlike Nottingham, every one has its own ONS Community Safety
# Partnership row - and transport and healthcare carry every borough over the
# two-input floor regardless.
LEICESTER_BOROUGHS = {
    'Leicester': {'impact': 'low', 'avgPrice': 227322, 'trend': -1.5, 'crimeRate': 106.8, 'p8': 0.1, 'transport': 'poor', 'healthcare': 'good', 'airQualityWhoRatio': 1.58, 'floodMediumOrHighPct': 1.4, 'roadNoiseAboveWhoPct': 35.1},
    'Blaby': {'impact': 'low', 'avgPrice': 293412, 'trend': 3.4, 'crimeRate': 58.6, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.47, 'floodMediumOrHighPct': 0.56, 'roadNoiseAboveWhoPct': 40.6},
    'Charnwood': {'impact': 'low-moderate', 'avgPrice': 270351, 'trend': 0.4, 'crimeRate': 67.7, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.45, 'floodMediumOrHighPct': 2.04, 'roadNoiseAboveWhoPct': 31.5},
    'Harborough': {'impact': 'low', 'avgPrice': 341706, 'trend': 5.0, 'crimeRate': 44.3, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.35, 'floodMediumOrHighPct': 0.08, 'roadNoiseAboveWhoPct': 33.9},
    'Hinckley and Bosworth': {'impact': 'low', 'avgPrice': 258960, 'trend': -0.1, 'crimeRate': 57.7, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.41, 'floodMediumOrHighPct': 0.04, 'roadNoiseAboveWhoPct': 36.0},
    'Melton': {'impact': 'low', 'avgPrice': 286469, 'trend': 4.1, 'crimeRate': 56.6, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.3, 'floodMediumOrHighPct': 0.58, 'roadNoiseAboveWhoPct': 39.9},
    'North West Leicestershire': {'impact': 'moderate', 'avgPrice': 282397, 'trend': 1.7, 'crimeRate': 58.8, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.37, 'floodMediumOrHighPct': 0.75, 'roadNoiseAboveWhoPct': 33.3},
    'Oadby and Wigston': {'impact': 'low', 'avgPrice': 257504, 'trend': -1.5, 'crimeRate': 52.8, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.45, 'floodMediumOrHighPct': 0.25, 'roadNoiseAboveWhoPct': 27.7},
}

# Teesside: the five Tees Valley unitaries. Darlington is included because it
# is in the Tees Valley Combined Authority and travel-to-work area, which costs
# an include-list in the crime loader - Darlington is Durham Constabulary while
# the other four are Cleveland.
TEESSIDE_BOROUGHS = {
    'Hartlepool': {'impact': 'low', 'avgPrice': 136894, 'trend': 4.7, 'crimeRate': 136.7, 'p8': -0.47, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.09, 'roadNoiseAboveWhoPct': 48.0, 'floodMediumOrHighPct': 0.45},
    'Middlesbrough': {'impact': 'low', 'avgPrice': 142868, 'trend': 3.7, 'crimeRate': 153.7, 'p8': -0.45, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.19, 'roadNoiseAboveWhoPct': 53.8, 'floodMediumOrHighPct': 0.53},
    'Redcar and Cleveland': {'impact': 'low', 'avgPrice': 146259, 'trend': -3.0, 'crimeRate': 109.8, 'p8': -0.36, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.06, 'roadNoiseAboveWhoPct': 48.1, 'floodMediumOrHighPct': 0.67},
    'Stockton-on-Tees': {'impact': 'moderate', 'avgPrice': 172698, 'trend': 3.1, 'crimeRate': 117.1, 'p8': -0.19, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.15, 'roadNoiseAboveWhoPct': 45.9, 'floodMediumOrHighPct': 1.86},
    'Darlington': {'impact': 'moderate', 'avgPrice': 159988, 'trend': 1.9, 'crimeRate': 91.5, 'p8': -0.32, 'transport': 'moderate', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.09, 'roadNoiseAboveWhoPct': 53.1, 'floodMediumOrHighPct': 6.09},
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
    'City of Nottingham': {'impact': 'low', 'avgPrice': 189547, 'trend': -1.8, 'crimeRate': 128.2, 'p8': -0.25, 'transport': 'moderate', 'healthcare': 'good', 'airQualityWhoRatio': 1.54, 'floodMediumOrHighPct': 3.51, 'roadNoiseAboveWhoPct': 42.8},
    'Broxtowe': {'impact': 'low-moderate', 'avgPrice': 251231, 'trend': -4.0, 'transport': 'moderate', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.48, 'floodMediumOrHighPct': 0.82, 'roadNoiseAboveWhoPct': 36.1},
    'Gedling': {'impact': 'low', 'avgPrice': 245028, 'trend': 2.1, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.48, 'floodMediumOrHighPct': 2.52, 'roadNoiseAboveWhoPct': 27.2},
    'Rushcliffe': {'impact': 'moderate', 'avgPrice': 329528, 'trend': -1.0, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.37, 'floodMediumOrHighPct': 0.79, 'roadNoiseAboveWhoPct': 29.5},
}

# Greater Norwich (added 2026-09-27, API-only): the three authorities of the
# Greater Norwich Local Plan. Composition and why it is not all of Norfolk:
# CITY_LADS in scripts/build_hpi_prices.py.
#
# UNLIKE Nottingham, every one of the three has its OWN ONS Community Safety
# Partnership row in Table C4, so crime is measured for all three. Like
# Nottingham's districts, NONE has Progress 8: Norfolk County Council is the
# education authority, and DfE publishes P8 for Norfolk, not its districts.
# That absence is the honest reading, not a gap to fill with the county figure.
#
# Every field below is written by a script (avgPrice/trend by
# build_hpi_prices.py, crimeRate by refresh_crime_from_ons.py, impact by
# build_aircraft_bands.py, the rest by build_borough_bands.py); do not
# hand-edit.
NORWICH_BOROUGHS = {
    'Norwich': {'impact': 'moderate', 'avgPrice': 227535, 'trend': -2.0, 'crimeRate': 108.3, 'transport': 'poor', 'healthcare': 'good', 'airQualityWhoRatio': 1.49, 'floodMediumOrHighPct': 0.43, 'roadNoiseAboveWhoPct': 48.1},
    'Broadland': {'impact': 'moderate-high', 'avgPrice': 313407, 'trend': 2.8, 'crimeRate': 34.4, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.42, 'floodMediumOrHighPct': 0.57, 'roadNoiseAboveWhoPct': 30.0},
    'South Norfolk': {'impact': 'low', 'avgPrice': 307735, 'trend': -0.2, 'crimeRate': 41.8, 'transport': 'poor', 'healthcare': 'moderate', 'airQualityWhoRatio': 1.38, 'floodMediumOrHighPct': 0.56, 'roadNoiseAboveWhoPct': 33.8},
}

# The San Francisco Bay Area's 50 cities (release 2, 2026-10-22), scored by CITIES['bayarea'] (the API only:
# the site shows them as facts until its own release, SITE_FACTS_ONLY_CITIES). Every field is joined by Census
# GEOID from the readers' committed files (field-by-field sources in scripts/build_bayarea_records.py), and the
# US measures carry their own names so no UK ramp can read them: crimePer1000Us, roadNoiseUsSharePct and
# floodSfhaPct go to us_anchored_to_score against US_CALIFORNIA_ANCHORS. A city missing an input carries the
# reader's reason in `withheld`, published as context.inputsWithheld.
# BAYAREA-BOROUGHS:START (generated by scripts/build_bayarea_records.py --write; do not hand-edit)
US_CALIFORNIA_ANCHORS = {'crimePer1000Us': 21.39, 'roadNoiseUsSharePct': 6.88, 'floodSfhaPct': 3.14}
BAYAREA_BOROUGHS = {
    'Alameda': {'impact': 'high', 'avgPrice': 1235700, 'priceTopCoded': False, 'trend': -1.91, 'county': 'Alameda', 'crimePer1000Us': 39.9, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 13.3, 'floodSfhaPct': 7.04},
    'Albany': {'impact': 'low', 'avgPrice': 1202200, 'priceTopCoded': False, 'trend': -1.91, 'county': 'Alameda', 'crimePer1000Us': 25.5, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 10.2, 'floodSfhaPct': 0.0},
    'Atherton': {'impact': 'low', 'avgPrice': 2000001, 'priceTopCoded': True, 'trend': -0.61, 'county': 'San Mateo', 'crimePer1000Us': 8.6, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 1.3, 'floodSfhaPct': 0.0},
    'Belmont': {'impact': 'low-moderate', 'avgPrice': 2000001, 'priceTopCoded': True, 'trend': -0.61, 'county': 'San Mateo', 'crimePer1000Us': 13.2, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 5.4, 'floodSfhaPct': 1.4},
    'Berkeley': {'impact': 'low-moderate', 'avgPrice': 1413900, 'priceTopCoded': False, 'trend': -1.91, 'county': 'Alameda', 'crimePer1000Us': 46.5, 'crimeFewResidents': False, 'transport': 'moderate', 'roadNoiseUsSharePct': 11.2, 'floodSfhaPct': 0.0},
    'Brisbane': {'impact': 'moderate', 'avgPrice': 1232200, 'priceTopCoded': False, 'trend': -0.61, 'county': 'San Mateo', 'crimePer1000Us': 9.9, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 7.0, 'floodSfhaPct': 0.62},
    'Burlingame': {'impact': 'moderate-high', 'avgPrice': 2000001, 'priceTopCoded': True, 'trend': -0.61, 'county': 'San Mateo', 'crimePer1000Us': 20.4, 'crimeFewResidents': False, 'transport': 'moderate', 'roadNoiseUsSharePct': 11.8, 'floodSfhaPct': 3.38},
    'Campbell': {'impact': 'low', 'avgPrice': 1617000, 'priceTopCoded': False, 'trend': -0.63, 'county': 'Santa Clara', 'crimePer1000Us': 27.9, 'crimeFewResidents': False, 'transport': 'moderate', 'roadNoiseUsSharePct': 11.7, 'floodSfhaPct': None, 'withheld': {'floodSfhaPct': 'FEMA has not determined the flood risk for 9% of residents (zone D or unmapped)'}},
    'Colma': {'impact': 'moderate', 'avgPrice': 1062000, 'priceTopCoded': False, 'trend': -0.61, 'county': 'San Mateo', 'crimePer1000Us': 469.3, 'crimeFewResidents': True, 'transport': 'excellent', 'roadNoiseUsSharePct': 8.3, 'floodSfhaPct': 0.0},
    'Cupertino': {'impact': 'low', 'avgPrice': 2000001, 'priceTopCoded': True, 'trend': -0.63, 'county': 'Santa Clara', 'crimePer1000Us': 15.2, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 7.4, 'floodSfhaPct': None, 'withheld': {'floodSfhaPct': 'FEMA has not determined the flood risk for 27% of residents (zone D or unmapped)'}},
    'Daly City': {'impact': 'moderate', 'avgPrice': 1115000, 'priceTopCoded': False, 'trend': -0.61, 'county': 'San Mateo', 'crimePer1000Us': 16.0, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 8.5, 'floodSfhaPct': 0.0},
    'Dublin': {'impact': 'low', 'avgPrice': 1317100, 'priceTopCoded': False, 'trend': -1.91, 'county': 'Alameda', 'crimePer1000Us': 15.1, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 5.5, 'floodSfhaPct': 0.28},
    'East Palo Alto': {'impact': 'low', 'avgPrice': 1102600, 'priceTopCoded': False, 'trend': -0.61, 'county': 'San Mateo', 'crimePer1000Us': 21.4, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 15.0, 'floodSfhaPct': 32.45},
    'Emeryville': {'impact': 'low-moderate', 'avgPrice': 604800, 'priceTopCoded': False, 'trend': -1.91, 'county': 'Alameda', 'crimePer1000Us': 109.1, 'crimeFewResidents': True, 'transport': None, 'roadNoiseUsSharePct': 24.8, 'floodSfhaPct': 0.0, 'withheld': {'transport': "its only rail station, Capitol Corridor's, is absent from BTS's transit layer, and with it put back the city reads good, not poor (measured 2026-10-22)"}},
    'Foster City': {'impact': 'moderate', 'avgPrice': 1838200, 'priceTopCoded': False, 'trend': -0.61, 'county': 'San Mateo', 'crimePer1000Us': 8.3, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 6.3, 'floodSfhaPct': 2.15},
    'Fremont': {'impact': 'low-moderate', 'avgPrice': 1403800, 'priceTopCoded': False, 'trend': -1.91, 'county': 'Alameda', 'crimePer1000Us': 18.1, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 6.9, 'floodSfhaPct': 0.63},
    'Gilroy': {'impact': 'low', 'avgPrice': 1027400, 'priceTopCoded': False, 'trend': -0.63, 'county': 'Santa Clara', 'crimePer1000Us': 23.1, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 5.9, 'floodSfhaPct': None, 'withheld': {'floodSfhaPct': 'FEMA has not determined the flood risk for 13% of residents (zone D or unmapped)'}},
    'Half Moon Bay': {'impact': 'low-moderate', 'avgPrice': 1549500, 'priceTopCoded': False, 'trend': -0.61, 'county': 'San Mateo', 'crimePer1000Us': None, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 3.8, 'floodSfhaPct': 0.27, 'withheld': {'crimePer1000Us': "policed by the San Mateo County Sheriff under contract; DOJ counts its crime in the sheriff's county figures, so it has no rate of its own"}},
    'Hayward': {'impact': 'moderate', 'avgPrice': 854400, 'priceTopCoded': False, 'trend': -1.91, 'county': 'Alameda', 'crimePer1000Us': 30.7, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 11.1, 'floodSfhaPct': 2.02},
    'Hillsborough': {'impact': 'low-moderate', 'avgPrice': 2000001, 'priceTopCoded': True, 'trend': -0.61, 'county': 'San Mateo', 'crimePer1000Us': 5.1, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 3.5, 'floodSfhaPct': 0.0},
    'Livermore': {'impact': 'low', 'avgPrice': 1105600, 'priceTopCoded': False, 'trend': -1.91, 'county': 'Alameda', 'crimePer1000Us': 19.9, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 4.8, 'floodSfhaPct': 1.06},
    'Los Altos': {'impact': 'low', 'avgPrice': 2000001, 'priceTopCoded': True, 'trend': -0.63, 'county': 'Santa Clara', 'crimePer1000Us': 10.5, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 4.6, 'floodSfhaPct': None, 'withheld': {'floodSfhaPct': 'FEMA has not determined the flood risk for 8% of residents (zone D or unmapped)'}},
    'Los Altos Hills': {'impact': 'low', 'avgPrice': 2000001, 'priceTopCoded': True, 'trend': -0.63, 'county': 'Santa Clara', 'crimePer1000Us': 3.8, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 2.6, 'floodSfhaPct': None, 'withheld': {'floodSfhaPct': 'FEMA has not determined the flood risk for 5% of residents (zone D or unmapped)'}},
    'Los Gatos': {'impact': 'low', 'avgPrice': 2000001, 'priceTopCoded': True, 'trend': -0.63, 'county': 'Santa Clara', 'crimePer1000Us': 13.7, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 7.3, 'floodSfhaPct': None, 'withheld': {'floodSfhaPct': 'FEMA has not determined the flood risk for 9% of residents (zone D or unmapped)'}},
    'Menlo Park': {'impact': 'low', 'avgPrice': 2000001, 'priceTopCoded': True, 'trend': -0.61, 'county': 'San Mateo', 'crimePer1000Us': 17.2, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 7.8, 'floodSfhaPct': 14.83},
    'Millbrae': {'impact': 'high', 'avgPrice': 1934900, 'priceTopCoded': False, 'trend': -0.61, 'county': 'San Mateo', 'crimePer1000Us': None, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 12.1, 'floodSfhaPct': 3.2, 'withheld': {'crimePer1000Us': "policed by the San Mateo County Sheriff under contract; DOJ counts its crime in the sheriff's county figures, so it has no rate of its own"}},
    'Milpitas': {'impact': 'low-moderate', 'avgPrice': 1251700, 'priceTopCoded': False, 'trend': -0.63, 'county': 'Santa Clara', 'crimePer1000Us': 31.1, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 10.0, 'floodSfhaPct': None, 'withheld': {'floodSfhaPct': 'FEMA has not determined the flood risk for 10% of residents (zone D or unmapped)'}},
    'Monte Sereno': {'impact': 'low', 'avgPrice': 2000001, 'priceTopCoded': True, 'trend': -0.63, 'county': 'Santa Clara', 'crimePer1000Us': 4.5, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 0.9, 'floodSfhaPct': 0.0},
    'Morgan Hill': {'impact': 'low', 'avgPrice': 1210200, 'priceTopCoded': False, 'trend': -0.63, 'county': 'Santa Clara', 'crimePer1000Us': 16.3, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 2.6, 'floodSfhaPct': None, 'withheld': {'floodSfhaPct': 'FEMA has not determined the flood risk for 7% of residents (zone D or unmapped)'}},
    'Mountain View': {'impact': 'low', 'avgPrice': 1927000, 'priceTopCoded': False, 'trend': -0.63, 'county': 'Santa Clara', 'crimePer1000Us': 26.9, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 8.6, 'floodSfhaPct': 0.05},
    'Newark': {'impact': 'low-moderate', 'avgPrice': 1142800, 'priceTopCoded': False, 'trend': -1.91, 'county': 'Alameda', 'crimePer1000Us': 32.4, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 5.7, 'floodSfhaPct': 2.36},
    'Oakland': {'impact': 'low-moderate', 'avgPrice': 929900, 'priceTopCoded': False, 'trend': -1.91, 'county': 'Alameda', 'crimePer1000Us': 67.5, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 17.0, 'floodSfhaPct': 0.81},
    'Pacifica': {'impact': 'moderate-high', 'avgPrice': 1249800, 'priceTopCoded': False, 'trend': -0.61, 'county': 'San Mateo', 'crimePer1000Us': 10.9, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 4.3, 'floodSfhaPct': 1.56},
    'Palo Alto': {'impact': 'low', 'avgPrice': 2000001, 'priceTopCoded': True, 'trend': -0.63, 'county': 'Santa Clara', 'crimePer1000Us': 30.1, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 5.3, 'floodSfhaPct': 22.59},
    'Piedmont': {'impact': 'low-moderate', 'avgPrice': 2000001, 'priceTopCoded': True, 'trend': -1.91, 'county': 'Alameda', 'crimePer1000Us': 20.5, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 2.8, 'floodSfhaPct': 0.0},
    'Pleasanton': {'impact': 'low', 'avgPrice': 1537100, 'priceTopCoded': False, 'trend': -1.91, 'county': 'Alameda', 'crimePer1000Us': 14.9, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 6.2, 'floodSfhaPct': 4.08},
    'Portola Valley': {'impact': 'low', 'avgPrice': 2000001, 'priceTopCoded': True, 'trend': -0.61, 'county': 'San Mateo', 'crimePer1000Us': None, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 1.6, 'floodSfhaPct': 4.58, 'withheld': {'crimePer1000Us': "policed by the San Mateo County Sheriff under contract; DOJ counts its crime in the sheriff's county figures, so it has no rate of its own"}},
    'Redwood City': {'impact': 'low-moderate', 'avgPrice': 1801700, 'priceTopCoded': False, 'trend': -0.61, 'county': 'San Mateo', 'crimePer1000Us': 18.3, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 9.2, 'floodSfhaPct': 12.83},
    'San Bruno': {'impact': 'high', 'avgPrice': 1207500, 'priceTopCoded': False, 'trend': -0.61, 'county': 'San Mateo', 'crimePer1000Us': 16.4, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 11.0, 'floodSfhaPct': 3.95},
    'San Carlos': {'impact': 'low', 'avgPrice': 2000001, 'priceTopCoded': True, 'trend': -0.61, 'county': 'San Mateo', 'crimePer1000Us': None, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 3.3, 'floodSfhaPct': 1.63, 'withheld': {'crimePer1000Us': "policed by the San Mateo County Sheriff under contract; DOJ counts its crime in the sheriff's county figures, so it has no rate of its own"}},
    'San Francisco': {'impact': 'low-moderate', 'avgPrice': 1394500, 'priceTopCoded': False, 'trend': 0.5, 'county': 'San Francisco', 'crimePer1000Us': 33.7, 'crimeFewResidents': False, 'transport': 'good', 'roadNoiseUsSharePct': 12.2, 'floodSfhaPct': 0.29},
    'San Jose': {'impact': 'low-moderate', 'avgPrice': 1233200, 'priceTopCoded': False, 'trend': -0.63, 'county': 'Santa Clara', 'crimePer1000Us': 28.9, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 7.6, 'floodSfhaPct': None, 'withheld': {'floodSfhaPct': 'FEMA has not determined the flood risk for 76% of residents (zone D or unmapped)'}},
    'San Leandro': {'impact': 'high', 'avgPrice': 844200, 'priceTopCoded': False, 'trend': -1.91, 'county': 'Alameda', 'crimePer1000Us': 34.4, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 10.4, 'floodSfhaPct': 7.11},
    'San Mateo': {'impact': 'moderate', 'avgPrice': 1618700, 'priceTopCoded': False, 'trend': -0.61, 'county': 'San Mateo', 'crimePer1000Us': 16.4, 'crimeFewResidents': False, 'transport': 'moderate', 'roadNoiseUsSharePct': 16.4, 'floodSfhaPct': 2.92},
    'Santa Clara': {'impact': 'low-moderate', 'avgPrice': 1582600, 'priceTopCoded': False, 'trend': -0.63, 'county': 'Santa Clara', 'crimePer1000Us': 27.6, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 4.1, 'floodSfhaPct': 5.42},
    'Saratoga': {'impact': 'low', 'avgPrice': 2000001, 'priceTopCoded': True, 'trend': -0.63, 'county': 'Santa Clara', 'crimePer1000Us': 5.5, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 5.3, 'floodSfhaPct': 0.85},
    'South San Francisco': {'impact': 'severe', 'avgPrice': 1188800, 'priceTopCoded': False, 'trend': -0.61, 'county': 'San Mateo', 'crimePer1000Us': 15.1, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 10.4, 'floodSfhaPct': 1.5},
    'Sunnyvale': {'impact': 'low-moderate', 'avgPrice': 1801800, 'priceTopCoded': False, 'trend': -0.63, 'county': 'Santa Clara', 'crimePer1000Us': 20.4, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 6.4, 'floodSfhaPct': 8.12},
    'Union City': {'impact': 'moderate', 'avgPrice': 1104900, 'priceTopCoded': False, 'trend': -1.91, 'county': 'Alameda', 'crimePer1000Us': 22.5, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 7.7, 'floodSfhaPct': 3.67},
    'Woodside': {'impact': 'low', 'avgPrice': 2000001, 'priceTopCoded': True, 'trend': -0.61, 'county': 'San Mateo', 'crimePer1000Us': None, 'crimeFewResidents': False, 'transport': 'poor', 'roadNoiseUsSharePct': 4.3, 'floodSfhaPct': 0.0, 'withheld': {'crimePer1000Us': "policed by the San Mateo County Sheriff under contract; DOJ counts its crime in the sheriff's county figures, so it has no rate of its own"}},
}
# BAYAREA-BOROUGHS:END

# The Census's top code for ACS table B25077: a city whose median home value is "$2,000,000+" is carried as
# 2,000,001 (scripts/build_bayarea_prices.py; Bill, 2026-10-17: kept in the formula, flagged) and published as
# at least this, never as a price (calc_score; validate_us_fields holds the encoding).
US_PRICE_TOP_CODE = 2_000_000

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
            if local_postcode_served()
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
        # local_postcode_served() caught it on the first run.
        'postcodeResolver': lambda: (
            'ONS NSPL local table by LAD code, postcodes.io fallback'
            if local_postcode_served()
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
        # local_postcode_served() caught it on the first run.
        'postcodeResolver': lambda: (
            'ONS NSPL local table by LAD code, postcodes.io fallback'
            if local_postcode_served()
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
        # local_postcode_served() caught it on the first run.
        'postcodeResolver': lambda: (
            'ONS NSPL local table by LAD code, postcodes.io fallback'
            if local_postcode_served()
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
        # local_postcode_served() caught it on the first run.
        'postcodeResolver': lambda: (
            'ONS NSPL local table by LAD code, postcodes.io fallback'
            if local_postcode_served()
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
        # local_postcode_served() caught it on the first run.
        'postcodeResolver': lambda: (
            'ONS NSPL local table by LAD code, postcodes.io fallback'
            if local_postcode_served()
            else 'postcodes.io'
        ),
        # Omitted, so False: postdates PREVIOUS_VINTAGE, so ?compare=previous
        # must decline rather than report a fabricated zero change.
    },
    'leicester': {
        'boroughs': LEICESTER_BOROUGHS,
        'currency': 'GBP',
        'name': 'Leicester',
        'country': 'United Kingdom',
        'postcodeFormat': 'UK postcode (e.g. LE1 1AA)',
        'postcodeResolver': lambda: (
            'ONS NSPL local table by LAD code, postcodes.io fallback'
            if local_postcode_served()
            else 'postcodes.io'
        ),
        # Omitted, so False: postdates PREVIOUS_VINTAGE, so ?compare=previous
        # must decline rather than report a fabricated zero change.
    },
    'teesside': {
        'boroughs': TEESSIDE_BOROUGHS,
        'currency': 'GBP',
        'name': 'Teesside',
        'country': 'United Kingdom',
        'postcodeFormat': 'UK postcode (e.g. TS1 1AA)',
        'postcodeResolver': lambda: (
            'ONS NSPL local table by LAD code, postcodes.io fallback'
            if local_postcode_served()
            else 'postcodes.io'
        ),
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
        # local_postcode_served() caught it on the first run.
        'postcodeResolver': lambda: (
            'ONS NSPL local table by LAD code, postcodes.io fallback'
            if local_postcode_served()
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
        # local_postcode_served() caught it on the first run.
        'postcodeResolver': lambda: (
            'ONS NSPL local table by LAD code, postcodes.io fallback'
            if local_postcode_served()
            else 'postcodes.io'
        ),
        # Omitted, so False: postdates PREVIOUS_VINTAGE, so ?compare=previous
        # must decline rather than report a fabricated zero change.
    },
    'norwich': {
        'boroughs': NORWICH_BOROUGHS,
        'currency': 'GBP',
        'name': 'Greater Norwich',
        'country': 'United Kingdom',
        'postcodeFormat': 'UK postcode (e.g. NR1 1AA)',
        'postcodeResolver': lambda: (
            'ONS NSPL local table by LAD code, postcodes.io fallback'
            if local_postcode_served()
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
        # local_postcode_served() caught it on the first run.
        'postcodeResolver': lambda: (
            'ONS NSPL local table by LAD code, postcodes.io fallback'
            if local_postcode_served()
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
        # local_postcode_served() caught it on the first run.
        'postcodeResolver': lambda: (
            'ONS NSPL local table by LAD code, postcodes.io fallback'
            if local_postcode_served()
            else 'postcodes.io'
        ),
        # Omitted deliberately, which means False: Greater Manchester did not
        # exist at PREVIOUS_VINTAGE, so ?compare=previous must DECLINE rather
        # than return the current set and present a fabricated zero change.
        # 'hasHistory': False,
    },
    # The San Francisco Bay Area's 50 cities (release 2, 2026-10-22): the API scores them, the site shows
    # them as facts until its own release (SITE_FACTS_ONLY_CITIES below). Its own POOL (decision 2): pooled
    # with New York by currency, the "$2M+" top code would set the p95 and move New York's published
    # affordability (Queens 6.5 -> 9.9). Reached by city NAME only for now: the Lambda holds no Bay Area ZIP
    # table, and a ZIP spans cities (resolve_query says so on a Bay Area ZIP rather than guessing one).
    # hasHistory omitted, so ?compare=previous declines: no previous vintage was ever held.
    'bayarea': {
        'boroughs': BAYAREA_BOROUGHS,
        'currency': 'USD',
        'pool': 'bayarea',
        'name': 'San Francisco Bay Area',
        'country': 'United States',
        'postcodeFormat': 'none yet: query a Bay Area city by name (borough=Palo Alto); ZIPs are not resolved',
        'postcodeResolver': lambda: 'none (by city name only)',
        # The anchors its US fields are scored against (validate_us_fields): California's, measured.
        'usAnchors': US_CALIFORNIA_ANCHORS,
        # Bill, 2026-10-22 (the code review): FHFA's trend is COUNTY-wide, so the 50 cities hold four values,
        # and scaled against each other they sat on the rails by construction (San Francisco +0.5%, a fall
        # after inflation, 10.0; all 14 Alameda cities 0.0): the shape v5.2 went national to remove. Held out,
        # its weight redistributed, until a wider US trend cohort is held. Published in coverage.notices.
        'growthNotScored': (
            "FHFA's price trend is county-wide, so the Bay Area's 50 cities hold only four values, and scaled "
            'against each other they read as extremes they do not have; context.priceTrendPct reports the '
            "county's change as a fact"
        ),
    },
}

# Cities the API scores and the consumer site does NOT yet: the site renders them as FACTS, with no score
# (CITY_DATA[city].facts). Bill, 2026-10-22: "API first, site second". Declared, never inferred, and held BOTH
# ways by tests/test_borough_data_parity.py and tests/borough-score-parity.mjs: a city here must render no score
# on the site, and a site city that renders facts while the API scores it must be here. Leaving this set is
# the same one-way door as leaving BACKEND_ONLY_CITIES: the site must then reproduce the API on every borough.
# scripts/build_area_pages.py writes no scored page for these.
SITE_FACTS_ONLY_CITIES = frozenset({'bayarea'})

# v5.1: the real-terms trend, attached to every sterling city's records here
# rather than written into the thirteen borough tables above. IN PLACE, so the
# module constants (LONDON_BOROUGHS, ...) and the registry keep sharing one
# object - `build_hpi_prices.py --write` edits the constants' source text and
# the tests read them by name, and a copy here would let the two disagree on
# a field that scores. New York's records gain nothing (no series held) and
# scored_trend() falls back to nominal for them by construction.
for _cfg in CITIES.values():
    for _name, _bd in with_real_trends(_cfg['boroughs'], SNAPSHOT_VINTAGE, _cfg['currency']).items():
        _cfg['boroughs'][_name].update(_bd)
del _cfg, _name, _bd

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


# A US measure fills the SAME scoring slot as its UK counterpart, on a scale that is not comparable with it
# (us_anchored_to_score against California's figures; the UK ramps against WHO and the EA's thresholds). So a
# record carrying both, or a US field in a city that names no California anchor, would score on whichever
# field happened to be read first. Checked at import, like the vocabulary above, so it fails pytest and the SAM
# build instead.
_US_FIELD_REPLACES = {
    'crimePer1000Us': 'crimeRate',
    'roadNoiseUsSharePct': 'roadNoiseAboveWhoPct',
    'floodSfhaPct': 'floodMediumOrHighPct',
}
# context.inputsWithheld names the scoring INPUT, in the vocabulary sourceBreakdown and the resolutions use,
# not the record's field name, which is internal.
_WITHHELD_INPUT_OF = {'crimePer1000Us': 'crimeRate', 'transport': 'transport', 'floodSfhaPct': 'flood'}


def validate_us_fields(cities):
    """Raise on a US measure that could be scored on the wrong scale, or a withheld input that is not one."""
    problems = []
    for city_id, cfg in cities.items():
        for name, bd in cfg['boroughs'].items():
            for us_field, uk_field in _US_FIELD_REPLACES.items():
                if bd.get(us_field) is None:
                    continue
                if cfg.get('usAnchors') is not US_CALIFORNIA_ANCHORS:
                    problems.append(f'{city_id}/{name}: {us_field} is scored on California\'s anchor, which {city_id} does not name')
                if bd.get(uk_field) is not None:
                    problems.append(f'{city_id}/{name}: carries both {us_field} and {uk_field}')
            if bd.get('priceTopCoded') and bd['avgPrice'] != US_PRICE_TOP_CODE + 1:
                problems.append(f'{city_id}/{name}: top-coded at {bd["avgPrice"]}, not the floor {US_PRICE_TOP_CODE + 1}')
            for field, reason in (bd.get('withheld') or {}).items():
                if field not in _WITHHELD_INPUT_OF:
                    problems.append(f'{city_id}/{name}: withheld {field!r} is not an input any scorer reads')
                elif bd.get(field) is not None:
                    problems.append(f'{city_id}/{name}: {field} is withheld yet carries a value')
                elif not reason:
                    problems.append(f'{city_id}/{name}: {field} is withheld with no reason')
    if problems:
        raise ValueError('Borough records a US scale could misread:\n  ' + '\n  '.join(problems))


validate_us_fields(CITIES)


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

# Flight path geometry: list of paths, each with a sequence of (lat, lon)
# waypoints at 1 km. Distance to the nearest waypoint is the proxy for distance
# to the corridor, same approach as the consumer site.
#
# London's corridors are DERIVED FROM THE UK AIP since 2026-09-26 (methodology
# v5.3): every runway's final approach from its published threshold, bearing and
# glide angle, and every departure from the published route - Heathrow's Noise
# Preferential Routes, London City's RNAV SID coding tables. They replaced a
# hand-drawn set in which Ockham and Bovingdon ran due north-south into two
# east-west runways. The procedure each line came from is recorded in
# data/flight-procedures.json. Do not edit between the markers: change the
# procedures and run scripts/build_flight_paths.py --write, which rewrites this
# block and index.html's FLIGHT_PATHS together. `--check` is blocking in
# preflight, and test_flight_path_geometry_matches_the_site still compares the
# two holders directly.
# FLIGHT-PATHS-LONDON:START (generated by scripts/build_flight_paths.py --write; do not hand-edit)
FLIGHT_PATHS_LONDON = [
    {
        'name': 'LCY 09 final approach',
        'airport': 'LCY',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [
            (51.5099, -0.0926),
            (51.5094, -0.0781),
            (51.509, -0.0637),
            (51.5085, -0.0493),
            (51.5081, -0.0349),
            (51.5076, -0.0205),
            (51.5072, -0.0061),
            (51.5067, 0.0083),
            (51.5062, 0.0228),
            (51.5058, 0.0372),
            (51.5056, 0.0443),
        ],
    },
    {
        'name': 'LCY 27 final approach',
        'airport': 'LCY',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (51.5006, 0.2029),
            (51.501, 0.1885),
            (51.5015, 0.1741),
            (51.5019, 0.1597),
            (51.5024, 0.1452),
            (51.5028, 0.1308),
            (51.5033, 0.1164),
            (51.5038, 0.102),
            (51.5042, 0.0876),
            (51.5047, 0.0732),
            (51.5049, 0.066),
        ],
    },
    {
        'name': 'LCY 27 departure via BPK1A',
        'airport': 'LCY',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (51.5056, 0.0443),
            (51.506, 0.0299),
            (51.5065, 0.0155),
            (51.5096, 0.0044),
            (51.5183, 0.0003),
            (51.5269, -0.0039),
            (51.5356, -0.008),
            (51.5442, -0.0122),
            (51.5529, -0.0163),
            (51.5607, -0.0159),
            (51.5664, -0.0047),
            (51.5721, 0.0065),
            (51.5778, 0.0177),
            (51.5835, 0.0288),
            (51.5892, 0.04),
            (51.5953, 0.0481),
            (51.6029, 0.0404),
            (51.6106, 0.0328),
            (51.6183, 0.0251),
            (51.6259, 0.0174),
            (51.6336, 0.0097),
        ],
    },
    {
        'name': 'LCY 09 departure via BPK1H',
        'airport': 'LCY',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (51.5049, 0.066),
            (51.5044, 0.0804),
            (51.506, 0.0909),
            (51.5148, 0.0876),
            (51.5236, 0.0843),
            (51.5324, 0.081),
            (51.5413, 0.0777),
            (51.5501, 0.0744),
            (51.5589, 0.0711),
            (51.5677, 0.0678),
            (51.5765, 0.0645),
            (51.5846, 0.0587),
            (51.5923, 0.0511),
            (51.5999, 0.0434),
            (51.6076, 0.0357),
            (51.6153, 0.028),
            (51.6229, 0.0204),
            (51.6306, 0.0127),
            (51.6382, 0.005),
            (51.6459, -0.0027),
            (51.6536, -0.0104),
        ],
    },
    {
        'name': 'LCY 27 departure via ODUKU1A',
        'airport': 'LCY',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (51.5056, 0.0443),
            (51.506, 0.0299),
            (51.5065, 0.0155),
            (51.5097, 0.0053),
            (51.5187, 0.0038),
            (51.5277, 0.0023),
            (51.5367, 0.0008),
            (51.5457, -0.0006),
            (51.5547, -0.0021),
            (51.5637, -0.0036),
            (51.5699, 0.0013),
            (51.5723, 0.0153),
            (51.5747, 0.0292),
            (51.5772, 0.0431),
            (51.5796, 0.057),
            (51.582, 0.0709),
            (51.5844, 0.0848),
            (51.5868, 0.0987),
            (51.5892, 0.1126),
            (51.5916, 0.1265),
            (51.594, 0.1404),
        ],
    },
    {
        'name': 'LCY 09 departure via ODUKU1H',
        'airport': 'LCY',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (51.5049, 0.066),
            (51.5044, 0.0804),
            (51.5056, 0.0938),
            (51.5123, 0.1034),
            (51.519, 0.1131),
            (51.5258, 0.1227),
            (51.5325, 0.1324),
            (51.5392, 0.142),
            (51.5459, 0.1517),
            (51.5527, 0.1613),
            (51.5574, 0.1733),
            (51.5613, 0.1863),
            (51.5653, 0.1993),
            (51.5692, 0.2123),
            (51.5732, 0.2253),
            (51.5771, 0.2383),
            (51.5811, 0.2512),
            (51.585, 0.2642),
            (51.589, 0.2772),
        ],
    },
    {
        'name': 'LCY 09 departure via SOQQA1H',
        'airport': 'LCY',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (51.5049, 0.066),
            (51.5044, 0.0804),
            (51.5056, 0.0938),
            (51.5123, 0.1034),
            (51.519, 0.1131),
            (51.5258, 0.1227),
            (51.5325, 0.1324),
            (51.5392, 0.142),
            (51.5459, 0.1517),
            (51.5527, 0.1613),
            (51.5557, 0.1742),
            (51.5572, 0.1885),
            (51.5587, 0.2027),
            (51.5602, 0.2169),
            (51.5617, 0.2312),
            (51.5635, 0.2452),
            (51.5674, 0.2583),
            (51.5712, 0.2713),
            (51.5751, 0.2844),
            (51.5789, 0.2975),
            (51.5828, 0.3105),
        ],
    },
    {
        'name': 'LHR 09L final approach',
        'airport': 'LHR',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [
            (51.4766, -0.7366),
            (51.4766, -0.7222),
            (51.4767, -0.7078),
            (51.4767, -0.6934),
            (51.4768, -0.6789),
            (51.4769, -0.6645),
            (51.4769, -0.6501),
            (51.477, -0.6357),
            (51.477, -0.6213),
            (51.4771, -0.6068),
            (51.4771, -0.5924),
            (51.4772, -0.578),
            (51.4772, -0.5636),
            (51.4773, -0.5491),
            (51.4773, -0.5347),
            (51.4774, -0.5203),
            (51.4774, -0.5059),
            (51.4775, -0.4915),
            (51.4775, -0.485),
        ],
    },
    {
        'name': 'LHR 09R final approach',
        'airport': 'LHR',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [
            (51.4639, -0.734),
            (51.464, -0.7195),
            (51.464, -0.7051),
            (51.4641, -0.6907),
            (51.4641, -0.6763),
            (51.4642, -0.6618),
            (51.4642, -0.6474),
            (51.4643, -0.633),
            (51.4643, -0.6186),
            (51.4644, -0.6042),
            (51.4644, -0.5897),
            (51.4645, -0.5753),
            (51.4645, -0.5609),
            (51.4646, -0.5465),
            (51.4646, -0.532),
            (51.4647, -0.5176),
            (51.4647, -0.5032),
            (51.4648, -0.4888),
            (51.4648, -0.4823),
        ],
    },
    {
        'name': 'LHR 27L final approach',
        'airport': 'LHR',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (51.4657, -0.1824),
            (51.4657, -0.1969),
            (51.4656, -0.2113),
            (51.4656, -0.2257),
            (51.4655, -0.2401),
            (51.4655, -0.2546),
            (51.4655, -0.269),
            (51.4654, -0.2834),
            (51.4654, -0.2978),
            (51.4653, -0.3123),
            (51.4653, -0.3267),
            (51.4652, -0.3411),
            (51.4652, -0.3555),
            (51.4651, -0.3699),
            (51.4651, -0.3844),
            (51.4651, -0.3988),
            (51.465, -0.4132),
            (51.465, -0.4276),
            (51.465, -0.4341),
        ],
    },
    {
        'name': 'LHR 27R final approach',
        'airport': 'LHR',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (51.4785, -0.1816),
            (51.4784, -0.1961),
            (51.4784, -0.2105),
            (51.4783, -0.2249),
            (51.4783, -0.2393),
            (51.4782, -0.2537),
            (51.4782, -0.2682),
            (51.4782, -0.2826),
            (51.4781, -0.297),
            (51.4781, -0.3114),
            (51.478, -0.3259),
            (51.478, -0.3403),
            (51.4779, -0.3547),
            (51.4779, -0.3691),
            (51.4778, -0.3836),
            (51.4778, -0.398),
            (51.4777, -0.4124),
            (51.4777, -0.4268),
            (51.4777, -0.4333),
        ],
    },
    {
        'name': 'LHR 09 departure via Brookmans Park',
        'airport': 'LHR',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (51.4713, -0.4337),
            (51.4763, -0.4259),
            (51.4821, -0.4148),
            (51.4879, -0.4037),
            (51.4937, -0.3926),
            (51.4995, -0.3816),
            (51.5053, -0.3705),
            (51.5102, -0.3586),
            (51.5131, -0.345),
            (51.516, -0.3313),
            (51.5189, -0.3177),
            (51.5219, -0.304),
            (51.5248, -0.2904),
            (51.5277, -0.2767),
            (51.5306, -0.263),
            (51.5335, -0.2494),
            (51.5364, -0.2357),
            (51.5393, -0.2221),
            (51.5425, -0.2086),
            (51.5485, -0.198),
            (51.5567, -0.1924),
        ],
    },
    {
        'name': 'LHR 27 departure via Brookmans Park',
        'airport': 'LHR',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (51.4711, -0.4837),
            (51.4753, -0.4965),
            (51.4794, -0.5093),
            (51.4836, -0.5221),
            (51.4877, -0.5349),
            (51.4918, -0.5478),
            (51.496, -0.5606),
            (51.5001, -0.5734),
            (51.5043, -0.5862),
            (51.5084, -0.5991),
            (51.5125, -0.6119),
            (51.5169, -0.6245),
            (51.5237, -0.6338),
            (51.5323, -0.6376),
            (51.5411, -0.6348),
            (51.548, -0.6257),
            (51.5548, -0.6161),
            (51.5615, -0.6065),
            (51.5683, -0.5969),
            (51.575, -0.5872),
            (51.5817, -0.5776),
        ],
    },
    {
        'name': 'LHR 09 departure via Compton',
        'airport': 'LHR',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (51.4713, -0.4337),
            (51.4698, -0.4233),
            (51.4646, -0.4117),
            (51.4567, -0.4049),
            (51.4478, -0.4042),
            (51.4396, -0.41),
            (51.4338, -0.4209),
            (51.4321, -0.4347),
            (51.4327, -0.4491),
            (51.4334, -0.4635),
            (51.4341, -0.4779),
            (51.4348, -0.4923),
            (51.4354, -0.5066),
            (51.4361, -0.521),
            (51.4368, -0.5354),
            (51.4374, -0.5498),
            (51.4381, -0.5642),
            (51.4388, -0.5786),
            (51.4394, -0.5929),
            (51.4401, -0.6073),
            (51.4408, -0.6217),
        ],
    },
    {
        'name': 'LHR 27 departure via Compton',
        'airport': 'LHR',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (51.4711, -0.4837),
            (51.4711, -0.4981),
            (51.4711, -0.5125),
            (51.471, -0.5269),
            (51.471, -0.5413),
            (51.4709, -0.5558),
            (51.4709, -0.5702),
            (51.4692, -0.5843),
            (51.467, -0.5983),
            (51.4649, -0.6123),
            (51.4627, -0.6263),
            (51.4606, -0.6403),
            (51.4588, -0.6545),
            (51.4584, -0.6689),
            (51.458, -0.6833),
            (51.4576, -0.6977),
            (51.4573, -0.7121),
            (51.4569, -0.7265),
            (51.4565, -0.7409),
            (51.4561, -0.7553),
            (51.4557, -0.7697),
        ],
    },
    {
        'name': 'LHR 09 departure via Detling',
        'airport': 'LHR',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (51.4713, -0.4337),
            (51.4672, -0.4248),
            (51.4625, -0.4125),
            (51.4578, -0.4002),
            (51.4532, -0.3878),
            (51.449, -0.3751),
            (51.4467, -0.3612),
            (51.4444, -0.3472),
            (51.4421, -0.3333),
            (51.4398, -0.3194),
            (51.4375, -0.3054),
            (51.4352, -0.2915),
            (51.433, -0.2774),
            (51.431, -0.2634),
            (51.4289, -0.2494),
            (51.4268, -0.2353),
            (51.4247, -0.2213),
            (51.4227, -0.2072),
            (51.4206, -0.1932),
            (51.4185, -0.1792),
            (51.4165, -0.1651),
        ],
    },
    {
        'name': 'LHR 27 departure via Detling',
        'airport': 'LHR',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (51.4711, -0.4837),
            (51.4711, -0.4981),
            (51.4711, -0.5125),
            (51.4691, -0.5265),
            (51.4637, -0.5378),
            (51.4556, -0.544),
            (51.4467, -0.544),
            (51.4388, -0.5373),
            (51.432, -0.5279),
            (51.4251, -0.5184),
            (51.4183, -0.5089),
            (51.4115, -0.4995),
            (51.4047, -0.49),
            (51.3978, -0.4805),
            (51.391, -0.4711),
            (51.3842, -0.4616),
            (51.3774, -0.4521),
            (51.3705, -0.4427),
            (51.3637, -0.4332),
            (51.3569, -0.4238),
            (51.3501, -0.4143),
        ],
    },
    {
        'name': 'LHR 09 departure via GASGU',
        'airport': 'LHR',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (51.4713, -0.4337),
            (51.4698, -0.4233),
            (51.4649, -0.4112),
            (51.4597, -0.3994),
            (51.4545, -0.3876),
            (51.4493, -0.3758),
            (51.4441, -0.3641),
            (51.4379, -0.3575),
            (51.4296, -0.3631),
            (51.4213, -0.3687),
            (51.4129, -0.3743),
            (51.4046, -0.38),
            (51.3963, -0.3856),
            (51.388, -0.3912),
            (51.3796, -0.3968),
            (51.3713, -0.4025),
            (51.363, -0.4081),
            (51.3546, -0.4137),
            (51.3463, -0.4193),
            (51.338, -0.4249),
            (51.3297, -0.4306),
        ],
    },
    {
        'name': 'LHR 27 departure via GOGSI',
        'airport': 'LHR',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (51.4711, -0.4837),
            (51.4711, -0.4981),
            (51.4711, -0.5125),
            (51.471, -0.5269),
            (51.471, -0.5413),
            (51.4709, -0.5558),
            (51.4709, -0.5702),
            (51.4692, -0.5843),
            (51.467, -0.5983),
            (51.4649, -0.6123),
            (51.4627, -0.6263),
            (51.4606, -0.6403),
            (51.4588, -0.6545),
            (51.4588, -0.6689),
            (51.4587, -0.6833),
            (51.4586, -0.6977),
            (51.4585, -0.7121),
            (51.4584, -0.7266),
            (51.4584, -0.741),
            (51.4583, -0.7554),
            (51.4582, -0.7698),
        ],
    },
    {
        'name': 'LHR 27 departure via MAXIT',
        'airport': 'LHR',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (51.4711, -0.4837),
            (51.4711, -0.4981),
            (51.4711, -0.5125),
            (51.471, -0.5269),
            (51.471, -0.5413),
            (51.4709, -0.5558),
            (51.4709, -0.5702),
            (51.4692, -0.5843),
            (51.4662, -0.5972),
            (51.4581, -0.6036),
            (51.4499, -0.61),
            (51.4418, -0.6163),
            (51.4337, -0.6227),
            (51.4255, -0.6265),
            (51.4169, -0.6219),
            (51.4084, -0.6173),
            (51.3998, -0.6126),
            (51.3912, -0.608),
            (51.3827, -0.6033),
            (51.3741, -0.5987),
            (51.3656, -0.5941),
        ],
    },
    {
        'name': 'LHR 09 departure via MODMI',
        'airport': 'LHR',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (51.4713, -0.4337),
            (51.4698, -0.4233),
            (51.4649, -0.4112),
            (51.4597, -0.3994),
            (51.4545, -0.3877),
            (51.4476, -0.3786),
            (51.4389, -0.3752),
            (51.4301, -0.3784),
            (51.4218, -0.3839),
            (51.4134, -0.3894),
            (51.405, -0.3948),
            (51.3967, -0.4003),
            (51.3883, -0.4058),
            (51.38, -0.4113),
            (51.3716, -0.4168),
            (51.3632, -0.4223),
            (51.3549, -0.4277),
            (51.3465, -0.4332),
            (51.3381, -0.4387),
            (51.3298, -0.4442),
            (51.3214, -0.4497),
        ],
    },
    {
        'name': 'LHR 09 departure via ULTIB',
        'airport': 'LHR',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (51.4713, -0.4337),
            (51.4763, -0.4259),
            (51.4821, -0.4148),
            (51.4879, -0.4037),
            (51.4937, -0.3926),
            (51.4995, -0.3816),
            (51.5053, -0.3705),
            (51.5102, -0.3586),
            (51.5131, -0.345),
            (51.516, -0.3313),
            (51.5189, -0.3177),
            (51.5219, -0.304),
            (51.5248, -0.2904),
            (51.5277, -0.2767),
            (51.5306, -0.263),
            (51.5335, -0.2494),
            (51.5364, -0.2357),
            (51.5393, -0.2221),
            (51.544, -0.2163),
            (51.5518, -0.2237),
            (51.5596, -0.2311),
        ],
    },
    {
        'name': 'LHR 27 departure via UMLAT',
        'airport': 'LHR',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (51.4711, -0.4837),
            (51.4753, -0.4965),
            (51.4794, -0.5093),
            (51.4836, -0.5221),
            (51.4877, -0.5349),
            (51.4918, -0.5478),
            (51.496, -0.5606),
            (51.5001, -0.5734),
            (51.5043, -0.5862),
            (51.5084, -0.5991),
            (51.5125, -0.6119),
            (51.5167, -0.6247),
            (51.5208, -0.6375),
            (51.5223, -0.651),
            (51.5205, -0.6651),
            (51.5203, -0.6773),
            (51.5293, -0.6783),
            (51.5384, -0.6792),
            (51.5474, -0.6802),
            (51.5564, -0.6811),
            (51.5654, -0.6821),
        ],
    },
]
# FLIGHT-PATHS-LONDON:END


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
# FLIGHT-PATHS-MANCHESTER:START (generated by scripts/build_flight_paths.py --write; do not hand-edit)
FLIGHT_PATHS_MANCHESTER = [
    {
        'name': 'MAN 05L final approach',
        'airport': 'MAN',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [
            (53.2484, -2.492),
            (53.2541, -2.4803),
            (53.2597, -2.4686),
            (53.2654, -2.4569),
            (53.2711, -2.4452),
            (53.2768, -2.4335),
            (53.2825, -2.4218),
            (53.2882, -2.4101),
            (53.2939, -2.3983),
            (53.2995, -2.3866),
            (53.3052, -2.3749),
            (53.3109, -2.3632),
            (53.3166, -2.3515),
            (53.3223, -2.3398),
            (53.328, -2.3281),
            (53.3336, -2.3164),
            (53.3393, -2.3047),
            (53.345, -2.293),
            (53.3476, -2.2878),
        ],
    },
    {
        'name': 'MAN 05R final approach',
        'airport': 'MAN',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [
            (53.2328, -2.5148),
            (53.2384, -2.5031),
            (53.2441, -2.4914),
            (53.2498, -2.4797),
            (53.2555, -2.468),
            (53.2612, -2.4563),
            (53.2669, -2.4446),
            (53.2726, -2.4329),
            (53.2782, -2.4212),
            (53.2839, -2.4095),
            (53.2896, -2.3978),
            (53.2953, -2.3861),
            (53.301, -2.3744),
            (53.3067, -2.3627),
            (53.3124, -2.351),
            (53.3181, -2.3393),
            (53.3237, -2.3276),
            (53.3294, -2.3159),
            (53.332, -2.3107),
        ],
    },
    {
        'name': 'MAN 23L final approach',
        'airport': 'MAN',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (53.4473, -2.073),
            (53.4416, -2.0847),
            (53.4359, -2.0964),
            (53.4303, -2.1081),
            (53.4246, -2.1198),
            (53.4189, -2.1315),
            (53.4132, -2.1432),
            (53.4075, -2.1549),
            (53.4018, -2.1666),
            (53.3962, -2.1783),
            (53.3905, -2.19),
            (53.3848, -2.2017),
            (53.3791, -2.2134),
            (53.3734, -2.2251),
            (53.3677, -2.2368),
            (53.3621, -2.2486),
            (53.3564, -2.2603),
            (53.3507, -2.272),
            (53.3482, -2.2772),
        ],
    },
    {
        'name': 'MAN 23R final approach',
        'airport': 'MAN',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (53.4604, -2.055),
            (53.4548, -2.0667),
            (53.4491, -2.0784),
            (53.4434, -2.0901),
            (53.4377, -2.1018),
            (53.432, -2.1135),
            (53.4263, -2.1252),
            (53.4207, -2.1369),
            (53.415, -2.1487),
            (53.4093, -2.1604),
            (53.4036, -2.1721),
            (53.3979, -2.1838),
            (53.3923, -2.1955),
            (53.3866, -2.2072),
            (53.3809, -2.2189),
            (53.3752, -2.2306),
            (53.3695, -2.2423),
            (53.3639, -2.254),
            (53.3613, -2.2593),
        ],
    },
]
# FLIGHT-PATHS-MANCHESTER:END

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
# FLIGHT-PATHS-WESTMIDLANDS:START (generated by scripts/build_flight_paths.py --write; do not hand-edit)
FLIGHT_PATHS_WESTMIDLANDS = [
    {
        'name': 'BHX 15 final approach',
        'airport': 'BHX',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [
            (52.594, -1.9033),
            (52.5865, -1.895),
            (52.579, -1.8867),
            (52.5716, -1.8784),
            (52.5641, -1.8702),
            (52.5566, -1.8619),
            (52.5491, -1.8536),
            (52.5416, -1.8453),
            (52.5342, -1.837),
            (52.5267, -1.8287),
            (52.5192, -1.8204),
            (52.5117, -1.8122),
            (52.5042, -1.8039),
            (52.4968, -1.7956),
            (52.4893, -1.7873),
            (52.4818, -1.779),
            (52.4743, -1.7707),
            (52.4668, -1.7624),
            (52.4635, -1.7587),
        ],
    },
    {
        'name': 'BHX 33 final approach',
        'airport': 'BHX',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (52.3157, -1.5951),
            (52.3232, -1.6034),
            (52.3307, -1.6116),
            (52.3382, -1.6199),
            (52.3457, -1.6282),
            (52.3531, -1.6365),
            (52.3606, -1.6448),
            (52.3681, -1.6531),
            (52.3756, -1.6613),
            (52.3831, -1.6696),
            (52.3905, -1.6779),
            (52.398, -1.6862),
            (52.4055, -1.6945),
            (52.413, -1.7028),
            (52.4205, -1.711),
            (52.428, -1.7193),
            (52.4354, -1.7276),
            (52.4429, -1.7359),
            (52.4463, -1.7396),
        ],
    },
    {
        'name': 'BHX 33 departure via ADMEX1M',
        'airport': 'BHX',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (52.4635, -1.7587),
            (52.4709, -1.767),
            (52.4784, -1.7754),
            (52.4859, -1.7837),
            (52.4924, -1.7853),
            (52.4966, -1.7723),
            (52.5009, -1.7593),
            (52.5052, -1.7464),
            (52.5095, -1.7334),
            (52.5137, -1.7204),
            (52.518, -1.7074),
            (52.5223, -1.6944),
            (52.5266, -1.6814),
            (52.5277, -1.6692),
            (52.5212, -1.6588),
            (52.5148, -1.6484),
            (52.5084, -1.638),
            (52.502, -1.6276),
            (52.4956, -1.6172),
            (52.4892, -1.6068),
            (52.4828, -1.5964),
        ],
    },
    {
        'name': 'BHX 33 departure via BRUMI1M',
        'airport': 'BHX',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (52.4635, -1.7587),
            (52.4709, -1.7671),
            (52.4784, -1.7754),
            (52.4859, -1.7837),
            (52.4933, -1.792),
            (52.5008, -1.8003),
            (52.5083, -1.8086),
            (52.5157, -1.817),
            (52.5232, -1.8253),
            (52.5206, -1.8394),
            (52.518, -1.8535),
            (52.5154, -1.8676),
            (52.5128, -1.8817),
            (52.5102, -1.8958),
            (52.507, -1.9091),
            (52.4988, -1.9152),
            (52.4905, -1.9213),
            (52.4823, -1.9274),
            (52.4741, -1.9336),
            (52.4658, -1.9397),
            (52.4576, -1.9458),
        ],
    },
    {
        'name': 'BHX 15 departure via COWLY2Y',
        'airport': 'BHX',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (52.4463, -1.7396),
            (52.4388, -1.7313),
            (52.4313, -1.723),
            (52.4238, -1.7147),
            (52.4164, -1.7064),
            (52.4083, -1.7003),
            (52.3995, -1.6967),
            (52.3907, -1.6931),
            (52.382, -1.6895),
            (52.3739, -1.6829),
            (52.3658, -1.6763),
            (52.3577, -1.6698),
            (52.3498, -1.6626),
            (52.3421, -1.6548),
            (52.3345, -1.6469),
            (52.3269, -1.639),
            (52.3192, -1.6311),
            (52.3116, -1.6232),
            (52.3039, -1.6153),
            (52.2963, -1.6074),
            (52.2887, -1.5995),
        ],
    },
    {
        'name': 'BHX 15 departure via CPT2Y',
        'airport': 'BHX',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (52.4463, -1.7396),
            (52.4388, -1.7313),
            (52.4313, -1.723),
            (52.4238, -1.7147),
            (52.4164, -1.7064),
            (52.4083, -1.7003),
            (52.3995, -1.6967),
            (52.3907, -1.6931),
            (52.382, -1.6895),
            (52.3739, -1.6829),
            (52.3658, -1.6763),
            (52.3577, -1.6698),
            (52.3495, -1.6636),
            (52.3411, -1.6581),
            (52.3327, -1.6525),
            (52.3243, -1.647),
            (52.3159, -1.6415),
            (52.3076, -1.636),
            (52.2992, -1.6304),
            (52.2908, -1.6249),
            (52.2824, -1.6194),
        ],
    },
    {
        'name': 'BHX 15 departure via DTY2Y',
        'airport': 'BHX',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (52.4463, -1.7396),
            (52.4388, -1.7313),
            (52.4313, -1.723),
            (52.4238, -1.7147),
            (52.4164, -1.7064),
            (52.4083, -1.7003),
            (52.3995, -1.6967),
            (52.3907, -1.6931),
            (52.382, -1.6895),
            (52.3739, -1.6829),
            (52.3658, -1.6763),
            (52.3577, -1.6698),
            (52.3522, -1.66),
            (52.3506, -1.6455),
            (52.3489, -1.631),
            (52.3472, -1.6165),
            (52.3456, -1.602),
            (52.3439, -1.5875),
            (52.3414, -1.5735),
            (52.3373, -1.5604),
            (52.3331, -1.5472),
        ],
    },
    {
        'name': 'BHX 33 departure via LUVUM1M',
        'airport': 'BHX',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (52.4635, -1.7587),
            (52.4709, -1.767),
            (52.4784, -1.7754),
            (52.4859, -1.7837),
            (52.4934, -1.792),
            (52.5023, -1.7904),
            (52.5113, -1.7885),
            (52.5202, -1.7867),
            (52.5292, -1.7849),
            (52.5382, -1.783),
            (52.5472, -1.7812),
            (52.5561, -1.7794),
            (52.5651, -1.7775),
            (52.5741, -1.7757),
            (52.5831, -1.7739),
            (52.592, -1.7721),
            (52.601, -1.7702),
            (52.61, -1.7684),
            (52.619, -1.7666),
            (52.6279, -1.7647),
            (52.6369, -1.7629),
        ],
    },
    {
        'name': 'BHX 15 departure via LUVUM1Y',
        'airport': 'BHX',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (52.4463, -1.7396),
            (52.4388, -1.7313),
            (52.4313, -1.723),
            (52.4238, -1.7147),
            (52.4164, -1.7064),
            (52.4089, -1.6981),
            (52.4014, -1.6898),
            (52.403, -1.6757),
            (52.405, -1.6613),
            (52.407, -1.6469),
            (52.4089, -1.6325),
            (52.4109, -1.6182),
            (52.4183, -1.6122),
            (52.427, -1.6084),
            (52.4358, -1.6046),
            (52.4445, -1.6009),
            (52.4533, -1.5971),
            (52.4622, -1.5968),
            (52.4712, -1.5976),
            (52.4803, -1.5985),
            (52.4893, -1.5993),
        ],
    },
]
# FLIGHT-PATHS-WESTMIDLANDS:END

AIRPORTS_WESTYORKSHIRE = [
    {'code': 'LBA', 'name': 'Leeds Bradford', 'lat': 53.8659, 'lon': -1.6606},
]

# Leeds Bradford runway 14/32, from OurAirports. Geometry, not measurement.
# FLIGHT-PATHS-WESTYORKSHIRE:START (generated by scripts/build_flight_paths.py --write; do not hand-edit)
FLIGHT_PATHS_WESTYORKSHIRE = [
    {
        'name': 'LBA 14 final approach',
        'airport': 'LBA',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [
            (53.9715, -1.8223),
            (53.9648, -1.812),
            (53.9581, -1.8018),
            (53.9514, -1.7915),
            (53.9447, -1.7813),
            (53.938, -1.771),
            (53.9313, -1.7608),
            (53.9246, -1.7506),
            (53.9179, -1.7403),
            (53.9113, -1.7301),
            (53.9046, -1.7198),
            (53.8979, -1.7096),
            (53.8912, -1.6993),
            (53.8845, -1.6891),
            (53.8778, -1.6788),
            (53.8714, -1.6691),
        ],
    },
    {
        'name': 'LBA 32 final approach',
        'airport': 'LBA',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (53.7436, -1.4733),
            (53.7503, -1.4836),
            (53.7569, -1.4938),
            (53.7636, -1.5041),
            (53.7703, -1.5143),
            (53.777, -1.5245),
            (53.7837, -1.5348),
            (53.7904, -1.545),
            (53.7971, -1.5553),
            (53.8038, -1.5655),
            (53.8105, -1.5758),
            (53.8172, -1.586),
            (53.8239, -1.5963),
            (53.8306, -1.6065),
            (53.8373, -1.6167),
            (53.844, -1.627),
            (53.8507, -1.6372),
            (53.8574, -1.6475),
            (53.8604, -1.6521),
        ],
    },
]
# FLIGHT-PATHS-WESTYORKSHIRE:END

AIRPORTS_MERSEYSIDE = [
    {'code': 'LPL', 'name': 'Liverpool John Lennon', 'lat': 53.3349, 'lon': -2.8496},
]

# Liverpool John Lennon runway 09/27, from OurAirports. Geometry, not measurement.
# FLIGHT-PATHS-MERSEYSIDE:START (generated by scripts/build_flight_paths.py --write; do not hand-edit)
FLIGHT_PATHS_MERSEYSIDE = [
    {
        'name': 'LPL 09 final approach',
        'airport': 'LPL',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [
            (53.3208, -3.1277),
            (53.3215, -3.1127),
            (53.3222, -3.0977),
            (53.3229, -3.0827),
            (53.3236, -3.0677),
            (53.3242, -3.0527),
            (53.3249, -3.0377),
            (53.3256, -3.0227),
            (53.3263, -3.0077),
            (53.327, -2.9927),
            (53.3277, -2.9777),
            (53.3284, -2.9627),
            (53.3291, -2.9477),
            (53.3298, -2.9327),
            (53.3305, -2.9177),
            (53.3312, -2.9027),
            (53.3319, -2.8877),
            (53.3326, -2.8727),
            (53.3329, -2.866),
        ],
    },
    {
        'name': 'LPL 27 final approach',
        'airport': 'LPL',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (53.3465, -2.571),
            (53.3458, -2.586),
            (53.3451, -2.601),
            (53.3444, -2.616),
            (53.3437, -2.631),
            (53.343, -2.646),
            (53.3423, -2.661),
            (53.3416, -2.676),
            (53.3409, -2.691),
            (53.3403, -2.706),
            (53.3396, -2.721),
            (53.3389, -2.736),
            (53.3382, -2.751),
            (53.3375, -2.766),
            (53.3368, -2.781),
            (53.3361, -2.796),
            (53.3354, -2.811),
            (53.3347, -2.826),
            (53.3344, -2.8327),
        ],
    },
]
# FLIGHT-PATHS-MERSEYSIDE:END

AIRPORTS_TYNEANDWEAR = [
    {'code': 'NCL', 'name': 'Newcastle', 'lat': 55.0380, 'lon': -1.6896},
]

# Newcastle runway 07/25, from OurAirports. Geometry, not measurement.
# FLIGHT-PATHS-TYNEANDWEAR:START (generated by scripts/build_flight_paths.py --write; do not hand-edit)
FLIGHT_PATHS_TYNEANDWEAR = [
    {
        'name': 'NCL 07 final approach',
        'airport': 'NCL',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [
            (54.9678, -1.9529),
            (54.9716, -1.9387),
            (54.9754, -1.9244),
            (54.9792, -1.9102),
            (54.983, -1.896),
            (54.9867, -1.8817),
            (54.9905, -1.8675),
            (54.9943, -1.8533),
            (54.9981, -1.8391),
            (55.0019, -1.8248),
            (55.0057, -1.8106),
            (55.0095, -1.7964),
            (55.0133, -1.7821),
            (55.0171, -1.7679),
            (55.0209, -1.7537),
            (55.0247, -1.7395),
            (55.0285, -1.7252),
            (55.0323, -1.711),
            (55.034, -1.7046),
        ],
    },
    {
        'name': 'NCL 25 final approach',
        'airport': 'NCL',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (55.108, -1.4269),
            (55.1042, -1.4412),
            (55.1004, -1.4554),
            (55.0966, -1.4696),
            (55.0928, -1.4838),
            (55.089, -1.4981),
            (55.0852, -1.5123),
            (55.0814, -1.5265),
            (55.0776, -1.5408),
            (55.0738, -1.555),
            (55.07, -1.5692),
            (55.0662, -1.5835),
            (55.0625, -1.5977),
            (55.0587, -1.6119),
            (55.0549, -1.6261),
            (55.0511, -1.6404),
            (55.0473, -1.6546),
            (55.0435, -1.6688),
            (55.0418, -1.6752),
        ],
    },
    {
        'name': 'NCL 07 departure via GIRLI1T',
        'airport': 'NCL',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (55.0418, -1.6752),
            (55.0456, -1.661),
            (55.0493, -1.6467),
            (55.0531, -1.6325),
            (55.0569, -1.6182),
            (55.0606, -1.604),
            (55.0644, -1.5897),
            (55.0682, -1.5755),
            (55.0719, -1.5612),
            (55.0757, -1.547),
            (55.0795, -1.5327),
            (55.0711, -1.532),
            (55.062, -1.5321),
            (55.053, -1.5321),
            (55.0439, -1.5321),
            (55.0349, -1.5322),
            (55.0258, -1.5322),
            (55.0168, -1.5323),
            (55.0078, -1.5323),
            (54.9987, -1.5323),
            (54.9897, -1.5324),
        ],
    },
    {
        'name': 'NCL 25 departure via GIRLI1Y',
        'airport': 'NCL',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (55.034, -1.7046),
            (55.0302, -1.7189),
            (55.0264, -1.7331),
            (55.0226, -1.7473),
            (55.0188, -1.7616),
            (55.0151, -1.7758),
            (55.0097, -1.7841),
            (55.001, -1.78),
            (54.9922, -1.7759),
            (54.9835, -1.7717),
            (54.9748, -1.7676),
            (54.9661, -1.7635),
            (54.9574, -1.7593),
            (54.9486, -1.7552),
            (54.9399, -1.751),
            (54.9312, -1.7469),
            (54.9224, -1.7455),
            (54.9134, -1.7479),
            (54.9045, -1.7504),
            (54.8956, -1.7528),
            (54.8866, -1.7553),
        ],
    },
    {
        'name': 'NCL 25 departure via GIRLI3X',
        'airport': 'NCL',
        'type': 'departure',
        'freq': 'medium',
        'coords': [
            (55.034, -1.7046),
            (55.0302, -1.7189),
            (55.0264, -1.7331),
            (55.022, -1.7462),
            (55.0136, -1.752),
            (55.0052, -1.7577),
            (54.9968, -1.7635),
            (54.9884, -1.7692),
            (54.98, -1.7749),
            (54.9715, -1.7807),
            (54.9631, -1.7864),
            (54.9547, -1.7922),
            (54.9463, -1.7979),
            (54.9379, -1.8036),
            (54.9295, -1.8094),
            (54.921, -1.8151),
            (54.9126, -1.8209),
            (54.9042, -1.8266),
            (54.8958, -1.8323),
            (54.8874, -1.8381),
            (54.879, -1.8438),
        ],
    },
]
# FLIGHT-PATHS-TYNEANDWEAR:END

AIRPORTS_BRISTOL = [
    {'code': 'BRS', 'name': 'Bristol', 'lat': 51.3823, 'lon': -2.7165},
]

# Bristol runway 09/27, from OurAirports. Geometry, not measurement.
# FLIGHT-PATHS-BRISTOL:START (generated by scripts/build_flight_paths.py --write; do not hand-edit)
FLIGHT_PATHS_BRISTOL = [
    {
        'name': 'BRS 09 final approach',
        'airport': 'BRS',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [
            (51.3723, -2.9841),
            (51.3728, -2.9698),
            (51.3734, -2.9554),
            (51.374, -2.941),
            (51.3745, -2.9267),
            (51.3751, -2.9123),
            (51.3757, -2.898),
            (51.3762, -2.8836),
            (51.3768, -2.8692),
            (51.3774, -2.8549),
            (51.3779, -2.8405),
            (51.3785, -2.8261),
            (51.379, -2.8118),
            (51.3796, -2.7974),
            (51.3802, -2.783),
            (51.3807, -2.7687),
            (51.3813, -2.7543),
            (51.3819, -2.7399),
            (51.3821, -2.7335),
        ],
    },
    {
        'name': 'BRS 27 final approach',
        'airport': 'BRS',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (51.3929, -2.4559),
            (51.3924, -2.4702),
            (51.3918, -2.4846),
            (51.3912, -2.499),
            (51.3907, -2.5133),
            (51.3901, -2.5277),
            (51.3896, -2.5421),
            (51.389, -2.5564),
            (51.3884, -2.5708),
            (51.3879, -2.5852),
            (51.3873, -2.5995),
            (51.3868, -2.6139),
            (51.3862, -2.6283),
            (51.3856, -2.6426),
            (51.3851, -2.657),
            (51.3845, -2.6714),
            (51.384, -2.6857),
            (51.3834, -2.7001),
            (51.3832, -2.7065),
        ],
    },
]
# FLIGHT-PATHS-BRISTOL:END

AIRPORTS_CARDIFF = [
    {'code': 'CWL', 'name': 'Cardiff', 'lat': 51.3967, 'lon': -3.3433},
]

# Cardiff runway 12/30, from OurAirports. Geometry, not measurement.
# FLIGHT-PATHS-CARDIFF:START (generated by scripts/build_flight_paths.py --write; do not hand-edit)
FLIGHT_PATHS_CARDIFF = [
    {
        'name': 'CWL 12 final approach',
        'airport': 'CWL',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [
            (51.4715, -3.5799),
            (51.4675, -3.5671),
            (51.4634, -3.5542),
            (51.4593, -3.5414),
            (51.4552, -3.5285),
            (51.4512, -3.5156),
            (51.4471, -3.5028),
            (51.443, -3.4899),
            (51.439, -3.4771),
            (51.4349, -3.4642),
            (51.4308, -3.4514),
            (51.4267, -3.4385),
            (51.4227, -3.4256),
            (51.4186, -3.4128),
            (51.4145, -3.3999),
            (51.4104, -3.3871),
            (51.4064, -3.3742),
            (51.4023, -3.3614),
            (51.4005, -3.3556),
        ],
    },
    {
        'name': 'CWL 30 final approach',
        'airport': 'CWL',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (51.3214, -3.1059),
            (51.3254, -3.1187),
            (51.3295, -3.1316),
            (51.3336, -3.1445),
            (51.3377, -3.1573),
            (51.3417, -3.1702),
            (51.3458, -3.183),
            (51.3499, -3.1959),
            (51.354, -3.2087),
            (51.358, -3.2216),
            (51.3621, -3.2344),
            (51.3662, -3.2473),
            (51.3703, -3.2601),
            (51.3743, -3.273),
            (51.3784, -3.2859),
            (51.3825, -3.2987),
            (51.3866, -3.3116),
            (51.3906, -3.3244),
            (51.3925, -3.3302),
        ],
    },
]
# FLIGHT-PATHS-CARDIFF:END


AIRPORTS_NOTTINGHAM = [
    {'code': 'EMA', 'name': 'East Midlands', 'lat': 52.8311, 'lon': -1.3281},
]

# East Midlands runway 09/27, from OurAirports. Geometry, not measurement.
# The airport sits in Leicestershire, outside the city region.
# FLIGHT-PATHS-NOTTINGHAM:START (generated by scripts/build_flight_paths.py --write; do not hand-edit)
FLIGHT_PATHS_NOTTINGHAM = [
    {
        'name': 'EMA 09 final approach',
        'airport': 'EMA',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [
            (52.8259, -1.6062),
            (52.8261, -1.5913),
            (52.8264, -1.5765),
            (52.8267, -1.5616),
            (52.827, -1.5468),
            (52.8272, -1.5319),
            (52.8275, -1.517),
            (52.8278, -1.5022),
            (52.8281, -1.4873),
            (52.8283, -1.4725),
            (52.8286, -1.4576),
            (52.8289, -1.4427),
            (52.8292, -1.4279),
            (52.8294, -1.413),
            (52.8297, -1.3981),
            (52.83, -1.3833),
            (52.8303, -1.3684),
            (52.8305, -1.3536),
            (52.8307, -1.3469),
        ],
    },
    {
        'name': 'EMA 27 final approach',
        'airport': 'EMA',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (52.8361, -1.0493),
            (52.8358, -1.0641),
            (52.8355, -1.079),
            (52.8353, -1.0939),
            (52.835, -1.1087),
            (52.8347, -1.1236),
            (52.8344, -1.1385),
            (52.8342, -1.1533),
            (52.8339, -1.1682),
            (52.8336, -1.183),
            (52.8334, -1.1979),
            (52.8331, -1.2128),
            (52.8328, -1.2276),
            (52.8326, -1.2425),
            (52.8323, -1.2574),
            (52.832, -1.2722),
            (52.8317, -1.2871),
            (52.8315, -1.3019),
            (52.8314, -1.3086),
        ],
    },
]
# FLIGHT-PATHS-NOTTINGHAM:END

# Norwich International (EGSH), runway 09/27, in Broadland - inside its own
# cohort, like East Midlands for Leicester. Aerodrome reference point from
# UK AIP AD 2.2. NOT in DEFRA Round 4, so geometry is the only tier here.
AIRPORTS_NORWICH = [
    {'code': 'NWI', 'name': 'Norwich', 'lat': 52.675833, 'lon': 1.282778},
]

# FLIGHT-PATHS-NORWICH:START (generated by scripts/build_flight_paths.py --write; do not hand-edit)
FLIGHT_PATHS_NORWICH = [
    {
        'name': 'NWI 09 final approach',
        'airport': 'NWI',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [
            (52.6739, 1.0131),
            (52.674, 1.028),
            (52.6741, 1.0428),
            (52.6742, 1.0576),
            (52.6743, 1.0724),
            (52.6744, 1.0872),
            (52.6745, 1.102),
            (52.6747, 1.1168),
            (52.6748, 1.1317),
            (52.6749, 1.1465),
            (52.675, 1.1613),
            (52.6751, 1.1761),
            (52.6752, 1.1909),
            (52.6753, 1.2057),
            (52.6755, 1.2205),
            (52.6756, 1.2354),
            (52.6757, 1.2502),
            (52.6758, 1.265),
            (52.6758, 1.2691),
        ],
    },
    {
        'name': 'NWI 27 final approach',
        'airport': 'NWI',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (52.678, 1.5548),
            (52.6779, 1.5399),
            (52.6777, 1.5251),
            (52.6776, 1.5103),
            (52.6775, 1.4955),
            (52.6774, 1.4807),
            (52.6773, 1.4659),
            (52.6772, 1.4511),
            (52.6771, 1.4362),
            (52.677, 1.4214),
            (52.6769, 1.4066),
            (52.6767, 1.3918),
            (52.6766, 1.377),
            (52.6765, 1.3622),
            (52.6764, 1.3473),
            (52.6763, 1.3325),
            (52.6762, 1.3177),
            (52.6761, 1.3029),
            (52.676, 1.2963),
        ],
    },
]
# FLIGHT-PATHS-NORWICH:END

AIRPORTS_LEICESTER = [
    {'code': 'EMA', 'name': 'East Midlands', 'lat': 52.8311, 'lon': -1.32806},
]

# East Midlands runway 09/27, from OurAirports. Geometry, not measurement.
# Waypoints at 1 km, the common interval every corridor here uses.
# FLIGHT-PATHS-LEICESTER:START (generated by scripts/build_flight_paths.py --write; do not hand-edit)
FLIGHT_PATHS_LEICESTER = [
    {
        'name': 'EMA 09 final approach',
        'airport': 'EMA',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [
            (52.8259, -1.6062),
            (52.8261, -1.5913),
            (52.8264, -1.5765),
            (52.8267, -1.5616),
            (52.827, -1.5468),
            (52.8272, -1.5319),
            (52.8275, -1.517),
            (52.8278, -1.5022),
            (52.8281, -1.4873),
            (52.8283, -1.4725),
            (52.8286, -1.4576),
            (52.8289, -1.4427),
            (52.8292, -1.4279),
            (52.8294, -1.413),
            (52.8297, -1.3981),
            (52.83, -1.3833),
            (52.8303, -1.3684),
            (52.8305, -1.3536),
            (52.8307, -1.3469),
        ],
    },
    {
        'name': 'EMA 27 final approach',
        'airport': 'EMA',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (52.8361, -1.0493),
            (52.8358, -1.0641),
            (52.8355, -1.079),
            (52.8353, -1.0939),
            (52.835, -1.1087),
            (52.8347, -1.1236),
            (52.8344, -1.1385),
            (52.8342, -1.1533),
            (52.8339, -1.1682),
            (52.8336, -1.183),
            (52.8334, -1.1979),
            (52.8331, -1.2128),
            (52.8328, -1.2276),
            (52.8326, -1.2425),
            (52.8323, -1.2574),
            (52.832, -1.2722),
            (52.8317, -1.2871),
            (52.8315, -1.3019),
            (52.8314, -1.3086),
        ],
    },
]
# FLIGHT-PATHS-LEICESTER:END

AIRPORTS_TEESSIDE = [
    {'code': 'MME', 'name': 'Teesside International', 'lat': 54.509201, 'lon': -1.42941},
]

# Teesside International runway 05/23, from OurAirports. Geometry, not measurement.
# Waypoints at 1 km, the common interval every corridor here uses.
# FLIGHT-PATHS-TEESSIDE:START (generated by scripts/build_flight_paths.py --write; do not hand-edit)
FLIGHT_PATHS_TEESSIDE = [
    {
        'name': 'MME 05 final approach',
        'airport': 'MME',
        'type': 'arrival',
        'freq': 'medium',
        'coords': [
            (54.3955, -1.6412),
            (54.4016, -1.6298),
            (54.4077, -1.6185),
            (54.4139, -1.6071),
            (54.42, -1.5957),
            (54.4261, -1.5843),
            (54.4322, -1.5729),
            (54.4383, -1.5615),
            (54.4444, -1.5501),
            (54.4506, -1.5387),
            (54.4567, -1.5273),
            (54.4628, -1.5159),
            (54.4689, -1.5045),
            (54.475, -1.4931),
            (54.4811, -1.4817),
            (54.4873, -1.4703),
            (54.4934, -1.4589),
            (54.4995, -1.4475),
            (54.5022, -1.4424),
        ],
    },
    {
        'name': 'MME 23 final approach',
        'airport': 'MME',
        'type': 'arrival',
        'freq': 'high',
        'coords': [
            (54.6228, -1.2175),
            (54.6167, -1.2289),
            (54.6106, -1.2403),
            (54.6045, -1.2517),
            (54.5984, -1.2631),
            (54.5923, -1.2745),
            (54.5861, -1.2859),
            (54.58, -1.2973),
            (54.5739, -1.3087),
            (54.5678, -1.3201),
            (54.5617, -1.3315),
            (54.5556, -1.3429),
            (54.5495, -1.3543),
            (54.5433, -1.3657),
            (54.5372, -1.3771),
            (54.5311, -1.3885),
            (54.525, -1.3999),
            (54.5189, -1.4113),
            (54.5161, -1.4164),
        ],
    },
]
# FLIGHT-PATHS-TEESSIDE:END

# The San Francisco Bay Area's aircraft geometry: its airports, the final approaches
# and departures of the runways actually flown, and the values fitted against SFO's
# and San Jose's noise monitors. scripts/measure_us_quiet_yardstick.py --check holds it
# to the monitors. CITIES['bayarea'] is reached by city name only (no ZIP table yet), so
# calc_postcode_quiet reads it only through the city bands build_bayarea_quiet.py derives.
# US-QUIET-BAYAREA:START (generated by scripts/measure_us_quiet_yardstick.py --write; do not hand-edit)
AIRPORTS_BAYAREA = [
    {'code': 'SFO', 'name': 'San Francisco', 'lat': 37.618806, 'lon': -122.375417},
    {'code': 'OAK', 'name': 'Oakland', 'lat': 37.721261, 'lon': -122.22115},
    {'code': 'SJC', 'name': 'San Jose', 'lat': 37.362994, 'lon': -121.928619},
]
FLIGHT_PATHS_BAYAREA = [
    {
        'name': 'SFO 28L final approach',
        'airport': 'SFO',
        'kind': 'final',
        'runway': '28L',
        'coords': [
            (37.5343, -122.1752),
            (37.5384, -122.1849),
            (37.5425, -122.1946),
            (37.5466, -122.2043),
            (37.5507, -122.214),
            (37.5548, -122.2236),
            (37.5589, -122.2333),
            (37.563, -122.243),
            (37.5671, -122.2527),
            (37.5712, -122.2624),
            (37.5753, -122.2721),
            (37.5794, -122.2818),
            (37.5835, -122.2915),
            (37.5875, -122.3011),
            (37.5916, -122.3108),
            (37.5957, -122.3205),
            (37.5998, -122.3302),
            (37.6039, -122.3399),
            (37.608, -122.3496),
            (37.6121, -122.3593),
        ],
    },
    {
        'name': 'SFO 28R final approach',
        'airport': 'SFO',
        'kind': 'final',
        'runway': '28R',
        'coords': [
            (37.5401, -122.1832),
            (37.5442, -122.1929),
            (37.5483, -122.2026),
            (37.5524, -122.2124),
            (37.5565, -122.2221),
            (37.5606, -122.2318),
            (37.5647, -122.2415),
            (37.5688, -122.2512),
            (37.5729, -122.2609),
            (37.577, -122.2706),
            (37.5811, -122.2803),
            (37.5852, -122.2901),
            (37.5893, -122.2998),
            (37.5934, -122.3095),
            (37.5975, -122.3192),
            (37.6016, -122.3289),
            (37.6057, -122.3386),
            (37.6098, -122.3483),
            (37.6139, -122.3581),
        ],
    },
    {
        'name': 'OAK 28R final approach',
        'airport': 'OAK',
        'kind': 'final',
        'runway': '28R',
        'coords': [
            (37.665, -122.0213),
            (37.6684, -122.0315),
            (37.6717, -122.0417),
            (37.675, -122.0519),
            (37.6783, -122.0621),
            (37.6816, -122.0723),
            (37.685, -122.0824),
            (37.6883, -122.0926),
            (37.6916, -122.1028),
            (37.6949, -122.113),
            (37.6982, -122.1232),
            (37.7016, -122.1334),
            (37.7049, -122.1436),
            (37.7082, -122.1538),
            (37.7115, -122.164),
            (37.7149, -122.1741),
            (37.7182, -122.1843),
            (37.7215, -122.1945),
            (37.7248, -122.2047),
        ],
    },
    {
        'name': 'OAK 30 final approach',
        'airport': 'OAK',
        'kind': 'final',
        'runway': '30',
        'coords': [
            (37.6, -122.0631),
            (37.6056, -122.0715),
            (37.6113, -122.0799),
            (37.6169, -122.0883),
            (37.6226, -122.0968),
            (37.6282, -122.1052),
            (37.6339, -122.1136),
            (37.6395, -122.122),
            (37.6452, -122.1304),
            (37.6508, -122.1388),
            (37.6565, -122.1472),
            (37.6621, -122.1557),
            (37.6678, -122.1641),
            (37.6734, -122.1725),
            (37.6791, -122.1809),
            (37.6847, -122.1893),
            (37.6904, -122.1977),
            (37.696, -122.2061),
            (37.7017, -122.2146),
        ],
    },
    {
        'name': 'SJC 30L final approach',
        'airport': 'SJC',
        'kind': 'final',
        'runway': '30L',
        'coords': [
            (37.2373, -121.7933),
            (37.2439, -121.8005),
            (37.2505, -121.8077),
            (37.2571, -121.8149),
            (37.2637, -121.8221),
            (37.2703, -121.8293),
            (37.2769, -121.8365),
            (37.2835, -121.8437),
            (37.2901, -121.8509),
            (37.2967, -121.8581),
            (37.3034, -121.8653),
            (37.31, -121.8724),
            (37.3166, -121.8796),
            (37.3232, -121.8868),
            (37.3298, -121.894),
            (37.3364, -121.9012),
            (37.343, -121.9084),
            (37.3496, -121.9156),
            (37.3562, -121.9228),
        ],
    },
    {
        'name': 'SJC 30R final approach',
        'airport': 'SJC',
        'kind': 'final',
        'runway': '30R',
        'coords': [
            (37.2385, -121.7915),
            (37.2451, -121.7987),
            (37.2517, -121.8059),
            (37.2584, -121.8131),
            (37.265, -121.8203),
            (37.2716, -121.8275),
            (37.2782, -121.8347),
            (37.2848, -121.8418),
            (37.2914, -121.849),
            (37.298, -121.8562),
            (37.3046, -121.8634),
            (37.3112, -121.8706),
            (37.3178, -121.8778),
            (37.3245, -121.885),
            (37.3311, -121.8922),
            (37.3377, -121.8994),
            (37.3443, -121.9066),
            (37.3509, -121.9138),
            (37.3575, -121.921),
        ],
    },
    {
        'name': 'SFO departure via GAPP7',
        'airport': 'SFO',
        'kind': 'departure',
        'runway': '28L',
        'coords': [
            (37.6121, -122.3593),
            (37.6163, -122.369),
            (37.6204, -122.3788),
            (37.6246, -122.3886),
            (37.6287, -122.3983),
            (37.6329, -122.4081),
            (37.637, -122.4179),
            (37.6412, -122.4276),
            (37.6454, -122.4374),
            (37.6495, -122.4472),
            (37.6537, -122.4569),
            (37.6578, -122.4667),
            (37.662, -122.4765),
            (37.6662, -122.4862),
            (37.6703, -122.496),
            (37.6745, -122.5057),
            (37.6786, -122.5155),
            (37.6828, -122.5253),
            (37.6869, -122.535),
            (37.6911, -122.5448),
            (37.6953, -122.5546),
            (37.6994, -122.5643),
            (37.7036, -122.5741),
            (37.7077, -122.5839),
            (37.7119, -122.5936),
            (37.716, -122.6034),
            (37.7202, -122.6132),
        ],
    },
    {
        'name': 'SFO departure via GNNRR3',
        'airport': 'SFO',
        'kind': 'departure',
        'runway': '28L',
        'coords': [
            (37.6121, -122.3593),
            (37.6163, -122.3689),
            (37.6204, -122.3785),
            (37.6246, -122.3881),
            (37.6288, -122.3977),
            (37.633, -122.4073),
            (37.6372, -122.4169),
            (37.6413, -122.4265),
            (37.6455, -122.4361),
            (37.6497, -122.4457),
            (37.6539, -122.4553),
            (37.658, -122.465),
            (37.6622, -122.4746),
            (37.6664, -122.4842),
            (37.6706, -122.4938),
            (37.6747, -122.5034),
        ],
    },
    {
        'name': 'SFO departure via MOLEN9',
        'airport': 'SFO',
        'kind': 'departure',
        'runway': '28L',
        'coords': [
            (37.6121, -122.3593),
            (37.6161, -122.3686),
            (37.6201, -122.3779),
            (37.6242, -122.3872),
            (37.6282, -122.3965),
            (37.6322, -122.4058),
            (37.6362, -122.4151),
            (37.6402, -122.4244),
            (37.6443, -122.4337),
            (37.6483, -122.4431),
            (37.6523, -122.4524),
            (37.6563, -122.4617),
            (37.6604, -122.471),
            (37.6644, -122.4803),
            (37.6695, -122.4895),
            (37.6745, -122.4988),
            (37.6796, -122.508),
            (37.6847, -122.5173),
            (37.6898, -122.5265),
            (37.6949, -122.5358),
            (37.7, -122.545),
            (37.7051, -122.5543),
            (37.7101, -122.5635),
            (37.7152, -122.5728),
            (37.7203, -122.582),
            (37.7254, -122.5913),
            (37.7305, -122.6005),
            (37.7356, -122.6098),
            (37.7406, -122.619),
            (37.7457, -122.6283),
            (37.7508, -122.6375),
            (37.7559, -122.6468),
        ],
    },
    {
        'name': 'SFO departure via NIITE4',
        'airport': 'SFO',
        'kind': 'departure',
        'runway': '01L',
        'coords': [
            (37.6095, -122.3819),
            (37.6163, -122.3748),
            (37.6231, -122.3677),
            (37.63, -122.3605),
            (37.6368, -122.3534),
            (37.6437, -122.3463),
            (37.6505, -122.3392),
            (37.6574, -122.3321),
            (37.6642, -122.325),
            (37.6711, -122.3178),
            (37.6779, -122.3107),
            (37.6848, -122.3036),
            (37.6929, -122.308),
            (37.701, -122.3124),
            (37.709, -122.3167),
            (37.7171, -122.3211),
            (37.7252, -122.3255),
            (37.7333, -122.3298),
            (37.7414, -122.3342),
            (37.7495, -122.3386),
            (37.7575, -122.3426),
            (37.7654, -122.3466),
            (37.7734, -122.3506),
            (37.7813, -122.3546),
            (37.7893, -122.3586),
            (37.7972, -122.3627),
            (37.8052, -122.3667),
            (37.8131, -122.3707),
            (37.8211, -122.3747),
            (37.8291, -122.3787),
            (37.837, -122.3827),
            (37.845, -122.3867),
        ],
    },
    {
        'name': 'SFO departure via SEGUL1',
        'airport': 'SFO',
        'kind': 'departure',
        'runway': '01L',
        'coords': [
            (37.6095, -122.3819),
            (37.6175, -122.3785),
            (37.6256, -122.375),
            (37.6337, -122.3716),
            (37.6417, -122.3681),
            (37.6498, -122.3647),
            (37.6579, -122.3613),
            (37.6659, -122.3578),
            (37.674, -122.3544),
            (37.6821, -122.351),
            (37.6783, -122.361),
            (37.6745, -122.371),
            (37.6707, -122.381),
            (37.6669, -122.391),
            (37.6631, -122.401),
            (37.6594, -122.411),
            (37.6556, -122.421),
            (37.6518, -122.431),
            (37.648, -122.4411),
            (37.6442, -122.4511),
            (37.6404, -122.4611),
            (37.6367, -122.4711),
            (37.6329, -122.4811),
            (37.6291, -122.4911),
            (37.6253, -122.5011),
            (37.6215, -122.5111),
            (37.6177, -122.5211),
            (37.614, -122.5312),
            (37.6102, -122.5412),
            (37.6064, -122.5512),
            (37.6026, -122.5612),
            (37.5988, -122.5712),
        ],
    },
    {
        'name': 'SFO departure via SEGUL1',
        'airport': 'SFO',
        'kind': 'departure',
        'runway': '28L',
        'coords': [
            (37.6121, -122.3593),
            (37.6163, -122.3689),
            (37.6205, -122.3786),
            (37.6247, -122.3883),
            (37.6288, -122.398),
            (37.633, -122.4077),
            (37.6372, -122.4174),
            (37.6414, -122.4271),
            (37.6456, -122.4367),
            (37.6498, -122.4464),
            (37.6539, -122.4561),
            (37.6581, -122.4658),
            (37.6623, -122.4755),
            (37.6665, -122.4852),
            (37.6617, -122.4943),
            (37.6569, -122.5034),
            (37.6521, -122.5125),
            (37.6473, -122.5217),
            (37.6425, -122.5308),
            (37.6378, -122.5399),
            (37.633, -122.549),
            (37.6282, -122.5582),
            (37.6234, -122.5673),
            (37.6186, -122.5764),
            (37.6138, -122.5855),
            (37.609, -122.5947),
            (37.6042, -122.6038),
            (37.5994, -122.6129),
            (37.5946, -122.622),
            (37.5898, -122.6311),
            (37.5851, -122.6403),
            (37.5803, -122.6494),
        ],
    },
    {
        'name': 'SFO departure via SNTNA2',
        'airport': 'SFO',
        'kind': 'departure',
        'runway': '28L',
        'coords': [
            (37.6121, -122.3593),
            (37.6162, -122.3689),
            (37.6204, -122.3786),
            (37.6245, -122.3883),
            (37.6287, -122.398),
            (37.6328, -122.4076),
            (37.637, -122.4173),
            (37.6411, -122.427),
            (37.6453, -122.4367),
            (37.6494, -122.4463),
            (37.6536, -122.456),
            (37.6577, -122.4657),
            (37.6619, -122.4754),
            (37.666, -122.485),
            (37.6702, -122.4947),
            (37.6743, -122.5044),
            (37.6785, -122.5141),
            (37.6826, -122.5238),
            (37.6913, -122.5241),
            (37.7, -122.5244),
            (37.7087, -122.5248),
            (37.7174, -122.5251),
            (37.7261, -122.5254),
            (37.7348, -122.5258),
            (37.7435, -122.5261),
            (37.7523, -122.5264),
            (37.761, -122.5268),
            (37.7697, -122.5271),
            (37.7784, -122.5274),
            (37.7871, -122.5278),
            (37.7958, -122.5281),
            (37.8045, -122.5285),
            (37.8046, -122.5281),
        ],
    },
    {
        'name': 'SFO departure via SSTIK5',
        'airport': 'SFO',
        'kind': 'departure',
        'runway': '01L',
        'coords': [
            (37.6095, -122.3819),
            (37.6181, -122.3794),
            (37.6267, -122.3768),
            (37.6353, -122.3743),
            (37.6439, -122.3718),
            (37.6525, -122.3692),
            (37.6611, -122.3667),
            (37.6697, -122.3642),
            (37.6783, -122.3617),
            (37.6705, -122.3664),
            (37.6626, -122.3711),
            (37.6547, -122.3758),
            (37.6469, -122.3805),
            (37.639, -122.3852),
            (37.6311, -122.3899),
            (37.6233, -122.3946),
            (37.6154, -122.3993),
            (37.6075, -122.4041),
            (37.5997, -122.4088),
            (37.5918, -122.4135),
            (37.584, -122.4182),
            (37.5761, -122.4229),
            (37.5682, -122.4276),
            (37.5604, -122.4323),
            (37.5525, -122.437),
            (37.5446, -122.4417),
            (37.5368, -122.4464),
            (37.5289, -122.4512),
            (37.521, -122.4559),
            (37.5132, -122.4606),
            (37.5053, -122.4653),
            (37.4974, -122.47),
        ],
    },
    {
        'name': 'SFO departure via TRUKN2',
        'airport': 'SFO',
        'kind': 'departure',
        'runway': '01L',
        'coords': [
            (37.6095, -122.3819),
            (37.6152, -122.3738),
            (37.6209, -122.3658),
            (37.6266, -122.3577),
            (37.6323, -122.3496),
            (37.638, -122.3416),
            (37.6437, -122.3335),
            (37.6494, -122.3254),
            (37.6551, -122.3174),
            (37.6608, -122.3093),
            (37.6665, -122.3012),
            (37.6722, -122.2931),
            (37.6779, -122.2851),
            (37.6836, -122.277),
            (37.6893, -122.2689),
            (37.694, -122.2599),
            (37.6987, -122.2508),
            (37.7034, -122.2418),
            (37.7081, -122.2327),
            (37.7129, -122.2236),
            (37.7176, -122.2146),
        ],
    },
    {
        'name': 'SFO departure via WESLA5',
        'airport': 'SFO',
        'kind': 'departure',
        'runway': '28L',
        'coords': [
            (37.6121, -122.3593),
            (37.6161, -122.3686),
            (37.6201, -122.3779),
            (37.6242, -122.3872),
            (37.6282, -122.3965),
            (37.6322, -122.4058),
            (37.6362, -122.4151),
            (37.6402, -122.4244),
            (37.6443, -122.4337),
            (37.6483, -122.4431),
            (37.6523, -122.4524),
            (37.6563, -122.4617),
            (37.6604, -122.471),
            (37.6644, -122.4803),
            (37.6554, -122.48),
            (37.6464, -122.4797),
            (37.6375, -122.4794),
            (37.6285, -122.4791),
            (37.6195, -122.4788),
            (37.6106, -122.4785),
            (37.6016, -122.4782),
            (37.5927, -122.4779),
            (37.5837, -122.4777),
            (37.5747, -122.4774),
            (37.5658, -122.4771),
            (37.5568, -122.4768),
            (37.5478, -122.4765),
            (37.5389, -122.4762),
            (37.5299, -122.4759),
            (37.5209, -122.4756),
            (37.512, -122.4753),
            (37.503, -122.475),
        ],
    },
    {
        'name': 'OAK departure via CNDEL5',
        'airport': 'OAK',
        'kind': 'departure',
        'runway': '30',
        'coords': [
            (37.7017, -122.2146),
            (37.7071, -122.2228),
            (37.7126, -122.2309),
            (37.7181, -122.2391),
            (37.7235, -122.2473),
            (37.729, -122.2555),
            (37.7344, -122.2637),
            (37.7399, -122.2719),
            (37.7453, -122.2801),
            (37.7508, -122.2883),
            (37.7562, -122.2965),
            (37.7617, -122.3047),
            (37.7671, -122.3127),
            (37.7725, -122.3207),
            (37.7779, -122.3287),
            (37.7833, -122.3368),
            (37.7753, -122.3405),
            (37.7674, -122.3442),
            (37.7595, -122.3479),
            (37.7515, -122.3517),
            (37.7436, -122.3554),
            (37.7356, -122.3591),
            (37.7277, -122.3628),
            (37.7198, -122.3666),
            (37.7118, -122.3703),
            (37.7039, -122.374),
            (37.696, -122.3778),
            (37.688, -122.3815),
            (37.6801, -122.3852),
            (37.6721, -122.3889),
            (37.6642, -122.3927),
            (37.6563, -122.3964),
            (37.6483, -122.4001),
        ],
    },
    {
        'name': 'OAK departure via HUSSH2',
        'airport': 'OAK',
        'kind': 'departure',
        'runway': '30',
        'coords': [
            (37.7017, -122.2146),
            (37.7054, -122.2241),
            (37.709, -122.2336),
            (37.7127, -122.2432),
            (37.7164, -122.2527),
            (37.7201, -122.2623),
            (37.7238, -122.2718),
            (37.7274, -122.2813),
            (37.7311, -122.2909),
            (37.7348, -122.3004),
            (37.7385, -122.31),
            (37.7421, -122.3195),
            (37.7458, -122.3291),
            (37.7495, -122.3386),
            (37.7575, -122.3426),
            (37.7655, -122.3466),
            (37.7734, -122.3507),
            (37.7814, -122.3547),
            (37.7894, -122.3587),
            (37.7974, -122.3627),
            (37.8053, -122.3668),
            (37.8133, -122.3708),
            (37.8213, -122.3748),
            (37.8293, -122.3788),
            (37.8373, -122.3828),
            (37.8452, -122.3869),
        ],
    },
    {
        'name': 'SJC departure via LOUPE1',
        'airport': 'SJC',
        'kind': 'departure',
        'runway': '30L',
        'coords': [
            (37.3562, -121.9228),
            (37.3622, -121.9294),
            (37.3682, -121.9359),
            (37.3742, -121.9425),
            (37.3801, -121.949),
            (37.3861, -121.9556),
            (37.3921, -121.9621),
            (37.3981, -121.9687),
            (37.3953, -121.9584),
            (37.3925, -121.9481),
            (37.3897, -121.9378),
            (37.3868, -121.9275),
            (37.384, -121.9172),
            (37.3812, -121.9069),
            (37.3784, -121.8966),
            (37.3756, -121.8863),
            (37.3728, -121.876),
            (37.37, -121.8657),
            (37.3672, -121.8554),
            (37.3644, -121.8451),
            (37.3616, -121.8348),
            (37.3588, -121.8246),
            (37.356, -121.8143),
            (37.3532, -121.804),
        ],
    },
    {
        'name': 'SJC departure via LOUPE1',
        'airport': 'SJC',
        'kind': 'departure',
        'runway': '30R',
        'coords': [
            (37.3575, -121.921),
            (37.3635, -121.9275),
            (37.3694, -121.9341),
            (37.3754, -121.9406),
            (37.3813, -121.9471),
            (37.3873, -121.9537),
            (37.3933, -121.9602),
            (37.3992, -121.9667),
            (37.3963, -121.9566),
            (37.3935, -121.9464),
            (37.3906, -121.9362),
            (37.3877, -121.926),
            (37.3848, -121.9159),
            (37.3819, -121.9057),
            (37.3791, -121.8955),
            (37.3762, -121.8854),
            (37.3733, -121.8752),
            (37.3704, -121.865),
            (37.3676, -121.8548),
            (37.3647, -121.8447),
            (37.3618, -121.8345),
            (37.3589, -121.8243),
            (37.356, -121.8141),
            (37.3532, -121.804),
        ],
    },
    {
        'name': 'SJC departure via SPTNS1',
        'airport': 'SJC',
        'kind': 'departure',
        'runway': '30L',
        'coords': [
            (37.3562, -121.9228),
            (37.3622, -121.9294),
            (37.3682, -121.9359),
            (37.3742, -121.9425),
            (37.3801, -121.949),
            (37.3861, -121.9556),
            (37.3921, -121.9621),
            (37.3981, -121.9687),
            (37.3942, -121.9586),
            (37.3903, -121.9485),
            (37.3863, -121.9384),
            (37.3824, -121.9283),
            (37.3785, -121.9182),
            (37.3746, -121.9081),
            (37.3707, -121.898),
            (37.3668, -121.8879),
            (37.3629, -121.8778),
            (37.359, -121.8677),
            (37.3551, -121.8576),
            (37.3512, -121.8475),
            (37.3472, -121.8374),
            (37.3433, -121.8273),
            (37.3394, -121.8172),
            (37.3355, -121.8071),
            (37.3316, -121.797),
            (37.3277, -121.7869),
            (37.3219, -121.7804),
            (37.3162, -121.7739),
            (37.3104, -121.7674),
            (37.3046, -121.7608),
            (37.2989, -121.7543),
            (37.2931, -121.7478),
            (37.2874, -121.7413),
        ],
    },
    {
        'name': 'SJC departure via SPTNS1',
        'airport': 'SJC',
        'kind': 'departure',
        'runway': '30R',
        'coords': [
            (37.3575, -121.921),
            (37.3635, -121.9275),
            (37.3694, -121.9341),
            (37.3754, -121.9406),
            (37.3813, -121.9471),
            (37.3873, -121.9537),
            (37.3933, -121.9602),
            (37.3992, -121.9667),
            (37.3952, -121.9568),
            (37.3913, -121.9468),
            (37.3873, -121.9368),
            (37.3833, -121.9268),
            (37.3793, -121.9168),
            (37.3754, -121.9068),
            (37.3714, -121.8968),
            (37.3674, -121.8868),
            (37.3635, -121.8768),
            (37.3595, -121.8668),
            (37.3555, -121.8569),
            (37.3515, -121.8469),
            (37.3476, -121.8369),
            (37.3436, -121.8269),
            (37.3396, -121.8169),
            (37.3356, -121.8069),
            (37.3317, -121.7969),
            (37.3277, -121.7869),
            (37.3218, -121.7803),
            (37.3159, -121.7736),
            (37.3101, -121.767),
            (37.3042, -121.7603),
            (37.2983, -121.7537),
            (37.2924, -121.747),
            (37.2866, -121.7404),
        ],
    },
]
BAYAREA_QUIET = {
    'runway_lobes': {
        'SFO': [
            {'bearing': 27.7, 'runway': '01L', 'kind': 'departure', 'share': 0.308},
            {'bearing': 117.91, 'runway': '28L', 'kind': 'arrival', 'share': 0.397},
            {'bearing': 297.91, 'runway': '28L', 'kind': 'departure', 'share': 0.554},
            {'bearing': 117.91, 'runway': '28R', 'kind': 'arrival', 'share': 0.599},
            {'bearing': 297.91, 'runway': '28R', 'kind': 'departure', 'share': 0.136},
        ],
        'OAK': [
            {'bearing': 344.49, 'runway': '15', 'kind': 'arrival', 'share': 0.183},
            {'bearing': 112.26, 'runway': '28R', 'kind': 'arrival', 'share': 0.213},
            {'bearing': 130.13, 'runway': '30', 'kind': 'arrival', 'share': 0.48},
            {'bearing': 310.13, 'runway': '30', 'kind': 'departure', 'share': 0.689},
            {'bearing': 344.49, 'runway': '33', 'kind': 'departure', 'share': 0.138},
        ],
        'SJC': [
            {'bearing': 138.94, 'runway': '30L', 'kind': 'arrival', 'share': 0.831},
            {'bearing': 318.94, 'runway': '30L', 'kind': 'departure', 'share': 0.267},
            {'bearing': 138.94, 'runway': '30R', 'kind': 'arrival', 'share': 0.119},
            {'bearing': 318.94, 'runway': '30R', 'kind': 'departure', 'share': 0.678},
        ],
    },
    'airport_sizes': {'SFO': 0.85, 'OAK': 0.85, 'SJC': 0.5},
    'corridor_weight': 1.25,
    'major_airports': ['SFO', 'OAK', 'SJC'],
    'runway_use_period': '2026-07-01 to 2026-08-31',
}
# US-QUIET-BAYAREA:END

# New York's aircraft geometry, fitted to the Port Authority's monitors the same way
# (Bill, 2026-10-16: the hand-drawn corridors and Heathrow-sized circles read 15 of 17 JFK
# monitors quieter than measured). The FAA's routes, runway lobes from flight-track use,
# fitted sizes and corridor weight. The hand-drawn AIRPORTS_NYC and FLIGHT_PATHS_NYC are deleted.
# US-QUIET-NYC:START (generated by scripts/measure_us_quiet_yardstick.py --write; do not hand-edit)
AIRPORTS_NYC_FITTED = [
    {'code': 'JFK', 'name': 'John F. Kennedy', 'lat': 40.639928, 'lon': -73.778692},
    {'code': 'LGA', 'name': 'LaGuardia', 'lat': 40.777242, 'lon': -73.872606},
    {'code': 'EWR', 'name': 'Newark Liberty', 'lat': 40.692481, 'lon': -74.168689},
    {'code': 'TEB', 'name': 'Teterboro', 'lat': 40.850103, 'lon': -74.060833},
]
FLIGHT_PATHS_NYC_FITTED = [
    {
        'name': 'JFK 04R final approach',
        'airport': 'JFK',
        'kind': 'final',
        'runway': '04R',
        'coords': [
            (40.4897, -73.8757),
            (40.4972, -73.8698),
            (40.5048, -73.864),
            (40.5123, -73.8581),
            (40.5199, -73.8523),
            (40.5274, -73.8464),
            (40.5349, -73.8406),
            (40.5425, -73.8347),
            (40.55, -73.8289),
            (40.5576, -73.823),
            (40.5651, -73.8172),
            (40.5726, -73.8113),
            (40.5802, -73.8055),
            (40.5877, -73.7996),
            (40.5953, -73.7938),
            (40.6028, -73.7879),
            (40.6103, -73.782),
            (40.6179, -73.7762),
            (40.6254, -73.7703),
        ],
    },
    {
        'name': 'JFK 22L final approach',
        'airport': 'JFK',
        'kind': 'final',
        'runway': '22L',
        'coords': [
            (40.7809, -73.6495),
            (40.7734, -73.6553),
            (40.7659, -73.6612),
            (40.7583, -73.667),
            (40.7508, -73.6729),
            (40.7432, -73.6787),
            (40.7357, -73.6846),
            (40.7282, -73.6904),
            (40.7206, -73.6963),
            (40.7131, -73.7022),
            (40.7056, -73.708),
            (40.698, -73.7139),
            (40.6905, -73.7197),
            (40.6829, -73.7256),
            (40.6754, -73.7314),
            (40.6679, -73.7373),
            (40.6603, -73.7431),
            (40.6528, -73.749),
            (40.6452, -73.7549),
        ],
    },
    {
        'name': 'JFK 31R final approach',
        'airport': 'JFK',
        'kind': 'final',
        'runway': '31R',
        'coords': [
            (40.5642, -73.5851),
            (40.5687, -73.595),
            (40.5732, -73.6048),
            (40.5777, -73.6147),
            (40.5822, -73.6245),
            (40.5867, -73.6344),
            (40.5912, -73.6442),
            (40.5957, -73.6541),
            (40.6002, -73.664),
            (40.6047, -73.6738),
            (40.6092, -73.6837),
            (40.6137, -73.6935),
            (40.6182, -73.7034),
            (40.6227, -73.7132),
            (40.6272, -73.7231),
            (40.6317, -73.7329),
            (40.6362, -73.7428),
            (40.6407, -73.7526),
            (40.6452, -73.7625),
        ],
    },
    {
        'name': 'LGA 04 final approach',
        'airport': 'LGA',
        'kind': 'final',
        'runway': '04',
        'coords': [
            (40.6414, -73.989),
            (40.6489, -73.9828),
            (40.6564, -73.9766),
            (40.6639, -73.9705),
            (40.6714, -73.9643),
            (40.679, -73.9581),
            (40.6865, -73.952),
            (40.694, -73.9458),
            (40.7015, -73.9396),
            (40.709, -73.9335),
            (40.7165, -73.9273),
            (40.7241, -73.9211),
            (40.7316, -73.915),
            (40.7391, -73.9088),
            (40.7466, -73.9026),
            (40.7541, -73.8965),
            (40.7616, -73.8903),
            (40.7692, -73.8841),
        ],
    },
    {
        'name': 'LGA 22 final approach',
        'airport': 'LGA',
        'kind': 'final',
        'runway': '22',
        'coords': [
            (40.9192, -73.7609),
            (40.9118, -73.767),
            (40.9043, -73.7731),
            (40.8969, -73.7792),
            (40.8895, -73.7853),
            (40.882, -73.7914),
            (40.8746, -73.7975),
            (40.8672, -73.8036),
            (40.8597, -73.8097),
            (40.8523, -73.8158),
            (40.8449, -73.8219),
            (40.8375, -73.828),
            (40.83, -73.8341),
            (40.8226, -73.8402),
            (40.8152, -73.8463),
            (40.8077, -73.8524),
            (40.8003, -73.8585),
            (40.7929, -73.8646),
            (40.7854, -73.8707),
        ],
    },
    {
        'name': 'EWR 04R final approach',
        'airport': 'EWR',
        'kind': 'final',
        'runway': '04R',
        'coords': [
            (40.536, -74.2637),
            (40.544, -74.2586),
            (40.552, -74.2535),
            (40.5601, -74.2484),
            (40.5681, -74.2434),
            (40.5761, -74.2383),
            (40.5842, -74.2332),
            (40.5922, -74.2282),
            (40.6002, -74.2231),
            (40.6083, -74.218),
            (40.6163, -74.2129),
            (40.6243, -74.2079),
            (40.6323, -74.2028),
            (40.6404, -74.1977),
            (40.6484, -74.1927),
            (40.6564, -74.1876),
            (40.6645, -74.1825),
            (40.6725, -74.1774),
            (40.6805, -74.1724),
        ],
    },
    {
        'name': 'EWR 22L final approach',
        'airport': 'EWR',
        'kind': 'final',
        'runway': '22L',
        'coords': [
            (40.84, -74.0716),
            (40.8321, -74.0766),
            (40.8242, -74.0816),
            (40.8163, -74.0865),
            (40.8084, -74.0915),
            (40.8005, -74.0965),
            (40.7926, -74.1015),
            (40.7847, -74.1065),
            (40.7768, -74.1115),
            (40.7689, -74.1165),
            (40.761, -74.1215),
            (40.7531, -74.1264),
            (40.7452, -74.1314),
            (40.7373, -74.1364),
            (40.7294, -74.1414),
            (40.7215, -74.1464),
            (40.7136, -74.1514),
            (40.7058, -74.1564),
            (40.6979, -74.1614),
        ],
    },
    {
        'name': 'TEB 06 final approach',
        'airport': 'TEB',
        'kind': 'final',
        'runway': '06',
        'coords': [
            (40.7412, -74.2244),
            (40.7471, -74.2158),
            (40.753, -74.2073),
            (40.7588, -74.1987),
            (40.7647, -74.1901),
            (40.7705, -74.1816),
            (40.7764, -74.173),
            (40.7823, -74.1645),
            (40.7881, -74.1559),
            (40.794, -74.1473),
            (40.7998, -74.1388),
            (40.8057, -74.1302),
            (40.8116, -74.1217),
            (40.8174, -74.1131),
            (40.8233, -74.1045),
            (40.8291, -74.096),
            (40.835, -74.0874),
            (40.8409, -74.0789),
            (40.8467, -74.0703),
        ],
    },
    {
        'name': 'TEB 19 final approach',
        'airport': 'TEB',
        'kind': 'final',
        'runway': '19',
        'coords': [
            (41.0133, -74.0476),
            (41.0046, -74.0482),
            (40.9958, -74.0489),
            (40.987, -74.0495),
            (40.9783, -74.0501),
            (40.9695, -74.0508),
            (40.9608, -74.0514),
            (40.952, -74.0521),
            (40.9433, -74.0527),
            (40.9345, -74.0533),
            (40.9258, -74.054),
            (40.917, -74.0546),
            (40.9083, -74.0553),
            (40.8995, -74.0559),
            (40.8908, -74.0565),
            (40.882, -74.0572),
            (40.8733, -74.0578),
            (40.8645, -74.0585),
            (40.8558, -74.0591),
        ],
    },
    {
        'name': 'TEB 24 final approach',
        'airport': 'TEB',
        'kind': 'final',
        'runway': '24',
        'coords': [
            (40.9566, -73.9096),
            (40.9508, -73.9181),
            (40.945, -73.9266),
            (40.9392, -73.9351),
            (40.9333, -73.9436),
            (40.9275, -73.9521),
            (40.9217, -73.9606),
            (40.9159, -73.9691),
            (40.9101, -73.9776),
            (40.9043, -73.9861),
            (40.8984, -73.9946),
            (40.8926, -74.0031),
            (40.8868, -74.0116),
            (40.881, -74.0201),
            (40.8752, -74.0286),
            (40.8694, -74.0371),
            (40.8636, -74.0456),
            (40.8577, -74.0541),
        ],
    },
    {
        'name': 'JFK departure via DEEZZ6',
        'airport': 'JFK',
        'kind': 'departure',
        'runway': '04L',
        'coords': [
            (40.6231, -73.7847),
            (40.6301, -73.7793),
            (40.6371, -73.7738),
            (40.6442, -73.7683),
            (40.6512, -73.7628),
            (40.6582, -73.7573),
            (40.6652, -73.7518),
            (40.6722, -73.7464),
        ],
    },
    {
        'name': 'LGA departure via GLDMN8',
        'airport': 'LGA',
        'kind': 'departure',
        'runway': '13',
        'coords': [
            (40.7823, -73.8785),
            (40.7746, -73.8727),
            (40.7668, -73.8668),
            (40.7591, -73.861),
            (40.7514, -73.8551),
            (40.7437, -73.8493),
            (40.736, -73.8434),
            (40.7282, -73.8376),
            (40.7205, -73.8317),
            (40.7128, -73.8259),
            (40.7073, -73.8343),
            (40.7018, -73.8426),
            (40.6963, -73.851),
            (40.6908, -73.8594),
            (40.6852, -73.8677),
            (40.6797, -73.8761),
            (40.6742, -73.8844),
            (40.6687, -73.8928),
            (40.6731, -73.9025),
            (40.6774, -73.9121),
            (40.6817, -73.9218),
            (40.6861, -73.9314),
            (40.6904, -73.941),
            (40.6948, -73.9507),
            (40.6991, -73.9603),
            (40.7035, -73.97),
        ],
    },
    {
        'name': 'LGA departure via NTHNS6',
        'airport': 'LGA',
        'kind': 'departure',
        'runway': '13',
        'coords': [
            (40.7823, -73.8785),
            (40.7746, -73.8727),
            (40.7668, -73.8668),
            (40.7591, -73.861),
            (40.7514, -73.8551),
            (40.7437, -73.8493),
            (40.736, -73.8434),
            (40.7282, -73.8376),
            (40.7205, -73.8317),
            (40.7128, -73.8259),
            (40.7046, -73.8281),
            (40.6964, -73.8303),
            (40.6882, -73.8325),
            (40.68, -73.8347),
            (40.6717, -73.837),
            (40.6647, -73.8441),
            (40.6577, -73.8512),
            (40.6506, -73.8584),
            (40.6436, -73.8655),
            (40.6365, -73.8726),
            (40.6295, -73.8798),
            (40.6224, -73.8869),
            (40.6153, -73.8927),
            (40.6082, -73.8985),
            (40.6011, -73.9042),
            (40.594, -73.91),
            (40.5869, -73.9158),
            (40.5798, -73.9215),
            (40.5727, -73.9273),
            (40.5656, -73.9331),
            (40.5585, -73.9388),
            (40.5514, -73.9446),
        ],
    },
    {
        'name': 'EWR departure via PORTT4',
        'airport': 'EWR',
        'kind': 'departure',
        'runway': '22L',
        'coords': [
            (40.6979, -74.1614),
            (40.6894, -74.1648),
            (40.681, -74.1682),
            (40.6725, -74.1716),
            (40.6641, -74.1751),
            (40.6556, -74.1785),
            (40.6472, -74.1819),
            (40.6387, -74.1853),
            (40.6303, -74.1888),
            (40.6218, -74.1922),
            (40.6187, -74.2024),
            (40.6156, -74.2125),
            (40.6125, -74.2227),
            (40.6094, -74.2329),
            (40.6063, -74.2431),
            (40.6032, -74.2532),
            (40.6001, -74.2634),
            (40.597, -74.2736),
            (40.5939, -74.2838),
            (40.5908, -74.2939),
        ],
    },
    {
        'name': 'TEB departure via WENTZ1',
        'airport': 'TEB',
        'kind': 'departure',
        'runway': '24',
        'coords': [
            (40.8577, -74.0541),
            (40.852, -74.0626),
            (40.8462, -74.071),
            (40.8405, -74.0795),
            (40.8347, -74.0879),
            (40.829, -74.0964),
            (40.8264, -74.1059),
            (40.8238, -74.1153),
            (40.8211, -74.1248),
            (40.8185, -74.1342),
            (40.8159, -74.1437),
            (40.8133, -74.1531),
            (40.8135, -74.1645),
            (40.8137, -74.1759),
            (40.8139, -74.1872),
            (40.8141, -74.1986),
            (40.8144, -74.21),
            (40.8146, -74.2213),
            (40.8148, -74.2327),
            (40.815, -74.2441),
            (40.8152, -74.2554),
            (40.8154, -74.2668),
            (40.8156, -74.2782),
        ],
    },
]
NYC_QUIET = {
    'runway_lobes': {
        'JFK': [
            {'bearing': 30.66, 'runway': '04L', 'kind': 'departure', 'share': 0.137},
            {'bearing': 210.67, 'runway': '04R', 'kind': 'arrival', 'share': 0.152},
            {'bearing': 120.84, 'runway': '13R', 'kind': 'departure', 'share': 0.108},
            {'bearing': 30.68, 'runway': '22L', 'kind': 'arrival', 'share': 0.479},
            {'bearing': 210.67, 'runway': '22R', 'kind': 'departure', 'share': 0.536},
            {'bearing': 300.86, 'runway': '31L', 'kind': 'departure', 'share': 0.2},
            {'bearing': 120.87, 'runway': '31R', 'kind': 'arrival', 'share': 0.232},
        ],
        'LGA': [
            {'bearing': 212.03, 'runway': '04', 'kind': 'arrival', 'share': 0.206},
            {'bearing': 32.03, 'runway': '04', 'kind': 'departure', 'share': 0.182},
            {'bearing': 122.23, 'runway': '13', 'kind': 'departure', 'share': 0.682},
            {'bearing': 32.04, 'runway': '22', 'kind': 'arrival', 'share': 0.72},
            {'bearing': 302.25, 'runway': '31', 'kind': 'departure', 'share': 0.125},
        ],
        'EWR': [
            {'bearing': 205.74, 'runway': '04R', 'kind': 'arrival', 'share': 0.317},
            {'bearing': 25.74, 'runway': '04R', 'kind': 'departure', 'share': 0.271},
            {'bearing': 25.74, 'runway': '22L', 'kind': 'arrival', 'share': 0.607},
            {'bearing': 205.74, 'runway': '22L', 'kind': 'departure', 'share': 0.561},
            {'bearing': 205.74, 'runway': '22R', 'kind': 'departure', 'share': 0.103},
        ],
        'TEB': [
            {'bearing': 3.19, 'runway': '01', 'kind': 'departure', 'share': 0.306},
            {'bearing': 228.05, 'runway': '06', 'kind': 'arrival', 'share': 0.293},
            {'bearing': 3.19, 'runway': '19', 'kind': 'arrival', 'share': 0.489},
            {'bearing': 48.06, 'runway': '24', 'kind': 'arrival', 'share': 0.188},
            {'bearing': 228.06, 'runway': '24', 'kind': 'departure', 'share': 0.649},
        ],
    },
    'airport_sizes': {'JFK': 2.05, 'LGA': 1.35, 'EWR': 1.0, 'TEB': 0.3},
    'corridor_weight': 1.0,
    'major_airports': ['JFK', 'LGA', 'EWR', 'TEB'],
    'runway_use_period': '2026-01-01 to 2026-07-30',
}
# US-QUIET-NYC:END

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
    #
    # Since 2026-10-16 New York scores from the FITTED block above, like the Bay Area:
    # every airport is a major one ('major_airports'), so 'major_airport' and the old
    # 'secondary_airport' (LGA) are None.
    'nyc': {
        'airports': AIRPORTS_NYC_FITTED,
        'paths': FLIGHT_PATHS_NYC_FITTED,
        'heliports': [],
        'major_airport': None,
        'secondary_airport': None,
        **NYC_QUIET,
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
    'leicester': {
        'airports': AIRPORTS_LEICESTER,
        'paths': FLIGHT_PATHS_LEICESTER,
        'heliports': [],
        'major_airport': 'EMA',
        # East Midlands sits INSIDE North West Leicestershire, so unlike the
        # other cities here the airport is within its own cohort rather than
        # beyond it. Ladder still calibrated on Heathrow, so still pessimistic.
        'secondary_airport': None,
    },
    'teesside': {
        'airports': AIRPORTS_TEESSIDE,
        'paths': FLIGHT_PATHS_TEESSIDE,
        'heliports': [],
        'major_airport': 'MME',
        # Distance ladder calibrated on Heathrow, so it reaches further than
        # this airport does: the estimate is PESSIMISTIC. Teesside International
        # handles a fraction of Heathrow's traffic.
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
    'norwich': {
        'airports': AIRPORTS_NORWICH,
        'paths': FLIGHT_PATHS_NORWICH,
        'heliports': [],
        # Norwich International sits in Broadland, inside the cohort. It is
        # below the threshold DEFRA maps at, so the ladder is floored at the
        # smallest published Round 4 footprint exactly as Teesside's is: the
        # estimate is PESSIMISTIC.
        'major_airport': 'NWI',
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
    # Three airports, each the major airport of its own part of the region, so
    # 'major_airports' lists them and 'major_airport' is None (the site's
    # MAJOR_AIRPORT says null too). Its sizes, lobes and corridor weight come from
    # BAYAREA_QUIET, fitted to monitors; calc_postcode_quiet reads them only here.
    'bayarea': {
        'airports': AIRPORTS_BAYAREA,
        'paths': FLIGHT_PATHS_BAYAREA,
        'heliports': [],
        'major_airport': None,
        'secondary_airport': None,
        **BAYAREA_QUIET,
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

# Whether the local NSPL tier answered THIS request. Drives the `sources`
# attribution — see _postcode_source_line.
#
# PER REQUEST, NOT PER CONTAINER (audit finding I11, fixed 2026-08-22). This
# was a plain module global, set True on the first NSPL hit and never reset.
# Lambda reuses containers, so one local hit credited ONS NSPL on every later
# response from that container — including the ones postcodes.io actually
# answered. The old comment reasoned about the write race under the batch
# worker pool ("idempotent") and not about the READ, which is where the defect
# was: two threads writing True is harmless, one thread reading another's True
# is a false provenance claim.
#
# threading.local() gives each batch worker its own value, and reset_postcode_
# attribution() at the top of resolve_query() clears it per query, so a
# reused container and a 100-query batch both attribute honestly. B2B
# customers audit this array; crediting a body that did not answer is the
# same class of error as the Home Office line dropped on 2026-08-03.
_postcode_attribution = threading.local()


def local_postcode_served():
    """True if ONS NSPL served the postcode lookup for the current request."""
    return getattr(_postcode_attribution, 'served', False)


def mark_local_postcode_served():
    _postcode_attribution.served = True


def reset_postcode_attribution():
    _postcode_attribution.served = False


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


def airport_distance_km(lat, lon, ap):
    """Runway-shaped distance from an airport to a point, in kilometres (v5.5).

    With `along` and `side` the parts of the airport-to-point vector along and
    across the runway axis, this is sqrt(along^2 + (AIRPORT_SHAPE_K * side)^2):
    straight down the runway it is the plain great-circle distance, and
    directly beside it AIRPORT_SHAPE_K times that. Only the airport TERM of
    calc_postcode_quiet uses it; a displayed "nearest airport, x km" stays the
    plain distance. An airport with no axis in RUNWAY_AXIS_DEG keeps a circle.

    Mirrored by runwayShapedKm in index.html. The factor depends on the
    angle off the axis only through cos^2 and sin^2, so which end of the
    runway the bearing is measured from cannot change it.
    """
    d = haversine_km(lat, lon, ap['lat'], ap['lon'])
    axis = RUNWAY_AXIS_DEG.get(ap['code'])
    if axis is None:
        return d
    p = math.pi / 180.0
    f1, f2, dl = ap['lat'] * p, lat * p, (lon - ap['lon']) * p
    bearing = math.atan2(math.sin(dl) * math.cos(f2),
                         math.cos(f1) * math.sin(f2) - math.sin(f1) * math.cos(f2) * math.cos(dl))
    off = bearing - axis * p
    return d * math.sqrt(math.cos(off) ** 2 + (AIRPORT_SHAPE_K * math.sin(off)) ** 2)


def runway_lobe_km(lat, lon, ap, lobes):
    """Distance to the nearest FLOWN runway lobe, in kilometres (US, 2026-10-16).

    A lobe is a half-line from the airport along which aircraft are low: the
    approach side of a runway end that is landed on, or the climb-out side of
    one that is taken off from. Only lobes with a real share of the airport's
    movements are passed in (scripts/measure_us_quiet_yardstick.py keeps those
    at 10% or more, counted from flight tracks), because a published runway is
    not a busy one: SFO's 01/19 line runs over Millbrae, where monitors measure
    42 dB, and is almost never landed on.

    On a lobe's side the distance is runway-shaped exactly as airport_distance_km
    shapes it, sqrt(along^2 + (AIRPORT_SHAPE_K * side)^2); behind it, the point
    is off the strip and reads AIRPORT_SHAPE_K times its distance. Since v5.7 a
    lobe runs RUNWAY_LOBE_KM straight out and no further: past its end the
    distance along it counts AIRPORT_SHAPE_K times over, as it does across the
    strip, so the reading is continuous at the end (no ring on the map). An
    airport with no lobes keeps a circle. Used only where a city's geometry
    carries 'runway_lobes' (the Bay Area and, since 2026-10-16, New York); no
    UK city does, so no UK quiet value can move.
    """
    d = haversine_km(lat, lon, ap['lat'], ap['lon'])
    if not lobes:
        return d
    p = math.pi / 180.0
    f1, f2, dl = ap['lat'] * p, lat * p, (lon - ap['lon']) * p
    bearing = math.atan2(math.sin(dl) * math.cos(f2),
                         math.cos(f1) * math.sin(f2) - math.sin(f1) * math.cos(f2) * math.cos(dl))
    best = math.inf
    for lobe in lobes:
        off = bearing - lobe['bearing'] * p
        along, side = d * math.cos(off), d * math.sin(off)
        if along > RUNWAY_LOBE_KM:
            along = RUNWAY_LOBE_KM + AIRPORT_SHAPE_K * (along - RUNWAY_LOBE_KM)
        km = AIRPORT_SHAPE_K * d if along < 0 else math.hypot(along, AIRPORT_SHAPE_K * side)
        best = min(best, km)
    return best


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

# CEILING ADDED 2026-08-12. The guard below described itself as "a range, not a
# value" while implementing only a floor, and the two sentinels in play have
# OPPOSITE SIGNS: the London region export declares nodata as +3.4e38, every
# per-airport coverage as -3.4e38. So the floor catches the per-airport form and
# lets the London form through, where lden_db_to_quiet scores it 0.0 - a whole
# area reading maximally LOUD off a cell that holds no measurement at all. Same
# defect as the 35.0 fill, mirrored: absence rendered as a measurement, only in
# the pessimistic direction rather than the favourable one.
#
# 120 dB is chosen to be unreachable by any real Lden while catching every
# sentinel: the loudest cell across all 13 rasters on disk is 88.9 dB.
_RASTER_MAX_PLAUSIBLE_DB = 120.0


def _plausible_value(value, floor, ceiling, log_tag, key, postcode_clean='', known_fill=None):
    """THE range check for every raster-derived number, scalar form.

    Extracted 2026-08-27, and it is the FIFTH copy of this eight-line check to
    be folded in. `_plausible_from_row` below already called itself "ONE holder,
    four callers" and was telling the truth about the four ROW-based fields -
    but the tail of `_lookup_lden_raster`, which reads the same table for the
    same quantity, kept its own inline copy the whole time, and its own
    docstring said so ("Mirrors the tail of _lookup_lden_raster, which still
    exists"). A holder that names its callers can still be missing one; count
    the copies, not the callers.

    This is the copy that would have drifted next: it is the only one reached by
    `calc_postcode_quiet`'s sentinel-driven path, so a future ceiling change
    made in the row helper alone would leave the postcode tier reading a
    sentinel as decibels - which is exactly the 2026-08-21 road-Lden defect,
    one tier further down.

    Returns the value unchanged when it is inside [floor, ceiling], else None.
    `known_fill` names a sentinel expected at volume so it does not spam the
    alarm channel; anything else out of range warns, because an unexpected
    sentinel is a data problem a human should see.
    """
    if value is None:
        return None
    if value < floor or value > ceiling:
        if value != known_fill:
            logger.warning(
                '[%s] postcode=%s err=implausible-%s value=%s',
                log_tag, _log_district(postcode_clean), key, value)
        return None
    return value


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
        logger.warning('[SCORE_RASTER_DEGRADED] postcode=%s err=no-ddb-client', _log_district(postcode_clean))
        return None

    try:
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        logger.warning('[SCORE_RASTER_DEGRADED] postcode=%s err=botocore-import-failed', _log_district(postcode_clean))
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
        logger.warning('[SCORE_RASTER_DEGRADED] postcode=%s err=%r', _log_district(postcode_clean), exc)
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
    value = _plausible_value(
        value, _RASTER_MIN_PLAUSIBLE_DB, _RASTER_MAX_PLAUSIBLE_DB,
        'SCORE_RASTER_DEGRADED', 'lden', postcode_clean,
        known_fill=_RASTER_NODATA_FILL)
    if value is None:
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
#
# LONDON-ONLY UNTIL 2026-09-10. The per-postcode pass had been run against the
# London mosaic alone, so M2 4NG answered None with "not measured, or still
# being loaded" while SW11 answered 69.1 dB - though all eleven city mosaics had
# been on disk since August. Measured before loading
# (scripts/probe_road_raster_coverage.py): 100% of live postcodes in every
# English city are inside their mosaic and surveyed.
#
# THE SURVEYED-QUIET STATE, `roadLdenBelowDb`. DEFRA's road mosaic carries a 0
# for ground it SURVEYED and found under its lowest mapped band - 40.00 dB in
# every city, measured - and the loader used to drop those with the sentinels,
# so 2.0% of covered postcodes (11,281, every one of them quiet) told their
# reader the noise had "not been measured". Audit I3 on the borough SHARE, one
# tier down. The loader now writes the bound under its own attribute, and it is
# published here as `roadNoiseBelowDb`, never as a decibel reading: nobody
# measured 40 dB there, they measured "less than". The range on the reader is a
# guard on the BOUND (a re-fetched mosaic with a 45 dB floor would publish
# "under 45"), not a plausibility band for a level.
_ROAD_MIN_PLAUSIBLE_DB = 40.0
_ROAD_BELOW_MIN_DB = 30.0
_ROAD_BELOW_MAX_DB = 60.0




def _lookup_noise_row(postcode_clean):
    """One GetItem returning every noise metric on this postcode's row.

    ONE ROUND-TRIP, SHARED. Aircraft and road Lden live on the same row, and
    IndependentReviewRegressionTests holds the line at one GetItem per score
    (two for ?compare=previous) because duplicate lookups once pushed a
    ?compare=previous request past the 28s Lambda timeout into a 502. Fetching
    road separately doubled the count and that test caught it immediately, which
    is why this exists rather than two independent readers.

    Returns {'lden', 'roadLden', 'roadLdenBelow', 'no2', 'pm25'}, each float|None, or None if the table
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
            ProjectionExpression='ldenDb, roadLdenDb, roadLdenBelowDb, no2Ugm3, pm25Ugm3',
        )
    except (BotoCoreError, ClientError) as exc:
        logger.warning('[SCORE_RASTER_DEGRADED] postcode=%s err=%r', _log_district(postcode_clean), exc)
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
        # Surveyed-quiet bound, written by the road loader for DEFRA's zero
        # cells (2026-09-10). A row carries roadLden OR roadLdenBelow, never
        # both; see road_below_from_row.
        'roadLdenBelow': _num('roadLdenBelowDb'),
        'no2': _num('no2Ugm3'),
        'pm25': _num('pm25Ugm3'),
    }


# Air-quality plausibility range, in ug/m3 - NOT dB, so the noise bounds above
# cannot be reused. Measured off the 2022 PCM grids on 2026-08-24 (254,905
# cells each): NO2 spans 0.42-36.33, PM2.5 1.72-13.55. The floor stays at 0.0
# rather than the measured minima because concentrations improve year on year
# and a cleaner future vintage must not be swallowed by a floor read off one
# year; a negative concentration is physically impossible and is the shape the
# -3.4e38 sentinel takes. 200 is unreachable by any plausible annual mean -
# the worst city annual means on record sit near 110 ug/m3 (PM2.5, Delhi) and
# below 100 (NO2, kerbside) - while catching every sentinel in play
# (+/-3.4e38, +/-9999).
_AQ_MIN_PLAUSIBLE_UGM3 = 0.0
_AQ_MAX_PLAUSIBLE_UGM3 = 200.0


def _plausible_from_row(row, key, floor, ceiling, log_tag, postcode_clean='', known_fill=None):
    """Row-shaped wrapper over _plausible_value: extract `key`, then range-check.

    Four callers - aircraft Lden, road Lden, NO2, PM2.5 - because this check
    drifted as mirrored copies three times: lden_from_row gained its ceiling on
    2026-08-12, road_lden_from_row not until 2026-08-21, and the air-quality
    pair on the same row kept a floor-only `>= 0` until 2026-08-24, so +3.4e38
    was publishable as an annual-mean concentration. A fifth field on this row
    must call this, never copy it.

    **This docstring used to open "ONE holder, four callers" and that was not
    true of the CHECK, only of the row-reading half.** The tail of
    `_lookup_lden_raster` held a fifth inline copy from before this function
    existed until 2026-08-27; the range logic now lives in `_plausible_value`
    and both reach it. `known_fill` and the alarm behaviour are documented
    there.
    """
    return _plausible_value(
        (row or {}).get(key), floor, ceiling, log_tag, key,
        postcode_clean, known_fill=known_fill)


def lden_from_row(row, postcode_clean=''):
    """Aircraft Lden off a pre-fetched row, range-guarded.

    Mirrors the tail of _lookup_lden_raster, which still exists for
    calc_postcode_quiet's own sentinel-driven path. Rows written before
    2026-08-03 carry a literal 35.0 wherever the raster had no data, and 89.5%
    of London holds that value — treating it as a reading is what made every
    uncovered postcode look like a successful hit.
    """
    return _plausible_from_row(
        row, 'lden', _RASTER_MIN_PLAUSIBLE_DB, _RASTER_MAX_PLAUSIBLE_DB,
        'SCORE_RASTER_DEGRADED', postcode_clean, known_fill=_RASTER_NODATA_FILL)


def road_lden_from_row(row, postcode_clean=''):
    """Road Lden off a pre-fetched row, range-guarded.

    A RANGE, both ends, and the word is load-bearing. This was a floor alone
    until 2026-08-21 while its mirror lden_from_row - eleven lines above, same
    row, same table - had gained a ceiling on 2026-08-12. Two functions written
    as an explicit pair, and only one was corrected.

    The ceiling is not hypothetical. GeoTIFF nodata here is +/-3.4e38 and the
    two sentinels have OPPOSITE SIGNS depending on the coverage: the London
    region export declares +3.4e38, every per-airport coverage -3.4e38. A floor
    catches the negative one and passes the positive one straight through, so
    `roadNoiseLdenDb: 3.4e+38` was publishable on an unauthenticated endpoint.
    """
    return _plausible_from_row(
        row, 'roadLden', _ROAD_MIN_PLAUSIBLE_DB, _RASTER_MAX_PLAUSIBLE_DB,
        'SCORE_ROAD_DEGRADED', postcode_clean)


def road_below_from_row(row, postcode_clean=''):
    """The surveyed-quiet BOUND off a pre-fetched row, or None.

    Read only when road_lden_from_row gave nothing - a row holds one or the
    other. The value is the level the postcode is UNDER (40.0 today), so it is
    published as roadNoiseBelowDb and must never be handed to anything that
    wants a reading. Same range machinery as its siblings, because a sentinel
    in this column is as publishable as one in any other.
    """
    return _plausible_from_row(
        row, 'roadLdenBelow', _ROAD_BELOW_MIN_DB, _ROAD_BELOW_MAX_DB,
        'SCORE_ROAD_DEGRADED', postcode_clean)


def no2_from_row(row, postcode_clean=''):
    """NO2 annual mean off a pre-fetched row, range-guarded (see the guard)."""
    return _plausible_from_row(
        row, 'no2', _AQ_MIN_PLAUSIBLE_UGM3, _AQ_MAX_PLAUSIBLE_UGM3,
        'SCORE_AQ_DEGRADED', postcode_clean)


def pm25_from_row(row, postcode_clean=''):
    """PM2.5 annual mean off a pre-fetched row, range-guarded (see the guard)."""
    return _plausible_from_row(
        row, 'pm25', _AQ_MIN_PLAUSIBLE_UGM3, _AQ_MAX_PLAUSIBLE_UGM3,
        'SCORE_AQ_DEGRADED', postcode_clean)


def _quiet_across_all_geometry(lat, lon, postcode_clean=None):
    """Loudest quiet score any UK city's geometry gives for a point, or None.

    For coordinates outside every city we score - 68% of live UK postcodes,
    measured against NSPL 2026-02 - where naming one city would be a guess.

    LOUDEST, i.e. the MINIMUM quiet, not the nearest city's. Distance gating
    does the work: a Cornish postcode is beyond every ramp of every airport
    here, so each city returns 10.0 and the minimum is 10.0 - which is the
    right answer, not a fallback. A postcode in Cheshire is inside Manchester's
    ramps and outside everyone else's, so Manchester's reading wins on its own
    merits. Taking a maximum instead, or picking the geographically nearest
    city, both re-open the exact failure this replaced: silence about the
    airport overhead.

    UK cities only, chosen by country rather than by excluding US cities by
    name: New York was excluded by name, and the Bay Area's geometry (added
    2026-10-16, in no CITIES entry) then slipped into this loop unnoticed (audit
    2026-10-16). Both are thousands of km away and would always return 10.0, but
    including them would mean this quietly depended on that staying true.
    """
    readings = [
        calc_postcode_quiet(lat, lon, city, postcode_clean, raster_lden=None)
        for city in CITY_GEOMETRY
        if city in CITIES and CITIES[city]['country'] == 'United Kingdom'
    ]
    readings = [r for r in readings if r is not None]
    return min(readings) if readings else None


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

    # Every distance below is divided by that airport's AIRPORT_NOISE_SCALE
    # before being laddered - the ramps are Heathrow-calibrated, so an
    # "effective km" is how far this would be from Heathrow for the same
    # exposure. v3.8; before it, all four ramps ran on raw kilometres and every
    # airport was implicitly Heathrow-sized.
    #
    # The near field survives scaling here in a way it did NOT at borough level,
    # and the reason is resolution: a borough is one centroid, so dividing by
    # 0.19 could push a borough containing an airport out of the top band
    # entirely, which is why that path needed a floor. A postcode carries a real
    # distance, so a point 500 m from the Teesside runway is still 2.6 effective
    # km and still scores the maximum. No floor is needed and none is applied.
    #
    # Since v5.5 the distance is RUNWAY-SHAPED (airport_distance_km): a
    # kilometre across the runway axis counts AIRPORT_SHAPE_K times, because
    # the noise lies in a strip along it. As a circle, this term read postcodes
    # beside a runway 3.7 points too loud. The scale divides the shaped distance
    # exactly as it divided the circular one.
    #
    # A US city's geometry carries its own fitted values (2026-10-16): per-airport
    # sizes measured against that airport's monitors, runway lobes weighted by how
    # each runway is flown, its own corridor weight and a LIST of major airports.
    # Each is read only when present, so a city without them - every UK city -
    # takes exactly the path it took before. New York carries them since v5.6. The
    # US sizes deliberately do NOT go in AIRPORT_NOISE_SCALE: that table mirrors
    # index.html for the UK; the site reads New York's from its own US_QUIET_NYC block.
    sizes = geo.get('airport_sizes', {})
    lobes = geo.get('runway_lobes')

    def scale_of(code):
        return sizes[code] if code in sizes else airport_noise_scale(code)

    def airport_km(ap):
        if lobes is not None and ap['code'] in lobes:
            return runway_lobe_km(lat, lon, ap, lobes[ap['code']])
        return airport_distance_km(lat, lon, ap)

    airport_dists = [
        (ap['code'], airport_km(ap) / scale_of(ap['code']))
        for ap in geo['airports']
    ]
    # The LOUDEST airport, not the nearest one. With per-airport scales those can
    # differ: a point 8 km from London City (42 effective km) and 20 km from
    # Heathrow (20 effective km) is a Heathrow location, and taking the nearest
    # would have scored it as neither.
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

    # 2. Distance to nearest flight path waypoint, scaled by the airport that
    #    corridor serves - an approach into London City is not an approach into
    #    Heathrow, and until v3.8 the two were worth the same overhead.
    min_path_dist = float('inf')
    for path in geo['paths']:
        path_scale = scale_of(path.get('airport'))
        for plat, plon in path['coords']:
            d = haversine_km(lat, lon, plat, plon) / path_scale
            if d < min_path_dist:
                min_path_dist = d

    if min_path_dist < 1:
        path_points = 4
    elif min_path_dist < 2:
        path_points = 3
    elif min_path_dist < 4:
        path_points = 2
    elif min_path_dist < 6:
        path_points = 1
    else:
        path_points = 0
    noise_score += geo.get('corridor_weight', CORRIDOR_WEIGHT) * path_points

    # 3. Major-airport bonus (matches consumer site)
    #
    # A city with several airports that each serve their own area (the Bay Area:
    # SFO, OAK, SJC) lists them in 'major_airports', and the bonus comes from the
    # nearest of them. The single London-shaped 'major_airport' left San Jose
    # without its near-field term and read its monitors 2.3 points too quiet.
    majors = geo.get('major_airports')
    if majors:
        major_dist = min((d for code, d in airport_dists if code in majors), default=None)
    else:
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
def _takes_city(func):
    """Does this provenance callable accept a city argument?"""
    try:
        return len(inspect.signature(func).parameters) >= 1
    except (TypeError, ValueError):  # builtins without signatures
        return False


def _takes_borough(func):
    """Does this provenance callable also accept the borough's data row?

    Same signature-driven dispatch as _takes_city, for the same reason: a
    try/except around the call would also swallow TypeErrors raised INSIDE it.
    """
    try:
        return len(inspect.signature(func).parameters) >= 2
    except (TypeError, ValueError):  # builtins without signatures
        return False


# Provenance for the liveability inputs, COMPUTED from what the city's boroughs
# actually carry rather than written down beside them.
#
# It was written down, and it went stale the moment the data improved. Eight
# cities carried the sentence "Schools, transport and healthcare: not sourced"
# and a breakdown reading "UNAVAILABLE, 1 of 4 inputs measured" while v3.6 and
# v3.7 had given every one of them transport and healthcare - so the trust
# surface was understating the product to the exact audience it exists for.
# A static claim about data is a claim that has to be remembered; this one
# cannot be wrong because it reads the data.
_LIVE_INPUT_SOURCES = {
    'p8': 'DfE Key Stage 4 Progress 8, 2023/24 Revised',
    'schools': 'curated tier (no DfE equivalent for this city)',
    'crimeRate': 'ONS Crime in England and Wales, Table C4',
    'transport': 'NaPTAN rail, metro and tram access within 800 m',
    'healthcare': 'NHS Organisation Data Service GP practices within 500 m',
    # A city carrying the US crime field names its own source in CITY_PROVENANCE[city]['liveInputs']; this is
    # the fallback a missing entry would show, true but unsourced, never a UK body.
    'crimePer1000Us': "crimes per 1,000 residents, on a US scale anchored on California's rate",
}


def _live_input_source(city, field):
    """The source of one liveability input for `city`: its own (CITY_PROVENANCE[city]['liveInputs']) where it
    names one, else the UK text above. A US city's transport is BTS's, never NaPTAN's, and saying NaPTAN
    there would be the 2026-07 defect that credited UK bodies over US data."""
    own = (CITY_PROVENANCE.get(city) or {}).get('liveInputs') or {}
    return own.get(field) or _LIVE_INPUT_SOURCES[field]


_INPUT_LABEL = {'crimeRate': 'Crime', 'transport': 'Transport access', 'flood': 'Flood risk'}


def _withheld_sentence(bd, inputs):
    """' Crime is withheld here: <the reader's reason>.' for each of the given scoring inputs this record
    withholds; '' when it withholds none of them (every UK record), so no UK sentence changes."""
    held = [(_WITHHELD_INPUT_OF[f], reason) for f, reason in ((bd or {}).get('withheld') or {}).items()
            if _WITHHELD_INPUT_OF.get(f) in inputs]
    return ''.join(f' {_INPUT_LABEL[i]} is withheld here: {r}.' for i, r in held)


def _live_inputs_present(city, bd=None):
    """Which liveability inputs are actually held.

    With a borough record, THAT borough's inputs; without one, any borough of
    `city`. The distinction is the 2026-08-24 fix: the any-borough union was
    stamped on every response, so Broxtowe - whose row carries neither
    Progress 8 nor an ONS crime rate - was credited "DfE ...; ONS Table C4"
    while the same response's context.liveResolution said 2 of 4. Ten boroughs
    (Nottingham's three districts, Leicester's seven) carried that
    contradiction. The union remains the right claim at CITY level
    (build_batch_sources, /v1/changes), which is why bd stays optional rather
    than required.
    """
    fields = ('p8', 'schools', 'crimeRate', 'crimePer1000Us', 'transport', 'healthcare')
    if bd is not None:
        present = [f for f in fields if bd.get(f) is not None]
        # Mirror live_resolution's schools slot: for an English borough the
        # retired curated band without a Progress 8 figure is DEFAULTED, not
        # measured (METHODOLOGY 4.4), so it must not be credited as an input
        # here - the two sentences travel in the same response and must agree.
        if uk_shape(city) and bd.get('p8') is None and 'schools' in present:
            present.remove('schools')
        return present
    cfg = CITIES.get(city)
    if not cfg:
        return []
    present = []
    for field in fields:
        if any(row.get(field) is not None for row in cfg['boroughs'].values()):
            present.append(field)
    return present


def _live_sources_line(city, bd=None):
    """One sentence naming the liveability inputs measured HERE - for the
    requested borough when its record is supplied, else for the city."""
    present = _live_inputs_present(city, bd)
    named = [_live_input_source(city, f) for f in present]
    # schools is one COMPONENT fed by either p8 or the curated tier, so the
    # denominator is four however many raw fields are present.
    measured = len({{'p8': 'schools', 'schools': 'schools'}.get(f, f) for f in present})
    if not named:
        return ('Liveability: no inputs sourced. Weight is redistributed, not '
                'defaulted, see sourceBreakdown.live')
    if bd is not None and measured < _LIVE_MIN_FIELDS:
        # Below the floor the component is not scored, so nothing here may read as a credit for a score
        # (code review, 2026-10-22: Woodside credited "Liveability (1 of 4 inputs)" with `live` absent). No UK
        # borough sits below the floor, so only a withheld Bay Area input reaches this.
        return (f'Liveability: NOT scored here; only {measured} of 4 inputs is held ('
                + '; '.join(named) + '), below the two-input floor')
    return (f'Liveability ({measured} of 4 inputs): ' + '; '.join(named)
            + '. Any absent input has its weight redistributed, not defaulted')


def _live_breakdown_line(city, bd=None):
    """The sourceBreakdown.live sentence, counted rather than asserted.

    TAKES `bd` SINCE 2026-08-31 (audit I27). It did not, so it counted the
    CITY-LEVEL union and credited DfE Key Stage 4 for boroughs that carry no
    Progress 8 at all - seven of Leicester's eight today. The same response
    said, in two other places, that the input was absent:

        liveResolution      : partial - 3/4 inputs measured
        sources             : Liveability (3 of 4 inputs): ONS...; NaPTAN...; NHS ODS...
        sourceBreakdown.live: 4 of 4 inputs measured. DfE Key Stage 4 Progress 8...

    This is verbatim the 2026-08-24 defect that gave `_live_inputs_present` its
    `bd` parameter. That fix reached `_live_sources_line(city, bd)` and not its
    sibling here, which takes no `bd` and is called per borough from
    resolve_query - the mirrored-code family, fourth instance in this file.

    The city-level union remains right where there is no borough in hand
    (build_batch_sources, /v1/changes), which is why `bd` is optional.
    """
    present = _live_inputs_present(city, bd)
    measured = len({{'p8': 'schools', 'schools': 'schools'}.get(f, f) for f in present})
    # Both '' for every UK city: what this city never holds (CITY_PROVENANCE[city]['liveNotHeld']) and what
    # this borough's record withholds, with the reason its reader recorded.
    not_held = (CITY_PROVENANCE.get(city) or {}).get('liveNotHeld', '')
    withheld = _withheld_sentence(bd, ('crimeRate', 'transport'))
    if measured < _LIVE_MIN_FIELDS:
        return (f'UNAVAILABLE, {measured} of 4 inputs measured, and '
                'context.liveResolution says so per response.' + not_held + withheld)
    named = '; '.join(_live_input_source(city, f) for f in present)
    return (f'{measured} of 4 inputs measured. {named}. Absent inputs have their '
            'weight redistributed across the measured ones rather than being '
            'defaulted to a mid value, and context.liveResolution reports the '
            'count per response.' + not_held + withheld)


def _growth_breakdown_line(city):
    """Growth lineage, DERIVED for every city (v5.1, 2026-09-15).

    Replaces thirteen hand-written strings, twelve of which carried the
    literal 'June 2026' - the HPI roll due this month would have left every
    one of them naming the wrong vintage, the exact defect
    SNAPSHOT_VINTAGE_LABEL was introduced to end for the sources array. And
    v5.1 changes what the line has to SAY (real terms, the deflator, the
    city it is scaled within), which in thirteen places is thirteen chances
    to drift. A derived line cannot describe a basis the engine is not using.
    """
    cfg = CITIES[city]
    if cfg.get('growthNotScored'):
        basis = (
            f"NOT scored for this city: {cfg['growthNotScored']}. The trend is "
            f"{CITY_PROVENANCE[city]['trendSource']}, nominal. Growth's weight is redistributed across the "
            'components that are scored, as for any component that cannot be published'
        )
    elif cfg['currency'] == 'GBP':
        inflation = CPIH_12M_PCT[SNAPSHOT_VINTAGE]
        basis = (
            f'HM Land Registry UK House Price Index, {SNAPSHOT_VINTAGE_LABEL} vintage, 12-month '
            f'price trend deflated by ONS CPIH ({inflation}% for {SNAPSHOT_VINTAGE_LABEL}) - REAL-terms '
            'growth since methodology v5.1, so a flat score of 5.0 means prices held their value '
            'against inflation. context.priceTrendPct is the cash trend, context.priceTrendRealPct '
            'the figure scored. Methodology v5.2 scales each tail against the real-terms fastest '
            f'riser and steepest faller across ALL {_pool_size(pool_of(city))} boroughs in the sterling '
            'pool, not this city cohort - a city-sized cohort put one borough per city on each rail '
            'every month by construction. Growth is therefore comparable BETWEEN cities; '
            'context.growthRankInCity carries the within-city standing'
        )
    else:
        own = CITY_PROVENANCE[city]
        basis = (
            f"{own['trendSource']}, NOMINAL. NOT HM Land Registry HPI, "
            'and not deflated: no US inflation series is held, and dividing dollars by a UK '
            'index would be a number nobody measured. context.growthBasis says so. '
            f"Cohort-relative among the {own['poolMembers'].format(n=_pool_size(pool_of(city)))} - "
            f"the {own['poolLabel']} pool is exactly them"
        )
    if cfg.get('hasHistory'):
        history = 'A previous vintage exists, so ?compare=previous reports real movement.'
    else:
        history = (
            'No previous vintage exists for this city, so ?compare=previous declines rather '
            'than reporting zero change.'
        )
    return f'{basis}. {history}'


def _hpi_source_line():
    """The price-source line every sterling city carries, derived from the label.

    Written out by hand in TWELVE city dicts until 2026-09-16 - the same shape
    the growth line had until v5.1 and the environment lines until audit F1,
    and the one the July roll reached first: `build_hpi_prices.py --check`
    counted 13 strings naming the June 2026 release and every one of them had
    to be found and retyped. Read at request time, so the label constant above is
    the only holder; the gate now asserts what build_sources() EMITS for each
    city rather than counting literals in this file.
    """
    return (
        f'Prices: HM Land Registry UK House Price Index, {SNAPSHOT_VINTAGE_LABEL} vintage, '
        'Open Government Licence v3.0'
    )


def _inflation_source_line(city):
    """The CPIH line, only where growth was actually deflated by it."""
    if CITIES[city]['currency'] != 'GBP':
        return None
    return (
        f'Inflation: ONS CPIH 12-month rate, all items (series L55O, dataset MM23), '
        f'{SNAPSHOT_VINTAGE_LABEL}, Open Government Licence v3.0'
    )


def _afford_breakdown_line(city, bd=None):
    """Affordability lineage, DERIVED for every city (v5.0, 2026-09-09).

    This replaced THIRTEEN hand-written strings, and the replacement is the
    point rather than a tidy-up. Every one of them existed mainly to carry the
    incomparability caveat that within-city min-max forced - *"scaled WITHIN
    this city cohort, so the numbers are not comparable across cities: the
    priciest borough in any cohort scores 0.0 whatever it costs"* - and v5.0
    makes that sentence false in thirteen places at once. Thirteen mirrored
    strings is how this repo has repeatedly shipped a claim that stopped being
    true in twelve of them; a derived line cannot say something the anchor is
    not doing.

    The bounds are read from the live pool, so a new city that shifts the
    national distribution re-describes every city's lineage by itself.
    """
    currency = CITIES[city]['currency']
    p5, p95 = national_price_bounds(city, CITIES[city]['boroughs'], pool_of(city))
    pool = _pool_size(pool_of(city))
    # The OTHER pool's size, for the sentence that contrasts the two. It was
    # the literal '94-borough' three lines under the line deriving `pool`
    # (audit M10) - right today, and the shape this docstring warns about.
    gbp_pool = _pool_size('GBP')
    unit = 'GBP' if currency == 'GBP' else 'USD'

    if currency == 'GBP':
        source = (
            f'HM Land Registry UK House Price Index, {SNAPSHOT_VINTAGE_LABEL} vintage, '
            'Open Government Licence v3.0'
        )
        scope = (
            f'Methodology v5.0 scores this on a LOG scale against the 5th-95th percentile '
            f'of borough medians across ALL {pool} boroughs in the sterling pool '
            f'({unit} {p5:,.0f} to {unit} {p95:,.0f}), not against this city cohort. '
            'Affordability is therefore comparable BETWEEN cities: a cheaper borough '
            'always scores higher than a dearer one, which within-city min-max did not '
            'deliver - it inverted 1,619 of the 4,371 cross-city borough pairs. '
            'context.priceRankInCity carries the within-city standing that scaling used '
            'to imply.'
        )
    else:
        # Every non-sterling city is its own pool (decision 2: one per US metro), so the sentence names this
        # pool's members and every OTHER pool it must not be compared with, derived rather than written: it
        # said "New York is the only city Sky Score covers outside the United Kingdom", which the Bay Area's
        # entry made false in New York's own response.
        own = CITY_PROVENANCE[city]
        others = sorted(
            CITY_PROVENANCE[name]['poolLabel'] for name, cfg in CITIES.items()
            if cfg['currency'] != 'GBP' and pool_of(name) != pool_of(city)
        )
        source = own['priceSource']
        # A p95 ON the top code is the encoding's 2,000,001, never a price (code review, 2026-10-22), so it is
        # said the way the response says the price itself: the top code, "or more".
        capped = sorted(n for n, b in CITIES[city]['boroughs'].items() if b.get('priceTopCoded'))
        top = (f'{unit} {US_PRICE_TOP_CODE:,} or more, the Census top code'
               if capped and p95 == US_PRICE_TOP_CODE + 1 else f'{unit} {p95:,.0f}')
        scope = (
            f'Methodology v5.0 scores this on a LOG scale against the 5th-95th percentile '
            f"of the {own['poolLabel']} pool ({unit} {p5:,.0f} to {top}). Stated plainly: "
            f"that pool is the {own['poolMembers'].format(n=pool)} alone, because each US metro is its own "
            f"pool - so this is a within-{own['region']} scale, and it is NOT comparable with the sterling "
            f'scores, which are anchored on a {gbp_pool}-borough national pool'
            + ''.join(f', nor with the {o} pool' for o in others)
            + '. Prices in different pools are not pooled.'
        )
        if capped:
            scope += (
                f' {len(capped)} of the {len(CITIES[city]["boroughs"])} carry the Census top code, '
                f'"{unit} {US_PRICE_TOP_CODE:,} or more", and are scored on that floor: it is the pool\'s 95th '
                'percentile, so they score 0.0, the least affordable end, whatever their true price, and '
                'context.priceTopCoded says which.'
            )
    return f'{source}. {scope}'


CITY_PROVENANCE = {
    'london': {
        'sources': [
            # These two replaced 'EPC data: MHCLG' and 'Sold prices: HM Land
            # Registry' on 2026-08-25: those datasets back /epc and
            # /sold-prices, not this response, while NaPTAN and NHS ODS have
            # supplied 0.35 of London's liveability weight since v3.6/v3.7 with
            # no credit - and OGL v3.0 requires attribution. Same list length
            # and order, so the postcode line keeps its index-2 contract.
            'Transport access: DfT NaPTAN, Open Government Licence v3.0',
            'Healthcare access: NHS Organisation Data Service, Open Government Licence v3.0',
            # Index 2 by contract — two tests assert the postcode line's position.
            lambda: _postcode_source_line(local_postcode_served()),
            # The Home Office was dropped here on 2026-08-03. v3.5 moved the crime
            # rate to ONS Table C4, which left the Home Office credited in every
            # London response while answering for nothing — the same "crediting on
            # configuration rather than on what actually answered" this whole
            # registry exists to prevent. The breakdown below already named the
            # real sources; only this coarse line lagged.
            _BOROUGH_METADATA_SENTINEL,
            'Aviation noise context: DEFRA strategic noise mapping, Open Government Licence v3.0',
            # RESTORED 2026-09-07 (audit C7). The 2026-08-25 edit above removed
            # 'Sold prices: HM Land Registry' on the reasoning that HMLR "backs
            # /epc and /sold-prices, not this response". That was right about
            # SOLD PRICES and wrong about avgPrice and trend, which are the UK
            # House Price Index - a different HMLR product, feeding `afford`
            # (0.27 of the balanced score) and `growth` in THIS response. The
            # breakdown four lines below has said 'HM Land Registry House Price
            # Index (HPI)' throughout, so the correction and the omission sat in
            # one dict literal, and London - the flagship city - was the only
            # one of twelve UK cities crediting no price source at all.
            #
            # terms.html obliges integrators to carry `sources` through to their
            # own users, so an integrator obeying the terms exactly republished
            # HMLR data with no HMLR attribution.
            #
            # APPENDED, not inserted: the postcode line above is index 2 by
            # contract and test_score.py asserts that position directly.
            _hpi_source_line,
        ],
        'breakdown': {
            'quiet': 'DEFRA Strategic Noise Mapping (Round 4, 2022). Resolution chain: v3.1 direct raster sample at postcode centroid (when populated) → v3.0 Haversine to airports + flight-path geometry → v2.x borough-aggregate Lden band. The chosen resolution is reported in context.quietResolution.',
            'afford': _afford_breakdown_line,
            'live': f'Composite weighted (schools 35% + crime 30% + transport 25% + healthcare 10%). Schools: DfE Key Stage 4 Progress 8, 2023/24 Revised, local-authority level (rolled 2026-08-27 from 2022/23). The measure IS suspended for the 2024/25 and 2025/26 cohorts, whose KS2 baseline was lost to the 2020/2021 test cancellations, so 2023/24 is the last edition until 2026/27 publishes. Crime: ONS Crime in England and Wales, Police Force Area data tables, {CRIME_EDITION_LABEL}, Table C4, offences per 1,000 residents on mid-2024 population. Transport: NaPTAN, share of postcodes within 800 m of a rail, metro or tram node (v3.6, 2026-08-11). Healthcare: NHS Organisation Data Service, GP practices within 500 m (v3.7). Methodologically aligned with English Indices of Deprivation domains.',
        },
    },
    'nyc': {
        # What the derived afford and growth lines name for a non-sterling city (_afford_breakdown_line,
        # _growth_breakdown_line): `poolMembers` takes the pool's size as {n}.
        'priceSource': (
            'Curated New York borough median sale prices (USD). NOT HM Land Registry, '
            'which holds England and Wales only'
        ),
        'trendSource': 'Curated New York borough annualised price trend',
        'poolLabel': 'New York',
        'poolMembers': '{n} New York boroughs',
        'region': 'New-York',
        'sources': [
            'Borough metadata: curated from public New York City sources',
            'Crime: NYPD CompStat-derived offence rates per 1,000, against New York City population denominators',
            'Prices: curated New York borough median sale prices, in USD',
            'Aviation noise context: ESTIMATED from the FAA routes of JFK, LaGuardia, Newark and Teterboro, '
            'fitted to the Port Authority of New York and New Jersey noise-monitor readings for January-July '
            '2026; NOT a measurement at this address',
            'Borough aircraft band: the same estimate averaged over residents by 2020 ZIP Code Tabulation '
            'Area, weighted by US Census Bureau ACS 2020-2024 population (public domain)',
            'Licence note: Open Government Licence v3.0 covers UK Crown copyright and does NOT apply to any data in this response',
        ],
        'breakdown': {
            'quiet': (
                "ESTIMATED from the FAA's coded routes of JFK, LaGuardia, Newark and Teterboro: the "
                'runway directions flown at least 10% of the time (counted from aircraft positions), with '
                "each airport's size and the route weight fitted to the Port Authority of New York and New "
                "Jersey's noise-monitor readings for January-July 2026, so that at every airport the "
                'estimate reads louder than its monitors on average. Runway use is counted over the '
                "monitors' own months (every third day, January-July 2026), and each flown direction "
                'counts as a runway strip for 15 km out from the airport, the coded routes beyond. NOT '
                'DEFRA and not a measurement at this address: no published Lden survey covers New York, '
                'so the dB thresholds in METHODOLOGY section 3 are not directly applicable. A borough '
                'query reads a band derived from the same estimate, averaged '
                "over the borough's residents. The chosen resolution is reported in context.quietResolution."
            ),
            'afford': _afford_breakdown_line,
            'live': 'NYPD CompStat-derived crime rates with New York population denominators, plus curated school / transport / healthcare tiers. NOT ONS, Home Office, DfE, TfL or NHS — none has a New York remit. Cross-city comparison against UK boroughs should be approached with caution: different collection methodologies.',
        },
    },
    'westmidlands': {
        'sources': [
            _hpi_source_line,
            'Aviation noise context: ESTIMATED from Birmingham Airport runway geometry, with the distance ladder scaled by its measured DEFRA Round 4 55 dB Lden footprint; NOT a DEFRA sample at this address',
            f'Crime: ONS Crime in England and Wales, Police Force Area data tables, {CRIME_EDITION_LABEL}, Open Government Licence v3.0',
            _live_sources_line,
        ],
        'breakdown': {
            'quiet': 'PROVISIONAL ESTIMATE derived from Birmingham Airport (BHX) runway 15/33 alignment and its extended approach centreline. Where context.quietResolution reads raster, the value IS a DEFRA Round 4 sample at this postcode: the per-airport coverages were sampled and loaded on 2026-08-12 (7,339 postcodes across eight cities). Where it reads postcode, this address sits outside those contour strips and the geometry estimate below applies. Trust the resolution field over any sentence here - a static string cannot know which tier answered. So the dB Lden thresholds in METHODOLOGY section 3 are not evidenced for this city. The distance ladder is calibrated on Heathrow, which is several times Birmingham\'s size, so these bands reach further than the airport really does and are PESSIMISTIC rather than optimistic. Corridor waypoints are on a common 1 km interval across all cities, so corridor distances are comparable. Treat as indicative only.',
            'afford': _afford_breakdown_line,
            'live': _live_breakdown_line,
        },
    },
    'westyorkshire': {
        'sources': [
            _hpi_source_line,
            'Aviation noise context: ESTIMATED from Leeds Bradford Airport (LBA) runway 14/32 geometry, with the distance ladder scaled by its measured DEFRA Round 4 55 dB Lden footprint; NOT a DEFRA sample at this address',
            f'Crime: ONS Crime in England and Wales, Police Force Area data tables, {CRIME_EDITION_LABEL}, Open Government Licence v3.0',
            _live_sources_line,
        ],
        'breakdown': {
            'quiet': "PROVISIONAL ESTIMATE derived from Leeds Bradford Airport (LBA) runway 14/32 alignment and its extended approach centreline. Where context.quietResolution reads raster, the value IS a DEFRA Round 4 sample at this postcode: the per-airport coverages were sampled and loaded on 2026-08-12 (7,339 postcodes across eight cities). Where it reads postcode, this address sits outside those contour strips and the geometry estimate below applies. Trust the resolution field over any sentence here - a static string cannot know which tier answered. So the dB Lden thresholds in METHODOLOGY section 3 are not evidenced here. The distance ladder is calibrated on Heathrow, which is several times this airport's size, so the bands reach further than it really does and are PESSIMISTIC rather than optimistic. Corridor waypoints are on a common 1 km interval across all cities, so corridor distances are comparable. Indicative only.",
            'afford': _afford_breakdown_line,
            'live': _live_breakdown_line,
        },
    },
    'leicester': {
        'sources': [
            _hpi_source_line,
            'Aviation noise context: ESTIMATED from East Midlands Airport (EMA) runway 09/27 geometry, with the distance ladder scaled by its measured DEFRA Round 4 55 dB Lden footprint; NOT a DEFRA sample at this address',
            f'Crime: ONS Crime in England and Wales, Police Force Area data tables, {CRIME_EDITION_LABEL}, Open Government Licence v3.0',
            _live_sources_line,
        ],
        'breakdown': {
            'quiet': (
                'PROVISIONAL ESTIMATE derived from East Midlands Airport (EMA) runway 09/27 '
                'alignment and its extended approach centreline, sampled at 1 km. NOT sampled '
                'from the DEFRA Round 4 raster, which does publish an EMA surface: that surface '
                'covers a 35 x 10 km lobe around the runway and reaches a small minority of this '
                "city's addresses, so it cannot replace a borough-level estimate. The distance "
                'ladder is calibrated on Heathrow, several times EMA in size, so these bands '
                'reach further than the airport really does and the estimate is PESSIMISTIC.'
            ),
            'afford': _afford_breakdown_line,
            'live': _live_breakdown_line,
        },
    },
    'teesside': {
        'sources': [
            _hpi_source_line,
            'Aviation noise context: ESTIMATED from Teesside International Airport (MME) runway 05/23 geometry, with the distance ladder floored at the smallest published DEFRA Round 4 footprint because this airport is below the threshold DEFRA maps at all; NOT a DEFRA sample at this address',
            f'Crime: ONS Crime in England and Wales, Police Force Area data tables, {CRIME_EDITION_LABEL}, Open Government Licence v3.0. Cleveland for four authorities and Durham for Darlington, this city region spanning two forces',
            _live_sources_line,
        ],
        'breakdown': {
            'quiet': (
                'PROVISIONAL ESTIMATE derived from Teesside International Airport (MME) runway '
                '05/23 alignment and its extended approach centreline, sampled at 1 km. NOT '
                'sampled from DEFRA, which publishes no Round 4 surface for this airport. The '
                'distance ladder is calibrated on Heathrow, which handles many times MME traffic, '
                'so these bands reach further than the airport really does and the estimate is '
                'PESSIMISTIC - Stockton-on-Tees reads `severe` on approach geometry alone.'
            ),
            'afford': _afford_breakdown_line,
            'live': _live_breakdown_line,
        },
    },
    'southyorkshire': {
        'sources': [
            _hpi_source_line,
            'Aviation noise context: NO operating commercial airport in the city region; Doncaster Sheffield closed to commercial flights in 2022',
            f'Crime: ONS Crime in England and Wales, Police Force Area data tables, {CRIME_EDITION_LABEL}, Open Government Licence v3.0',
            _live_sources_line,
        ],
        'breakdown': {
            'quiet': "NO OPERATING COMMERCIAL AIRPORT. Doncaster Sheffield Airport is listed `type=closed` by OurAirports, commercial flights having ceased in 2022, and the nearest large airports are Leeds Bradford and Manchester at roughly 50-60 km. Every borough is therefore banded `low`. That is a MEASURED ABSENCE of a noise source rather than an unmeasured city, and it is stated so that a flat band cannot be read as a survey result. NOT a DEFRA sample.",
            'afford': _afford_breakdown_line,
            'live': _live_breakdown_line,
        },
    },
    'merseyside': {
        'sources': [
            _hpi_source_line,
            'Aviation noise context: ESTIMATED from Liverpool John Lennon Airport (LPL) runway 09/27 geometry, with the distance ladder scaled by its measured DEFRA Round 4 55 dB Lden footprint; NOT a DEFRA sample at this address',
            f'Crime: ONS Crime in England and Wales, Police Force Area data tables, {CRIME_EDITION_LABEL}, Open Government Licence v3.0',
            _live_sources_line,
        ],
        'breakdown': {
            'quiet': "PROVISIONAL ESTIMATE derived from Liverpool John Lennon Airport (LPL) runway 09/27 alignment and its extended approach centreline. Where context.quietResolution reads raster, the value IS a DEFRA Round 4 sample at this postcode: the per-airport coverages were sampled and loaded on 2026-08-12 (7,339 postcodes across eight cities). Where it reads postcode, this address sits outside those contour strips and the geometry estimate below applies. Trust the resolution field over any sentence here - a static string cannot know which tier answered. So the dB Lden thresholds in METHODOLOGY section 3 are not evidenced here. The distance ladder is calibrated on Heathrow, which is several times this airport's size, so the bands reach further than it really does and are PESSIMISTIC rather than optimistic. Corridor waypoints are on a common 1 km interval across all cities, so corridor distances are comparable. Indicative only.",
            'afford': _afford_breakdown_line,
            'live': _live_breakdown_line,
        },
    },
    'tyneandwear': {
        'sources': [
            _hpi_source_line,
            'Aviation noise context: ESTIMATED from Newcastle Airport (NCL) runway 07/25 geometry, with the distance ladder scaled by its measured DEFRA Round 4 55 dB Lden footprint; NOT a DEFRA sample at this address',
            f'Crime: ONS Crime in England and Wales, Police Force Area data tables, {CRIME_EDITION_LABEL}, Open Government Licence v3.0',
            _live_sources_line,
        ],
        'breakdown': {
            'quiet': "PROVISIONAL ESTIMATE derived from Newcastle Airport (NCL) runway 07/25 alignment and its extended approach centreline. Where context.quietResolution reads raster, the value IS a DEFRA Round 4 sample at this postcode: the per-airport coverages were sampled and loaded on 2026-08-12 (7,339 postcodes across eight cities). Where it reads postcode, this address sits outside those contour strips and the geometry estimate below applies. Trust the resolution field over any sentence here - a static string cannot know which tier answered. So the dB Lden thresholds in METHODOLOGY section 3 are not evidenced here. The distance ladder is calibrated on Heathrow, which is several times this airport's size, so the bands reach further than it really does and are PESSIMISTIC rather than optimistic. Corridor waypoints are on a common 1 km interval across all cities, so corridor distances are comparable. Indicative only.",
            'afford': _afford_breakdown_line,
            'live': _live_breakdown_line,
        },
    },
    'bristol': {
        'sources': [
            _hpi_source_line,
            'Aviation noise context: ESTIMATED from Bristol Airport (BRS) runway 09/27 geometry, with the distance ladder scaled by its measured DEFRA Round 4 55 dB Lden footprint; NOT a DEFRA sample at this address',
            f'Crime: ONS Crime in England and Wales, Police Force Area data tables, {CRIME_EDITION_LABEL}, Open Government Licence v3.0',
            _live_sources_line,
        ],
        'breakdown': {
            'quiet': "PROVISIONAL ESTIMATE derived from Bristol Airport (BRS) runway 09/27 alignment and its extended approach centreline. Where context.quietResolution reads raster, the value IS a DEFRA Round 4 sample at this postcode: the per-airport coverages were sampled and loaded on 2026-08-12 (7,339 postcodes across eight cities). Where it reads postcode, this address sits outside those contour strips and the geometry estimate below applies. Trust the resolution field over any sentence here - a static string cannot know which tier answered. So the dB Lden thresholds in METHODOLOGY section 3 are not evidenced here. The distance ladder is calibrated on Heathrow, which is several times this airport's size, so the bands reach further than it really does and are PESSIMISTIC rather than optimistic. Corridor waypoints are on a common 1 km interval across all cities, so corridor distances are comparable. Indicative only.",
            'afford': _afford_breakdown_line,
            'live': _live_breakdown_line,
        },
    },
    'cardiff': {
        'sources': [
            _hpi_source_line,
            'Aviation noise context: ESTIMATED from Cardiff Airport (CWL) runway 12/30 geometry, with the distance ladder floored at the smallest published DEFRA Round 4 footprint because this airport is below the threshold DEFRA maps at all; NOT a DEFRA sample at this address',
            f'Crime: ONS Crime in England and Wales, Police Force Area data tables, {CRIME_EDITION_LABEL}, Open Government Licence v3.0',
            _live_sources_line,
        ],
        'breakdown': {
            'quiet': "PROVISIONAL ESTIMATE derived from Cardiff Airport (CWL) runway 12/30 alignment and its extended approach centreline. NOT a DEFRA sample: DEFRA's Round 4 mapping does not cover Cardiff Airport at all - it is below the traffic threshold the Environmental Noise Directive maps at - so no raster exists to sample and the ladder is floored at the smallest published footprint, exactly as the sources line says.  So the dB Lden thresholds in METHODOLOGY section 3 are not evidenced here. The distance ladder is calibrated on Heathrow, which is several times this airport's size, so the bands reach further than it really does and are PESSIMISTIC rather than optimistic. Corridor waypoints are on a common 1 km interval across all cities, so corridor distances are comparable. Indicative only.",
            'afford': _afford_breakdown_line,
            'live': _live_breakdown_line,
        },
    },
    'norwich': {
        'sources': [
            _hpi_source_line,
            'Aviation noise context: ESTIMATED from Norwich International Airport (NWI) runway 09/27 final approaches as published in the UK AIP, with the distance ladder floored at the smallest published DEFRA Round 4 footprint because this airport is below the threshold DEFRA maps at all; NOT a DEFRA sample at this address',
            f'Crime: ONS Crime in England and Wales, Police Force Area data tables, {CRIME_EDITION_LABEL}, Open Government Licence v3.0. Norfolk force, one Community Safety Partnership row per authority',
            _live_sources_line,
        ],
        'breakdown': {
            'quiet': (
                'PROVISIONAL ESTIMATE derived from Norwich International Airport (NWI): its two '
                'runway 09/27 final approaches as published in the UK AIP, sampled at 1 km. NOT '
                'sampled from DEFRA, which publishes no Round 4 surface for this airport. The '
                'distance ladder is calibrated on Heathrow and floored at the smallest airport '
                'DEFRA maps, so it reaches further than Norwich really does and the estimate is '
                'PESSIMISTIC. No departure routes are drawn because Norwich publishes no SIDs in '
                'the AIP at all, as at Teesside. Indicative only.'
            ),
            'afford': _afford_breakdown_line,
            'live': _live_breakdown_line,
        },
    },
    'nottingham': {
        'sources': [
            _hpi_source_line,
            'Aviation noise context: ESTIMATED from East Midlands Airport (EMA) runway 09/27 geometry, with the distance ladder scaled by its measured DEFRA Round 4 55 dB Lden footprint; NOT a DEFRA sample at this address',
            f'Crime: ONS Crime in England and Wales, Police Force Area data tables, {CRIME_EDITION_LABEL}, CITY OF NOTTINGHAM ONLY, Open Government Licence v3.0',
            _live_sources_line,
        ],
        'breakdown': {
            'quiet': "PROVISIONAL ESTIMATE derived from East Midlands Airport (EMA) runway 09/27 alignment and its extended approach centreline. The airport lies OUTSIDE the city region, in Leicestershire, so no borough here is nearer than 16 km and none is banded above low-moderate. NOT sampled from the DEFRA Round 4 raster, so the dB Lden thresholds in METHODOLOGY section 3 are not evidenced here. The ladder is calibrated on Heathrow and is therefore PESSIMISTIC rather than optimistic. Indicative only.",
            'afford': _afford_breakdown_line,
            'live': 'Liveability IS served here since v3.6/v3.7 (2026-08-11) - trust context.liveResolution over any sentence, including this one, which spent thirteen days claiming the score beside it did not exist. The CITY OF NOTTINGHAM measures all four inputs (DfE Progress 8; ONS Table C4; NaPTAN rail, metro and tram access within 800 m; NHS ODS GP practices within 500 m). Broxtowe, Gedling and Rushcliffe measure TWO: ONS folds their crime into the combined South Nottinghamshire partnership row (publishing that figure three times would render one measurement as three, so it is left absent), and Progress 8 publishes for Nottinghamshire, the upper-tier authority, not for its districts. Absent inputs have their weight redistributed, never defaulted.',
        },
    },
    # CORRECTED 2026-08-12. `breakdown.live` here read "PARTIAL, 2 of 4 inputs
    # measured ... Transport and healthcare are NOT sourced" - true when written,
    # false from 2026-08-11, when transport landed in methodology v3.6 and
    # healthcare in v3.7. Two days of API responses told customers their
    # liveability rested on two inputs when it rested on four.
    #
    # Found only by widening scripts/check_score_sanity.py past London, whose
    # sixteen probes could never reach it. Provenance strings are hand-written
    # per city and nothing derives them from the data they describe, so this
    # class of staleness will recur - the same liability as the legend strings
    # that printed "NO DATA" over live readings. Prefer deriving; where a
    # string must be hand-written, give it a probe.
    #
    # NOTE the word PARTIAL must not appear in a live-breakdown string that is
    # not partial: the gate substring-matches on it, and quoting the old text
    # inside the new one reds the gate on a correct value.
    'manchester': {
        'sources': [
            _hpi_source_line,
            'Aviation noise context: ESTIMATED from Manchester Airport runway geometry, with the distance ladder scaled by its measured DEFRA Round 4 55 dB Lden footprint; NOT a DEFRA sample at this address',
            'Schools: Department for Education, Key Stage 4 Progress 8, 2023/24, Open Government Licence v3.0',
            f'Crime: ONS Crime in England and Wales, Police Force Area data tables, {CRIME_EDITION_LABEL}, Open Government Licence v3.0',
            'Transport: NaPTAN (DfT National Public Transport Access Nodes), Open Government Licence v3.0', 'Healthcare: NHS Organisation Data Service, Open Government Licence v3.0',
        ],
        'breakdown': {
            'quiet': 'PROVISIONAL ESTIMATE derived from Manchester Airport (MAN) runway alignment and approach geometry. Where context.quietResolution reads raster, the value IS a DEFRA Round 4 sample at this postcode: the per-airport coverages were sampled and loaded on 2026-08-12 (7,339 postcodes across eight cities). Where it reads postcode, this address sits outside those contour strips and the geometry estimate below applies. Trust the resolution field over any sentence here - a static string cannot know which tier answered. So the dB Lden thresholds in METHODOLOGY §3 are not evidenced for this city. Corridor waypoints are on a common 1 km interval across all cities, so corridor distances are comparable. Treat as indicative only.',
            'afford': _afford_breakdown_line,
            'live': f'MEASURED on all four inputs, matching London. Schools: DfE Key Stage 4 Progress 8, 2023/24 Revised, same release and year as London. Crime: ONS Crime in England and Wales, Police Force Area data tables, {CRIME_EDITION_LABEL}, Table C4 Community Safety Partnership rows, same release and period as London. Transport: NaPTAN, share of postcodes within 800 m of a rail, metro or tram node (methodology v3.6). Healthcare: NHS Organisation Data Service, share of postcodes within 500 m of a GP practice (v3.7).',
        },
    },
    # The San Francisco Bay Area (release 2, 2026-10-22). Every source is a US one and is credited as its
    # publisher asks (LICENSING.md); none is UK, so nothing here may name DEFRA, the EA, ONS, DfE, NaPTAN or
    # NHS except to say they do NOT apply (test_non_uk_city_never_credits_uk_bodies). Liveability and the
    # environment lines are DERIVED per city from its record, so a city whose crime, transport or flood is
    # withheld credits only what it was scored on and says why the rest is missing.
    'bayarea': {
        'priceSource': (
            'US Census Bureau, American Community Survey 2020-2024 5-year estimates, table B25077: the median '
            'VALUE of owner-occupied homes as their owners estimate it, in USD, not sale prices; public domain'
        ),
        'trendSource': (
            'Federal Housing Finance Agency House Price Index for counties (annual, all-transactions, 2025; a '
            "series FHFA calls developmental), each city taking its county's change"
        ),
        'poolLabel': 'Bay Area',
        'poolMembers': '{n} Bay Area cities',
        'region': 'Bay-Area',
        'liveInputs': {
            'crimePer1000Us': (
                'California DOJ OpenJustice Crimes and Clearances 2025, violent and property crimes per 1,000 '
                'residents (US Census Bureau Vintage 2025 estimates), public domain, on a US scale anchored on '
                f"California's own rate over the agencies that police residents, {US_CALIFORNIA_ANCHORS['crimePer1000Us']}"
            ),
            'transport': (
                'US Department of Transportation, Bureau of Transportation Statistics, National Transit Map '
                'Stops: the share of residents '
                'within 800 m of a rail, metro or light-rail station, banded as the UK is (CC BY 3.0 US; buses '
                'and ferries not counted)'
            ),
        },
        'liveNotHeld': (
            ' Schools and healthcare are not held for the Bay Area, so liveability is crime and transport, and '
            'a city missing either is below the two-input floor.'
        ),
        'envNote': (
            ' Air quality is not held for the Bay Area. Road noise and flood are shares of residents at 2020 '
            "Census blocks, on US scales anchored on California's own shares (road "
            f"{US_CALIFORNIA_ANCHORS['roadNoiseUsSharePct']}%, flood {US_CALIFORNIA_ANCHORS['floodSfhaPct']}%): 10 at "
            "none, 5.0 at California's figure, 0 at double; NOT comparable with the UK's DEFRA and Environment "
            'Agency scales.'
        ),
        'sources': [
            'Prices: US Census Bureau, American Community Survey 2020-2024 5-year estimates, table B25077 '
            '(median value of owner-occupied homes, USD), public domain',
            'Price trend: Federal Housing Finance Agency, House Price Index for counties (annual, '
            'all-transactions), public domain; no FHFA endorsement is implied',
            _live_sources_line,
            'Residents: US Census Bureau, 2020 Census block population (P.L. 94-171), public domain; the frame '
            "every Bay Area share and the city aircraft band is taken over",
            'Aviation noise context: ESTIMATED from the FAA routes of San Francisco, Oakland and San Jose '
            "airports, fitted to SFO's 29 noise monitors (DataSF, PDDL 1.0) and San Jose airport's 13 (its "
            'quarterly noise report to Caltrans), July 2025-June 2026; NOT a measurement at this address',
            'Licence note: Open Government Licence v3.0 covers UK Crown copyright and does NOT apply to any data in this response',
        ],
        'breakdown': {
            'quiet': (
                "ESTIMATED from the FAA's coded routes of San Francisco (SFO), Oakland (OAK) and San Jose (SJC): "
                'the runway directions flown, counted from aircraft positions, with each airport\'s size and the '
                "route weight fitted to SFO's 29 noise monitors (their aircraft-only ANEEM CNEL) and San Jose's 13 "
                '(CNEL), July 2025-June 2026, so that the estimate reads louder than the monitors at every airport '
                'on average. NOT DEFRA and not a measurement at this address: no published Lden survey covers the '
                'Bay Area. A city query reads a band derived from the same estimate at every 2020 Census resident '
                "block, averaged over the city's residents and published at the band at or below that average, so "
                'it never reads quieter. The chosen resolution is reported in context.quietResolution.'
            ),
            'afford': _afford_breakdown_line,
            'live': _live_breakdown_line,
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


# --- environment provenance (audit F1) -------------------------------------
#
# The scored `environment` component was credited to NOBODY: no sourceBreakdown
# key and no sources line, while terms.html obliges integrators to carry the
# sources array through to their own users and METHODOLOGY §18 tells their
# auditor the array is complete. The component carries 0.14 of six personas and
# 0.18 of `family` and `laterlife`, entirely from three OGL v3.0 datasets.
#
# Derived per city rather than listed, because a hand-written list is what went
# stale through v3.9 and v4.0 without one gate noticing.

_ENV_SOURCE_TEXT = {
    'airQuality': (
        'Air quality: DEFRA background pollution maps (PCM), '
        'Open Government Licence v3.0'
    ),
    'roadNoise': (
        'Road noise: DEFRA Strategic Noise Mapping Round 4 road Lden, '
        'Open Government Licence v3.0'
    ),
    'flood': (
        'Flood risk: Environment Agency Risk of Flooding from Rivers and Sea, '
        'Open Government Licence v3.0'
    ),
}

_ENV_FIELD_OF = {
    'airQuality': 'airQualityWhoRatio',
    'roadNoise': 'roadNoiseAboveWhoPct',
    'flood': 'floodMediumOrHighPct',
}

# The US fields filling the same slots (env_component_scores), and their own sources: a Bay Area response
# crediting DEFRA or the Environment Agency would be the 2026-07 defect that put UK provenance on US data.
_ENV_US_FIELD_OF = {
    'roadNoise': 'roadNoiseUsSharePct',
    'flood': 'floodSfhaPct',
}
_ENV_US_SOURCE_TEXT = {
    'roadNoise': (
        'Road noise: USDOT Bureau of Transportation Statistics, National Transportation Noise Map 2022 '
        '(road, 24-hour LAeq), a US government work; BTS says it should not be used to evaluate noise '
        'levels at individual locations'
    ),
    'flood': (
        'Flood risk: FEMA National Flood Hazard Layer, Special Flood Hazard Area (1% annual chance), '
        'public domain'
    ),
}


def _env_field_in_use(city, key):
    """'uk' or 'us': which field fills environment input `key` in `city`'s records, or None for neither."""
    boroughs = ((CITIES.get(city) or {}).get('boroughs') or {}).values()
    if any(isinstance(b.get(_ENV_FIELD_OF[key]), (int, float)) for b in boroughs):
        return 'uk'
    us_field = _ENV_US_FIELD_OF.get(key)
    if us_field and any(isinstance(b.get(us_field), (int, float)) for b in boroughs):
        return 'us'
    return None


def _env_source_text(city, key):
    return (_ENV_US_SOURCE_TEXT if _env_field_in_use(city, key) == 'us' else _ENV_SOURCE_TEXT)[key]


def _env_inputs_present(city):
    """Which environment datasets any borough of `city` actually carries.

    Read from the borough records, not declared, so a city that gains or loses
    a dataset changes its own provenance without anyone remembering to.
    """
    return [key for key in _ENV_FIELD_OF if _env_field_in_use(city, key)]


def _env_source_line(key):
    """A source line for one dataset, or None where the city does not use it.

    With a borough's record (code review, 2026-10-22), a US city also drops the line where that record was not
    scored on it: the input is withheld (San Jose's flood), or the component is below its floor (San Jose's road
    then informs nothing). A UK city keeps its city-level credit, because a UK postcode response can report a
    reading from the same dataset (`build_environment`) even where the component is not scored, and the credit
    must travel with that reading; a US response has no per-location readings to credit.
    """

    def line(city, bd=None):
        if key not in _env_inputs_present(city):
            return None
        if bd is not None and not uk_shape(city):
            withheld = {_WITHHELD_INPUT_OF.get(f) for f in (bd.get('withheld') or {})}
            if key in withheld or len(env_component_scores(bd)) < _ENV_MIN_FIELDS:
                return None
        return _env_source_text(city, key)

    return line


def _env_breakdown_line(city, bd=None):
    """Per-component lineage for `environment`.

    METHODOLOGY §18: where a component has no source the response must SAY so
    rather than publish a silent default, so the below-floor and no-data cases
    are stated rather than omitted. `bd`, when given, adds what that borough's
    record withholds (a Bay Area city's flood share FEMA has not determined).
    """
    present = _env_inputs_present(city)
    if not present:
        # 'NOT' in capitals is load-bearing, not shouting:
        # test_non_uk_city_never_credits_uk_bodies permits a UK body to appear
        # in a non-UK response ONLY inside an explicit disclaimer, and detects
        # one by that token. The guard exists because New York once shipped
        # crediting MHCLG, DfE, TfL, NHS and DEFRA under OGL v3.0, none of which
        # has any New York remit. Naming DEFRA here to say it does NOT apply is
        # the honest form; softening the token would weaken a real guard.
        return (
            'NOT scored for this city. DEFRA and the Environment Agency publish '
            'for the UK only, so no environment input is available here.'
        )
    named = ', '.join(
        f'{_env_source_text(city, k).split(":")[0]} ({_ENV_WEIGHTS[k]:.2f})' for k in present
    )
    # Both '' for every UK city, so no UK sentence changes.
    note = (CITY_PROVENANCE.get(city) or {}).get('envNote', '')
    withheld = _withheld_sentence(bd, ('flood',))
    if len(present) < 2:
        return (
            f'Not scored for this city: {named} is the only input available, below '
            'the two-input floor the component requires, so environment is omitted '
            'from the score rather than published on one reading.' + note + withheld
        )
    return (
        f'{named}. Weights are re-normalised over the inputs a borough actually '
        'has; a borough below the two-input floor omits the component entirely.' + note + withheld
    )


# --- flight-route provenance (website audit 2026-10-06, C1) -----------------
#
# The UK flight routes and runway axes behind the quiet estimate have been
# DERIVED FROM THE UK AIP since v5.3-v5.5: every corridor between the
# FLIGHT-PATHS markers and every entry in RUNWAY_AXIS_DEG is generated from
# data/flight-procedures.json by scripts/build_flight_paths.py. The AIP is
# published by NATS and is public but NOT openly licensed, and LICENSING.md
# asks for it to be credited wherever the routes are used. The website
# credited it from 6 Oct; `sources` did not, and terms.html obliges
# integrators to carry `sources` through to their own users, so every
# response passed the omission on.
#
# DERIVED from the geometry the engine scores with, not listed by city: an
# airport in the city's CITY_GEOMETRY, or the airport a corridor serves, whose
# code is in RUNWAY_AXIS_DEG. That table is generated from the AIP records and
# held to them by build_flight_paths.py's blocking --check, so membership
# means "the AIP publishes this airport and the quiet term reads its axis".
# New York's routes are the FAA's (v5.6) and credited by _us_routes_source_line; South
# Yorkshire has no airport. Both get None, and build_sources drops the line.
#
# City-level, like the aviation lines beside it, and deliberately not keyed
# on the tier that answered: the postcode geometry estimate reads the routes
# and axes, and Norwich's borough band is also built from AIP thresholds
# (scripts/build_aircraft_bands.py), so no tier rule describes every city.

_AIP_SOURCE_LINE = (
    'Flight routes: UK Aeronautical Information Publication (NATS), derived by Sky Score '
    'for the aircraft noise estimate; public but not openly licensed, and not for navigation'
)


def _aip_airports(city):
    """Codes of the airports whose UK AIP geometry this city's quiet estimate reads.

    Sorted, so the breakdown sentence that names them is stable.
    """
    geo = CITY_GEOMETRY.get(city) or {}
    used = {ap.get('code') for ap in geo.get('airports') or []}
    used |= {path.get('airport') for path in geo.get('paths') or []}
    return sorted(code for code in used if code in RUNWAY_AXIS_DEG)


def _aip_source_line(city):
    """The UK AIP credit, or None for a city whose geometry does not come from it."""
    return _AIP_SOURCE_LINE if _aip_airports(city) else None


# US flight routes and runway use (2026-10-16). A city whose quiet geometry is the
# FITTED US one - it carries 'runway_lobes': New York, and the Bay Area once it is served -
# scores from the FAA's coded routes and from runway use Sky Score counted from adsb.lol
# flight tracks. The FAA supplies its procedures "as is", without warranty, and asks for
# that to travel with them; adsb.lol is ODbL, whose produced works must say so. Both are
# derived from the geometry the engine scores with, like the AIP line above, and None
# (dropped) everywhere else, so no UK response can carry them.
_FAA_ROUTES_LINE = (
    'Flight routes: FAA Coded Instrument Flight Procedures, derived by Sky Score for the '
    'aircraft noise estimate; supplied "as is", without warranty, and not for navigation'
)


def _us_routes_source_line(city):
    """The FAA credit, for a city scored from the fitted US geometry; else None."""
    return _FAA_ROUTES_LINE if 'runway_lobes' in (CITY_GEOMETRY.get(city) or {}) else None


def _runway_use_source_line(city):
    """The adsb.lol (ODbL) credit, naming the period the runway use was counted over."""
    period = (CITY_GEOMETRY.get(city) or {}).get('runway_use_period')
    if not period:
        return None
    return (f'Runway use: counted by Sky Score from aircraft positions via adsb.lol (ODbL 1.0), '
            f'{period}; the counts are offered under the ODbL')


def _quiet_breakdown_with_routes(static):
    """Wrap a city's hand-written `quiet` lineage with where its routes come from.

    The twelve UK strings describe the estimate and its DEFRA scaling and name
    no source for the corridors themselves, so a reader of the breakdown could
    not tell the routes are the AIP's. The sentence is appended only where
    _aip_airports finds AIP geometry, and names those airports.
    """

    def line(city, bd=None):
        codes = _aip_airports(city)
        if not codes:
            return static
        return (
            f"{static} The geometry estimate's flight routes and runway alignments "
            f"({', '.join(codes)}) are derived by Sky Score from the UK Aeronautical "
            'Information Publication (NATS), and are not for navigation.'
        )

    return line


# Environment provenance is injected here rather than written into each of the
# thirteen city dicts above (audit F1). A per-city literal is exactly what went
# stale through v3.9 and v4.0 with no gate noticing, and a city added tomorrow
# would need someone to remember. Injection means it cannot be forgotten, and
# both the breakdown line and the three source lines are DERIVED from the
# borough records, so a city that gains or loses a dataset re-describes itself.
for _city_key, _prov in CITY_PROVENANCE.items():
    _prov['breakdown']['env'] = _env_breakdown_line
    # v5.1: growth derived the same way, for the same reason - see
    # _growth_breakdown_line. The CPIH line is None for New York and dropped.
    _prov['breakdown']['growth'] = _growth_breakdown_line
    _prov['sources'] = list(_prov['sources']) + [
        _env_source_line('airQuality'),
        _env_source_line('roadNoise'),
        _env_source_line('flood'),
        _inflation_source_line,
    ]
    # POSTCODE RESOLUTION, for every UK city (2026-09-13 audit, I4). The
    # `_postcode_source_line` callable sat in London's list alone - at index 2,
    # by a contract two tests assert - so twelve cities' responses never named
    # ONS NSPL or postcodes.io, the two OGL datasets that have resolved every
    # UK postcode query since 2026-08-12. Appended here, not inserted, so no
    # city's existing indices move; London keeps its own copy at index 2 and
    # is skipped. New York resolves ZIPs from its own table and credits
    # neither body. Injected for the same reason the environment lines are:
    # a per-city literal is what went stale.
    if _city_key != 'london' and CITIES[_city_key]['country'] == 'United Kingdom':
        _prov['sources'].append(lambda: _postcode_source_line(local_postcode_served()))
    # FLIGHT ROUTES, from the UK AIP (website audit 2026-10-06, C1). APPENDED
    # last, after the postcode line, so no city's existing indices move -
    # London's postcode line keeps its index-2 contract. Derived per city by
    # _aip_airports; None where the geometry is not the AIP's, and dropped.
    _prov['sources'].append(_aip_source_line)
    # US ROUTES AND RUNWAY USE (2026-10-16), appended after the AIP line for the same
    # reason; None, and dropped, for every city not scored from the fitted US geometry.
    _prov['sources'].append(_us_routes_source_line)
    _prov['sources'].append(_runway_use_source_line)
    _prov['breakdown']['quiet'] = _quiet_breakdown_with_routes(_prov['breakdown']['quiet'])
del _prov, _city_key


# The eight regional aviation lines in CITY_PROVENANCE describe the GEOMETRY
# tier and end "NOT a DEFRA sample at this address". That was true of every
# postcode until 2026-08-12, when the per-airport DEFRA rasters were loaded
# for seven airports and the raster tier began answering ~7,300 postcodes in
# those cities - and the line kept saying it. build_sources() had no way to
# know which tier answered, so an integrator obeying terms.html republished a
# denial of the dataset that scored the address, and that dataset was
# credited nowhere (2026-09-13 audit, C2; verified live on M22 0AD:
# quietResolution "raster", measuredAtLocation true, and this tail in the
# same body). The prefix is the marker build_sources substitutes on.
_AVIATION_ESTIMATE_PREFIX = 'Aviation noise context: ESTIMATED from '
_AVIATION_RASTER_LINE = (
    'Aviation noise context: DEFRA Round 4 strategic noise mapping, Lden sampled at '
    'this postcode (Open Government Licence v3.0); the airport-geometry estimate '
    'stands in only where DEFRA published no contour'
)


def build_sources(city='london', bd=None, quiet_source=None):
    """The response `sources` array, built per request and per city.

    Deliberately a function, not the import-time constant it replaced: the
    postcode line depends on runtime state (see _postcode_source_line), and
    a constant snapshot taken at cold start would keep claiming postcodes.io
    for the life of a container that had since started resolving locally.

    An unknown city says so rather than falling back to London's list — a
    silent default is how the original defect published UK provenance over
    New York data.

    `quiet_source` is `context.quietResolution` for the response being built
    ('raster', 'postcode', 'borough'). When the DEFRA raster answered, the
    regional aviation line - written for the geometry tier - is replaced by
    the line that credits the dataset that actually scored the address. None
    (a caller with no scored query, e.g. the licence file) leaves the
    geometry line, which is the honest default: it is what the great
    majority of postcodes get.
    """
    prov = CITY_PROVENANCE.get(city)
    if prov is None:
        return [f'Provenance not recorded for city {city!r}']
    out = []
    for line in prov['sources']:
        if callable(line):
            # Some provenance callables need the city (the computed liveability
            # line) and some do not (the postcode-resolver line, which reads a
            # module-level flag). The SIGNATURE decides, not a try/except: a
            # bare `except TypeError` around a call also swallows TypeErrors
            # raised INSIDE the callable, and it did - a len()-over-generator
            # bug surfaced as "missing argument" from the fallback path rather
            # than as itself. The liveability line additionally takes the
            # borough's row, so a response describes the borough it scored
            # rather than the city's any-borough union (see
            # _live_inputs_present for the ten boroughs that contradiction
            # reached).
            if _takes_city(line):
                out.append(line(city, bd) if _takes_borough(line) else line(city))
            else:
                out.append(line())
        elif line is _BOROUGH_METADATA_SENTINEL:
            out.append(_london_borough_metadata_line(bd))
        else:
            out.append(line)
    # A callable may return None to mean "this dataset is not used for this
    # city". Dropping it is the point: crediting DEFRA for New York would be
    # the 2026-07 defect that published UK provenance over US data, and
    # test_non_uk_city_never_credits_uk_bodies exists because of it.
    if quiet_source == 'raster':
        out = [
            _AVIATION_RASTER_LINE if isinstance(line, str) and line.startswith(_AVIATION_ESTIMATE_PREFIX) else line
            for line in out
        ]
    return [line for line in out if line]


def build_source_breakdown(city='london', bd=None):
    """Per-component lineage for `city`. See build_sources() for why per-city.

    `bd` is the resolved borough row when there is one. Without it the
    liveability line counts the city-level union, which over-credits any
    borough missing an input - see _live_breakdown_line.
    """
    prov = CITY_PROVENANCE.get(city)
    if prov is None:
        return {}

    def _resolve(value):
        if not callable(value):
            return value
        # Pass bd only to the builders that accept it, so a per-component
        # lineage function that does not care is unaffected.
        try:
            return value(city, bd)
        except TypeError:
            return value(city)

    # Callables are resolved here for the same reason build_sources resolves
    # them: a value that depends on the data must be read at response time.
    return {key: _resolve(value) for key, value in prov['breakdown'].items()}


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


def round_1dp(x):
    """Round to one decimal place, halves AWAY FROM ZERO - not Python's default.

    Every number this returns has a SECOND holder: index.html recomputes the
    same score client-side and rounds it with Math.round(), which takes halves
    towards +infinity. Python's round() takes halves to EVEN. The two agree on
    every input except an exact .x5 tie, where they disagree by construction -
    so the tie-break is made explicit and identical here rather than left to
    two languages' differing defaults.

    It is not hypothetical. Four boroughs sit exactly on a tie today (Manhattan,
    Bronx, Dudley, Bath and North East Somerset) and agree only because float
    noise happens to push each one off the boundary in the same direction on
    both sides. Removing that noise from live_weights_for is what surfaced it:
    banker's rounding sends BANES to 5.8 while the site says 5.9, and
    site/API divergence is a defect this repo has already shipped three times.

    math.floor(x + 0.5) reproduces Math.round() exactly, negatives included
    (both send -2.5 to -2), so the two holders cannot drift on a tie again.
    """
    return math.floor(x * 10 + 0.5) / 10


def uk_shape(city):
    """Whether the UK liveability shape applies here: the curated UK bands, with Progress 8 standing in for the
    schools band in England. A REGISTRY question (`country`), where it was a by-name test against New York in four
    places, so a new US city cannot fall into the UK shape by not being named (tests/test_us_city_branches.py). A
    city outside CITIES reads as UK, exactly as that test did; every caller passes a registry key.
    """
    cfg = CITIES.get(city)
    return cfg is None or cfg['country'] == 'United Kingdom'


def us_anchored_to_score(value, anchor):
    """A US measure (crime per 1,000, the share of residents in BTS's road band holding WHO's 53 dB Lden, or
    the share in FEMA's 1% flood zone) to 0-10, LINEAR on its California anchor: 10 at zero, 5.0 at the
    anchor, 0 at double or more.

    Bill, 2026-10-18, over a log form that put 9 Bay Area cities at 10 on crime: the same form as the UK's road
    and crime ramps, so no city reaches 10 unless it has none. The anchors are published, never the loaded
    cohort's range (the min-max trap METHODOLOGY 7.1 rejects): California's 2025 rate over every agency that
    polices residents, like for like with a city's rate (Bill, 2026-10-22: 21.39 per 1,000; the all-agency 22.27
    counted railroad, university and Highway Patrol crimes no city rate holds; scripts/build_bayarea_crime.py),
    its statewide road share, 6.88%
    (scripts/build_bayarea_road.py), and its flood share, 3.14%, measured over every county
    (scripts/build_bayarea_flood.py --write-state). NOT comparable with the UK scores, whose counting differs
    (decision 4). Absent is absent: None in, None out, never a stand-in value. Read by live_component_scores
    and env_component_scores through _US_SCALED, so only a record carrying a US field reaches it.
    """
    if value is None:
        return None
    if not anchor or anchor <= 0:
        raise ValueError(f'a US scale needs a positive anchor, got {anchor!r}')
    return max(0.0, min(10.0, 10.0 - 5.0 * value / anchor))


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

# Declared weights. Previously these were four literals inside get_live_score;
# naming them is what lets an absent input be redistributed rather than filled
# with a placeholder.
#
# They sum to 1.0 as DECLARED and to 0.9999999999999999 as FLOATS, which is why
# live_weights_for short-circuits a complete set instead of dividing it through
# by that total. See the note there.
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
    # Nothing absent means nothing to redistribute, and that identity has to be
    # EXACT rather than merely arithmetically true. The declared weights sum to
    # 0.9999999999999999 in binary floating point, so dividing a COMPLETE set
    # through by their own total inflates each one by ~1e-16 - invisible
    # everywhere except on a borough sitting exactly on a rounding boundary,
    # where it decides the published digit. Bath and North East Somerset landed
    # there on the 2023/24 Progress 8 roll: its declared weights give exactly
    # 5.85 and the renormalised ones gave 5.850000000000001, so it published
    # 5.9 having been nudged there by float noise rather than by its data.
    if len(present) == len(_LIVE_FIELDS):
        return {f: _LIVE_WEIGHTS[f] for f in present}
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
    elif bd.get('crimePer1000Us') is not None:
        # The same slot on the US scale (validate_us_fields: never both on one record).
        scores['crimeRate'] = us_anchored_to_score(bd['crimePer1000Us'], US_CALIFORNIA_ANCHORS['crimePer1000Us'])
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
    return round_1dp(sum(scores[f] * w for f, w in weights.items()))


# ---------------------------------------------------------------------------
# Environment composite (methodology v4.0). Air quality + road noise + flood.
#
# WHY THIS EXISTS AT ALL. All three datasets have been loaded, verified and
# banded for every covered city since 2026-08-11, and none entered the weighted
# total until now. Air quality and flood were wired in by v3.9; ROAD NOISE was
# the last measured input still only DRAWN - it colours a map layer and is
# reported by /v1/environment, and nothing scored it. This wires it in and
# closes the "measured but display-only" category entirely.
#
# ROAD NOISE COVERAGE IS NOT A CONSTRAINT, WHICH IS WHY IT COULD BE SCORED.
# Leicester and Teesside carried no road or flood raster until 2026-08-29, and
# CLAUDE.md, AUDIT_REPORT I6 and this file all recorded that as a property of
# the data. It was not: fetch_defra_road_noise.py and fetch_ea_flood_risk.py
# are both per-city against ENGLAND-WIDE coverages, both cities are in England,
# both have boundary files, and neither was in NO_ROAD_COVERAGE or
# NO_FLOOD_COVERAGE. The rasters had simply never been fetched for the two
# cities that joined on 2026-08-11. A measurement recorded without its cause
# reads as a constraint.
#
# WHY THE CONTINUOUS FIELD AND NOT THE BAND. The three-band summaries exist to
# colour a map, and they are far too coarse to score: measured across all 91
# boroughs on 2026-08-26, 68.1% of `airQuality` is "moderate" and 63.7% of
# `flood` is "low". Scoring those would put two-thirds of the country on an
# identical number. The continuous fields build_borough_bands.py already writes
# beside them discriminate properly - airQualityWhoRatio spans 1.26-3.39 with 60
# distinct values in 86 boroughs, floodMediumOrHighPct spans 0-31.39 with 69 in
# 73. The data was always there; nothing read it.
#
# ROAD NOISE HAD THE SAME TRAP ONE LEVEL DOWN, and the obvious continuous field
# is the WRONG one. Two are derived beside the band: roadNoiseLdenMedian looks
# plottable and is not - measured 2026-08-29 it carries only 41 distinct values
# across 73 boroughs with an interquartile range of 1.7 dB (53.0-54.7), because
# a borough-wide median of a 10 m raster averages the quiet streets into the
# arterials. roadNoiseAboveWhoPct carries 69 distinct values over an IQR of
# 13.4 points. They correlate at 0.931 - the same signal, very differently
# resolved. "Continuous" was never the criterion; DISCRIMINATION was.
#
# WHY THESE ANCHORS AND NOT THE OBSERVED RANGE. METHODOLOGY 7.1 is explicit that
# "no band is a percentile or a tertile", because a scale defined relative to the
# other boroughs cannot return "all of them are bad" - the answer that would
# matter most. So both ends of both ramps are PUBLISHED thresholds:
#
#   Air quality  1.0x = the WHO 2021 annual-mean guideline, already the anchor
#                the ratio is expressed against -> 10
#                4.0x = the UK legal limit for NO2 (40 ug/m3 against WHO's 10),
#                a statutory figure, not one chosen here -> 0
#   Road noise   0% of postcodes at or above the WHO 2018 road-traffic
#                guideline of 53 dB Lden -> 10
#                100% = every address in the borough over that guideline -> 0.
#                Both ends are the natural limits of a SHARE, and the threshold
#                defining the share is WHO's, not ours. Zeroing at the `high`
#                band cut of 66.7% was measured and rejected: it clamps 11 of 73
#                boroughs to 0. Flood can use its band cut because its
#                distribution is crushed toward zero (median 1.08%); road's
#                median is 56.6%, the opposite shape, so the same choice is
#                wrong here. Anchoring the low end on the observed minimum was
#                rejected outright - that is the min-max trap this file names
#                below.
#   Flood        0% of postcodes at EA Medium-or-High -> 10
#                10% = the cut METHODOLOGY 7.1 already uses for the `high` band,
#                which is itself the 1%-annual-chance planning line -> 0
#
# Picking the cohort max (3.39, City of London) would have been the min-max trap
# this file rejects everywhere else, and would silently re-scale every borough
# the next time one city is added.
# ---------------------------------------------------------------------------

_ENV_FIELDS = ('airQuality', 'roadNoise', 'flood')

_ENV_WEIGHTS = {
    'airQuality': 0.45,
    'roadNoise': 0.35,
    'flood': 0.20,
}

# Air quality keeps the largest share on the v3.9 reasoning: it is a CHRONIC
# exposure applying to every resident every day. ROAD NOISE takes second on the
# same reasoning - it is the other continuous daily exposure, and largely from
# the same traffic - but a smaller share than air because its health evidence
# base (annoyance, sleep disturbance) is softer than air quality's mortality
# one. Flood stays smallest as the only EPISODIC risk, near-zero for most of the
# country (median 1.08% of postcodes) and already surfaced in conveyancing
# searches. Flood is not weighted down because it matters less to the household
# it happens to.
#
# MEASURED CONSEQUENCE, so it is not discovered later. Adding road noise LOWERS
# environment for every covered borough, because most urban English addresses
# genuinely exceed the WHO road guideline: the median environment score moves
# 7.80 -> 6.75, mean -0.98, worst -1.74 (Westminster). At env's 0.14 balanced
# weight that is at most -0.24 on a headline score. Some boroughs RISE - Sefton
# +0.49 - which is the component discriminating rather than a uniform penalty.
# The fall is new information, not a re-basing: it is what counting a real
# adverse exposure looks like the first time it is counted.

_AQ_GUIDELINE_RATIO = 1.0   # WHO 2021 annual mean, NO2 10 / PM2.5 5 ug/m3
_AQ_LEGAL_LIMIT_RATIO = 4.0  # UK legal limit NO2 40 ug/m3 = 4x the WHO guideline
_FLOOD_HIGH_PCT = 10.0       # METHODOLOGY 7.1 `high` cut, the planning threshold
# 100% = every address in the borough at or above WHO's 53 dB Lden road-traffic
# guideline. The WHO threshold itself lives in build_borough_bands.py, which is
# what DERIVES the share; this is the ramp's far end, not the exposure cut.
_ROAD_FULL_EXPOSURE_PCT = 100.0

# Floor of TWO measured inputs. RAISED FROM ONE on 2026-08-29, when road noise
# made it a third input, and raised on a MEASUREMENT rather than a principle.
#
# v3.9 set this to 1 and wrote down the risk it accepted: a single-input score
# "may be systematically FLATTERING", because the missing input is often the one
# the borough would score worst on. That was the right call at two declared
# inputs, where one of two is half of what the label promises. At THREE declared
# inputs one is a third, and the risk stops being theoretical.
#
# WHAT WAS MEASURED, 2026-08-29, over the 86 boroughs that then had a score.
# Adding road noise lowers every borough that HAS road data and leaves untouched
# every borough that does not - so the boroughs missing an input rise through
# the table purely by standing still. Keeping the floor at 1 would move the 13
# single-input boroughs (Leicester 8, Teesside 5) from a median rank of 41 to 9
# of 86, and from 3 of the top 20 to 10 of the top 20. Teesside would hold the
# top FOUR places outright - Redcar and Cleveland, Hartlepool, Darlington,
# Stockton-on-Tees - every one of them scored on one input of three, and
# Teesside is coastal, so flood is plausibly its worst input. A national table
# whose leaders lead because we know least about them is worse than no table.
#
# WHY NOT LEAN ON env_single_input() INSTEAD. Because it has no consumer and
# never has. It is published as context.environmentSingleInput and is read by
# NOTHING - not index.html (which mentions it only in a comment), not the area
# pages, not the extension; the single other reference in the tree is a unit
# test asserting it is False. Its own docstring says it "exists so ranking
# surfaces can exclude them", and no ranking surface does. That is the same
# shape as lineStatusAvailable, fixed on 2026-08-27: A FIELD ONLY ITS PRODUCER
# READS IS NOT A FIX, and a mitigation that was never wired cannot be the reason
# to keep a floor that needs it.
#
# WHAT IT COSTS, and why the cost is small. Fetching the two rasters Leicester
# and Teesside had never been given takes them from one input to three, so the
# boroughs this floor actually excludes are CARDIFF's four - Wales genuinely has
# no English road or flood coverage, exactly as it has no Progress 8. They now
# decline the component and disclose environmentResolution 'unavailable',
# which is what New York's five have always done. Four of 99, to remove a
# structurally misleading ranking position.
_ENV_MIN_FIELDS = 2


def aq_to_score(who_ratio):
    """Air quality 0-10 from the worse-of-NO2/PM2.5 ratio to its WHO guideline.

    Higher is better, like every other component score and unlike the ratio it
    is derived from - see METHODOLOGY 11.0 on scale direction. Meeting the WHO
    guideline is 10; reaching the UK legal limit is 0.
    """
    span = _AQ_LEGAL_LIMIT_RATIO - _AQ_GUIDELINE_RATIO
    return max(0.0, min(10.0, 10.0 * (_AQ_LEGAL_LIMIT_RATIO - who_ratio) / span))


def flood_to_score(medium_or_high_pct):
    """Flood 0-10 from the share of a borough's postcodes at EA Medium or High.

    Linear to the `high` threshold and clamped there: at or above 10% of
    postcodes on the 1%-annual-chance line, the borough scores 0. Six boroughs
    are over that cut and Sefton reaches 31.4%, so the clamp is doing real work
    rather than guarding a theoretical case.

    The distribution is heavily skewed - median 1.08%, p75 1.65% - and that is
    the shape of the real risk, not an artefact to be corrected away. Most
    places genuinely are low-risk and a handful are not.
    """
    return max(0.0, min(10.0, 10.0 * (1.0 - medium_or_high_pct / _FLOOD_HIGH_PCT)))


def road_to_score(above_who_pct):
    """Road noise 0-10 from the share of postcodes at or above WHO 53 dB Lden.

    Higher is better, like every other component score and unlike the share it
    is derived from - see METHODOLOGY 11.0 on scale direction. No address over
    the WHO road-traffic guideline is 10; every address over it is 0.

    THE OBSERVED RANGE IS 0.44-6.77 AND THAT IS NOT A BUG. Measured across the
    73 boroughs that had road data on 2026-08-29: median 4.34, against air
    quality's 7.60 and flood's 8.92. The three components are anchored on their
    own published thresholds and are not expected to share a median - but this
    one sits low because WHO's 53 dB guideline is strict and most urban English
    addresses exceed it. A borough scoring 10 would be one where no address is
    over the guideline, which is reachable in a rural district and by none of
    the urban boroughs covered today. The top of the scale being empty is a
    true statement about urban England, not a scale that needs rebasing - and
    rebasing it onto the observed range is precisely the min-max trap
    METHODOLOGY 7.1 rejects, which would also re-scale every borough the next
    time a quieter district is added.
    """
    return max(0.0, min(10.0, 10.0 * (1.0 - above_who_pct / _ROAD_FULL_EXPOSURE_PCT)))


def env_weights_for(present):
    """Weights over exactly the environment inputs this borough has.

    Proportional redistribution, the same choice live_weights_for() makes and
    for the same reason: the declared ratio keeps its meaning. Returns an empty
    dict below the floor, meaning the caller must decline to score rather than
    invent a value.
    """
    present = [f for f in _ENV_FIELDS if f in present]
    if len(present) < _ENV_MIN_FIELDS:
        return {}
    total = sum(_ENV_WEIGHTS[f] for f in present)
    return {f: _ENV_WEIGHTS[f] / total for f in present}


def env_component_scores(bd):
    """Score each environment input the borough actually has.

    An absent input is ABSENT from the result, never present with a stand-in.
    Guarded on the CONTINUOUS field rather than the band: a borough can carry
    the band and not the ratio (New York keeps curated FEMA-derived flood bands
    and has no DEFRA anything), and scoring a band we did not derive would
    reintroduce exactly the editorial tier v3.5 removed.
    """
    scores = {}
    ratio = bd.get('airQualityWhoRatio')
    if isinstance(ratio, (int, float)):
        scores['airQuality'] = aq_to_score(ratio)
    road = bd.get('roadNoiseAboveWhoPct')
    if isinstance(road, (int, float)):
        scores['roadNoise'] = road_to_score(road)
    pct = bd.get('floodMediumOrHighPct')
    if isinstance(pct, (int, float)):
        scores['flood'] = flood_to_score(pct)
    # The same slots on the US scales (validate_us_fields: never both on one record). A withheld flood share
    # is None, so it is absent here and the two-input floor decides, exactly as for a UK gap.
    for slot, field in _ENV_US_FIELD_OF.items():
        if isinstance(bd.get(field), (int, float)):
            scores[slot] = us_anchored_to_score(bd[field], US_CALIFORNIA_ANCHORS[field])
    return scores


def get_env_score(bd):
    """Environment composite over the inputs that exist, or None if too few.

    None means the component cannot be published for this borough at all and
    callers must drop it and rescale - the way v3.3 dropped growth and v3.8
    drops live. New York returns None here: DEFRA and the EA are UK sources, so
    all five NYC boroughs have neither continuous field.
    """
    scores = env_component_scores(bd)
    weights = env_weights_for(scores)
    if not weights:
        return None
    return round_1dp(sum(scores[f] * w for f, w in weights.items()))


def env_single_input(bd):
    """True when `environment` rests on exactly ONE measured input of the three.

    LITERAL TO ITS NAME SINCE v4.0, AND THAT IS A CHANGE. It used to return
    `0 < len(scores) < len(_ENV_FIELDS)`, which at two declared fields could
    only mean one - so the name and the test agreed by arithmetic accident. Road
    noise made _ENV_FIELDS three, and the old expression would have fired for a
    two-of-three borough as well: a field called `single input` reporting True
    for a borough with two. The published key `environmentSingleInput` is part
    of the response contract, so the TEST was corrected to match the NAME rather
    than the other way round.

    THE RANKING FILTER IS environmentResolution, NOT THIS. Under _ENV_MIN_FIELDS
    = 2 a one-input borough is not published at all, so this flag no longer
    selects anything a ranking surface can see; it is a diagnostic. A caller
    ordering boroughs should exclude on `environmentResolution` starting
    'partial', which is the state that IS published and IS less certain, and
    which says so in its own text.

    Nothing in this repo reads either field, which is why the v3.9 note that
    "env_single_input() exists so ranking surfaces can exclude them" could not
    be used as the reason to keep the floor at one. A field only its producer
    reads is not a fix.
    """
    return len(env_component_scores(bd)) == 1


def env_resolution(bd):
    """How much of the environment composite is measured. Mirrors liveResolution.

    Served in context.environmentResolution, so a stale string here is a public
    claim about how a number was reached - the reason liveResolution's wording
    had to be corrected on 2026-08-09 when the behaviour it described changed.
    Counted from the same guard get_env_score() uses, so the two cannot disagree.
    """
    present = len(env_component_scores(bd))
    total = len(_ENV_FIELDS)
    if present == total:
        return 'measured'
    if present < _ENV_MIN_FIELDS:
        return (
            f'unavailable — {present}/{total} inputs measured, too few to publish; '
            'the component is omitted and its weight redistributed'
        )
    missing = total - present
    return (
        f'partial — {present}/{total} inputs measured; the '
        f'{"absent input is" if missing == 1 else "absent inputs are"} not '
        f'estimated, {"its" if missing == 1 else "their"} weight is '
        f'redistributed across the measured '
        f'{"one" if present == 1 else "ones"}. '
        'Not comparable with a fully-measured borough for ranking'
    )


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
# The values `aircraftQuietCoverage` can take on /v1/environment, in the order a
# reader would rank them. 'measured': DEFRA's raster has this postcode.
# 'city': estimated from the resolved city's own airports and flight paths.
# 'outside': the postcode resolved to no city Sky Score covers, so the estimate
# is the loudest of every geometry held - a weaker claim, and the one state the
# extension's panel-wide caveat is about. The key is absent when there is no
# aircraft figure at all. Declared as a tuple so a test can assert the handler
# never emits a fourth spelling.
AIRCRAFT_QUIET_COVERAGE = ('measured', 'city', 'outside')

_COVERAGE_NOTICES = {
    'raster': None,  # measured at this location — nothing to disclose
    # No city name in this sentence. It said "about 10% of London postcodes"
    # and was served verbatim for Manchester, Leeds and everywhere else - a
    # coverage figure for one city presented as this postcode's own. The share
    # genuinely differs per city (0.6-3.9% outside London), so naming a number
    # at all would need it measured per city; the claim that carries is simply
    # that this postcode is not in the measured set.
    'postcode': (
        'Aircraft noise here is estimated from distance to airports and '
        'flight-path geometry, not measured. DEFRA publishes contours for '
        'part of this area and this postcode falls outside them.'
    ),
    # OUTSIDE EVERY COVERED CITY (2026-09-07, audit I4). The 'postcode' notice
    # above says "DEFRA publishes contours for part of this area", which is a
    # claim about a city we cover. For a coordinate in no covered city it was
    # served beside `aircraftQuietBasis` reading "outside every city Sky Score
    # covers" - one payload asserting both. Measured live at TR1 1DT (Truro).
    #
    # This is 68% of live UK postcodes by the file's own count, and it is the
    # surface the public browser extension renders. The previous fix to this
    # string removed the CITY NAME and left the COVERAGE CLAIM, which is the
    # half that was wrong here.
    'postcode-uncovered': (
        'Aircraft noise here is estimated from distance to the nearest airports '
        'we hold and from flight-path geometry, not measured. This location is '
        'outside every city Sky Score covers, so no measured contour applies.'
    ),
    # New York gets its own sentence: the one above names DEFRA, a UK
    # regulator with no product covering any US city - the same city-blind
    # provenance shape as the 2026-07 NYC/OGL incident, one field over.
    'postcode-nyc': (
        'Aircraft noise here is estimated from the FAA routes of JFK, '
        'LaGuardia, Newark and Teterboro, fitted to the airports\' noise '
        'monitors, not measured at this address. No published Lden survey '
        'covers New York.'
    ),
    'postcode-bayarea': (
        'Aircraft noise here is estimated from the FAA routes of San Francisco, '
        'Oakland and San Jose airports, fitted to the airports\' noise monitors, '
        'not measured at this address. No published Lden survey covers the Bay Area.'
    ),
    'borough': (
        'Aircraft noise here is a borough-wide average, not a figure for this '
        'address. Expect real variation of 10-15 dB within a borough.'
    ),
    # A CITY WHOSE AIRPORT DEFRA DOES NOT MAP (2026-09-13 audit, I3). The
    # 'postcode' notice above says "DEFRA publishes contours for part of this
    # area" - true of the ten cities with a Round 4 airport and false of
    # Teesside (MME) and Cardiff (CWL), whose airports sit below the size at
    # which the mapping duty applies; data/aircraft-footprint.json records
    # both as unmapped and the near-field floor uses a disc there for that
    # reason. 38,195 live postcodes were told a contour existed nearby.
    'postcode-unmapped': (
        'Aircraft noise here is estimated from distance to this area\'s airport '
        'and flight-path geometry, not measured. DEFRA publishes no noise '
        'contours for that airport, so no measured value exists for any '
        'postcode in this area.'
    ),
    # A CITY WITH NO AIRPORT (South Yorkshire: Doncaster Sheffield closed to
    # commercial flights in 2022). /v1/environment served the 'postcode'
    # sentence - "estimated from distance to airports ... DEFRA publishes
    # contours for part of this area" - beside a payload carrying NO aircraft
    # key at all, because there is nothing to estimate from.
    'postcode-no-airport': (
        'No commercial airport operates in this city region, so aircraft noise '
        'is not estimated for this postcode; the score carries the borough-wide '
        'band instead.'
    ),
}


def _defra_contour_status(city):
    """'mapped', 'unmapped' or 'none': does DEFRA Round 4 map any airport in
    `city`? Derived from the geometry registry against AIRPORT_NOISE_SCALE,
    whose keys are exactly the twelve airports DEFRA published a footprint
    for - one holder, so a city added with an unmapped airport describes
    itself correctly without anyone remembering to say so."""
    codes = [a.get('code') for a in (CITY_GEOMETRY.get(city) or {}).get('airports', [])]
    if not codes:
        return 'none'
    return 'mapped' if any(c in AIRPORT_NOISE_SCALE for c in codes) else 'unmapped'


def _postcode_coverage_notice(city):
    """The estimate notice that is TRUE for this city's DEFRA situation."""
    if city and not uk_shape(city):
        # A US city's own sentence (DEFRA has no remit there), by registry rather than by name, so a US city
        # added without one raises here rather than borrowing a UK sentence.
        return _COVERAGE_NOTICES[f'postcode-{city}']
    if not city:
        return _COVERAGE_NOTICES['postcode-uncovered']
    status = _defra_contour_status(city)
    if status == 'none':
        return _COVERAGE_NOTICES['postcode-no-airport']
    if status == 'unmapped':
        return _COVERAGE_NOTICES['postcode-unmapped']
    return _COVERAGE_NOTICES['postcode']

def _road_absence_notice(city):
    """The sentence that is TRUE when a postcode has no road-noise row.

    One holder, derived (audit M12, 2026-09-14). Until then every absence got
    'has not been measured for this postcode, or is still being loaded' -
    false for Cardiff, where DEFRA's Round 4 road map is an ENGLAND-ONLY
    coverage (`NO_ROAD_COVERAGE` in build_borough_bands.py) and the load will
    never happen; false outside the eleven mosaics, where the map exists and
    Sky Score simply does not hold it; and stale inside them, where "still
    being loaded" described the 10 Sep run. Whether a city HAS road coverage
    is read off its borough records through _env_inputs_present - the same
    holder the provenance reads - so no city is named here, and New York
    falls out of the same branch as Cardiff without being special-cased.
    """
    if not city:
        return (
            "Sky Score holds DEFRA's road-noise map for the city-regions it "
            'scores, and this postcode is outside all of them. No figure is '
            'shown rather than an assumed one.'
        )
    name = CITIES[city]['name']
    if 'roadNoise' not in _env_inputs_present(city):
        return (
            f"Road noise is not mapped for {name}: DEFRA's Round 4 road-noise "
            'map is an England-only coverage and Sky Score holds no equivalent '
            'here. No figure is shown rather than an assumed one.'
        )
    return (
        "Road noise has not been loaded for this postcode. Sky Score holds DEFRA's "
        f'road map for {name}, so this is a gap in the load - a postcode newer than '
        'it, or ground the map leaves unmapped - not a measurement. No figure is '
        'shown rather than an assumed one.'
    )


# THE TEXT MUST MATCH WHAT THE ENGINE DOES, and for a year it did not.
# It said the component was "a neutral placeholder" - true before v3.8, which
# stopped defaulting and started OMITTING an uncomputable component and
# redistributing its weight. `live_resolution` has said so in its own returned
# sentence since 2026-08-09; this notice, forty lines away, was not updated.
# Corrected 2026-09-11 (audit I9) at the same time as the branch that emits it,
# which could not fire at all - see build_coverage.
_LIVE_UNAVAILABLE_NOTICE = (
    'Liveability inputs are unavailable for this area, so that component is '
    'omitted from the score and its weight is redistributed across the '
    'components that were measured. It is not a placeholder value, and the '
    'score is not directly comparable with a fully-measured borough.'
)

# Environment's sibling. Fires for the 9 boroughs below the two-input floor -
# New York's 5 (no UK coverage at all) and Cardiff's 4 (England-only road and
# flood coverages). Added 2026-09-11 with the `env` coverage block: the
# component had been omitted from the score and from `coverage` alike, so the
# one object a caller is told to read for limitations said nothing about it.
_ENV_UNAVAILABLE_NOTICE = (
    'Environment inputs are unavailable for this area, so that component is '
    'omitted from the score and its weight is redistributed across the '
    'components that were measured. It is not a placeholder value, and the '
    'score is not directly comparable with a fully-measured borough.'
)


def build_environment(noise_row, postcode_clean=''):
    """Measured environmental readings for a postcode, omitting what is absent.

    Returns a dict to be spliced into `context`. An absent measurement means an
    ABSENT KEY — never null, never a default. A numeric field carrying a
    placeholder is precisely how "we did not measure here" becomes "we measured
    here and it was fine", which is the defect that quarantined the aircraft
    raster and the one this codebase has repeated most often.

    The per-postcode road Lden here is reported and is not itself scored.
    Road noise DOES score since methodology v4.0 - at BOROUGH level, as the
    share of postcodes over WHO's 53 dB Lden, 0.35 of `environment` - so this
    docstring's old "reported, not scored" (audit M11) was true of the
    dataset only until 2026-08-29. Folding the postcode-level reading into the
    weighted total as well would change every score the API returns, which
    METHODOLOGY §7 treats as a version bump with 14 days' notice to integrators
    — a product decision, not a side effect of holding a finer measurement.
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
    else:
        # Surveyed and under the lowest mapped level. A BOUND, under its own
        # key - a reader summing or charting roadNoiseLdenDb must not find a
        # 40 here and plot it as a reading. The WHO reference and the source
        # travel with it for the same reason they travel with the figure.
        road_below = road_below_from_row(noise_row, postcode_clean)
        if road_below is not None:
            env['roadNoiseBelowDb'] = round(road_below, 1)
            env['roadNoiseWhoGuidelineDb'] = 53
            env['roadNoiseSource'] = (
                'DEFRA Strategic Noise Mapping Round 4, road Lden. Surveyed; '
                'below the lowest level the map records. Published 2022, maps 2021.'
            )

    # Air quality: DEFRA PCM background maps, annual mean, 2024, 1 km grid.
    #
    # NOT the Daily Air Quality Index. DAQI is a daily index at monitoring
    # stations — sparse, and as much about today's weather as about the
    # address. (This comment said "that plannedComponents still names" until
    # 2026-08-29; the airQuality entry it named left plannedComponents at v3.9,
    # three days earlier, taking the wrong source claim with it.) Annual mean concentration on a
    # modelled grid is the measure a property decision wants, and the one the
    # WHO guidelines below are expressed against.
    #
    # The guideline is carried alongside the value because a bare "13.3" means
    # nothing to a reader. WHO 2021: NO2 10 ug/m3, PM2.5 5 ug/m3 annual mean.
    # Stating the reference is not editorialising — omitting it would leave the
    # number to be interpreted against whatever the reader assumes.
    # Range-guarded through the same single guard as the two Lden fields.
    # The bare `>= 0` this replaces was a floor alone, so +3.4e38 - the
    # positive GeoTIFF nodata shape both Lden fields are guarded against -
    # was publishable as an annual-mean concentration.
    no2 = no2_from_row(noise_row, postcode_clean)
    if no2 is not None:
        env['no2AnnualMeanUgm3'] = round(no2, 1)
        env['no2WhoGuidelineUgm3'] = 10

    pm25 = pm25_from_row(noise_row, postcode_clean)
    if pm25 is not None:
        env['pm25AnnualMeanUgm3'] = round(pm25, 1)
        env['pm25WhoGuidelineUgm3'] = 5

    # Guarded values, so a row holding only rejected sentinels credits no
    # source - attribution with no readings under it is the inverse of the
    # absence-as-measurement defect.
    if no2 is not None or pm25 is not None:
        env['airQualitySource'] = (
            'DEFRA background pollution maps (PCM), annual mean 2024, 1 km grid'
        )

    return env


def build_coverage(quiet_source, live_source, env_source, city=None, withheld=None, growth_not_scored=None):
    """Per-component coverage statements plus any plain-English notices.

    Returned on every response, not only degraded ones: a field that appears
    only when something is wrong trains readers to ignore its absence, and
    'measured' is itself worth stating. `notices` is empty when everything is
    measured at the queried location. `withheld` ({input: reason}) adds the
    reason a borough's record gives for each input it withholds, so the one
    object a caller may not filter away says WHY a component is thin.
    """
    notices = []

    # The 'postcode' (geometry) tier's notice depends on whether DEFRA maps
    # this city's airport at all; every other tier's notice is fixed.
    quiet_notice = (
        _postcode_coverage_notice(city) if quiet_source == 'postcode'
        else _COVERAGE_NOTICES.get(quiet_source)
    )
    if quiet_notice:
        notices.append(quiet_notice)

    # 'unavailable' is live_resolution's way of saying too few inputs were
    # measured to publish the component, which is then omitted and its weight
    # redistributed - the fix for a uniform Greater Manchester 5.0 reading as a
    # finding rather than a gap.
    #
    # STARTSWITH, NOT EQUALITY (2026-09-11, audit I9). This tested
    # `live_source == 'unavailable'`, and live_resolution has returned a full
    # SENTENCE - 'unavailable - n/4 inputs measured, too few to publish; ...' -
    # since the 2026-08-09 wording change that the function's own comment
    # records. So the bare token stopped being returned that day and this
    # branch has fired ZERO times since, across all 99 boroughs. Two tests
    # pinned the dead branch by calling build_coverage with the literal
    # 'unavailable', so they passed green on a path production cannot enter;
    # they pass the real sentence now.
    if live_source.startswith('unavailable'):
        notices.append(_LIVE_UNAVAILABLE_NOTICE)
    if env_source.startswith('unavailable'):
        notices.append(_ENV_UNAVAILABLE_NOTICE)
    for name, reason in (withheld or {}).items():
        notices.append(f'{_INPUT_LABEL[name]} is withheld here: {reason}.')
    if growth_not_scored:
        # On every response for such a city, whatever the persona weights it: the component does not exist.
        notices.append(f'Growth is not scored here: {growth_not_scored}.')

    return {
        'quiet': {
            'basis': quiet_source,
            'measuredAtLocation': quiet_source == 'raster',
        },
        'live': {
            'basis': live_source,
            'measuredAtLocation': live_source == 'measured',
        },
        # ENV WAS ABSENT FROM THIS OBJECT ENTIRELY until 2026-09-11 (audit I8),
        # although `environment` has been a scored component since v3.9 at
        # 0.14-0.18 of every persona and is DROPPED for 9 of 99 boroughs. A
        # Cardiff response published context.environmentResolution saying
        # '1/3 inputs measured' while `coverage` - the one object
        # filter_response refuses to let a caller strip, precisely so a
        # limitation cannot be filtered away, and which terms.html s6 obliges
        # integrators to carry through to their own users - said nothing about
        # it. Two of three scored components were described and the third was
        # not.
        'env': {
            'basis': env_source,
            'measuredAtLocation': env_source == 'measured',
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
    # Crime is the same shape and only the SCHOOLS half was ever implemented
    # (audit I28). The docstring above already names the City of London as the
    # borough where BOTH credits were wrong, and the code below fixed one of
    # them; `crimeEstimated` was published in the record, read by
    # `_live_sources_line` for the `sources` array, and read by NOTHING here.
    #
    # The consequence was a response contradicting itself: `sources` said "crime
    # rate is a Sky Score estimate ... must not be attributed to them" while
    # `liveResolution` in the same payload said `measured`, and the estimate
    # carried its full 30% of a live headline score - about 0.9 points.
    #
    # An estimate is not a measurement even when it is a good estimate. The
    # figure still SCORES, exactly as an unmeasured input does not; what changes
    # is that the response stops claiming ONS measured it.
    def _slot_present(f):
        if f == 'crimeRate':
            if bd.get('crimePer1000Us') is not None:  # the US slot: a DOJ count, never an estimate
                return True
            return bd.get('crimeRate') is not None and not bd.get('crimeEstimated')
        if f != 'schools':
            return bd.get(f) is not None
        if english:
            return bd.get('p8') is not None
        return bd.get('schools') is not None

    present = sum(1 for f in _LIVE_FIELDS if _slot_present(f))
    total = len(_LIVE_FIELDS)

    # ESTIMATED IS NOT ABSENT, and the two must not share a sentence.
    #
    # `crimeEstimated` demotes an input out of `present` (audit I28), but the
    # figure is still there and still SCORES - get_live_score redistributes on
    # value presence, not on this test. So the "partial" wording below, which
    # says the missing inputs "are not estimated" and that "their weight is
    # redistributed", would be false in both clauses for the City of London: the
    # input IS an estimate, and its 30% is not redistributed anywhere.
    #
    # Saying "2/4 measured" and stopping there would be the safer-sounding
    # error - it understates, but it also tells a customer a number was dropped
    # when it was used. Name the estimate instead.
    estimated = [
        f
        for f in _LIVE_FIELDS
        if not _slot_present(f) and bd.get(f) is not None and bd.get('crimeEstimated')
        and f == 'crimeRate'
    ]
    if present == total:
        return 'measured'
    if estimated and present + len(estimated) == total:
        return (
            f'partial — {present}/{total} inputs measured; the crime rate is a Sky Score '
            'estimate, not an ONS measurement, and it carries its full weight'
        )
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
    if estimated:
        return (
            f'partial — {present}/{total} inputs measured; the crime rate is a Sky Score '
            'estimate carrying its full weight, and the remaining absent inputs have '
            'theirs redistributed'
        )
    return (
        f'partial — {present}/{total} inputs measured; the absent inputs are not '
        'estimated, their weight is redistributed across the measured ones'
    )


def _percentile(values, q):
    """Linear-interpolated percentile, matching numpy's default method.

    Written out rather than imported: this Lambda has no numpy, and
    `statistics.quantiles` cuts a distribution into n equal groups rather than
    answering "the value at q", which is a different question and returns
    different numbers at the tails - exactly where this is used.
    """
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = (len(ordered) - 1) * q
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    return float(ordered[low] + (ordered[high] - ordered[low]) * (pos - low))


# Cache for the CURRENT-vintage national bounds, which are static per process.
# An override (a previous vintage) recomputes, because its pool is different.
_NATIONAL_AFFORD_BOUNDS = {}
_NATIONAL_GROWTH_BOUNDS = {}


def pool_of(city):
    """The pool a city's affordability and growth anchors are taken over.

    DECISION 2 of the Bay Area's release 2 (Bill, 2026-10-16): one pool per US METRO, not one per
    currency, because adding the Bay Area to the dollar pool as it stood would put the p95 anchor on
    the "$2M+" top code and MOVE New York's published affordability (Queens 6.5 -> 9.9). A city takes
    its own pool by naming it in CITIES (`'pool'`); every city without one, or with `'pool': None`,
    pools by its currency, which is every city on 2026-10-18, so introducing the key moved no score
    (816 of 816 identical). `or`, not a .get default, so that a None reads as the currency exactly as
    the site's `poolOf` reads `pool: null` (its key-parity gate puts `pool` on EVERY city once one has it).
    """
    return CITIES[city].get('pool') or CITIES[city]['currency']


def national_trend_pool(city, boroughs, pool):
    """Every borough in the pool (pool_of) with the trend growth is SCORED on,
    as (label, trend) pairs - v5.2's growth cohort.

    `boroughs` stands in for `city`'s own slice, exactly as in
    national_price_bounds, so a previous-vintage comparison anchors on a pool
    with that slice at the previous vintage. Labels outside `city` carry the
    city's name - "Trafford (Greater Manchester)" - because a yardstick a
    London response names may now be a Manchester borough, and a bare
    "Trafford" in a London explanation reads as a borough the reader cannot
    find on the London map.
    """
    members = []
    for other, cfg in CITIES.items():
        if pool_of(other) != pool:
            continue
        source = boroughs if other == city else cfg['boroughs']
        for name, bd in source.items():
            label = name if other == city else f"{name} ({cfg['name']})"
            members.append((label, scored_trend(bd)))
    return members


def _pool_size(pool):
    """How many boroughs share `pool` - the cohort size v5.2 growth names."""
    return sum(len(cfg['boroughs']) for name, cfg in CITIES.items() if pool_of(name) == pool)


def national_trend_bounds(city, boroughs, pool):
    """(max_trend, min_trend) across the whole pool (pool_of) - v5.2.

    WHY THE COHORT WENT NATIONAL (2026-09-16). Until v5.2 each city's growth
    was dual-anchored against ITS OWN fastest riser and steepest faller, so by
    construction one borough per rising city scored 10.0 and one per falling
    city 0.0 every month - 22 of 94 boroughs on a rail whatever their trend.
    Replayed over 24 months of HPI (2024-08 .. 2026-07, all 94 sterling
    boroughs): the mean month-on-month growth change was 1.44 points, 8.2% of
    transitions moved 5 or more, and the mean within-city spread was 8.79 of
    10. The July 2026 roll made it visible: Hartlepool's trend went +0.8% ->
    +5.5% and its growth 0.0 -> 10.0 because Teesside's leader changed hands;
    Newport 8.5 -> 0.0 for the same reason in Cardiff's four. Pooling the 94
    real trends halves the churn (0.76 mean, 0.2% moving 5+) and leaves one
    borough at each rail. Smoothing the input instead (a 3-month mean) was
    measured and rejected: it barely touches the churn (0.95) because the
    per-city rails stay, and it would publish a trend that no longer equals
    HMLR's own Annual_Change, which is what an integrator verifies against.
    Same argument as v5.0's affordability, same shape, same pool (pool_of):
    a narrow cohort manufactures spread it has not measured.

    The 5.0 = flat anchor is unchanged and absolute; only the two tails'
    extremes moved from the city to the pool. New York's USD pool is still its
    own five boroughs, so nothing changes there.
    """
    override = boroughs is not CITIES[city]['boroughs']
    if not override and pool in _NATIONAL_GROWTH_BOUNDS:
        return _NATIONAL_GROWTH_BOUNDS[pool]
    trends = [t for _, t in national_trend_pool(city, boroughs, pool)]
    bounds = (max(trends), min(trends))
    if not override:
        _NATIONAL_GROWTH_BOUNDS[pool] = bounds
    return bounds


def national_price_bounds(city, boroughs, pool):
    """The 5th and 95th percentile borough median price across the whole
    pool (pool_of) - v5.0's affordability anchor.

    THE POOL IS NEVER GLOBAL: per pool_of, which is the currency unless a city names its own (one per
    US metro, decision 2). New York's medians are curated USD
    figures, not HM Land Registry sterling, so pooling them with the UK would be
    a category error rather than a wider cohort. In practice that makes the USD
    pool exactly NYC's five boroughs, and the methodology says so instead of
    implying a national US comparison the data cannot support.

    `boroughs` stands in for `city`'s own slice, so scoring a previous vintage
    anchors on a pool with that slice at the previous vintage. That pool is an
    APPROXIMATION of the previous-vintage pool, not a reproduction of it
    (audit M8, corrected 2026-09-14): only London holds a real previous dataset
    - `previous_dataset` returns the CURRENT set for every other city - so the
    other 61 sterling boroughs enter at today's prices, and the June 2026 roll
    moved 54 of those 61. Measured effect on the day it was written down: zero,
    because p5 and p95 both land on boroughs the roll did not move. Latent
    rather than absent - a roll that moves a percentile borough will make
    `previousScore` for London drift by whatever the anchor moved, and the
    honest fix is a previous-vintage price for every city, not this docstring.
    """
    override = boroughs is not CITIES[city]['boroughs']
    if not override and pool in _NATIONAL_AFFORD_BOUNDS:
        return _NATIONAL_AFFORD_BOUNDS[pool]
    prices = []
    for other, cfg in CITIES.items():
        if pool_of(other) != pool:
            continue
        source = boroughs if other == city else cfg['boroughs']
        prices.extend(b['avgPrice'] for b in source.values())
    bounds = (_percentile(prices, 0.05), _percentile(prices, 0.95))
    if not override:
        _NATIONAL_AFFORD_BOUNDS[pool] = bounds
    return bounds


def afford_score(price, p5, p95):
    """Methodology v5.0: affordability on a LOG scale between national p5/p95.

    Cheaper is higher, 10.0 at or below p5 and 0.0 at or above p95.

    WHY THIS REPLACED WITHIN-CITY MIN-MAX (2026-09-09). Until v5.0 every city
    was scaled against its own cohort, so the cheapest borough of any city
    scored 10.0 and the priciest 0.0 whatever the money. Measured across the
    4,371 cross-city borough pairs in the GBP pool, **1,619 of them were
    inverted** - a cheaper borough scoring LOWER than a dearer one. The headline
    case: Barking and Dagenham published 10.0 at GBP 371,030 while
    Stockton-on-Tees published 0.0 at GBP 170,923, 2.2x cheaper. A national
    anchor takes those inversions to zero.

    WHY LOG, AND WHY NOT THE LINEAR p10/p90 THAT WAS FIRST PROPOSED. UK borough
    medians are strongly right-skewed - min 130k, median 273k, p90 610k, max
    1.25M - and a linear scale over that range piles boroughs at both ends.
    Measured, linear p10/p90 flattened FOUR of thirteen cities to under one
    point of internal spread (Teesside to exactly 0.0, all five boroughs on
    10.0) and pinned 22 of 99 boroughs at a rail. Affordability is 27% of the
    composite, so that would stop it separating boroughs inside a city at all -
    the dominant consumer use case. Log p5/p95 flattens ONE city, keeps the best
    mean internal spread of the four candidates tested (3.1 points), and still
    clamps at percentiles so a single outlier cannot set the scale.

    A NARROW COHORT GENUINELY SHOULD COMPRESS. Teesside's five boroughs really
    do sit inside 171k-200k, and the codebase has already accepted this argument
    once: Leicester's cohort was widened because "min-max over a narrow cohort
    manufactures spread it has not measured". The within-city signal is not
    lost - it is published as an explicit `priceRankInCity` rather than being
    smuggled into a score that also claims to mean something nationally.

    NOT a price-to-earnings ratio, which is the standard UK affordability
    measure and the obvious reach. METHODOLOGY 10 commits publicly that income
    and wealth distributions of residents are never inputs, and that section
    exists because the customer set includes Sharia-compliant home-finance
    providers, where indirect discrimination is a live compliance question.
    """
    if p95 <= p5 or price <= 0:
        return 5.0
    span = math.log(p95) - math.log(p5)
    return max(0.0, min(1.0, (math.log(p95) - math.log(price)) / span)) * 10


def price_rank_in_city(price, boroughs):
    """This borough's price rank within its own city, 1 = cheapest.

    The within-city signal v5.0 took out of the affordability SCORE, published
    as what it is. Ties share the better (lower) rank, so two boroughs at the
    same median cannot be ordered by an accident of dict iteration.
    """
    prices = sorted(b['avgPrice'] for b in boroughs.values())
    return {'rank': prices.index(price) + 1, 'of': len(prices)}


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

    # v5.0: NATIONAL log anchor, not the city cohort. See afford_score() for the
    # 1,619 inverted cross-city pairs this replaced, and for why the linear
    # p10/p90 first proposed was rejected on measurement.
    p5, p95 = national_price_bounds(city, boroughs, pool_of(city))
    afford = afford_score(bd['avgPrice'], p5, p95)

    # v5.1: scored on the REAL-terms trend where the city has one (every
    # sterling city), nominal where it does not (New York). The extremes are
    # taken over the same quantity, so the 5.0 anchor means "held its value
    # against inflation" and the tails are scaled against the real fastest
    # riser and steepest faller.
    # v5.2: those extremes are the CURRENCY POOL's, not the city's - see
    # national_trend_bounds() for the 24-month replay that decided it.
    # Methodology v3.4: dual-anchor — 0% growth sits at 5.0, each tail scaled
    # to its own extreme. See growth_score() for why the v3.2 single-anchor
    # formula collapsed 14 of 33 boroughs onto one value.
    # A city declaring `growthNotScored` (the Bay Area) has no growth component at all: dropped and its weight
    # redistributed exactly as `live` and `env` are below their floors, never scored as 5.0.
    if CITIES[city].get('growthNotScored'):
        growth = None
    else:
        max_trend, min_trend = national_trend_bounds(city, boroughs, pool_of(city))
        growth = growth_score(scored_trend(bd), max_trend, min_trend)

    live = get_live_score(bd, english=uk_shape(city))

    # `live` is None when fewer than two of its four inputs exist, so the
    # component would say nothing about this place. Drop it and rescale the
    # remaining weights in proportion - the same move v3.3 made when it dropped
    # `growth` for non-investor personas. The alternative it replaced, a 5.0
    # placeholder, sat below every real London live score and so penalised a
    # city for the gap - which is what made Greater Manchester all-or-nothing.
    env = get_env_score(bd)

    # v3.9 generalises this from one droppable component to two. `env` is None
    # for every borough with neither continuous field - all five NYC boroughs
    # (DEFRA and the EA are UK sources) and the eight in Cardiff and Nottingham,
    # which are backend-only and so have no borough-extra entry to derive from.
    #
    # `weights.get(name, 0.0)` and NOT `weights[name]`. METHODOLOGY 5.3 lets a
    # caller send its own weight set, and every custom set written before today
    # names four components. Indexing would 500 those callers on the first
    # request after this deploys; defaulting to 0.0 gives them EXACTLY their
    # previous behaviour - env contributes nothing and the four they did send
    # rescale to 1.0 - so the change is additive for them until they opt in.
    parts = {'quiet': quiet, 'afford': afford}
    effective = {k: weights.get(k, 0.0) for k in parts}
    for name, value in (('growth', growth), ('live', live), ('env', env)):
        if value is not None:
            parts[name] = value
            effective[name] = weights.get(name, 0.0)

    # Rescale over whatever survived, unconditionally. With every component
    # present this is a no-op (the persona rows sum to 1.00), so it replaces the
    # previous if/else without changing any score it used to produce - and it
    # cannot go stale the way a per-component branch does when a third droppable
    # component arrives.
    scale = sum(effective.values())
    if scale > 0:
        effective = {k: v / scale for k, v in effective.items()}

    total = sum(parts[k] * effective[k] for k in parts)

    currency_field = 'avgPriceUsd' if CITIES[city]['currency'] == 'USD' else 'avgPriceGbp'

    return {
        'score': round_1dp(total),
        # THE APPLIED WEIGHTS, NOT THE PERSONA'S NOMINAL ONES (2026-09-09).
        #
        # These are `effective` - what actually multiplied the components above -
        # so `sum(components x weights)` reproduces `score`. Until today the
        # response published the persona's NOMINAL row while the engine scored
        # with this rescaled one, so wherever a component was dropped the
        # published arithmetic did not reach the published number: Brooklyn
        # `balanced` summed to 3.9 against a published 4.5, Cardiff 5.4 against
        # 6.3. Measured across all 792 persona x borough combinations, the worst
        # gap was **1.518 points**.
        #
        # NOT a second `weightsApplied` field beside a wrong `weights`. That is
        # the `lineStatusAvailable` shape this repo has hit four times - an
        # optional correct field leaves the naive computation wrong for everyone
        # who does not know to switch, and "consumers can upgrade to read it"
        # makes the second half optional, so it never happens. The persona's
        # NOMINAL row stays in the OpenAPI spec, where it is a definition rather
        # than a reproduction aid.
        #
        # ROUNDED TO 6dp FOR PUBLICATION ONLY - `total` above uses the unrounded
        # values. 6dp is not a precision compromise: measured, the residual is
        # identical at 3dp and 6dp (0.069), because what remains is NOT weight
        # precision but COMPONENT rounding - see the note on the gate in
        # test_score.py. It also restores the persona's exact 2dp figures for a
        # complete set, whose division by a total of 0.9999999999999999 would
        # otherwise publish 0.32000000000000006.
        'weights': {k: round(v, 6) for k, v in effective.items()},
        # `live` is OMITTED, not null and not defaulted, when it could not be
        # computed - the same convention build_environment uses below and for
        # the same reason: a placeholder in a numeric field is how "not
        # measured" becomes "measured as fine". liveResolution says why.
        'components': {
            'quiet': round_1dp(quiet),
            'afford': round_1dp(afford),
            **({'growth': round_1dp(growth)} if growth is not None else {}),
            **({'live': round_1dp(live)} if live is not None else {}),
            # `env` follows `live` exactly: omitted rather than null when the
            # borough has neither input, so a consumer cannot read a gap as a
            # reading. environmentResolution says which it is.
            **({'env': round_1dp(env)} if env is not None else {}),
        },
        'context': {
            **_price_context(bd, currency_field),
            'priceTrendPct': bd['trend'],
            # v5.1. The trend growth was SCORED on and the inflation behind it,
            # present only where the deflation happened (sterling cities), so a
            # consumer can reproduce growth_score() from the response and can
            # tell a real-terms score from a nominal one by the key's presence.
            **({'priceTrendRealPct': bd['trendReal'],
                'inflationPct': CPIH_12M_PCT[SNAPSHOT_VINTAGE]} if 'trendReal' in bd else {}),
            # 'not scored' where the city declares growthNotScored: priceTrendPct stays, as a fact, named for the
            # county it belongs to (LICENSING.md: FHFA's county trend is never shown as a city's own).
            'growthBasis': ('not scored' if growth is None else 'real' if 'trendReal' in bd else 'nominal'),
            **({'priceTrendArea': f"{bd['county']} County, FHFA's annual change (no city series is published)"}
               if growth is None and bd.get('county') else {}),
            # v5.0. The within-city signal that affordability used to carry, now
            # published as what it IS rather than smuggled into a score that
            # also claims to mean something nationally. `rank` is 1 for the
            # cheapest borough of the city; `of` is the cohort size.
            #
            # ONE nested object, not two flat keys, deliberately: a pair that
            # can be updated independently is a pair that drifts, and this repo
            # has lost days to exactly that. They are read together or not at
            # all.
            'priceRankInCity': price_rank_in_city(bd['avgPrice'], boroughs),
            # v5.2: the same move for growth. The score is against the currency
            # pool; the within-city standing is published beside it, as one
            # nested object for the same reason as the line above. `rank` is 1
            # for the fastest real-terms riser of the city (growth_ranks).
            **({'growthRankInCity': {
                'rank': growth_ranks(boroughs)[borough_name],
                'of': len(boroughs),
            }} if growth is not None else {}),
            'noiseImpactBand': bd['impact'],
            'quietResolution': quiet_source,
            'liveResolution': live_resolution(bd, english=uk_shape(city)),
            'environmentResolution': env_resolution(bd),
            # A scoring input this borough's record WITHHOLDS, keyed by input, with the reason its reader
            # recorded (a Bay Area city FEMA has not mapped, one policed by the county sheriff). Absent, not
            # empty, where nothing is withheld, which is every UK and New York record.
            **({'inputsWithheld': _inputs_withheld(bd)} if bd.get('withheld') else {}),
            # Beside the figure, never in it: the rate and the score are unchanged (decision 4).
            **({'crimeNote': _CRIME_FEW_RESIDENTS_NOTE} if bd.get('crimeFewResidents') else {}),
            # True when `env` rests on one measured input rather than two, so a
            # ranking surface can exclude the borough from "best environment"
            # comparisons. Disclosure alone is not enough for an ORDERED list: a
            # reader still sees the number at the top whatever sits beside it,
            # and the absent input is not missing at random - the 13 affected
            # boroughs are coastal Teesside and inland Leicester, where flood is
            # plausibly the input they would score worst on.
            'environmentSingleInput': env_single_input(bd),
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
            quiet_source,
            live_resolution(bd, english=uk_shape(city)),
            env_resolution(bd),
            city=city,
            withheld=_inputs_withheld(bd),
            growth_not_scored=CITIES[city].get('growthNotScored'),
        ),
    }


def _price_context(bd, currency_field):
    """The price fields of `context`. A top-coded price (US_PRICE_TOP_CODE) is published as the floor it is,
    under its own key, never as a price: the record's 2,000,001 is an encoding, and a reader charting
    avgPriceUsd must not find it there (Bill, 2026-10-17: show "$2M+", never the number). `priceTopCoded` is on
    every record of a city that carries the flag (the Bay Area) and on no other."""
    if bd.get('priceTopCoded'):
        out = {f'{currency_field}AtLeast': US_PRICE_TOP_CODE}
    else:
        out = {currency_field: bd['avgPrice']}
    if 'priceTopCoded' in bd:
        out['priceTopCoded'] = bool(bd['priceTopCoded'])
    return out


def _inputs_withheld(bd):
    """{scoring input: reason} for what this record withholds; {} for none."""
    return {_WITHHELD_INPUT_OF[f]: reason for f, reason in (bd.get('withheld') or {}).items()}


_CRIME_FEW_RESIDENTS_NOTE = (
    'Few residents: crime is counted where it happens and divided by the people who live here, and this '
    "city's shops, offices or cemeteries draw far more people by day than live in it, so its rate per "
    'resident reads high. The rate and the score are unchanged by this note.'
)


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
        logger.warning('DDB postcode lookup failed for %s: %s', _log_district(clean), exc)
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
    mark_local_postcode_served()

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
        logger.warning('postcodes.io lookup failed for %s: %s', _log_district(clean), exc)
        return None
    except json.JSONDecodeError as exc:
        logger.warning('postcodes.io returned non-JSON for %s: %s', _log_district(clean), exc)
        return None
    if payload.get('status') != 200:
        return None
    return payload.get('result')


_reverse_cache_get, _reverse_cache_put = _make_lru(1024)


def reverse_geocode(lat, lon):
    """Nearest UK location to a coordinate, or None.

    Returns a dict of `postcode`, `ladCode` and `adminDistrict` — the last two
    so the caller can derive a city. It returned the bare postcode string until
    2026-08-21; see derive_city for what that cost.

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
        logger.warning('postcodes.io reverse lookup failed for %s: %s', _log_coarse(lat, lon), exc)
        return None
    except json.JSONDecodeError as exc:
        logger.warning('postcodes.io returned non-JSON for %s: %s', _log_coarse(lat, lon), exc)
        return None

    # A coordinate in the sea returns status 200 with result: null. That is a
    # legitimate "no postcode here", not an error, and must not be cached as
    # one — _make_lru does not cache negatives, so returning None is enough.
    results = payload.get('result') or []
    if not results:
        return None

    row = results[0] or {}
    postcode = row.get('postcode')
    if not postcode:
        return None

    # The LAD travels with the postcode because it arrives in the SAME payload.
    # postcodes.io has always returned codes.admin_district here; this function
    # discarded it and returned the string alone, so the only caller had nothing
    # to derive a city from and hardcoded 'london'. Keeping it costs no request.
    location = {
        'postcode': postcode,
        'ladCode': (row.get('codes') or {}).get('admin_district'),
        'adminDistrict': row.get('admin_district'),
    }
    _reverse_cache_put(key, location)
    return location


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
def _norm_borough_key(name):
    """Loose key for matching a resolver's borough spelling to ours."""
    s = (name or '').lower().replace('.', '').replace('-', ' ')
    # ONS inverts the qualifier and postcodes.io passes it through, so the same
    # authority arrives as "City of Bristol" from LAD_TO_BOROUGH and
    # "Bristol, City of" from the fallback resolver.
    for tail in (', city of', ', county of'):
        if s.endswith(tail):
            s = s[: -len(tail)]
    for prefix in ('city of ', 'county of ', 'the '):
        if s.startswith(prefix):
            s = s[len(prefix):]
    for suffix in (' city', ' borough', ' district'):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    return ' '.join(s.split())


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
    'E06000016': ('leicester', 'Leicester'),
    'E07000129': ('leicester', 'Blaby'),
    'E07000130': ('leicester', 'Charnwood'),
    'E07000131': ('leicester', 'Harborough'),
    'E07000132': ('leicester', 'Hinckley and Bosworth'),
    'E07000133': ('leicester', 'Melton'),
    'E07000134': ('leicester', 'North West Leicestershire'),
    'E07000135': ('leicester', 'Oadby and Wigston'),
    'E06000001': ('teesside', 'Hartlepool'),
    'E06000002': ('teesside', 'Middlesbrough'),
    'E06000003': ('teesside', 'Redcar and Cleveland'),
    'E06000004': ('teesside', 'Stockton-on-Tees'),
    'E06000005': ('teesside', 'Darlington'),
    'E06000023': ('bristol', 'City of Bristol'),
    'E06000022': ('bristol', 'Bath and North East Somerset'),
    'E06000024': ('bristol', 'North Somerset'),
    'E06000025': ('bristol', 'South Gloucestershire'),
    'E06000018': ('nottingham', 'City of Nottingham'),
    'E07000172': ('nottingham', 'Broxtowe'),
    'E07000173': ('nottingham', 'Gedling'),
    'E07000176': ('nottingham', 'Rushcliffe'),
    'E07000148': ('norwich', 'Norwich'),
    'E07000144': ('norwich', 'Broadland'),
    'E07000149': ('norwich', 'South Norfolk'),
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
    # CHARSET GATE (2026-09-07, audit I15). A UK postcode is letters and digits
    # only, and `clean` goes on to be interpolated into a postcodes.io URL
    # PATH via `quote()` - whose default is `safe='/'`, so `/` survives, and `.`
    # is always safe. `../outcodes/SW11` therefore traversed to a different
    # postcodes.io endpoint, whose payload has a different shape
    # (`admin_district` is a list, not a string), and crashed on an unhashable
    # dict key:
    #
    #   /badge?postcode=../outcodes/SW11  ->  500  application/json
    #   /badge?postcode=A/B               ->  404  (so it was not "any slash")
    #
    # That 500 defeats `/badge`'s whole contract. Its own docstring says an
    # unresolvable postcode must return a BADGE, never an error, because the
    # badge renders inside an <img> on a third-party listing page and a
    # non-image response is a broken image on a customer's site.
    #
    # Rejected HERE rather than at each caller: this is the single funnel every
    # tier goes through, and the value must never reach a URL. Length is bounded
    # too - the longest UK postcode is 7 characters without the space.
    # `str.isalnum()` is deliberately NOT used: it is true for Cyrillic letters
    # and Arabic-Indic digits, so it would answer a question about characters
    # when the question is about ASCII. The longest UK postcode is 7 characters
    # without the space; 8 leaves headroom without admitting a path.
    if not re.fullmatch(r'[A-Z0-9]{1,8}', clean):
        return None
    cached = _postcode_cache_get(clean)
    if cached is not None:
        # RE-CREDIT ONS ON A CACHE HIT (2026-08-31, audit I30).
        #
        # `mark_local_postcode_served()` lives inside `_lookup_postcode_local`,
        # and this early return is ABOVE it - so in a warm container only the
        # FIRST request for a given postcode credited ONS, and requests 2..N
        # credited postcodes.io, which was never called. Proven with the NSPL
        # table stubbed to answer and `_fetch_postcode` replaced by a raise:
        # request 1 published "ONS National Statistics Postcode Lookup... with
        # postcodes.io as fallback", requests 2 and 3 published "postcodes.io"
        # alone, on a path where postcodes.io was unreachable.
        #
        # It is also inconsistent WITHIN one response: repeat the same postcode
        # twice in a /v1/score/batch `queries` array and the two results carried
        # different provenance. `_postcode_source_line`'s own docstring says
        # "Credit what actually answered".
        if cached.get('_resolver') == 'nspl':
            mark_local_postcode_served()
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
    # Last resort: match on the loose key, which absorbs the qualifier
    # inversion ONS and postcodes.io use. "Bristol, City of" and "Nottingham"
    # both arrive here and must reach "City of Bristol" and "City of
    # Nottingham". Before 2026-08-12 they returned None and the caller 404'd
    # with "Borough not currently supported", having already resolved the right
    # city. BOROUGH_ALIASES stays the explicit path; this only catches
    # spellings nobody has had to enumerate yet.
    key = _norm_borough_key(name)
    for candidate in boroughs:
        if _norm_borough_key(candidate) == key:
            return candidate
    return None


# The four components every persona weights, and the fifth a caller MAY weight.
#
# `env` became a scored component at v3.9 and this parser kept requiring the
# key set to be exactly the original four, so `?weights=...,env:0.14` - the
# shape the response's own `weights` field publishes - was rejected, fell back
# to `balanced`, and said nothing (audit I29). The legal four-key set was worse
# than the rejection: it silences `env` to weight 0 while the same response
# still reports `env: 4.4` as `measured` and credits three OGL datasets for it.
#
# `env` is OPTIONAL rather than required, because requiring it would break every
# integrator sending the four-key set that has been documented for months.
WEIGHT_KEYS_REQUIRED = frozenset({'quiet', 'afford', 'growth', 'live'})
WEIGHT_KEYS_OPTIONAL = frozenset({'env'})


def parse_weights(raw):
    """Parse '?weights=quiet:0.5,afford:0.2,growth:0.1,live:0.2[,env:0.1]'.

    Returns (weights, None) on success and (None, reason) on failure. The reason
    is the half that did not exist: a rejected override fell back to `balanced`
    with no error field, so a caller asking for one scoring model was answered
    under another and had no way to tell.
    """
    if not raw:
        return None, None
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
            return None, "weights must look like 'quiet:0.4,afford:0.3,growth:0.1,live:0.2'"

    keys = set(result.keys())
    missing = sorted(WEIGHT_KEYS_REQUIRED - keys)
    unknown = sorted(keys - WEIGHT_KEYS_REQUIRED - WEIGHT_KEYS_OPTIONAL)
    if missing or unknown:
        detail = []
        if missing:
            detail.append(f"missing {', '.join(missing)}")
        if unknown:
            detail.append(f"unknown {', '.join(unknown)}")
        allowed = ', '.join(sorted(WEIGHT_KEYS_REQUIRED) + sorted(WEIGHT_KEYS_OPTIONAL))
        return None, f"weights {'; '.join(detail)}. Allowed keys: {allowed} (env optional)"
    try:
        result = {k: float(v) for k, v in result.items()}
    except (ValueError, TypeError):
        return None, 'every weight must be a number'
    # Each weight must be a sane fraction on its own — a sum-only check
    # accepted pathological inputs like {quiet: -1, afford: 2} (A-0724-M11).
    if any(not (0.0 <= v <= 1.0) for v in result.values()):
        return None, 'every weight must be between 0 and 1'
    total = sum(result.values())
    if not (0.99 <= total <= 1.01):
        return None, f'weights must sum to 1.0 (within 1%); these sum to {total:.3f}'
    return result, None


# ---------------------------------------------------------------------------
# Per-field provenance (2026-10-23; Bill, after reading Mireye's per-field citations: "can and should we do
# something similar"). `sources` and `sourceBreakdown` stay byte for byte: they are prose for people and a
# contract integrators already carry through (terms.html). `provenance` adds, per value, WHICH source answered,
# HOW that source made it, at what resolution and for what period. It is a function of the response already
# built, so it credits what ANSWERED (the city's own source lines, the tier in quietResolution, the *Source
# line beside a figure), never configuration: the defect CITY_PROVENANCE was built to end. The periods are held
# equal to the loaders' own holders by tests/test_provenance.py: read the holder, never retype it.
# ---------------------------------------------------------------------------

# How a source made its figure. A field says "modelled" or "measured", never both, and an agent can pass the word
# through as it stands. Only an instrument's reading is "measured": nothing in /v1/score is, today.
PROVENANCE_METHODS = {
    'measured': 'read by an instrument at a place (a monitor or a sensor)',
    'modelled': "an official body's published model output (a noise, air-pollution or flood map)",
    'statistic': 'an official statistic, compiled from records by its publisher',
    'register': 'an official register or publication (stations, GP practices, postcodes, flight procedures)',
    'curated': 'assembled by Sky Score from public sources',
    'estimated': "Sky Score's own model, where no published figure covers the place",
    'derived': 'computed by Sky Score from the sources named (a score, a rank, a real-terms trend)',
    'reference': 'a guideline value, not a figure about this place',
}

OGL = 'Open Government Licence v3.0'
# Periods without a holder in this file. Each is held equal to its loader's constant by tests/test_provenance.py.
PROVENANCE_PERIODS = {
    'defra-noise': '2021',              # DEFRA Round 4 (check_data_freshness NOISE_ROUND); published 2022
    'defra-pcm': '2024',                # load_defra_air_quality.PCM_YEAR
    'ons-crime-c4': CRIME_EDITION_LABEL,        # refresh_crime_from_ons.edition_label()
    'dfe-ks4': '2023/24',               # build_progress8.VINTAGE
    'ons-nspl': 'August 2026',          # load_nspl.NSPL_VINTAGE ('2026-08'), written as a month like the rest
    'uk-aip': 'AIRAC 2026-10-01',       # build_flight_paths.AIRAC
    'faa-cifp': 'cycle 2610, effective 2026-10-01',  # build_us_flight_paths.RECORD 'cycle' / 'effective'
}
NOT_RECORDED = None  # a continuously updated register or a map with no edition: when we last pulled it is not stored
# Said beside every NOT_RECORDED period, so an agent can tell "not stored yet" from "does not apply".
_NOT_RECORDED_NOTE = 'updated continuously; the date Sky Score last took its copy is not recorded yet'

PROVENANCE_SOURCES = {
    'hmlr-hpi': {'publisher': 'HM Land Registry', 'dataset': 'UK House Price Index', 'licence': OGL,
                 'method': 'statistic', 'resolution': 'local authority', 'period': SNAPSHOT_VINTAGE_LABEL},
    'ons-cpih': {'publisher': 'Office for National Statistics', 'dataset': 'CPIH 12-month rate, all items (L55O)',
                 'licence': OGL, 'method': 'statistic', 'resolution': 'United Kingdom', 'period': SNAPSHOT_VINTAGE_LABEL},
    'defra-noise-road': {'publisher': 'DEFRA', 'dataset': 'Strategic Noise Mapping Round 4, road Lden', 'licence': OGL,
                         'method': 'modelled', 'resolution': 'read at the postcode', 'period': PROVENANCE_PERIODS['defra-noise'],
                         'published': '2022', 'caveat': 'maps 2021, a COVID-affected year, so readings err quiet'},
    'defra-noise-aircraft': {'publisher': 'DEFRA', 'dataset': 'Strategic Noise Mapping Round 4, aircraft Lden',
                             'licence': OGL, 'method': 'modelled', 'resolution': 'read at the postcode',
                             'period': PROVENANCE_PERIODS['defra-noise'], 'published': '2022',
                             'caveat': 'maps 2021, a COVID-affected year, so readings err quiet'},
    'defra-pcm': {'publisher': 'DEFRA', 'dataset': 'Background pollution maps (PCM), annual mean NO2 and PM2.5',
                  'licence': OGL, 'method': 'modelled', 'resolution': '1 km grid', 'period': PROVENANCE_PERIODS['defra-pcm']},
    'ea-rofrs': {'publisher': 'Environment Agency', 'dataset': 'Risk of Flooding from Rivers and Sea', 'licence': OGL,
                 'method': 'modelled', 'resolution': 'share of the local authority', 'period': NOT_RECORDED,
                 'note': _NOT_RECORDED_NOTE},
    'ons-crime-c4': {'publisher': 'Office for National Statistics',
                     'dataset': 'Crime in England and Wales, Police Force Area tables, Table C4', 'licence': OGL,
                     'method': 'statistic', 'resolution': 'community safety partnership',
                     'period': PROVENANCE_PERIODS['ons-crime-c4']},
    'dfe-ks4': {'publisher': 'Department for Education', 'dataset': 'Key Stage 4 Progress 8', 'licence': OGL,
                'method': 'statistic', 'resolution': 'local authority', 'period': PROVENANCE_PERIODS['dfe-ks4']},
    'dft-naptan': {'publisher': 'Department for Transport', 'dataset': 'NaPTAN', 'licence': OGL, 'method': 'register',
                   'resolution': 'share of the local authority', 'period': NOT_RECORDED,
                 'note': _NOT_RECORDED_NOTE},
    'nhs-ods': {'publisher': 'NHS England', 'dataset': 'Organisation Data Service, GP practices', 'licence': OGL,
                'method': 'register', 'resolution': 'share of the local authority', 'period': NOT_RECORDED,
                 'note': _NOT_RECORDED_NOTE},
    'ons-nspl': {'publisher': 'Office for National Statistics', 'dataset': 'National Statistics Postcode Lookup',
                 'licence': OGL, 'method': 'register', 'resolution': 'postcode', 'period': PROVENANCE_PERIODS['ons-nspl']},
    'uk-aip': {'publisher': 'NATS', 'dataset': 'UK Aeronautical Information Publication', 'method': 'register',
               'licence': 'public but not openly licensed; not for navigation', 'resolution': 'flight procedures',
               'period': PROVENANCE_PERIODS['uk-aip']},
    'ourairports': {'publisher': 'OurAirports', 'dataset': 'Runway coordinates and geometry',
                    'licence': 'public domain (CC0)', 'method': 'register', 'resolution': 'runway', 'period': NOT_RECORDED,
                 'note': _NOT_RECORDED_NOTE},
    'postcodes-io': {'publisher': 'postcodes.io, from ONS data', 'dataset': 'Postcode lookup (fallback)',
                     'licence': 'Open Government Licence v3.0 (data); MIT (the service)', 'method': 'register',
                     'resolution': 'postcode', 'period': NOT_RECORDED,
                 'note': _NOT_RECORDED_NOTE},
    'faa-cifp': {'publisher': 'Federal Aviation Administration', 'dataset': 'Coded Instrument Flight Procedures',
                 'licence': 'not copyrighted; supplied as is, without warranty; not for navigation',
                 'method': 'register', 'resolution': 'flight procedures', 'period': PROVENANCE_PERIODS['faa-cifp']},
    'adsb-runway-use': {'publisher': 'Sky Score, from adsb.lol aircraft positions', 'dataset': 'Runway use counted',
                        'licence': 'ODbL 1.0', 'method': 'derived', 'resolution': 'airport', 'period': NOT_RECORDED,
                 'note': _NOT_RECORDED_NOTE},
    'nyc-curated': {'publisher': 'Sky Score', 'dataset': 'New York borough inputs, from public New York City sources',
                    'method': 'curated', 'resolution': 'borough', 'period': NOT_RECORDED,
                 'note': _NOT_RECORDED_NOTE},
    'nypd-compstat': {'publisher': 'NYPD', 'dataset': 'CompStat-derived offence rates per 1,000', 'method': 'statistic',
                      'resolution': 'borough', 'period': NOT_RECORDED,
                 'note': _NOT_RECORDED_NOTE},
    'nyc-faa-estimate': {'publisher': 'Sky Score', 'dataset': 'Aircraft estimate from FAA routes, fitted to Port '
                         'Authority of New York and New Jersey monitors (January-July 2026)', 'method': 'estimated',
                         'resolution': 'computed for the place', 'period': 'January-July 2026'},
    'census-acs': {'publisher': 'US Census Bureau', 'dataset': 'ACS 2020-2024 population by ZCTA',
                   'licence': 'public domain', 'method': 'statistic', 'resolution': 'ZIP code tabulation area',
                   'period': '2020-2024'},
    'census-acs-b25077': {'publisher': 'US Census Bureau', 'dataset': 'American Community Survey 2020-2024, table '
                          'B25077 (median value of owner-occupied homes)', 'licence': 'public domain',
                          'method': 'statistic', 'resolution': 'city', 'period': '2020-2024'},
    'fhfa-hpi': {'publisher': 'Federal Housing Finance Agency', 'dataset': 'House Price Index for counties (annual, '
                 'all-transactions)', 'licence': 'public domain; no FHFA endorsement is implied', 'method': 'statistic',
                 'resolution': 'county', 'period': NOT_RECORDED, 'note': _NOT_RECORDED_NOTE},
    'ca-doj-openjustice': {'publisher': 'California Department of Justice', 'dataset': 'OpenJustice Crimes and '
                           'Clearances', 'licence': 'public domain', 'method': 'statistic',
                           'resolution': 'police agency', 'period': '2025'},
    'bts-transit-stops': {'publisher': 'US Bureau of Transportation Statistics', 'dataset': 'National Transit Map Stops',
                          'licence': 'CC BY 3.0 US', 'method': 'register', 'resolution': 'share of the residents',
                          'period': NOT_RECORDED, 'note': _NOT_RECORDED_NOTE},
    'census-2020-blocks': {'publisher': 'US Census Bureau', 'dataset': '2020 Census block population (P.L. 94-171)',
                           'licence': 'public domain', 'method': 'statistic', 'resolution': 'census block',
                           'period': '2020'},
    'bts-noise-map': {'publisher': 'US Bureau of Transportation Statistics', 'dataset': 'National Transportation '
                      'Noise Map 2022 (road, 24-hour LAeq)', 'licence': 'US government work', 'method': 'modelled',
                      'resolution': 'share of the residents', 'period': '2022',
                      'caveat': 'BTS says it should not be used to evaluate noise levels at individual locations'},
    'fema-nfhl': {'publisher': 'FEMA', 'dataset': 'National Flood Hazard Layer, Special Flood Hazard Area (1% annual '
                  'chance)', 'licence': 'public domain', 'method': 'modelled', 'resolution': 'share of the residents',
                  'period': NOT_RECORDED, 'note': _NOT_RECORDED_NOTE},
    'bayarea-faa-estimate': {'publisher': 'Sky Score', 'dataset': 'Aircraft estimate from the FAA routes of San '
                             "Francisco, Oakland and San Jose, fitted to SFO's and San Jose's noise monitors",
                             'method': 'estimated', 'resolution': 'computed for the place',
                             'period': 'July 2025-June 2026'},
    'who-noise-2018': {'publisher': 'World Health Organization', 'dataset': 'Environmental Noise Guidelines for the '
                       'European Region (2018)', 'method': 'reference', 'period': '2018'},
    'who-aq-2021': {'publisher': 'World Health Organization', 'dataset': 'Global air quality guidelines (2021)',
                    'method': 'reference', 'period': '2021'},
}

# A credit line (in `sources`, or a figure's own *Source line) -> the registry ids it names. Matched from the
# START of the line, so a line no pattern knows stays unmatched and tests/test_provenance.py names it.
PROVENANCE_LINE_IDS = (
    (r'Prices: HM Land Registry', ('hmlr-hpi',)),
    (r'Prices: curated New York', ('nyc-curated',)),
    (r'Inflation: ONS CPIH', ('ons-cpih',)),
    (r'Transport access: DfT NaPTAN', ('dft-naptan',)),
    (r'Healthcare access: NHS Organisation Data Service', ('nhs-ods',)),
    (r'Postcode resolution: ONS National Statistics Postcode Lookup', ('ons-nspl',)),
    (r'Borough metadata: ONS .*Department for Education', ('ons-crime-c4', 'dfe-ks4')),
    (r'Borough metadata: ONS', ('ons-crime-c4',)),
    (r'Borough metadata: curated from public New York', ('nyc-curated',)),
    (r'Crime: NYPD CompStat', ('nypd-compstat',)),
    (r'Crime: ONS Crime in England and Wales', ('ons-crime-c4',)),
    (r'Schools: Department for Education, Key Stage 4 Progress 8', ('dfe-ks4',)),
    (r'Transport: NaPTAN', ('dft-naptan',)),
    (r'Healthcare: NHS Organisation Data Service', ('nhs-ods',)),
    (r'Postcode resolution: postcodes\.io', ('postcodes-io',)),
    (r'Aviation noise context: ESTIMATED from .*published in the UK AIP', ('uk-aip', 'defra-noise-aircraft')),
    (r'Aviation noise context: ESTIMATED from .*runway \S+ geometry', ('ourairports', 'defra-noise-aircraft')),
    (r'Flight routes: FAA Coded Instrument Flight Procedures', ('faa-cifp',)),
    (r'Runway use: counted by Sky Score from aircraft positions', ('adsb-runway-use',)),
    (r'Aviation noise context: DEFRA', ('defra-noise-aircraft',)),
    (r'Aviation noise context: ESTIMATED from the FAA routes of JFK', ('nyc-faa-estimate',)),
    (r'Aviation noise context: ESTIMATED from the FAA routes of San Francisco', ('bayarea-faa-estimate',)),
    (r'Borough aircraft band: .*Census', ('census-acs',)),
    (r'Flight routes: UK Aeronautical Information Publication', ('uk-aip',)),
    (r'Air quality: DEFRA background', ('defra-pcm',)),
    (r'DEFRA background pollution maps \(PCM\)', ('defra-pcm',)),
    (r'Road noise: DEFRA', ('defra-noise-road',)),
    (r'DEFRA Strategic Noise Mapping Round 4, road', ('defra-noise-road',)),
    (r'DEFRA Strategic Noise Mapping Round 4, aircraft', ('defra-noise-aircraft',)),
    (r'Flood risk: Environment Agency', ('ea-rofrs',)),
    (r'Prices: US Census Bureau, American Community Survey', ('census-acs-b25077',)),
    (r'Price trend: Federal Housing Finance Agency', ('fhfa-hpi',)),
    (r'Residents: US Census Bureau, 2020 Census block', ('census-2020-blocks',)),
    (r'Road noise: USDOT Bureau of Transportation Statistics', ('bts-noise-map',)),
    (r'Flood risk: FEMA National Flood Hazard Layer', ('fema-nfhl',)),
    (r'Licence note:', ()),
)

# A figure carried beside its own credit line: that line names exactly the map that answered.
_OWN_SOURCE_LINE = {
    'roadNoiseLdenDb': 'roadNoiseSource', 'roadNoiseBelowDb': 'roadNoiseSource',
    'no2AnnualMeanUgm3': 'airQualitySource', 'pm25AnnualMeanUgm3': 'airQualitySource',
    'aircraftNoiseLdenDb': 'aircraftNoiseSource',
}
# Fields that describe the response rather than the place.
_DESCRIBES_ITSELF = ('growthBasis', 'environmentSingleInput', 'priceTopCoded')

# Which credit lines feed each component, by the line's own prefix.
_COMPONENT_LINES = {
    'afford': ('Prices',),
    'growth': ('Prices', 'Price trend', 'Inflation'),
    'live': ('Borough metadata', 'Crime', 'Schools', 'Transport access', 'Transport', 'Healthcare access', 'Healthcare',
             'Liveability'),
    'env': ('Air quality', 'Road noise', 'Flood risk'),
}


_LIVEABILITY_INPUTS = (('Progress 8', 'dfe-ks4'), ('Table C4', 'ons-crime-c4'), ('NaPTAN', 'dft-naptan'),
                       ('NHS Organisation Data Service', 'nhs-ods'), ('OpenJustice', 'ca-doj-openjustice'),
                       ('National Transit Map', 'bts-transit-stops'))


def provenance_line_ids(line):
    """The registry ids a credit line names; None when no pattern knows the line."""
    if re.match(r'Liveability \(\d of \d inputs\):', line):
        return tuple(i for word, i in _LIVEABILITY_INPUTS if word in line) or None
    for pattern, ids in PROVENANCE_LINE_IDS:
        if re.match(pattern, line):
            return ids
    return None


def _ids_for(sources, prefixes):
    out = []
    for line in sources:
        # The name before any '(3 of 4 inputs)': a line's count of inputs moves with the place.
        if line.split(':', 1)[0].split(' (', 1)[0] in prefixes:
            out += [i for i in (provenance_line_ids(line) or ()) if i not in out]
    return out


def _from_source(ids):
    """An entry for a figure that IS one source's figure: its method, resolution and period."""
    entry = {'sources': list(ids)}
    if len(ids) == 1:
        src = PROVENANCE_SOURCES[ids[0]]
        entry.update({k: src[k] for k in ('method', 'resolution', 'period') if k in src})
    return entry


def _derived(ids, basis=None):
    entry = {'sources': list(ids), 'method': 'derived'}
    if basis:
        entry['basis'] = basis
    return entry


def _quiet(body, sources):
    tier = (body.get('context') or {}).get('quietResolution')
    aviation = _ids_for(sources, ('Aviation noise context', 'Flight routes', 'Runway use', 'Borough aircraft band',
                                  'Residents'))
    if tier == 'raster':
        # DEFRA's map read at the postcode, through Sky Score's ramp (METHODOLOGY 4.5).
        return {**_derived([i for i in aviation if i.startswith('defra-noise')]), 'basis': 'raster'}
    if tier == 'postcode':
        estimate = [i for i in aviation if not i.startswith('defra-noise') and i != 'census-acs']
        entry = {'sources': estimate, 'method': 'estimated', 'basis': 'postcode'}
        if 'defra-noise-aircraft' in aviation:
            entry['fittedTo'] = 'defra-noise-aircraft'
        return entry
    return _derived(aviation, basis=tier)


def build_provenance(body):
    """({field path: entry}, {source id: registry record}) for a /v1/score or /v1/environment body.

    Values only: a *Source line, a *Resolution, `growthBasis` and the like ARE provenance and get no entry.
    A value no rule covers gets {'sources': [], 'method': None}: absence said, never filled (the gate fails on it).
    """
    sources = [s for s in body.get('sources', []) if isinstance(s, str)]
    ctx = body.get('context') or body.get('environment') or {}
    section = 'context' if 'context' in body else 'environment'
    out = {}

    for comp in (body.get('components') or {}):
        if comp == 'quiet':
            out['components.quiet'] = _quiet(body, sources)
        else:
            # No basis copied from `coverage` here: its 'measured' means the inputs are PRESENT, and this object
            # keeps that word for an instrument's reading. `coverage` still says how many inputs answered.
            out[f'components.{comp}'] = _derived(_ids_for(sources, _COMPONENT_LINES.get(comp, ())))

    if 'score' in body and isinstance(body['score'], (int, float)):
        # The headline is the weighted sum of the components sent, so it credits all of theirs.
        out['score'] = _derived(sorted({i for k, e in out.items() if k.startswith('components.')
                                         for i in e['sources']}))

    prices = _ids_for(sources, ('Prices',))
    # A trend from its own source where it has one (the Bay Area's FHFA county index), else the price source's.
    trend = _ids_for(sources, ('Price trend',)) or prices
    inflation = _ids_for(sources, ('Inflation',))
    for key in ctx:
        path = f'{section}.{key}'
        if key.endswith(('Source', 'Resolution', 'Coverage')) or key in _DESCRIBES_ITSELF:
            continue
        own = ctx.get(_OWN_SOURCE_LINE.get(key, ''))
        if 'WhoGuideline' in key:
            out[path] = _from_source(['who-noise-2018' if 'Noise' in key else 'who-aq-2021'])
        elif isinstance(own, str) and provenance_line_ids(own):
            out[path] = _from_source(provenance_line_ids(own))
        elif key in ('avgPriceGbp', 'avgPriceUsd', 'avgPriceUsdAtLeast'):
            out[path] = _from_source(prices)
        elif key in ('priceTrendPct', 'priceTrendArea'):
            out[path] = _from_source(trend)
        elif key == 'inflationPct':
            out[path] = _from_source(inflation)
        elif key == 'priceTrendRealPct':
            out[path] = _derived(trend + inflation)
        elif key == 'priceRankInCity':
            out[path] = _derived(prices)
        elif key == 'growthRankInCity':
            out[path] = _derived(trend + inflation)
        elif key in ('noiseImpactBand', 'aircraftQuiet'):
            out[path] = _derived((out.get('components.quiet') or {}).get('sources')
                                 or provenance_line_ids(ctx.get('aircraftNoiseSource', '')) or [])
        else:
            out[path] = {'sources': [], 'method': None}

    loc = body.get('location') or {}
    if loc.get('postcode') and loc.get('city') not in ('nyc', 'bayarea', None):
        resolver = _ids_for(sources, ('Postcode resolution',))
        for key in ('latitude', 'longitude', 'borough', 'region'):
            if key in loc:
                out[f'location.{key}'] = _from_source(resolver)

    used = sorted({i for e in out.values() for i in e.get('sources', []) + [e.get('fittedTo')] if i})
    index = {i: PROVENANCE_SOURCES[i] for i in used}
    return out, index


def with_provenance(body, sent=None):
    """`sent` (the body after filter_response; `body` itself when unfiltered) with `provenance` and `sourceIndex`
    for the values it CARRIES. Built from the FULL body, so the headline score still credits its components and
    quiet tier when ?include=score drops them; then cut to the fields sent, so nothing describes a field the
    caller never got."""
    sent = body if sent is None else sent
    prov, _ = build_provenance(body)
    kept = {k: e for k, e in prov.items() if k.split('.', 1)[0] in sent}
    if kept:
        used = sorted({i for e in kept.values() for i in e['sources'] + [e.get('fittedTo')] if i})
        sent['provenance'], sent['sourceIndex'] = kept, {i: PROVENANCE_SOURCES[i] for i in used}
    return sent


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
    # Missing until 2026-08-24, so any ?include= silently stripped every
    # coverage caveat - build_coverage promises it "on every response" and the
    # filter was quietly breaking that promise. It is also in filter_response's
    # always-kept set: listing it here alone would only make it requestable.
    'coverage',
    # Built AFTER the filter (with_provenance), so they always describe exactly what was sent.
    'provenance',
    'sourceIndex',
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
    fields (apiVersion, methodologyVersion, generatedAt, sources, coverage)."""
    if not include:
        return body
    # coverage is kept for the same reason sources is: it is the caveat
    # surface. A payload-slimming filter must not be able to remove the
    # sentence that says a component is a placeholder rather than a reading.
    always = {'apiVersion', 'methodologyVersion', 'methodologyUrl', 'generatedAt', 'sources',
              'coverage'}
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


# Borough NAME -> (city, borough), the name-keyed twin of LAD_TO_BOROUGH.
# Needed because the postcodes.io fallback tier returns a borough name and no
# LAD code, so a code-only derivation would fix the local NSPL tier and leave
# the fallback still defaulting to london.
_CITY_BY_BOROUGH_NAME = {
    _norm_borough_key(borough): (city, borough)
    for city, borough in LAD_TO_BOROUGH.values()
}


def derive_city(lad_code, admin_district):
    """City id for a resolved location, or None if we do not cover it.

    ONE HOLDER, called by both resolve_query and handle_environment. It was
    inline in resolve_query alone until 2026-08-21, and handle_environment -
    written later - simply passed the literal 'london' instead. The endpoint is
    unauthenticated and the public browser extension renders it, so a postcode
    1.2 km from Manchester Airport published aircraftQuietEstimated 10.0, the
    top of the scale, against 2.0 under Manchester's own geometry. Eight points
    of error on a ten-point scale, in the flattering direction.

    Two tiers because the two resolver paths carry different fields: the local
    NSPL row has the LAD code, the postcodes.io fallback has only the district
    NAME. A code-only lookup repairs the loaded tier and leaves the fallback
    answering london, which is the same defect one step further down.

    Returns None rather than a default. A caller that cannot name a city must
    decide what that means for its own surface - there is no city here that is
    safe to assume.
    """
    derived = LAD_TO_BOROUGH.get(lad_code)
    if not derived:
        derived = _CITY_BY_BOROUGH_NAME.get(_norm_borough_key(admin_district))
    if derived and derived[0] in CITIES:
        return derived[0]
    return None


def resolve_query(query):
    """Run a single score query. Returns the response body or an error dict."""
    # Per-request attribution starts clean. Without this a reused container
    # carries the previous caller's NSPL hit into this response's `sources`.
    reset_postcode_attribution()
    postcode = parse_str_param(query.get('postcode'))
    borough_input = parse_str_param(query.get('borough'))
    city = parse_str_param(query.get('city'), 'london').lower()
    persona = parse_str_param(query.get('persona'), 'balanced').lower()
    weights_override, weights_error = parse_weights(query.get('weights'))
    if weights_error:
        # A rejected override used to fall through to `balanced` in silence, so
        # a caller could ask for one scoring model, be answered under another,
        # and have nothing in the response to say so. 400 is the honest answer:
        # the request named a model we did not apply.
        return {
            'error': weights_error,
            'weightsKeys': {
                'required': sorted(WEIGHT_KEYS_REQUIRED),
                'optional': sorted(WEIGHT_KEYS_OPTIONAL),
            },
        }, 400
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
            named_city = parse_str_param(query.get('city')).lower()
            if zip5 in NYC_ZIP_TO_BOROUGH and named_city and named_city != 'nyc' and not uk_shape(named_city):
                # A New York ZIP asked of another US city was answered as New York in silence, so a caller asking
                # the Bay Area about 10001 got a New York score under a request naming the Bay Area. A UK city
                # named with it is NOT refused: `city=london` is the documented default, and scripts/score_bulk.py
                # sends it on every row, so refusing it failed every New York ZIP in a bulk book (code review,
                # 2026-10-22); a UK city cannot hold a ZIP, so the ZIP decides there, as it always has.
                return {
                    'error': f'ZIP {zip5} is a New York City ZIP, not in {CITIES[named_city]["name"]}.',
                    'note': 'Send it without city, or with city=nyc.',
                }, 404
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
                # `supportedNycBoroughs` stays: scripts/score_bulk.py reads it as "outside New York". The Bay Area
                # is named because its ZIPs land here too: no ZIP table is held for it, and a ZIP there spans
                # cities. The site's table (data/us-bayarea-zips.json) gives each ZIP to the city with most of
                # its LAND, so 94010 goes to Hillsborough and 7 of the 50 cities hold no ZIP's majority
                # (measured 2026-10-22). A score needs the residents' city, so the honest answer is the city
                # name, not a guessed city.
                return {
                    'error': f'ZIP not currently supported: {postcode}',
                    'note': (
                        'Sky Score resolves New York City ZIPs only at present (Manhattan, Brooklyn, Queens, '
                        'Bronx, Staten Island). San Francisco Bay Area cities are scored by name: '
                        'borough=<city>&city=bayarea, the 50 cities listed by /v1/regions.'
                    ),
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
            # DERIVE THE CITY FROM THE RESOLVED LAD when the caller did not
            # name one (2026-08-12).
            #
            # `city` defaults to 'london', so a postcode-only query - the
            # natural call, and the one score-demo and api/index.html both
            # document - resolved its borough correctly and then looked that
            # borough up in LONDON_BOROUGHS. M1 1AE answered
            # "Borough not currently supported in london.", naming a city the
            # caller never mentioned; B15, LS1, S1, BS1 and NG1 did the same.
            #
            # So postcode-level scoring was LONDON-ONLY in production for any
            # caller who did not already know which city to ask for, while
            # CLAUDE.md, ROADMAP and METHODOLOGY all recorded it as un-gated
            # since 2026-08-10. The un-gating was real - `?city=manchester`
            # with the same postcode scores 7.7 - it simply could not be
            # reached without supplying the answer in the question. The LAD
            # code was on every row the whole time; nothing read it to pick a
            # city.
            #
            # Keyed on the LAD CODE first and the borough NAME second, because
            # the two resolver tiers carry different fields: the local NSPL row
            # has `_ladCode`, the postcodes.io fallback has only
            # `admin_district`. An explicit `city=` still wins, so a caller can
            # still force a cohort. Guarded by PostcodeCityDerivationTests.
            if not parse_str_param(query.get('city')):
                derived_city = derive_city(
                    pc.get('_ladCode'), pc.get('admin_district')
                )
                if derived_city:
                    city = derived_city
                    location_meta['city'] = city
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
        if postcode and not parse_str_param(query.get('city')):
            # NOT COVERED YET (2026-10-22, found by the MCP server's first live test). A postcode in no covered
            # city fell through to the DEFAULT city and answered "Borough not currently supported in london."
            # for EX1 1HS, naming a city the caller never asked about, with London's boroughs as the list. Only
            # a NYC ZIP or a UK postcode reaches here (any other ZIP returned above), and a NYC ZIP always
            # resolves, so this is a UK postcode outside every city derive_city knows.
            return {
                'error': f'Not covered yet: {location_meta.get("postcode") or postcode} is outside every city Sky Score scores.',
                'attemptedBorough': location_meta.get('borough'),
                'supportedCities': sorted(CITIES.keys()),
            }, 404
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
    if not any(score_data['weights'].values()):
        # Custom weights that fall only on components this place cannot score (growth for the Bay Area, `env`
        # for New York) applied nothing, and the engine answered 200 with a score of 0.0: a number nobody
        # measured (code review, 2026-10-22). Refused, with what IS scored here, as a bad weight set is.
        return {
            'error': 'None of the weighted components is scored for this borough, so there is no score to give.',
            'scoredComponents': sorted(score_data['components']),
        }, 400

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
            # APPLIED weights, matching what the response now publishes. This
            # function's own docstring already required "the weights the two
            # results were scored under" (audit note), and `weights` was the
            # nominal row - so wherever a component was dropped, every
            # `contribution` was computed against a weight the engine had not
            # used, and `attributionSum` could not reconcile. Taking the CURRENT
            # result's set is right for the components build_attribution keeps:
            # it already skips anything absent from either vintage.
            comparison = build_comparison(
                score_data, prev_data, city, score_data['weights'], borough
            )

    body = {
        **score_data,
        **({'comparison': comparison} if comparison is not None else {}),
        **({'comparisonUnavailable': comparison_unavailable} if comparison_unavailable else {}),
        'location': location_meta,
        'persona': persona_label,
        # `weights` COMES FROM score_data - deliberately not re-stated here.
        #
        # It used to be `'weights': weights`, the persona's nominal row, written
        # AFTER the `**score_data` spread and therefore overriding the applied
        # set calc_score computes. Removing this line is the whole fix on the
        # response side: one holder, and it is the holder that did the
        # arithmetic. Re-adding a nominal `weights` here silently reinstates a
        # published sum that does not reach the published score.
        'methodologyVersion': METHODOLOGY_VERSION,
        'methodologyUrl': METHODOLOGY_URL,
        'apiVersion': API_VERSION,
        'generatedAt': datetime.now(UTC).isoformat(),
        # ONE record for both, so the sources array and the lineage cannot
        # disagree about which inputs this borough has - which is exactly what
        # they did before 2026-08-31.
        'sources': build_sources(
            city, bd=_borough_record(city, borough),
            quiet_source=score_data.get('context', {}).get('quietResolution'),
        ),
        'sourceBreakdown': build_source_breakdown(city, _borough_record(city, borough)),
    }
    # Roadmap-visible placeholder components, let prospects see what's planned
    # before they ask. Each entry has a status flag so integrators don't try
    # to consume placeholder data as if it were live.
    # `flood` and `airQuality` LEFT this block at methodology v3.9, 2026-08-26.
    # Both now ship inside the `env` component, so advertising them as planned
    # would be the inverse of the usual staleness here: a promise still being
    # made for something already delivered, which reads to a prospect as though
    # it is not.
    #
    # The airQuality entry also carried a source claim that was never right.
    # It named the DEFRA *Daily Air Quality Index*, a sparse daily index at
    # monitoring stations; what actually scores is the DEFRA background
    # pollution maps (PCM), an annual mean on a 1 km grid. The loader's own
    # docstring has said WHY NOT DAQI since it was written. Removing the entry
    # retires the wrong claim with it.
    #
    # `roadNoise` never entered this block and now never will: it went straight
    # from display-only to scored at methodology v4.0, 2026-08-29, joining
    # `env` alongside air quality and flood. The v3.9 note here said it was
    # "scheduled for the v4.0 noise composite" and declined to promise it,
    # which turned out to be the right call one wave early.
    #
    # THE MEASURED-BUT-UNSCORED CATEGORY IS NOW EMPTY. Every input this product
    # derives is either scored or is a MEASUREMENT reported by /v1/environment
    # under a label naming what it measures. Nothing is drawn on the map that
    # a score silently ignores.
    #
    # UK cities only (code review, 2026-10-22): both entries are UK datasets (MHCLG, ONS), so in a New York or
    # Bay Area response they credited UK bodies with no NOT, the defect test_non_uk_city_never_credits_uk_bodies
    # guards against, unseen because that test did not read this block. Neither is planned for a US city.
    if not uk_shape(city):
        return with_provenance(body, filter_response(body, include)), 200
    body['plannedComponents'] = {
        'epcDistribution': {
            'status': 'planned',
            'source': 'MHCLG Get Energy Performance Data (currently in /epc; planned in /v1/score)',
            'eta': 'roadmap',
        },
        'crimeBreakdown': {
            'status': 'planned',
            # "planned" FOR THIS RESPONSE. The consumer site already renders a
            # per-borough offence breakdown (`crimeTop`, ONS Table C4, 85 of 91
            # boroughs, in data/borough-extra.json since 2026-09-13); what is
            # planned is publishing it through /v1/score. Said here so the next
            # reader does not "close" this entry on seeing the panel (audit M37).
            'source': 'ONS Table C4 offence groups per CSP (on the consumer site today; planned for this API, OGL v3.0)',
            'eta': 'roadmap',
        },
    }
    return with_provenance(body, filter_response(body, include)), 200


def handle_options():
    """CORS preflight response. Open to any origin.

    The conclusion is right and the ORIGINAL REASON WENT FALSE. This said
    "the GET/POST are API-key gated, so origin restriction adds no security",
    and three GET routes on this function are not gated at all - /v1/regions,
    /v1/changes and /v1/environment each answer 200 with no key (verified live
    2026-08-27). The reason that actually holds is the one ROADMAP records:
    CORS is a BROWSER control and does not protect against server-side calls,
    so an origin restriction buys nothing on any of these routes, gated or not.
    Keeping a stale justification is worse than keeping none - it reads as
    evidence the question was asked recently."""
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


# Computed once per container. `handle_changes` never reads `event` and every
# input is a module constant (CITIES, previous_dataset, PERSONAS['balanced'],
# the vintage strings), so the body cannot vary between callers within a
# deployment - only a redeploy changes it, and that replaces the container.
#
# Audit finding I2, fixed 2026-08-22: the route is UNAUTHENTICATED and was
# recomputing 66 calc_score() calls, two benchmark passes, two growth-rank
# passes and 33 attribution builds on every request, to return a 116 KB body
# that is byte-identical every time. That is a cost amplifier anyone can pull.
_CHANGES_BODY = None

# One hour. The payload only changes on a vintage roll, which arrives with a
# deploy, so a longer TTL would serve correctly for months - but this repo has
# already served a user days-stale borough data through an over-eager cache,
# and an hour bounds how long a rolled vintage can keep answering with the old
# one at the edge.
_CHANGES_MAX_AGE = 3600
_CHANGES_HEADERS = {'Cache-Control': f'public, max-age={_CHANGES_MAX_AGE}'}


def handle_changes(event):
    """GET /v1/changes — quarter-over-quarter movement for every London
    borough under balanced weights.

    Public (no API key): the underlying tables are already public via the
    consumer site, and this is the shareable 'what moved this quarter'
    surface.

    NOT the only key-free route on this function: /v1/regions is ALSO
    unauthenticated. This docstring said the opposite until 2026-08-21 - and an
    earlier version had it right and was "corrected" into the falsehood. Checked
    against the live API rather than against this file: `GET /v1/regions` with no
    key returns HTTP 200 and 4.9 KB, and `RegionsGet` in template.yaml carries no
    `Auth` block at all. Whether it SHOULD be gated is open (see AUDIT_REPORT.md
    I1); what it is, is open.

    Each borough carries an `attribution` breakdown and a derived
    `explanation`, so "why did this move?" is answerable from the response
    without a second call."""
    global _CHANGES_BODY
    if _CHANGES_BODY is not None:
        return response(
            200,
            {**_CHANGES_BODY, 'generatedAt': datetime.now(UTC).isoformat()},
            _CHANGES_HEADERS,
        )

    bal = PERSONAS['balanced']
    prev_set = previous_dataset('london')
    cur_bm = benchmarks(CITIES['london']['boroughs'], 'london')
    prev_bm = benchmarks(prev_set, 'london', previous=True)
    cur_ranks = growth_ranks(CITIES['london']['boroughs'])
    prev_ranks = growth_ranks(prev_set)
    changes = []
    # Seeded with the nominal row so the name is always bound, then replaced by
    # the APPLIED set each borough was actually scored under. London carries all
    # five components, so the two are identical today - the point is that this
    # endpoint cannot become the last surface publishing nominal weights if that
    # ever stops being true.
    applied_weights = bal
    for name in CITIES['london']['boroughs']:
        cur = calc_score(name, 'london', bal)
        applied_weights = cur['weights']
        prev = calc_score(name, 'london', bal, boroughs_override=prev_set)
        # `cur['weights']`, not `bal`. Identical today - every London borough
        # carries all five components, so the applied set IS the nominal one -
        # but DERIVED rather than restated, so this cannot become the surface
        # that still uses nominal weights if London ever loses a component. A
        # second holder of the same idea is how mirrored code drifts here.
        attribution = build_attribution(cur, prev, cur['weights'])
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
                **({'previousTrendRealPct': prev['context']['priceTrendRealPct']}
                   if 'priceTrendRealPct' in prev['context'] else {}),
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
                    cur, prev, 'london', cur['weights'], name, cur_bm, prev_bm, cur_ranks, prev_ranks
                ),
                'why': build_why(
                    cur, prev, 'london', cur['weights'], name, cur_bm, prev_bm, cur_ranks, prev_ranks
                ),
            }
        )
    changes.sort(key=lambda c: abs(c['scoreChange']), reverse=True)
    moved = [c for c in changes if abs(c['scoreChange']) > 0.5]
    risers = [c for c in changes if c['scoreChange'] > 0]
    fallers = [c for c in changes if c['scoreChange'] < 0]
    # Built AFTER the tally so its closing sentence can count what the scores
    # did rather than infer it from the trend (see market_context).
    market = market_context(
        CITIES['london']['boroughs'], prev_set, [c['scoreChange'] for c in changes]
    )
    _CHANGES_BODY = {
            'city': 'london',
            'persona': 'balanced',
            'currentVintage': SNAPSHOT_VINTAGE,
            'previousVintage': PREVIOUS_VINTAGE,
            'refreshedAt': SNAPSHOT_REFRESHED_AT,
            'note': COMPARISON_NOTE,
            # Published so a caller can reproduce every `attribution`
            # contribution as weight x component change, and verify the parts
            # sum to scoreChange.
            #
            # DERIVED from a scored result, not restated from `bal`. Identical
            # today because every London borough carries all five components,
            # but /v1/score publishes APPLIED weights as of 2026-09-09 and this
            # endpoint must not become the one surface still publishing nominal
            # ones. `changes` is London-only, so one borough's set speaks for
            # the page - and a per-borough divergence would show up in the
            # roundingResidual each row already publishes.
            'weights': applied_weights,
            # The city-wide picture, so a reader can see how many boroughs
            # moved and that the market moved with them - without it, 25 of 33
            # dropping (or 14 rising while the trend fell, as in July 2026)
            # reads as a scoring fault rather than a description of the quarter.
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
            # /v1/changes covers the London cohort only - previous_dataset() has
            # no vintage for any other city - so London's provenance is the
            # accurate claim here rather than a default that happens to fit.
            #
            # THE POSTCODE LINE IS DROPPED (2026-09-07, audit I3). This route
            # resolves no postcode at all, so the line describing which resolver
            # answered describes nothing that happened. Worse, it was WRONG and
            # STUCK: `_postcode_source_line` reads a `threading.local()` flag
            # that `handle_changes` never sets and never resets, so it published
            # whatever the container's last /v1/score request happened to leave
            # behind - and then froze that into `_CHANGES_BODY` for the life of
            # the container. Measured live: 3 of 3 requests credited "ONS
            # National Statistics Postcode Lookup ... with postcodes.io as
            # fallback" on a route that looks up neither.
            #
            # Removing it is the fix rather than resetting the flag: a correct
            # value for a lookup that did not happen is still a claim about
            # nothing. Attribution follows what ANSWERED.
            'sources': [
                line for line in build_sources('london')
                if 'Postcode resolution' not in str(line)
            ],
    }
    # `generatedAt` is stamped per response, NOT cached with the body. Freezing
    # it would have the payload claim it was generated at container start for
    # the life of that container - a caller reading it as freshness would be
    # misled by the very optimisation that made the response cheap. Everything
    # above it is deterministic within a deployment; this line is not.
    return response(
        200,
        {**_CHANGES_BODY, 'generatedAt': datetime.now(UTC).isoformat()},
        _CHANGES_HEADERS,
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

    location = reverse_geocode(lat, lon)
    if not location:
        return response(
            404,
            {
                'error': 'No UK postcode found near those coordinates.',
                'location': {'lat': lat, 'lon': lon},
            },
        )

    pc = location['postcode']
    city = derive_city(location.get('ladCode'), location.get('adminDistrict'))
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
        # MACHINE-READABLE basis, one of AIRCRAFT_QUIET_COVERAGE, set in the
        # same branch that decides the sentence so the two cannot disagree.
        # Until 2026-09-18 the extension classified coverage by matching a
        # PHRASE in aircraftQuietBasis, guarded by an e2e probe of the live
        # endpoint - a caveat keyed on wording is how audit I12's caveat
        # deleted itself. Consumers read this; the prose stays for people.
        env['aircraftQuietCoverage'] = 'measured'
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
        #
        # THE CITY IS DERIVED, NOT ASSUMED. This read `'london'` as a literal
        # until 2026-08-21, for every coordinate in the UK. Measured: M22 5RX,
        # 1.2 km from Manchester Airport's runway, published 10.0 - the top of
        # the scale, "no aircraft noise" - where Manchester's own geometry gives
        # 2.0. Every term here is distance-gated, so the wrong city's geometry
        # fails silently and always in the flattering direction: it does not
        # know about the airport you live under, so it reports quiet.
        #
        # When the postcode sits outside every city we cover - 68% of live UK
        # postcodes, measured against NSPL with thirteen cities - take the LOUDEST reading any of our
        # geometries gives rather than one city's. Two reasons it is safe here
        # and would not be above: /v1/score 404s those postcodes, so there is no
        # per-city answer to contradict; and a maximum cannot under-report,
        # which is the single direction this defect failed in. It costs 0.2 ms
        # over 624 waypoints. `basis` names which of the two ran, because a
        # union is a weaker claim than a city and must not read as the same one.
        if city:
            # raster_lden=None, not the sentinel: lden_from_row has already
            # resolved this row and missed, and the sentinel would send
            # calc_postcode_quiet back to DynamoDB for the same key. Its own
            # docstring calls that doubling out - _make_lru never caches a
            # negative, so a miss genuinely hits the network twice.
            estimated = calc_postcode_quiet(
                lat, lon, city, postcode_clean, raster_lden=None
            )
            basis = 'flight-path geometry, not measured'
            coverage = 'city'
        else:
            estimated = _quiet_across_all_geometry(lat, lon, postcode_clean)
            # A NOUN PHRASE, because the extension renders this as
            # `Estimated from ${basis}.` — panel.js:696. A string that reads
            # well alone can read as gibberish in its caller's sentence, and
            # this one is the sentence a user actually sees.
            basis = (
                'the nearest airports we hold, not measured - this postcode is '
                'outside every city Sky Score covers'
            )
            coverage = 'outside'
        if estimated is not None:
            env['aircraftQuietEstimated'] = estimated
            env['aircraftQuietBasis'] = basis
            env['aircraftQuietCoverage'] = coverage
        # Keyed on the same `city` the basis above was resolved from. It used
        # to be `'postcode-nyc' if city == 'nyc' else 'postcode'`, which has no
        # branch for `city is None` - so the uncovered case fell through to a
        # notice claiming DEFRA coverage, contradicting the basis string set
        # eight lines earlier in the same response.
        # One holder for which estimate sentence is true here (I3): NYC, an
        # uncovered coordinate, a city DEFRA does not map, a city with no
        # airport at all, or the ordinary case.
        notices.append(_postcode_coverage_notice(city))
    if 'roadNoiseBelowDb' in env:
        # Quiet, and KNOWN to be. The old notice below was what a surveyed
        # zero produced until 2026-09-10, and "has not been measured" was
        # false for every one of them.
        notices.append(
            f'DEFRA surveyed this postcode and mapped no road noise at or above '
            f'{env["roadNoiseBelowDb"]:.0f} dB Lden, the lowest level its Round 4 '
            'road map records - under the WHO guideline of 53 dB. That is a quiet '
            'reading, not a missing one, so no figure is shown.'
        )
    elif 'roadNoiseLdenDb' not in env:
        notices.append(_road_absence_notice(city))

    return response(
        200,
        with_provenance({
            'location': {'lat': lat, 'lon': lon, 'postcode': pc},
            'environment': env,
            'notices': notices,
            'apiVersion': API_VERSION,
            'methodologyVersion': METHODOLOGY_VERSION,
        }),
    )


# --- Embeddable badge -------------------------------------------------------
#
# WHY AN SVG SERVED AS <img>, and not a JavaScript snippet.
#
# This is the Walk Score mechanism: the badge is what puts a score on somebody
# else's listing page, and the API becomes worth buying because the badge made
# the number familiar. So the only thing that matters is that it renders on
# pages we do not control.
#
# A JS embed does not clear that bar. Property portals and agency CMSes run
# strict CSP, and a script from a third-party origin is the first thing their
# policy blocks - the badge would silently not appear on exactly the sites worth
# appearing on. An <img> is allowed almost everywhere, needs no JS at all,
# survives a CMS that strips <script>, and is cached by CloudFront rather than
# re-executed per view. The link back is a plain <a> the embedder pastes around
# it, which also means the backlink survives when the image does not load.
#
# WHAT IT EXPOSES, and why that is not the product. The composite score for a
# postcode is already public: the consumer site renders it for anyone. What the
# API sells is programmatic access - components, personas, weights, comparison
# and batch - and none of those appear here. Same posture as /v1/environment:
# the reading, not the engine.

_BADGE_BANDS = [
    (8.0, '#1a7f37', 'Excellent'),
    (6.5, '#3f8f29', 'Good'),
    (5.0, '#9a6700', 'Fair'),
    (0.0, '#a40e26', 'Poor'),
]


def _badge_band(score):
    for floor, colour, label in _BADGE_BANDS:
        if score >= floor:
            return colour, label
    return _BADGE_BANDS[-1][1], _BADGE_BANDS[-1][2]


def _svg_escape(text):
    """XML-escape. The postcode reaches the SVG body, so this is not optional.

    An SVG served from our origin and embedded on a third-party page is a
    script-capable document; unescaped input in it is stored XSS on someone
    else's site, carrying our domain in the frame. Everything interpolated
    below goes through here.
    """
    return (
        str(text)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
        .replace("'", '&#39;')
    )


def _badge_svg(postcode, score, band_label, colour, dark=False):
    bg = '#1c1c1c' if dark else '#ffffff'
    fg = '#f5f5f4' if dark else '#141414'
    sub = '#a1a1a1' if dark else '#636363'
    line = '#3a3a3a' if dark else '#e7e5e4'
    pc = _svg_escape(postcode)
    label = _svg_escape(band_label)
    # role="img" plus <title> is what gives a screen reader something to say;
    # an <img> embed also carries the alt text the embedder writes.
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="220" height="64" viewBox="0 0 220 64" role="img" aria-label="Sky Score {pc}: {score} out of 10, {label}">
  <title>Sky Score {pc}: {score} out of 10 ({label})</title>
  <rect x="0.5" y="0.5" width="219" height="63" rx="6" fill="{bg}" stroke="{line}"/>
  <rect x="1" y="1" width="6" height="62" rx="3" fill="{colour}"/>
  <text x="20" y="24" font-family="Helvetica,Arial,sans-serif" font-size="10" font-weight="700" letter-spacing="1.2" fill="{sub}">SKY SCORE</text>
  <text x="20" y="50" font-family="Helvetica,Arial,sans-serif" font-size="24" font-weight="700" fill="{fg}">{score}</text>
  <text x="60" y="50" font-family="Helvetica,Arial,sans-serif" font-size="11" fill="{sub}">/ 10</text>
  <text x="92" y="42" font-family="Helvetica,Arial,sans-serif" font-size="11" font-weight="600" fill="{colour}">{label}</text>
  <text x="92" y="55" font-family="Helvetica,Arial,sans-serif" font-size="9" fill="{sub}">{pc}</text>
</svg>'''


BADGE_ECHO_MAX = 10


def _svg_response(svg, status=200, cache_seconds=86400):
    return {
        'statusCode': status,
        'headers': {
            'Content-Type': 'image/svg+xml; charset=utf-8',
            # Long cache on purpose. Scores move on data vintages, roughly
            # quarterly, and this is embedded on pages that may render it
            # thousands of times a day - an uncached badge would make somebody
            # else's traffic our Lambda bill.
            'Cache-Control': f'public, max-age={cache_seconds}',
            # Explicitly NOT a JSON CORS surface. An <img> needs no CORS at all;
            # allowing it would only widen what can read this.
            'X-Content-Type-Options': 'nosniff',
            'Strict-Transport-Security': 'max-age=31536000',
            # SINCE 2026-09-17 THIS SVG IS SERVED FROM skyscore.co.uk ITSELF
            # (the /badge edge-cache behaviour), so it shares an origin with the
            # app and an SVG opened as a document can run script. Escaping was
            # the only barrier; this makes one regression in it inert rather
            # than script on the main origin (2026-09-25 audit M-3). The same
            # policy html_page() already sends.
            'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'",
        },
        'body': svg,
    }


def handle_badge(event):
    """GET /badge?postcode=&theme= - an embeddable SVG score badge.

    UNAUTHENTICATED, necessarily: it is embedded on pages we do not control, so
    it cannot carry a key. It reuses resolve_query, so a badge can never show a
    score /v1/score would not.

    An unresolvable postcode returns a BADGE, not an error. A broken image on a
    customer's listing page is worse than an honest one saying the postcode is
    not covered, and a 404 renders as exactly that broken image. The status code
    still tells a machine what happened.
    """
    params = event.get('queryStringParameters') or {}
    postcode = parse_str_param(params.get('postcode'))
    dark = parse_str_param(params.get('theme')).lower() == 'dark'

    if not postcode:
        return _svg_response(
            _badge_svg('No postcode', '-', 'Add ?postcode=', '#636363', dark),
            status=400,
            cache_seconds=300,
        )

    body, status = resolve_query({'postcode': postcode})
    if status != 200 or not isinstance(body.get('score'), (int, float)):
        # Short cache: an uncovered postcode becomes covered when a city lands,
        # and a day-long cache would keep showing "not covered" after it did.
        return _svg_response(
            # Capped: the longest UK postcode is 8 characters with its space.
            # Uncapped, any caller-chosen text rendered under our brand on our
            # own origin (escaped, so spoofed wording rather than script).
            _badge_svg(postcode.upper()[:BADGE_ECHO_MAX], '-', 'Not covered', '#636363', dark),
            status=status if status >= 400 else 404,
            cache_seconds=300,
        )

    score = round(float(body['score']), 1)
    colour, label = _badge_band(score)
    resolved = (body.get('location') or {}).get('postcode') or postcode.upper()
    return _svg_response(_badge_svg(resolved, score, label, colour, dark))


def handle_get(event):
    path = (event.get('path') or '').rstrip('/')
    if path.endswith('/badge'):
        return handle_badge(event)
    if path.endswith('/regions'):
        return handle_regions(event)
    if path.endswith('/changes'):
        return handle_changes(event)
    if path.endswith('/environment'):
        return handle_environment(event)
    params = event.get('queryStringParameters') or {}
    body, status = resolve_query(params)
    return response(status, body)


def handle_batch(event, context=None):
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

    # A valid-JSON non-object (`[]`, `"x"`, `1`) raised AttributeError on
    # `.get` and answered 500 (audit M3). Same guard chat gained on 13 Sep.
    if not isinstance(payload, dict):
        return response(400, {'error': 'Body must be a JSON object with a "queries" array.'})
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

    # Parallel resolution. Each `resolve_query` call may hit postcodes.io
    # (network-bound, ~100-500 ms p95). Sequential at MAX_BATCH_SIZE=100 that
    # is 10-50 s against the 28 s function Timeout in template.yaml - the
    # API Gateway integration cap less one second - so a full batch of
    # fallback-tier postcodes could not finish in series.
    # ThreadPoolExecutor with bounded workers gives us request-level
    # concurrency without overwhelming postcodes.io (which is generous
    # but unspecified on per-IP limits) or hitting Python GIL pressure.
    from concurrent.futures import ThreadPoolExecutor

    indexed_queries = list(enumerate(queries))

    # The invocation deadline, from the one place it is knowable. context is
    # optional (None from unit tests and direct invocations) and the method is
    # probed rather than assumed, so a missing or unusual context degrades to
    # the old no-deadline behaviour instead of a 500 for the whole batch.
    deadline = None
    if context is not None and hasattr(context, 'get_remaining_time_in_millis'):
        try:
            deadline = (time.monotonic()
                        + context.get_remaining_time_in_millis() / 1000.0
                        - _BATCH_DEADLINE_MARGIN_S)
        except Exception:  # noqa: BLE001 - a broken context must not kill the batch
            deadline = None

    def run_one(item):
        idx, query = item
        if not isinstance(query, dict):
            return idx, ({'error': 'Query must be an object.'}, 400)
        # Refuse to START once the deadline nears, so a stalled upstream costs
        # the batch its tail rather than the whole response: without this, 100
        # queries each spending a 5s postcodes.io timeout across 10 workers is
        # 50s of wall clock against a 28s Lambda ceiling, and every answer -
        # including the computed ones - died together in a raw 504. The item
        # SAYS it was never attempted; a refused slot must never be readable
        # as "scored" or as "this postcode has no data".
        if deadline is not None and time.monotonic() >= deadline:
            return idx, ({
                'error': ('Not attempted: the batch neared the request '
                          'deadline before this query started, so it was '
                          'never attempted. The results above it are '
                          'complete; resubmit the unattempted queries in a '
                          'smaller batch.'),
                'notAttempted': True,
            }, 503)
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
    # ONE sourceIndex for the batch (Bill, 2026-10-23): each result keeps its own `provenance`, whose ids all
    # resolve here, so a 100-place batch does not carry the same source records 100 times to an agent that pays
    # for every byte it reads.
    source_index = {}
    for idx, (body, status) in outcomes:
        result = {'queryIndex': idx, 'status': status}
        if status == 200:
            result.update(body)
            source_index.update(result.pop('sourceIndex', {}))
            success += 1
        else:
            result['error'] = body.get('error', 'Unknown error')
            # notAttempted is the deadline marker: it distinguishes "this
            # query was refused unrun" from every error a query can EARN, so
            # a caller can resubmit exactly the unattempted tail.
            # `note` carries the way round a refusal (a Bay Area ZIP: ask by city name), so it travels too.
            for k in ('attemptedBorough', 'supportedBoroughs', 'supportedCities', 'example', 'note',
                      'notAttempted'):
                if k in body:
                    result[k] = body[k]
            error += 1
        results.append(result)

    not_attempted = sum(1 for r in results if r.get('notAttempted'))

    return response(
        200,
        {
            'totalQueries': len(queries),
            'successCount': success,
            'errorCount': error,
            # Only present when the deadline fired: a partial batch announces
            # itself at the top level rather than requiring a scan of 100
            # per-item errors to notice the response is incomplete.
            **({'notAttemptedCount': not_attempted} if not_attempted else {}),
            'apiVersion': API_VERSION,
            'methodologyVersion': METHODOLOGY_VERSION,
            'generatedAt': datetime.now(UTC).isoformat(),
            # A batch may span cities; credit only those that actually answered.
            'sources': build_batch_sources(
                r.get('location', {}).get('city') for r in results
            ),
            **({'sourceIndex': dict(sorted(source_index.items()))} if source_index else {}),
            'results': results,
        },
    )


def log_request(event, status):
    """One line per request: WHICH KEY called WHICH route, and nothing else.

    Added 2026-09-28 because nothing could say whether anyone outside the
    project had ever used the API: API Gateway keeps per-key DAILY totals only,
    access logging is off (privacy.html s2d promises so), and the demo key is
    shared by the public tester and, until that day, by our own gates.

    The key ID is API Gateway's identifier (e.g. `1zy00lrqs5`), never the
    secret value. Deliberately absent: source IP, user agent, the query string
    and so the POSTCODE (a postcode can identify a home), and the body.
    privacy.html s2d names exactly these fields; widening this line means
    widening that sentence in the same deploy.
    """
    identity = (event.get('requestContext') or {}).get('identity') or {}
    logger.info(
        '[API_REQUEST] %s',
        json.dumps(
            {
                'method': (event.get('httpMethod') or 'GET').upper(),
                'route': event.get('resource') or event.get('path'),
                'status': status,
                'apiKeyId': identity.get('apiKeyId'),
            }
        ),
    )


def handler(event, context):
    method = (event.get('httpMethod') or 'GET').upper()
    try:
        if method == 'OPTIONS':
            return handle_options()
        if method == 'POST':
            # context carries the invocation deadline the batch path budgets
            # against; see _BATCH_DEADLINE_MARGIN_S.
            result = handle_batch(event, context)
        else:
            result = handle_get(event)
    except Exception as exc:  # final guard, never let internals leak
        logger.exception('Unhandled exception in score handler: %s', exc)
        result = response(500, {'error': 'Internal server error'})
    try:
        log_request(event, result.get('statusCode'))
    except Exception:  # noqa: S110 - a log line must never fail a request
        pass
    return result


def cors_headers():
    return {
        'Access-Control-Allow-Origin': CORS_ORIGIN,
        'Strict-Transport-Security': 'max-age=31536000',
        'X-Content-Type-Options': 'nosniff',
        'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type,X-Api-Key',
        'Access-Control-Max-Age': '86400',
    }


def response(status, body, headers=None):
    """JSON response. `headers` adds to (and may override) the defaults."""
    return {
        'statusCode': status,
        'headers': {
            'Content-Type': 'application/json',
            **cors_headers(),
            **(headers or {}),
        },
        'body': json.dumps(body),
    }
