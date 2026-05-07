"""
Sky Score live-flights proxy Lambda.

  GET /live-flights?city=london   → live aircraft over London
  GET /live-flights?city=nyc      → live aircraft over New York

Proxies OpenSky Network's /api/states/all endpoint with our own CORS
headers. Required because OpenSky now restricts browser CORS to
https://opensky-network.org — direct fetches from skyscore.co.uk are
blocked by the browser. The previous front-end code (which fetched
the API directly) silently broke when OpenSky tightened CORS.

In-memory caching: response is cached per-city for CACHE_TTL_SEC so
multiple concurrent visitors don't spam OpenSky's anonymous tier
(which has tight per-IP rate limits). Lambda container persistence is
~15 min on AWS, so the cache lives across calls within a warm window.

Anonymous access still works for the OpenSky bbox query, but if we hit
rate limits we can later add OAuth2 client credentials via env vars.

Audit hardening (matches the rest of the Lambdas in this codebase):
- Specific exception types + structured `logger.exception` final guard
- No bare except
- CORS_ORIGIN env var honoured
"""

import json
import logging
import os
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

CORS_ORIGIN = os.environ.get('CORS_ORIGIN', '*')
OPENSKY_URL = 'https://opensky-network.org/api/states/all'
OPENSKY_TOKEN_URL = 'https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token'
CACHE_TTL_SEC = int(os.environ.get('LIVE_FLIGHTS_CACHE_TTL', '12'))

# OAuth2 client credentials flow (added 2026-05 — anonymous access from
# AWS Lambda IPs hard-times-out, so we authenticate). Set these env vars
# in template.yaml or via SSM. If unset, we fall back to anonymous (which
# will likely time out on AWS but still works from CLI for development).
OPENSKY_CLIENT_ID = os.environ.get('OPENSKY_CLIENT_ID', '')
OPENSKY_CLIENT_SECRET = os.environ.get('OPENSKY_CLIENT_SECRET', '')

# In-memory token cache. OpenSky access tokens are valid for 30 min;
# we refresh slightly earlier to avoid edge-case expiry mid-request.
_token_cache = {'access_token': None, 'expires_at': 0.0}

# Bounding boxes per supported city. OpenSky's /states/all takes
# lamin/lomin/lamax/lomax (south, west, north, east). Boxes match the
# consumer site's previous client-side bounding boxes.
CITY_BBOX = {
    'london': {'lamin': 51.15, 'lomin': -0.6, 'lamax': 51.85, 'lomax': 0.4},
    'nyc':    {'lamin': 40.45, 'lomin': -74.3, 'lamax': 40.95, 'lomax': -73.6},
}

ATTRIBUTION = (
    'Live aircraft positions: OpenSky Network (https://opensky-network.org). '
    'Data provided "as is" by OpenSky contributors; coverage gaps and delays '
    'are normal at night and over rural areas.'
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_cache = {}  # {city: (timestamp, payload)} — survives warm-container lifetime


def _get_access_token():
    """Fetch (or return cached) OpenSky OAuth2 access token. Returns None
    if credentials aren't configured (caller falls back to anonymous)."""
    if not OPENSKY_CLIENT_ID or not OPENSKY_CLIENT_SECRET:
        return None
    now = time.time()
    if _token_cache['access_token'] and _token_cache['expires_at'] > now + 60:
        return _token_cache['access_token']

    body = urlencode({
        'grant_type': 'client_credentials',
        'client_id': OPENSKY_CLIENT_ID,
        'client_secret': OPENSKY_CLIENT_SECRET,
    }).encode()
    req = Request(OPENSKY_TOKEN_URL, data=body, headers={
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
    })
    try:
        with urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode())
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning('OpenSky token fetch failed: %s', exc)
        return None

    token = payload.get('access_token')
    expires_in = payload.get('expires_in', 1800)  # default 30 min
    if token:
        _token_cache['access_token'] = token
        _token_cache['expires_at'] = now + expires_in
    return token


