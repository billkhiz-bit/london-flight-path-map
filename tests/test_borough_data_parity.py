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
#
# The two ratios joined on 2026-08-26 with methodology v3.9, when air quality
# and flood stopped being display-only and became the `environment` component.
# The CONTINUOUS fields are the scored ones and therefore the ones that must
# agree; the three-band summaries beside them still live only in
# borough-extra.json, because they are still only drawn.
#
# Neither is universal, and that is expected rather than drift: New York has
# neither (DEFRA and the EA are UK sources) and Leicester and Teesside have the
# ratio but no flood coverage. What this file checks is that the two holders
# agree about WHICH boroughs have them - see
# test_a_field_is_not_silently_missing_from_one_side, which is the assertion
# that a propagation gap fails rather than passes quietly.
SHARED_FIELDS = (
    'crimeRate',
    'schools',
    'transport',
    'healthcare',
    'p8',
    'airQualityWhoRatio',
    'floodMediumOrHighPct',
)

# Cities the score Lambda serves that the consumer site does NOT, so they have
# one holder and nothing to compare. Declared explicitly rather than inferred,
# because the difference between "backend-only on purpose" and "someone put a
# city on the site and forgot its data" is exactly what this file exists to
# catch, and inferring it would make the second case look like the first.
#
# TWO entries. Six Core Cities regions passed through here on 2026-08-10 and
# left the same day, once Progress 8 gave them a second liveability input and
# they went on the site - which is exactly the shape an entry here should have.
#
# It earned its place first: a preview branch put Greater Manchester on the site
# with no borough-extra entry and ALL TEN boroughs disagreed with the API by up
# to 1.5 points, because the site could not see p8 or crimeRate and dropped
# `live` entirely. The map looked correct throughout.
BACKEND_ONLY_CITIES = frozenset({
    # Cardiff and Nottingham STAY, and cannot leave on current data. Progress 8
    # is an ENGLAND measure so Cardiff has none at all, and Nottingham gets 1 of
    # 4 because Broxtowe, Gedling and Rushcliffe are districts inside
    # Nottinghamshire rather than local authorities - ONS crime has the same gap.
    # The other six left on 2026-08-10 when p8 landed and they went on the site.
    'cardiff',
    'nottingham',
    # Leicester and Teesside LEFT on 2026-08-11, once the site half was built
    # and all 13 boroughs were output-compared site-vs-Lambda. They were never
    # here for data reasons: Teesside publishes Progress 8 for all five
    # unitaries, and Leicester's districts hold 3 of 4 measured liveability
    # inputs, well clear of the two-input floor.
})

# Corrected 2026-08-11: Nottingham's outer districts hold TWO measured inputs,
# not one. The comment above said "1 of 4" and that was true until healthcare
# landed in v3.7 - Broxtowe, Gedling and Rushcliffe gained transport in v3.6 and
# healthcare in v3.7, so they now clear the floor and publish a liveability
# score. Nottingham is therefore promotable on the floor, and stays here on
# JUDGEMENT rather than on impossibility: `live` of 2.6 on two inputs is thin
# enough that the site would be claiming more than it knows. Cardiff genuinely
# cannot leave - Progress 8 is an England measure and Wales has none.


def _site_cities():
    with open(DATA, encoding='utf-8') as handle:
        return set(json.load(handle))


# Cities held by BOTH surfaces, so there is something to compare. Derived, not
# listed: the three tests below were parametrised over a hardcoded
# ['london', 'nyc'] and silently kept comparing two cities after a third was
# added to both holders — the same decay these tests exist to catch, in the file
# that catches it. test_comparison_covers_every_shared_city guards the
# derivation itself, because parametrising over an empty list SKIPS rather than
# fails.
COMPARED_CITIES = sorted(set(score_app.CITIES) & _site_cities())


def test_comparison_covers_every_shared_city():
    """The derived list must cover every city both holders carry.

    Without this, a rename or a load failure would shrink COMPARED_CITIES and
    the parametrised tests below would quietly pass over fewer cities, or none.
    """
    assert COMPARED_CITIES == sorted(set(score_app.CITIES) & _site_cities())
    assert len(COMPARED_CITIES) >= 2, 'comparison collapsed to fewer than two cities'


def test_backend_only_cities_are_declared_not_discovered():
    """Every city the Lambda scores is either on the site or declared here.

    Fails in BOTH directions, which is the point: a new city that reaches the
    site without borough-extra data fails, and a city that gains borough-extra
    data while still listed as backend-only also fails, so it starts being
    compared instead of staying exempt.
    """
    lambda_cities = set(score_app.CITIES)
    site_cities = _site_cities()

    undeclared = lambda_cities - site_cities - BACKEND_ONLY_CITIES
    assert not undeclared, (
        'city scored by the Lambda with no borough-extra.json data and not '
        f'declared backend-only: {sorted(undeclared)}. The site cannot '
        'reproduce its liveability, so the two will disagree on every borough.'
    )

    no_longer_exempt = BACKEND_ONLY_CITIES & site_cities
    assert not no_longer_exempt, (
        f'{sorted(no_longer_exempt)} now has borough-extra.json data, so it '
        'must be removed from BACKEND_ONLY_CITIES and actually compared.'
    )


def test_site_has_no_city_the_lambda_cannot_score():
    """The reverse gap: data on the site for a city the API does not serve."""
    orphans = _site_cities() - set(score_app.CITIES)
    assert not orphans, f'borough-extra.json holds unscoreable cities: {sorted(orphans)}'


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


@pytest.mark.parametrize('city', COMPARED_CITIES)
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


@pytest.mark.parametrize('city', COMPARED_CITIES)
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


@pytest.mark.parametrize('city', COMPARED_CITIES)
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


def test_name_aliases_match_the_builder():
    """The borough-name alias exists twice; fail the build if the copies drift.

    `scripts/build_borough_bands.py` needs the same `Barking` ->
    `Barking and Dagenham` mapping this file needs, for the same reason: the two
    holders key that borough differently. Without it `--sync-lambda` searches the
    Lambda source for "'Barking': {", finds nothing, and skips - which on
    2026-08-26 left Barking and Dagenham as the one London borough with no
    airQualityWhoRatio while its 32 neighbours had one.

    DUPLICATED RATHER THAN EXTRACTED, DELIBERATELY. No test here imports from
    scripts/ and no script imports from tests/, so sharing one entry means
    inventing a module for it. The precedent is _US_AIRPORT_CODES in the score
    Lambda, duplicated the same week for the same reason and guarded exactly
    like this. Extraction is the better end state; this is the control that
    makes the interim safe, per feedback-mirrored-code-drifts - a second correct
    copy is fine only while something fails when it stops being correct.
    """
    import importlib.util
    import os

    builder = os.path.normpath(
        os.path.join(
            os.path.dirname(__file__), os.pardir, 'scripts', 'build_borough_bands.py'
        )
    )
    spec = importlib.util.spec_from_file_location('build_borough_bands_alias', builder)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.NAME_ALIASES == NAME_ALIASES, (
        'NAME_ALIASES has drifted between tests/test_borough_data_parity.py and '
        f'scripts/build_borough_bands.py: {NAME_ALIASES} vs {module.NAME_ALIASES}. '
        'A borough missing from the builder copy is SILENTLY skipped by '
        '--sync-lambda, so it keeps the old value in the Lambda while the site '
        'moves on.'
    )
