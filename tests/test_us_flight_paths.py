"""Tests for scripts/build_us_flight_paths.py, the FAA CIFP parser.

Why these exist: ARINC 424 is fixed-width, and a parser that reads one column
to the left still returns numbers. The slices in the builder were read off the
real file, and this pins them against a REAL excerpt of it - every San Jose
(KSJC) line of cycle 2610, with the header and the eleven enroute fixes and
navaids its departures name (tests/fixtures/cifp-ksjc-2610.txt, FAA data, a
work of the US government). Nothing in the fixture was written by hand, so it
can contradict the parser; the expected values below are worked out from the
raw strings, not copied from the parser's output.

They also pin the four things the builder refuses to do, each of which the
first version got wrong against real data on 2026-10-02: draw through radar
vectors, draw to an initial fix the route never reached, treat a fix that only
anchors a course as a point on the line, and give a runway with no published
glide angle three degrees.

Offline only.
"""

import copy
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    'build_us_flight_paths', REPO_ROOT / 'scripts' / 'build_us_flight_paths.py'
)
us = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(us)

FIXTURE = REPO_ROOT / 'tests' / 'fixtures' / 'cifp-ksjc-2610.txt'
SJC = {'SJC': {'icao': 'KSJC', 'cities': ['bayarea']}}


@pytest.fixture(scope='module')
def lines():
    return FIXTURE.read_text(encoding='ascii').splitlines()


@pytest.fixture(scope='module')
def sjc(lines):
    return us.build(lines, airports=SJC, effective='2026-10-01')['airports']['SJC']


def departure(sjc, name, runway):
    hits = [d for d in sjc['departures'] if d['name'] == name and d['runway'] == runway]
    assert len(hits) == 1, f'{name} {runway}: {len(hits)} transitions'
    return hits[0]


# ---- the fixture is the real file -----------------------------------------


def test_fixture_is_fixed_width_and_names_its_cycle(lines):
    assert lines[0].startswith('HDR01')
    body = [ln for ln in lines if ln.startswith('S')]
    assert len(body) >= 400, 'the excerpt has shrunk; it was 499 records'
    assert {len(ln) for ln in body} == {132}, 'a record lost its trailing spaces - an editor stripped them'


# ---- coordinates -----------------------------------------------------------


def test_dms_reads_hundredths_of_a_second():
    # N37212246 is 37 deg 21 min 22.46 s; W121552213 is 121 deg 55 min 22.13 s.
    assert us.dms('N37212246') == pytest.approx(37 + 21 / 60 + 22.46 / 3600, abs=1e-9)
    assert us.dms('W121552213') == pytest.approx(-(121 + 55 / 60 + 22.13 / 3600), abs=1e-9)


@pytest.mark.parametrize('bad', ['N3721224', '37212246N', 'E37212246', 'N372122461', ''])
def test_dms_refuses_anything_that_is_not_a_coordinate(bad):
    with pytest.raises(ValueError):
        us.dms(bad)


def test_variation_is_east_positive():
    assert us.variation('E0130') == 13.0
    assert us.variation('W0125') == -12.5


# ---- runways ---------------------------------------------------------------


def test_runway_thresholds_come_from_the_runway_record(sjc):
    assert sorted(sjc['runways']) == ['12L', '12R', '30L', '30R']
    # 'SUSAP KSJCK2GRW30L   0110003060 N37212246W121552213 ...'
    assert sjc['runways']['30L']['thr'] == [pytest.approx(37.356239, abs=1e-6), pytest.approx(-121.922814, abs=1e-6)]
    assert sjc['runways']['30L']['mag_brg'] == 306.0


def test_true_bearing_is_measured_and_agrees_with_the_published_magnetic(sjc):
    assert sjc['magvar_deg'] == 13.0
    r30, r12 = sjc['runways']['30L'], sjc['runways']['12R']
    # 306 magnetic + 13 east = 319 true, within what a magnetic bearing rounds to.
    assert us.angle_between(r30['true_brg'], 319.0) < 1.0
    assert us.angle_between(r30['true_brg'], r12['true_brg']) == pytest.approx(180, abs=0.1)


