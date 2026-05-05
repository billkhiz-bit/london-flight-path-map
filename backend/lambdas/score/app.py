"""
Sky Score B2B API.

Endpoints:
  GET  /v1/score          — single-postcode/borough score
  POST /v1/score/batch    — bulk lookup (up to 100 queries per call)
  OPTIONS for both        — browser CORS preflight (open to any origin
                            since the GET/POST are API-key gated anyway)

Methodology: see METHODOLOGY.md at the project root. The scoring values and
formulas in this file are anchored to that document; any change to weights,
thresholds, or component formulas should bump METHODOLOGY_VERSION and be
documented in the methodology changelog.
"""

import json
import os
import re
from datetime import datetime, timezone
from functools import lru_cache
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

CORS_ORIGIN = os.environ.get('CORS_ORIGIN', '*')
METHODOLOGY_URL = 'https://github.com/billkhiz-bit/london-flight-path-map/blob/master/METHODOLOGY.md'
METHODOLOGY_VERSION = '2.0'
API_VERSION = '1.0'
MAX_BATCH_SIZE = 100

SCHOOL_SCORE = {'outstanding': 10, 'excellent': 9, 'good': 6, 'mixed': 3}
TRANSPORT_SCORE = {'excellent': 10, 'good': 7, 'moderate': 4, 'poor': 2}
HEALTH_SCORE = {'excellent': 10, 'good': 7, 'moderate': 4}
IMPACT_TO_QUIET = {
    'low': 10.0, 'low-moderate': 7.5, 'moderate': 5.0,
    'moderate-high': 3.0, 'high': 1.5, 'severe': 0.0,
}

PERSONAS = {
    'balanced':  {'quiet': 0.30, 'afford': 0.25, 'growth': 0.20, 'live': 0.25},
    'family':    {'quiet': 0.20, 'afford': 0.20, 'growth': 0.10, 'live': 0.50},
    'investor':  {'quiet': 0.10, 'afford': 0.30, 'growth': 0.40, 'live': 0.20},
    'firsttime': {'quiet': 0.15, 'afford': 0.40, 'growth': 0.20, 'live': 0.25},
    'quietlife': {'quiet': 0.50, 'afford': 0.20, 'growth': 0.10, 'live': 0.20},
}

