"""The /badge edge cache is four holders that must agree, and none is a test.

Audit M1 (2026-09-14): every badge render was a Lambda invocation because
nothing between the viewer and the Lambda honoured its Cache-Control. Closed
2026-09-17 by a CloudFront behaviour on the site's own distribution
(`scripts/cloudfront_badge_behaviour.py`, applied and verified that day) and
then by repointing the two badge URLs in index.html at the site origin.

What can silently undo it, each caught here:

  - a badge URL drifting back to `${API_BASE}/badge` - correct output, no
    cache, one invocation per viewer again; the page has TWO badge URLs and
    the incident this repo records about scale direction is that two copies
    of one thing drift on the next edit, so both must read ONE holder;
  - the holder pointing anywhere but the distribution the behaviour is on -
    the script's SITE is the origin that was verified, so the page's
    BADGE_BASE is asserted against it, never against a literal here;
  - the site host missing from the CSP `img-src` - the page is also served
    from the cloudfront.net hostname and inside the native app, where the
    badge origin is NOT 'self', and a CSP block renders as a broken image;
  - the service worker caching /badge - same-origin paths are cache-first
    by default in sw.js, which would pin the first render in Cache Storage
    where Cache-Control cannot reach it (the borough-extra.json incident, on
    an image). The pass-through must sit BEFORE that default branch, and
    "present" is not "reached": a rule after `cacheFirst` is dead code.

The live half - that the behaviour exists and a second request HITs - is
`cloudfront_badge_behaviour.py --verify`; this file is the tree half.
"""

import os
import re

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), os.pardir))


def read(rel):
    with open(os.path.join(REPO_ROOT, rel), encoding='utf-8') as fh:
        return fh.read()


def script_constant(source, name):
    m = re.search(rf"^{name} = '([^']+)'$", source, re.M)
    assert m, f'{name} not found in cloudfront_badge_behaviour.py'
    return m.group(1)


def test_the_page_holds_the_badge_origin_once_and_it_is_the_verified_one():
    index = read('index.html')
    script = read(os.path.join('scripts', 'cloudfront_badge_behaviour.py'))
    expected = script_constant(script, 'SITE') + script_constant(script, 'PATH_PATTERN')
    holders = re.findall(r"const BADGE_BASE = '([^']+)';", index)
    assert holders == [expected], (
        f'BADGE_BASE is {holders}; the behaviour was applied and verified on {expected} '
        '(scripts/cloudfront_badge_behaviour.py SITE + PATH_PATTERN)'
    )


def test_both_badge_urls_read_the_holder_and_none_bypasses_the_cache():
    index = read('index.html')
    assert '${API_BASE}/badge' not in index, (
        'a badge URL points at API_BASE, which bypasses the CloudFront behaviour - '
        'every viewer becomes a Lambda invocation again (audit M1)'
    )
    uses = index.count('${BADGE_BASE}?postcode=')
    assert uses == 2, f'expected the embed snippet AND the preview to read BADGE_BASE; found {uses} use(s)'


def test_the_csp_allows_the_badge_origin_where_self_is_not_it():
    index = read('index.html')
    origin = re.match(r'https://[^/]+', re.search(r"const BADGE_BASE = '([^']+)';", index).group(1)).group(0)
    m = re.search(r"img-src ([^;]+);", index)
    assert m, 'no img-src directive in the CSP meta tag'
    assert origin in m.group(1).split(), (
        f"{origin} is not in img-src; 'self' covers it on skyscore.co.uk only, not on the cloudfront.net "
        'hostname or inside the native app'
    )


def test_the_service_worker_passes_badge_through_before_cache_first():
    sw = read('sw.js')
    start = sw.index("self.addEventListener('fetch'")
    handler = sw[start:]
    rule = re.search(r"url\.pathname === '/badge'\) return;", handler)
    assert rule, 'sw.js has no /badge pass-through; same-origin defaults to cacheFirst and would pin the badge'
    default = re.search(r'if \(url\.origin === self\.location\.origin\) \{\s*event\.respondWith\(cacheFirst\(req\)\)', handler)
    assert default, 'the same-origin cacheFirst branch moved; re-read the handler before trusting this test'
    assert rule.start() < default.start(), (
        'the /badge pass-through sits AFTER the same-origin cacheFirst branch, so it is never reached'
    )
