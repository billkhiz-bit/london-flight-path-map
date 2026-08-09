"""Liveability redistribution: what happens when an input does not exist.

The defect this replaces is subtle and was live in production. Every absent
liveability input defaulted to 5.0, and 5.0 is not neutral - London's computed
live scores span 5.5-8.4, so the placeholder sat BELOW every real borough.
Consequences, both counter-intuitive:

  - a place with no data scored worse than the worst place with data
  - filling in ONE of four fields could push a city LOWER, which is why Greater
    Manchester has to be all four fields or none

City of London is the live example: it has no Progress 8 because it has no
state secondary provision, so 35% of its published liveability was a number
about nothing. That absence is CORRECT and must stay scoreable - the fix is to
redistribute the weight, not to refuse the borough.
"""

import itertools
import os
import sys

import pytest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), os.pardir, 'lambdas', 'score')
)
import app  # noqa: E402

ALL_FIELDS = app._LIVE_FIELDS


# ---- live_weights_for -------------------------------------------------------


@pytest.mark.parametrize(
    'subset',
    [
        s
        for n in range(1, len(ALL_FIELDS) + 1)
        for s in itertools.combinations(ALL_FIELDS, n)
    ],
)
def test_weights_sum_to_one_or_decline(subset):
    """Every non-empty subset either sums to 1.0 or declines outright.

    A subset summing to anything else silently rescales the whole composite -
    the component would still be called `live` and still be on 0-10, but would
    no longer mean what the other cities' means.
    """
    w = app.live_weights_for(subset)
    if not w:
        assert len(subset) < app._LIVE_MIN_FIELDS
        return
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert set(w) == set(subset), 'weights must cover exactly the inputs given'


def test_complete_set_is_unchanged_from_declared_weights():
    """With all four present, redistribution must be the identity.

    This is what keeps 37 of 38 existing boroughs bit-identical.
    """
    w = app.live_weights_for(ALL_FIELDS)
    assert w == pytest.approx(app._LIVE_WEIGHTS)


def test_redistribution_is_proportional_not_equal():
    """Dropping schools must keep crime at 3x healthcare, as declared.

    Equal shares would promote healthcare from a 10% input to a 25% one, which
    is a different opinion about the place rather than the same one with a gap.
    """
    w = app.live_weights_for(('crimeRate', 'transport', 'healthcare'))
    assert w['crimeRate'] / w['healthcare'] == pytest.approx(0.30 / 0.10)
    assert w['transport'] / w['healthcare'] == pytest.approx(0.25 / 0.10)
    assert w['healthcare'] != pytest.approx(1 / 3), 'that would be equal shares'


@pytest.mark.parametrize('field', ALL_FIELDS)
def test_single_input_declines_rather_than_scaling_to_one(field):
    """One input promoted to 100% would make `live` mean that one thing."""
    assert app.live_weights_for((field,)) == {}


def test_two_inputs_is_the_floor_and_is_accepted():
    w = app.live_weights_for(('crimeRate', 'healthcare'))
    assert w, 'two inputs is on the accepted side of the floor'
    assert sum(w.values()) == pytest.approx(1.0)


# ---- absence is never a value ----------------------------------------------


# A full borough, so each case below removes exactly one field and nothing else.
_COMPLETE = {
    'p8': 0.1,
    'crimeRate': 100,
    'transport': 'good',
    'healthcare': 'good',
}

# Which data key backs each scored field, so 'schools' maps to p8 for an
# English borough rather than to a key of its own name.
_FIELD_KEY = {
    'schools': 'p8',
    'crimeRate': 'crimeRate',
    'transport': 'transport',
    'healthcare': 'healthcare',
}


@pytest.mark.parametrize('field', ALL_FIELDS)
def test_absent_input_is_omitted_not_defaulted(field):
    """The 5.0 placeholder must not reappear under any name, for ANY field.

    Parametrised per field on purpose. The first version of this test pinned a
    fixture that happened to supply `transport`, so restoring the old
    `.get(..., 5)` on that one field left it green - the exact scope gap this
    repo keeps rediscovering. Removing one field at a time is what makes the
    test cover what its name claims.
    """
    bd = {k: v for k, v in _COMPLETE.items() if k != _FIELD_KEY[field]}
    scores = app.live_component_scores(bd, english=True)
    assert field not in scores, f'{field} was defaulted rather than omitted'
    assert set(scores) == set(ALL_FIELDS) - {field}


def test_english_borough_ignores_the_retired_ofsted_band():
    """v3.5 removed the band as editorial, so it is not a schools input.

    Counting it would make a borough claim `measured` on a source the
    methodology explicitly retired.
    """
    bd = {'schools': 'good', 'crimeRate': 100, 'transport': 'good'}
    assert 'schools' not in app.live_component_scores(bd, english=True)
    assert 'schools' in app.live_component_scores(bd, english=False)


def test_get_live_score_returns_none_below_the_floor():
    assert app.get_live_score({'crimeRate': 100}) is None
    assert app.get_live_score({}) is None


def test_unknown_categorical_raises_rather_than_scoring_five():
    """The old code silently scored 5.0 for a value no table recognised.

    validate_borough_vocabulary() catches this at import for real data, so a
    KeyError here means that guard was bypassed - which must be loud.
    """
    with pytest.raises(KeyError):
        app.live_component_scores({'transport': 'mixed'})  # TRANSPORT's is 'poor'


# ---- regression against the live data --------------------------------------


def test_city_of_london_is_no_longer_part_placeholder():
    bd = app.CITIES['london']['boroughs']['City of London']
    assert bd.get('p8') is None, 'the City genuinely has no Progress 8'
    scores = app.live_component_scores(bd, english=True)
    assert 'schools' not in scores
    assert app.get_live_score(bd, english=True) is not None, 'still scoreable'


def test_every_complete_borough_is_unchanged_by_redistribution():
    """The lock that makes this a correction rather than a reweighting.

    Recomputes the pre-change formula and asserts only boroughs with a genuine
    gap moved. If a future weight edit changes a complete borough, this fails.
    """

    def old_formula(bd):
        p8 = bd.get('p8')
        sch = (
            app.school_score(p8)
            if p8 is not None
            else app.SCHOOL_SCORE.get(bd.get('schools'), 5)
        )
        crm = app.crime_to_score(bd.get('crimeRate'))
        trn = app.TRANSPORT_SCORE.get(bd.get('transport'), 5)
        hlt = app.HEALTH_SCORE.get(bd.get('healthcare'), 5)
        return round((sch * 0.35 + crm * 0.30 + trn * 0.25 + hlt * 0.10) * 10) / 10

    moved = []
    for city_id, cfg in app.CITIES.items():
        english = cfg.get('country') == 'United Kingdom'
        for name, bd in cfg['boroughs'].items():
            new = app.get_live_score(bd, english=english)
            if new != old_formula(bd):
                moved.append(f'{city_id}/{name}')

    assert moved == ['london/City of London'], (
        'only boroughs with a genuine data gap may move; moved=' + repr(moved)
    )
