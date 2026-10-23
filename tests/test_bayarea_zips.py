"""The Bay Area's ZIP table: data/us-bayarea-zips.json, the Lambda's BAYAREA_ZIPS, and their one builder.

A ZIP is named by where its RESIDENTS live (Bill, 2026-10-23), and scored as a city when half or more of them
live in one of the 50. The rows and counts below are REAL, copied from the Census files on 2026-10-23 (the ZCTA
gazetteer, the 2020 ZCTA-to-county and ZCTA-to-block relationship files, and the 2020 redistricting file's
blocks), one ZIP per case. A fixture written by hand would only prove the builder agrees with its author.

  94301  wholly Palo Alto
  94010  the case that set the rule: its LAND is mostly Hillsborough's, 71% of its residents live in Burlingame
  95014  "44% Cupertino" by land (the hills), 96% by residents
  94546  98% in Castro Valley, an unincorporated community: named, never scored
  94074  282 residents, none in a place the map holds (San Gregorio)
"""

import copy
import json
import os
import sys
from collections import Counter

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, os.path.join(REPO_ROOT, 'scripts'))

import build_bayarea_zips as zips  # noqa: E402

GAZETTEER = [
    'GEOID\tALAND\tAWATER\tALAND_SQMI\tAWATER_SQMI\tINTPTLAT\tINTPTLONG',
    '94010\t39161641\t2265357\t15.12\t0.875\t37.571918\t-122.375028',
    '94074\t59889346\t66452\t23.123\t0.026\t37.331714\t-122.341466',
    '94301\t6138863\t0\t2.37\t0.\t37.444218\t-122.149855',
    '94546\t41329606\t3969840\t15.957\t1.533\t37.745399\t-122.103127',
    '95014\t64388214\t339868\t24.86\t0.131\t37.308354\t-122.081882',
]

COUNTY = [
    'OID_ZCTA5_20|GEOID_ZCTA5_20|NAMELSAD_ZCTA5_20|AREALAND_ZCTA5_20|AREAWATER_ZCTA5_20|MTFCC_ZCTA5_20|CLASSFP_ZCTA5_20|FUNCSTAT_ZCTA5_20|OID_COUNTY_20|GEOID_COUNTY_20|NAMELSAD_COUNTY_20|AREALAND_COUNTY_20|AREAWATER_COUNTY_20|MTFCC_COUNTY_20|CLASSFP_COUNTY_20|FUNCSTAT_COUNTY_20|AREALAND_PART|AREAWATER_PART',
    '221704258476555|94010|ZCTA5 94010|39154296|2265357|G6350|B5|S|27590351392772|06081|San Mateo County|1161922036|757123906|G4020|H1|A|39154296|2265357',
    '221704258476598|94074|ZCTA5 94074|59889346|66452|G6350|B5|S|27590351392772|06081|San Mateo County|1161922036|757123906|G4020|H1|A|59889346|66452',
    '221704258476657|94301|ZCTA5 94301|6138863|0|G6350|B5|S|27590154292295|06085|Santa Clara County|3343892719|33595850|G4020|H1|A|6138863|0',
    '221704258476753|94546|ZCTA5 94546|41329607|3969840|G6350|B5|S|27590141293924|06001|Alameda County|1910017353|216902808|G4020|H1|A|41329607|3969840',
    '221704258476956|95014|ZCTA5 95014|64388215|339868|G6350|B5|S|27590154292295|06085|Santa Clara County|3343892719|33595850|G4020|H1|A|64388215|339868',
]

# 2020 residents per Census place (None: in no place) in each ZIP area, from block_residents() over the real files.
RESIDENTS = {
    '94010': Counter({'0609066': 31386, '0633798': 11387, None: 1258, '0668252': 10, '0647486': 4}),
    '94546': Counter({'0611964': 45597, '0633000': 1068, None: 22}),
    '94301': Counter({'0655282': 17299}),
    '95014': Counter({'0617610': 60310, '0668000': 1906, None: 369}),
    '94074': Counter({None: 282}),
}

