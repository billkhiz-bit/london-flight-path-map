"""
Sky Score NHS Lambda, nearby NHS-relevant services for a given lat/lon.

Returns hospitals, pharmacies, GP surgeries (and clinics) within 1.5 km of a
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
# 1500 m, reduced from 3000 m on 2026-08-06. Measured at Collingham Road SW5:
# 3 km returns 187 elements, 1.5 km returns 66 — and MAX_RESULTS_PER_TYPE means
# we display 3 per category regardless, so the wider radius bought nothing and
# cost the timeouts above. 1.5 km still comfortably contains the nearest GP,
# pharmacy and hospital anywhere in urban London.
SEARCH_RADIUS_M = 1500
MAX_RESULTS_PER_TYPE = 5

# Reworded 2026-08-06. The previous string claimed results were "verified
# against NHS service-search where available". No such verification happens —
# nothing in this file contacts NHS Digital, and the NHS Service Search API has
# required a subscription key since before this Lambda was written. It also
# called them "NHS service locations", which OSM cannot support: `amenity=doctors`
# tags private clinics identically to NHS practices, so a search at Collingham
# Road SW5 returns "The Medical Chambers Kensington" and "Courtfield Private
# Practice" at the top. Both are real doctors; neither is an NHS GP surgery.
ATTRIBUTION = (
    'Healthcare locations: OpenStreetMap contributors (ODbL). '
    'OpenStreetMap does not distinguish NHS practices from private clinics, so both appear.'
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


def _log_coarse(lat, lon):
    """Coordinates for log lines at 2 dp (~1 km, district-sized), never full
    precision: 4 dp is ~11 m, finer than a postcode. privacy.html s2d promises
    this; backend/tests/test_log_privacy.py holds every Lambda to it.
    """
    try:
        return f'{float(lat):.2f},{float(lon):.2f}'
    except (TypeError, ValueError):
        return '?'


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


# --- Bundled snapshot: London 2026-08-06, every UK area we cover 2026-10-27 ---
#
# /nhs proxied Overpass on every request and kept falling back to nhs.uk links.
# The query was never the problem: the identical query with identical headers
# returns 200 in ~2s from a laptop. Lambda egress uses AWS-managed SHARED IPs,
# so we compete for Overpass's per-IP budget with everything else running on
# AWS. That is an address we do not control and cannot tune our way out of.
#
# Mirrors were tested and rejected. overpass.kumi.systems timed out at 60s, and
# overpass.osm.ch returned 200 with ZERO elements for a London query — which is
# the worst outcome available, because an empty success renders as "no
# healthcare nearby" rather than as an error.
#
# So the whole of Greater London shipped with the function (3,224 named POIs,
# 447 KB): no network call, no shared-IP lottery, and one bulk query against
# Overpass every few months instead of one per visitor — which is also a far
# politer way to use a service that costs us nothing.
#
# EVERY UK AREA SINCE 2026-10-27. Outside London every point still went to live
# Overpass, and in October the map's Manchester centre alone fell back to links
# 147 times, some after waiting up to 26 s (the duration alarm's main cause).
# scripts/fetch_healthcare.py now bundles each area the site or the API scores,
# its box DERIVED from that area's boundary file plus 3 km. Boxes overlap (Greater
# Manchester and Merseyside meet near Warrington), so a point reads every area
# whose box holds it and a service held by two is counted once.
#
# Coordinates outside every box still go to live Overpass, where nhs.uk fallback
# links remain the honest answer when it cannot reply.
_BUNDLE_PATH = os.path.join(os.path.dirname(__file__), 'healthcare.json')
_BUNDLE = None


def _load_bundle():
    """Read the snapshot once per container. Returns None if unreadable, which
    degrades to the live Overpass path rather than failing the request."""
    global _BUNDLE
    if _BUNDLE is None:
        try:
            with open(_BUNDLE_PATH, encoding='utf-8') as fh:
                _BUNDLE = json.load(fh)
        except (OSError, ValueError) as exc:
            logger.warning('[NHS_BUNDLE_UNREADABLE] %r', exc)
            _BUNDLE = False
    return _BUNDLE or None


def areas_holding(lat, lon):
    """The bundled areas whose box holds the point: none, one, or two where boxes overlap."""
    bundle = _load_bundle()
    if not bundle:
        return []
    return [a for a in bundle['areas']
            if a['bbox'][0] <= lat <= a['bbox'][2] and a['bbox'][1] <= lon <= a['bbox'][3]]


def in_bundle_area(lat, lon):
    return bool(areas_holding(lat, lon))


def from_bundle(lat, lon):
    """Nearest services from the bundled snapshot, same shape as Overpass.

    Only the areas holding the point are read (London's 3,224 haversines are
    microseconds), so there is no index to keep correct. A service inside two
    overlapping boxes is in both areas' lists and is counted once.
    """
    buckets = {'hospitals': [], 'pharmacies': [], 'gp': []}
    seen = set()

    for row in (row for area in areas_holding(lat, lon) for row in area['items']):
        key = (row['a'], row['n'], row['lat'], row['lon'])
        if key in seen:
            continue
        seen.add(key)
        category = AMENITY_TO_CATEGORY.get(row['a'])
        if not category:
            continue
        distance = haversine(lat, lon, row['lat'], row['lon'])
        if distance > SEARCH_RADIUS_M:
            continue
        buckets[category].append(
            {
                'name': row['n'],
                'address': row.get('ad', ''),
                'postcode': row.get('pc', ''),
                'phone': row.get('ph', ''),
                'website': row.get('w', ''),
                'distance': round(distance),
            }
        )

    for cat in buckets:
        buckets[cat].sort(key=lambda x: x['distance'])
        buckets[cat] = buckets[cat][:MAX_RESULTS_PER_TYPE]
    return buckets


def query_overpass(lat, lon):
    """Single Overpass query for all four amenity types in one round-trip.
    Returns parsed elements or raises HTTPError/URLError on failure."""
    # [timeout:N] is the OVERPASS-SIDE budget, not ours. At 10s this returned
    # 504 Gateway Timeout under load, which surfaced as "Live data unavailable"
    # on both the site's healthcare panel and the extension — reproduced from a
    # second IP on 2026-08-06, so it was the query cost, not our Lambda being
    # rate-limited. The same query at [timeout:25] returned 200 in ~3s.
    #
    # It must stay below the urlopen timeout below, which must stay below the
    # function Timeout in template.yaml (28s). Ordering matters: if Overpass's
    # budget exceeds ours we abandon a query it is still paying to run, which is
    # the least polite possible way to use a free shared service.
    query = (
        f'[out:json][timeout:25];'
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
    # 26s, not 30. It must sit ABOVE Overpass's own [timeout:25] budget so we
    # do not cut the upstream off just as it answers, and BELOW the function's
    # 28s ceiling so the fallback branch has room to build a response. At 30 it
    # sat above the ceiling, so a slow Overpass killed the whole invocation
    # instead of degrading to search links.
    with urlopen(req, timeout=26) as resp:
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


def none_nearby(service_type):
    """The HAPPY-PATH row for an empty bucket: Overpass answered, and maps
    nothing of this type within SEARCH_RADIUS_M. Distinct from
    fallback_links() by name, wording and flag (audit M16): until 2026-09-14
    an empty bucket after a SUCCESSFUL query carried `fallback: True`, so
    "no GP within 1.5 km here" and "we could not ask" were the same row,
    and a reader in a well-served village was told the service was down.
    Both renderers key on `link: True` to draw a link rather than a place."""
    km = SEARCH_RADIUS_M / 1000
    return [
        {
            'name': f'No {service_type} services within {km:g} km in OpenStreetMap - search nhs.uk',
            'website': NHS_SEARCH_PAGES.get(service_type, 'https://www.nhs.uk/'),
            'distance': None,
            'fallback': False,
            'noneNearby': True,
            'link': True,
        }
    ]


def fallback_links(service_type):
    """Return a single fallback row pointing at the canonical NHS search
    page when Overpass is unavailable. Used only when the upstream call
    fails; the happy path uses none_nearby() for an empty bucket."""
    return [
        {
            'name': f'Search NHS {service_type} services on nhs.uk',
            'website': NHS_SEARCH_PAGES.get(service_type, 'https://www.nhs.uk/'),
            'distance': None,
            'fallback': True,
            'link': True,
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

        # Every UK area we cover is served from the bundled snapshot: no network
        # call, so no shared-IP lottery and no fallback. See the block above
        # _load_bundle.
        #
        # AN EMPTY BUNDLE RESULT IS NOT AN ANSWER (audit finding I10, fixed
        # 2026-08-22, found on London's box alone). `in_bundle_area` tests
        # BOUNDING BOXES - London's was 51.25..51.72 by -0.55..0.35 - which reach
        # well into Surrey, Kent, Essex and Herts,
        # none of which the snapshot covers. Measured over a 24x24 grid of that
        # rectangle, 35.4% of points had no bundled service within 1500 m and
        # were being published as `available: true` with three empty lists:
        # "we checked, there is no GP, pharmacy or hospital near you". The
        # sibling Overpass path below, when IT cannot answer, returns fallback
        # links and `available: false` - so one branch admitted ignorance and
        # the other asserted absence, for the same missing data.
        #
        # Falling through rather than returning fallback links directly is
        # deliberate: outside the snapshot's real coverage Overpass usually DOES
        # have the data, and if it does not, the branch below already degrades
        # honestly. "A bounding box is not containment", recurring.
        if in_bundle_area(lat, lon):
            buckets = from_bundle(lat, lon)
            if any(buckets.values()):
                # An empty bucket beside a populated one is a measured "none
                # within 1.5 km" in the snapshot - the same row the Overpass
                # branch below publishes for the same finding (audit M16), so
                # the two paths cannot answer one meaning in two shapes.
                for cat, label in (('gp', 'GP'), ('pharmacies', 'Pharmacy'), ('hospitals', 'Hospital')):
                    if not buckets[cat]:
                        buckets[cat] = none_nearby(label)
                buckets.update(
                    {
                        'location': {'lat': lat, 'lon': lon},
                        'sources': [ATTRIBUTION],
                        'available': True,
                        'dataSource': 'bundled-snapshot',
                    }
                )
                return response(200, buckets)
            logger.info(
                'Inside the bundle bbox but no service within %sm; deferring to '
                'Overpass. near=%s',
                SEARCH_RADIUS_M,
                _log_coarse(lat, lon),
            )

        try:
            elements = query_overpass(lat, lon)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.warning(
                'Overpass unavailable, using fallback links. near=%s err=%s',
                _log_coarse(lat, lon),
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
                'gp': buckets['gp'] or none_nearby('GP'),
                'pharmacies': buckets['pharmacies'] or none_nearby('Pharmacy'),
                'hospitals': buckets['hospitals'] or none_nearby('Hospital'),
                'sources': [ATTRIBUTION],
                'available': True,
            },
        )

    except Exception as exc:  # pragma: no cover, final guard
        logger.exception('Unhandled exception in NHS handler: %s', exc)
        return response(500, {'error': 'Internal server error.'})


def response(status, body):
    if status >= 500:
        # [5XX] (2026-10-27): API Gateway counts a 5xx but cannot say whose, and a handler that RETURNS one logs
        # nothing else; backend/tests/test_5xx_logged.py holds every builder to this line.
        logger.warning('[5XX] %s %s', status, str(body.get('error', '') if isinstance(body, dict) else '')[:200])
    return {
        'statusCode': status,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': CORS_ORIGIN,
            'Strict-Transport-Security': 'max-age=31536000',
            'X-Content-Type-Options': 'nosniff',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'GET,OPTIONS',
        },
        'body': json.dumps(body),
    }
