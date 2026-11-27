"""The news strip counts sends by inbox exactly as the Lambda does (audit M-6, 2026-11-25).

The Lambda sends at most SEND_CAP_PER_DAY a day to one INBOX, keyed by mailbox_key() (lower case, any +tag dropped,
Gmail's dots ignored), and answers a capped request with the same 201 as a real send. The strip (js/news-signup.mjs)
now keeps its own count by inbox so that "Use a different address" cannot offer the same inbox a send the Lambda would
skip; that only holds while its mailboxKey() says what mailbox_key() says. This runs both, the JS in node on the repo's
own module, over the same addresses, and holds their Gmail tables equal.
"""
import importlib.util
import json
import os
import subprocess
import sys
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
LAMBDAS_DIR = os.path.join(REPO, 'backend', 'lambdas')

ADDRESSES = [
    'someone@example.com', 'Someone@Example.com', 'someone+news@example.com', 'some.one@example.com',
    'some.one@gmail.com', 'S.o.m.e.One+x@GMAIL.com', 'someone@googlemail.com', 'a+b+c@example.org',
    'first.last+tag@outlook.com', 'x@sub.example.co.uk', '  padded@example.com  ', 'a@b',
]


def load_signup():
    alias = 'signup_app_mailbox_parity'
    if alias in sys.modules:
        return sys.modules[alias]
    spec = importlib.util.spec_from_file_location(alias, os.path.join(LAMBDAS_DIR, 'signup', 'app.py'))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


def site_keys(addresses):
    js = (
        "import { readFileSync } from 'node:fs';"
        "import { mailboxKey, DOT_BLIND_DOMAINS } from './js/news-signup.mjs';"
        "const list = JSON.parse(readFileSync(0, 'utf8'));"
        "console.log(JSON.stringify({ keys: list.map((a) => mailboxKey(a)), dots: DOT_BLIND_DOMAINS }));"
    )
    out = subprocess.run(  # noqa: S603 - node with our own fixed script
        ['node', '--input-type=module', '-e', js],  # noqa: S607 - node from PATH, as preflight runs it
        cwd=REPO, input=json.dumps(addresses), capture_output=True, text=True, encoding='utf-8', check=True,
    ).stdout
    return json.loads(out)


class MailboxKeyParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = load_signup()
        cls.site = site_keys(ADDRESSES)

    def test_same_gmail_table(self):
        self.assertEqual(self.site['dots'], self.app.DOT_BLIND_DOMAINS)

    def test_same_inbox_for_every_address(self):
        # The Lambda is handed a trimmed, lower-cased address (handle_post); the strip lower-cases and trims itself.
        lambda_keys = [self.app.mailbox_key(a.strip().lower()) for a in ADDRESSES]
        self.assertEqual(self.site['keys'], lambda_keys)

    def test_the_news_sender_reads_the_do_not_email_list_by_the_same_inbox(self):
        # Audit I-2, 2026-11-27: the sign-up writes the do-not-email entries by the address and its inbox, and the news
        # sender reads them by its OWN copy of mailbox_key: the two must agree, or an alias slips past the list.
        spec = importlib.util.spec_from_file_location('news_app_mailbox_parity', os.path.join(LAMBDAS_DIR, 'news', 'app.py'))
        news = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(news)
        self.assertEqual(news.DOT_BLIND_DOMAINS, self.app.DOT_BLIND_DOMAINS)
        for a in ADDRESSES:
            email = a.strip().lower()
            self.assertEqual(news.mailbox_key(email), self.app.mailbox_key(email), email)
            self.assertEqual(news.suppress_keys(email), self.app.suppress_keys(email), email)


if __name__ == '__main__':
    unittest.main()
