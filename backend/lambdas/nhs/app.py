import json
import math
import os
from urllib.request import Request, urlopen

CORS_ORIGIN = os.environ.get('CORS_ORIGIN', '*')

ATTRIBUTION = (
    'NHS service data: NHS Service Search API (NHS Digital).'
)


def handler(event, context):
    try:
        params = event.get('queryStringParameters') or {}
        lat = params.get('lat')
        lon = params.get('lon')

        if not lat or not lon:
            return response(400, {'error': 'lat and lon parameters are required'})

        lat, lon = float(lat), float(lon)

        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return response(400, {'error': 'lat/lon out of range'})

        # NHS Service Search API - official, free, no key required
        # Search for GP surgeries near the location
        gp_results = search_nhs_services(lat, lon, 'GP')
        pharmacy_results = search_nhs_services(lat, lon, 'Pharmacy')
        hospital_results = search_nhs_services(lat, lon, 'Hospital')

        return response(200, {
            'location': {'lat': lat, 'lon': lon},
            'gp': gp_results,
            'pharmacies': pharmacy_results,
            'hospitals': hospital_results,
            'sources': [ATTRIBUTION],
        })

    except Exception:
        return response(500, {'error': 'Internal server error'})


def search_nhs_services(lat, lon, service_type):
    # NHS Service Search API
    url = (
        f'https://api.nhs.uk/service-search/search'
        f'?api-version=2'
        f'&search={service_type}'
        f'&latitude={lat}'
        f'&longitude={lon}'
        f'&distance=3'
        f'&top=5'
        f'&orderby=Distance'
    )

    req = Request(url, headers={
        'Accept': 'application/json',
        'subscription-key': 'public'
    })

    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        # Fallback: try the older directory API
        return search_nhs_fallback(lat, lon, service_type)

    results = []
    for item in data.get('value', []):
        dist = haversine(lat, lon,
                         item.get('Latitude', 0),
                         item.get('Longitude', 0))
        results.append({
            'name': item.get('OrganisationName', ''),
            'address': item.get('Address1', ''),
            'postcode': item.get('Postcode', ''),
            'phone': item.get('Phone', ''),
            'distance': round(dist),
            'acceptingPatients': item.get('AcceptingPatients', None),
            'url': item.get('URL', ''),
        })

    return results[:5]


def search_nhs_fallback(lat, lon, service_type):
    # Fallback using the NHS choices directory
    type_map = {'GP': 'doctors', 'Pharmacy': 'pharmacies', 'Hospital': 'hospitals'}
    nhs_type = type_map.get(service_type, 'doctors')

    url = f'https://www.nhs.uk/service-search/find-a-{nhs_type}/results?latitude={lat}&longitude={lon}'

    # Can't scrape - return a helpful link instead
    return [{
        'name': f'Search NHS {service_type} services',
        'url': url,
        'distance': None,
        'fallback': True
    }]


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    p = math.pi / 180
    a = 0.5 - math.cos((lat2-lat1)*p)/2 + math.cos(lat1*p)*math.cos(lat2*p)*(1-math.cos((lon2-lon1)*p))/2
    return R * 2 * math.asin(math.sqrt(a))


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
