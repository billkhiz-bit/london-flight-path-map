"""The borough liveability inputs exist twice - keep them identical.

`data/borough-extra.json` is what the consumer site scores from, client-side.
`CITIES` in the score Lambda is what `/v1/score` scores from. Both carry
`crimeRate`, `schools`, `transport`, `healthcare` and (London only) `p8`, and
until this test nothing linked them. They agree today; nothing enforced it.

Audit finding I4 called this out as borough metadata having two holders and it
has stayed open, because de-duplicating properly means the site fetching its
inputs from the API - a bigger change than the risk warrants right now. This
test closes the RISK without the refactor: drift becomes a failed build rather
than two confident, different answers.

The risk is not hypothetical. Three separate site/API divergences have shipped
from one side of a duplicated calculation changing alone, and the liveability
redistribution on 2026-08-09 came within one commit of being a fourth - it was
caught by diffing all 38 boroughs by hand, which is not a control.

Deliberately checks the INPUTS rather than the scores. A scores comparison needs
a browser and is already covered by tests/site-api-parity.mjs against the
deployed pair; this runs offline in the blocking suite and catches the drift one
layer earlier, where it is cheaper to understand.
"""

import json
import os

import pytest

from .conftest import load_lambda

DATA = os.path.normpath(
    os.path.join(os.path.dirname(__file__), os.pardir, 'data', 'borough-extra.json')
)

score_app = load_lambda('score', 'score_app_borough_parity')

# The two holders do not agree on this borough's NAME, so any comparison has to
# say so out loud. `Barking` is the site's key; `Barking and Dagenham` is the
# Lambda's and is the borough's actual name. Declared rather than normalised by
# a fuzzy match, because a fuzzy match would also quietly pair up a genuinely
# missing borough with a similar one and report success.
NAME_ALIASES = {'Barking': 'Barking and Dagenham'}

# Fields both holders carry. `p8` is London-only: New York has neither Ofsted
# nor DfE, so its curated `schools` tier is its schools input.
SHARED_FIELDS = ('crimeRate', 'schools', 'transport', 'healthcare', 'p8')


def _extra():
    with open(DATA, encoding='utf-8') as handle:
        return json.load(handle)


def _pairs(city):
    """(borough, site_record, lambda_record) for every borough in both."""
    extra = _extra()[city]
    boroughs = score_app.CITIES[city]['boroughs']
    out = []
    for name, record in extra.items():
        canonical = NAME_ALIASES.get(name, name)
        if canonical in boroughs:
            out.append((canonical, record, boroughs[canonical]))
    return out


@pytest.mark.parametrize('city', ['london', 'nyc'])
def test_both_holders_cover_the_same_boroughs(city):
    """Coverage, not just agreement.

    A borough present in one holder and absent from the other is drift the
    field-by-field check below cannot see: it only compares what it can pair up,
    so a missing borough would silently reduce the comparison rather than fail
    it. This is the lesson from every previous list that decayed by omission.
    """
    extra = _extra()[city]
    boroughs = score_app.CITIES[city]['boroughs']
    site_names = {NAME_ALIASES.get(n, n) for n in extra}
    assert site_names == set(boroughs), (
        f'{city}: borough sets differ. '
        f'only in borough-extra.json={sorted(site_names - set(boroughs))}, '
        f'only in CITIES={sorted(set(boroughs) - site_names)}'
    )


@pytest.mark.parametrize('city', ['london', 'nyc'])
def test_shared_liveability_inputs_agree(city):
    """Every field both holders carry must hold the same value.

    These are the inputs to `live`, so a disagreement here is the site and the
    API publishing different liveability for the same place - each confident,
    neither flagged.
    """
    disagreements = []
    for name, site, lam in _pairs(city):
        for field in SHARED_FIELDS:
            if field in site and field in lam and site[field] != lam[field]:
                disagreements.append(f'{city}/{name}.{field}: site={site[field]!r} api={lam[field]!r}')
    assert not disagreements, 'borough inputs have drifted:\n  ' + '\n  '.join(disagreements)


@pytest.mark.parametrize('city', ['london', 'nyc'])
def test_a_field_is_not_silently_missing_from_one_side(city):
    """Presence must match too, not only value.

    `field in site and field in lam` above skips a field one side has dropped,
    so without this a deletion reads as agreement. Asserting per-borough rather
    than per-city because a single borough losing `p8` is exactly the City of
    London case, which is legitimate - so the comparison is against what the
    OTHER holder has, not against a fixed expectation.
    """
    mismatched = []
    for name, site, lam in _pairs(city):
        for field in SHARED_FIELDS:
            if (field in site) != (field in lam):
                holder = 'borough-extra.json' if field in site else 'CITIES'
                mismatched.append(f'{city}/{name}.{field}: present only in {holder}')
    assert not mismatched, 'a liveability input exists on one side only:\n  ' + '\n  '.join(mismatched)


def test_the_comparison_actually_compared_something():
    """Guard against the guard silently pairing up nothing.

    If a rename broke every pairing, all three tests above would pass over an
    empty set. This is the coverage assertion for the coverage assertions.
    """
    assert len(_pairs('london')) == 33
    assert len(_pairs('nyc')) == 5
