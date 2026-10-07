"""Tests for scripts/build_bay_area_page.py, the Bay Area flight-path page.

The page states three kinds of fact about each city - a route is overhead, how
low the aircraft are, how much of the city the noise map covers - and every one
is a geometry calculation that returns a plausible number when it is wrong.
These pin the calculations on shapes small enough to work out by hand, and pin
the invariants by breaking the REAL inputs one way at a time: a mis-paired
shapefile record, a picture one tile out of place, a missing city.

They also hold the defects found building it on 2026-10-02, each of which
printed a confident sentence: a pruned distance read as "overhead" for every
later route; "the runway is inside the city" inferred from a low height
(Alameda), then from a threshold 126 m over a generalised boundary (Santa
Clara); and a noise cross-check that failed a correctly placed picture because
BTS maps land only. And the eight a review found before the first commit: a
map that drew departures further than the table read them, shading credited to
the NEAREST airfield (San Carlos, for San Francisco's approach coming ashore
at Foster City), a picture that vanished at the address without its slash.

Offline only. The Census zips are not needed: the checked-in inputs are.
"""

import copy
import importlib.util
import json
import math
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location('build_bay_area_page', REPO_ROOT / 'scripts' / 'build_bay_area_page.py')
bay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bay)

# A square "city" about 4.4 km across, and a hole in its middle.
SQUARE = [[-122.02, 37.48], [-121.97, 37.48], [-121.97, 37.52], [-122.02, 37.52], [-122.02, 37.48]]
HOLE = [[-122.00, 37.495], [-122.00, 37.505], [-121.99, 37.505], [-121.99, 37.495], [-122.00, 37.495]]


def approach(lat, lon, bearing_from_threshold, km, glide=3.0):
    far = bay.destination(lat, lon, bearing_from_threshold, km)
    return {
        'airport': 'TST',
        'runway': '09',
        'glide': glide,
        'line': [(lat, lon), far],
        'points': bay.densify([(lat, lon), far]),
    }


# ---- geometry --------------------------------------------------------------


def test_inside_is_even_odd_so_a_hole_is_outside():
    assert bay.inside([SQUARE], -122.01, 37.50)
    assert not bay.inside([SQUARE], -122.03, 37.50)
    assert not bay.inside([SQUARE, HOLE], -121.995, 37.50)
    assert bay.inside([SQUARE, HOLE], -122.01, 37.50)


def test_area_is_worked_out_in_kilometres_and_a_hole_reduces_it():
    width = 0.05 * 111.32 * math.cos(math.radians(bay.LAT0))
    height = 0.04 * 110.574
    assert bay.area_km2([SQUARE]) == pytest.approx(width * height, rel=1e-6)
    # The hole winds the other way, as a shapefile's holes do, so it nets out.
    hole = 0.01 * 111.32 * math.cos(math.radians(bay.LAT0)) * 0.01 * 110.574
    assert bay.area_km2([SQUARE, HOLE]) == pytest.approx(width * height - hole, rel=1e-6)


def test_simplify_drops_points_on_a_straight_edge_and_keeps_corners():
    edge = [[-122.02 + 0.005 * i, 37.48] for i in range(11)]
    ring = edge + [[-121.97, 37.52], [-122.02, 37.52], [-122.02, 37.48]]
    out = bay.simplify(ring, bay.SIMPLIFY_DEG)
    assert out == [[-122.02, 37.48], [-121.97, 37.48], [-121.97, 37.52], [-122.02, 37.52], [-122.02, 37.48]]


def test_distance_is_zero_inside_and_measured_outside():
    shape = bay.Shape([SQUARE])
    assert shape.distance(-122.0, 37.5) == 0.0
    # 0.01 degrees of latitude north of the top edge.
    assert shape.distance(-122.0, 37.53) == pytest.approx(0.01 * 110.574, rel=1e-6)


def test_a_pruned_distance_comes_back_as_the_limit_never_as_zero():
    shape = bay.Shape([SQUARE])
    assert shape.distance(-121.0, 37.5, best=0.5) == 0.5


