import json
import logging
import math
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CORS_ORIGIN = os.environ.get('CORS_ORIGIN', '*')

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# TfL API - free, no key required (key optional for higher rate limits)
TFL_BASE = 'https://api.tfl.gov.uk'

ATTRIBUTION = (
    'Transport data powered by TfL Open Data. '
    'Contains OS data © Crown copyright and database rights 2016 and Geomni UK Map data © and database rights [2019].'
)


def handler(event, context):
    try:
        params = event.get('queryStringParameters') or {}
        lat = params.get('lat')
        lon = params.get('lon')

        if not lat or not lon:
            return response(400, {'error': 'lat and lon parameters are required'})

        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            return response(400, {'error': 'lat and lon must be numbers'})

        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return response(400, {'error': 'lat/lon out of range'})

        # 1. Find nearest stations (tube, rail, DLR) within 1km.
        # None means TfL was unreachable — distinct from "no stations nearby"
        # so the frontend never renders an outage as confident emptiness
        # (A-0724-I5).
        stations = fetch_nearby_stations(lat, lon)
        if stations is None:
            return response(
                200,
                {
                    'stations': [],
                    'lineStatus': [],
                    'location': {'lat': lat, 'lon': lon},
                    'available': False,
                    'note': 'Live transport data temporarily unavailable.',
                    'sources': [ATTRIBUTION],
                },
            )

        # 2. Get live line statuses for relevant lines
        line_ids = set()
        for s in stations:
            for line in s.get('lines', []):
                line_ids.add(line)
        line_status = fetch_line_status(list(line_ids)[:10]) if line_ids else []

        return response(
            200,
            {
                'stations': stations,
                'lineStatus': line_status,
                'location': {'lat': lat, 'lon': lon},
                'available': True,
                'sources': [ATTRIBUTION],
            },
        )

    except Exception as exc:  # pragma: no cover, final guard
        logger.exception('Unhandled exception in transport handler: %s', exc)
        return response(500, {'error': 'Internal server error'})


def fetch_nearby_stations(lat, lon):
    """Returns a list of nearby stations, or None when TfL is unreachable
    (callers must treat None as an upstream outage, not an empty area)."""
    url = f'{TFL_BASE}/StopPoint?lat={lat}&lon={lon}&stopTypes=NaptanMetroStation,NaptanRailStation&radius=1500'

    req = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'SkyScore/1.0'})
    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning('TfL StopPoint lookup failed: %s', exc)
        return None

    stops = data.get('stopPoints', [])
    results = []

    for stop in stops[:8]:
        dist = haversine(lat, lon, stop.get('lat', 0), stop.get('lon', 0))
        lines = []
        for lp in stop.get('lineModeGroups', []):
            lines.extend(lp.get('lineIdentifier', []))

        results.append(
            {
                'name': stop.get('commonName', ''),
                'distance': round(dist),
                'modes': [lp.get('modeName', '') for lp in stop.get('lineModeGroups', [])],
                'lines': lines,
                'lat': stop.get('lat'),
                'lon': stop.get('lon'),
            }
        )

    results.sort(key=lambda x: x['distance'])
    return results[:5]


def fetch_line_status(line_ids):
    if not line_ids:
        return []

    ids_str = ','.join(line_ids[:10])
    url = f'{TFL_BASE}/Line/{ids_str}/Status'

    req = Request(url, headers={'Accept': 'application/json'})
    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning('TfL Line/Status lookup failed: %s', exc)
        return []

    results = []
    for line in data:
        statuses = line.get('lineStatuses', [{}])
        results.append(
            {
                'name': line.get('name', ''),
                'id': line.get('id', ''),
                'mode': line.get('modeName', ''),
                'status': statuses[0].get('statusSeverityDescription', 'Unknown') if statuses else 'Unknown',
                'reason': statuses[0].get('reason', '')
                if statuses and statuses[0].get('statusSeverityDescription') != 'Good Service'
                else '',
            }
        )

    return results


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    p = math.pi / 180
    a = (
        0.5
        - math.cos((lat2 - lat1) * p) / 2
        + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def response(status, body):
    return {
        'statusCode': status,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': CORS_ORIGIN,
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'GET,OPTIONS',
        },
        'body': json.dumps(body),
    }
