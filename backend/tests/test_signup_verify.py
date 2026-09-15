"""I17 option A: verification-first signup, behind SIGNUP_VERIFY.

Why each test is here:

  - the POST answers ONE identical 201 for a new address, a subscribed one
    and a key holder, and never consults the register on the way - the
    three-reply oracle audit I17 describes is closed at the source;
  - nothing reaches the signups table on the POST: a stranger's submission
    cannot subscribe you or take the row that later 409s your own signup;
  - the pending row carries what the confirm needs and a TTL; the email
    carries the link and nothing else;
  - a failed send leaves no live token (503, pending row deleted);
  - the confirm consumes the token in ONE call (delete-and-return), so a
    second click finds nothing - one email cannot mint two keys;
  - an expired or unknown token is a 410 page, a malformed one a 400 page,
    and a good one runs complete_signup() - the same function the POST runs
    with the flag off, so the two modes cannot drift on the rules;
  - the confirm page is HTML with the key escaped, no-store, and a CSP;
  - with the flag OFF the POST is the pre-I17 path, byte for byte - the
    existing handler tests cover that path and this file asserts the switch.

Offline: ddb, ses and the APIGW helpers are patched at the boundary.
"""

import importlib.util
import json
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

LAMBDAS_DIR = os.path.join(os.path.dirname(__file__), '..', 'lambdas')


def load_signup():
    alias = 'signup_app_verify'
    if alias in sys.modules:
        return sys.modules[alias]
    spec = importlib.util.spec_from_file_location(alias, os.path.join(LAMBDAS_DIR, 'signup', 'app.py'))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


def post(body):
    return {
        'httpMethod': 'POST',
        'body': json.dumps(body),
        'requestContext': {'domainName': 'x.execute-api.eu-west-2.amazonaws.com', 'stage': 'prod'},
        'headers': {},
    }


def get_confirm(token):
    return {
        'httpMethod': 'GET',
        'path': '/v1/signup/confirm',
        'queryStringParameters': {'token': token} if token is not None else None,
        'requestContext': {'domainName': 'x.execute-api.eu-west-2.amazonaws.com', 'stage': 'prod'},
        'headers': {},
    }


