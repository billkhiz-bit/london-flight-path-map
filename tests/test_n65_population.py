"""N65 item 3: the people inside the 50-event contour (scripts/n65_population.py), 2026-11-12.

The Census and NSPL files here are MADE UP, so it runs anywhere; one check reads the built file when this machine has
it. Held: P001's two sexes summed, another table's header, a part-person count and a repeated row refused; each
postcode at NSPL's grid reference, never its lat/long (only a row with no grid reference is projected, and counted);
a retired postcode keeps its people; a large user is flagged; a Census postcode NSPL lacks is counted as unplaced,
never dropped; a person counts only in a cell that reaches the level, by the grid's own cell rule (never a bounding
box); a contour at the grid's edge, counts for another grid, a missing or foreign file are refused.
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import n65_population as pop  # noqa: E402

GRID = {'x0': 0.0, 'y0': 0.0, 'nx': 10, 'ny': 8}
CELL = 100.0
NSPL_COLUMNS = ['pcds', 'dointr', 'doterm', 'usrtypind', 'east1m', 'north1m', 'lat', 'long']
ENGLAND_AND_WALES_2021 = 59_597_542  # Census 2021 usual residents, TS001 (Nomis NM_2021_1), read 12 Nov 2026


def _census(path, rows, header=pop.CENSUS_HEADER):
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return path


def _nspl(path, rows):
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, NSPL_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({'dointr': '202001', 'doterm': '', 'usrtypind': '0', 'lat': '51.47', 'long': '-0.45', **r})
    return path


def _people(points):
    """A population as load() returns it: [(east, north, residents, large_user, retired)]."""
    e, n, r, big, old = zip(*points, strict=True)
    return {'east': np.asarray(e, float), 'north': np.asarray(n, float), 'residents': np.asarray(r, np.int32),
            'large_user': np.asarray(big, bool), 'retired': np.asarray(old, bool), 'meta': {'kind': pop.KIND}}


def _counts(cells, value=60.0):
    """A flat grid (j * nx + i) with `value` at each (i, j) in `cells`, 0 elsewhere."""
    c = np.zeros(GRID['nx'] * GRID['ny'])
    for i, j in cells:
        c[j * GRID['nx'] + i] = value
    return c


def test_the_two_sexes_are_summed(tmp_path):
    f = _census(tmp_path / 'p001.csv', [['TW6 2GA', '1', 'Female', '11'], ['TW6 2GA', '2', 'Male', '2'],
                                        ['tw4 5aa', '2', 'Male', '7']])
    assert pop.read_census(f) == {'TW6 2GA': 13, 'TW4 5AA': 7}


@pytest.mark.parametrize('rows, header, why', [
    ([['TW6 2GA', '1', 'Female', '3']], ['Postcode', 'Households'], 'is not P001'),
    ([['TW6 2GA', '1', 'Female', '3.5']], pop.CENSUS_HEADER, 'not a whole number'),
    ([['TW6 2GA', '1', 'Female', '-3']], pop.CENSUS_HEADER, 'not a whole number'),
    ([['TW6 2GA', '1', 'Female', '3'], ['TW6 2GA', '1', 'Female', '3']], pop.CENSUS_HEADER, 'twice'),
])
def test_another_table_a_part_person_and_a_repeat_are_refused(tmp_path, rows, header, why):
    with pytest.raises(pop.Refused, match=why):
        pop.read_census(_census(tmp_path / 'p001.csv', rows, header))


def test_each_postcode_sits_at_nspls_grid_reference_with_its_flags(tmp_path):
    residents = {'AA1 1AA': 10, 'AA1 1AB': 20, 'AA1 1AC': 30, 'AA1 1AD': 40, 'ZZ9 9ZZ': 5}
    nspl = _nspl(tmp_path / 'nspl.csv', [
        {'pcds': 'AA1 1AA', 'east1m': '150', 'north1m': '250'},  # its lat/long would put it ~507 km east
        {'pcds': 'AA1 1AB', 'east1m': '350', 'north1m': '250', 'doterm': '202304'},  # retired since 2021
        {'pcds': 'AA1 1AC', 'east1m': '450', 'north1m': '250', 'usrtypind': '1'},  # a large user
        {'pcds': 'AA1 1AD', 'east1m': '', 'north1m': ''},  # no grid reference: its lat/long, projected
        {'pcds': 'BB1 1BB', 'east1m': '1', 'north1m': '1'},  # in NSPL, nobody living there in 2021
    ])
    arrays, about = pop.place(residents, nspl)
    got = {(round(e), round(n)): int(r) for e, n, r in zip(arrays['east'], arrays['north'], arrays['residents'],
                                                            strict=True)}
    assert got[(150, 250)] == 10 and got[(350, 250)] == 20 and got[(450, 250)] == 30
    assert list(arrays['retired']) == [False, True, False, False]
    assert list(arrays['large_user']) == [False, False, True, False]
    assert about['placed_from_lat_long'] == 1
    assert 500_000 < arrays['east'][3] < 510_000  # (51.47, -0.45) is near Heathrow, projected
    assert about['postcodes_unplaced'] == 1 and about['people_unplaced'] == 5 and about['unplaced_examples'] == ['ZZ9 9ZZ']
    assert about['people_placed'] + about['people_unplaced'] == about['people_in_census'] == 105


def test_a_person_counts_only_inside_the_cells_never_a_bounding_box():
    # An L of cells reaching 50: (2..5, 2) and (2, 3..5). The notch (4, 4) is inside its bounding box, not the L.
    counts = _counts([(i, 2) for i in range(2, 6)] + [(2, j) for j in range(3, 6)])
    people = _people([(450, 250, 100, False, False),  # in (4, 2): inside
                      (250, 450, 20, True, False),  # in (2, 4): inside, a large user
                      (450, 450, 7000, False, False),  # in the notch (4, 4): outside
                      (950, 750, 9, False, False),  # in (9, 7), a cell at 0
                      (-50, 250, 3, False, False), (1050, 250, 3, False, False)])  # off the grid
    got = pop.people_inside(counts, GRID, CELL, people, 50)
    assert got == {'people': 120, 'postcodes': 2, 'people_at_large_users': 20, 'people_at_retired_postcodes': 0,
                   'level': 50}


def test_the_level_is_reached_at_the_level_itself_as_the_area_counts_it():
    people = _people([(250, 250, 1, False, False)])
    assert pop.people_inside(_counts([(2, 2)], 50.0), GRID, CELL, people, 50)['people'] == 1
    assert pop.people_inside(_counts([(2, 2)], 49.999), GRID, CELL, people, 50)['people'] == 0


def test_a_point_on_a_cells_edge_belongs_to_the_cell_it_starts():
    people = _people([(300.0, 250.0, 1, False, False)])  # x = x0 + 3 cells exactly: cell 3, not 2
    assert pop.people_inside(_counts([(3, 2)]), GRID, CELL, people, 50)['people'] == 1
    assert pop.people_inside(_counts([(2, 2)]), GRID, CELL, people, 50)['people'] == 0


@pytest.mark.parametrize('cell', [(4, 0), (4, 7), (0, 3), (9, 3)])
def test_a_contour_at_the_grids_edge_is_refused(cell):
    with pytest.raises(pop.Refused, match="reaches the grid's edge"):
        pop.people_inside(_counts([cell]), GRID, CELL, _people([(450, 350, 1, False, False)]), 50)


def test_counts_for_another_grid_are_refused():
    with pytest.raises(pop.Refused, match='for a 10 x 8 grid'):
        pop.people_inside(np.zeros(81), GRID, CELL, _people([(450, 350, 1, False, False)]), 50)


def test_build_writes_a_file_load_reads_back(tmp_path):
    census = _census(tmp_path / 'p001.csv', [['AA1 1AA', '1', 'Female', '4'], ['AA1 1AA', '2', 'Male', '5']])
    nspl = _nspl(tmp_path / 'nspl.csv', [{'pcds': 'AA1 1AA', 'east1m': '250', 'north1m': '350'}])
    meta = pop.build(census, nspl, tmp_path / 'out' / 'residents.npz')
    back = pop.load(tmp_path / 'out' / 'residents.npz')
    assert back['meta'] == json.loads(json.dumps(meta)) and back['meta']['source'] == pop.SOURCE
    assert int(back['residents'][0]) == 9 and float(back['east'][0]) == 250.0
    assert pop.people_inside(_counts([(2, 3)]), GRID, CELL, back, 50)['people'] == 9


def test_a_missing_or_foreign_file_is_refused(tmp_path):
    with pytest.raises(pop.Refused, match='no population file'):
        pop.load(tmp_path / 'nowhere.npz')
    np.savez_compressed(tmp_path / 'other.npz', meta=json.dumps({'kind': 'something-else'}), east=np.zeros(1))
    with pytest.raises(pop.Refused, match='not an N65 population file'):
        pop.load(tmp_path / 'other.npz')


@pytest.mark.skipif(not pop.DEFAULT_FILE.exists(), reason='data/n65/population/ is not built on this machine '
                    '(gitignored: n65_population.py build)')
def test_the_built_file_holds_the_whole_census_placed():
    meta = pop.load()['meta']
    assert meta['source'] == pop.SOURCE
    # The postcode file sums within 0.01% of ONS's own total (disclosure control moves small counts, never the sum).
    assert abs(meta['people_in_census'] / ENGLAND_AND_WALES_2021 - 1) < 1e-4, meta['people_in_census']
    assert meta['people_unplaced'] < 1e-4 * meta['people_in_census'], meta['unplaced_examples']
