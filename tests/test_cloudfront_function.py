"""The CloudFront viewer-request function, run in Node exactly as written (audit I15, 2026-10-07).

`scripts/install_cloudfront_index_rewrite.py` holds the function's source as a string and
publishes it to the live distribution, so nothing else ever executes it before a visitor does.
This runs that string in Node (CloudFront Functions are JavaScript; the subset used here is
plain ES5 plus String.prototype.endsWith) and checks three things:

  - the index rewrite still serves extensionless paths and directories from <path>/index.html,
    and leaves real .html keys (/score-demo/api-docs.html, /404.html) alone
  - each old .html name answers 301 to its page, and the target does not redirect again
  - every redirect target is a key the Makefile uploads, because a 301 to a key nobody
    deploys sends a visitor to the not-found page with extra steps

    python -m pytest tests/test_cloudfront_function.py
"""

import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    'install_cloudfront_index_rewrite', REPO_ROOT / 'scripts' / 'install_cloudfront_index_rewrite.py'
)
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)

NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(NODE is None, reason='node is not on PATH')


def run(uris, tmp_path):
    """The function's result for each URI: the rewritten URI, or the redirect it returns."""
    harness = tmp_path / 'fn.js'
    harness.write_text(
        installer.FUNCTION_CODE
        + '\nconst uris = JSON.parse(process.argv[2]);\n'
        + 'console.log(JSON.stringify(uris.map((u) => handler({ request: { uri: u } }))));\n',
        encoding='utf-8',
    )
    # Node on PATH, our own harness file and JSON we built: fixed, not untrusted, input.
    out = subprocess.run(  # noqa: S603
        [NODE, str(harness), json.dumps(uris)], capture_output=True, text=True, check=True
    )
    return dict(zip(uris, json.loads(out.stdout), strict=True))


def moved(js):
    """The redirect map, read out of the function source rather than copied here."""
    block = re.search(r'var MOVED = \{(.*?)\};', js, re.S)
    assert block, 'no MOVED map in the function source'
    pairs = dict(re.findall(r"'(/[^']+)':\s*'(/[^']+)'", block.group(1)))
    assert pairs, 'the MOVED map parsed empty'
    return pairs


def test_the_index_rewrite_is_unchanged(tmp_path):
    got = run(['/', '/pricing', '/area/london/camden/', '/map/', '/score-demo/api-docs.html', '/404.html'], tmp_path)
    assert got['/']['uri'] == '/index.html'
    assert got['/pricing']['uri'] == '/pricing/index.html'
    assert got['/area/london/camden/']['uri'] == '/area/london/camden/index.html'
    assert got['/map/']['uri'] == '/map/index.html'
    # Real .html keys pass through untouched.
    assert got['/score-demo/api-docs.html']['uri'] == '/score-demo/api-docs.html'
    assert got['/404.html']['uri'] == '/404.html'


def test_each_old_html_name_redirects_once_to_its_page(tmp_path):
    pairs = moved(installer.FUNCTION_CODE)
    assert set(pairs) == {'/privacy.html', '/terms.html', '/pricing.html', '/changes.html'}
    got = run(list(pairs) + list(pairs.values()), tmp_path)
    for old, new in pairs.items():
        assert got[old]['statusCode'] == 301, old
        assert got[old]['headers']['location']['value'] == new
        # The target is served, not redirected again.
        assert got[new].get('statusCode') is None, f'{new} redirects again'
        assert got[new]['uri'] == f'{new}/index.html'


def handle(requests, tmp_path):
    """The function's result for each whole request object (host header and query string included)."""
    harness = tmp_path / 'fn-requests.js'
    harness.write_text(
        installer.FUNCTION_CODE
        + '\nconst reqs = JSON.parse(process.argv[2]);\n'
        + 'console.log(JSON.stringify(reqs.map((r) => handler({ request: r }))));\n',
        encoding='utf-8',
    )
    out = subprocess.run(  # noqa: S603 - Node on PATH, our own harness and JSON we built
        [NODE, str(harness), json.dumps(requests)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


def www(uri, querystring=None):
    return {'uri': uri, 'headers': {'host': {'value': 'www.skyscore.co.uk'}}, 'querystring': querystring or {}}


def test_www_goes_to_the_bare_name_with_its_path_and_query(tmp_path):
    # 2026-11-09: www served 200 copies of every page, which Search Console listed as alternates.
    got = handle([
        www('/'),
        www('/area/london/camden/'),
        www('/map/', {'city': {'value': 'london'}, 'borough': {'value': 'Ealing'}}),
        www('/', {'postcode': {'value': 'SW11%201AA'}}),
        www('/x', {'a': {'value': '1', 'multiValue': [{'value': '1'}, {'value': '2'}]}, 'flag': {'value': ''}}),
    ], tmp_path)
    locations = [r['headers']['location']['value'] for r in got]
    assert all(r['statusCode'] == 301 for r in got)
    assert locations == [
        'https://skyscore.co.uk/',
        'https://skyscore.co.uk/area/london/camden/',
        'https://skyscore.co.uk/map/?city=london&borough=Ealing',
        'https://skyscore.co.uk/?postcode=SW11%201AA',
        'https://skyscore.co.uk/x?a=1&a=2&flag',
    ]


def test_www_and_an_old_name_is_one_hop(tmp_path):
    got = handle([www('/privacy.html')], tmp_path)[0]
    assert got['headers']['location']['value'] == 'https://skyscore.co.uk/privacy'


def test_the_bare_name_is_never_redirected_for_its_host(tmp_path):
    bare = {'uri': '/pricing', 'headers': {'host': {'value': 'skyscore.co.uk'}}, 'querystring': {}}
    cloudfront = {'uri': '/map/', 'headers': {'host': {'value': 'd1oe4ftwutjpf.cloudfront.net'}}, 'querystring': {}}
    got = handle([bare, cloudfront], tmp_path)
    assert got[0].get('statusCode') is None and got[0]['uri'] == '/pricing/index.html'
    assert got[1].get('statusCode') is None and got[1]['uri'] == '/map/index.html'


def test_the_comment_fits_cloudfronts_limit():
    assert len(installer.FUNCTION_COMMENT) <= 64, len(installer.FUNCTION_COMMENT)


def test_every_redirect_target_is_a_key_the_makefile_uploads():
    makefile = (REPO_ROOT / 'Makefile').read_text(encoding='utf-8')
    for new in moved(installer.FUNCTION_CODE).values():
        key = f's3://$(S3_BUCKET){new}/index.html'
        assert key in makefile, f'{new} is a redirect target and no Makefile target uploads {key}'
