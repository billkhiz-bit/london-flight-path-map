"""Malformed input and upstream faults answer with the truth, not a 5xx or a lie.

The 13 Sep 2026 audit's backend Minors (M2, M3, M13, M15, M16), closed on
14 Sep. Each test here was RED against the committed Lambdas before the fix:

  M13  a denied GetItem on the signups table returned None, which the handler
       read as "no row" - so a KEY HOLDER using the consumer form got 200
       "already-subscribed" for a list they are not on, and nothing was logged.
  M2   a BotoCoreError (transport fault, not an AWS error) after the API key
       had been created escaped as a raw 500: an enabled key with no row and a
       caller who never received it. The create step also echoed AWS error
       codes into the body of an unauthenticated endpoint.
  M3   `[]` as the batch body and a non-object / non-string-postcode DELETE on
       favourites raised on `.get` and answered 500 / 503 for a bad request.
  M15  chat built a boto3 client per request, twice, under a comment saying
       the clients had been hoisted.
  M16  /nhs answered a SUCCESSFUL Overpass query with an empty bucket using
       the OUTAGE row (`fallback: True`), so "none within 1.5 km" and "we could
       not ask" were one shape.

Offline: no AWS. Clients and tables are patched at the boundary.
"""

import importlib.util
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError, EndpointConnectionError

LAMBDAS_DIR = os.path.join(os.path.dirname(__file__), '..', 'lambdas')


def load_lambda(name, alias):
    """Import backend/lambdas/<name>/app.py under its own alias - the
    backend suite is not a package, so it cannot borrow tests/conftest's."""
    if alias in sys.modules:
        return sys.modules[alias]
    spec = importlib.util.spec_from_file_location(alias, os.path.join(LAMBDAS_DIR, name, 'app.py'))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


def _denied(op):
    return ClientError({'Error': {'Code': 'AccessDeniedException', 'Message': 'no'}}, op)


class SignupLookupFailureTests(unittest.TestCase):
    """M13: a read that failed is not a row that is absent."""

    def setUp(self):
        self.app = load_lambda('signup', 'signup_app_errors')

    def test_denied_lookup_answers_503_not_already_subscribed(self):
        with patch.object(self.app.ddb, 'get_item', side_effect=_denied('GetItem')), \
             patch.object(self.app.ddb, 'put_item') as mock_put, \
             self.assertLogs(level='ERROR') as logs:
            result = self.app.handler({
                'httpMethod': 'POST',
                'body': json.dumps({'email': 'holder@example.com', 'source': 'consumer'}),
            }, None)
        self.assertEqual(result['statusCode'], 503)
        body = json.loads(result['body'])
        self.assertNotEqual(body.get('status'), 'already-subscribed')
        self.assertNotIn('AccessDenied', result['body'])
        mock_put.assert_not_called()
        self.assertTrue(any('SIGNUP_LOOKUP_FAILED' in line for line in logs.output))


class SignupTransportFaultTests(unittest.TestCase):
    """M2: a transport fault is handled at both AWS calls."""

    def setUp(self):
        self.app = load_lambda('signup', 'signup_app_errors')

    def _event(self):
        return {'httpMethod': 'POST', 'body': json.dumps({'email': 'api@example.com'})}

    def test_transport_fault_creating_the_key_is_a_503_without_an_aws_code(self):
        fault = EndpointConnectionError(endpoint_url='https://apigateway.example')
        with patch.object(self.app, 'get_existing_signup', return_value=None), \
             patch.object(self.app, 'create_api_key', side_effect=fault), \
             self.assertLogs(level='ERROR'):
            result = self.app.handler(self._event(), None)
        self.assertEqual(result['statusCode'], 503)
        self.assertNotIn('code', json.loads(result['body']))

    def test_transport_fault_recording_the_signup_still_returns_the_key(self):
        # The key exists in API Gateway by now. Returning it is the only
        # outcome that does not strand an enabled key behind a 500 and send
        # the caller back to mint a second one.
        fault = EndpointConnectionError(endpoint_url='https://dynamodb.example')
        with patch.object(self.app, 'get_existing_signup', return_value=None), \
             patch.object(self.app, 'create_api_key', return_value=('key-1', 'sk_live')), \
             patch.object(self.app, 'record_signup', side_effect=fault), \
             self.assertLogs(level='WARNING') as logs:
            result = self.app.handler(self._event(), None)
        self.assertEqual(result['statusCode'], 201)
        self.assertEqual(json.loads(result['body'])['keyId'], 'key-1')
        self.assertTrue(any('key-1' in line for line in logs.output))