# London borough dataset — sourced from index.html BOROUGH_DATA_RAW + BOROUGH_EXTRA.
# Schema: impact (DEFRA Lden band), avgPrice (GBP), trend (% YoY),
# schools/transport/healthcare (categorical), crimeRate (per 1,000 ONS).
LONDON_BOROUGHS = {
    'Hounslow':              {'impact': 'severe',         'avgPrice': 465000,  'trend': 3.2, 'schools': 'good',      'crimeRate': 89,  'transport': 'good',      'healthcare': 'good'},
    'Hillingdon':            {'impact': 'severe',         'avgPrice': 480000,  'trend': 2.8, 'schools': 'good',      'crimeRate': 72,  'transport': 'good',      'healthcare': 'good'},
    'Richmond upon Thames':  {'impact': 'high',           'avgPrice': 825000,  'trend': 1.5, 'schools': 'excellent', 'crimeRate': 58,  'transport': 'good',      'healthcare': 'good'},
    'Ealing':                {'impact': 'high',           'avgPrice': 540000,  'trend': 4.1, 'schools': 'good',      'crimeRate': 88,  'transport': 'excellent', 'healthcare': 'good'},
    'Wandsworth':            {'impact': 'moderate',       'avgPrice': 680000,  'trend': 2.1, 'schools': 'excellent', 'crimeRate': 82,  'transport': 'excellent', 'healthcare': 'good'},
    'Lambeth':               {'impact': 'moderate',       'avgPrice': 560000,  'trend': 3.5, 'schools': 'good',      'crimeRate': 115, 'transport': 'excellent', 'healthcare': 'good'},
    'Lewisham':              {'impact': 'low-moderate',   'avgPrice': 445000,  'trend': 4.8, 'schools': 'good',      'crimeRate': 91,  'transport': 'good',      'healthcare': 'good'},
    'Greenwich':             {'impact': 'moderate',       'avgPrice': 430000,  'trend': 5.2, 'schools': 'good',      'crimeRate': 93,  'transport': 'good',      'healthcare': 'good'},
    'Tower Hamlets':         {'impact': 'low-moderate',   'avgPrice': 495000,  'trend': 2.0, 'schools': 'good',      'crimeRate': 120, 'transport': 'excellent', 'healthcare': 'excellent'},
    'Camden':                {'impact': 'low',            'avgPrice': 780000,  'trend': 1.2, 'schools': 'excellent', 'crimeRate': 130, 'transport': 'excellent', 'healthcare': 'excellent'},
    'Islington':             {'impact': 'low',            'avgPrice': 720000,  'trend': 1.8, 'schools': 'good',      'crimeRate': 125, 'transport': 'excellent', 'healthcare': 'good'},
    'Hackney':               {'impact': 'low',            'avgPrice': 590000,  'trend': 3.0, 'schools': 'good',      'crimeRate': 112, 'transport': 'excellent', 'healthcare': 'good'},
    'Barnet':                {'impact': 'low-moderate',   'avgPrice': 560000,  'trend': 3.1, 'schools': 'excellent', 'crimeRate': 74,  'transport': 'good',      'healthcare': 'good'},
    'Croydon':               {'impact': 'moderate',       'avgPrice': 395000,  'trend': 4.5, 'schools': 'good',      'crimeRate': 98,  'transport': 'good',      'healthcare': 'good'},
    'Bromley':               {'impact': 'low',            'avgPrice': 480000,  'trend': 3.8, 'schools': 'excellent', 'crimeRate': 65,  'transport': 'moderate',  'healthcare': 'good'},
    'Newham':                {'impact': 'moderate-high',  'avgPrice': 410000,  'trend': 5.8, 'schools': 'good',      'crimeRate': 108, 'transport': 'excellent', 'healthcare': 'good'},
    'Southwark':             {'impact': 'low-moderate',   'avgPrice': 530000,  'trend': 2.5, 'schools': 'good',      'crimeRate': 118, 'transport': 'excellent', 'healthcare': 'excellent'},
    'Hammersmith and Fulham':{'impact': 'moderate-high',  'avgPrice': 750000,  'trend': 1.0, 'schools': 'excellent', 'crimeRate': 96,  'transport': 'excellent', 'healthcare': 'good'},
    'Kensington and Chelsea':{'impact': 'moderate',       'avgPrice': 1350000, 'trend': 0.5, 'schools': 'excellent', 'crimeRate': 95,  'transport': 'excellent', 'healthcare': 'excellent'},
    'Brent':                 {'impact': 'low-moderate',   'avgPrice': 490000,  'trend': 4.0, 'schools': 'good',      'crimeRate': 92,  'transport': 'good',      'healthcare': 'good'},
    'Haringey':              {'impact': 'low',            'avgPrice': 545000,  'trend': 3.5, 'schools': 'good',      'crimeRate': 99,  'transport': 'good',      'healthcare': 'moderate'},
    'Waltham Forest':        {'impact': 'low',            'avgPrice': 480000,  'trend': 4.2, 'schools': 'good',      'crimeRate': 88,  'transport': 'good',      'healthcare': 'moderate'},
    'Merton':                {'impact': 'low-moderate',   'avgPrice': 560000,  'trend': 2.8, 'schools': 'good',      'crimeRate': 70,  'transport': 'good',      'healthcare': 'good'},
    'Redbridge':             {'impact': 'low',            'avgPrice': 445000,  'trend': 3.9, 'schools': 'excellent', 'crimeRate': 83,  'transport': 'good',      'healthcare': 'good'},
    'Enfield':               {'impact': 'low',            'avgPrice': 430000,  'trend': 4.3, 'schools': 'good',      'crimeRate': 85,  'transport': 'moderate',  'healthcare': 'moderate'},
    'Kingston upon Thames':  {'impact': 'low-moderate',   'avgPrice': 550000,  'trend': 2.0, 'schools': 'excellent', 'crimeRate': 62,  'transport': 'good',      'healthcare': 'good'},
    'Sutton':                {'impact': 'low',            'avgPrice': 415000,  'trend': 3.5, 'schools': 'excellent', 'crimeRate': 60,  'transport': 'moderate',  'healthcare': 'good'},
    'Westminster':           {'impact': 'moderate',       'avgPrice': 980000,  'trend': 0.8, 'schools': 'good',      'crimeRate': 175, 'transport': 'excellent', 'healthcare': 'excellent'},
    'City of London':        {'impact': 'low-moderate',   'avgPrice': 850000,  'trend': 1.0, 'schools': 'good',      'crimeRate': 190, 'transport': 'excellent', 'healthcare': 'good'},
    'Barking and Dagenham':  {'impact': 'low',            'avgPrice': 340000,  'trend': 5.8, 'schools': 'good',      'crimeRate': 105, 'transport': 'good',      'healthcare': 'moderate'},
    'Havering':              {'impact': 'low',            'avgPrice': 400000,  'trend': 4.0, 'schools': 'good',      'crimeRate': 72,  'transport': 'moderate',  'healthcare': 'good'},
    'Bexley':                {'impact': 'low',            'avgPrice': 380000,  'trend': 4.5, 'schools': 'good',      'crimeRate': 68,  'transport': 'moderate',  'healthcare': 'good'},
    'Harrow':                {'impact': 'low',            'avgPrice': 490000,  'trend': 3.2, 'schools': 'excellent', 'crimeRate': 70,  'transport': 'good',      'healthcare': 'good'},
}

