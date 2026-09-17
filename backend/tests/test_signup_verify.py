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
    existing handler tests cover that path and this file asserts the switch;
  - the PAGES and the FLAG move together (VerifyPagesAndTemplateTests):
    privacy.html describes consent-by-link only when the template default is
    `on`, says the pending request is DELETED only when the table carries the
    TTL that deletes it, and SUBPROCESSORS.md says "NOT YET SENDING" only
    while that is true. OPERATIONS.md s3.9 step 4 says the pages ship in the
    same deploy as the flip; a runbook step is a note, and this is the guard.

Offline: ddb, ses and the APIGW helpers are patched at the boundary.
"""

import importlib.util
import json
import os
import re
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
        self.assertFalse(
            app.SIGNUP_VERIFY,
            'the CODE default is off: the flag arrives from the template as an env var at deploy time, '
            'and a bare import of the module must not start sending',
        )
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


ROOT = os.path.join(os.path.dirname(__file__), '..', '..')

# The exact sentences the branch that flips the flag writes into privacy.html
# s2a. Held here, not re-typed on the page, so the page and the gate cannot
# describe two different promises.
CONSENT_BY_LINK = 'by clicking the confirmation link we email you'
PENDING_DELETED = 'not confirmed within 24 hours is deleted'
REGISTER_NOT_SENDING = 'NOT YET SENDING'


def read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
        return fh.read()


class VerifyPagesAndTemplateTests(unittest.TestCase):
    """The flip is one deploy with three moving parts, and each pair is
    asserted in BOTH directions so the tree can never describe a state the
    stack is not in: a page a minute early is a privacy policy that overclaims,
    a minute late is one that under-discloses.

    The deletion clause is the one a runbook could not hold. The pending
    table has no TTL until two IAM verbs are granted (template.yaml comment on
    SignupPendingTable), and the template's own comment calls the missing TTL a
    cost of "nothing" - true operationally, false the moment privacy.html says
    the request is deleted. So the branch carrying the page edits is RED here
    until the TTL lands, and cannot be merged early by accident.
    """

    @classmethod
    def setUpClass(cls):
        cls.template = read(os.path.join('backend', 'template.yaml'))
        cls.privacy = read('privacy.html')
        cls.register = read('SUBPROCESSORS.md')
        cls.policy = read(os.path.join('backend', 'iam-policy.json'))
        m = re.search(r"^  SignupVerify:\n(?:    .*\n)*?    Default: '(on|off)'", cls.template, re.M)
        assert m, 'SignupVerify parameter not found in template.yaml - the regex, not the flag, is what changed'
        cls.flag = m.group(1)
        # The block runs from its key to the first line that is neither
        # indented under it nor blank - the next resource, or the comment
        # banner above it. A blank line ends nothing in YAML.
        block = re.search(r'^  SignupPendingTable:\n(?:(?:    .*|\s*)\n)*', cls.template, re.M)
        assert block, 'SignupPendingTable block not found in template.yaml'
        # Anchored to the line start: the template's comment on this table
        # spells the key out as the thing to add, and a substring test read
        # that comment as the TTL itself on the gate's first run.
        cls.pending_ttl = re.search(r'^ +TimeToLiveSpecification:', block.group(0), re.M) is not None

    def test_privacy_describes_consent_by_link_iff_the_flag_is_on(self):
        claims = CONSENT_BY_LINK in self.privacy
        if self.flag == 'on':
            self.assertTrue(
                claims,
                'SignupVerify defaults to on but privacy.html s2a still says consent is '
                'given by submitting the form - the page ships in the SAME deploy (s3.9 step 4)',
            )
        else:
            self.assertFalse(
                claims,
                'privacy.html says consent is given by clicking an emailed link while the '
                'template default is off - nobody is emailed a link',
            )

    def test_privacy_claims_deletion_only_when_the_table_deletes(self):
        if PENDING_DELETED in self.privacy:
            self.assertTrue(
                self.pending_ttl,
                'privacy.html says an unconfirmed request is deleted after 24 hours, '
                'but SignupPendingTable has no TimeToLiveSpecification - expiry is '
                'enforced in code and the row is never removed (s3.9 step 3)',
            )

    def test_a_ttl_in_the_template_has_the_verbs_that_deploy_it(self):
        if self.pending_ttl:
            for verb in ('dynamodb:UpdateTimeToLive', 'dynamodb:DescribeTimeToLive'):
                self.assertIn(
                    verb,
                    self.policy,
                    f'{verb} is missing from iam-policy.json; a TTL in the template '
                    'fails the WHOLE stack deploy without it (s3.9 step 3)',
                )

    def test_register_says_not_yet_sending_iff_the_flag_is_off(self):
        row = next((ln for ln in self.register.splitlines() if 'Simple Email Service' in ln), None)
        self.assertIsNotNone(row, 'SUBPROCESSORS.md row 1 no longer names SES')
        if self.flag == 'on':
            self.assertNotIn(
                REGISTER_NOT_SENDING, row, 'the flag is on and SUBPROCESSORS.md still says SES is not sending'
            )
        else:
            self.assertIn(REGISTER_NOT_SENDING, row, 'SUBPROCESSORS.md describes SES as live while the flag is off')


if __name__ == '__main__':
    unittest.main()
