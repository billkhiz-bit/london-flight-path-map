"""The aircraft-quiet files, the page and the Lambda must agree on the RAMP.

`data/aircraft-quiet-london.json` and `data/aircraft-quiet-regions.json` ship
the COMPUTED quiet score for every postcode DEFRA measured, so index.html never
reimplements `lden_db_to_quiet`. The cost is that the files go stale when the
ramp changes, and nothing but this test says so before deploy: index.html
refuses a file whose ramp fingerprint it does not expect, which is a runtime
safety net that silently returns ~42,000 measured postcodes to geometry.

Audit M25 (13 Sep 2026): the key was `methodologyVersion`, held at '3.6' in
the builder and the page against a Lambda at '5.0', under comments claiming
each "must match" - and no test compared the builder's mirrored ramp to the
Lambda's. The key is now a fingerprint DERIVED from the Lambda's ramp, the
builder calls the Lambda's function rather than mirroring it, and this file
asserts every holder against the Lambda and never against each other, because
two equally stale mirrors agree.

Offline: reads the repo and imports the Lambda from source.
"""

import json
import os
import re

import pytest

from .conftest import load_lambda, load_script

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), os.pardir))
INDEX_HTML = os.path.join(REPO_ROOT, 'index.html')
DATA_FILES = [
    os.path.join(REPO_ROOT, 'data', 'aircraft-quiet-london.json'),
    os.path.join(REPO_ROOT, 'data', 'aircraft-quiet-regions.json'),
]

score_app = load_lambda('score', 'score_app_quiet_dataset')
builder = load_script('build_aircraft_quiet_dataset')


def _expected():
    return builder.ramp_identity(score_app)


def _page_fingerprint():
    with open(INDEX_HTML, encoding='utf-8') as fh:
        source = fh.read()
    match = re.search(r"const AIRCRAFT_QUIET_RAMP_FINGERPRINT = '([0-9a-f]{16})';", source)
    assert match, 'could not locate AIRCRAFT_QUIET_RAMP_FINGERPRINT in index.html'
    return match.group(1)


def test_fingerprint_moves_when_the_ramp_does():
    """The guard is only a guard if a ramp change changes the key.

    A version string has to be remembered; the fingerprint is derived. Prove
    it: perturb each anchor and the rounding on a stand-in module and assert
    a different hash every time, then that the real one is stable.
    """
    baseline = _expected()['fingerprint']

    class Ramp:
        def __init__(self, ceiling, floor, decimals=1):
            self._QUIET_CEILING_DB = ceiling
            self._QUIET_FLOOR_DB = floor
            self.decimals = decimals

        def lden_db_to_quiet(self, lden):
            if lden <= self._QUIET_CEILING_DB:
                return 10.0
            if lden >= self._QUIET_FLOOR_DB:
                return 0.0
            span = self._QUIET_FLOOR_DB - self._QUIET_CEILING_DB
            return round(10.0 * (self._QUIET_FLOOR_DB - lden) / span, self.decimals)

    ceiling, floor = score_app._QUIET_CEILING_DB, score_app._QUIET_FLOOR_DB
    same = builder.ramp_identity(Ramp(ceiling, floor))['fingerprint']
    assert same == baseline, (
        "a stand-in with the Lambda's anchors must reproduce its fingerprint - if it does "
        "not, lden_db_to_quiet's SHAPE changed and this stand-in no longer models it"
    )

    seen = {baseline}
    for variant in (
        Ramp(ceiling - 1.0, floor),
        Ramp(ceiling, floor + 2.0),
        Ramp(ceiling, floor, decimals=2),
    ):
        fp = builder.ramp_identity(variant)['fingerprint']
        assert fp not in seen, f'{vars(variant)} produced a fingerprint already seen'
        seen.add(fp)


def test_page_expects_the_lambdas_ramp():
    want = _expected()['fingerprint']
    got = _page_fingerprint()
    assert got == want, (
        f"index.html expects ramp fingerprint {got!r} but the Lambda's ramp is {want!r}. "
        'If lden_db_to_quiet changed: regenerate both data files with '
        'scripts/build_aircraft_quiet_dataset.py (and --regions), then set '
        f"AIRCRAFT_QUIET_RAMP_FINGERPRINT = '{want}' in index.html."
    )


@pytest.mark.parametrize('path', DATA_FILES, ids=os.path.basename)
def test_shipped_file_was_built_under_the_lambdas_ramp(path):
    with open(path, encoding='utf-8') as fh:
        payload = json.load(fh)
    want = _expected()
    got = payload.get('ramp')
    assert got == want, (
        f"{os.path.basename(path)} carries ramp {got!r}; the Lambda's is {want!r}. "
        'Regenerate with scripts/build_aircraft_quiet_dataset.py'
        + (' --regions' if path.endswith('regions.json') else '')
        + ' - a stale file is refused by index.html at runtime and every measured '
        'postcode silently falls back to geometry.'
    )
    assert 'methodologyVersion' not in payload, (
        'methodologyVersion was the wrong key (audit M25) and is not written any more'
    )


@pytest.mark.parametrize('path', DATA_FILES, ids=os.path.basename)
def test_shipped_file_holds_ramp_outputs_only(path):
    """Every value must be one the ramp can produce.

    The ramp rounds to 1 dp on a 0-10 scale, so 101 distinct values are
    possible. A file holding anything else was not built by this ramp, whatever
    its header says. Cheap, and it is the only assertion that looks at the
    numbers rather than the label on them.
    """
    with open(path, encoding='utf-8') as fh:
        payload = json.load(fh)
    grid = builder.FINGERPRINT_GRID_TENTHS
    producible = {score_app.lden_db_to_quiet(t / 10) for t in grid}
    values = set(payload['quiet'].values())
    stray = sorted(values - producible)
    assert not stray, f'{os.path.basename(path)} holds values the ramp cannot produce: {stray[:10]}'
    assert payload['count'] == len(payload['quiet'])