# Three real rows of the ZCTA-to-block file (a Burlingame block and a Hillsborough block of 94010, and a water block
# in no ZIP area) and those blocks as bayarea_blocks.pl_blocks() yields them.
BLOCK_REL = [
    'OID_ZCTA5_20|GEOID_ZCTA5_20|NAMELSAD_ZCTA5_20|AREALAND_ZCTA5_20|AREAWATER_ZCTA5_20|MTFCC_ZCTA5_20|CLASSFP_ZCTA5_20|FUNCSTAT_ZCTA5_20|OID_TABBLOCK_20|GEOID_TABBLOCK_20|NAMELSAD_TABBLOCK_20|AREALAND_TABBLOCK_20|AREAWATER_TABBLOCK_20|MTFCC_TABBLOCK_20|FUNCSTAT_TABBLOCK_20|AREALAND_PART|AREAWATER_PART',
    '221704258476555|94010|ZCTA5 94010|39154296|2265357|G6350|B5|S|210701000920740|060816050001001|Block 1001|31710|0|G5040|S|31710|0',
    '221704258476555|94010|ZCTA5 94010|39154296|2265357|G6350|B5|S|210701000923500|060816056001002|Block 1002|157601|0|G5040|S|157601|0',
    '||||||||210701000923896|060816001002000|Block 2000|0|805387|G5040|S|0|805387',
]
PL = [
    ('060816050001001', '0609066', 273, -122.383823, 37.5960698),
    ('060816056001002', '0633798', 170, -122.3600948, 37.5773614),
    ('060816001002000', None, 0, -122.40, 37.60),
]


def places():
    with open(zips.PLACES, encoding='utf-8') as fh:
        return json.load(fh)['places']


def derived(held=None, county=None, residents=None):
    return zips.derive(GAZETTEER, list(zips.rows(county or COUNTY)), residents or RESIDENTS, held or places())


def test_block_residents_adds_each_block_to_its_zip_in_its_place():
    got = zips.block_residents(list(zips.rows(BLOCK_REL)), PL)
    assert {z: dict(c) for z, c in got.items()} == {'94010': {'0609066': 273, '0633798': 170}}


def test_a_zip_wholly_in_a_city_is_that_city_with_its_point():
    assert derived()['94301'] == {'lat': 37.44422, 'lon': -122.14986, 'county': 'Santa Clara', 'residents': 17299,
                                  'place': 'Palo Alto', 'kind': 'city', 'share': 1.0, 'others': [], 'cityMajority': True}


def test_residents_not_land_name_the_city():
    # 94010's land is mostly Hillsborough's; 71% of its people live in Burlingame. San Mateo's 10 round away.
    r = derived()['94010']
    assert (r['place'], r['share'], r['others'], r['cityMajority']) == ('Burlingame', 0.71, [['Hillsborough', 0.26]], True)


def test_hills_do_not_dilute_a_city():
    r = derived()['95014']
    assert (r['place'], r['share'], r['others']) == ('Cupertino', 0.96, [['San Jose', 0.03]])


def test_a_majority_in_a_community_is_named_but_never_scored():
    r = derived()['94546']
    assert (r['place'], r['kind'], r['share'], r['cityMajority']) == ('Castro Valley', 'cdp', 0.98, False)


def test_residents_in_no_held_place_name_none():
    r = derived()['94074']
    assert (r['place'], r['kind'], r['share'], r['others'], r['cityMajority']) == (None, None, None, [], False)
    assert r['residents'] == 282 and r['county'] == 'San Mateo'


def test_the_exact_ratio_decides_a_majority_not_the_rounded_share():
    # 496 of 1,000 prints as 50% but is not half: the rule reads the ratio
    r = derived(residents={**RESIDENTS, '94301': Counter({'0655282': 496, None: 504})})['94301']
    assert (r['share'], r['cityMajority']) == (0.5, False)


def test_a_place_the_map_does_not_hold_is_never_named():
    # Without Cupertino, 95014's largest held place is San Jose, at 3%: named with its share, not scored
    r = derived(held=[p for p in places() if p['name'] != 'Cupertino'])['95014']
    assert (r['place'], r['share'], r['cityMajority']) == ('San Jose', 0.03, False)


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


def test_the_lambda_holds_the_same_table_as_the_file():
    assert zips.lambda_block_now() == zips.render_lambda(checked_in())


def test_well_known_zips_are_scored_as_their_cities():
    table = checked_in()
    for code, city in (('94301', 'Palo Alto'), ('94102', 'San Francisco'), ('94612', 'Oakland'), ('95110', 'San Jose'),
                       ('94010', 'Burlingame')):
        assert (table[code]['place'], table[code]['cityMajority']) == (city, True), f'{code}: {table[code]}'


def test_a_table_paired_with_the_wrong_cities_fails_the_outline_check():
    table = copy.deepcopy(checked_in())
    for record in table.values():
        if record['cityMajority'] and record['share'] >= zips.POINT_CHECK_SHARE:
            record['place'] = 'Gilroy'
    problems, _points = zips.sanity(table)
    assert any('inside ANOTHER city' in p for p in problems)


def test_a_majority_claimed_for_a_community_fails():
    table = copy.deepcopy(checked_in())
    table['94546']['cityMajority'] = True
    problems, _points = zips.sanity(table)
    assert any('94546' in p and 'not one' in p for p in problems)


def test_a_short_table_fails():
    table = dict(list(checked_in().items())[:40])
    problems, _points = zips.sanity(table)
    assert any('ZIP areas' in p for p in problems)
