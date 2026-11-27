"""The monthly news sender (backend/lambdas/news/app.py; Bill's picks 2026-11-23). Why each test is here:

  - layout A with the fixed subject, every link ours and tagged for totals only, nothing remote, the same words in the
    plain-text part;
  - an issue file is refused unless its id is its month, its subject is the fixed form and every link is a skyscore.co.uk
    page; an issue with nothing new is never sent;
  - a preview goes to ONE address and never reads the list;
  - a send needs the exact confirm words, an approved file and its own month (at most one email a month);
  - only confirmed members, the do-not-email list read before each send, never a member without a working unsubscribe
    link, each member's own link, one-click unsubscribe headers, once each (a re-run sends nothing twice), and one
    failure does not stop the rest;
  - the function has no route, and only the access it needs.

Offline: the module's ddb and ses clients are replaced by an in-memory table and a mock, so the tests read what was
STORED and SENT.
"""
import datetime as dt
import email
import email.policy
import importlib.util
import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

LAMBDAS = Path(__file__).resolve().parent.parent / 'lambdas'
TEMPLATE = LAMBDAS.parent / 'template.yaml'


def load_news():
    alias = 'news_app_under_test'
    if alias in sys.modules:
        return sys.modules[alias]
    os.environ.setdefault('AWS_REGION', 'eu-west-2')
    spec = importlib.util.spec_from_file_location(alias, LAMBDAS / 'news' / 'app.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeMail:
    """The mail table keyed by `pk`, with the scan, get and put the sender uses; records the order of every read."""

    def __init__(self):
        self.rows = {}
        self.log = []

    def scan(self, TableName, FilterExpression, ExpressionAttributeValues, **_):
        prefix = ExpressionAttributeValues[':p']['S']
        self.log.append(('scan', prefix))
        return {'Items': [r for k, r in sorted(self.rows.items()) if k.startswith(prefix)]}

    def get_item(self, TableName, Key, **_):
        self.log.append(('get', Key['pk']['S']))
        row = self.rows.get(Key['pk']['S'])
        return {'Item': row} if row else {}

    def put_item(self, TableName, Item, ConditionExpression=None, **_):
        pk = Item['pk']['S']
        self.log.append(('put', pk))
        # A member's copy is CLAIMED with a conditional write (audit M-2, 2026-11-27), refused as DynamoDB refuses it.
        if ConditionExpression == 'attribute_not_exists(pk)' and pk in self.rows:
            raise ClientError({'Error': {'Code': 'ConditionalCheckFailedException'}}, 'PutItem')
        self.rows[pk] = Item
        return {}

    def delete_item(self, TableName, Key, **_):
        self.log.append(('delete', Key['pk']['S']))
        self.rows.pop(Key['pk']['S'], None)
        return {}

    def member(self, email, token='', consent=True):
        row = {'pk': {'S': f'updates#{email}'}, 'email': {'S': email}}
        if consent:
            row['consent'] = {'S': 'news-v2 (2026-11-22): News by email. New cities and new data. At most one email a month.'}
        if token:
            row['unsubToken'] = {'S': token}
        self.rows[f'updates#{email}'] = row


ISSUE = {
    'id': '2026-12', 'approved': True, 'subject': 'Sky Score news: December 2026', 'heading': "What's new this month",
    'intro': 'Two changes.',
    'items': [
        {'title': 'Planes overhead now runs to September 2026', 'body': 'Nine airports.',
         'link': 'https://skyscore.co.uk/planes-overhead/', 'label': 'See the planes'},
        {'title': 'House prices to September 2026', 'body': 'The UK House Price Index for September.',
         'link': 'https://skyscore.co.uk/area/', 'label': 'Browse council areas'},
    ],
}
TOKEN_A = 'A' * 43
TOKEN_E = 'E' * 43
DECEMBER = dt.date(2026, 12, 3)


class NewsBase(unittest.TestCase):
    def setUp(self):
        self.app = load_news()
        self.db = FakeMail()
        self.ses = MagicMock()
        self.patches = [patch.object(self.app, 'ddb', self.db), patch.object(self.app, 'ses', self.ses)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def sent(self):
        """[(to, parsed message)] for every email the mock SES was asked to send."""
        out = []
        for call in self.ses.send_email.call_args_list:
            kw = call.kwargs
            # The modern parser unfolds headers as a mail app does.
            out.append((kw['Destination']['ToAddresses'][0],
                        email.message_from_bytes(kw['Content']['Raw']['Data'], policy=email.policy.default)))
        return out

    @staticmethod
    def part(msg, kind):
        for p in msg.walk():
            if p.get_content_type() == f'text/{kind}':
                return p.get_payload(decode=True).decode('utf-8')
        return ''


class RenderTests(NewsBase):
    def test_layout_a_every_link_ours_and_tagged_nothing_remote(self):
        subject, text, page = self.app.render(ISSUE, TOKEN_A)
        self.assertEqual(subject, 'Sky Score news: December 2026')
        for item in ISSUE['items']:
            for key in ('title', 'body', 'label'):
                self.assertIn(item[key], page)
                self.assertIn(item[key], text, 'the plain-text part carries the same words')
        hrefs = re.findall(r'href="([^"]+)"', page)
        self.assertTrue(hrefs)
        for h in hrefs:
            self.assertTrue(h.startswith('https://skyscore.co.uk'), h)
        for item in ISSUE['items']:
            self.assertIn(item['link'] + '?utm_source=news&amp;utm_medium=email&amp;utm_campaign=2026-12', page)
        for banned in ('<img', 'src=', 'url(', '@import', '<script', '<link'):
            self.assertNotIn(banned, page.lower(), banned)
        self.assertIn(f'https://skyscore.co.uk/v1/signup/unsubscribe?token={TOKEN_A}', text)

    def test_every_word_is_escaped(self):
        issue = {**ISSUE, 'items': [{**ISSUE['items'][0], 'body': '<b>bold</b> & more'}]}
        _s, _t, page = self.app.render(issue, TOKEN_A)
        self.assertIn('&lt;b&gt;bold&lt;/b&gt; &amp; more', page)
        self.assertNotIn('<b>bold</b>', page)


class IssueFileTests(NewsBase):
    def write(self, name, data):
        import json
        d = Path(self.tmp.name)
        (d / name).write_text(json.dumps(data), encoding='utf-8')

    def setUp(self):
        super().setUp()
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.p_issues = patch.object(self.app, 'ISSUES', Path(self.tmp.name))
        self.p_issues.start()

    def tearDown(self):
        self.p_issues.stop()
        self.tmp.cleanup()
        super().tearDown()

    def refused(self, data, issue_id='2026-12'):
        self.write(f'{issue_id}.json', data)
        with self.assertRaises(self.app.Refused):
            self.app.load_issue(issue_id)

    def test_a_good_file_loads(self):
        self.write('2026-12.json', ISSUE)
        self.assertEqual(self.app.load_issue('2026-12')['id'], '2026-12')

    def test_refusals(self):
        self.refused({**ISSUE, 'subject': 'Big news from Sky Score!'})
        self.refused({**ISSUE, 'id': '2026-11'})
        self.refused({**ISSUE, 'items': []})
        self.refused({**ISSUE, 'items': [{**ISSUE['items'][0], 'link': 'https://example.com/'}]})
        self.refused({**ISSUE, 'items': [{**ISSUE['items'][0], 'link': 'http://skyscore.co.uk/'}]})
        self.refused({**ISSUE, 'items': [{**ISSUE['items'][0], 'link': 'https://skyscore.co.uk/?x=1'}]})
        self.refused({**ISSUE, 'items': [{**ISSUE['items'][0], 'label': ''}]})
        with self.assertRaises(self.app.Refused):
            self.app.load_issue('December')

    def test_the_real_first_issue_loads_and_is_not_approved(self):
        with patch.object(self.app, 'ISSUES', LAMBDAS / 'news' / 'issues'):
            issue = self.app.load_issue('2026-12')
        self.assertIs(issue.get('approved'), False, 'the first issue ships unapproved: Bill approves after the preview')


class PreviewTests(NewsBase):
    def test_one_copy_to_one_address_and_the_list_is_never_read(self):
        self.db.member('a@example.com', TOKEN_A)
        out = self.app.preview(ISSUE, 'bill@example.com')
        self.assertEqual(out['sent'], 1)
        sent = self.sent()
        self.assertEqual([to for to, _ in sent], ['bill@example.com'])
        self.assertTrue(sent[0][1]['Subject'].startswith('[Preview] Sky Score news: December 2026'))
        self.assertFalse([e for e in self.db.log if e[0] == 'scan'], 'a preview must never read the list')

    def test_a_preview_needs_an_address(self):
        with self.assertRaises(self.app.Refused):
            self.app.preview(ISSUE, None)
        self.ses.send_email.assert_not_called()


class SendGateTests(NewsBase):
    def setUp(self):
        super().setUp()
        self.db.member('a@example.com', TOKEN_A)

    def test_the_exact_confirm_words(self):
        for confirm in (None, 'yes', 'send 2026-11', 'SEND 2026-12'):
            with self.assertRaises(self.app.Refused):
                self.app.send(ISSUE, confirm, today=DECEMBER, pause=0)
        self.ses.send_email.assert_not_called()

    def test_an_unapproved_issue(self):
        with self.assertRaises(self.app.Refused):
            self.app.send({**ISSUE, 'approved': False}, 'send 2026-12', today=DECEMBER, pause=0)
        self.ses.send_email.assert_not_called()

    def test_only_in_its_own_month(self):
        for day in (dt.date(2026, 11, 30), dt.date(2027, 1, 1)):
            with self.assertRaises(self.app.Refused):
                self.app.send(ISSUE, 'send 2026-12', today=day, pause=0)
        self.ses.send_email.assert_not_called()

    def test_the_handler_says_why_in_words(self):
        out = self.app.handler({'issue': '2026-12', 'mode': 'shout'}, None)
        self.assertEqual(out['sent'], 0)
        self.assertIn('refused', out)


class SendTests(NewsBase):
    def setUp(self):
        super().setUp()
        self.db.member('a@example.com', TOKEN_A)
        self.db.member('b@example.com', 'B' * 43)
        self.db.rows['suppress#b@example.com'] = {'pk': {'S': 'suppress#b@example.com'}}
        self.db.member('c@example.com', 'C' * 43, consent=False)
        self.db.member('d@example.com', '')
        self.db.member('e@example.com', TOKEN_E)

    def sent_row(self, who):
        return f"sent#{self.app.sent_key('2026-12', who)}"

    def test_confirmed_members_only_once_each(self):
        out = self.app.send(ISSUE, 'send 2026-12', today=DECEMBER, pause=0)
        self.assertEqual([to for to, _ in self.sent()], ['a@example.com', 'e@example.com'])
        self.assertEqual((out['sent'], out['do_not_email'], out['no_token'], out['already'], out['failed']), (2, 1, 1, 0, 0))
        self.assertIn(self.sent_row('a@example.com'), self.db.rows)
        again = self.app.send(ISSUE, 'send 2026-12', today=DECEMBER, pause=0)
        self.assertEqual((again['sent'], again['already']), (0, 2), 'a re-run sends nothing twice')
        self.assertEqual(len(self.sent()), 2)

    def test_the_do_not_email_list_is_read_before_each_send(self):
        self.app.send(ISSUE, 'send 2026-12', today=DECEMBER, pause=0)
        for who in ('a@example.com', 'e@example.com'):
            reads = [k for op, k in self.db.log if op == 'get']
            self.assertIn(f'suppress#{who}', reads)
            put_at = self.db.log.index(('put', self.sent_row(who)))
            self.assertLess(self.db.log.index(('get', f'suppress#{who}')), put_at)

    def test_a_listed_inbox_stops_its_other_forms(self):
        # Audit I-2, 2026-11-27: the list is read by the address AND its inbox, so a tagged or dotted Gmail form of an
        # address that said stop hears nothing either.
        self.db.member('a.lice+news@gmail.com', 'F' * 43)
        self.db.rows['suppress#alice@gmail.com'] = {'pk': {'S': 'suppress#alice@gmail.com'}}
        out = self.app.send(ISSUE, 'send 2026-12', today=DECEMBER, pause=0)
        self.assertNotIn('a.lice+news@gmail.com', [to for to, _ in self.sent()])
        self.assertEqual(out['do_not_email'], 2)

    def test_the_sent_record_names_no_address_and_expires_after_the_month(self):
        # Audit I-3, 2026-11-27: these rows outlived an unsubscribe with the address in them. Now a hash, gone a week
        # after the issue's month (MailTable's TTL on expiresAt).
        self.app.send(ISSUE, 'send 2026-12', today=DECEMBER, pause=0)
        sent = {k: r for k, r in self.db.rows.items() if k.startswith('sent#')}
        self.assertEqual(len(sent), 2)
        for key, row in sent.items():
            self.assertNotIn('@', key, 'a sent record must not hold the address')
            self.assertNotIn('email', row)
            self.assertEqual(int(row['expiresAt']['N']),
                             int(dt.datetime(2027, 1, 8, tzinfo=dt.UTC).timestamp()), key)

    def test_a_copy_already_claimed_is_never_sent_again(self):
        # Audit M-2, 2026-11-27: the claim comes BEFORE SES, so a run alongside another, or after a write that failed,
        # can never send a second copy.
        self.db.rows[self.sent_row('a@example.com')] = {'pk': {'S': self.sent_row('a@example.com')}}
        order = []
        self.ses.send_email.side_effect = lambda **kw: order.append(('ses', kw['Destination']['ToAddresses'][0])) or {}
        out = self.app.send(ISSUE, 'send 2026-12', today=DECEMBER, pause=0)
        self.assertEqual([to for _, to in order], ['e@example.com'])
        self.assertEqual((out['sent'], out['already']), (1, 1))
        claim_at = self.db.log.index(('put', self.sent_row('e@example.com')))
        self.assertLess(claim_at, len(self.db.log), 'the claim is written')
        # botocore reads max_attempts as RETRIES (N + 1 in all), so "never retried" is total_max_attempts 1.
        self.assertEqual(self.app._SES_BOTO.retries, {'total_max_attempts': 1, 'mode': 'standard'},
                         'SES is never retried: a timed-out send may have gone')

    def test_each_member_gets_their_own_link_and_the_one_click_headers(self):
        self.app.send(ISSUE, 'send 2026-12', today=DECEMBER, pause=0)
        by = dict(self.sent())
        for who, mine, theirs in (('a@example.com', TOKEN_A, TOKEN_E), ('e@example.com', TOKEN_E, TOKEN_A)):
            msg = by[who]
            self.assertEqual(msg['List-Unsubscribe'], f'<https://skyscore.co.uk/v1/signup/unsubscribe?token={mine}>')
            self.assertEqual(msg['List-Unsubscribe-Post'], 'List-Unsubscribe=One-Click')
            self.assertEqual(msg['Reply-To'], 'Sky Score <support@skyscore.co.uk>')
            self.assertEqual(msg['Subject'], 'Sky Score news: December 2026')
            for kind in ('plain', 'html'):
                body = self.part(msg, kind)
                self.assertIn(mine, body)
                self.assertNotIn(theirs, body)

    def test_it_stops_with_time_in_hand_and_the_next_run_carries_on(self):
        left = iter([20000, 4000])  # time for one member, then under the 5 s it keeps in hand
        out = self.app.send(ISSUE, 'send 2026-12', today=DECEMBER, pause=0, ms_left=lambda: next(left))
        self.assertTrue(out['stopped_early'])
        self.assertEqual([to for to, _ in self.sent()], ['a@example.com'])
        again = self.app.send(ISSUE, 'send 2026-12', today=DECEMBER, pause=0, ms_left=lambda: 20000)
        self.assertFalse(again['stopped_early'])
        self.assertEqual([to for to, _ in self.sent()], ['a@example.com', 'e@example.com'], 'each member once')

    def test_one_failure_does_not_stop_the_rest_and_is_sent_on_the_rerun(self):
        calls = {'n': 0}

        def flaky(**_):
            calls['n'] += 1
            if calls['n'] == 1:
                raise ClientError({'Error': {'Code': 'Throttling'}}, 'SendEmail')
            return {}

        self.ses.send_email.side_effect = flaky
        out = self.app.send(ISSUE, 'send 2026-12', today=DECEMBER, pause=0)
        self.assertEqual((out['sent'], out['failed']), (1, 1))
        self.assertNotIn(self.sent_row('a@example.com'), self.db.rows, 'a failed send gives its claim back, so a re-run sends it')
        self.ses.send_email.side_effect = None
        again = self.app.send(ISSUE, 'send 2026-12', today=DECEMBER, pause=0)
        self.assertEqual((again['sent'], again['already']), (1, 1))


class TemplateTests(unittest.TestCase):
    def block(self):
        text = TEMPLATE.read_text(encoding='utf-8')
        m = re.search(r'\n  NewsFunction:\n(.*?)(?=\n  [A-Za-z]+:\n)', text, re.S)
        self.assertIsNotNone(m, 'NewsFunction is missing from the template')
        return m.group(1)

    def test_no_route_and_only_what_it_needs(self):
        b = self.block()
        self.assertIn('CodeUri: lambdas/news/', b)
        self.assertNotIn('Events:', b, 'the sender has no route: Bill triggers it from the console')
        self.assertIn('MAIL_TABLE: !Ref MailTable', b)
        self.assertIn('ses:SendEmail', b)
        self.assertIn('TableName: !Ref MailTable', b)
        for other in ('SignupsTable', 'SignupPendingTable', 'apigateway:', 'bedrock:', 'lambda:InvokeFunction'):
            self.assertNotIn(other, b, other)

    def test_its_logs_expire_as_privacy_says_and_its_records_expire(self):
        # Audit M-1, 2026-11-27: made by the template with 30 days BEFORE the first run (Lambda's own group never
        # expires); and I-3: MailTable expires the sent# rows on expiresAt.
        text = TEMPLATE.read_text(encoding='utf-8')
        group = re.search(r'\n  NewsLogGroup:\n(.*?)(?=\n  [A-Za-z]+:\n|\n\n  #)', text, re.S)
        self.assertIsNotNone(group, 'NewsLogGroup is missing: its first run would make a log group that never expires')
        self.assertIn("LogGroupName: !Sub '/aws/lambda/${NewsFunction}'", group.group(1))
        self.assertIn('RetentionInDays: 30', group.group(1))
        mail = re.search(r'\n  MailTable:\n(.*?)(?=\n  [A-Za-z]+:\n|\n\n  #)', text, re.S)
        self.assertIsNotNone(mail)
        self.assertRegex(mail.group(1), r'TimeToLiveSpecification:\s+AttributeName: expiresAt\s+Enabled: true')
