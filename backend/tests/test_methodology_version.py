"""Every surface that names a methodology version must name the engine's.

WHY THIS EXISTS (2026-09-11, audit C2). `METHODOLOGY_VERSION` is `'5.0'` and
every `/v1/score` response carries it, while five published surfaces disagreed
with the engine and with each other:

    index.html footer     "Methodology v3.7"
    METHODOLOGY.md :3     "Version 4.0, last updated 2026-08-29"
    METHODOLOGY.md s12    'the API response includes ... currently "4.0"'
    README.md :7          "Methodology v4.0 - API v1.0"
    LICENSING.md :133     'Footer link: "Methodology v3.1"'

METHODOLOGY.md is the document s16 names as the B2B contract reference and the
one the consumer footer links to, so an auditor landed on a page headed
"Version 4.0" describing an API that returns 5.0 - and the same document
printed `"methodologyVersion": "5.0"` in its own worked example, contradicting
its header. `sw.js` v1.0.9 records the footer being corrected for exactly this
once before (v3.4 against an API returning 3.5); nothing asserted it, so it
drifted again through v3.8, v3.9, v4.0 and v5.0.

THE ENGINE IS THE SOURCE. Nothing here hardcodes "5.0": the expectation is read
from `app.METHODOLOGY_VERSION`, so a version bump makes these fail until the
documents follow, which is the whole point. Same shape as
`test_the_published_residual_figure_does_not_understate_reality`, which already
reads two documents and fails on drift.

DELIBERATELY NOT A BLANKET SCAN. A regex for `v\\d+\\.\\d+` across the tree
would fire on every historical note ("corrected at v3.8", "before v4.0"), and a
gate that cries wolf gets switched off. Each entry below names a file and the
PATTERN that carries its current-state claim, so history stays readable.
"""

import os
import re
import sys
import unittest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lambdas', 'score'))
)

import app  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

# (file, regex capturing the version, human description of the surface).
# The regex must match EXACTLY ONCE - see test_every_pattern_matches_once.
SURFACES = (
    (
        'METHODOLOGY.md',
        r'^> Version (\d+\.\d+), last updated',
        'the document header, which is what an auditor reads first',
    ),
    (
        'METHODOLOGY.md',
        r'includes `methodologyVersion` \(currently `"(\d+\.\d+)"`\)',
        'METHODOLOGY s12, which quotes the field the API returns',
    ),
    (
        'README.md',
        r'^> Methodology v(\d+\.\d+) ',
        'the README badge line',
    ),
    (
        'index.html',
        r'Methodology v(\d+\.\d+)\s*$',
        'the consumer site footer link, which points AT METHODOLOGY.md',
    ),
)


def _read(rel):
    with open(os.path.join(REPO, rel), encoding='utf-8') as handle:
        return handle.read().replace('\r\n', '\n')


class MethodologyVersionTests(unittest.TestCase):
    def test_the_engine_declares_a_version_at_all(self):
        """A floor. Every assertion below is vacuous if this is empty."""
        self.assertRegex(
            app.METHODOLOGY_VERSION,
            r'^\d+\.\d+$',
            'METHODOLOGY_VERSION is not a version string, so the comparisons '
            'below are not comparing anything',
        )

    def test_every_pattern_matches_once(self):
        """The patterns are the gate; a pattern that stops matching is silent.

        A `findall` returning [] makes the version check below pass by vacuity -
        the `FAIL_MODERATE` shape this repo has already paid for, where the
        rule was right and never ran. Asserted separately from the values so a
        reworded document fails as a BROKEN GATE rather than as agreement.
        """
        for rel, pattern, what in SURFACES:
            with self.subTest(surface=what):
                found = re.findall(pattern, _read(rel), re.M)
                self.assertEqual(
                    1,
                    len(found),
                    f'{rel}: the pattern for {what} matched {len(found)} times, '
                    f'not once. If the wording changed, update the pattern - do '
                    f'not let it match nothing, because that is a pass.',
                )

    def test_every_published_version_matches_the_engine(self):
        want = app.METHODOLOGY_VERSION
        wrong = []
        for rel, pattern, what in SURFACES:
            found = re.findall(pattern, _read(rel), re.M)
            if len(found) != 1:
                continue  # reported by the test above; not double-counted here
            if found[0] != want:
                wrong.append(f'{rel} ({what}) says {found[0]}')
        self.assertEqual(
            [],
            wrong,
            f'the engine returns methodologyVersion {want} and these disagree: '
            + '; '.join(wrong),
        )


if __name__ == '__main__':
    unittest.main()
