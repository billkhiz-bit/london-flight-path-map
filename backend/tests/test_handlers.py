"""Handler-level smoke tests for the 9 Lambdas without dedicated test files.

Covers the cheap, high-leverage cases each handler should always get right:
- 400 on missing required params
- 401 on missing auth (favourites)
- 405 on unsupported methods
- 200 on the OPTIONS preflight
- 413 on oversized bodies (Bedrock endpoints)
- Validation rules for parsing inputs

Bedrock invocations and external HTTP calls are mocked / skipped, these
tests cover request-handling logic, not upstream integrations. The
upstream integrations are tested via live curl smoke-tests at deploy time.

Run from project root:
    python -m unittest backend.tests.test_handlers
"""

import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Make every Lambda's app module importable without spinning up boto3.
LAMBDAS_DIR = os.path.join(os.path.dirname(__file__), '..', 'lambdas')


def _import_lambda(name):
    """Import a Lambda's app module by name. Each Lambda is its own
    package-style folder; we add the folder to sys.path, import as 'app',
    then pop sys.modules so the next import is clean."""
    path = os.path.abspath(os.path.join(LAMBDAS_DIR, name))
    sys.path.insert(0, path)
    if 'app' in sys.modules:
        del sys.modules['app']
    try:
        import app # noqa: F401, pylint: disable=import-outside-toplevel
        return app
    finally:
        sys.path.pop(0)


# ---------- Score handler tests (in addition to test_score.py) ----------

class ScoreHandlerTests(unittest.TestCase):
    def setUp(self):
        self.app = _import_lambda('score')

    def test_options_returns_200(self):
        result = self.app.handler({'httpMethod': 'OPTIONS'}, None)
        self.assertEqual(result['statusCode'], 200)

    def test_get_no_params_returns_400(self):
        result = self.app.handler(
            {'httpMethod': 'GET', 'queryStringParameters': None}, None,
        )
        self.assertEqual(result['statusCode'], 400)

    def test_batch_invalid_json_returns_400(self):
        result = self.app.handler(
            {'httpMethod': 'POST', 'body': 'not-json'}, None,
        )
        self.assertEqual(result['statusCode'], 400)

    def test_batch_missing_queries_returns_400(self):
        result = self.app.handler(
            {'httpMethod': 'POST', 'body': '{}'}, None,
        )
        self.assertEqual(result['statusCode'], 400)


# ---------- Favourites, requires X-Device-Token (audit C3) ----------

class FavouritesHandlerTests(unittest.TestCase):
    def setUp(self):
        self.app = _import_lambda('favourites')

    def test_options_returns_200(self):
        result = self.app.handler({'httpMethod': 'OPTIONS', 'headers': {}}, None)
        self.assertEqual(result['statusCode'], 200)

    def test_get_without_token_returns_401(self):
        result = self.app.handler(
            {'httpMethod': 'GET', 'headers': {}}, None,
        )
        self.assertEqual(result['statusCode'], 401)

    def test_get_with_invalid_token_returns_401(self):
        result = self.app.handler(
            {'httpMethod': 'GET',
             'headers': {'X-Device-Token': 'not-a-uuid'}},
            None,
        )
        self.assertEqual(result['statusCode'], 401)

    def test_uuid_format_accepted(self):
        # Token validates, but DynamoDB call would happen; mock it.
        good_token = '550e8400-e29b-41d4-a716-446655440000'
        canonical = self.app.get_device_token(
            {'headers': {'X-Device-Token': good_token}},
        )
        self.assertEqual(canonical, '550e8400e29b41d4a716446655440000')

    def test_bare_hex_token_accepted(self):
        canonical = self.app.get_device_token(
            {'headers': {'X-Device-Token': 'a' * 32}},
        )
        self.assertEqual(canonical, 'a' * 32)


# ---------- Signup, POST creates key, idempotent on email ----------

