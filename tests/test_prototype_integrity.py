"""The /prototype/ page's modules from jsDelivr each carry a SHA-384 (audit 2026-10-16 M-9).

The page runs three.js from a third-party CDN on our own origin, where it could read the
favourites device token. Since 2026-10-16 its import map lists an integrity hash for every
module the page fetches (recorded by loading it), so a changed file at the CDN is refused.
This holds the map to the page: every module the page imports directly resolves to a URL
with a hash, every hash is SHA-384, and nothing else on the page loads from the CDN.
"""

import json
import os
import re
import unittest

PAGE = os.path.join(os.path.dirname(__file__), '..', 'prototype', 'index.html')


def importmap():
    src = open(PAGE, encoding='utf-8').read()
    m = re.search(r'<script type="importmap">\s*(\{.*?\})\s*</script>', src, re.S)
    if not m:
        raise AssertionError('no import map in prototype/index.html')
    return src, json.loads(m.group(1))


def resolve(spec, imports):
    if spec in imports:
        return imports[spec]
    prefix = max((k for k in imports if k.endswith('/') and spec.startswith(k)), key=len, default=None)
    return imports[prefix] + spec[len(prefix):] if prefix else spec


class PrototypeIntegrityTests(unittest.TestCase):
    def test_every_direct_import_has_a_sha384(self):
        src, imap = importmap()
        integrity = imap.get('integrity', {})
        self.assertTrue(integrity, 'the import map carries no integrity hashes')
        specs = re.findall(r"^\s*import .*? from '([^']+)';", src, re.M)
        self.assertGreaterEqual(len(specs), 6, f'expected the page\'s three.js imports, found {specs}')
        for spec in specs:
            url = resolve(spec, imap['imports'])
            with self.subTest(spec=spec):
                self.assertIn(url, integrity, f'{spec} -> {url} has no integrity hash')

    def test_every_hash_is_sha384_and_every_cdn_url_is_hashed(self):
        src, imap = importmap()
        for url, h in imap['integrity'].items():
            with self.subTest(url=url):
                self.assertRegex(h, r'^sha384-[A-Za-z0-9+/]{64}$')
        # No other script or style loads from the CDN outside the import map.
        outside = re.sub(r'<script type="importmap">.*?</script>', '', src, flags=re.S)
        self.assertNotRegex(outside, r'<(script|link)[^>]+cdn\.jsdelivr\.net')


if __name__ == '__main__':
    unittest.main()