def test_the_tile_arithmetic_agrees_with_the_textbook_formula():
    # Worked the other way: the standard slippy-map formula with log(tan + sec).
    lat, lon, z = 37.6213, -122.379, bay.TILE_ZOOM
    n = 2**z
    x = (lon + 180) / 360 * n
    y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
    gx, gy = bay.global_px(lon, lat)
    assert (gx / bay.TILE, gy / bay.TILE) == pytest.approx((x, y), abs=1e-9)
    assert (int(x), int(y)) == (327, 792)  # the tile over San Francisco airport at zoom 11
    assert bay.lonlat_of(gx, gy) == pytest.approx((lon, lat), abs=1e-9)


# ---- what the routes say about a place --------------------------------------


def test_an_approach_overhead_gives_the_lowest_height_on_the_glide_path():
    # A threshold 5 km east of the square's east edge, approached from the west:
    # the line enters the square 5 km out and leaves it about 9.4 km out.
    east_edge_lon = -121.97
    thr_lon = east_edge_lon + 5.0 / (111.32 * math.cos(math.radians(37.5)))
    m = bay.measure(bay.Shape([SQUARE]), [approach(37.5, thr_lon, 270, 15)], [])
    want = 5.0 * math.tan(math.radians(3.0)) / bay.FT_KM
    assert m['approaches']['TST 09'] == pytest.approx(want, rel=0.02)
    assert m['nearest_km'] == 0.0


def test_a_route_that_misses_is_not_overhead_and_its_distance_is_reported():
    # Parallel to the top edge, 2 km north of it.
    lat = 37.52 + 2.0 / 110.574
    m = bay.measure(bay.Shape([SQUARE]), [approach(lat, -121.90, 270, 15)], [])
    assert m['approaches'] == {}
    assert m['nearest_km'] == pytest.approx(2.0, abs=0.02)
    assert m['nearest'] == 'TST 09 approach'


def test_once_one_route_is_overhead_a_distant_route_is_still_not():
    # The defect: `nearest` reaches 0 with the first route, and the pruning in
    # Shape.distance then handed 0 back for every later point, however far.
    over = approach(37.5, -121.90, 270, 15)
    far = {'airport': 'FAR', 'name': 'AWAY1', 'line': [(38.5, -121.0), (38.6, -121.0)]}
    far['points'] = bay.densify(far['line'])
    m = bay.measure(bay.Shape([SQUARE]), [over], [far])
    assert 'TST 09' in m['approaches']
    assert m['departures'] == []


def test_a_line_is_cut_at_a_distance_along_it_and_a_short_one_is_left_alone():
    line = [(37.5, -122.0), (37.5, -121.0)]  # about 88 km due east
    cut = bay.clip_line(line, 30.0)
    assert cut[0] == line[0] and len(cut) == 2
    assert bay.densify(cut)[-1][2] == pytest.approx(30.0, abs=0.01)
    assert bay.clip_line(line, 500.0) == line


def test_a_departure_is_drawn_exactly_as_far_as_the_table_reads_it():
    # The defect: the table read the first 30 km and the map drew the whole
    # route, so six cities had a line across them and "No" in their row.
    runway = {'thr': [37.5, -122.0], 'true_brg': 90.0, 'glide_deg': 3.0}
    record = {
        'airports': {
            code: {
                'runways': {'09': runway},
                'departures': [{'name': 'FAR1', 'runways': ['09'], 'waypoints': [[37.5, -121.0]]}],
            }
            for code in bay.AIRPORTS
        }
    }
    _, departures, _ = bay.routes(record)
    for dep in departures:
        assert bay.densify(dep['line'])[-1][2] == pytest.approx(bay.DEPARTURE_KM, abs=0.01)
        assert dep['points'][-1][2] == pytest.approx(bay.DEPARTURE_KM, abs=0.01)