class SignupHandlerTests(unittest.TestCase):
    def setUp(self):
        self.app = _import_lambda('signup')

    def test_options_returns_200(self):
        result = self.app.handler({'httpMethod': 'OPTIONS'}, None)
        self.assertEqual(result['statusCode'], 200)

    def test_post_no_body_returns_400(self):
        result = self.app.handler(
            {'httpMethod': 'POST', 'body': ''}, None,
        )
        self.assertEqual(result['statusCode'], 400)

    def test_post_invalid_email_returns_400(self):
        result = self.app.handler(
            {'httpMethod': 'POST', 'body': json.dumps({'email': 'nope'})},
            None,
        )
        self.assertEqual(result['statusCode'], 400)

    def test_post_oversized_email_returns_400(self):
        result = self.app.handler(
            {'httpMethod': 'POST',
             'body': json.dumps({'email': 'a' * 300 + '@example.com'})},
            None,
        )
        self.assertEqual(result['statusCode'], 400)

    def test_get_returns_405(self):
        result = self.app.handler({'httpMethod': 'GET'}, None)
        self.assertEqual(result['statusCode'], 405)


# ---------- NHS, lat/lon validation, fallback shape ----------

class NhsHandlerTests(unittest.TestCase):
    def setUp(self):
        self.app = _import_lambda('nhs')

    def test_missing_params_returns_400(self):
        result = self.app.handler({'queryStringParameters': None}, None)
        self.assertEqual(result['statusCode'], 400)

    def test_non_numeric_returns_400(self):
        result = self.app.handler(
            {'queryStringParameters': {'lat': 'abc', 'lon': 'def'}}, None,
        )
        self.assertEqual(result['statusCode'], 400)

    def test_lat_out_of_range_returns_400(self):
        result = self.app.handler(
            {'queryStringParameters': {'lat': '999', 'lon': '0'}}, None,
        )
        self.assertEqual(result['statusCode'], 400)

    def test_partition_results_groups_by_amenity(self):
        elements = [
            {'type': 'node', 'lat': 51.5, 'lon': -0.1,
             'tags': {'amenity': 'hospital', 'name': 'St Bart\'s'}},
            {'type': 'node', 'lat': 51.51, 'lon': -0.11,
             'tags': {'amenity': 'pharmacy', 'name': 'Boots'}},
            {'type': 'node', 'lat': 51.52, 'lon': -0.12,
             'tags': {'amenity': 'doctors', 'name': 'GP Surgery'}},
        ]
        out = self.app.partition_results(elements, 51.5, -0.1)
        self.assertEqual(len(out['hospitals']), 1)
        self.assertEqual(len(out['pharmacies']), 1)
        self.assertEqual(len(out['gp']), 1)


# ---------- Sold Prices, postcode validation ----------

class SoldPricesHandlerTests(unittest.TestCase):
    def setUp(self):
        self.app = _import_lambda('sold_prices')

    def test_missing_postcode_returns_400(self):
        result = self.app.handler({'queryStringParameters': None}, None)
        self.assertEqual(result['statusCode'], 400)


# ---------- Transport, lat/lon validation ----------

class TransportHandlerTests(unittest.TestCase):
    def setUp(self):
        self.app = _import_lambda('transport')

    def test_missing_params_returns_400(self):
        result = self.app.handler({'queryStringParameters': None}, None)
        self.assertEqual(result['statusCode'], 400)

    def test_lat_out_of_range_returns_400(self):
        result = self.app.handler(
            {'queryStringParameters': {'lat': '200', 'lon': '0'}}, None,
        )
        self.assertEqual(result['statusCode'], 400)


# ---------- Chat, body size + validation ----------

