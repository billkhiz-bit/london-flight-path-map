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

    def test_cors_origin_echoed_for_allowlisted(self):
        # Allowed origin should be echoed back (not '*'), per N-Sec-4 lockdown.
        result = self.app.handler(
            {'httpMethod': 'OPTIONS',
             'headers': {'Origin': 'https://skyscore.co.uk'}},
            None,
        )
        self.assertEqual(result['headers']['Access-Control-Allow-Origin'],
                         'https://skyscore.co.uk')

    def test_cors_origin_canonical_fallback_for_unknown(self):
        # Hostile / unknown origin should fall back to the canonical site,
        # NOT echo the requester's origin and NOT use '*'.
        result = self.app.handler(
            {'httpMethod': 'OPTIONS',
             'headers': {'Origin': 'https://evil.example.com'}},
            None,
        )
        self.assertEqual(result['headers']['Access-Control-Allow-Origin'],
                         'https://skyscore.co.uk')
        self.assertNotEqual(result['headers']['Access-Control-Allow-Origin'], '*')

    def test_cors_origin_canonical_fallback_when_no_origin(self):
        # No Origin header at all (server-to-server, curl, etc.) → canonical.
        result = self.app.handler({'httpMethod': 'OPTIONS', 'headers': {}}, None)
        self.assertEqual(result['headers']['Access-Control-Allow-Origin'],
                         'https://skyscore.co.uk')

    def test_cors_origin_lowercase_header_also_works(self):
        # API Gateway can deliver headers as either 'Origin' or 'origin'
        # depending on stage / proxy; both must be honoured.
        result = self.app.handler(
            {'httpMethod': 'OPTIONS',
             'headers': {'origin': 'https://www.skyscore.co.uk'}},
            None,
        )
        self.assertEqual(result['headers']['Access-Control-Allow-Origin'],
                         'https://www.skyscore.co.uk')

    def test_safe_revoke_orphan_key_refuses_non_prefix(self):
        # Belt-and-braces guard alongside the IAM tag-condition (N-Code-1):
        # if get_api_key returns a key whose name doesn't start with
        # KEY_NAME_PREFIX, _safe_revoke_orphan_key must NOT call delete_api_key.
        # Mocked since unit tests don't touch live AWS.
        with patch.object(self.app.apigw, 'get_api_key',
                          return_value={'name': 'NotOurPrefix-attacker-controlled'}), \
             patch.object(self.app.apigw, 'delete_api_key') as mock_delete:
            self.app._safe_revoke_orphan_key('some-key-id')
            mock_delete.assert_not_called()  # the prefix guard fired

    def test_safe_revoke_orphan_key_proceeds_for_own_prefix(self):
        # Conversely: a key whose name starts with KEY_NAME_PREFIX is
        # eligible for delete (plus the IAM tag-condition would also apply).
        with patch.object(self.app.apigw, 'get_api_key',
                          return_value={'name': self.app.KEY_NAME_PREFIX + 'user_at_example_com'}), \
             patch.object(self.app.apigw, 'delete_api_key') as mock_delete:
            self.app._safe_revoke_orphan_key('legitimate-key-id')
            mock_delete.assert_called_once_with(apiKey='legitimate-key-id')


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


# ChatHandlerTests / MultiAgentHandlerTests / ReportHandlerTests removed
# 2026-05-07 along with their Lambda directories. All five Bedrock-backed
# Lambdas (chat, multi_agent, analyze_image, analyze_document, report)
# were deleted; restoring is a `git revert` away. See LICENSING.md
# "Removed sources" / CHANGELOG for context.


# ---------- EPC, validation ----------

class EpcHandlerTests(unittest.TestCase):
    def setUp(self):
        self.app = _import_lambda('epc')

    def test_missing_postcode_returns_400(self):
        result = self.app.handler({'queryStringParameters': None}, None)
        self.assertEqual(result['statusCode'], 400)


if __name__ == '__main__':
    unittest.main()