def test_a_runway_with_no_published_glide_angle_is_not_drawn():
    record = {
        'airports': {
            code: {
                'runways': {
                    '09': {'thr': [37.5, -122.0], 'true_brg': 90.0, 'glide_deg': 3.0},
                    '27': {'thr': [37.5, -121.97], 'true_brg': 270.0, 'glide_deg': None},
                },
                'departures': [
                    {'name': 'COAST1', 'runways': ['09'], 'waypoints': [[37.5, -121.8]]},
                    {'name': 'RADAR1', 'runways': ['09'], 'waypoints': []},
                ],
            }
            for code in bay.AIRPORTS
        }
    }
    approaches, departures, undrawn = bay.routes(record)
    assert [(r['airport'], r['runway']) for r in approaches] == [(c, '09') for c in bay.AIRPORTS]
    assert undrawn == [f'{c} 27' for c in bay.AIRPORTS]
    # A departure that is radar vectors from the runway has no line to draw.
    assert {r['name'] for r in departures} == {'COAST1'}
    # 3,000 ft on a 3 degree path is 17.45 km from the threshold, back along the approach.
    first = approaches[0]
    assert first['points'][-1][2] == pytest.approx(3000 * bay.FT_KM / math.tan(math.radians(3)), rel=1e-6)
    assert first['line'][1][1] < first['line'][0][1]  # runway 09 is approached from the west


# ---- arrivals (added 2026-10-06) ---------------------------------------------

AT = {'min_ft': 6000, 'max_ft': 6000}


def alt(lo=None, hi=None):
    return {'min_ft': lo, 'max_ft': hi}


def test_an_arrival_is_drawn_from_where_the_faa_first_allows_10000_ft_or_lower():
    # SERFR4's real profile: nothing at SERFR, a floor of 20,000 at NRRLI,
    # 10,000-15,000 at EPICK, a floor of 8,000 at FOLET.
    assert bay.arrival_start([None, alt(20000), alt(10000, 15000), alt(8000)]) == 2
    # A ceiling alone counts when no floor is published: the FAA allows lower.
    assert bay.arrival_start([alt(hi=13000), alt(hi=9000)]) == 1
    # A fix with no published altitude never starts a line, and nothing low means nothing drawn.
    assert bay.arrival_start([None, None]) == 2
    assert bay.arrival_start([alt(12000), alt(11000, 15000)]) == 2


def arrival_record(arrivals, transitions):
    """Runway 09 drawn (3 degrees), 27 not (no glide angle); the same at all three airports."""
    return {
        'airports': {
            code: {
                'ref': [37.5, -121.985],
                'runways': {
                    '09': {'thr': [37.5, -122.0], 'true_brg': 90.0, 'glide_deg': 3.0},
                    '27': {'thr': [37.5, -121.97], 'true_brg': 270.0, 'glide_deg': None},
                },
                'departures': [],
                'arrivals': arrivals,
                'approach_transitions': transitions,
            }
            for code in bay.AIRPORTS
        }
    }


A, B, C, D = [37.9, -121.6], [37.7, -121.7], [37.5, -122.3], [37.5, -121.6]


def star(name, fixes, vectored=False):
    pts = {'A': A, 'B': B}
    return {
        'name': name,
        'runway': 'ALL',
        'runways': ['09', '27'],
        'waypoints': [pts[f] for f in fixes],
        'fixes': list(fixes),
        'altitudes': [AT] * len(fixes),
        'vectored': vectored,
    }


def transition(approach, runway, end):
    return {
        'approach': approach,
        'runway': runway,
        'transition': 'B',
        'waypoints': [B, {'C': C, 'D': D}[end]],
        'fixes': ['B', end],
        'altitudes': [AT, alt(3000)],
        'vectored': False,
    }


def test_an_arrival_joins_the_transition_from_where_it_ends_and_only_to_a_drawn_final():
    record = arrival_record([star('JOIN1', 'AB')], [transition('I09', '09', 'C'), transition('I27', '27', 'D')])
    lines = bay.arrival_routes(record)
    assert {tuple(f for f, _, _ in r['fixes']) for r in lines} == {('A', 'B', 'C')}
    assert len(lines) == len(bay.AIRPORTS)


def test_an_arrival_that_ends_in_vectors_is_not_joined_to_anything():
    record = arrival_record([star('VECT1', 'AB', vectored=True)], [transition('I09', '09', 'C')])
    assert {tuple(f for f, _, _ in r['fixes']) for r in bay.arrival_routes(record)} == {('A', 'B')}


def test_approaches_that_share_a_transition_draw_one_line():
    # The ILS and RNAV approaches to one runway often share theirs fix for fix.
    record = arrival_record([star('JOIN1', 'AB')], [transition('I09', '09', 'C'), transition('R09', '09', 'C')])
    assert len(bay.arrival_routes(record)) == len(bay.AIRPORTS)