# NYC borough dataset — sourced from index.html NYC_BOROUGH_DATA_RAW + NYC_BOROUGH_EXTRA.
# avgPrice in USD (not GBP). Crime rates use the same per-1,000 convention but
# are derived from NYPD CompStat / NYC ONS-equivalent denominators; cross-city
# comparison should be approached with caution (different methodologies).
NYC_BOROUGHS = {
    'Queens':         {'impact': 'severe',       'avgPrice': 620000,  'trend': 4.5, 'schools': 'good',      'crimeRate': 78,  'transport': 'excellent', 'healthcare': 'good'},
    'Brooklyn':       {'impact': 'high',         'avgPrice': 850000,  'trend': 3.8, 'schools': 'good',      'crimeRate': 82,  'transport': 'excellent', 'healthcare': 'excellent'},
    'Manhattan':      {'impact': 'moderate',     'avgPrice': 1200000, 'trend': 2.0, 'schools': 'excellent', 'crimeRate': 95,  'transport': 'excellent', 'healthcare': 'excellent'},
    'Bronx':          {'impact': 'low-moderate', 'avgPrice': 420000,  'trend': 5.5, 'schools': 'good',      'crimeRate': 110, 'transport': 'good',      'healthcare': 'good'},
    'Staten Island':  {'impact': 'low',          'avgPrice': 550000,  'trend': 3.0, 'schools': 'good',      'crimeRate': 52,  'transport': 'poor',      'healthcare': 'moderate'},
}

CITIES = {
    'london': {'boroughs': LONDON_BOROUGHS, 'currency': 'GBP'},
    'nyc':    {'boroughs': NYC_BOROUGHS,    'currency': 'USD'},
}

