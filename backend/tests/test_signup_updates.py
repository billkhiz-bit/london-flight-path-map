"""News by email (Bill, 2026-11-22; the front page's strip, mock-up claude.ai/artifact/XFr75aGp5ziqBEeFFNCCmu v6),
grown out of the area updates list built 2026-11-10 (claude.ai/artifact/LfzxhdZ62gm8u5uifTcAnw).

Why each test is here:

  - CLOSED unless both flags are on: the POST refuses source 'updates' unless UPDATES_LIST and SIGNUP_VERIFY are both
    on, with one answer for every address, and writes nothing; the template now ships both ON (Bill's approval);
  - open, a POST only starts the emailed confirmation (a pending row for source 'updates', an email that says "one
    email a month"); news only since news-v2: a postcode sent anyway is dropped, never checked, stored or emailed;
  - the confirm page confirms itself for news (one hashed script, the CSP names it); API keys and the map's list keep
    the button;
  - the confirm button joins the list in its OWN table: the signups table, with its one-row-per-email rules, is never
    read or written for this source;
  - joining writes the unsubscribe token BEFORE the member that names it, retires an earlier token and clears the
    do-not-email entry (a confirmed sign-up is fresh consent); the member records the consent wording and when;
  - the unsubscribe GET changes nothing (mail scanners prefetch links); the POST (the button, or a mail client's RFC 8058
    one-click with the token in the query) removes the member and the token and adds the address to the do-not-email
    list; an unknown or used token says so and changes nothing;
  - the template holds the routes with their own throttles, the table, the flag default and the function's access.

Offline: the Lambda's ddb and ses clients are replaced at the boundary by an in-memory table (FakeDdb), so the tests
read what was STORED, not which calls were made.
"""

import base64
import hashlib
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
TEMPLATE = os.path.join(os.path.dirname(__file__), '..', 'template.yaml')
CTX = {'domainName': 'x.execute-api.eu-west-2.amazonaws.com', 'stage': 'prod'}


def load_signup():
    alias = 'signup_app_updates'
    if alias in sys.modules:
        return sys.modules[alias]
    spec = importlib.util.spec_from_file_location(alias, os.path.join(LAMBDAS_DIR, 'signup', 'app.py'))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeDdb:
    """get/put/delete/update on named tables, each a dict keyed by the item's key attribute; records the order of writes."""

    KEYS = {}

    def __init__(self, keys):
        self.KEYS = keys
        self.tables = {name: {} for name in keys}
        self.writes = []
        self.reads = []
        self.fail = set()  # {(op, key prefix)}: that write raises once, as DynamoDB does on a throttle

    def _maybe_fail(self, op, key):
        for want in list(self.fail):
            if want[0] == op and key.startswith(want[1]):
                self.fail.discard(want)
                raise ClientError({'Error': {'Code': 'ProvisionedThroughputExceededException'}}, op)

    def _key(self, table, key):
        attr = self.KEYS[table]
        return key[attr]['S']

    def get_item(self, TableName, Key, **_):
        self.reads.append((TableName, self._key(TableName, Key)))
        self._maybe_fail('get', self._key(TableName, Key))
        item = self.tables[TableName].get(self._key(TableName, Key))
        return {'Item': item} if item else {}

    def put_item(self, TableName, Item, ReturnValues=None, **_):
        attr = self.KEYS[TableName]
        self._maybe_fail('put', Item[attr]['S'])
        old = self.tables[TableName].get(Item[attr]['S'])
        self.tables[TableName][Item[attr]['S']] = Item
        self.writes.append(('put', TableName, Item[attr]['S']))
        return {'Attributes': old} if (old and ReturnValues == 'ALL_OLD') else {}

    def delete_item(self, TableName, Key, ReturnValues=None, **_):
        self._maybe_fail('delete', self._key(TableName, Key))
        old = self.tables[TableName].pop(self._key(TableName, Key), None)
        self.writes.append(('delete', TableName, self._key(TableName, Key)))
        return {'Attributes': old} if (old and ReturnValues == 'ALL_OLD') else {}

    # The do-not-email list is read by the address AND its inbox in one call, and written the same way (audit I-2,
    # 2026-11-27); an unsubscribe finds the address's older tokens with a scan and deletes them in a batch (I-3).
    def batch_get_item(self, RequestItems, **_):
        out, left = {}, {}
        for table, spec in RequestItems.items():
            for key in spec['Keys']:
                k = self._key(table, key)
                self.reads.append((table, k))
                self._maybe_fail('get', k)
                if k in self.tables[table]:
                    out.setdefault(table, []).append({self.KEYS[table]: {'S': k}})
        return {'Responses': out, 'UnprocessedKeys': left}

    def batch_write_item(self, RequestItems, **_):
        for table, ops in RequestItems.items():
            for op in ops:
                if 'PutRequest' in op:
                    self.put_item(TableName=table, Item=op['PutRequest']['Item'])
                else:
                    self.delete_item(TableName=table, Key=op['DeleteRequest']['Key'])
        return {'UnprocessedItems': {}}

    def scan(self, TableName, ExpressionAttributeValues, **_):
        prefix, email = ExpressionAttributeValues[':p']['S'], ExpressionAttributeValues[':e']['S']
        attr = self.KEYS[TableName]
        items = [{attr: {'S': k}} for k, row in sorted(self.tables[TableName].items())
                 if k.startswith(prefix) and row.get('email', {}).get('S') == email]
        return {'Items': items}

    def update_item(self, **_):
        self.counted += 1
        return {'Attributes': {'sends': {'N': '1'}}}  # the send-cap counter

    counted = 0