def arrival_over(fixes):
    line = [p for _, p, _ in fixes]
    return {'airport': 'TST', 'name': 'ARR1', 'fixes': fixes, 'line': line, 'points': bay.densify(line)}


def test_an_arrival_overhead_gives_the_lowest_published_altitude_at_a_fix_inside():
    fixes = [
        ('OUT1', (37.5, -122.10), alt(8000)),
        ('IN1', (37.5, -122.00), AT),
        ('IN2', (37.5, -121.98), alt(4000)),
        ('OUT2', (37.5, -121.90), alt(2000)),  # lower, but outside the city: not its figure
    ]
    m = bay.measure(bay.Shape([SQUARE]), [], [], [arrival_over(fixes)])
    assert m['arrivals'] == {'TST ARR1': ('IN2', alt(4000))}
    assert m['nearest_km'] == 0.0


def test_an_arrival_crossing_a_city_between_fixes_is_overhead_with_no_altitude():
    # Between fixes the FAA publishes nothing, and nothing is drawn in.
    fixes = [('W', (37.5, -122.10), alt(8000)), ('E', (37.5, -121.90), alt(6000))]
    m = bay.measure(bay.Shape([SQUARE]), [], [], [arrival_over(fixes)])
    assert m['arrivals'] == {'TST ARR1': None}
    assert bay.arrival_cell(city(arrivals=m['arrivals'])) == 'Yes: TST ARR1'


def test_an_arrival_altitude_is_worded_by_what_was_published():
    assert bay.altitude_words(alt(4000)) == '4,000 ft or above'
    assert bay.altitude_words(AT) == '6,000 ft'
    assert bay.altitude_words(alt(hi=13000)) == '13,000 ft or below'
    assert bay.altitude_words(alt(10000, 14000)) == 'between 10,000 and 14,000 ft'
    cell = bay.arrival_cell(city(arrivals={'SFO SERFR4': ('SIDBY', alt(4000)), 'SJC RAZRR5': None}))
    assert cell == 'Yes: SFO SERFR4; SJC RAZRR5. Published altitude at SIDBY, inside the city: 4,000 ft or above'
    # Two routes with a published altitude inside: the city's figure is the LOWER one.
    two = {'SFO SERFR4': ('SIDBY', alt(4000)), 'SFO DYAMD5': ('FRELY', alt(8000))}
    assert bay.arrival_cell(city(arrivals=two)).endswith('at SIDBY, inside the city: 4,000 ft or above')
    assert bay.nearest_cell(city(arrivals={'SFO SERFR4': None})) == 'Overhead'


# ---- what the table prints ---------------------------------------------------


def city(**over):
    base = {
        'approaches': {},
        'departures': [],
        'arrivals': {},
        'nearest_km': 3.0,
        'nearest': 'SFO 28L approach',
        'airports_inside': [],
        'noise_pct': 0.0,
        'airfield': None,
    }
    return {**base, **over}


def test_the_airport_is_inside_a_city_only_by_its_reference_point():
    # Never by a low height, and never by a threshold: the Census outline puts
    # San Jose's runway 12R threshold 126 m inside Santa Clara.
    assert 'airport is inside the city' in bay.approach_cell(city(approaches={'SJC 30L': 0.0}, airports_inside=['SJC']))
    beside = bay.approach_cell(city(approaches={'SJC 12R': 0.0}))
    assert 'under 500 ft above the runway, beside the airport' in beside and 'inside the city' not in beside


def test_a_height_is_rounded_to_the_nearest_hundred_feet():
    # "Above the runway": the figure is height on the glide path, not above a hill.
    assert bay.approach_cell(city(approaches={'SFO 28L': 1460.0, 'SFO 28R': 1502.0})) == (
        'Yes: SFO 28L, SFO 28R. Lowest about 1,500 ft above the runway'
    )
    assert bay.approach_cell(city()) == 'No'


def test_the_nearest_route_is_overhead_a_distance_or_too_close_to_call():
    assert bay.nearest_cell(city(departures=['SFO GAPP7'])) == 'Overhead'
    assert bay.nearest_cell(city(nearest_km=3.0)) == '1.9 mi (SFO 28L approach)'
    # 0.0 mi beside "No" would read as overhead-and-not; the boundary is not that exact.
    assert bay.nearest_cell(city(nearest_km=0.03)).startswith('Under 0.1 mi')


