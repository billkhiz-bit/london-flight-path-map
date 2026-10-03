"""The Bay Area's ZIP table: data/us-bayarea-zips.json and its builder.

The rows below are REAL: copied verbatim from the three Census files on
2026-10-04 (the ZCTA gazetteer and the two 2020 relationship files), four ZIPs
chosen because each is a different case. A fixture written by hand would only
prove the builder agrees with its author.

  94301  wholly inside Palo Alto
  95014  44% Cupertino, and MORE of it in no city at all (the hills)
  94074  in no city (San Gregorio)
  94128  the airport's own ZIP: 9% South San Francisco, the rest in no city
"""

import copy
import json
import os
import sys

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, os.path.join(REPO_ROOT, 'scripts'))

import build_bayarea_zips as zips  # noqa: E402

GAZETTEER = [
    'GEOID\tALAND\tAWATER\tALAND_SQMI\tAWATER_SQMI\tINTPTLAT\tINTPTLONG                                                                                                                                  ',
    '94074\t59889346\t66452\t23.123\t0.026\t37.331714\t-122.341466                                                                                                                                                 ',
    '94128\t8687482\t0\t3.354\t0.\t37.621955\t-122.383797                                                                                                                                                          ',
    '94301\t6138863\t0\t2.37\t0.\t37.444218\t-122.149855                                                                                                                                                           ',
    '95014\t64388214\t339868\t24.86\t0.131\t37.308354\t-122.081882                                                                                                                                                 ',
]

COUNTY = [
    'OID_ZCTA5_20|GEOID_ZCTA5_20|NAMELSAD_ZCTA5_20|AREALAND_ZCTA5_20|AREAWATER_ZCTA5_20|MTFCC_ZCTA5_20|CLASSFP_ZCTA5_20|FUNCSTAT_ZCTA5_20|OID_COUNTY_20|GEOID_COUNTY_20|NAMELSAD_COUNTY_20|AREALAND_COUNTY_20|AREAWATER_COUNTY_20|MTFCC_COUNTY_20|CLASSFP_COUNTY_20|FUNCSTAT_COUNTY_20|AREALAND_PART|AREAWATER_PART',
    '221704258476598|94074|ZCTA5 94074|59889346|66452|G6350|B5|S|27590351392772|06081|San Mateo County|1161922036|757123906|G4020|H1|A|59889346|66452',
    '221704258476645|94128|ZCTA5 94128|8687478|0|G6350|B5|S|27590351392772|06081|San Mateo County|1161922036|757123906|G4020|H1|A|8687478|0',
    '221704258476657|94301|ZCTA5 94301|6138863|0|G6350|B5|S|27590154292295|06085|Santa Clara County|3343892719|33595850|G4020|H1|A|6138863|0',
    '221704258476956|95014|ZCTA5 95014|64388215|339868|G6350|B5|S|27590154292295|06085|Santa Clara County|3343892719|33595850|G4020|H1|A|64388215|339868',
]

PLACE = [
    'OID_ZCTA5_20|GEOID_ZCTA5_20|NAMELSAD_ZCTA5_20|AREALAND_ZCTA5_20|AREAWATER_ZCTA5_20|MTFCC_ZCTA5_20|CLASSFP_ZCTA5_20|FUNCSTAT_ZCTA5_20|OID_PLACE_20|GEOID_PLACE_20|NAMELSAD_PLACE_20|AREALAND_PLACE_20|AREAWATER_PLACE_20|MTFCC_PLACE_20|CLASSFP_PLACE_20|FUNCSTAT_PLACE_20|AREALAND_PART|AREAWATER_PART',
    '221704258476598|94074|ZCTA5 94074|59889346|66452|G6350|B5|S|||||||||59889346|66452',
    '221704258476645|94128|ZCTA5 94128|8687478|0|G6350|B5|S|||||||||7947319|0',
    '221704258476645|94128|ZCTA5 94128|8687478|0|G6350|B5|S|27890351406889|0673262|South San Francisco city|23835620|54315204|G4110|C1|A|740159|0',
    '221704258476657|94301|ZCTA5 94301|6138863|0|G6350|B5|S|27890154306299|0655282|Palo Alto city|62408630|4940291|G4110|C1|A|6138863|0',
    '221704258476956|95014|ZCTA5 95014|64388215|339868|G6350|B5|S|||||||||35475677|337348',
    '221704258476956|95014|ZCTA5 95014|64388215|339868|G6350|B5|S|27890154306286|0617610|Cupertino city|29338791|2520|G4110|C1|A|28594585|2520',
    '221704258476956|95014|ZCTA5 95014|64388215|339868|G6350|B5|S|27890154306300|0668000|San Jose city|461691712|8089813|G4110|C1|A|190042|0',
    '221704258476956|95014|ZCTA5 95014|64388215|339868|G6350|B5|S|27890154306306|0677000|Sunnyvale city|57135716|1858933|G4110|C1|A|127911|0',
]