# NYC ZIP-to-borough mapping. ZIPs grouped per borough and flattened into a
# dict for O(1) lookup. Sourced from NYC OpenData ZCTA boundaries + USPS.
# Covers ~230 ZIPs across the 5 boroughs (residential + general use ZIPs;
# excludes some PO Box / single-building ZIPs that wouldn't be typed by a
# user). 9-digit ZIP+4 inputs are reduced to first 5 digits before lookup.
_NYC_ZIPS_BY_BOROUGH = {
    'Manhattan': [
        '10001','10002','10003','10004','10005','10006','10007','10009','10010',
        '10011','10012','10013','10014','10016','10017','10018','10019','10020',
        '10021','10022','10023','10024','10025','10026','10027','10028','10029',
        '10030','10031','10032','10033','10034','10035','10036','10037','10038',
        '10039','10040','10044','10065','10069','10075','10128','10280','10282',
    ],
    'Bronx': [
        '10451','10452','10453','10454','10455','10456','10457','10458','10459',
        '10460','10461','10462','10463','10464','10465','10466','10467','10468',
        '10469','10470','10471','10472','10473','10474','10475',
    ],
    'Staten Island': [
        '10301','10302','10303','10304','10305','10306','10307','10308','10309',
        '10310','10311','10312','10314',
    ],
    'Brooklyn': [
        '11201','11203','11204','11205','11206','11207','11208','11209','11210',
        '11211','11212','11213','11214','11215','11216','11217','11218','11219',
        '11220','11221','11222','11223','11224','11225','11226','11228','11229',
        '11230','11231','11232','11233','11234','11235','11236','11237','11238',
        '11239','11249',
    ],
    'Queens': [
        '11004','11005','11101','11102','11103','11104','11105','11106','11109',
        '11354','11355','11356','11357','11358','11359','11360','11361','11362',
        '11363','11364','11365','11366','11367','11368','11369','11370','11372',
        '11373','11374','11375','11377','11378','11379','11385','11411','11412',
        '11413','11414','11415','11416','11417','11418','11419','11420','11421',
        '11422','11423','11426','11427','11428','11429','11432','11433','11434',
        '11435','11436','11691','11692','11693','11694','11697',
    ],
}
NYC_ZIP_TO_BOROUGH = {
    zip5: borough
    for borough, zips in _NYC_ZIPS_BY_BOROUGH.items()
    for zip5 in zips
}

US_ZIP_PATTERN = re.compile(r'^\d{5}(-\d{4})?$')

# Aliases for boroughs whose canonical name differs from postcodes.io's
# admin_district output, or common variants.
BOROUGH_ALIASES = {
    'Barking and Dagenham': 'Barking and Dagenham',
    'Barking': 'Barking and Dagenham',
    'City of London Corporation': 'City of London',
    'Westminster City': 'Westminster',
}

SOURCES = [
    'EPC data: MHCLG, Open Government Licence v3.0',
    'Sold prices: HM Land Registry, Open Government Licence v3.0',
    'Postcode resolution: postcodes.io (Open Government Licence v3.0)',
    'Borough metadata: ONS, Home Office, Department for Education (Open Government Licence v3.0)',
    'Aviation noise context: DEFRA strategic noise mapping, Open Government Licence v3.0',
]

# Per-component data lineage. Auditable provenance for each scoring input —
# B2B audit teams ask "where did this number come from" component-by-component
# and this surfaces the answer at the response level. The /v1/score endpoint
# does NOT call OpenSky directly (consumer site does); aviation noise context
# for the API comes from pre-computed DEFRA borough-aggregate Lden bands.
SOURCE_BREAKDOWN = {
    'quiet': 'DEFRA Strategic Noise Mapping (Round 4, 2022) — borough-aggregate Lden band; the API does not depend on OpenSky',
    'afford': 'HM Land Registry Price Paid Data — borough cohort min-max scaling',
    'growth': 'HM Land Registry Price Paid Data — annualised price trend, cohort-relative',
    'live': 'ONS + Home Office + DfE + TfL + NHS — composite weighted (schools 35% + crime 30% + transport 25% + healthcare 10%)',
}


def crime_to_score(rate):
    if rate is None:
        return 5.0
    return max(0.0, min(10.0, 10.0 - (rate - 50) / 15.0))


def get_live_score(bd):
    sch = SCHOOL_SCORE.get(bd.get('schools'), 5)
    crm = crime_to_score(bd.get('crimeRate'))
    trn = TRANSPORT_SCORE.get(bd.get('transport'), 5)
    hlt = HEALTH_SCORE.get(bd.get('healthcare'), 5)
    return round((sch * 0.35 + crm * 0.30 + trn * 0.25 + hlt * 0.10) * 10) / 10