def test_departures_are_grouped_by_airport():
    assert bay.departure_cell(city(departures=['OAK CNDEL5', 'SFO GAPP7', 'SFO MOLEN9'])) == (
        'Yes: OAK CNDEL5; SFO GAPP7, MOLEN9'
    )


def test_the_noise_share_does_not_round_a_little_to_none_or_nearly_all_to_all():
    assert bay.noise_cell({'noise_pct': 0.0}) == 'None'
    assert bay.noise_cell({'noise_pct': 0.04}) == 'Under 1%'
    assert bay.noise_cell({'noise_pct': 51.4}) == '51%'
    assert bay.noise_cell({'noise_pct': 99.7}) == 'Over 99%'
    assert bay.noise_cell({'noise_pct': 100.0}) == '100%'


def test_a_departure_name_reaches_the_page_escaped():
    assert bay.departure_cell(city(departures=['SFO A<b>&1'])) == 'Yes: SFO A&lt;b&gt;&amp;1'


def test_an_airfield_name_is_spelt_out_and_a_cut_off_one_loses_its_fragment():
    assert bay.airfield_name({'name': 'LIVERMORE MUNI'}) == 'Livermore Municipal'
    assert bay.airfield_name({'name': 'SAN FRANCISCO INTL'}) == 'San Francisco International'
    # Exactly the width of the FAA's name field, so the last word is a fragment.
    assert bay.airfield_name({'name': 'REID-HILLVIEW OF SANTA CLARA C'}) == 'Reid-Hillview of Santa Clara'


def test_a_city_under_one_per_cent_names_no_airfield_and_an_unowned_patch_says_so():
    lvk = {'ident': 'KLVK', 'name': 'LIVERMORE MUNI'}
    assert bay.airfield_cell(city(noise_pct=0.4, airfield=lvk)) == ''
    assert bay.airfield_cell(city(noise_pct=36.0, airfield=lvk)) == 'Livermore Municipal'
    assert bay.airfield_cell(city(noise_pct=36.0, airfield=None)) == 'Not identified'


# ---- the real inputs, and the invariants that guard them --------------------


@pytest.fixture(scope='module')
def real():
    data, record = bay.load()
    return data, record, bay.facts(data, record)


def test_the_real_inputs_pass_their_own_invariants(real):
    data, _, facts = real
    assert bay.invariants(data, facts) == []
    assert len(facts['cities']) == sum(n for _, n in bay.COUNTIES.values()) == 50


def test_a_missing_city_fails_the_county_count(real):
    data, record, _ = real
    short = copy.deepcopy(data)
    short['places'] = [p for p in short['places'] if p['name'] != 'Colma']
    fails = bay.invariants(short, bay.facts(short, record))
    assert any('San Mateo County: 19' in f for f in fails)


def test_a_shape_paired_with_the_wrong_attributes_fails_the_area_check(real):
    # What a reader one record out of step would produce.
    data, record, _ = real
    swapped = copy.deepcopy(data)
    by_name = {p['name']: p for p in swapped['places']}
    by_name['Colma']['rings'], by_name['Fremont']['rings'] = by_name['Fremont']['rings'], by_name['Colma']['rings']
    fails = bay.invariants(swapped, bay.facts(swapped, record))
    assert any(f.startswith('Colma: the polygon is') for f in fails)
    assert any(f.startswith('Fremont: the polygon is') for f in fails)


def test_a_picture_one_tile_out_of_place_fails_against_the_routes(real):
    data, record, _ = real
    shifted = copy.deepcopy(data)
    shifted['frame']['px'] = [v + bay.TILE * (i % 2 == 0) for i, v in enumerate(shifted['frame']['px'])]
    fails = bay.invariants(shifted, bay.facts(shifted, record))
    # Two separate guards, and each must fire by itself: asserting "mis-placed"
    # alone passed with either one deleted.
    assert any('best-covered approach' in f for f in fails)
    assert any(f.startswith('runway thresholds off the noise picture') for f in fails)


