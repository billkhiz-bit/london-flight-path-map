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


def post_confirm(token):
    """The confirm BUTTON: a form POST carrying the token in the body."""
    return {
        'httpMethod': 'POST',
        'path': '/v1/signup/confirm',
        'body': f'token={token}' if token is not None else '',
        'queryStringParameters': None,
        'requestContext': {'domainName': 'x.execute-api.eu-west-2.amazonaws.com', 'stage': 'prod'},
        'headers': {'content-type': 'application/x-www-form-urlencoded'},
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
        self.ddb.update_item.return_value = {'Attributes': {'sends': {'N': '1'}}}
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
        # A reply reaches a person (2026-11-22): the privacy page's published contact, never the no-reply sender.
        self.assertEqual(send['ReplyToAddresses'], ['Sky Score <support@skyscore.co.uk>'])
        text = send['Content']['Simple']['Body']['Text']['Data']
        link = f'https://x.execute-api.eu-west-2.amazonaws.com/prod/v1/signup/confirm?token={token}'
        self.assertIn(link, text)
        self.assertIn('M1 1AE', text)
        # Since 2026-11-22 an HTML part goes beside the plain text (Bill's pick: the blue-grey band, Stitch S2): the same
        # link and words, and nothing that loads from anywhere: no image, no stylesheet, no script, no tracking.
        page = send['Content']['Simple']['Body']['Html']['Data']
        self.assertIn(f'href="{link}"', page)
        self.assertIn('M1 1AE', page)
        self.assertIn(self.app.CONFIRM_SMALL_PRINT, page)
        for banned in ('<img', '<link', '<script', 'src=', 'url(', '@import'):
            self.assertNotIn(banned, page.lower(), banned)

    def test_a_failed_send_is_a_503_and_leaves_no_live_token(self):
        self.ses.send_email.side_effect = ClientError(
            {'Error': {'Code': 'MessageRejected', 'Message': 'sandbox'}}, 'SendEmail'
        )
        r = self.app.handler(post({'email': 'a@example.com'}), None)
        self.assertEqual(r['statusCode'], 503)
        self.assertNotIn('MessageRejected', r['body'])
        token = self.ddb.put_item.call_args.kwargs['Item']['token']['S']
        self.assertEqual(self.ddb.delete_item.call_args.kwargs['Key'], {'token': {'S': token}})
        self.assertCountsGivenBack()

    def test_a_failed_pending_write_is_a_503_and_sends_nothing(self):
        self.ddb.put_item.side_effect = ClientError({'Error': {'Code': 'AccessDeniedException', 'Message': 'no'}}, 'PutItem')
        r = self.app.handler(post({'email': 'a@example.com'}), None)
        self.assertEqual(r['statusCode'], 503)
        self.ses.send_email.assert_not_called()
        self.assertCountsGivenBack()

    def assertCountsGivenBack(self):
        # Audit M-5 (2026-11-25): send_decision() counts BEFORE the send, so a failed one took one of the visitor's three
        # a day, and one of the day's ceiling, for an email that never went. Both come back, the same rows, never made new.
        calls = [c.kwargs for c in self.ddb.update_item.call_args_list]
        added = [c['Key'] for c in calls if c['ExpressionAttributeValues'].get(':one') == {'N': '1'}]
        back = [c for c in calls if c['ExpressionAttributeValues'].get(':minus') == {'N': '-1'}]
        self.assertEqual(len(added), 2, calls)
        self.assertEqual(sorted(json.dumps(c['Key'], sort_keys=True) for c in back),
                         sorted(json.dumps(k, sort_keys=True) for k in added), 'each count added is given back once')
        for c in back:
            self.assertEqual(c['ConditionExpression'], 'attribute_exists(sends)')

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
            r = self.app.handler(post_confirm(token), None)
            self.assertEqual(r['statusCode'], 400)
            self.assertIn('text/html', r['headers']['Content-Type'])
        self.ddb.delete_item.assert_not_called()

    def test_unknown_or_expired_token_is_a_410_page(self):
        self.ddb.delete_item.return_value = {}
        r = self.app.handler(post_confirm('A' * 43), None)
        self.assertEqual(r['statusCode'], 410)
        self.ddb.delete_item.return_value = {'Attributes': self._pending(expiresAt={'N': str(int(time.time()) - 5)})}
        r = self.app.handler(post_confirm('A' * 43), None)
        self.assertEqual(r['statusCode'], 410)

    def test_token_is_consumed_in_one_call_and_the_key_is_shown_once(self):
        self.ddb.delete_item.return_value = {'Attributes': self._pending()}
        with patch.object(self.app, 'get_existing_signup', return_value=None), \
             patch.object(self.app, 'create_api_key', return_value=('kid123', 'SECRET<KEY>')), \
             patch.object(self.app, 'record_signup', return_value=None):
            r = self.app.handler(post_confirm('A' * 43), None)
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
            r = self.app.handler(post_confirm('A' * 43), None)
        self.assertEqual(r['statusCode'], 200)
        self.assertEqual(rec.call_args.kwargs['source'], 'consumer')
        self.assertEqual(rec.call_args.kwargs['postcode'], 'SW11 1AA')
        self.assertIn('Confirmed', r['body'])

    def test_an_address_already_holding_a_key_is_told_so_on_the_page_not_the_post(self):
        self.ddb.delete_item.return_value = {'Attributes': self._pending()}
        existing = {'email': {'S': 'a@example.com'}, 'keyId': {'S': 'kid'}}
        with patch.object(self.app, 'get_existing_signup', return_value=existing), \
             patch.object(self.app, 'create_api_key', side_effect=AssertionError('no second key')):
            r = self.app.handler(post_confirm('A' * 43), None)
        self.assertEqual(r['statusCode'], 200)
        self.assertIn('Already signed up', r['body'])

    def test_a_transient_completion_failure_asks_for_a_new_link(self):
        self.ddb.delete_item.return_value = {'Attributes': self._pending()}
        with patch.object(self.app, 'get_existing_signup', side_effect=self.app.SignupLookupError()):
            r = self.app.handler(post_confirm('A' * 43), None)
        self.assertEqual(r['statusCode'], 503)
        self.assertIn('Request a new link', r['body'])


class ScannerSafeConfirmTests(unittest.TestCase):
    """Audit I-5 (25 Sep): opening the link must change nothing.

    Mail gateways fetch every link before a person does. While the GET
    consumed the token, the scanner took the only copy of the key.
    """

    def setUp(self):
        self.app = load_signup()
        self.ddb = MagicMock()
        self.patches = [
            patch.object(self.app, 'SIGNUP_VERIFY', True),
            patch.object(self.app, 'ddb', self.ddb),
            patch.object(self.app, 'ses', MagicMock()),
            patch.object(self.app, 'create_api_key', side_effect=AssertionError('a GET minted a key')),
            patch.object(self.app, 'record_signup', side_effect=AssertionError('a GET wrote the register')),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def _row(self, **over):
        row = {'token': {'S': 'A' * 43}, 'email': {'S': 'a@example.com'}, 'source': {'S': 'api'},
               'expiresAt': {'N': str(int(time.time()) + 3600)}}
        row.update(over)
        return row

    def test_a_get_renders_a_button_and_never_deletes_the_token(self):
        self.ddb.get_item.return_value = {'Item': self._row()}
        for _ in range(3):  # a scanner, a preview pane, then the person
            r = self.app.handler(get_confirm('A' * 43), None)
            self.assertEqual(r['statusCode'], 200)
        self.ddb.delete_item.assert_not_called()
        self.assertTrue(self.ddb.get_item.call_args.kwargs['ConsistentRead'])
        self.assertIn('<form method="post"', r['body'])
        self.assertNotIn('<script', r['body'], 'an API key page never posts itself: the key is shown once')
        self.assertIn('name="token" value="' + 'A' * 43 + '"', r['body'])
        self.assertIn("form-action 'self'", r['headers']['Content-Security-Policy'])

    def test_a_get_for_an_unknown_or_expired_token_is_a_410_and_deletes_nothing(self):
        self.ddb.get_item.return_value = {}
        self.assertEqual(self.app.handler(get_confirm('A' * 43), None)['statusCode'], 410)
        self.ddb.get_item.return_value = {'Item': self._row(expiresAt={'N': str(int(time.time()) - 5)})}
        self.assertEqual(self.app.handler(get_confirm('A' * 43), None)['statusCode'], 410)
        self.ddb.delete_item.assert_not_called()

    def test_a_counter_row_can_never_be_confirmed(self):
        # Counter keys contain '#', which TOKEN_PATTERN excludes.
        key = self.app.SEND_COUNTER_PREFIX + 'f' * 64 + '#2026-09-28'
        self.assertIsNone(self.app.TOKEN_PATTERN.match(key))
        self.assertEqual(self.app.handler(get_confirm(key), None)['statusCode'], 400)
        self.ddb.get_item.assert_not_called()


class SendCapTests(unittest.TestCase):
    def setUp(self):
        self.app = load_signup()
        self.ddb = MagicMock()
        self.ses = MagicMock()
        self.patches = [
            patch.object(self.app, 'SIGNUP_VERIFY', True),
            patch.object(self.app, 'ddb', self.ddb),
            patch.object(self.app, 'ses', self.ses),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def _sends(self, n):
        self.ddb.update_item.return_value = {'Attributes': {'sends': {'N': str(n)}}}

    def test_over_the_cap_is_the_same_201_with_nothing_written_or_sent(self):
        self._sends(self.app.SEND_CAP_PER_DAY)
        under = self.app.handler(post({'email': 'a@example.com'}), None)
        self.assertEqual(self.ses.send_email.call_count, 1)
        self.ddb.reset_mock()
        self.ses.reset_mock()
        self._sends(self.app.SEND_CAP_PER_DAY + 1)
        over = self.app.handler(post({'email': 'a@example.com'}), None)
        self.assertEqual((over['statusCode'], over['body']), (under['statusCode'], under['body']),
                         'the cap must not be visible in the reply')
        self.ses.send_email.assert_not_called()
        self.ddb.put_item.assert_not_called()

    def test_the_counter_rows_hold_a_hash_not_the_address(self):
        self._sends(1)
        self.app.handler(post({'email': 'someone@example.com'}), None)
        calls = [c.kwargs for c in self.ddb.update_item.call_args_list]
        self.assertEqual(len(calls), 2, 'one row for the inbox, one for the day')
        for call in calls:
            self.assertEqual(call['TableName'], self.app.PENDING_TABLE)
            self.assertNotIn('someone', json.dumps(call))
            self.assertTrue(call['Key']['token']['S'].startswith(self.app.SEND_COUNTER_PREFIX))
            self.assertIn('expiresAt', call['UpdateExpression'])

    def test_an_unreadable_counter_fails_open(self):
        self.ddb.update_item.side_effect = ClientError({'Error': {'Code': 'ProvisionedThroughputExceededException', 'Message': ''}}, 'UpdateItem')
        r = self.app.handler(post({'email': 'a@example.com'}), None)
        self.assertEqual(r['statusCode'], 201)
        self.ses.send_email.assert_called_once()

    def _inbox_rows(self, *emails):
        rows = []
        for email in emails:
            self.ddb.reset_mock()
            self._sends(1)
            self.app.handler(post({'email': email}), None)
            rows.append(self.ddb.update_item.call_args_list[0].kwargs['Key']['token']['S'])
        return rows

    def test_tags_and_gmail_dots_count_as_one_inbox(self):
        # Audit M-3 (5 Oct): each spelling had its own three sends at ONE inbox.
        rows = self._inbox_rows('bill+1@gmail.com', 'b.i.l.l+news@googlemail.com', 'BILL@Gmail.com', 'bill@gmail.com')
        self.assertEqual(len(set(rows)), 1, rows)
        rows = self._inbox_rows('ann+a@example.com', 'ann+b@example.com', 'ann@example.com')
        self.assertEqual(len(set(rows)), 1, rows)

    def test_dots_still_matter_outside_gmail(self):
        # a.nn@ and ann@ can be two people anywhere Google does not run the mail.
        rows = self._inbox_rows('a.nn@example.com', 'ann@example.com')
        self.assertEqual(len(set(rows)), 2, rows)


class MailboxKeyTests(unittest.TestCase):
    def test_what_one_inbox_looks_like(self):
        key = load_signup().mailbox_key
        cases = {
            'bill@gmail.com': 'bill@gmail.com',
            'b.ill+x@gmail.com': 'bill@gmail.com',
            'bill@googlemail.com': 'bill@gmail.com',
            'ann+tag+more@example.com': 'ann@example.com',
            'a.nn@example.com': 'a.nn@example.com',
            'ann@sub.example.com': 'ann@sub.example.com',
        }
        for address, inbox in cases.items():
            self.assertEqual(key(address), inbox, address)

    def test_only_the_count_sees_it(self):
        # The email still goes to the address as typed, and the pending row (which
        # becomes the register entry) stores it as typed: normalising is for counting.
        app = load_signup()
        ddb, ses = MagicMock(), MagicMock()
        ddb.update_item.return_value = {'Attributes': {'sends': {'N': '1'}}}
        with patch.object(app, 'SIGNUP_VERIFY', True), patch.object(app, 'ddb', ddb), patch.object(app, 'ses', ses):
            app.handler(post({'email': 'B.ill+News@gmail.com'}), None)
        self.assertEqual(ses.send_email.call_args.kwargs['Destination']['ToAddresses'], ['b.ill+news@gmail.com'])
        self.assertEqual(ddb.put_item.call_args.kwargs['Item']['email']['S'], 'b.ill+news@gmail.com')


class SendCeilingTests(unittest.TestCase):
    """The day's ceiling: emails to ALL addresses, the residual OPERATIONS.md s3.9
    held the flip behind. Counters are answered per row, so each test says what
    the inbox's row and the day's row hold."""

    def setUp(self):
        self.app = load_signup()
        self.ddb = MagicMock()
        self.ses = MagicMock()
        self.patches = [
            patch.object(self.app, 'SIGNUP_VERIFY', True),
            patch.object(self.app, 'ddb', self.ddb),
            patch.object(self.app, 'ses', self.ses),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def _rows(self, inbox, day):
        """inbox: the inbox row's count after this request's ADD; day: the day row's
        count BEFORE this request (an ADD answers day + 1, a read answers day)."""
        day_row = f'{self.app.SEND_COUNTER_PREFIX}{self.app.SEND_CEILING_ROW}#'

        def update_item(**kw):
            row = kw['Key']['token']['S']
            n = day + 1 if row.startswith(day_row) else inbox
            return {'Attributes': {'sends': {'N': str(n)}}}

        def get_item(**kw):
            # Every kind of sign-up reads the do-not-email list first (audit I-1, 2026-11-23): not listed here.
            if kw['TableName'] == self.app.MAIL_TABLE:
                self.assertTrue(kw['Key']['pk']['S'].startswith('suppress#'), 'only the do-not-email list is read there')
                return {}
            self.assertTrue(kw['Key']['token']['S'].startswith(day_row), 'only the day row is ever read')
            return {'Item': {'sends': {'N': str(day)}}} if day else {}

        self.ddb.update_item.side_effect = update_item
        self.ddb.get_item.side_effect = get_item

    def _ask(self, email='a@example.com'):
        self.ses.reset_mock()
        self.ddb.put_item.reset_mock()
        return self.app.handler(post({'email': email}), None)

    def test_under_the_ceiling_the_email_goes(self):
        self._rows(inbox=1, day=self.app.SEND_CEILING_PER_DAY - 1)
        r = self._ask()
        self.assertEqual(r['statusCode'], 201)
        self.ses.send_email.assert_called_once()

    def test_over_the_ceiling_nothing_is_sent_and_the_reply_says_why(self):
        self._rows(inbox=1, day=self.app.SEND_CEILING_PER_DAY)
        r = self._ask()
        self.assertEqual(r['statusCode'], 503)
        self.assertEqual(json.loads(r['body'])['error'], self.app.SEND_CEILING_MESSAGE)
        self.ses.send_email.assert_not_called()
        self.ddb.put_item.assert_not_called()

    def test_a_full_day_answers_every_address_alike(self):
        # A capped inbox must not get a 201 while a fresh one gets the 503: the pair
        # would say which addresses had been asked for three times today.
        self._rows(inbox=1, day=self.app.SEND_CEILING_PER_DAY)
        fresh = self._ask('fresh@example.com')
        self._rows(inbox=self.app.SEND_CAP_PER_DAY + 1, day=self.app.SEND_CEILING_PER_DAY)
        capped = self._ask('capped@example.com')
        self.assertEqual((fresh['statusCode'], fresh['body']), (capped['statusCode'], capped['body']))

    def test_a_capped_inbox_does_not_use_up_the_day(self):
        # Only a real send adds to the day's row: one script hammering one address
        # must not lock every other signup out for the day.
        self._rows(inbox=self.app.SEND_CAP_PER_DAY + 1, day=5)
        r = self._ask()
        self.assertEqual(r['statusCode'], 201)
        self.ses.send_email.assert_not_called()
        rows = [c.kwargs['Key']['token']['S'] for c in self.ddb.update_item.call_args_list]
        self.assertFalse(any(f'#{self.app.SEND_CEILING_ROW}#' in row for row in rows), rows)

    def test_the_day_row_cannot_collide_with_an_inbox_row_or_be_confirmed(self):
        self.assertIsNone(re.fullmatch(r'[0-9a-f]{64}', self.app.SEND_CEILING_ROW))
        key = f'{self.app.SEND_COUNTER_PREFIX}{self.app.SEND_CEILING_ROW}#2026-11-21'
        self.assertIsNone(self.app.TOKEN_PATTERN.match(key))

    def test_an_unreadable_day_row_fails_open(self):
        err = ClientError({'Error': {'Code': 'ProvisionedThroughputExceededException', 'Message': ''}}, 'GetItem')
        self._rows(inbox=self.app.SEND_CAP_PER_DAY + 1, day=0)

        def day_read_fails(**kw):
            # Only the DAY ROW is unreadable; the do-not-email list (read first since audit I-1) answers "not listed",
            # since an unreadable list fails CLOSED on purpose (DoNotEmailTests).
            if kw['TableName'] == self.app.MAIL_TABLE:
                return {}
            raise err

        self.ddb.get_item.side_effect = day_read_fails
        self.assertEqual(self._ask()['statusCode'], 201, 'a capped inbox stays the silent 201')

        def day_fails(**kw):
            if f'#{self.app.SEND_CEILING_ROW}#' in kw['Key']['token']['S']:
                raise err
            return {'Attributes': {'sends': {'N': '1'}}}

        self.ddb.update_item.side_effect = day_fails
        r = self._ask()
        self.assertEqual(r['statusCode'], 201)
        self.ses.send_email.assert_called_once()


class EmailPostcodeTests(unittest.TestCase):
    def _body(self, postcode):
        app = load_signup()
        ses = MagicMock()
        with patch.object(app, 'ses', ses):
            app.send_confirmation_email('a@example.com', 'consumer', postcode, 'https://x/confirm?token=t')
        return ses.send_email.call_args.kwargs['Content']['Simple']['Body']['Text']['Data']

    def test_a_real_postcode_is_shown(self):
        for pc in ('SW11 1AA', 'M1 1AE', 'EC1A 1BB', 'B338TH'):
            self.assertIn(pc, self._body(pc))

    def test_anything_domain_shaped_or_odd_is_not_put_in_the_email(self):
        for pc in ('EVIL.COM', 'WWW.X.CO', 'HTTP://A', 'SW11 1AA X', '<B>'):
            body = self._body(pc)
            self.assertNotIn(pc, body)
            self.assertIn('an area', body)


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
# 'pressing Confirm', not 'clicking the link': since 2026-09-28 a GET of the
# link renders a button and only the POST consumes the token (audit I-5).
CONSENT_BY_LINK = 'by pressing Confirm on the page our email links to'
# The deletion clause says what the TTL really does (Bill's pick A, 2026-11-21):
# the token stops working at 24 h in code, but AWS removes an expired row
# "typically within a few days", sometimes past 48 h. "Deleted after 24 hours"
# read as deleted AT 24 hours, so these promises may not come back.
PENDING_DELETED = 'deleted automatically within a few days'
RETIRED_PROMISES = ('at most 24 hours', 'deleted after 24 hours', 'within 24 hours is deleted', '24-hour clock')
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
    table had no TTL until two IAM verbs were granted (landed on master
    2026-09-29), and the missing TTL cost "nothing" operationally while being
    false the moment privacy.html says the request is deleted. So a page that
    claims deletion is RED here whenever the TTL is absent - the branch that
    carries the page edits was red on exactly this until that day.
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
                'privacy.html says consent is given by pressing Confirm on an emailed link while the '
                'template default is off - nobody is emailed a link',
            )

    def test_privacy_claims_deletion_only_when_the_table_deletes(self):
        if PENDING_DELETED in self.privacy:
            self.assertTrue(
                self.pending_ttl,
                'privacy.html says an unconfirmed request is deleted automatically, '
                'but SignupPendingTable has no TimeToLiveSpecification - expiry is '
                'enforced in code and the row is never removed (s3.9 step 3)',
            )

    def test_privacy_says_when_a_pending_request_goes_iff_the_flag_is_on(self):
        # Without this, rewording the clause would leave the test above
        # skipping on a phrase that is no longer there, green and blind.
        says = PENDING_DELETED in self.privacy
        if self.flag == 'on':
            self.assertTrue(says, f'SignupVerify is on but privacy.html never says "{PENDING_DELETED}"')
        else:
            self.assertFalse(says, 'privacy.html describes pending requests while the template default is off')

    def test_no_page_promises_deletion_at_24_hours(self):
        notices = read('changes.html')
        for page, text in (('privacy.html', self.privacy), ('changes.html', notices), ('SUBPROCESSORS.md', self.register)):
            for promise in RETIRED_PROMISES:
                self.assertNotIn(
                    promise, text,
                    f'{page} says "{promise}", but the TTL deletes a row within a few days of '
                    'its expiry, not at it (AWS: "typically within a few days")',
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
