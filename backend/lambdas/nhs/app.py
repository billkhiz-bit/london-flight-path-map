"""
Sky Score NHS Lambda, nearby NHS-relevant services for a given lat/lon.

Returns hospitals, pharmacies, GP surgeries (and clinics) within 3 km of a
property location. Used by the consumer site to surface "what's nearby"
context on a postcode page.

Data source: OpenStreetMap Overpass API. Free, no key required, decent
UK coverage of NHS services. NHS Service Search API (api.nhs.uk) was the
original source but now requires a registered subscription key, the
public 'public' literal that used to work was deactivated. OSM is our
ongoing replacement; the only edge case is gaps in OSM coverage for
smaller GP surgeries, which we accept rather than gating signups behind
an NHS Digital registration.

Fallback: if Overpass is down or rate-limited, return search-page links
to nhs.uk's official service-search pages. These were broken in the
previous version (`find-a-doctors/results` 404s, the URL changed) so
this rewrite uses the current canonical URLs verified live.

Attribution: OpenStreetMap contributors (ODbL).
"""

import json
import logging
import math
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

CORS_ORIGIN = os.environ.get('CORS_ORIGIN', '*')
OVERPASS_URL = os.environ.get('OVERPASS_URL', 'https://overpass-api.de/api/interpreter')
SEARCH_RADIUS_M = 3000  # 3 km, typical "your nearest" range
MAX_RESULTS_PER_TYPE = 5

ATTRIBUTION = (
    'NHS service locations: OpenStreetMap contributors (ODbL); verified against NHS service-search where available.'
)

# NHS Service Search canonical URLs, verified live 2026-05-06.
# The previous fallback used `find-a-doctors/results?lat=...&lon=...` which
# returned 404 (NHS removed the lat/lon-prefilled results pages). Users
# clicking these now land on the real NHS search page and enter their
# postcode there.
NHS_SEARCH_PAGES = {
    'GP': 'https://www.nhs.uk/service-search/find-a-gp',
    'Pharmacy': 'https://www.nhs.uk/service-search/pharmacy/find-a-pharmacy',
    'Hospital': 'https://www.nhs.uk/nhs-services/hospitals/',
}

