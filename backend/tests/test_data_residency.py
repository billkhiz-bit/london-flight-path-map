"""Every non-UK region a Lambda talks to must be disclosed in SUBPROCESSORS.md.

WHY THIS EXISTS. `POST /v1/chat` was restored on 2026-08-06 and calls AWS
Bedrock in `us-east-1`. For a month afterwards four published documents said
that could not be happening:

  SUBPROCESSORS.md  "no LLM provider receives any customer data"
  SUBPROCESSORS.md  "One outbound route leaves the UK ... intra-EEA transfer
                     rather than a third-country transfer, and no Article 46
                     safeguard is required"
  SECURITY.md       "All data processed in AWS eu-west-2 (London)"
  SECURITY.md       the Bedrock Lambdas "were removed entirely on 2026-05-07"

Every one of them was true when written. The restoration is what made them
false, and nothing connected the two - a code change in `backend/lambdas/` has
no reason to make anyone open a compliance document.

`SUBPROCESSORS.md` exists specifically to answer a B2B buyer's data-residency
question, and a buyer with a UK- or EEA-only requirement would have been given
the wrong answer in writing. That is the cost this file is guarding, not tidiness.

WHAT IT COMPARES. The regions come from the CODE - every AWS region literal in
`backend/lambdas/**/app.py` - and the disclosure comes from the DOCUMENT. Two
holders that can genuinely disagree, rather than an expectation read from the
thing it checks.
"""

import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
LAMBDAS = os.path.join(ROOT, 'backend', 'lambdas')

HOME_REGION = 'eu-west-2'
REGISTER = os.path.join(ROOT, 'SUBPROCESSORS.md')

# An AWS region code: two-or-three letter area, a compass word, a digit.
REGION_RE = re.compile(r"\b((?:af|ap|ca|eu|il|me|sa|us)-[a-z]+-\d)\b")


def _sources():
    for dirpath, _dirs, files in os.walk(LAMBDAS):
        for name in files:
            if name.endswith('.py'):
                path = os.path.join(dirpath, name)
                with open(path, encoding='utf-8') as fh:
                    yield os.path.relpath(path, ROOT), fh.read()


class DataResidencyTests(unittest.TestCase):

    def test_the_scan_actually_found_lambda_sources(self):
        """A scan that reads nothing must fail, not wave everything through."""
        found = list(_sources())
        self.assertGreaterEqual(
            len(found), 7,
            f'only {len(found)} Lambda source file(s) scanned - the layout '
            f'changed, so every check below is vacuous. Fix the walk, do not '
            f'delete it.')

    def test_every_non_uk_region_in_the_code_is_disclosed(self):
        with open(REGISTER, encoding='utf-8') as fh:
            register = fh.read()

        offenders = []
        regions_seen = set()
        for rel, src in _sources():
            for region in REGION_RE.findall(src):
                if region == HOME_REGION:
                    continue
                regions_seen.add(region)
                if region not in register:
                    offenders.append(f'{rel} talks to {region}, undisclosed')

        self.assertEqual(
            [], sorted(set(offenders)),
            'A Lambda sends data to a region SUBPROCESSORS.md does not mention. '
            'That document is what a B2B buyer reads to answer their own data-'
            'residency question, and an undisclosed transfer out of the UK is an '
            'Article 13 gap as well as a broken promise:\n  '
            + '\n  '.join(sorted(set(offenders))))

        # A NEGATIVE "the register must not still say X" CHECK WAS TRIED AND
        # REMOVED, and the reason is worth keeping.
        #
        # It asserted that the phrases "no LLM provider receives any customer
        # data" and "One outbound route leaves the UK" were absent. It went red
        # on the CORRECTED document - because the correction QUOTES the sentence
        # it is withdrawing, which is exactly what a good correction does. That
        # is the same trap as reading New York's "NOT HM Land Registry" as a
        # credit: a substring test cannot tell an assertion from an account of a
        # withdrawn assertion.
        #
        # The positive check above is the one that would have caught the real
        # defect anyway - `us-east-1` appeared in the code and nowhere in the
        # register for a month - and it cannot be tripped by prose ABOUT the
        # defect. Keep it that way.
        #
        # What the positive check still needs is that a disclosed region is
        # disclosed as a TRANSFER, not merely mentioned in passing.
        for region in sorted(regions_seen):
            idx = register.find(region)
            window = register[max(0, idx - 600):idx + 600].lower()
            self.assertIn(
                'transfer', window,
                f'SUBPROCESSORS.md mentions {region} but the surrounding text '
                f'never calls it a transfer. A region named in a table cell is '
                f'not a residency disclosure; §5 is where a buyer looks.')


class EnvironmentNoticeTests(unittest.TestCase):
    """`/v1/environment` must not assert coverage and deny it in one payload.

    Live defect, 2026-09-07 (audit I4). At TR1 1DT (Truro) the response carried:

        aircraftQuietBasis: "...outside every city Sky Score covers"
        notices[0]:         "...DEFRA publishes contours for part of this area"

    The notice was selected by `'postcode-nyc' if city == 'nyc' else 'postcode'`,
    which has no branch for `city is None` - eight lines after the code had
    already established that case and picked a different basis string for it.
    By the file's own measurement that is 68% of live UK postcodes, and it is
    the surface the public browser extension renders.

    Asserted as an INVARIANT over the payload rather than as a string match on
    one postcode: any response that denies coverage in one field and asserts it
    in another fails, wherever the coordinate is.
    """

    @staticmethod
    def _env(lat, lon):
        import json
        import sys
        sys.path.insert(0, os.path.join(ROOT, 'backend', 'lambdas', 'score'))
        import app as score_app
        resp = score_app.handle_environment(
            {'queryStringParameters': {'lat': str(lat), 'lon': str(lon)}}
        )
        return json.loads(resp['body'])

    def test_coverage_is_not_asserted_and_denied_in_one_payload(self):
        cases = [
            ('Truro, outside every covered city', 50.2632, -5.0510),
            ('central London, covered', 51.5074, -0.1278),
            ('Manchester, covered', 53.4808, -2.2426),
            ('Brooklyn, NYC', 40.6782, -73.9442),
        ]
        checked = 0
        for label, lat, lon in cases:
            body = self._env(lat, lon)
            basis = str((body.get('environment') or {}).get('aircraftQuietBasis') or '')
            notices = ' '.join(str(n) for n in (body.get('notices') or []))
            if not basis:
                continue
            checked += 1
            denies = 'outside every city' in basis
            asserts = 'DEFRA publishes contours' in notices
            self.assertFalse(
                denies and asserts,
                f'{label}: aircraftQuietBasis says this location is outside every '
                f'covered city, while notices claim DEFRA publishes contours for '
                f'it. One payload, two answers.\n  basis: {basis}\n  notices: '
                f'{notices[:200]}')
        self.assertGreaterEqual(
            checked, 3,
            f'only {checked} coordinate(s) produced a basis string, so this '
            f'invariant was barely exercised')


if __name__ == '__main__':
    unittest.main()
