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


def test_every_redirect_target_is_a_key_the_makefile_uploads():
    makefile = (REPO_ROOT / 'Makefile').read_text(encoding='utf-8')
    for new in moved(installer.FUNCTION_CODE).values():
        key = f's3://$(S3_BUCKET){new}/index.html'
        assert key in makefile, f'{new} is a redirect target and no Makefile target uploads {key}'