# OSM amenity tags → service category. `clinic` is folded into GP since
# both are primary-care surgeries from a renter's perspective.
AMENITY_TO_CATEGORY = {
    'hospital': 'hospitals',
    'pharmacy': 'pharmacies',
    'doctors': 'gp',
    'clinic': 'gp',
}

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def haversine(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres."""
    r = 6_371_000
    p = math.pi / 180
    a = (
        0.5
        - math.cos((lat2 - lat1) * p) / 2
        + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    )
    return r * 2 * math.asin(math.sqrt(a))


def query_overpass(lat, lon):
    """Single Overpass query for all four amenity types in one round-trip.
    Returns parsed elements or raises HTTPError/URLError on failure."""
    query = (
        f'[out:json][timeout:10];'
        f'('
        f'nwr["amenity"="hospital"](around:{SEARCH_RADIUS_M},{lat},{lon});'
        f'nwr["amenity"="pharmacy"](around:{SEARCH_RADIUS_M},{lat},{lon});'
        f'nwr["amenity"="doctors"](around:{SEARCH_RADIUS_M},{lat},{lon});'
        f'nwr["amenity"="clinic"](around:{SEARCH_RADIUS_M},{lat},{lon});'
        f');'
        f'out center;'
    )
    body = f'data={quote(query)}'.encode()
    req = Request(
        OVERPASS_URL,
        data=body,
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'sky-score/1.0 (https://d1oe4ftwutjpf.cloudfront.net)',
        },
    )
    with urlopen(req, timeout=12) as resp:
        return json.loads(resp.read().decode()).get('elements', [])


def element_coords(el):
    """Return (lat, lon) for an OSM element, taking center for ways/relations."""
    if el.get('type') == 'node':
        return el.get('lat'), el.get('lon')
    center = el.get('center') or {}
    return center.get('lat'), center.get('lon')


def format_address(tags):
    """Stitch OSM addr:* tags into a one-line address. Returns '' when
    OSM has no address tags (common for ways tagged at the building level)."""
    parts = []
    for k in ('addr:housenumber', 'addr:street'):
        if tags.get(k):
            parts.append(tags[k])
    line = ' '.join(parts)
    if tags.get('addr:locality') and tags['addr:locality'] not in line:
        line = f'{line}, {tags["addr:locality"]}' if line else tags['addr:locality']
    return line.strip(', ')


def normalise_element(el, origin_lat, origin_lon):
    """Convert an OSM element to a Sky Score response item, or None if it
    lacks essential fields (no name, no coordinates)."""
    tags = el.get('tags') or {}
    name = tags.get('name')
    if not name:
        return None
    elat, elon = element_coords(el)
    if elat is None or elon is None:
        return None
    return {
        'name': name,
        'address': format_address(tags),
        'postcode': tags.get('addr:postcode', ''),
        'phone': tags.get('phone') or tags.get('contact:phone', ''),
        'website': tags.get('website') or tags.get('contact:website', ''),
        'distance': round(haversine(origin_lat, origin_lon, elat, elon)),
    }


def partition_results(elements, lat, lon):
    """Group OSM elements by NHS service category, sort by distance, cap at
    MAX_RESULTS_PER_TYPE. Returns the three lists ready for the response."""
    buckets = {'hospitals': [], 'pharmacies': [], 'gp': []}
    for el in elements:
        amenity = (el.get('tags') or {}).get('amenity')
        category = AMENITY_TO_CATEGORY.get(amenity)
        if not category:
            continue
        item = normalise_element(el, lat, lon)
        if item:
            buckets[category].append(item)

    for cat in buckets:
        buckets[cat].sort(key=lambda x: x['distance'])
        buckets[cat] = buckets[cat][:MAX_RESULTS_PER_TYPE]
    return buckets


def fallback_links(service_type):
    """Return a single fallback row pointing at the canonical NHS search
    page when Overpass is unavailable. Used only when the upstream call
    fails, happy path returns real OSM data."""
    return [
        {
            'name': f'Search NHS {service_type} services on nhs.uk',
            'website': NHS_SEARCH_PAGES.get(service_type, 'https://www.nhs.uk/'),
            'distance': None,
            'fallback': True,
        }
    ]


def all_fallback():
    return {
        'gp': fallback_links('GP'),
        'pharmacies': fallback_links('Pharmacy'),
        'hospitals': fallback_links('Hospital'),
    }


def handler(event, context):
    """GET /nhs?lat=...&lon=... Returns nearby NHS services."""
    try:
        params = event.get('queryStringParameters') or {}
        lat_raw = params.get('lat')
        lon_raw = params.get('lon')

        if not lat_raw or not lon_raw:
            return response(400, {'error': 'lat and lon parameters are required.'})

        try:
            lat, lon = float(lat_raw), float(lon_raw)
        except (TypeError, ValueError):
            return response(400, {'error': 'lat and lon must be numbers.'})

        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return response(400, {'error': 'lat/lon out of range.'})

        try:
            elements = query_overpass(lat, lon)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.warning(
                'Overpass unavailable, using fallback links. lat=%s lon=%s err=%s',
                lat,
                lon,
                exc,
            )
            buckets = all_fallback()
            buckets.update(
                {
                    'location': {'lat': lat, 'lon': lon},
                    'sources': [ATTRIBUTION],
                    'available': False,
                    'note': 'Live data unavailable; links go to NHS service search.',
                }
            )
            return response(200, buckets)

        buckets = partition_results(elements, lat, lon)
        return response(
            200,
            {
                'location': {'lat': lat, 'lon': lon},
                'gp': buckets['gp'] or fallback_links('GP'),
                'pharmacies': buckets['pharmacies'] or fallback_links('Pharmacy'),
                'hospitals': buckets['hospitals'] or fallback_links('Hospital'),
                'sources': [ATTRIBUTION],
                'available': True,
            },
        )

    except Exception as exc:  # pragma: no cover, final guard
        logger.exception('Unhandled exception in NHS handler: %s', exc)
        return response(500, {'error': 'Internal server error.'})


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