def calc_score(borough_name, city, weights):
    boroughs = CITIES[city]['boroughs']
    bd = boroughs[borough_name]

    quiet = IMPACT_TO_QUIET.get(bd['impact'], 5.0)

    prices = [b['avgPrice'] for b in boroughs.values()]
    max_price, min_price = max(prices), min(prices)
    if max_price == min_price:
        afford = 5.0
    else:
        afford = ((max_price - bd['avgPrice']) / (max_price - min_price)) * 10

    trends = [b['trend'] for b in boroughs.values()]
    max_trend = max(trends) or 1.0
    growth = (bd['trend'] / max_trend) * 10

    live = get_live_score(bd)

    total = (
        quiet * weights['quiet']
        + afford * weights['afford']
        + growth * weights['growth']
        + live * weights['live']
    )

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
        },
    }


@lru_cache(maxsize=512)
def _lookup_postcode_cached(clean):
    """In-memory LRU cache for postcodes.io lookups within a Lambda container.
    Containers persist ~15 min on AWS; repeat lookups within that window
    bypass the upstream call (~100-500ms p95). For higher-volume B2B traffic,
    a DynamoDB cache layer is on the roadmap — the lru_cache is a low-cost
    interim. Keyed on the cleaned (no-space, upper-case) postcode."""
    if not clean:
        return None
    url = f'https://api.postcodes.io/postcodes/{quote(clean)}'
    req = Request(url, headers={'Accept': 'application/json'})
    try:
        with urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read().decode())
    except (HTTPError, URLError):
        return None
    if payload.get('status') != 200:
        return None
    return payload.get('result')


def lookup_postcode(postcode):
    """Resolve UK postcode → admin_district via postcodes.io (free, OGL)."""
    clean = postcode.strip().replace(' ', '').upper()
    return _lookup_postcode_cached(clean) if clean else None


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
    total = sum(result.values())
    if not (0.99 <= total <= 1.01):
        return None
    return result


def resolve_query(query):
    """Run a single score query. Returns the response body or an error dict."""
    postcode = (query.get('postcode') or '').strip()
    borough_input = (query.get('borough') or '').strip()
    city = (query.get('city') or 'london').strip().lower()
    persona = (query.get('persona') or 'balanced').strip().lower()
    weights_override = parse_weights(query.get('weights'))

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
        # US ZIP auto-detection — 5 digits with optional +4 suffix.
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
            else:
                return {
                    'error': f'ZIP not currently supported: {postcode}',
                    'note': 'Sky Score supports NYC ZIPs only at present (Manhattan, Brooklyn, Queens, Bronx, Staten Island).',
                    'supportedNycBoroughs': sorted(NYC_BOROUGHS.keys()),
                }, 404
        else:
            # UK postcode path — postcodes.io resolves to a London borough.
            if city != 'london':
                return {
                    'error': f'Postcode resolution is UK-only for non-NYC ZIPs. For {city} use ?borough=, or pass a 5-digit US ZIP for NYC auto-detection.',
                }, 400
            pc = lookup_postcode(postcode)
            if not pc:
                return {
                    'error': f'Postcode not recognised by postcodes.io: {postcode}',
                }, 404
            borough = normalise_borough(pc.get('admin_district'), city)
            location_meta.update({
                'postcode': pc.get('postcode'),
                'borough': borough,
                'longitude': pc.get('longitude'),
                'latitude': pc.get('latitude'),
                'region': pc.get('region'),
            })
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

    score_data = calc_score(borough, city, weights)

    return {
        **score_data,
        'location': location_meta,
        'persona': persona_label,
        'weights': weights,
        'methodologyVersion': METHODOLOGY_VERSION,
        'methodologyUrl': METHODOLOGY_URL,
        'apiVersion': API_VERSION,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'sources': SOURCES,
        'sourceBreakdown': SOURCE_BREAKDOWN,
    }, 200


