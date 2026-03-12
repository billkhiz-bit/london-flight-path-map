import base64
import csv
import io
import json
import os
from urllib.parse import quote
from urllib.request import Request, urlopen


def handler(event, context):
    try:
        params = event.get('queryStringParameters') or {}
        postcode = params.get('postcode', '')

        if not postcode:
            return response(400, {'error': 'postcode parameter is required'})

        api_key = os.environ.get('EPC_API_KEY', '')
        api_email = os.environ.get('EPC_API_EMAIL', '')
        if not api_key or not api_email:
            return response(200, {
                'postcode': postcode,
                'available': False,
                'message': 'EPC API key not configured.'
            })

        clean = postcode.strip().upper()

        # EPC Open Data API - official UK government
        url = f'https://epc.opendatacommunities.org/api/v1/domestic/search?postcode={quote(clean)}&size=50'

        # API uses basic auth with email:api_key
        auth = base64.b64encode(f'{api_email}:{api_key}'.encode()).decode()

        # Request CSV format (JSON returns empty for this API)
        req = Request(url, headers={
            'Accept': 'text/csv',
            'Authorization': f'Basic {auth}'
        })

        with urlopen(req, timeout=10) as resp:
            raw = resp.read().decode()

        if not raw.strip():
            return response(200, {
                'postcode': postcode,
                'available': True,
                'count': 0,
                'certificates': [],
                'summary': None
            })

        # Parse CSV
        reader = csv.DictReader(io.StringIO(raw))
        rows = list(reader)

        if not rows:
            return response(200, {
                'postcode': postcode,
                'available': True,
                'count': 0,
                'certificates': [],
                'summary': None
            })

        # Aggregate stats
        bands = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0, 'F': 0, 'G': 0}
        ratings = []
        certs = []

        for row in rows:
            band = row.get('current-energy-rating', '').strip()
            if band in bands:
                bands[band] += 1
            rating_str = row.get('current-energy-efficiency', '').strip()
            if rating_str:
                try:
                    rating = int(rating_str)
                    ratings.append(rating)
                except ValueError:
                    rating = 0
            else:
                rating = 0

            certs.append({
                'address': row.get('address1', '').strip(),
                'band': band,
                'rating': rating,
                'type': row.get('property-type', '').strip(),
                'date': row.get('lodgement-date', '').strip(),
                'floorArea': row.get('total-floor-area', '').strip(),
                'heatingCost': row.get('heating-cost-current', '').strip(),
                'hotWaterCost': row.get('hot-water-cost-current', '').strip(),
                'lightingCost': row.get('lighting-cost-current', '').strip(),
            })

        avg_rating = round(sum(ratings) / len(ratings)) if ratings else 0
        avg_band = rating_to_band(avg_rating)
        modal_band = max(bands, key=bands.get) if any(bands.values()) else 'N/A'

        return response(200, {
            'postcode': postcode,
            'available': True,
            'count': len(rows),
            'summary': {
                'averageRating': avg_rating,
                'averageBand': avg_band,
                'mostCommonBand': modal_band,
                'bandDistribution': bands,
            },
            'certificates': certs[:10]
        })

    except Exception:
        return response(500, {'error': 'Internal server error'})


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
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'GET,OPTIONS'
        },
        'body': json.dumps(body)
    }
