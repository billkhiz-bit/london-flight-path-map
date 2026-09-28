"""No gate may spend the PUBLIC demo key, except the one that tests it.

The demo key is printed in score-demo/status.html and score-demo/index.html,
so it is shared by every visitor to the API tester - and, until 2026-09-28, by
every preflight run. `tests/stub-live-api.mjs` was written on 2026-09-11 for
"both current callers" (a11y-source, responsive); two more gates loaded
status.html without it (fonts-selfhosted, e2e/accessibility.spec.js), which is
why the key still logged 100-190 calls a day on working days after the fix.

That mattered beyond the quota: the demo key's daily usage is the ONLY measure
of whether a prospect has tried the API, and it cannot mean that while our own
gates add to it. So the rule is structural, not a list:

1. Any test file that names status.html must use stubLiveApi.
2. The demo key's literal value may appear only in demo-key-scope.mjs, whose
   job is to prove the demo plan's route denies and so must spend a few calls.

What this does NOT catch: a gate that reaches status.html through a DERIVED
path (a directory walk) without ever naming it. None does today; a11y-source
and responsive both name it in their page lists.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / 'tests'
STUB = TESTS / 'stub-live-api.mjs'
KEY_TESTER = TESTS / 'demo-key-scope.mjs'


def gate_files():
    return sorted(p for p in TESTS.rglob('*') if p.suffix in ('.js', '.mjs') and p != STUB)


def demo_key():
    """Read the key from the page that publishes it, so a rotation needs no edit here."""
    src = (ROOT / 'score-demo' / 'status.html').read_text(encoding='utf-8')
    m = re.search(r"API_KEY\s*=\s*'([A-Za-z0-9]{20,})'", src)
    if not m:
        raise AssertionError('could not find API_KEY in score-demo/status.html - this guard would check nothing')
    return m.group(1)


class DemoKeySpenderTests(unittest.TestCase):
    def test_every_gate_loading_status_page_uses_the_stub(self):
        loaders = [p for p in gate_files() if 'status.html' in p.read_text(encoding='utf-8')]
        # Floor: if this finds none, the search itself has broken, not the gates.
        self.assertGreaterEqual(len(loaders), 4, f'expected >=4 gates naming status.html, found {loaders}')
        unstubbed = [p.relative_to(ROOT).as_posix() for p in loaders if 'stubLiveApi' not in p.read_text(encoding='utf-8')]
        self.assertEqual(unstubbed, [], 'these gates load score-demo/status.html without stubLiveApi, so every run '
                         'spends the PUBLIC demo key: ' + ', '.join(unstubbed))

    def test_demo_key_literal_only_in_the_gate_that_tests_it(self):
        key = demo_key()
        holders = [p.relative_to(ROOT).as_posix() for p in gate_files() if key in p.read_text(encoding='utf-8')]
        self.assertEqual(holders, [KEY_TESTER.relative_to(ROOT).as_posix()],
                         'the public demo key is spent only by demo-key-scope.mjs; give any other gate the CI key')


if __name__ == '__main__':
    unittest.main()