def test_reciprocal_pairs_parallel_runways_across():
    assert us.reciprocal('30L') == '12R'
    assert us.reciprocal('12L') == '30R'
    assert us.reciprocal('01') == '19'
    assert us.reciprocal('36') == '18'


# ---- glide angles ----------------------------------------------------------


def test_glide_comes_from_the_ils_where_there_is_one(sjc):
    assert sjc['runways']['30L']['glide_deg'] == 3.0
    assert sjc['runways']['30L']['glide_source'] == 'CIFP ILS glide slope ISJC'


def test_glide_falls_back_to_an_approach_vertical_angle_and_says_which(sjc):
    # 12L and 30R have no ILS; their RNAV (GPS) approaches publish the angle.
    assert sjc['runways']['12L']['glide_deg'] == 3.0
    assert sjc['runways']['12L']['glide_source'] == 'CIFP approach R12LY vertical angle'


def test_a_runway_with_no_published_angle_gets_none_and_a_reason(lines):
    # Take away every source for 30R: its approach records. It has no ILS record.
    stripped = [ln for ln in lines if not (ln.startswith('SUSAP KSJCK2F') and ln[13:19].strip() in ('R30RY', 'H30RZ'))]
    r = us.build(stripped, airports=SJC)['airports']['SJC']['runways']['30R']
    assert r['glide_deg'] is None
    # The not-coded list was not read here, so the builder may not say what the FAA publishes.
    assert r['glide_source'].startswith('none in the CIFP')


def test_the_reason_for_no_glide_angle_says_which_kind_of_absence(lines):
    # Kennedy's 13R and Teterboro's 01 have a PUBLISHED approach the file does
    # not code. The first record said "none published" of both.
    stripped = [ln for ln in lines if not (ln.startswith('SUSAP KSJCK2F') and ln[13:19].strip() in ('R30RY', 'H30RZ'))]

    def reason(not_coded):
        rec = us.build(stripped, airports=SJC, not_coded=not_coded)
        return rec['airports']['SJC']['runways']['30R']['glide_source']

    uncoded = reason({'KSJC': ['R30RZ', 'SJC9']})
    assert uncoded.startswith('not coded') and 'R30RZ' in uncoded and 'SJC9' not in uncoded
    # An uncoded approach to the OTHER runway, or none at all, is not this runway's reason.
    assert reason({'KSJC': ['R30LZ']}).startswith('none published')
    assert reason({'KSJC': []}).startswith('none published')


@pytest.mark.parametrize(
    ('ident', 'runway'),
    [('R13RZ', '13R'), ('R01', '01'), ('R29-T', '29'), ('I28L', '28L'), ('JFK5', None), ('NIMI6', None)],
)
def test_an_approach_ident_names_its_runway(ident, runway):
    assert us.runway_of_approach(ident) == runway


# ---- departures ------------------------------------------------------------


def test_a_coded_departure_is_its_named_fixes_in_order(sjc):
    d = departure(sjc, 'TECKY4', '12')
    assert d['fixes'] == ['NEVSE', 'TECKY']
    assert d['runways'] == ['12L', '12R'], 'RW12B means both 12s'
    assert d['vectored'] is False
    # 'SUSAP KSJCK2CTECKY K20    W     N37035159W121292045 ...'
    assert d['waypoints'][1] == [pytest.approx(37.064331, abs=1e-6), pytest.approx(-121.489014, abs=1e-6)]
    assert 'VA 126M to 570 ft; DF NEVSE; TF TECKY' in d['source']