def test_a_picture_that_is_not_the_one_recorded_fails(real):
    data, _, facts = real
    other = copy.deepcopy(data)
    other['noise']['sha256'] = '0' * 64
    fails = bay.invariants(other, facts)
    # Two guards again, each named: the content, and the name that carries it.
    assert any('is not the picture' in f for f in fails)
    assert any('is not named after its own content' in f for f in fails)


def test_shading_belongs_to_the_airfield_in_its_patch_not_the_nearest_one(real):
    # Read off the checked-in picture, so a new BTS edition may move these.
    # Foster City's shading is San Francisco's runway 28 approach coming
    # ashore: no airfield is in that patch, and the NEAREST one is San Carlos.
    by_name = {c['name']: c for c in real[2]['cities']}
    assert by_name['Foster City']['airfield']['ident'] == 'KSFO'
    assert by_name['Livermore']['airfield']['ident'] == 'KLVK'
    assert by_name['Milpitas']['airfield']['ident'] == 'KSJC'
    # Fremont's shading is San Jose's runway 12 approach coming ashore from
    # the bay: a patch with no airfield in it, owned through the approach
    # drawn across it. Without that rule most of Fremont's shading is unowned.
    assert by_name['Fremont']['airfield']['ident'] == 'KSJC'


def test_every_shaded_pixel_a_city_is_sampled_at_lies_in_a_labelled_patch(real):
    # The half-size labelling and the full-size sampling must agree on where
    # a pixel is: a resize() to a rounded size left a few samples in patch 0.
    data, _, facts = real
    noise = bay.Noise(facts['frame'], bay.PAGE_DIR / data['noise']['file'])
    for name in ('Dublin', 'Pleasanton', 'San Jose', 'Sunnyvale'):
        place = next(p for p in data['places'] if p['name'] == name)
        _, sample = noise.share_pct(place['rings'])
        assert sample and all(noise.patch_at(lon, lat) for lon, lat in sample), name


def test_two_airports_with_no_departures_fail_though_the_total_is_healthy(real):
    # San Francisco alone has more coded departures than the other two together.
    data, record, _ = real
    thin = copy.deepcopy(record)
    for code in ('OAK', 'SJC'):
        for dep in thin['airports'][code]['departures']:
            dep['waypoints'] = []
    fails = bay.invariants(data, bay.facts(data, thin))
    assert any(f.startswith('OAK: ') and '0 departures' in f for f in fails)
    assert any(f.startswith('SJC: ') and '0 departures' in f for f in fails)


def test_a_key_that_no_longer_shows_the_picture_s_colours_fails(real, monkeypatch):
    # The key under the map is drawn from NOISE_SCALE_BTS in index.html, New
    # York's legend holder. Editing it must not re-colour this page's key
    # against an unchanged picture in silence.
    data, _, facts = real
    monkeypatch.setattr(bay.check_noise_legend, 'scale_from_index', lambda name: [(45, '#111111'), (50, '#222222')])
    assert any('the key under the map does not show' in f for f in bay.invariants(data, facts))


def test_a_superseded_picture_left_in_the_folder_fails(real):
    data, _, facts = real
    stale = bay.PAGE_DIR / f'{bay.NOISE_PREFIX}0000000000.png'
    stale.write_bytes(b'not a picture')
    try:
        assert any('superseded pictures' in f for f in bay.invariants(data, facts))
    finally:
        stale.unlink()


def test_the_map_draws_no_departure_beyond_what_the_table_reads(real):
    for dep in real[2]['departures']:
        assert bay.densify(dep['line'])[-1][2] <= bay.DEPARTURE_KM + 0.01


def test_every_real_arrival_starts_where_10000_ft_is_allowed_and_ends_near_its_airport(real):
    _, record, facts = real
    assert facts['arrivals'], 'no arrival drawn from the real record'
    for r in facts['arrivals']:
        first = r['fixes'][0][2]
        assert first is not None and bay.floor_of(first) <= bay.ARRIVAL_TOP_FT, r['name']
        ref = record['airports'][r['airport']]['ref']
        assert bay.build_us_flight_paths.distance_km(ref, r['line'][-1]) <= bay.ARRIVAL_END_KM, r['name']


def test_an_arrival_that_ends_far_from_its_airport_fails(real):
    data, _, facts = real
    bad = copy.deepcopy(facts)
    bad['arrivals'][0]['line'][-1] = (38.9, -121.9)
    assert any('the drawn arrival ends' in f for f in bay.invariants(data, bad))