class ChatHandlerTests(unittest.TestCase):
    def setUp(self):
        self.app = _import_lambda('chat')

    def test_oversized_body_returns_413(self):
        result = self.app.handler(
            {'httpMethod': 'POST',
             'body': '{"message":"' + 'x' * 70_000 + '"}'},
            None,
        )
        self.assertEqual(result['statusCode'], 413)

    def test_invalid_json_returns_400(self):
        result = self.app.handler(
            {'httpMethod': 'POST', 'body': 'not-json'}, None,
        )
        self.assertEqual(result['statusCode'], 400)

    def test_no_message_returns_400(self):
        result = self.app.handler(
            {'httpMethod': 'POST', 'body': '{}'}, None,
        )
        self.assertEqual(result['statusCode'], 400)


# ---------- Multi-agent, body size + validation ----------

class MultiAgentHandlerTests(unittest.TestCase):
    def setUp(self):
        self.app = _import_lambda('multi_agent')

    def test_oversized_body_returns_413(self):
        result = self.app.handler(
            {'httpMethod': 'POST',
             'body': '{"message":"' + 'x' * 70_000 + '"}'},
            None,
        )
        self.assertEqual(result['statusCode'], 413)

    def test_invalid_json_returns_400(self):
        result = self.app.handler(
            {'httpMethod': 'POST', 'body': 'not-json'}, None,
        )
        self.assertEqual(result['statusCode'], 400)


# ---------- Report, body size ----------

class ReportHandlerTests(unittest.TestCase):
    def setUp(self):
        self.app = _import_lambda('report')

    def test_oversized_body_returns_413(self):
        result = self.app.handler(
            {'httpMethod': 'POST',
             'body': '{"locationData":{"x":"' + 'x' * 70_000 + '"}}'},
            None,
        )
        self.assertEqual(result['statusCode'], 413)

    def test_invalid_json_returns_400(self):
        result = self.app.handler(
            {'httpMethod': 'POST', 'body': 'not-json'}, None,
        )
        self.assertEqual(result['statusCode'], 400)


# ---------- EPC, validation ----------

class EpcHandlerTests(unittest.TestCase):
    def setUp(self):
        self.app = _import_lambda('epc')

    def test_missing_postcode_returns_400(self):
        result = self.app.handler({'queryStringParameters': None}, None)
        self.assertEqual(result['statusCode'], 400)


# ---------- Live flights, OpenSky proxy + caching (audit N-Code-3) ----------

