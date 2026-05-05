import json
import os
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

CORS_ORIGIN = os.environ.get('CORS_ORIGIN', '*')

# New MHCLG service — see https://get-energy-performance-data.communities.gov.uk
# Replaces epc.opendatacommunities.org which retires 2026-05-30.
EPC_API_BASE = 'https://api.get-energy-performance-data.communities.gov.uk'
DOMESTIC_SEARCH_PATH = '/api/domestic/search'

# Search-response fields are a strict subset of the legacy CSV: only band,
# address, council, constituency, registration date, UPRN, certificate number.
# Numeric rating, property type, floor area, and cost fields are now only on
# the per-certificate detail endpoint (/api/certificate?certificate_number=...).
# Synthesise a numeric rating from band midpoints so downstream UI keeps working.
BAND_MIDPOINT = {'A': 95, 'B': 86, 'C': 75, 'D': 62, 'E': 47, 'F': 30, 'G': 10}

OGL_ATTRIBUTION = (
    'EPC data: Ministry of Housing, Communities and Local Government. '
    'Contains public sector information licensed under the Open Government Licence v3.0.'
)


def handler(event, context):
    try:
        params = event.get('queryStringParameters') or {}
        postcode = params.get('postcode', '')

        if not postcode:
            return response(400, {'error': 'postcode parameter is required'})

        bearer_token = os.environ.get('EPC_BEARER_TOKEN', '')
        if not bearer_token:
            return response(200, {
                'postcode': postcode,
                'available': False,
                'message': 'EPC bearer token not configured.',
                'sources': [OGL_ATTRIBUTION],
            })

        # API expects '+' for space (per docs example: ?postcode=LS1+4AP).
        clean = postcode.strip().upper().replace(' ', '+')
        url = f'{EPC_API_BASE}{DOMESTIC_SEARCH_PATH}?postcode={quote(clean, safe="+")}&page=50'

        req = Request(url, headers={
            'Accept': 'application/json',
            'Authorization': f'Bearer {bearer_token}',
        })

        try:
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
        except HTTPError as exc:
            if exc.code == 401:
                return response(200, {
                    'postcode': postcode,
                    'available': False,
                    'message': 'EPC bearer token is invalid or expired.',
                    'sources': [OGL_ATTRIBUTION],
                })
            if exc.code == 404:
                # Per docs: 404 means no certificates match, not endpoint missing.
                return response(200, {
                    'postcode': postcode,
                    'available': True,
                    'count': 0,
                    'certificates': [],
                    'summary': None,
                    'sources': [OGL_ATTRIBUTION],
                })
            if exc.code == 429:
                return response(429, {
                    'postcode': postcode,
                    'available': False,
                    'message': 'EPC API rate limit exceeded. Try again shortly.',
                    'sources': [OGL_ATTRIBUTION],
                })
            return response(502, {'error': f'EPC upstream error ({exc.code})'})
        except URLError:
            return response(504, {'error': 'EPC upstream unreachable'})

        rows = extract_rows(data)

        if not rows:
            return response(200, {
                'postcode': postcode,
                'available': True,
                'count': 0,
                'certificates': [],
                'summary': None,
                'sources': [OGL_ATTRIBUTION],
            })

        bands = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0, 'F': 0, 'G': 0}
        synthesised_ratings = []
        certs = []

        for row in rows:
            # New API: currentEnergyEfficiencyBand. Legacy fallback retained.
            band = pick(
                row,
                'currentEnergyEfficiencyBand',
                'currentEnergyRating',
                'current-energy-rating',
                '',
            ).strip().upper()

            if band in bands:
                bands[band] += 1
                synthesised_ratings.append(BAND_MIDPOINT[band])

            address = pick(row, 'addressLine1', 'address1', 'address', '').strip()

            certs.append({
                'address': address,
                'band': band,
                # Numeric rating is no longer in search responses — synthesise
                # from band midpoint so existing consumer-site UI keeps working.
                'rating': BAND_MIDPOINT.get(band, 0),
                # Fields below require a per-certificate fetch via /api/certificate;
                # left empty in the search response.
                'type': '',
                'date': pick(
                    row,
                    'registrationDate',
                    'lodgementDate',
                    'lodgement-date',
                    '',
                ).strip(),
                'floorArea': '',
                'heatingCost': '',
                'hotWaterCost': '',
                'lightingCost': '',
            })

        avg_rating = (
            round(sum(synthesised_ratings) / len(synthesised_ratings))
            if synthesised_ratings
            else 0
        )

        body = {
            'postcode': postcode,
            'available': True,
            'count': len(rows),
            'summary': {
                'averageRating': avg_rating,
                'averageBand': rating_to_band(avg_rating),
                'mostCommonBand': max(bands, key=bands.get) if any(bands.values()) else 'N/A',
                'bandDistribution': bands,
            },
            'certificates': certs[:10],
            'sources': [OGL_ATTRIBUTION],
        }

        if isinstance(data, dict) and isinstance(data.get('pagination'), dict):
            body['pagination'] = data['pagination']

        return response(200, body)

    except Exception:
        return response(500, {'error': 'Internal server error'})


def extract_rows(data):
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ('rows', 'results', 'data', 'items', 'certificates'):
        value = data.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            for inner in ('rows', 'results', 'items', 'certificates'):
                inner_value = value.get(inner)
                if isinstance(inner_value, list):
                    return inner_value
    return []


def pick(row, *keys_with_default):
    *keys, default = keys_with_default
    for key in keys:
        value = row.get(key) if isinstance(row, dict) else None
        if value not in (None, ''):
            return str(value) if not isinstance(value, str) else value
    return default


def rating_to_band(rating):
    if rating >= 92: return 'A'
    if rating >= 81: return 'B'
    if rating >= 69: return 'C'
    if rating >= 55: return 'D'
    if rating >= 39: return 'E'
    if rating >= 21: return 'F'
    return 'G'


def response(status, body):
    return {
        'statusCode': status,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': CORS_ORIGIN,
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'GET,OPTIONS'
        },
        'body': json.dumps(body)
    }
