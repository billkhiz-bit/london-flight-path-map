"""The planes overhead counts are OFFERED under the ODbL, because they are built from adsb.lol's ODbL tracks.

Bill accepted the share-alike on 2026-10-15 and the counts went live on 2026-10-27 with the offer "a few weeks" behind;
on 2026-11-25 it was still not built, and nothing could see that (LICENSING.md said so in prose). These hold the offer
to its source: while data/planes/airports.json names the ODbL, /open-data/ must link the download with the licence and
the credit, open-data-deploy must build and upload it, git must never carry it, and the zip must read back as exactly
the figures in data/planes/ (scripts/build_planes_open_data.py).
"""
import importlib.util
import io
import json
import re
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
spec = importlib.util.spec_from_file_location('build_planes_open_data', REPO / 'scripts' / 'build_planes_open_data.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

# data/planes/ is gitignored (the counts are built locally from the tracks), so a fresh checkout, CI's included, has
# none. Reading it at import stopped pytest's collection of the whole root suite, so CI ran NONE of its root tests from
# cdf70f9f (26 Nov) until this guard (27 Nov), the third such outage (ci.yml records 31 Aug and 3-19 Nov). The checks
# that need the files skip without them, saying why; the page, Makefile and git checks below run everywhere.
AIRPORTS = REPO / 'data' / 'planes' / 'airports.json'
HAVE_PLANES = AIRPORTS.exists()
NO_PLANES = 'data/planes/ is gitignored and absent here (a fresh checkout, as in CI): these run in local preflight'
META = json.loads(AIRPORTS.read_text(encoding='utf-8')) if HAVE_PLANES else None
PAGE = (REPO / 'open-data' / 'index.html').read_text(encoding='utf-8')
ZIP = builder.OUT.name


def recipe(target):
    text = (REPO / 'Makefile').read_text(encoding='utf-8').replace('\r\n', '\n')
    found = re.search(rf'^{re.escape(target)}:.*?\n((?:\t.*\n|#.*\n|\n)*)', text, re.M)
    assert found, f'no {target} target'
    return found.group(1)


class OfferTests(unittest.TestCase):
    @unittest.skipUnless(HAVE_PLANES, NO_PLANES)
    def test_the_source_is_odbl(self):
        # If this ever stops being true, the offer below is no longer owed: change these tests with the licence.
        self.assertIn('ODbL', META['licence'])

    def test_open_data_links_the_download_with_its_licence_and_credit(self):
        self.assertIn(f'href="/open-data/{ZIP}"', PAGE)
        self.assertIn('Open Database License (ODbL) 1.0', PAGE)
        self.assertIn('aircraft positions via adsb.lol (ODbL)', PAGE)
        self.assertIn('id="planes"', PAGE)

    def test_open_data_deploy_builds_then_uploads_the_zip(self):
        r = recipe('open-data-deploy')
        build = r.find('build_planes_open_data.py --write')
        upload = r.find(f'open-data/{ZIP}')
        self.assertGreaterEqual(build, 0, 'open-data-deploy never builds the zip')
        self.assertGreater(upload, build, 'the zip is uploaded before it is built')
        self.assertIn('application/zip', r[upload:])

    def test_git_never_carries_the_zip(self):
        tracked = subprocess.run(['git', 'ls-files', 'open-data'], cwd=REPO, capture_output=True, text=True,  # noqa: S603, S607  (git, fixed arguments)
                                 check=True).stdout
        self.assertNotIn('.zip', tracked)
        ignored = subprocess.run(['git', 'check-ignore', '-q', f'open-data/{ZIP}'], cwd=REPO, check=False)  # noqa: S603, S607  (git, fixed arguments)
        self.assertEqual(ignored.returncode, 0, f'open-data/{ZIP} is not ignored by git')


@unittest.skipUnless(HAVE_PLANES, NO_PLANES)
class ZipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob = builder.build()

    def test_deterministic(self):
        self.assertEqual(builder.build(), self.blob, 'two builds from the same files differ')

    def test_reads_back_as_data_planes(self):
        self.assertEqual(builder.round_trip(self.blob), [])

    def test_readme_says_what_the_source_says(self):
        readme = zipfile.ZipFile(io.BytesIO(self.blob)).read(builder.README_NAME).decode('utf-8')
        for key in ('definition', 'direction_rule', 'postcodes_rule'):
            self.assertIn(META[key], readme, f'the README does not carry airports.json {key} word for word')
        for credit in META['credits']:
            self.assertIn(credit, readme)
        self.assertIn('Open Database License (ODbL) 1.0', readme)
        self.assertIn('aircraft positions via adsb.lol (ODbL)', readme)


if __name__ == '__main__':
    unittest.main()
