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
