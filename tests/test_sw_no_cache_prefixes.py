"""Every key the Makefile uploads `no-cache` must not be served cache-first by sw.js.

A `--cache-control "no-cache"` on an upload is a statement that a stale copy of
that file is wrong, not merely old: borough-extra.json carries every borough's
inputs, js/api-base.js the API host, js/home-engine.mjs the engine of the
page under trial. But that header governs the browser's HTTP cache only.
sw.js's fetch handler answers same-origin requests from Cache Storage FIRST
unless a rule says otherwise, and Cache Storage never reads Cache-Control - so
a no-cache upload under the cache-first default is pinned for the life of the
worker. That is how borough-extra.json served pre-correction crime figures for
days (fixed for /data/ in v1.0.34), why /js/ is network-first, why /badge is
not intercepted at all, and what preview/ and open-data/ were about to do on
2026-10-03 before the handler was re-read.

Three of those were fixed one prefix at a time, after the fact. This derives
the list from the Makefile - the one holder of what is uploaded how - and
holds sw.js to it, so the NEXT no-cache surface is caught the day its deploy
target is written, not the day its stale copy is noticed on a phone.

The rule, per key prefix:
  - HTML keys are navigations, which the handler serves network-first before
    any path rule: exempt.
  - every other no-cache key's first path segment must appear in a
    network-first rule (`startsWith('/<prefix>/')` feeding networkFirstAsset)
    or a pass-through (`=== '/<path>'`) that sits BEFORE the same-origin
    cacheFirst default.
"""

import os
import re

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), os.pardir))


def read(rel):
    with open(os.path.join(REPO_ROOT, rel), encoding='utf-8') as fh:
        return fh.read()


def no_cache_keys():
    """S3 keys the Makefile uploads with no-cache, one per `aws s3 cp|sync` command."""
    text = read('Makefile').replace('\\\r\n', ' ').replace('\\\n', ' ')
    keys = []
    for line in text.splitlines():
        if 'aws s3' not in line or '--cache-control "no-cache"' not in line:
            continue
        m = re.search(r's3://\$\(S3_BUCKET\)/([^\s]*)', line)
        assert m, f'no-cache upload with no bucket key on its line: {line.strip()[:120]}'
        key = m.group(1)
        # A sync with --include "*.ext" uploads that extension under the prefix.
        inc = re.findall(r'--include "\*\.(\w+)"', line)
        if inc:
            keys.extend(f'{key}*.{ext}' for ext in inc)
        else:
            keys.append(key)
    return keys


def fetch_handler():
    sw = read('sw.js')
    start = sw.index("self.addEventListener('fetch'")
    handler = sw[start:]
    default = re.search(r'if \(url\.origin === self\.location\.origin\) \{\s*event\.respondWith\(cacheFirst\(req\)\)', handler)
    assert default, 'the same-origin cacheFirst branch moved; re-read the handler before trusting this test'
    return handler, handler[: default.start()]


def test_the_makefile_still_marks_things_no_cache():
    keys = no_cache_keys()
    assert len(keys) >= 6, f'only {len(keys)} no-cache upload(s) parsed from the Makefile: {keys}'
    assert any(k.startswith('data/') for k in keys), 'data/ lost its no-cache upload; the parse or the Makefile changed'


def test_every_non_html_no_cache_key_is_network_first_in_the_service_worker():
    _, before_default = fetch_handler()
    prefixes_nf = set(re.findall(r"url\.pathname\.startsWith\('/([^/']+)/'\)", before_default))
    # An exact path counts whether it is passed through (`) return;`, /badge) or
    # routed network-first (openapi.yaml); the rule below checks the latter kind.
    exact = set(re.findall(r"url\.pathname === '/([^']+)'", before_default))
    bad = []
    for key in no_cache_keys():
        if key.endswith('.html') or key.endswith('*.html'):
            continue  # a navigation: network-first by the first rule in the handler
        first = key.split('/')[0]
        if first in prefixes_nf or key in exact:
            continue
        bad.append(key)
    assert not bad, (
        'uploaded no-cache but served cache-first by sw.js (Cache Storage ignores the header, so these pin '
        f'for the life of the worker): {sorted(bad)}. Add a networkFirstAsset rule for the prefix, before the '
        'same-origin cacheFirst default, and bump VERSION.'
    )


def test_the_network_first_rules_feed_network_first():
    """A prefix in a startsWith() rule only counts if that branch is network-first, not cacheFirst."""
    _, before_default = fetch_handler()
    for m in re.finditer(r"url\.pathname\.startsWith\('/([^/']+)/'\)[^{]*\{([^}]*)\}", before_default, re.S):
        assert 'networkFirst' in m.group(2), f"the /{m.group(1)}/ rule does not call a networkFirst handler: {m.group(2).strip()[:80]}"


def test_preview_and_open_data_are_named_since_v1_0_36():
    """The two that prompted this file; proven red against the v1.0.35 handler."""
    _, before_default = fetch_handler()
    for prefix in ('preview', 'open-data'):
        assert f"startsWith('/{prefix}/')" in before_default, f'/{prefix}/ is not network-first in sw.js'
    # Found by the derived test's first run: the spec the Swagger page reads was
    # uploaded no-cache since 2026-08 and served cache-first all along.
    assert "url.pathname === '/score-demo/openapi.yaml'" in before_default, 'openapi.yaml is not network-first in sw.js'
