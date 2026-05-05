"""
Sky Score B2B API — /v1/score endpoint.

Computes a per-postcode (or per-borough) Sky Score from the structural inputs
extracted from the consumer-site scoring engine in index.html. Designed for
B2B integration partners (data aggregators, conveyancers, Islamic-finance
providers); the consumer site continues to use its own client-side scoring.

Methodology: see METHODOLOGY.md at the project root.
"""

import json
import os
from datetime import datetime, timezone
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

CORS_ORIGIN = os.environ.get('CORS_ORIGIN', '*')
METHODOLOGY_URL = 'https://github.com/billkhiz-bit/london-flight-path-map/blob/master/METHODOLOGY.md'
METHODOLOGY_VERSION = '1.0'

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

# London borough dataset — structural inputs only (narrative fields stripped).
# Sourced from index.html BOROUGH_DATA_RAW + BOROUGH_EXTRA (consumer site).
# Schema: impact, avgPrice, trend (% growth), schools, crimeRate (per 1000),
# transport, healthcare.
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

# Aliases for boroughs whose postcodes.io admin_district name differs from
# the canonical Sky Score borough name.
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


def calc_score(borough_name, weights):
    bd = LONDON_BOROUGHS[borough_name]

    quiet = IMPACT_TO_QUIET.get(bd['impact'], 5.0)

    # Min-max scale price across the cohort, inverted (cheaper = higher).
    prices = [b['avgPrice'] for b in LONDON_BOROUGHS.values()]
    max_price, min_price = max(prices), min(prices)
    if max_price == min_price:
        afford = 5.0
    else:
        afford = ((max_price - bd['avgPrice']) / (max_price - min_price)) * 10

    trends = [b['trend'] for b in LONDON_BOROUGHS.values()]
    max_trend = max(trends) or 1.0
    growth = (bd['trend'] / max_trend) * 10

    live = get_live_score(bd)

    total = (
        quiet * weights['quiet']
        + afford * weights['afford']
        + growth * weights['growth']
        + live * weights['live']
    )

    return {
        'score': round(total * 10) / 10,
        'components': {
            'quiet': round(quiet * 10) / 10,
            'afford': round(afford * 10) / 10,
            'growth': round(growth * 10) / 10,
            'live': round(live * 10) / 10,
        },
        'context': {
            'avgPriceGbp': bd['avgPrice'],
            'priceTrendPct': bd['trend'],
            'noiseImpactBand': bd['impact'],
        },
    }


def lookup_postcode(postcode):
    """Resolve postcode → admin_district via postcodes.io (free, OGL)."""
    clean = postcode.strip().replace(' ', '').upper()
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


def normalise_borough(name):
    if not name:
        return None
    if name in LONDON_BOROUGHS:
        return name
    return BOROUGH_ALIASES.get(name)


def parse_weights(raw):
    """Parse ?weights=quiet:0.5,afford:0.2,growth:0.1,live:0.2.

    Returns dict, or None if unparsable. Sum must be ~1 (within 1%).
    """
    if not raw:
        return None
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
    total = sum(result.values())
    if not (0.99 <= total <= 1.01):
        return None
    return result


def handler(event, context):
    try:
        params = event.get('queryStringParameters') or {}
        postcode = (params.get('postcode') or '').strip()
        borough_input = (params.get('borough') or '').strip()
        persona = (params.get('persona') or 'balanced').strip().lower()
        weights_override = parse_weights(params.get('weights'))

        if not postcode and not borough_input:
            return response(400, {
                'error': 'Provide either postcode or borough.',
                'example': '/v1/score?postcode=SW11+1AA',
            })

        # Resolve borough.
        location_meta = {'city': 'london'}
        if postcode:
            pc = lookup_postcode(postcode)
            if not pc:
                return response(404, {
                    'error': f'Postcode not recognised by postcodes.io: {postcode}',
                })
            borough = normalise_borough(pc.get('admin_district'))
            location_meta.update({
                'postcode': pc.get('postcode'),
                'borough': borough,
                'longitude': pc.get('longitude'),
                'latitude': pc.get('latitude'),
                'region': pc.get('region'),
            })
        else:
            borough = normalise_borough(borough_input)
            location_meta['borough'] = borough

        if not borough or borough not in LONDON_BOROUGHS:
            return response(404, {
                'error': 'Borough not currently supported. London boroughs only in v1.',
                'attemptedBorough': borough_input or location_meta.get('borough'),
                'supportedBoroughs': sorted(LONDON_BOROUGHS.keys()),
            })

        # Resolve weights (explicit override > persona preset > balanced).
        if weights_override:
            weights = weights_override
            persona_label = 'custom'
        elif persona in PERSONAS:
            weights = PERSONAS[persona]
            persona_label = persona
        else:
            weights = PERSONAS['balanced']
            persona_label = 'balanced'

        score_data = calc_score(borough, weights)

        body = {
            **score_data,
            'location': location_meta,
            'persona': persona_label,
            'weights': weights,
            'methodologyVersion': METHODOLOGY_VERSION,
            'methodologyUrl': METHODOLOGY_URL,
            'apiVersion': '1.0',
            'generatedAt': datetime.now(timezone.utc).isoformat(),
            'sources': SOURCES,
        }
        return response(200, body)

    except Exception:
        return response(500, {'error': 'Internal server error'})


def response(status, body):
    return {
        'statusCode': status,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': CORS_ORIGIN,
            'Access-Control-Allow-Headers': 'Content-Type,X-Api-Key',
            'Access-Control-Allow-Methods': 'GET,OPTIONS',
        },
        'body': json.dumps(body),
    }
