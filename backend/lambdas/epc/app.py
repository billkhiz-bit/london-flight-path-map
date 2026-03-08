import json
import os
import base64
from urllib.request import urlopen, Request
from urllib.parse import quote


def handler(event, context):
    try:
        params = event.get('queryStringParameters') or {}
        postcode = params.get('postcode', '')

        if not postcode:
            return response(400, {'error': 'postcode parameter is required'})

        api_key = os.environ.get('EPC_API_KEY', '')
        if not api_key:
            return response(200, {
                'postcode': postcode,
                'available': False,
                'message': 'EPC API key not configured. Register free at epc.opendatacommunities.org'
            })

        clean = postcode.strip().upper()

        # EPC Open Data API - official UK government
        url = f'https://epc.opendatacommunities.org/api/v1/domestic/search?postcode={quote(clean)}&size=50'

        # API uses basic auth with empty username and API key as password
        auth = base64.b64encode(f':{api_key}'.encode()).decode()

        req = Request(url, headers={
            'Accept': 'application/json',
            'Authorization': f'Basic {auth}'
        })

        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        rows = data.get('rows', [])

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
            band = row.get('current-energy-rating', '')
            if band in bands:
                bands[band] += 1
            rating = row.get('current-energy-efficiency', 0)
            if rating:
                ratings.append(int(rating))

            certs.append({
                'address': row.get('address1', ''),
                'band': band,
                'rating': rating,
                'type': row.get('property-type', ''),
                'date': row.get('lodgement-date', ''),
                'floorArea': row.get('total-floor-area', ''),
                'heatingCost': row.get('heating-cost-current', ''),
                'hotWaterCost': row.get('hot-water-cost-current', ''),
                'lightingCost': row.get('lighting-cost-current', ''),
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

    except Exception as e:
        return response(500, {'error': str(e)})


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
