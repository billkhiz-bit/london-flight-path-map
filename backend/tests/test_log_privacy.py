"""No Lambda may write a full postcode or precise coordinates into its log.

privacy.html s2d promises execution logs hold "postcodes only as the district
(for example SW11)" and no IP addresses. Until 2026-09-28 fifteen log lines in
three Lambdas wrote the FULL postcode (score, sold_prices) or coordinates to
4 dp (~11 m, from /v1/environment and /nhs lookups) whenever a lookup
degraded, and the policy did not mention either.

The check is STRUCTURAL: it parses every Lambda and fails on any logger call
whose arguments reach a postcode or coordinate variable except through
`_log_district()` / `_log_coarse()`. Found by AST rather than by grep because
a grep for single-line calls missed a multi-line one on its first run.

What this does not catch: a postcode that reaches a log line under a name not
in LOCATION_NAMES, or inside an exception message. The names list is the
vocabulary the Lambdas use today; extend it when a new one appears.
"""

import ast
import sys
import unittest
from pathlib import Path

LAMBDAS = Path(__file__).resolve().parent.parent / 'lambdas'
LOCATION_NAMES = {'postcode', 'postcode_clean', 'clean', 'pc', 'outcode', 'lat', 'lon', 'lng', 'latitude', 'longitude',
                  # Free text a caller typed (/v1/chat). Not a location, but the
                  # same promise: s2d does not cover it. Its len() is fine.
                  'question'}
SCRUBBERS = {'_log_district', '_log_coarse', 'len'}  # len(): a size is not the value


def _raw_location_names(node):
    """Location variable names in `node` that are NOT inside a scrubber call."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in SCRUBBERS:
        return set()
    if isinstance(node, ast.Name) and node.id in LOCATION_NAMES:
        return {node.id}
    found = set()
    for child in ast.iter_child_nodes(node):
        found |= _raw_location_names(child)
    return found


def _logger_calls(tree):
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and isinstance(n.func.value, ast.Name) and n.func.value.id == 'logger'):
            yield n


def _import(name):
    path = str(LAMBDAS / name)
    sys.path.insert(0, path)
    sys.modules.pop('app', None)
    try:
        import app  # noqa: F401, pylint: disable=import-outside-toplevel
        return app
    finally:
        sys.path.pop(0)


class LogPrivacyTests(unittest.TestCase):
    def test_no_logger_call_writes_a_raw_postcode_or_coordinate(self):
        offenders, calls = [], 0
        for app in sorted(LAMBDAS.glob('*/app.py')):
            tree = ast.parse(app.read_text(encoding='utf-8'))
            for call in _logger_calls(tree):
                calls += 1
                raw = set()
                for arg in call.args[1:]:
                    raw |= _raw_location_names(arg)
                if raw:
                    offenders.append(f'{app.parent.name}/app.py:{call.lineno} logs {sorted(raw)}')
        # Floor: a parse that finds no logger calls has broken, not passed.
        self.assertGreaterEqual(calls, 30, f'only {calls} logger calls found - the scan is not reading the Lambdas')
        self.assertEqual(offenders, [], 'wrap these in _log_district()/_log_coarse() (privacy.html s2d):\n'
                         + '\n'.join(offenders))

    def test_district_and_coarse_helpers_in_every_lambda_that_has_them(self):
        seen = 0
        for name in ('score', 'sold_prices', 'nhs'):
            app = _import(name)
            if hasattr(app, '_log_district'):
                seen += 1
                for full, district in (('SW11 1AA', 'SW11'), ('sw111aa', 'SW11'), ('M1 1AE', 'M1'),
                                       ('EC1A 1BB', 'EC1A'), ('', '?'), (None, '?'), ('ZZ', '?')):
                    self.assertEqual(app._log_district(full), district, f'{name}: {full!r}')
            if hasattr(app, '_log_coarse'):
                seen += 1
                self.assertEqual(app._log_coarse(51.46412, -0.16891), '51.46,-0.17', name)
                self.assertEqual(app._log_coarse('x', None), '?', name)
        # score has both, sold_prices one, nhs one.
        self.assertEqual(seen, 4)

    def test_a_degraded_lookup_logs_the_district_not_the_postcode(self):
        """Through the real code path, not the helper: the line users' data reaches."""
        from unittest.mock import patch
        app = _import('score')
        from urllib.error import URLError
        with patch.object(app, '_lookup_postcode_local', return_value=None), \
                patch.object(app, 'urlopen', side_effect=URLError('down')), \
                self.assertLogs(app.logger, level='WARNING') as cm:
            app.lookup_postcode('SW11 1AA')
        text = '\n'.join(r.getMessage() for r in cm.records)
        self.assertIn('SW11', text)
        self.assertNotIn('1AA', text)


if __name__ == '__main__':
    unittest.main()
