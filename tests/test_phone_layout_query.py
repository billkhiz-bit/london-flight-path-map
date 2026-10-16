"""The full map's phone layout is ONE condition, stated the same way everywhere (audit 2026-10-16 I-5).

The phone layout used to be width alone (900 px), so a wide but short screen - a phone on its
side at 915x412 - got the desktop layout and its chrome piled onto the map. It now applies below
500 px of height too. The condition lives in PHONE_LAYOUT (index.html) for the JavaScript and in
every @media rule for the CSS; a rule left on width alone would split the page into half one
layout and half the other on exactly the screens this fixed.
"""

import os
import re
import unittest

PAGE = os.path.join(os.path.dirname(__file__), '..', 'index.html')
PHONE = '(max-width: 900px), (max-height: 500px)'
# Every @media rule that names the 900 px or 500 px line, and what it may say.
ALLOWED = {
    PHONE,
    '(max-height: 500px)',  # short screens, any width: all phone layout now
    '(max-width: 480px), (max-height: 500px)',
    '(min-width: 901px) and (min-height: 501px)',
    '(min-width: 901px) and (max-width: 1366px) and (min-height: 501px)',
    '(min-width: 640px) and (max-width: 900px)',  # a tablet held upright: tall, so never short
}
RULE = re.compile(r'^\s*@media ([^{\n]+?)\s*\{\s*$', re.M)
LINE = re.compile(r'\b(900|901|500|501)px')


class PhoneLayoutQueryTests(unittest.TestCase):
    def setUp(self):
        self.src = open(PAGE, encoding='utf-8').read()

    def test_the_javascript_holder_is_the_phone_condition(self):
        m = re.search(r"const PHONE_LAYOUT = '([^']+)';", self.src)
        self.assertIsNotNone(m, 'PHONE_LAYOUT is missing from index.html')
        self.assertEqual(m.group(1), PHONE)
        # No width-only test left in the script.
        self.assertEqual(re.findall(r'innerWidth\s*[<>]=?\s*90[01]', self.src), [])

    def test_every_900px_media_rule_states_the_same_line(self):
        # Real rules only (a line that IS an @media rule), never the words in a comment.
        rules = [r.strip() for r in RULE.findall(self.src) if LINE.search(r)]
        self.assertGreaterEqual(len(rules), 10, f'expected the phone and desktop rules, found {len(rules)}')
        for rule in rules:
            with self.subTest(rule=rule):
                self.assertIn(rule, ALLOWED, 'a width-only (or new) 900 px rule: state the phone condition')


if __name__ == '__main__':
    unittest.main()
