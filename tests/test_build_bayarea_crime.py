"""Tests for scripts/build_bayarea_crime.py, the Bay Area's crime input (release 2, decision 4).

The raw DOJ and Census files are gitignored, so the guards are tested on small stand-ins: a blank
count fails the read rather than adding zero to the state total, a sheriff-contract city that gains
a DOJ row (or a city that loses one) stops the build, the check holds the no-rate set both ways and
the arithmetic of every rate, and the "few residents" rule flags the two cities decision 4 names.
Offline only.
"""

import copy
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location('build_bayarea_crime', REPO_ROOT / 'scripts' / 'build_bayarea_crime.py')
bc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bc)

HEAD = 'Year,County,NCICCode,Violent_sum,Property_sum\n'
STATE = 22.27  # California 2025, violent + property per 1,000 (decision 4's 22.3)


def place(name, geoid, county='San Mateo', kind='city'):
    return {'name': name, 'geoid': geoid, 'county': county, 'kind': kind}


def rated(name, geoid, violent, prop, population):
    return {'geoid': geoid, 'name': name, 'kind': 'city', 'county': 'San Mateo', 'population': population,
            'agency': name, 'violent': violent, 'property': prop,
            'per_1000': round(1000 * (violent + prop) / population, 1), 'few_residents': False}


def unrated(name, geoid):
    return {'geoid': geoid, 'name': name, 'kind': 'city', 'county': 'San Mateo', 'population': 30000,
            'agency': None, 'violent': None, 'property': None, 'per_1000': None, 'few_residents': False,
            'no_rate': bc.NO_RATE_REASON}


def sound_doc():
    sheriff = [unrated(n, f'06{i:05d}') for i, n in enumerate(sorted(bc.SHERIFF_CONTRACT))]
    return {'california': {'crimes': 876322, 'population': 39355309, 'per_1000': STATE},
            'cities': [rated('Belmont', '0605108', 60, 319, 28752), *sheriff]}


def test_a_blank_count_fails_the_read_instead_of_counting_as_zero(tmp_path, monkeypatch):
    raw = tmp_path / 'crime.csv'
    raw.write_text(HEAD + '2025,San Mateo County,Belmont,60,319\n2025,San Mateo County,Brisbane,,46\n',
                   encoding='utf-8')
    monkeypatch.setattr(bc, 'CRIME_RAW', raw)
    with pytest.raises(SystemExit, match='blank count'):
        bc.read_crime()


def test_only_the_year_is_read_and_a_repeated_agency_fails(tmp_path, monkeypatch):
    raw = tmp_path / 'crime.csv'
    raw.write_text(HEAD + '2024,San Mateo County,Belmont,1,1\n2025,San Mateo County,Belmont,60,319\n',
                   encoding='utf-8')
    monkeypatch.setattr(bc, 'CRIME_RAW', raw)
    assert bc.read_crime() == ({('San Mateo County', 'Belmont'): (60, 319)}, 379)
    raw.write_text(raw.read_text(encoding='utf-8') + '2025,San Mateo County,Belmont,1,1\n', encoding='utf-8')
    with pytest.raises(SystemExit, match='twice'):
        bc.read_crime()


@pytest.mark.parametrize('agencies, message', [
    # DOJ starts reporting San Carlos on its own: the declared set is out of date
    ({('San Mateo County', 'Belmont'): (60, 319), ('San Mateo County', 'San Carlos'): (40, 300)}, 'a DOJ row'),
    # Belmont loses its row: a city with no rate that is NOT a sheriff-contract city
    ({}, 'no DOJ row'),
])
def test_a_city_whose_row_disagrees_with_the_sheriff_set_stops_the_build(monkeypatch, agencies, message):
    monkeypatch.setattr(bc, 'cities', lambda: [place('Belmont', '0605108'), place('San Carlos', '0665070')])
    monkeypatch.setattr(bc, 'read_crime', lambda: (agencies, 876322))
    monkeypatch.setattr(bc, 'read_population', lambda: (
        {'0605108': ('Belmont city', 28752), '0665070': ('San Carlos city', 30000)}, 39355309))
    monkeypatch.setattr(bc, 'few_residents', lambda *a: False)
    with pytest.raises(SystemExit, match=message):
        bc.build()


def test_the_check_passes_a_sound_file_and_reds_each_defect():
    doc = sound_doc()
    want = [place(r['name'], r['geoid']) for r in doc['cities']]
    assert bc.problems(doc, want) == []

    zeroed = copy.deepcopy(doc)  # absence rendered as a measurement
    next(r for r in zeroed['cities'] if r['name'] == 'San Carlos').update(per_1000=0.0, violent=0, property=0)
    assert any('sheriff-contract set' in p for p in bc.problems(zeroed, want))

    dropped = copy.deepcopy(doc)
    dropped['cities'] = [r for r in dropped['cities'] if r['name'] != 'Belmont']
    assert any('missing' in p for p in bc.problems(dropped, want))

    edited = copy.deepcopy(doc)
    edited['cities'][0]['per_1000'] = 9.9
    assert any('not its counts' in p for p in bc.problems(edited, want))

    anchor = copy.deepcopy(doc)
    anchor['california']['per_1000'] = 22.3  # typed in, not derived
    assert any('anchor' in p for p in bc.problems(anchor, want))


def test_the_few_residents_note_marks_the_two_cities_decision_4_names_and_not_a_big_city():
    assert bc.few_residents(1385, 469.3, STATE)      # Colma: malls and cemeteries
    assert bc.few_residents(13251, 109.1, STATE)     # Emeryville: IKEA and Bay Street
    assert not bc.few_residents(440838, 67.5, STATE)  # Oakland: a high rate, but not few residents
