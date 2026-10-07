"""Every page that loads GoatCounter loads the PINNED script, with its integrity hash (2026-10-07).

GoatCounter's analytics script was loaded from https://gc.zgo.at/count.js on eleven pages
with no Subresource Integrity. That URL serves whatever GoatCounter publishes next (measured
7 Oct: count.js was 9,213 bytes, a different build from the versioned count.v5.js), so it
cannot carry a fixed hash, and a compromise of that host would run in every page's origin.

GoatCounter publishes versioned, immutable scripts for exactly this ("the versioned script
will always remain the same"). count.v5.js is the latest; its sha384 was COMPUTED from the
served file and matched the hash GoatCounter documents, and gc.zgo.at answers it with
Access-Control-Allow-Origin: * and a year's cache, which SRI on a cross-origin script needs.

The tag now lives on eleven pages and in scripts/build_bay_area_page.py. Nothing else keeps
them in step, so this does: every deployed HTML page that mentions gc.zgo.at must carry
exactly PINNED, and none may load the unversioned count.js. Upgrading means changing
PINNED here and on every page together, after recomputing the hash from the served file:

    curl -s https://gc.zgo.at/count.vN.js | openssl dgst -sha384 -binary | openssl base64 -A

    python -m pytest tests/test_goatcounter_pinned.py
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PINNED = (
    '<script data-goatcounter="https://cubitt33.goatcounter.com/count" async src="https://gc.zgo.at/count.v5.js" '
    'crossorigin="anonymous" integrity="sha384-atnOLvQb9t+jTSipvd75X2yginT4PjVbqDdlJAmxMm+wYElFmeR6EmLP5bYeoRVQ">'
)
# Not deployed, or copies another build makes: design prototypes, archives, the native
# app's generated assets, agent worktrees, dependencies and test fixtures.
SKIP = {'node_modules', 'archive', 'mobile', '.claude', 'design', 'tests', '.git'}


def pages():
    for path in REPO.rglob('*.html'):
        if SKIP.isdisjoint(path.relative_to(REPO).parts):
            yield path


def goatcounter_tags():
    found = {}
    for path in pages():
        text = path.read_text(encoding='utf-8')
        if 'gc.zgo.at' in text:
            found[path.relative_to(REPO).as_posix()] = re.findall(r'<script\b[^>]*gc\.zgo\.at[^>]*>', text)
    return found


def test_the_scan_reaches_the_pages_that_count():
    found = goatcounter_tags()
    # A walk that finds nothing would pass the checks below vacuously.
    assert len(found) >= 10, sorted(found)
    for page in ('index.html', 'home/index.html', 'pricing.html', 'bay-area/index.html'):
        assert page in found, f'{page} no longer loads GoatCounter, or the scan cannot see it'


def test_every_goatcounter_tag_is_the_pinned_one():
    wrong = {page: tags for page, tags in goatcounter_tags().items() if tags != [PINNED]}
    assert not wrong, f'pages whose GoatCounter tag is not exactly the pinned one: {wrong}'


def test_no_page_loads_the_unversioned_script():
    for path in pages():
        assert 'gc.zgo.at/count.js' not in path.read_text(encoding='utf-8'), path.relative_to(REPO).as_posix()


def test_the_bay_area_generator_writes_the_pinned_tag():
    # bay-area/index.html is generated: a hand fix to the page would be undone by --write.
    assert PINNED in (REPO / 'scripts' / 'build_bay_area_page.py').read_text(encoding='utf-8')