class BatchBodyShapeTests(unittest.TestCase):
    """M3: a JSON array where an object was expected is a 400."""

    def test_array_body_is_400(self):
        app = load_lambda('score', 'score_app_errors')
        result = app.handle_batch({'httpMethod': 'POST', 'body': '[]'})
        self.assertEqual(result['statusCode'], 400)
        self.assertIn('queries', json.loads(result['body'])['error'])


class FavouritesDeleteShapeTests(unittest.TestCase):
    """M3: a bad DELETE body is a 400, never a 503 about storage."""

    def setUp(self):
        self.app = load_lambda('favourites', 'favourites_app_errors')

    def _delete(self, body):
        event = {
            'httpMethod': 'DELETE',
            'headers': {'X-Device-Token': '0f7d9c2a-3b4e-4c5d-8e9f-0a1b2c3d4e5f'},
            'body': body,
        }
        with patch.object(self.app, 'table', MagicMock()) as table:
            result = self.app.handler(event, None)
        return result, table

    def test_array_body_is_400(self):
        result, table = self._delete('[]')
        self.assertEqual(result['statusCode'], 400)
        table.delete_item.assert_not_called()

    def test_non_string_postcode_is_400(self):
        result, table = self._delete(json.dumps({'postcode': 12345}))
        self.assertEqual(result['statusCode'], 400)
        table.delete_item.assert_not_called()


class ChatClientReuseTests(unittest.TestCase):
    """M15: one client per container, not one per request."""

    def test_clients_are_built_once(self):
        app = load_lambda('chat', 'chat_app_errors')
        app._CLIENTS.clear()
        with patch.object(app.boto3, 'client', return_value=MagicMock()) as ctor:
            a = app._bedrock_client()
            b = app._bedrock_client()
            c = app._lambda_client()
            d = app._lambda_client()
        self.assertIs(a, b)
        self.assertIs(c, d)
        self.assertEqual(ctor.call_count, 2, 'one construction per service, however many calls')


class NhsEmptyBucketTests(unittest.TestCase):
    """M16: an empty bucket after a successful query is not an outage row."""

    def test_none_nearby_is_distinct_from_the_outage_fallback(self):
        app = load_lambda('nhs', 'nhs_app_errors')
        nearby = app.none_nearby('GP')[0]
        outage = app.fallback_links('GP')[0]
        self.assertFalse(nearby['fallback'])
        self.assertTrue(nearby['noneNearby'])
        self.assertTrue(outage['fallback'])
        self.assertNotIn('noneNearby', outage)
        self.assertTrue(nearby['link'] and outage['link'], 'both render as a link')
        self.assertIn('1.5 km', nearby['name'])
        self.assertNotEqual(nearby['name'], outage['name'])

    def test_happy_path_empty_bucket_uses_none_nearby(self):
        app = load_lambda('nhs', 'nhs_app_errors')
        # An Overpass answer with elements that all land in one bucket, so the
        # other two are empty on a SUCCESSFUL query.
        elements = [{
            'type': 'node', 'id': 1, 'lat': 53.4809, 'lon': -2.2427,
            'tags': {'amenity': 'pharmacy', 'name': 'Test Pharmacy'},
        }]
        with patch.object(app, 'in_bundle_area', return_value=False), \
             patch.object(app, 'query_overpass', return_value=elements):
            result = app.handler(
                {'httpMethod': 'GET', 'queryStringParameters': {'lat': '53.4809', 'lon': '-2.2427'}},
                None,
            )
        body = json.loads(result['body'])
        self.assertTrue(body['available'])
        self.assertTrue(body['pharmacies'] and not body['pharmacies'][0].get('link'))
        self.assertTrue(body['gp'][0]['noneNearby'])
        self.assertFalse(body['gp'][0]['fallback'])


if __name__ == '__main__':
    unittest.main()
