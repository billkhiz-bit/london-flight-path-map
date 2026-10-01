"""Constants that exist in two scripts must be the same constant.

Audit M27 (13 Sep 2026). Three sets are declared twice, once in the script
that FETCHES a dataset and once in the script that DERIVES bands from it:

    fetch_defra_road_noise.WELSH        == build_borough_bands.NO_ROAD_COVERAGE
    fetch_ea_flood_risk.NO_COVERAGE     == build_borough_bands.NO_FLOOD_COVERAGE
    build_city_stations.RAIL_TYPES      == build_borough_bands.NAPTAN_RAIL_TYPES

They agreed on the day this was written and nothing checked it. The failure
each pair guards against is specific: a city added to the fetcher's exclusion
and not the builder's would have no raster and would be derived from nothing
(or from a stale one); a NaPTAN stop type added to the station list and not
the scored share would list stations the score does not count, or count
stations the panel does not list. `feedback-mirrored-code-drifts`: a second
correct copy is fine only while something fails when it stops being correct.

Offline. Imports the scripts from source; their heavy imports are lazy.
"""

import os
import re

import pytest

from .conftest import load_script

PAIRS = [
    ('fetch_defra_road_noise', 'WELSH', 'build_borough_bands', 'NO_ROAD_COVERAGE'),
    ('fetch_ea_flood_risk', 'NO_COVERAGE', 'build_borough_bands', 'NO_FLOOD_COVERAGE'),
    ('build_city_stations', 'RAIL_TYPES', 'build_borough_bands', 'NAPTAN_RAIL_TYPES'),
]


@pytest.mark.parametrize('mod_a,name_a,mod_b,name_b', PAIRS, ids=lambda p: p if isinstance(p, str) else '')
def test_mirrored_sets_agree(mod_a, name_a, mod_b, name_b):
    a = getattr(load_script(mod_a), name_a)
    b = getattr(load_script(mod_b), name_b)
    assert set(a) == set(b), (
        f'scripts/{mod_a}.py:{name_a} = {sorted(a)} but scripts/{mod_b}.py:{name_b} = '
        f'{sorted(b)}. Change both in the same commit, or the fetcher and the builder '
        'disagree about which cities (or stop types) exist.'
    )
    assert a, f'{mod_a}.{name_a} is empty - an emptied exclusion list is a silent widening'


# --- the DEFRA air-quality year (2026-10-01) --------------------------------
# One year, four holders: the loader's PCM_YEAR (which names the files it
# reads), the builder's AQ_VINTAGE, the score Lambda's source line, and
# METHODOLOGY's source table. A roll that moves three of them publishes figures
# from one year under a label naming another.

REPO = os.path.normpath(os.path.join(os.path.dirname(__file__), os.pardir))


def _years(path, pattern):
    text = open(os.path.join(REPO, path), encoding='utf-8').read()
    return {int(y) for y in re.findall(pattern, text)}


def test_pcm_air_quality_year_is_one_year_everywhere():
    loader = load_script('load_defra_air_quality')
    builder = load_script('build_borough_bands')
    year = loader.PCM_YEAR
    # The FILES each script reads, not only the labels it prints: a roll that
    # relabelled everything 2024 while the builder still read 2022 would pass a
    # label-only test (the first version of this one) and publish the wrong year.
    for name, mod in (('load_defra_air_quality', loader), ('build_borough_bands', builder)):
        assert mod.PCM_YEAR == year, f'scripts/{name}.py PCM_YEAR is {mod.PCM_YEAR}, the loader serves {year}'
        for path in (mod.NO2_CSV, mod.PM25_CSV):
            assert str(year) in path.name, f'scripts/{name}.py reads {path.name}, not PCM {year}'
    holders = {
        'scripts/build_borough_bands.py AQ_VINTAGE': {
            int(y) for y in re.findall(r'(\d{4}) annual mean', load_script('build_borough_bands').AQ_VINTAGE)
        },
        'backend/lambdas/score/app.py source line': _years(
            'backend/lambdas/score/app.py', r'background pollution maps \(PCM\), annual mean (\d{4})'
        ),
        'METHODOLOGY.md source table': _years(
            'METHODOLOGY.md', r'DEFRA background pollution maps \((\d{4}) annual mean'
        ),
    }
    for where, found in holders.items():
        assert found, f'{where}: no PCM year found - the pattern this test reads has moved'
        assert found == {year}, (
            f'{where} names {sorted(found)} but the loader serves PCM {year}. A roll changes all of them.'
        )


def test_air_quality_freshness_probe():
    """The probe's two failure directions, without the network."""
    check = load_script('check_air_quality_vintage')

    def probe_for(published):
        return lambda url: any(f'no2{y}.csv' in url or f'pm25{y}g.csv' in url for y in published)

    assert check.latest_published(2022, 2026, probe_for({2022, 2023, 2024})) == 2024
    assert check.latest_published(2022, 2026, probe_for({2022})) == 2022
    # A year counts only when BOTH files exist.
    half = lambda url: 'no2' in url or url.endswith('pm252022g.csv')  # noqa: E731
    assert check.latest_published(2022, 2026, half) == 2022
    # Renamed files: the served year no longer resolves, so "nothing newer" is
    # not evidence of being current - the probe must refuse, not report fresh.
    assert check.latest_published(2022, 2026, probe_for(set())) is None