def test_a_route_stops_where_radar_vectors_begin(sjc):
    # LOUPE1: 'VA; DF STCLR; DF LOUPE; FM LOUPE; IF SJC; TF BMRNG'. After LOUPE
    # a controller decides; SJC and BMRNG are not on a line anyone published.
    d = departure(sjc, 'LOUPE1', '30L')
    assert d['fixes'] == ['STCLR', 'LOUPE']
    assert d['vectored'] is True


def test_vectors_before_the_first_fix_leave_no_line(sjc):
    # BMRNG4: 'VA 126M to 570 ft; VM 126M; DF GRRIF; ...' - vectors from the runway.
    d = departure(sjc, 'BMRNG4', '12')
    assert d['waypoints'] == [] and d['fixes'] == []
    assert d['vectored'] is True


def test_an_initial_fix_the_route_never_reached_is_not_drawn_to(sjc):
    # SJC3 is coded as one leg, 'IF MOONY', 40 km away. Runway to MOONY in a
    # straight line is a path nobody published.
    d = departure(sjc, 'SJC3', '30')
    assert d['waypoints'] == []
    assert d['vectored'] is True


def test_a_fix_that_only_anchors_a_course_is_not_a_point_on_the_line(sjc):
    # SUNOL1 from 12: 'VI 126M; FA OAK; VM 303M; CF SUNOL'. OAK is the Oakland
    # VOR, 48 km away: the leg flies a course FROM it, not to it.
    d = departure(sjc, 'SUNOL1', '12')
    assert 'OAK' not in d['fixes']
    assert d['waypoints'] == []


def test_enroute_transitions_are_left_out(sjc):
    # TECKY4 continues to JFREE and VLREE on enroute transitions.
    assert all('JFREE' not in d['fixes'] and 'VLREE' not in d['fixes'] for d in sjc['departures'])


def test_not_coded_is_absent_unless_the_list_was_read(sjc):
    # The tests pass lines alone, so the builder must not claim an empty list.
    assert 'procedures_not_coded' not in sjc


def rekeyed_common_route(lines, sid, ident):
    """The fixture with one SID reduced to a common route keyed `ident`.

    The shape of Oakland's SLNT3 in the real file: no runway transition, one
    common-route record marked RW30. San Jose has none like it, so LOUPE1's
    real common route is re-keyed and its runway transitions dropped.
    """
    out = []
    for ln in lines:
        if ln.startswith('SUSAP KSJCK2D') and ln[13:19].strip() == sid:
            if ln[19] in us.RUNWAY_TRANSITION:
                continue
            if ln[19] in us.COMMON_ROUTE:
                ln = ln[:20] + ident.ljust(5) + ln[25:]
        out.append(ln)
    assert len(out) < len(lines)
    return out


def test_a_common_route_keyed_to_one_runway_serves_that_runway_alone(lines):
    rec = us.build(rekeyed_common_route(lines, 'LOUPE1', 'RW30L'), airports=SJC)
    loupe = [d for d in rec['airports']['SJC']['departures'] if d['name'] == 'LOUPE1']
    assert [(d['runway'], d['runways']) for d in loupe] == [('30L', ['30L'])]


def test_a_common_route_with_no_key_still_serves_every_runway(lines):
    rec = us.build(rekeyed_common_route(lines, 'LOUPE1', ''), airports=SJC)
    loupe = [d for d in rec['airports']['SJC']['departures'] if d['name'] == 'LOUPE1']
    assert [(d['runway'], d['runways']) for d in loupe] == [('ALL', ['12L', '12R', '30L', '30R'])]


def test_a_common_route_keyed_to_neither_a_runway_nor_all_is_refused(lines):
    with pytest.raises(SystemExit, match='neither a runway nor ALL'):
        us.build(rekeyed_common_route(lines, 'LOUPE1', 'HRNER'), airports=SJC)


# ---- the not-coded list ----------------------------------------------------

HEADER = ('ARINC_ID', 'TERM_ID')


