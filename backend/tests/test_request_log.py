"""The score Lambda's one-line request log: which KEY called which route.

It exists so we can tell whether anyone outside the project uses the API
(2026-09-28: five keys ever issued, all ours, and no way to split the shared
demo key's traffic). It is also a PRIVACY claim: privacy.html s2d says these
logs carry the method, route, status and API key ID, and not IP addresses,
user agents or postcodes. These tests hold the code to that sentence.
"""

import json
import os
import sys
import unittest
from unittest.mock import patch

LAMBDAS_DIR = os.path.join(os.path.dirname(__file__), '..', 'lambdas')

IP = '203.0.113.77'
UA = 'Mozilla/5.0 (RequestLogTest)'
KEY_ID = 'abc123keyid'
SECRET = 'SeCrEtKeyValueThatMustNeverBeLogged00000'  # noqa: S105 - deliberately fake; the test asserts it never reaches a log
POSTCODE = 'ZZ99ZZ'


def _import_score():
    path = os.path.abspath(os.path.join(LAMBDAS_DIR, 'score'))
    sys.path.insert(0, path)
    sys.modules.pop('app', None)
    try:
        import app  # noqa: F401, pylint: disable=import-outside-toplevel
        return app
    finally:
        sys.path.pop(0)


def _event(method='GET', resource='/v1/score', params=None):
    return {
        'httpMethod': method,
        'resource': resource,
        'path': resource,
        'queryStringParameters': params,
        'headers': {'User-Agent': UA, 'x-api-key': SECRET},
        'requestContext': {'identity': {'apiKeyId': KEY_ID, 'sourceIp': IP, 'userAgent': UA}},
    }


class RequestLogTests(unittest.TestCase):
    def setUp(self):
        self.app = _import_score()

    def _logged(self, event):
        # No network: an unknown postcode resolves to nothing locally. (The
        # first version of this test reached postcodes.io for real.)
        with patch.object(self.app, 'lookup_postcode', return_value=None), \
                self.assertLogs(self.app.logger, level='INFO') as cm:
            result = self.app.handler(event, None)
        lines = [r.getMessage() for r in cm.records if r.getMessage().startswith('[API_REQUEST]')]
        self.assertEqual(len(lines), 1, f'expected exactly one request line, got {lines}')
        return result, lines[0], '\n'.join(r.getMessage() for r in cm.records)

    def test_records_key_route_method_and_status(self):
        result, line, _ = self._logged(_event(params={'postcode': POSTCODE}))
        payload = json.loads(line.split(' ', 1)[1])
        self.assertEqual(payload, {'method': 'GET', 'route': '/v1/score',
                                   'status': result['statusCode'], 'apiKeyId': KEY_ID})

    def test_never_records_ip_user_agent_postcode_or_key_value(self):
        # Against EVERY line the invocation logs, not just ours: the claim in
        # privacy.html is about the log, and a neighbour line leaking a postcode
        # would make it false just the same.
        _, line, everything = self._logged(_event(params={'postcode': POSTCODE}))
        for secret in (IP, UA, SECRET):
            self.assertNotIn(secret, everything)
        self.assertNotIn(POSTCODE, line)

    def test_unauthenticated_route_logs_a_null_key(self):
        event = _event(resource='/v1/regions')
        event['requestContext']['identity'].pop('apiKeyId')
        _, line, _ = self._logged(event)
        self.assertIsNone(json.loads(line.split(' ', 1)[1])['apiKeyId'])

    def test_a_crashing_route_is_still_logged_with_its_500(self):
        with patch.object(self.app, 'handle_get', side_effect=RuntimeError('boom')):
            result, line, _ = self._logged(_event())
        self.assertEqual(result['statusCode'], 500)
        self.assertEqual(json.loads(line.split(' ', 1)[1])['status'], 500)

    def test_a_failing_log_line_never_fails_the_request(self):
        with patch.object(self.app, 'log_request', side_effect=RuntimeError('log down')):
            result = self.app.handler(_event(resource='/v1/regions'), None)
        self.assertEqual(result['statusCode'], 200)


if __name__ == '__main__':
    unittest.main()