def post(body):
    return {'httpMethod': 'POST', 'path': '/v1/signup', 'body': json.dumps(body), 'requestContext': CTX, 'headers': {}}


def form_post(path, token):
    return {'httpMethod': 'POST', 'path': path, 'body': f'token={token}', 'queryStringParameters': None,
            'requestContext': CTX, 'headers': {'content-type': 'application/x-www-form-urlencoded'}}


def get(path, token):
    return {'httpMethod': 'GET', 'path': path, 'queryStringParameters': {'token': token}, 'requestContext': CTX, 'headers': {}}


class UpdatesBase(unittest.TestCase):
    OPEN = True

    def setUp(self):
        self.app = load_signup()
        self.db = FakeDdb({self.app.PENDING_TABLE: 'token', self.app.MAIL_TABLE: 'pk', self.app.SIGNUPS_TABLE: 'email'})
        self.ses = MagicMock()
        self.patches = [
            patch.object(self.app, 'SIGNUP_VERIFY', self.OPEN),
            patch.object(self.app, 'UPDATES_LIST', self.OPEN),
            patch.object(self.app, 'ddb', self.db),
            patch.object(self.app, 'ses', self.ses),
            patch.object(self.app, 'get_existing_signup', side_effect=AssertionError('signups table read for updates')),
            patch.object(self.app, 'record_signup', side_effect=AssertionError('signups table written for updates')),
            patch.object(self.app, 'create_api_key', side_effect=AssertionError('key minted for updates')),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def mail(self, kind, value):
        return self.db.tables[self.app.MAIL_TABLE].get(f'{kind}#{value}')

    def join(self, email='a@example.com', area='SW15 1HL'):
        """POST, then the confirm button: the whole sign-up as a person does it."""
        r = self.app.handler(post({'email': email, 'source': 'updates', 'postcode': area}), None)
        self.assertEqual(r['statusCode'], 201, r['body'])
        token = next(iter(self.db.tables[self.app.PENDING_TABLE]))
        return self.app.handler(form_post('/v1/signup/confirm', token), None)


class ClosedTests(UpdatesBase):
    OPEN = False

    def test_closed_by_default_one_answer_nothing_written(self):
        for email in ('new@example.com', 'someone@example.com'):
            r = self.app.handler(post({'email': email, 'source': 'updates', 'postcode': 'SW15 1HL'}), None)
            self.assertEqual(r['statusCode'], 403, 'closed is a decision, never a 5xx in the error figures')
            self.assertEqual(json.loads(r['body'])['error'], 'News by email is not open yet.')
        self.assertEqual(self.db.writes, [])
        self.ses.send_email.assert_not_called()

    def test_closed_while_only_one_flag_is_on(self):
        for verify, updates in ((True, False), (False, True)):
            with patch.object(self.app, 'SIGNUP_VERIFY', verify), patch.object(self.app, 'UPDATES_LIST', updates):
                r = self.app.handler(post({'email': 'a@example.com', 'source': 'updates', 'postcode': 'SW15 1HL'}), None)
                self.assertEqual(r['statusCode'], 403, (verify, updates))
        self.assertEqual(self.db.writes, [])


class JoinTests(UpdatesBase):
    def test_the_post_only_starts_the_emailed_confirmation(self):
        r = self.app.handler(post({'email': 'A@Example.com', 'source': 'updates', 'postcode': ''}), None)
        self.assertEqual(r['statusCode'], 201)
        self.assertEqual(json.loads(r['body'])['status'], 'pending')
        (row,) = self.db.tables[self.app.PENDING_TABLE].values()
        self.assertEqual((row['email']['S'], row['source']['S'], row['postcode']['S']), ('a@example.com', 'updates', ''))
        self.assertEqual(self.db.tables[self.app.MAIL_TABLE], {}, 'nothing joins before the link is confirmed')
        mail = self.ses.send_email.call_args.kwargs['Content']['Simple']
        self.assertIn('one email a month', mail['Body']['Text']['Data'])

    def test_a_postcode_sent_anyway_is_dropped_never_checked_stored_or_emailed(self):
        # news-v2 (Bill, 2026-11-22): the front page offers news only and privacy s2a names no postcode. Every shape gets
        # the same 201 (a 400 for a bad one would say what the Lambda still looks at), and none reaches the row or email.
        for area in ('SW15 1HL', 'sw15 1hl', 'SW15', 'Putney', 'example.com'):
            self.db.tables[self.app.PENDING_TABLE].clear()
            r = self.app.handler(post({'email': 'a@example.com', 'source': 'updates', 'postcode': area}), None)
            self.assertEqual(r['statusCode'], 201, area)
            (row,) = self.db.tables[self.app.PENDING_TABLE].values()
            self.assertEqual(row['postcode']['S'], '', area)
            mail = self.ses.send_email.call_args.kwargs['Content']['Simple']
            self.assertEqual(mail['Subject']['Data'], 'Confirm your Sky Score news', area)
            for part in ('Text', 'Html'):
                self.assertNotIn(area.upper(), mail['Body'][part]['Data'].upper().replace('SKYSCORE.CO.UK', ''), (area, part))

    def test_news_only_needs_no_postcode_and_names_none(self):
        r = self.app.handler(post({'email': 'a@example.com', 'source': 'updates', 'postcode': ''}), None)
        self.assertEqual(r['statusCode'], 201, r['body'])
        (row,) = self.db.tables[self.app.PENDING_TABLE].values()
        self.assertEqual(row['source']['S'], 'updates')
        self.assertEqual(row.get('postcode', {}).get('S', ''), '')
        mail = self.ses.send_email.call_args.kwargs['Content']['Simple']
        self.assertEqual(mail['Subject']['Data'], 'Confirm your Sky Score news')
        self.assertIn('new cities and new data', mail['Body']['Text']['Data'])
        self.assertIn('one email a month', mail['Body']['Text']['Data'])
        self.assertNotIn('figures for', mail['Body']['Text']['Data'])

    def test_a_news_only_member_stores_no_postcode_and_the_words_agreed(self):
        page = self.join(area='')
        self.assertEqual(page['statusCode'], 200, page['body'])
        self.assertIn('Sky Score news', page['body'])
        member = self.mail('updates', 'a@example.com')
        self.assertNotIn('area', member, 'no postcode is stored')
        self.assertEqual(member['consent']['S'], self.app.consent_wording())
        self.assertEqual(member['consent']['S'], f'{self.app.NEWS_CONSENT_VERSION}: {self.app.NEWS_PROMISE}')
        self.assertTrue(self.app.NEWS_CONSENT_VERSION.startswith('news-v2'), 'the words changed, so did the version')
        self.assertNotIn('figures for', member['consent']['S'])

    def test_a_pending_row_from_before_the_box_went_stores_no_postcode(self):
        # A news-v1 link (made before news-v2 shipped, its row naming a postcode) pressed after: news only, as the
        # privacy page now says.
        self.app.handler(post({'email': 'a@example.com', 'source': 'updates', 'postcode': ''}), None)
        token = next(iter(self.db.tables[self.app.PENDING_TABLE]))
        self.db.tables[self.app.PENDING_TABLE][token]['postcode'] = {'S': 'SW15 1HL'}
        page = self.app.handler(form_post('/v1/signup/confirm', token), None)
        self.assertEqual(page['statusCode'], 200, page['body'])
        member = self.mail('updates', 'a@example.com')
        self.assertNotIn('area', member)
        self.assertEqual(member['consent']['S'], self.app.consent_wording())
        self.assertNotIn('SW15 1HL', page['body'])

    def test_the_closed_page_after_a_late_click_names_news_by_email(self):
        self.app.handler(post({'email': 'a@example.com', 'source': 'updates', 'postcode': ''}), None)
        token = next(iter(self.db.tables[self.app.PENDING_TABLE]))
        with patch.object(self.app, 'UPDATES_LIST', False):
            page = self.app.handler(form_post('/v1/signup/confirm', token), None)
        self.assertIn('News by email is closed', page['body'])

    def test_the_confirm_page_names_the_list_and_confirms_itself(self):
        # One click (Bill's pick 1, 2026-11-22): the page posts its own form as it opens. The GET itself still changes
        # nothing, so a scanner that only fetches the link (no script) cannot confirm.
        self.app.handler(post({'email': 'a@example.com', 'source': 'updates', 'postcode': ''}), None)
        token = next(iter(self.db.tables[self.app.PENDING_TABLE]))
        page = self.app.handler(get('/v1/signup/confirm', token), None)
        self.assertEqual(page['statusCode'], 200)
        self.assertIn('one email a month', page['body'])
        self.assertIn(token, self.db.tables[self.app.PENDING_TABLE], 'the GET changes nothing')
        self.assertEqual(self.db.tables[self.app.MAIL_TABLE], {}, 'nothing joins on a fetch')
        # The form the script submits, its button for no-script, and the one script the CSP allows by its hash.
        self.assertIn('<form method="post" id="confirm">', page['body'])
        self.assertIn('<button type="submit">Confirm</button>', page['body'])
        scripts = re.findall(r'<script>(.*?)</script>', page['body'], re.S)
        self.assertEqual(scripts, [self.app._AUTO_CONFIRM_JS])
        digest = base64.b64encode(hashlib.sha256(scripts[0].encode('utf-8')).digest()).decode('ascii')
        self.assertIn(f"script-src 'sha256-{digest}'", page['headers']['Content-Security-Policy'])
        self.assertIn("default-src 'none'", page['headers']['Content-Security-Policy'])

    def test_only_news_confirms_itself(self):
        # API keys are shown ONCE (a scanner running script would take one), and the map's list promises "Opening the
        # link alone confirms nothing": no script, no script-src, the button only.
        for source in ('api', 'consumer'):
            row = {'token': {'S': 'T' * 43}, 'email': {'S': 'a@example.com'}, 'source': {'S': source},
                   'expiresAt': {'N': str(int(time.time()) + 3600)}}
            self.db.tables[self.app.PENDING_TABLE]['T' * 43] = row
            page = self.app.handler(get('/v1/signup/confirm', 'T' * 43), None)
            self.assertEqual(page['statusCode'], 200, source)
            self.assertNotIn('<script', page['body'], source)
            self.assertNotIn('script-src', page['headers']['Content-Security-Policy'], source)
            self.assertIn('<button type="submit">Confirm</button>', page['body'], source)
        with self.assertRaises(ValueError):
            self.app.html_page(200, 'x', '<p>x</p>', script='alert(1)')

    def test_confirming_joins_the_list_in_its_own_table(self):
        page = self.join()
        self.assertEqual(page['statusCode'], 200)
        self.assertIn('one email a month', page['body'])
        self.assertIn("You&#x27;re signed up", page['body'])
        member = self.mail('updates', 'a@example.com')
        self.assertNotIn('area', member)
        self.assertEqual(member['consent']['S'], self.app.consent_wording())
        self.assertEqual(member['via']['S'], 'website')
        self.assertRegex(member['consentedAt']['S'], r'^\d{4}-\d\d-\d\dT')
        token = member['unsubToken']['S']
        self.assertRegex(token, self.app.TOKEN_PATTERN)
        self.assertEqual(self.mail('unsub', token)['email']['S'], 'a@example.com')
        self.assertEqual(self.db.tables[self.app.SIGNUPS_TABLE], {}, 'the signups table is not touched')

    def test_the_token_is_written_before_the_member_that_names_it(self):
        self.join()
        mail_puts = [w[2] for w in self.db.writes if w[0] == 'put' and w[1] == self.app.MAIL_TABLE]
        self.assertTrue(mail_puts[0].startswith('unsub#') and mail_puts[1].startswith('updates#'), mail_puts)

    def test_joining_again_keeps_the_old_unsubscribe_link_working(self):
        # Audit I-2, 2026-11-23: a re-join used to delete the old token, so the unsubscribe link in every email already
        # sent answered "You are not on the list" and the mail kept coming. Every link we ever sent must still stop it.
        self.join(area='')
        first = self.mail('updates', 'a@example.com')['unsubToken']['S']
        self.join(area='')
        self.assertNotEqual(self.mail('updates', 'a@example.com')['unsubToken']['S'], first)
        self.assertEqual(self.mail('unsub', first)['email']['S'], 'a@example.com', 'the old link still names its address')
        page = self.app.handler(form_post('/v1/signup/unsubscribe', first), None)
        self.assertEqual(page['statusCode'], 200, page['body'])
        self.assertIsNone(self.mail('updates', 'a@example.com'), 'pressing the OLD link took the member off')
        self.assertIsNotNone(self.mail('suppress', 'a@example.com'))

    def test_joining_again_says_so_only_on_the_page_after_the_click(self):
        # Bill's ask, 2026-11-23 (mock-up claude.ai/artifact/BbnnMwCUrpmkBHcDa4tgSz, option 1): a member who signs up again
        # is told so where only the inbox's owner can see it, the page after the click. The form's answer stays one answer
        # for every address (I17), or anyone could test whether an address is on the list.
        first = self.join(area='')
        self.assertIn('You&#x27;re signed up', first['body'])
        self.assertNotIn('already', first['body'])
        member_post = self.app.handler(post({'email': 'a@example.com', 'source': 'updates'}), None)
        stranger_post = self.app.handler(post({'email': 'b@example.com', 'source': 'updates'}), None)
        self.assertEqual(member_post['statusCode'], stranger_post['statusCode'])
        self.assertEqual(member_post['body'], stranger_post['body'], 'the form answers a member as it answers anyone')
        token = next(t for t, row in self.db.tables[self.app.PENDING_TABLE].items() if row['email']['S'] == 'a@example.com')
        again = self.app.handler(form_post('/v1/signup/confirm', token), None)
        self.assertEqual(again['statusCode'], 200, again['body'])
        self.assertIn('You&#x27;re already signed up', again['body'])
        self.assertIn('already on the list for Sky Score news', again['body'])
        self.assertEqual(self.mail('updates', 'a@example.com')['consent']['S'], self.app.consent_wording())

    def test_a_refused_alert_signup_says_nothing_was_saved(self):
        # Audit M-8, 2026-11-23: an API-key holder's score-alert sign-up is refused (already-registered), and the page's
        # heading said "Confirmed" over a message saying nothing was saved.
        token = 'T' * 43
        self.db.tables[self.app.PENDING_TABLE][token] = {
            'token': {'S': token}, 'email': {'S': 'k@example.com'}, 'source': {'S': 'consumer'},
            'postcode': {'S': 'M1 1AE'}, 'expiresAt': {'N': str(int(time.time()) + 3600)}}
        refused = self.app.response(200, {'status': 'already-registered',
                                          'error': 'This email already holds a Sky Score API key; use a different address.'})
        with patch.object(self.app, 'complete_signup', return_value=refused):
            page = self.app.handler(form_post('/v1/signup/confirm', token), None)
        self.assertIn('Nothing was saved', page['body'])
        self.assertNotIn('Confirmed', page['body'])

    def test_the_junk_line_goes_where_a_next_email_is_coming(self):
        # Bill's ask, 2026-11-23: a new domain's first emails to Outlook land in Junk; whoever finds ours there is asked
        # to mark it, so the next one arrives. News and the map's alerts send a next one; an API key request does not.
        link = 'https://skyscore.co.uk/v1/signup/confirm?token=' + 'x' * 43
        for source, want in (('updates', True), ('consumer', True), ('api', False)):
            self.ses.reset_mock()
            self.app.send_confirmation_email('a@example.com', source, 'M1 1AE', link)
            body = self.ses.send_email.call_args.kwargs['Content']['Simple']['Body']
            self.assertEqual(self.app.JUNK_HINT in body['Text']['Data'], want, source)
            page = body['Html']['Data']
            self.assertEqual(self.app.JUNK_HINT in page, want, source)
            if want:  # under the button, in body text, above the small print
                self.assertLess(page.index('Confirm my email</a>'), page.index(self.app.JUNK_HINT))
                self.assertLess(page.index(self.app.JUNK_HINT), page.index(self.app.CONFIRM_SMALL_PRINT))

    def test_the_answer_after_pressing_says_to_look_in_junk(self):
        r = self.app.handler(post({'email': 'a@example.com', 'source': 'updates'}), None)
        self.assertIn('It may land in Junk or Spam, so look there too.', json.loads(r['body'])['message'])

    def test_a_failed_tidy_up_after_joining_still_says_subscribed(self):
        # Review 2026-11-10: a tidy-up failed after the member was written, and the person was told 503. Since 2026-11-23
        # the only tidy-up is clearing the do-not-email entry (old tokens stay).
        self.join(area='')
        first = self.mail('updates', 'a@example.com')['unsubToken']['S']
        self.db.fail.add(('delete', 'suppress#a@example.com'))
        page = self.join(area='')
        self.assertEqual(page['statusCode'], 200, page['body'])
        self.assertIn('one email a month', page['body'])
        self.assertNotEqual(self.mail('updates', 'a@example.com')['unsubToken']['S'], first)

    def test_a_failure_before_joining_points_back_to_the_postcode_search(self):
        self.app.handler(post({'email': 'a@example.com', 'source': 'updates', 'postcode': 'SW15 1HL'}), None)
        token = next(iter(self.db.tables[self.app.PENDING_TABLE]))
        self.db.fail.add(('put', 'updates#'))
        page = self.app.handler(form_post('/v1/signup/confirm', token), None)
        self.assertEqual(page['statusCode'], 503)
        self.assertIn('href="https://skyscore.co.uk/"', page['body'])
        self.assertNotIn('score-demo', page['body'], 'an updates sign-up is never sent to the API-key page')

    def test_a_link_pressed_after_the_list_closes_saves_nothing(self):
        self.app.handler(post({'email': 'a@example.com', 'source': 'updates', 'postcode': 'SW15 1HL'}), None)
        token = next(iter(self.db.tables[self.app.PENDING_TABLE]))
        with patch.object(self.app, 'UPDATES_LIST', False):
            page = self.app.handler(form_post('/v1/signup/confirm', token), None)
        self.assertIn('closed', page['body'])
        self.assertEqual(self.db.tables[self.app.MAIL_TABLE], {})

    def test_the_expired_link_page_offers_every_way_back(self):
        page = self.app.handler(get('/v1/signup/confirm', 'x' * 43), None)
        self.assertEqual(page['statusCode'], 410)
        for href in ('https://skyscore.co.uk/', 'https://skyscore.co.uk/map/', 'https://skyscore.co.uk/score-demo/'):
            self.assertIn(f'href="{href}"', page['body'])

    def test_a_link_emailed_before_an_unsubscribe_and_pressed_after_it_rejoins(self):
        # A listed address gets no new link (DoNotEmailTests), but one already in its inbox is fresh consent when pressed.
        self.app.handler(post({'email': 'a@example.com', 'source': 'updates', 'postcode': ''}), None)
        token = next(iter(self.db.tables[self.app.PENDING_TABLE]))
        self.db.tables[self.app.MAIL_TABLE]['suppress#a@example.com'] = {'pk': {'S': 'suppress#a@example.com'}}
        page = self.app.handler(form_post('/v1/signup/confirm', token), None)
        self.assertEqual(page['statusCode'], 200, page['body'])
        self.assertIsNone(self.mail('suppress', 'a@example.com'))
        self.assertIsNotNone(self.mail('updates', 'a@example.com'))


class DoNotEmailTests(UpdatesBase):
    """Privacy s2a: an unsubscribed address is kept "so we never write to it again", the confirmation email included
    (code review 2026-11-22: nothing read the list, so a stranger typing that address re-sent it a confirmation)."""

    def listed(self, email='a@example.com'):
        self.db.tables[self.app.MAIL_TABLE][f'suppress#{email}'] = {'pk': {'S': f'suppress#{email}'}, 'email': {'S': email}}

    def test_a_listed_address_gets_the_same_answer_and_no_email(self):
        fresh = self.app.handler(post({'email': 'new@example.com', 'source': 'updates', 'postcode': ''}), None)
        self.ses.reset_mock()
        self.db.tables[self.app.PENDING_TABLE].clear()
        self.listed()
        counted = self.db.counted
        r = self.app.handler(post({'email': 'a@example.com', 'source': 'updates', 'postcode': 'SW15 1HL'}), None)
        self.assertEqual((r['statusCode'], r['body']), (fresh['statusCode'], fresh['body']), 'the list cannot be probed')
        self.ses.send_email.assert_not_called()
        self.assertEqual(self.db.tables[self.app.PENDING_TABLE], {}, 'no link exists to press')
        self.assertEqual(self.db.counted, counted, 'no send counter is touched for an address we will not write to')

    def test_every_kind_of_signup_reads_the_list(self):
        # Audit I-1, 2026-11-23: the list was read for news only, so an address that unsubscribed still got API-key and
        # score-alert confirmations when anyone typed it in. Each kind now answers a listed address as it answers anyone.
        for source in ('consumer', 'api', 'updates'):
            with self.subTest(source=source):
                self.db.tables[self.app.PENDING_TABLE].clear()
                fresh = self.app.handler(post({'email': f'new-{source}@example.com', 'source': source, 'postcode': 'M1 1AE'}), None)
                self.ses.reset_mock()
                self.db.tables[self.app.PENDING_TABLE].clear()
                self.listed()
                r = self.app.handler(post({'email': 'a@example.com', 'source': source, 'postcode': 'M1 1AE'}), None)
                self.assertEqual((r['statusCode'], r['body']), (fresh['statusCode'], fresh['body']))
                self.ses.send_email.assert_not_called()
                self.assertEqual(self.db.tables[self.app.PENDING_TABLE], {}, 'no link exists to press')

    def test_a_tagged_or_dotted_form_of_a_listed_inbox_gets_no_email(self):
        # Audit I-2, 2026-11-27: the list matched the exact address, so `alice+news@gmail.com` or `a.lice@gmail.com`
        # still got confirmation emails (every kind of sign-up) after `alice@gmail.com` said stop, though the send cap
        # already counted them as one inbox. Read by the address AND its inbox now.
        self.listed('alice@gmail.com')
        for source in ('updates', 'api'):
            for typed in ('alice+news@gmail.com', 'a.lice@gmail.com', 'A.Lice+x@googlemail.com'):
                with self.subTest(source=source, typed=typed):
                    self.ses.reset_mock()
                    self.db.tables[self.app.PENDING_TABLE].clear()
                    r = self.app.handler(post({'email': typed, 'source': source, 'postcode': 'M1 1AE'}), None)
                    self.assertEqual(r['statusCode'], 201, r['body'])
                    self.ses.send_email.assert_not_called()
                    self.assertEqual(self.db.tables[self.app.PENDING_TABLE], {}, 'no link exists to press')

    def test_a_listed_address_hears_a_full_day_like_anyone(self):
        # Audit M-1, 2026-11-23: once the day's ceiling is full every address hears the 503; a 201 for a listed one alone
        # would say it is on the list.
        import datetime as _dt
        day = _dt.datetime.now(_dt.UTC).strftime('%Y-%m-%d')
        self.db.tables[self.app.PENDING_TABLE][f'{self.app.SEND_COUNTER_PREFIX}{self.app.SEND_CEILING_ROW}#{day}'] = {
            'token': {'S': f'{self.app.SEND_COUNTER_PREFIX}{self.app.SEND_CEILING_ROW}#{day}'},
            'sends': {'N': str(self.app.SEND_CEILING_PER_DAY)}}
        self.listed()
        with patch.object(self.app, 'send_decision', return_value='full'):
            stranger = self.app.handler(post({'email': 'new@example.com', 'source': 'updates'}), None)
        listed = self.app.handler(post({'email': 'a@example.com', 'source': 'updates'}), None)
        self.assertEqual(stranger['statusCode'], 503)
        self.assertEqual((listed['statusCode'], listed['body']), (stranger['statusCode'], stranger['body']))
        self.ses.send_email.assert_not_called()

    def test_the_list_is_read_before_anything_else(self):
        self.app.handler(post({'email': 'a@example.com', 'source': 'updates', 'postcode': ''}), None)
        self.assertEqual(self.db.reads[0], (self.app.MAIL_TABLE, 'suppress#a@example.com'))

    def test_an_unreadable_list_fails_closed(self):
        self.db.fail.add(('get', 'suppress#'))
        r = self.app.handler(post({'email': 'a@example.com', 'source': 'updates', 'postcode': ''}), None)
        self.assertEqual(r['statusCode'], 503)
        self.ses.send_email.assert_not_called()
        self.assertEqual(self.db.tables[self.app.PENDING_TABLE], {})

    def test_the_confirm_path_spends_no_more_hops_than_budgeted(self):
        # pending DeleteItem + unsub PutItem + member PutItem (returning the old one) + 2 tidy DeleteItems = 5.
        self.join(area='SW15 1HL')
        self.db.writes.clear()
        self.db.reads.clear()
        self.join(area='TW9 3PZ')
        confirm_calls = [w for w in self.db.writes if w[1] != self.app.PENDING_TABLE or w[0] == 'delete']
        confirm_reads = [r for r in self.db.reads if r[0] != self.app.MAIL_TABLE or not r[1].startswith('suppress#')]
        self.assertEqual(confirm_reads, [], 'the confirm reads nothing: the old member comes back from the write')
        self.assertLessEqual(len(confirm_calls), 5, confirm_calls)


class UnsubscribeTests(UpdatesBase):
    def setUp(self):
        super().setUp()
        self.join()
        self.token = self.mail('updates', 'a@example.com')['unsubToken']['S']

    def test_the_get_shows_a_button_and_changes_nothing(self):
        before = dict(self.db.tables[self.app.MAIL_TABLE])
        page = self.app.handler(get('/v1/signup/unsubscribe', self.token), None)
        self.assertEqual(page['statusCode'], 200)
        self.assertIn('<form method="post">', page['body'])
        self.assertEqual(self.db.tables[self.app.MAIL_TABLE], before)

    def test_the_button_unsubscribes_and_suppresses(self):
        page = self.app.handler(form_post('/v1/signup/unsubscribe', self.token), None)
        self.assertEqual(page['statusCode'], 200)
        self.assertIn('unsubscribed', page['body'])
        self.assertIsNone(self.mail('updates', 'a@example.com'))
        self.assertIsNone(self.mail('unsub', self.token))
        self.assertEqual(self.mail('suppress', 'a@example.com')['email']['S'], 'a@example.com')

    def rows_naming(self, email):
        return sorted(k for k, row in self.db.tables[self.app.MAIL_TABLE].items()
                      if row.get('email', {}).get('S') == email and not k.startswith('suppress#'))

    def test_an_unsubscribe_forgets_every_token_of_the_address(self):
        # Audit I-3, 2026-11-27: a re-join keeps the old token (23 Nov's I-2), and an unsubscribe used to leave it, with
        # the address in it, for ever, against privacy s2a ("we then delete it, keeping only the address on a
        # do-not-email list"). Now nothing but the do-not-email entry names the address afterwards.
        old = self.token
        self.join()
        new = self.mail('updates', 'a@example.com')['unsubToken']['S']
        self.assertNotEqual(old, new)
        self.assertEqual(self.rows_naming('a@example.com'), sorted([f'unsub#{old}', f'unsub#{new}', 'updates#a@example.com']))
        page = self.app.handler(form_post('/v1/signup/unsubscribe', new), None)
        self.assertEqual(page['statusCode'], 200, page['body'])
        self.assertEqual(self.rows_naming('a@example.com'), [], 'only the do-not-email entry may name the address')
        self.assertIsNotNone(self.mail('suppress', 'a@example.com'))

    def test_an_unsubscribe_lists_the_inbox_too(self):
        # Audit I-2, 2026-11-27: so the plain address, or any other alias of that inbox, hears nothing either.
        self.join(email='a.lice+news@gmail.com')
        token = self.mail('updates', 'a.lice+news@gmail.com')['unsubToken']['S']
        self.assertEqual(self.app.handler(form_post('/v1/signup/unsubscribe', token), None)['statusCode'], 200)
        self.assertIsNotNone(self.mail('suppress', 'a.lice+news@gmail.com'))
        self.assertEqual(self.mail('suppress', 'alice@gmail.com')['email']['S'], 'a.lice+news@gmail.com')
        self.ses.reset_mock()
        self.db.tables[self.app.PENDING_TABLE].clear()
        r = self.app.handler(post({'email': 'alice@gmail.com', 'source': 'updates', 'postcode': ''}), None)
        self.assertEqual(r['statusCode'], 201, r['body'])
        self.ses.send_email.assert_not_called()

    def test_a_mail_clients_one_click_post_works(self):
        event = {'httpMethod': 'POST', 'path': '/v1/signup/unsubscribe', 'body': 'List-Unsubscribe=One-Click',
                 'queryStringParameters': {'token': self.token}, 'requestContext': CTX, 'headers': {}}
        self.assertEqual(self.app.handler(event, None)['statusCode'], 200)
        self.assertIsNone(self.mail('updates', 'a@example.com'))
        self.assertIsNotNone(self.mail('suppress', 'a@example.com'))

    def test_a_failure_part_way_is_finished_by_the_retry(self):
        # Review 2026-11-10: the token went first, so a failed member delete left the person subscribed and the retry
        # said there was nothing to stop. Now the token goes LAST, and the retry completes the job.
        self.db.fail.add(('delete', 'updates#'))
        first = self.app.handler(form_post('/v1/signup/unsubscribe', self.token), None)
        self.assertEqual(first['statusCode'], 503)
        self.assertIsNotNone(self.mail('unsub', self.token), 'the link still works after a failure')
        self.assertIsNotNone(self.mail('suppress', 'a@example.com'), 'no email goes out meanwhile')
        retry = self.app.handler(form_post('/v1/signup/unsubscribe', self.token), None)
        self.assertEqual(retry['statusCode'], 200)
        self.assertIn('unsubscribed', retry['body'])
        self.assertIsNone(self.mail('updates', 'a@example.com'))
        self.assertIsNone(self.mail('unsub', self.token))

    def test_an_unknown_or_used_token_says_so_and_changes_nothing(self):
        self.app.handler(form_post('/v1/signup/unsubscribe', self.token), None)
        before = dict(self.db.tables[self.app.MAIL_TABLE])
        for token in (self.token, 'x' * 43):
            page = self.app.handler(form_post('/v1/signup/unsubscribe', token), None)
            self.assertEqual(page['statusCode'], 200)
            self.assertIn('not on the list', page['body'])
        self.assertEqual(self.db.tables[self.app.MAIL_TABLE], before)

    def test_a_malformed_token_is_a_400_page(self):
        for token in ('', 'short', 'bad token with spaces!'):
            self.assertEqual(self.app.handler(form_post('/v1/signup/unsubscribe', token), None)['statusCode'], 400)


class TemplateTests(unittest.TestCase):
    def setUp(self):
        with open(TEMPLATE, encoding='utf-8') as fh:
            self.t = fh.read()

    def test_the_list_ships_on_since_bills_approval(self):
        m = re.search(r"\n  UpdatesList:\n(?:    .*\n)+", self.t)
        self.assertIsNotNone(m)
        self.assertIn("Default: 'on'", m.group(0))
        self.assertIn('UPDATES_LIST: !Ref UpdatesList', self.t)
        self.assertIn('MAIL_TABLE: !Ref MailTable', self.t)

    def test_the_unsubscribe_routes_exist_with_their_own_throttles(self):
        for method in ('get', 'post'):
            self.assertRegex(self.t, rf'Path: /v1/signup/unsubscribe\n\s+Method: {method}')
            self.assertRegex(self.t, rf'HttpMethod: {method.upper()}\n\s+ResourcePath: /v1/signup/unsubscribe\n\s+ThrottlingRateLimit: 2')

    def test_the_table_is_retained_and_backed_up_and_the_function_may_use_it(self):
        m = re.search(r'\n  MailTable:\n(?:    .*\n|      .*\n|        .*\n)+', self.t)
        self.assertIsNotNone(m)
        block = m.group(0)
        for want in ('DeletionPolicy: Retain', 'TableName: london-flight-map-mail', 'AttributeName: pk', 'PointInTimeRecoveryEnabled: true'):
            self.assertIn(want, block)
        self.assertRegex(self.t, r'DynamoDBCrudPolicy:\n\s+TableName: !Ref MailTable')


if __name__ == '__main__':
    unittest.main()