def test_every_drawn_threshold_is_on_the_picture_though_not_every_approach(real):
    # BTS paints land only: San Francisco's main approach is over the bay, so
    # "every approach lies on the picture" is false of a correctly placed one.
    _, _, facts = real
    assert facts['off_noise'] == []
    assert all(share >= bay.APPROACH_ON_NOISE for share in facts['on_noise'].values())


# ---- the page ---------------------------------------------------------------


@pytest.fixture(scope='module')
def page():
    return (REPO_ROOT / 'bay-area' / 'index.html').read_text(encoding='utf-8')


def test_the_page_draws_arrivals_and_no_longer_says_it_does_not(page, real):
    # Until 2026-10-06 the notes said arrivals before the final were not drawn.
    assert 'Arrivals further out are not drawn' not in page
    assert '<th scope="col">Arrival route overhead</th>' in page
    assert page.count('stroke-dasharray="5 3"') == len(real[2]['arrivals'])
    rows = re.findall(r'<tr><th scope="row">.*?</tr>', page)
    assert all(r.count('<td') == 7 for r in rows), 'a row lost or gained a cell'


def test_the_page_lists_every_city_once(page, real):
    names = re.findall(r'<tr><th scope="row">(.*?)</th>', page)
    assert len(names) == len(set(names)) == 50
    assert set(names) == {c['name'] for c in real[2]['cities']}


def test_the_page_carries_the_faa_disclaimer_its_licence_requires(page):
    assert 'Coded Instrument Flight Procedures' in page
    assert '"as is", without warranty of any kind' in page
    assert 'not for navigation' in page


def test_the_page_prints_no_decibel_figure_and_no_score(page):
    # The 2022 tile service publishes no legend, so the band values are unverified.
    text = re.sub(r'<[^>]+>', ' ', page)
    assert not re.search(r'\bdB\b|decibel', text)
    assert not re.search(r'\d(\.\d)?\s*/\s*10\b', text)


def test_the_page_repeats_what_bts_says_its_map_is_not_for(page):
    assert 'should not be used to evaluate noise at an individual location' in page


def test_the_page_names_the_cycle_the_record_holds(page):
    record = json.loads((REPO_ROOT / 'data' / 'us-flight-procedures.json').read_text(encoding='utf-8'))
    assert f'cycle {record["cycle"]}, effective {record["effective"]}' in page


def test_the_picture_is_asked_for_by_a_root_path_and_named_after_its_content(page, real):
    # `/bay-area` with no slash is served in place, with no redirect, so a
    # relative name resolved to the site root and the shading vanished.
    hrefs = re.findall(r'<image href="([^"]+)"', page)
    name = real[0]['noise']['file']
    assert hrefs == [f'/bay-area/{name}']
    assert name == f'{bay.NOISE_PREFIX}{real[0]["noise"]["sha256"][:10]}.png'
    assert (REPO_ROOT / 'bay-area' / name).exists()
    assert f'{bay.SITE}/bay-area/{bay.SHARE_NAME}' in page and (REPO_ROOT / 'bay-area' / bay.SHARE_NAME).exists()


def test_the_page_has_no_em_dash_and_no_inline_script(page):
    assert '—' not in page
    # The one script is GoatCounter, pinned to count.v5.js with its SRI hash since 2026-10-07
    # (tests/test_goatcounter_pinned.py holds every page to the same tag).
    assert len(re.findall(r'<script\b', page)) == 1 and 'gc.zgo.at/count.v5.js' in page


def test_any_shading_ranks_above_none():
    """'Under 1%' above 'None' (audit 2026-10-05 M-19): rounded to 1 dp, 0.04% tied
    with 0.0 and the tie fell to route distance, under a heading promising the
    noise-map order."""
    cities = [
        {'name': 'Unshaded, route overhead', 'noise_pct': 0.0, 'nearest_km': 0.0},
        {'name': 'Barely shaded, route far', 'noise_pct': 0.04, 'nearest_km': 5.0},
    ]
    assert [c['name'] for c in bay.order(cities)] == ['Barely shaded, route far', 'Unshaded, route overhead']