def _fetch_opensky(bbox):
    """Hit OpenSky and return (payload, error). Exactly one of the two is
    non-None: payload is the parsed JSON on success, error is a short
    diagnostic string on any failure so the caller can include it in the
    response envelope.

    Audit N-Code-6: previously stashed `last_error` on a function attribute
    for cross-call inspection, which races on warm containers under
    concurrent invocations and hides errors from the cache-hit path. The
    explicit tuple return is race-safe and makes the contract obvious.
    """
    url = f'{OPENSKY_URL}?{urlencode(bbox)}'
    headers = {
        'Accept': 'application/json',
        'User-Agent': 'sky-score/1.0 (+https://skyscore.co.uk)',
    }
    # Authenticated requests bypass the anonymous-tier throttling that
    # otherwise blocks AWS Lambda IPs entirely.
    token = _get_access_token()
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = Request(url, headers=headers)
    try:
        # 12s rather than 8 — OpenSky throttles AWS IPs heavily on their
        # anonymous tier. With OAuth2 token, response is typically <1s.
        with urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode()), None
    except HTTPError as exc:
        err = f'HTTPError {exc.code}: {exc.reason}'
        logger.warning('OpenSky HTTP error: %s', err)
        return None, err
    except URLError as exc:
        err = f'URLError: {exc.reason}'
        logger.warning('OpenSky URL error: %s', err)
        return None, err
    except TimeoutError as exc:
        err = f'TimeoutError: {exc}'
        logger.warning('OpenSky timeout: %s', err)
        return None, err
    except json.JSONDecodeError as exc:
        err = f'JSONDecodeError: {exc}'
        logger.warning('OpenSky returned non-JSON: %s', err)
        return None, err


def _normalise_states(raw):
    """Convert OpenSky's positional-array states into named-field dicts.
    Mirrors the previous client-side normalisation in index.html so the
    frontend rendering code doesn't need changes."""
    if not raw or not raw.get('states'):
        return []
    out = []
    for s in raw['states']:
        # OpenSky state schema (positional):
        # 0=icao24 1=callsign 2=country 3=time_position 4=last_contact
        # 5=longitude 6=latitude 7=baro_altitude 8=on_ground 9=velocity
        # 10=true_track 11=vertical_rate ... rest unused
        if s[5] is None or s[6] is None or s[8]:  # skip ground / no-position
            continue
        out.append({
            'icao': s[0],
            'callsign': (s[1] or '').strip(),
            'lon': s[5],
            'lat': s[6],
            'altitude': round(s[7] * 3.28084) if s[7] else None,  # m → ft
            'speed':    round(s[9] * 1.944) if s[9] else None,    # m/s → knots
            'track':    s[10] or 0,
            'vertRate': s[11] or 0,
        })
    return out


def handler(event, context):
    try:
        params = event.get('queryStringParameters') or {}
        city = (params.get('city') or 'london').strip().lower()

        if city not in CITY_BBOX:
            return _response(400, {
                'error': f'Unsupported city: {city}',
                'supportedCities': sorted(CITY_BBOX.keys()),
            })

        # Cache hit?
        now = time.time()
        cached = _cache.get(city)
        if cached and (now - cached[0]) < CACHE_TTL_SEC:
            return _response(200, cached[1])

        raw, err = _fetch_opensky(CITY_BBOX[city])
        if raw is None:
            # Upstream failed — serve last good cache if we have one,
            # annotated with the fresh-fetch error so debug clients can
            # see why the cache is being served (audit N-Code-6).
            if cached:
                return _response(200, {**cached[1], 'stale': True, 'upstreamError': err})
            return _response(200, {
                'flights': [],
                'count': 0,
                'available': False,
                'note': 'Live aircraft data temporarily unavailable.',
                'upstreamError': err,
                'sources': [ATTRIBUTION],
            })

        flights = _normalise_states(raw)
        payload = {
            'flights': flights,
            'count': len(flights),
            'city': city,
            'available': True,
            'fetchedAt': raw.get('time'),
            'sources': [ATTRIBUTION],
        }
        _cache[city] = (now, payload)
        return _response(200, payload)

    except Exception as exc:  # pragma: no cover  — final guard
        logger.exception('Unhandled exception in live_flights handler: %s', exc)
        return _response(500, {'error': 'Internal server error'})


def _response(status, body):
    return {
        'statusCode': status,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': CORS_ORIGIN,
            'Access-Control-Allow-Methods': 'GET,OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            # Browser-side cache hint matches our server-side TTL so the
            # browser doesn't re-request more often than the data refreshes.
            'Cache-Control': f'public, max-age={CACHE_TTL_SEC}',
        },
        'body': json.dumps(body),
    }