def test_not_coded_rows_are_read_per_airport():
    sheets = [[HEADER, ('KJFK', 'JFK5'), ('KJFK', 'R13RZ'), ('KBOS', 'LOGAN9'), ('KSJC', None)]]
    assert us.not_coded_from_rows(sheets, ['KJFK', 'KSJC']) == {'KJFK': ['JFK5', 'R13RZ'], 'KSJC': []}


def test_a_not_coded_sheet_with_a_moved_column_is_refused():
    # A column added in front would otherwise read states as airport codes and return "nothing uncoded".
    sheets = [[('STATE', 'ARINC_ID', 'TERM_ID'), ('NY', 'KJFK', 'JFK5')]]
    with pytest.raises(SystemExit, match='layout has changed'):
        us.not_coded_from_rows(sheets, ['KJFK'])


def test_a_not_coded_sheet_naming_none_of_our_airports_is_refused():
    sheets = [[HEADER, ('JFK', 'JFK5'), ('EWR', 'EWR5')]]
    with pytest.raises(SystemExit, match='changed form'):
        us.not_coded_from_rows(sheets, ['KJFK', 'KEWR'])


# ---- the zip ---------------------------------------------------------------


def test_a_renamed_zip_is_refused_before_it_can_write_a_null_date(tmp_path):
    with pytest.raises(SystemExit, match='does not carry the cycle date'):
        us.from_zip(tmp_path / 'cifp.zip')


def test_a_download_cut_short_is_not_a_complete_zip(tmp_path):
    import zipfile

    whole = tmp_path / 'whole.zip'
    with zipfile.ZipFile(whole, 'w') as z:
        z.writestr(us.MEMBER, 'HDR01')
        z.writestr(us.NOT_CODED, 'x')
    assert us.complete_zip(whole)
    cut = tmp_path / 'cut.zip'
    cut.write_bytes(whole.read_bytes()[:40])
    assert not us.complete_zip(cut)
    other = tmp_path / 'other.zip'
    with zipfile.ZipFile(other, 'w') as z:
        z.writestr('README.txt', 'not the CIFP')
    assert not us.complete_zip(other)


# ---- the parser fails loudly ----------------------------------------------


def test_a_short_record_is_refused(lines):
    broken = list(lines)
    i = next(n for n, ln in enumerate(broken) if ln.startswith('SUSAP KSJCK2G'))
    broken[i] = broken[i][:-1]
    with pytest.raises(SystemExit, match='131 characters'):
        us.build(broken, airports=SJC)


def test_a_fix_the_file_does_not_hold_is_refused(lines):
    without = [ln for ln in lines if not ln.startswith('SUSAP KSJCK2CNEVSE')]
    with pytest.raises(SystemExit, match='NEVSE'):
        us.build(without, airports=SJC)


def test_a_file_with_no_header_is_refused(lines):
    with pytest.raises(SystemExit, match='HDR01'):
        us.build(lines[1:], airports=SJC)


def test_a_runway_with_no_reciprocal_is_refused(lines):
    one_ended = [ln for ln in lines if not ln.startswith('SUSAP KSJCK2GRW12R')]
    with pytest.raises(SystemExit, match='no reciprocal'):
        us.build(one_ended, airports=SJC)


# ---- check() can go red ----------------------------------------------------


@pytest.fixture()
def record(lines):
    return us.build(lines, airports=SJC, effective='2026-10-01')


def test_check_passes_the_real_record_and_counts_what_it_checked(record):
    fails, compared = us.check(record)
    assert fails == []
    assert compared == 4 + len(record['airports']['SJC']['departures'])


def test_check_fails_on_an_empty_record():
    fails, compared = us.check({'airports': {}})
    assert compared == 0
    assert any('nothing was checked' in f for f in fails)


def test_check_fails_when_a_bearing_is_edited(record):
    bad = copy.deepcopy(record)
    bad['airports']['SJC']['runways']['30L']['true_brg'] += 10
    fails, _ = us.check(bad)
    assert any('30L' in f for f in fails)