class VerifyOnPostTests(unittest.TestCase):
    def setUp(self):
        self.app = load_signup()
        self.ddb = MagicMock()
        self.ses = MagicMock()
        self.patches = [
            patch.object(self.app, 'SIGNUP_VERIFY', True),
            patch.object(self.app, 'ddb', self.ddb),
            patch.object(self.app, 'ses', self.ses),
            patch.object(self.app, 'get_existing_signup', side_effect=AssertionError('register consulted on POST')),
            patch.object(self.app, 'create_api_key', side_effect=AssertionError('key minted on POST')),
            patch.object(self.app, 'record_signup', side_effect=AssertionError('register written on POST')),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_every_address_gets_the_same_201_and_the_register_is_untouched(self):
        bodies = []
        for payload in (
            {'email': 'new@example.com'},
            {'email': 'subscribed@example.com', 'source': 'consumer', 'postcode': 'SW11 1AA'},
            {'email': 'keyholder@example.com', 'name': 'K'},
        ):
            r = self.app.handler(post(payload), None)
            self.assertEqual(r['statusCode'], 201)
            bodies.append(json.loads(r['body']))
        self.assertEqual(len({json.dumps(b, sort_keys=True) for b in bodies}), 1, 'the reply must not vary by address')
        self.assertEqual(bodies[0]['status'], 'pending')
        # The register's table was never named in any DDB call.
        for call in self.ddb.put_item.call_args_list:
            self.assertEqual(call.kwargs['TableName'], self.app.PENDING_TABLE)

    def test_pending_row_and_email_carry_what_confirm_needs(self):
        self.app.handler(post({'email': 'a@example.com', 'name': 'A', 'source': 'consumer', 'postcode': 'm1 1ae'}), None)
        item = self.ddb.put_item.call_args.kwargs['Item']
        token = item['token']['S']
        self.assertRegex(token, self.app.TOKEN_PATTERN)
        self.assertEqual(item['email']['S'], 'a@example.com')
        self.assertEqual(item['source']['S'], 'consumer')
        self.assertEqual(item['postcode']['S'], 'M1 1AE')
        self.assertGreater(int(item['expiresAt']['N']), int(time.time()) + 23 * 3600)
        self.assertEqual(self.ddb.put_item.call_args.kwargs['ConditionExpression'], 'attribute_not_exists(#t)')
        send = self.ses.send_email.call_args.kwargs
        self.assertEqual(send['Destination']['ToAddresses'], ['a@example.com'])
        text = send['Content']['Simple']['Body']['Text']['Data']
        self.assertIn(f'https://x.execute-api.eu-west-2.amazonaws.com/prod/v1/signup/confirm?token={token}', text)
        self.assertIn('M1 1AE', text)
        self.assertNotIn('Html', send['Content']['Simple']['Body'])

    def test_a_failed_send_is_a_503_and_leaves_no_live_token(self):
        self.ses.send_email.side_effect = ClientError(
            {'Error': {'Code': 'MessageRejected', 'Message': 'sandbox'}}, 'SendEmail'
        )
        r = self.app.handler(post({'email': 'a@example.com'}), None)
        self.assertEqual(r['statusCode'], 503)
        self.assertNotIn('MessageRejected', r['body'])
        token = self.ddb.put_item.call_args.kwargs['Item']['token']['S']
        self.assertEqual(self.ddb.delete_item.call_args.kwargs['Key'], {'token': {'S': token}})

    def test_a_failed_pending_write_is_a_503_and_sends_nothing(self):
        self.ddb.put_item.side_effect = ClientError({'Error': {'Code': 'AccessDeniedException', 'Message': 'no'}}, 'PutItem')
        r = self.app.handler(post({'email': 'a@example.com'}), None)
        self.assertEqual(r['statusCode'], 503)
        self.ses.send_email.assert_not_called()

    def test_validation_still_precedes_the_pending_write(self):
        r = self.app.handler(post({'email': 'not-an-email'}), None)
        self.assertEqual(r['statusCode'], 400)
        self.ddb.put_item.assert_not_called()
        self.ses.send_email.assert_not_called()


class ConfirmTests(unittest.TestCase):
    def setUp(self):
        self.app = load_signup()
        self.ddb = MagicMock()
        self.patches = [
            patch.object(self.app, 'SIGNUP_VERIFY', True),
            patch.object(self.app, 'ddb', self.ddb),
            patch.object(self.app, 'ses', MagicMock()),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def _pending(self, **over):
        row = {
            'token': {'S': 'A' * 43},
            'email': {'S': 'a@example.com'},
            'name': {'S': 'A'},
            'source': {'S': 'api'},
            'postcode': {'S': ''},
            'expiresAt': {'N': str(int(time.time()) + 3600)},
        }
        row.update(over)
        return row

    def test_malformed_token_is_a_400_page_without_touching_the_table(self):
        for token in (None, '', 'short', 'has space ' + 'x' * 20, '<script>' + 'x' * 20):
            r = self.app.handler(get_confirm(token), None)
            self.assertEqual(r['statusCode'], 400)
            self.assertIn('text/html', r['headers']['Content-Type'])
        self.ddb.delete_item.assert_not_called()

    def test_unknown_or_expired_token_is_a_410_page(self):
        self.ddb.delete_item.return_value = {}
        r = self.app.handler(get_confirm('A' * 43), None)
        self.assertEqual(r['statusCode'], 410)
        self.ddb.delete_item.return_value = {'Attributes': self._pending(expiresAt={'N': str(int(time.time()) - 5)})}
        r = self.app.handler(get_confirm('A' * 43), None)
        self.assertEqual(r['statusCode'], 410)

    def test_token_is_consumed_in_one_call_and_the_key_is_shown_once(self):
        self.ddb.delete_item.return_value = {'Attributes': self._pending()}
        with patch.object(self.app, 'get_existing_signup', return_value=None), \
             patch.object(self.app, 'create_api_key', return_value=('kid123', 'SECRET<KEY>')), \
             patch.object(self.app, 'record_signup', return_value=None):
            r = self.app.handler(get_confirm('A' * 43), None)
        dl = self.ddb.delete_item.call_args.kwargs
        self.assertEqual(dl['TableName'], self.app.PENDING_TABLE)
        self.assertEqual(dl['ReturnValues'], 'ALL_OLD')
        self.assertEqual(r['statusCode'], 200)
        self.assertIn('text/html', r['headers']['Content-Type'])
        self.assertEqual(r['headers']['Cache-Control'], 'no-store')
        self.assertIn("default-src 'none'", r['headers']['Content-Security-Policy'])
        self.assertIn('SECRET&lt;KEY&gt;', r['body'])
        self.assertNotIn('SECRET<KEY>', r['body'])

    def test_consumer_confirm_subscribes_through_the_same_completion(self):
        self.ddb.delete_item.return_value = {'Attributes': self._pending(source={'S': 'consumer'}, postcode={'S': 'SW11 1AA'})}
        with patch.object(self.app, 'get_existing_signup', return_value=None), \
             patch.object(self.app, 'record_signup') as rec, \
             patch.object(self.app, 'create_api_key', side_effect=AssertionError('no key for a consumer')):
            r = self.app.handler(get_confirm('A' * 43), None)
        self.assertEqual(r['statusCode'], 200)
        self.assertEqual(rec.call_args.kwargs['source'], 'consumer')
        self.assertEqual(rec.call_args.kwargs['postcode'], 'SW11 1AA')
        self.assertIn('Confirmed', r['body'])

    def test_an_address_already_holding_a_key_is_told_so_on_the_page_not_the_post(self):
        self.ddb.delete_item.return_value = {'Attributes': self._pending()}
        existing = {'email': {'S': 'a@example.com'}, 'keyId': {'S': 'kid'}}
        with patch.object(self.app, 'get_existing_signup', return_value=existing), \
             patch.object(self.app, 'create_api_key', side_effect=AssertionError('no second key')):
            r = self.app.handler(get_confirm('A' * 43), None)
        self.assertEqual(r['statusCode'], 200)
        self.assertIn('Already signed up', r['body'])

    def test_a_transient_completion_failure_asks_for_a_new_link(self):
        self.ddb.delete_item.return_value = {'Attributes': self._pending()}
        with patch.object(self.app, 'get_existing_signup', side_effect=self.app.SignupLookupError()):
            r = self.app.handler(get_confirm('A' * 43), None)
        self.assertEqual(r['statusCode'], 503)
        self.assertIn('Request a new link', r['body'])


class FlagOffTests(unittest.TestCase):
    def test_flag_off_runs_the_pre_i17_path_directly(self):
        app = load_signup()
        self.assertFalse(app.SIGNUP_VERIFY, 'the template default is off; a fresh clone must not start sending')
        with patch.object(app, 'SIGNUP_VERIFY', False), \
             patch.object(app, 'start_verification', side_effect=AssertionError('verification ran with the flag off')), \
             patch.object(app, 'complete_signup', return_value=app.response(201, {'ok': True})) as done:
            r = app.handler(post({'email': 'a@example.com', 'source': 'consumer'}), None)
        self.assertEqual(r['statusCode'], 201)
        self.assertEqual(done.call_args.args[:3], ('a@example.com', '', 'consumer'))

    def test_confirm_route_exists_and_a_stray_get_is_still_405(self):
        app = load_signup()
        r = app.handler({'httpMethod': 'GET', 'path': '/v1/signup', 'headers': {}}, None)
        self.assertEqual(r['statusCode'], 405)


if __name__ == '__main__':
    unittest.main()
