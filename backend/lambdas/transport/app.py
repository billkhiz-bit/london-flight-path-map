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
                    # Statuses were never fetched, so this must not imply
                    # they were checked and found empty.
                    'lineStatusAvailable': False,
                    'note': 'Live transport data temporarily unavailable.',
                    'sources': [ATTRIBUTION],
                },
            )

        # 2. Get live line statuses for relevant lines.
        # None means the Status route was unreachable - the same contract the
        # stations half has had since A-0724-I5. Until 2026-08-24 the outage
        # collapsed into [] here, so a TfL 403 rendered as an empty disruption
        # list, indistinguishable from "every line is running normally".
        line_ids = set()
        for s in stations:
            for line in s.get('lines', []):
                line_ids.add(line)
        # NEVER ASKED IS NOT "ASKED AND NOTHING TO REPORT" (2026-08-31, F/I32).
        #
        # `... if line_ids else []` made line_status `[]` without calling TfL,
        # and `[] is not None` is True - so a stop with no line ids published
        # `lineStatusAvailable: true`, the machine-readable claim that the
        # status feed was consulted. Measured live across 12 city centres:
        # Manchester and Sheffield are tram-only, TfL's StopPoint serves their
        # Metrolink/Supertram stops with no lineModeGroups, and both reported
        # `true` on 0 lines. The lines exist; TfL does not publish their
        # metadata.
        #
        # The consequence on the site: renderTransportData computes
        # `lineStatusChecked = data.lineStatusAvailable !== false` -> true and
        # `lineStatusRows` -> false, so NEITHER the heading NOR the 2026-08-27
        # "could not be checked" notice renders. Silence, which that notice
        # exists to stop being read as "no disruptions".
        #
        # The old reasoning - "a station list whose stations carry no line ids
        # means there is genuinely nothing to report" - holds for a London stop
        # with no lines and is false for a tram stop. We did not ask; say so.
        if line_ids:
            line_status = fetch_line_status(list(line_ids))
        else:
            line_status = None

        # COMPAT: existing consumers (index.html, the extension) read
        # lineStatus as an array, so the outage case keeps lineStatus: [] and
        # says so in lineStatusAvailable rather than changing the field's
        # type. Consumers can upgrade to read the flag; none is required to.
        line_status_available = line_status is not None
        return response(
            200,
            {
                'stations': stations,
                'lineStatus': line_status if line_status_available else [],
                'lineStatusAvailable': line_status_available,
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


MAX_LINE_IDS = 40


def fetch_line_status(line_ids):
    """Live statuses for `line_ids`, or None when TfL is unreachable.

    None and [] are different facts: [] means "asked, nothing to report",
    None means "could not ask" - the distinction fetch_nearby_stations has
    carried since A-0724-I5 and this half of the file lacked until
    2026-08-24. Callers must not render None as an empty disruption list.
    """
    if not line_ids:
        return []

    # ONE CAP, IN ONE PLACE, AND HIGH ENOUGH NOT TO BITE (2026-08-31, audit
    # F20). This was `[:10]` here AND `list(line_ids)[:10]` at the call site -
    # capped twice - while King's Cross derives 14 line ids. TfL was asked about
    # ten of them, answered "Good Service" for those ten, and the response said
    # `lineStatusAvailable: true`: a partial answer published as a complete one,
    # with the dropped subset varying by set-iteration order. A suspended line
    # could be the one dropped.
    #
    # Raised rather than reported: a new `lineStatusPartial` field would be the
    # `lineStatusAvailable` mistake again - a field only its producer reads is
    # not a fix. 40 ids is roughly 400 URL characters and covers every
    # interchange on the network, so the truncation simply stops happening. The
    # cap survives as a safety valve and says so in the log if it ever fires.
    if len(line_ids) > MAX_LINE_IDS:
        logger.warning(
            'transport: %d line ids at this stop, asking about %d - raise MAX_LINE_IDS',
            len(line_ids), MAX_LINE_IDS,
        )
    ids_str = ','.join(line_ids[:MAX_LINE_IDS])
    url = f'{TFL_BASE}/Line/{ids_str}/Status'

    # THE USER-AGENT IS LOAD-BEARING. TfL answers 403 to urllib's default
    # `Python-urllib/3.x` on this route, and that 403 lands in the except
    # below - which until 2026-08-24 returned `[]`, an empty disruption list
    # indistinguishable from "every line is running normally". So this
    # endpoint had NEVER returned a line status. Verified live 2026-08-21:
    # Oxford Circus gave 5 stations and 0 statuses, and the same TfL URL
    # answers 403 without this header and 200 with it. The except now returns
    # None so an outage is at least NAMED, but the header is still what makes
    # the route answer at all.
    #
    # fetch_nearby_stations, eleven lines above, has always sent it - which is
    # why the stations half worked and the status half did not. Same mirrored-
    # pair trap as road_lden_from_row, and the same User-Agent trap CLAUDE.md
    # already records for the DEFRA host.
    req = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'SkyScore/1.0'})
    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning('TfL Line/Status lookup failed: %s', exc)
        return None

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