def test_check_fails_on_an_invented_glide_angle(record):
    bad = copy.deepcopy(record)
    bad['airports']['SJC']['runways']['30L']['glide_deg'] = 5.5
    assert any('glide angle' in f for f in us.check(bad)[0])


def test_check_fails_on_a_missing_glide_with_no_reason(record):
    bad = copy.deepcopy(record)
    bad['airports']['SJC']['runways']['30L'].update(glide_deg=None, glide_source='')
    assert any('no reason' in f for f in us.check(bad)[0])


def test_check_fails_on_an_angle_typed_over_a_runway_with_none(record):
    # In range, so the range check passes it: "given three degrees because most runways are".
    bad = copy.deepcopy(record)
    bad['airports']['SJC']['runways']['30L'].update(glide_deg=3.0, glide_source='none published: no ILS')
    assert any('its source is' in f for f in us.check(bad)[0])


def test_check_fails_on_a_record_with_no_effective_date(record):
    bad = copy.deepcopy(record)
    bad['effective'] = None
    assert any('not a date' in f for f in us.check(bad)[0])


def test_check_fails_on_a_departure_from_a_runway_that_is_not_there(record):
    bad = copy.deepcopy(record)
    bad['airports']['SJC']['departures'][0]['runways'] = ['07']
    assert any('not all runways here' in f for f in us.check(bad)[0])


def test_check_fails_on_a_first_fix_implausibly_far_away(record):
    bad = copy.deepcopy(record)
    dep = next(d for d in bad['airports']['SJC']['departures'] if d['waypoints'])
    dep['waypoints'][0] = [45.0, -100.0]
    assert any('km from the airport' in f for f in us.check(bad)[0])


# ---- the checked-in record -------------------------------------------------


def test_the_checked_in_record_passes_its_own_check():
    import json

    record = json.loads((REPO_ROOT / 'data' / 'us-flight-procedures.json').read_text(encoding='utf-8'))
    fails, compared = us.check(record)
    assert fails == []
    assert compared > 0
    assert set(record['airports']) == set(us.AIRPORTS)
    # Not_In_CIFP was read: every airport says what the FAA has not coded, even when that is nothing.
    assert all('procedures_not_coded' in ap for ap in record['airports'].values())


def test_the_checked_in_record_says_what_the_real_file_says():
    import json

    airports = json.loads((REPO_ROOT / 'data' / 'us-flight-procedures.json').read_text(encoding='utf-8'))['airports']
    # Oakland's SLNT3 is one common-route record keyed RW30. It was recorded as leaving all eight runways.
    slnt = [d for d in airports['OAK']['departures'] if d['name'] == 'SLNT3']
    assert [(d['runway'], d['runways']) for d in slnt] == [('30', ['30'])]
    # No departure claims every runway: none of these seven airports has a SID without a runway key.
    assert not [d['name'] for ap in airports.values() for d in ap['departures'] if d['runway'] == 'ALL']
    # Kennedy 13R and Teterboro 01 have a published approach the file does not code.
    assert 'R13RZ' in airports['JFK']['runways']['13R']['glide_source']
    assert airports['JFK']['runways']['13R']['glide_source'].startswith('not coded')
    assert airports['TEB']['runways']['01']['glide_source'].startswith('not coded')
    assert airports['SFO']['runways']['01L']['glide_source'].startswith('none published')


def test_check_without_the_zip_says_unverified_not_ok(monkeypatch, tmp_path, capsys):
    # The zip is gitignored, so this is every fresh clone. Preflight prints
    # INCONCLUSIVE for a line that STARTS with UNVERIFIED, and PASS otherwise.
    monkeypatch.setattr(us, 'CACHE', tmp_path)
    monkeypatch.setattr(us.sys, 'argv', ['build_us_flight_paths.py', '--check'])
    assert us.main() == 0
    assert any(ln.startswith('UNVERIFIED') for ln in capsys.readouterr().out.splitlines())