class LiveFlightsHandlerTests(unittest.TestCase):
    def setUp(self):
        self.app = _import_lambda('live_flights')
        # Reset module-level caches between tests so one test's success
        # doesn't poison the next.
        self.app._cache.clear()
        self.app._token_cache['access_token'] = None
        self.app._token_cache['expires_at'] = 0.0

    def test_unsupported_city_returns_400(self):
        result = self.app.handler(
            {'queryStringParameters': {'city': 'tokyo'}}, None,
        )
        self.assertEqual(result['statusCode'], 400)
        body = json.loads(result['body'])
        self.assertIn('supportedCities', body)
        self.assertIn('london', body['supportedCities'])
        self.assertIn('nyc', body['supportedCities'])

    def test_default_city_is_london(self):
        # No city param → defaults to london; mock the upstream so we don't
        # actually hit OpenSky during the test run.
        with patch.object(self.app, '_fetch_opensky',
                          return_value=({'states': [], 'time': 1700000000}, None)):
            result = self.app.handler({'queryStringParameters': None}, None)
        self.assertEqual(result['statusCode'], 200)
        body = json.loads(result['body'])
        self.assertEqual(body['city'], 'london')

    def test_normalise_states_drops_ground_and_no_position(self):
        # OpenSky positional state schema:
        # 0=icao24 1=callsign 2=country 3=time_pos 4=last_contact
        # 5=lon 6=lat 7=baro_alt 8=on_ground 9=velocity 10=track 11=vert_rate
        raw = {'states': [
            ['abc123', 'BAW123  ', 'GB', 0, 0, -0.45, 51.47,  300, False, 80, 90, 0],
            ['def456', 'GROUND  ', 'GB', 0, 0, -0.45, 51.47,    0, True,   0, 0, 0],
            ['ghi789', 'NOPOS   ', 'GB', 0, 0, None,  None,   500, False, 80, 0, 0],
        ]}
        out = self.app._normalise_states(raw)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['icao'], 'abc123')
        self.assertEqual(out[0]['callsign'], 'BAW123')

    def test_normalise_handles_empty_payload(self):
        self.assertEqual(self.app._normalise_states(None), [])
        self.assertEqual(self.app._normalise_states({}), [])
        self.assertEqual(self.app._normalise_states({'states': None}), [])

    def test_get_access_token_returns_none_without_credentials(self):
        # Credentials env vars empty by default in test env. Skips the
        # network call and returns None so caller falls back to anonymous.
        with patch.object(self.app, 'OPENSKY_CLIENT_ID', ''), \
             patch.object(self.app, 'OPENSKY_CLIENT_SECRET', ''):
            self.assertIsNone(self.app._get_access_token())

    def test_token_cache_returns_cached_token_when_fresh(self):
        # Pre-populate the cache with a token that expires in 30 minutes.
        self.app._token_cache['access_token'] = 'cached-token-xyz'
        self.app._token_cache['expires_at'] = 9999999999.0
        with patch.object(self.app, 'OPENSKY_CLIENT_ID', 'id'), \
             patch.object(self.app, 'OPENSKY_CLIENT_SECRET', 'secret'), \
             patch.object(self.app, 'urlopen') as mock_open:
            self.assertEqual(self.app._get_access_token(), 'cached-token-xyz')
            mock_open.assert_not_called()  # cache hit, no network

    def test_fetch_failure_no_cache_returns_unavailable(self):
        # First call, no warm cache, upstream fails → 200 with available=False
        # plus the upstream error string surfaced to the client (audit N-Code-6).
        with patch.object(self.app, '_fetch_opensky',
                          return_value=(None, 'TimeoutError: read timed out')):
            result = self.app.handler(
                {'queryStringParameters': {'city': 'london'}}, None,
            )
        self.assertEqual(result['statusCode'], 200)
        body = json.loads(result['body'])
        self.assertFalse(body['available'])
        self.assertEqual(body['count'], 0)
        self.assertEqual(body['upstreamError'], 'TimeoutError: read timed out')

    def test_fetch_failure_with_cache_serves_stale(self):
        # Cache from a prior good call → upstream fails → serve cached
        # payload with stale=True and the new fetch's error annotation.
        good_payload = {'flights': [{'icao': 'abc'}], 'count': 1, 'city': 'london',
                        'available': True, 'sources': ['…']}
        self.app._cache['london'] = (1.0, good_payload)  # ancient timestamp
        with patch.object(self.app, '_fetch_opensky',
                          return_value=(None, 'HTTPError 503: Service Unavailable')):
            result = self.app.handler(
                {'queryStringParameters': {'city': 'london'}}, None,
            )
        body = json.loads(result['body'])
        self.assertEqual(result['statusCode'], 200)
        self.assertTrue(body['stale'])
        self.assertEqual(body['count'], 1)
        self.assertEqual(body['upstreamError'], 'HTTPError 503: Service Unavailable')

    def test_cache_hit_skips_upstream(self):
        import time as time_mod
        fresh_payload = {'flights': [], 'count': 0, 'city': 'london',
                         'available': True, 'sources': ['…']}
        # Timestamp = now, so well within CACHE_TTL_SEC.
        self.app._cache['london'] = (time_mod.time(), fresh_payload)
        with patch.object(self.app, '_fetch_opensky') as mock_fetch:
            result = self.app.handler(
                {'queryStringParameters': {'city': 'london'}}, None,
            )
            mock_fetch.assert_not_called()
        self.assertEqual(result['statusCode'], 200)


if __name__ == '__main__':
    unittest.main()