def places():
    with open(zips.PLACES, encoding='utf-8') as fh:
        return json.load(fh)['places']


def derived(held=None, county=None):
    return zips.derive(GAZETTEER, list(zips.rows(county or COUNTY)), list(zips.rows(PLACE)), held or places())


def test_a_zip_wholly_inside_a_city_is_that_city_with_its_point():
    assert derived()['94301'] == {'lat': 37.44422, 'lon': -122.14986, 'county': 'Santa Clara', 'place': 'Palo Alto', 'share': 1.0}


def test_the_land_in_no_city_is_never_the_place():
    # More of 95014 is in no city than in Cupertino, and that row has an empty
    # place GEOID. Taking "the largest row" named nothing; the first rule
    # (half or more) named nothing either. Cupertino is the answer, with its share.
    record = derived()['95014']
    assert (record['place'], record['share']) == ('Cupertino', 0.44)


def test_a_zip_with_no_city_names_none():
    record = derived()['94074']
    assert record['place'] is None and record['share'] is None
    assert record['county'] == 'San Mateo'


def test_a_small_share_is_named_with_its_share_not_hidden():
    record = derived()['94128']
    assert (record['place'], record['share']) == ('South San Francisco', 0.09)


def test_a_place_the_map_does_not_hold_is_not_named_and_a_sliver_rounds_away():
    # Without Cupertino the next held places are San Jose and Sunnyvale, each a
    # fraction of one percent of 95014: a sliver that rounds to nothing names no city.
    held = [p for p in places() if p['name'] != 'Cupertino']
    record = derived(held=held)['95014']
    assert record['place'] is None and record['share'] is None


def test_a_zip_mostly_in_another_county_is_left_out():
    # The same real row, with a larger part of 94301 put in a county that is not one of the four.
    head, *body = COUNTY
    row = next(r for r in body if r.split('|')[1] == '94301').split('|')
    cols = head.split('|')
    other = row[:]
    other[cols.index('GEOID_COUNTY_20')] = '06087'
    other[cols.index('AREALAND_PART')] = str(int(row[cols.index('AREALAND_PART')]) * 2)
    table = derived(county=[head, *body, '|'.join(other)])
    assert '94301' not in table and '95014' in table


def checked_in():
    with open(zips.OUT, encoding='utf-8') as fh:
        return json.load(fh)['zips']


def test_the_checked_in_table_is_sound_and_agrees_with_the_outlines():
    problems, (agree, tested) = zips.sanity(checked_in())
    assert problems == []
    assert tested >= 80, 'the outline cross-check compared too few ZIPs to mean anything'
    assert agree / tested >= zips.POINT_CHECK_FLOOR


def test_well_known_zips_land_in_their_cities():
    table = checked_in()
    for code, city in (('94301', 'Palo Alto'), ('94102', 'San Francisco'), ('94612', 'Oakland'), ('95110', 'San Jose')):
        assert table[code]['place'] == city, f'{code} should be {city}, is {table[code]["place"]}'


def test_a_table_paired_with_the_wrong_cities_fails_the_outline_check():
    table = copy.deepcopy(checked_in())
    for record in table.values():
        if record['share'] and record['share'] >= zips.POINT_CHECK_SHARE:
            record['place'] = 'Gilroy'
    problems, _points = zips.sanity(table)
    assert any('fall inside the city' in p for p in problems)


def test_a_short_table_fails():
    table = dict(list(checked_in().items())[:40])
    problems, _points = zips.sanity(table)
    assert any('ZIP areas' in p for p in problems)
