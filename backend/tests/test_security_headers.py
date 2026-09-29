"""Every Lambda response carries HSTS and nosniff.

An OWASP ZAP baseline scan on 2026-09-29 found the website sending both
headers (CloudFront's sky-score-security-headers policy) and the API sending
neither: API Gateway responses do not pass through that policy, so each Lambda
has to set them itself. There are EIGHT Lambdas, each building its own
response headers, which is exactly the shape this repo keeps finding drift in
(a fix landing in seven copies of eight).

So the check is STRUCTURAL: it parses every Lambda and finds each dict literal
that is a response's `headers` value, or that sets Access-Control-Allow-Origin
(the cors_headers() builders). Each must name both headers itself, or spread
(`**`) a call to a builder that does. A new Lambda, or a new response path in
an old one, fails here on the day it is written.
"""

import ast
import unittest
from pathlib import Path

LAMBDAS = Path(__file__).resolve().parent.parent / 'lambdas'
REQUIRED = {
    'Strict-Transport-Security': 'max-age=31536000',  # same value the site serves
    'X-Content-Type-Options': 'nosniff',
}


def _str_keys(d):
    return {k.value: v for k, v in zip(d.keys, d.values, strict=True) if isinstance(k, ast.Constant) and isinstance(k.value, str)}


def _spreads_builder(d):
    """True if the dict spreads `**cors_headers(...)` - the builder is checked on its own."""
    return any(k is None and isinstance(v, ast.Call) and getattr(v.func, 'id', '') == 'cors_headers'
               for k, v in zip(d.keys, d.values, strict=True))


def _header_dicts(tree):
    """(lineno, dict) for every response-headers dict and every CORS builder dict."""
    for n in ast.walk(tree):
        if isinstance(n, ast.Dict):
            keys = _str_keys(n)
            if 'Access-Control-Allow-Origin' in keys:
                yield n.lineno, n
            hv = keys.get('headers')
            if isinstance(hv, ast.Dict):
                yield hv.lineno, hv


class SecurityHeaderTests(unittest.TestCase):
    def test_every_lambda_was_parsed(self):
        # A path that matches nothing must not pass as "no violations".
        self.assertGreaterEqual(len(list(LAMBDAS.glob('*/app.py'))), 8)

    def test_every_response_sets_hsts_and_nosniff(self):
        missing = []
        seen = 0
        for app in sorted(LAMBDAS.glob('*/app.py')):
            tree = ast.parse(app.read_text(encoding='utf-8'))
            for line, d in _header_dicts(tree):
                seen += 1
                if _spreads_builder(d):
                    continue
                keys = _str_keys(d)
                for name, value in REQUIRED.items():
                    v = keys.get(name)
                    if not (isinstance(v, ast.Constant) and v.value == value):
                        missing.append(f'{app.parent.name}/app.py:{line} lacks {name}: {value}')
        self.assertGreaterEqual(seen, 10, 'found fewer header dicts than exist today - the walker, not the code, changed')
        self.assertEqual(missing, [], '\n'.join(missing))


if __name__ == '__main__':
    unittest.main()
