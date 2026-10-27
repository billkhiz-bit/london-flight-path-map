"""Every response the Lambdas build with a 5xx status says so in the logs.

WHY THIS EXISTS (2026-10-27). AWS emailed that the account had used 858 of its
1,000 free alert emails for October. They came from the api-5xx alarm: 1,229 of
113,067 API requests (1.1%) answered 5xx, yet the Lambdas recorded ONE error and
no [ERROR] line, because the handlers catch their failures and RETURN the 5xx
themselves (epc's 502/504 for an upstream failure, a caught exception's 500). API
Gateway counts them but cannot say which route (no access logs, no per-method
metrics), so nothing could say where they came from.

So every function that builds a response from a status it was GIVEN logs a
`[5XX] <status> ...` line when that status is 500 or more, and one Logs Insights
query (`filter @message like /\\[5XX\\]/ | stats count() by @log`) names the
source. Whatever API Gateway counts beyond those lines is the gateway's own
(throttled invocations, malformed responses).

The check is STRUCTURAL, as in test_security_headers.py: there are eight
Lambdas, each with its own builders, the shape this repo keeps finding drift in.
A builder whose status is a literal below 500 (the OPTIONS 204s) cannot answer
5xx and is left alone.
"""

import ast
import unittest
from pathlib import Path

LAMBDAS = Path(__file__).resolve().parent.parent / 'lambdas'
TAG = '[5XX]'
# The builders there were on 2026-10-27: a floor, so a parse that finds nothing cannot pass.
KNOWN = {
    ('chat', 'response'), ('epc', 'response'), ('favourites', 'response'), ('nhs', 'response'),
    ('score', 'response'), ('score', '_svg_response'), ('signup', 'response'), ('signup', 'html_page'),
    ('sold_prices', 'response'), ('transport', 'response'),
}


def _builds_given_status(fn):
    """True if `fn` builds a {'statusCode': x} dict whose x is not a literal below 500."""
    for n in ast.walk(fn):
        if isinstance(n, ast.Dict):
            for k, v in zip(n.keys, n.values, strict=True):
                if isinstance(k, ast.Constant) and k.value == 'statusCode':
                    if not (isinstance(v, ast.Constant) and isinstance(v.value, int) and v.value < 500):
                        return True
    return False


def _logs_5xx(fn):
    """True if `fn` has an `if <...> >= 500:` whose body calls logger.<level>('[5XX] ...')."""
    for n in ast.walk(fn):
        if not isinstance(n, ast.If):
            continue
        test = n.test
        guarded = (isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.GtE)
                   and isinstance(test.comparators[0], ast.Constant) and test.comparators[0].value == 500)
        if not guarded:
            continue
        for call in ast.walk(ast.Module(body=n.body, type_ignores=[])):
            if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and getattr(call.func.value, 'id', '') == 'logger' and call.args
                    and isinstance(call.args[0], ast.Constant) and str(call.args[0].value).startswith(TAG)):
                return True
    return False


def _builders():
    for app in sorted(LAMBDAS.glob('*/app.py')):
        tree = ast.parse(app.read_text(encoding='utf-8'))
        for fn in ast.walk(tree):
            if isinstance(fn, ast.FunctionDef) and _builds_given_status(fn):
                yield app.parent.name, fn


class FiveXXLoggedTests(unittest.TestCase):
    def test_every_lambda_was_parsed(self):
        self.assertGreaterEqual(len(list(LAMBDAS.glob('*/app.py'))), 8)

    def test_the_known_builders_are_all_found(self):
        found = {(lam, fn.name) for lam, fn in _builders()}
        self.assertEqual(KNOWN - found, set(), 'a builder this test was written against is no longer found')

    def test_every_builder_logs_its_5xx(self):
        missing = sorted(f'{lam}/app.py:{fn.lineno} {fn.name}()' for lam, fn in _builders() if not _logs_5xx(fn))
        self.assertEqual(missing, [], 'these build a response from a given status but never log a 5xx with '
                                      f'"{TAG}" behind `>= 500`')


if __name__ == '__main__':
    unittest.main()