def handle_options():
    """CORS preflight response. Open to any origin — the GET/POST are
    API-key gated, so origin restriction adds no security."""
    return {
        'statusCode': 200,
        'headers': cors_headers(),
        'body': '',
    }


def handle_regions(event):
    """GET /v1/regions — discovery endpoint listing supported geographies.
    Used by integrators to know what's queryable without scraping responses."""
    return response(200, {
        'cities': [
            {
                'id': 'london',
                'name': 'London',
                'country': 'United Kingdom',
                'currency': 'GBP',
                'postcodeFormat': 'UK postcode (e.g. SW11 1AA)',
                'postcodeResolver': 'postcodes.io',
                'boroughCount': len(LONDON_BOROUGHS),
                'boroughs': sorted(LONDON_BOROUGHS.keys()),
            },
            {
                'id': 'nyc',
                'name': 'New York City',
                'country': 'United States',
                'currency': 'USD',
                'postcodeFormat': '5-digit US ZIP (e.g. 10001), with optional +4 suffix',
                'postcodeResolver': 'static ZIP-to-borough lookup',
                'boroughCount': len(NYC_BOROUGHS),
                'boroughs': sorted(NYC_BOROUGHS.keys()),
                'supportedZipCount': len(NYC_ZIP_TO_BOROUGH),
            },
        ],
        'apiVersion': API_VERSION,
        'methodologyVersion': METHODOLOGY_VERSION,
        'methodologyUrl': METHODOLOGY_URL,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
    })


def handle_get(event):
    path = (event.get('path') or '').rstrip('/')
    if path.endswith('/regions'):
        return handle_regions(event)
    params = event.get('queryStringParameters') or {}
    body, status = resolve_query(params)
    return response(status, body)


def handle_batch(event):
    raw_body = event.get('body') or ''
    if event.get('isBase64Encoded'):
        import base64
        try:
            raw_body = base64.b64decode(raw_body).decode()
        except Exception:
            return response(400, {'error': 'Invalid base64-encoded body'})

    try:
        payload = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError:
        return response(400, {'error': 'Invalid JSON body'})

    queries = payload.get('queries')
    if not isinstance(queries, list):
        return response(400, {
            'error': 'Body must contain a "queries" array.',
            'example': {
                'queries': [
                    {'postcode': 'SW11 1AA', 'persona': 'balanced'},
                    {'postcode': 'TW3 4DX', 'persona': 'family'},
                    {'borough': 'Hackney', 'city': 'london',
                     'weights': {'quiet': 0.5, 'afford': 0.2, 'growth': 0.1, 'live': 0.2}},
                ],
            },
        })

    if len(queries) == 0:
        return response(400, {'error': 'queries array is empty.'})

    if len(queries) > MAX_BATCH_SIZE:
        return response(400, {
            'error': f'Batch size exceeds limit of {MAX_BATCH_SIZE} queries.',
            'submitted': len(queries),
            'limit': MAX_BATCH_SIZE,
        })

    results = []
    success = 0
    error = 0
    for idx, query in enumerate(queries):
        if not isinstance(query, dict):
            results.append({'queryIndex': idx, 'error': 'Query must be an object.'})
            error += 1
            continue
        body, status = resolve_query(query)
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

    return response(200, {
        'totalQueries': len(queries),
        'successCount': success,
        'errorCount': error,
        'apiVersion': API_VERSION,
        'methodologyVersion': METHODOLOGY_VERSION,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'sources': SOURCES,
        'results': results,
    })


def handler(event, context):
    method = (event.get('httpMethod') or 'GET').upper()
    try:
        if method == 'OPTIONS':
            return handle_options()
        if method == 'POST':
            return handle_batch(event)
        return handle_get(event)
    except Exception:
        return response(500, {'error': 'Internal server error'})


def cors_headers():
    return {
        'Access-Control-Allow-Origin': '*',
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
