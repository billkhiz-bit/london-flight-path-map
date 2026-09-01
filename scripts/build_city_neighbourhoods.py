#!/usr/bin/env python3
"""Build a city's neighbourhood entries for the consumer-site ranking.

WHY THIS SCRIPT EXISTS RATHER THAN A HAND-WRITTEN TABLE.

London's and NYC's neighbourhood entries in `index.html` carry a curated
median price (LONDON_NEIGHBOURHOOD_DETAIL: `price`, in GBP thousands) and a
hand-assigned `crime` modifier on a -2..+1 scale. Those numbers are editorial.
Writing four hundred more of them by hand would repeat the defect this
project has already removed twice: the Ofsted school bands, which turned out
not to reproduce from any published threshold, and the prototype's invented
decibel readings at named locations.

So every number this emits is sourced or absent:

  price      MEDIAN of real HM Land Registry Price Paid transactions for the
             postcode district, over the vintage below. Not an estimate.
  lat/lon    MEAN of live postcode coordinates in that district, from the ONS
             National Statistics Postcode Lookup already on disk for the
             score Lambda's postcode table.
  borough    The Land Registry `district` field on the transactions themselves,
             checked against the city's boroughs in LAD_TO_BOROUGH.
  crime      0 for every entry, and NOT a measurement. There is no honest
             sub-borough crime source: ONS Table C4 publishes at Community
             Safety Partnership level, which for these cities is the
             borough. A modifier invented per neighbourhood would be exactly
             the editorial number this script exists to avoid. The site
             discloses this rather than printing a silent zero.

WHAT A "NEIGHBOURHOOD" IS HERE, STATED PLAINLY.

It is a POSTCODE DISTRICT (outward code: M20, BL1, SK4), labelled with the
Royal Mail locality that most transactions in it use. It is not a ward, not an
MSOA, and not a conservation-area boundary. METHODOLOGY's standing rule is to
say what a number is rather than dress a coarse figure as a fine one, so the
site labels these as postcode districts and names the source.

A district is DROPPED, not estimated, on either of two floors. Every drop is
printed, because a silent cap reads as full coverage.

  MIN_SALES        fewer than 30 transactions - a median drawn from four sales
                   is noise wearing a statistic's clothing.
  MIN_CONTAINMENT  less than half of its live postcodes inside the city
                   publishing it. Transactions are bucketed by Land Registry
                   DISTRICT (a local authority) but published as a POSTCODE
                   DISTRICT (Royal Mail), and those do not nest. WA8 is 4%
                   inside Knowsley and 94% inside Halton, which we do not
                   cover, so it published a Knowsley median under the name
                   "Widnes" at a centroid in Halton - Merseyside's fourth
                   priciest entry, off 32 sales. See DEFAULT_MIN_CONTAINMENT.

`lat/lon` and `postcodes` are computed over the COVERED part of a district
only, so the marker sits in the part the price describes.

SOURCES
  HM Land Registry Price Paid Data (bulk CSV, per calendar year)
    http://prod.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com/pp-<year>.csv
    Contains HM Land Registry data (C) Crown copyright and database right.
    Licensed under the Open Government Licence v3.0.
  ONS National Statistics Postcode Lookup (data/nspl.csv, already on disk)
    Contains OS data (C) Crown copyright and database right; Royal Mail data
    (C) Royal Mail copyright and database right; ONS data (C) Crown copyright.
    Open Government Licence v3.0.

GENERALISED 2026-08-11 from build_manchester_neighbourhoods.py. Greater
Manchester was the only generated city for two days; six more now use the same
path, which produced 448 districts across seven cities in one pass. Its output
for GM is byte-identical to the hand-run it replaced.

USAGE
    python scripts/build_city_neighbourhoods.py --write-index
    python scripts/build_city_neighbourhoods.py --city bristol --write-index
    python scripts/build_city_neighbourhoods.py --years 2025 2026 --min-sales 40

Writes data/<city>-neighbourhoods.json. Re-run when a new PPD year lands;
the output records its own vintage and the site prints it beside the figures,
because a median price with no date is unreadable and a stale one is worse
than none.
"""

import argparse
import csv
import json
import os
import re
import statistics
import sys
import urllib.request
from collections import defaultdict

PPD_URL = (
    'http://prod.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com/pp-{year}.csv'
)

# Boroughs come from the score Lambda's LAD_TO_BOROUGH, not from a table here.
#
# This replaced a hardcoded ten-entry GM_BOROUGHS dict when the script was
# generalised on 2026-08-11. A second copy of the borough list is the exact
# defect that took six cities off the map that morning - CITY_DATA held nine
# and a second registry held three - so the list is imported rather than
# retyped, and a city added to the Lambda is buildable here with no edit.
#
# Land Registry spells districts its own way in the `district` column, so the
# match is NORMALISED rather than exact. Measured against pp-2025 before being
# written: every borough of every city on the site matches, including
# `Westminster` -> `CITY OF WESTMINSTER`, `St Helens` -> `ST HELENS` and
# `City of Bristol` -> `CITY OF BRISTOL`. A borough that matches NOTHING is
# reported loudly by main() rather than quietly contributing no districts,
# because a silent miss reads as "this borough has no neighbourhoods".
def _norm_district(name):
    """Normalise a district name for matching across ONS and Land Registry."""
    import re

    s = (name or '').upper().replace('.', '').replace('-', ' ')
    s = re.sub(r'^THE\s+', '', s)
    s = re.sub(r'^(CITY OF|COUNTY OF)\s+', '', s)
    s = re.sub(r'\s+(CITY|DISTRICT|BOROUGH)$', '', s)
    return re.sub(r'\s+', ' ', s).strip()


def boroughs_for_city(city):
    """{normalised Land Registry district: our borough name} for one city."""
    import importlib.util

    path = os.path.join(REPO, 'backend', 'lambdas', 'score', 'app.py')
    spec = importlib.util.spec_from_file_location('score_app_nbhd', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out = {}
    for _code, (city_id, borough) in module.LAD_TO_BOROUGH.items():
        if city_id == city:
            out[_norm_district(borough)] = borough
    if not out:
        sys.exit(f'no boroughs registered for city {city!r} in LAD_TO_BOROUGH')
    return out

# PPD column indices. The bulk CSV has no header row.
C_PRICE, C_DATE, C_POSTCODE, C_LOCALITY, C_TOWN, C_DISTRICT = 1, 2, 3, 10, 11, 12
C_CATEGORY = 14

# HM Land Registry's PPD category type. 'A' is a standard price-paid entry;
# 'B' is their ADDITIONAL class - repossessions, power-of-sale transfers,
# buy-to-lets identified by mortgage, transfers to non-private individuals,
# and everything whose property type is 'O' (other/non-residential).
#
# WE PUBLISH CATEGORY A ONLY, and the reason is that the product already
# publishes a Category-A number beside these. HM Land Registry's own median
# price statistics and the UK HPI use Category A alone, and `avgPrice` in
# `borough-extra.json` is validated against HPI by a BLOCKING gate. So while
# this scan kept both classes, one product published two price bases: a
# borough figure on A and a neighbourhood figure on A+B, in the same panel.
#
# Measured over pp-2025.csv when the filter was added (2026-09-01): 16.5% of
# rows are Category B, the national median is GBP295,000 on A against
# GBP210,000 on B, and every one of the 45,371 property-type-'O' rows is B.
# Rows that were inside published medians include
# `GBP76,000 M9 7EP THE PALLET STORE TELECOMMUNICATIONS MAST SITE`.
# 412 of 485 published medians rose, 40 fell; TS26 Hartlepool by 40.0%.
PPD_CATEGORY_A = 'A'

# Display names for postal districts whose Royal Mail `locality` field is blank,
# so the fallback would be the post town and 17 different places would all read
# "Manchester".
#
# THIS IS A LABEL, NOT A MEASUREMENT, and the distinction is the whole reason
# it is allowed to be curated when `price` and `crime` are not. "M20 is
# Didsbury and Withington" is a checkable fact about postal geography; it does
# not enter any score, cannot move a ranking, and the outward code stays
# visible beside it so the label can never claim more precision than the data.
#
# Keyed by CITY, and the key must be one the builder actually uses - see the
# UNKNOWN CITY KEYS guard in `check_names()`, which exists because four of
# these dicts were first written under keys nobody looks up.
#
# HOW THESE ARE WRITTEN, AND WHY THEY ARE NOT JUST RECALLED (2026-08-12). Until
# today only Greater Manchester had any, and 273 of 503 districts across the
# other eight cities therefore rendered under a repeated post town - Birmingham
# x35, Liverpool x29, Leeds x16, Sheffield x15, Bristol x16. Nothing shipped was
# false, since the outward code is always visible beside the label, but a ranked
# list of thirty-five "Birmingham" rows tells a user nothing.
#
# Every name below is drawn from that district's OWN published MSOA names and
# checked back against them by `--check-names`. That matters more than it
# sounds: a name typed from memory is an unverifiable claim, and this file's
# whole argument for allowing a curated LABEL where it forbids a curated NUMBER
# is that the label is a checkable fact about postal geography. So it is now
# checked. See `check_names()` for the rule and `data/district-msoa-names.json`
# for the evidence.
#
# DERIVING the name outright was tried first and REJECTED ON MEASUREMENT, not
# taste. A postcode district spans 4-13 MSOAs, so the modal MSOA name carries
# only 15-33% of the district and names a sub-area: BS8 came out "Clifton East",
# SK5 came out "Brinnington" when the district is Reddish, and a shared-token
# variant produced "Five" for B16 (from Five Ways), "Quays" for M50, and
# "Mossley" for BOTH L17 and L18 - recreating the duplicate it was meant to
# fix. Scored against the 26 hand-written Manchester names as an answer key,
# every derived variant disagreed with most of them.
#
# A district is still left as its post town where no single area name is widely
# recognised - the three Darlington districts, B4, NE26, NE29, NE33, L20, B66,
# B70, BA1/BA2 - because inventing a plausible-sounding name is the same
# failure as inventing a plausible-sounding number.
NAME_OVERRIDES_BY_CITY = {}
NAME_OVERRIDES_BY_CITY['manchester'] = {
    'M1': 'Manchester City Centre',
    'M3': 'Salford Central',
    'M4': 'Ancoats & New Islington',
    'M5': 'Ordsall & Seedley',
    'M6': 'Pendleton',
    'M7': 'Broughton',
    'M8': 'Cheetham Hill & Crumpsall',
    'M9': 'Blackley & Harpurhey',
    'M11': 'Openshaw & Clayton',
    'M12': 'Ardwick & Longsight',
    'M13': 'Ardwick & Victoria Park',
    'M14': 'Fallowfield & Rusholme',
    'M15': 'Hulme',
    'M16': 'Whalley Range & Old Trafford',
    'M18': 'Gorton',
    'M19': 'Levenshulme & Burnage',
    'M20': 'Didsbury & Withington',
    'M21': 'Chorlton',
    'M22': 'Wythenshawe North',
    'M23': 'Wythenshawe South',
    'M40': 'Newton Heath & Moston',
    'M50': 'Salford Quays',
    'SK1': 'Stockport Town Centre',
    'SK3': 'Edgeley & Cheadle Heath',
    'SK4': 'Heaton Moor & Heaton Mersey',
    'SK5': 'Reddish',
    # The sixteen Greater Manchester districts still rendering under a repeated
    # post town when the other eight cities were done (2026-08-12).
    'BL1': 'Bolton Town Centre',
    'BL2': 'Harwood & Breightmet',
    'BL3': 'Great Lever & Daubhill',
    'BL8': 'Tottington & Walshaw',
    'BL9': 'Bury Town Centre',
    'OL1': 'Oldham Town North',
    'OL4': 'Lees & Springhead',
    'OL6': 'Ashton Central',
    'OL7': 'Ashton Waterloo',
    'OL8': 'Hathershaw & Garden Suburb',
    'OL11': 'Castleton & Kirkholt',
    'OL12': 'Healey & Shawclough',
    'OL16': 'Kingsway & Milnrow',
    'WN1': 'Wigan Central',
    'WN3': 'Winstanley & Worsley Mesnes',
    'WN5': 'Pemberton & Orrell',
}
NAME_OVERRIDES_BY_CITY['westmidlands'] = {
    # Birmingham. B4 is left as the post town: it straddles the Gun Quarter,
    # Aston University and Dartmouth Circus with no one recognised name.
    'B1': 'Ladywood',
    'B3': 'Birmingham City Centre',
    'B5': 'Digbeth & Park Central',
    'B6': 'Aston & Birchfield',
    'B8': 'Saltley & Washwood Heath',
    'B9': 'Bordesley Green',
    'B11': 'Sparkhill & Sparkbrook',
    'B12': 'Balsall Heath',
    'B13': 'Moseley',
    'B14': 'Kings Heath & Maypole',
    'B15': 'Edgbaston',
    'B16': 'Rotton Park & Summerfield',
    'B17': 'Harborne',
    'B18': 'Winson Green & Hockley',
    'B19': 'Lozells',
    'B20': 'Handsworth Wood',
    'B23': 'Erdington',
    'B24': 'Gravelly Hill & Pype Hayes',
    'B25': 'Yardley',
    'B26': 'Sheldon',
    'B28': 'Hall Green',
    'B29': 'Selly Oak',
    'B30': 'Bournville & Cotteridge',
    'B31': 'Northfield & Longbridge',
    'B33': 'Stechford & Kitts Green',
    'B34': 'Shard End',
    'B35': 'Castle Vale',
    'B36': 'Castle Bromwich',
    'B37': 'Chelmsley Wood',
    'B38': "King's Norton",
    'B42': 'Perry Barr',
    'B43': 'Great Barr',
    'B44': 'Kingstanding',
    # Black Country and the wider county. B66 and B70 keep their post towns:
    # B66 IS Smethwick, and B70 is West Bromwich's own centre.
    'B62': 'Quinton & Hurst Green',
    'B63': 'Halesowen Town',
    'B67': 'Bearwood',
    'B71': 'Stone Cross & Charlemont',
    'B72': 'Wylde Green',
    'B73': 'New Oscott',
    'B74': 'Streetly',
    'B75': 'Four Oaks & Little Sutton',
    'B76': 'Walmley & Minworth',
    'B91': 'Solihull Town Centre',
    'B92': 'Olton & Elmdon',
    'CV1': 'Coventry City Centre',
    'CV2': 'Wood End & Walsgrave',
    'CV3': 'Binley & Willenhall',
    'CV4': 'Canley & Tile Hill',
    'CV5': 'Earlsdon & Allesley',
    'CV6': 'Foleshill & Holbrooks',
    'DY1': 'Dudley Priory & Wrens Nest',
    'DY2': 'Netherton & Kates Hill',
    'DY3': 'Sedgley & Gornal',
    'DY8': 'Stourbridge Town & Wordsley',
    'DY9': 'Lye & Hagley',
    'WS1': 'Walsall Central',
    'WS2': 'Pleck & Bentley',
    'WS3': 'Bloxwich',
    'WS4': 'Rushall & Shelfield',
    'WS5': 'Yew Tree & The Delves',
    'WS8': 'Brownhills',
    'WS9': 'Aldridge',
    'WV1': 'Wolverhampton City Centre',
    'WV2': 'Blakenhall & Ettingshall',
    'WV3': 'Bradmore & Compton',
    'WV4': 'Penn & Goldthorn Park',
    'WV6': 'Tettenhall',
    'WV9': 'Pendeford & Coven',
    'WV10': 'Bushbury & Oxley',
    'WV11': 'Wednesfield',
    'WV12': 'Short Heath & New Invention',
    'WV13': 'Willenhall Town',
}
NAME_OVERRIDES_BY_CITY['merseyside'] = {
    # L20 keeps its post town: L20 IS Bootle, and L30 next door is Netherton.
    'CH41': 'Birkenhead Central',
    'CH42': 'Tranmere & Egerton Park',
    'CH44': 'Seacombe & Liscard',
    'CH45': 'New Brighton & Wallasey Village',
    'CH46': 'Moreton & Leasowe',
    # Not "Hoylake & West Kirby": CH48 IS West Kirby, and CH47's MSOA list
    # reaches over the boundary. Corroboration cannot catch a name that is
    # merely the NEIGHBOUR's, so read the sibling districts before writing one.
    'CH47': 'Hoylake & Meols',
    'CH49': 'Upton & Greasby',
    'CH60': 'Heswall',
    'CH61': 'Pensby & Thingwall',
    'CH62': 'Bromborough & Eastham',
    'CH63': 'Bebington',
    'L1': 'Liverpool City Centre',
    'L3': 'Vauxhall',
    'L4': 'Walton & Anfield',
    'L5': 'Kirkdale & Everton',
    'L6': 'Kensington & Fairfield',
    'L7': 'Edge Hill',
    'L8': 'Toxteth & Dingle',
    'L9': 'Walton Vale & Orrell Park',
    'L10': 'Fazakerley & Aintree',
    'L11': 'Norris Green & Croxteth',
    'L12': 'Croxteth Park & Sandfield Park',
    'L13': 'Tuebrook & Stoneycroft',
    'L14': 'Dovecot & Knotty Ash',
    'L15': 'Wavertree',
    'L16': 'Childwall',
    'L17': 'Sefton Park & Otterspool',
    'L18': 'Mossley Hill & Calderstones',
    'L19': 'Garston & Aigburth',
    'L21': 'Litherland & Seaforth',
    'L23': 'Crosby & Blundellsands',
    'L24': 'Speke',
    'L25': 'Woolton & Gateacre',
    'L27': 'Netherley',
    'L30': 'Netherton',
    'L31': 'Maghull',
    'L32': 'Kirkby South',
    'L33': 'Kirkby North',
    'L36': 'Huyton',
    'PR8': 'Birkdale & Ainsdale',
    'PR9': 'Southport Waterfront & Marshside',
    'WA9': 'Thatto Heath & Sutton',
    'WA10': 'St Helens Town Centre',
}
NAME_OVERRIDES_BY_CITY['westyorkshire'] = {
    'BD1': 'Bradford City Centre',
    'BD2': 'Eccleshill & Bolton Woods',
    'BD3': 'Barkerend & Thornbury',
    'BD4': 'Bierley & Holme Wood',
    'BD5': 'Bowling & Bankfoot',
    'BD6': 'Buttershaw & Wibsey',
    'BD7': 'Great Horton & Scholemoor',
    'BD8': 'Manningham & Girlington',
    'BD9': 'Heaton & Frizinghall',
    'BD10': 'Idle & Thackley',
    'BD21': 'Keighley Central',
    'BD22': 'Haworth & Oakworth',
    'HD1': 'Huddersfield Town Centre',
    'HD2': 'Fixby & Brackenhall',
    'HD3': 'Lindley & Longwood',
    'HD4': 'Newsome & Crosland Moor',
    'HD5': 'Almondbury & Kirkheaton',
    'HX1': 'Halifax Town Centre',
    'HX2': 'Illingworth & Ovenden',
    'HX3': 'Northowram & Southowram',
    'LS1': 'Leeds City Centre',
    'LS2': 'Woodhouse & Little London',
    'LS4': 'Burley & Kirkstall',
    'LS5': 'Hawksworth & West Park',
    'LS6': 'Headingley & Hyde Park',
    'LS7': 'Chapel Allerton & Chapeltown',
    'LS8': 'Roundhay & Harehills',
    'LS9': 'Burmantofts & Richmond Hill',
    'LS10': 'Hunslet & Middleton',
    'LS11': 'Beeston & Holbeck',
    'LS12': 'Armley & Wortley',
    'LS13': 'Bramley & Stanningley',
    'LS14': 'Seacroft & Swarcliffe',
    'LS15': 'Cross Gates & Whitkirk',
    'LS16': 'Adel & Lawnswood',
    'LS17': 'Alwoodley & Moortown',
    'WF1': 'Wakefield Central',
    'WF2': 'Sandal & Lupset',
    'WF12': 'Thornhill & Earlsheaton',
    'WF13': 'Dewsbury Central & Ravensthorpe',
}
NAME_OVERRIDES_BY_CITY['southyorkshire'] = {
    'DN1': 'Doncaster Town Centre',
    'DN2': 'Wheatley & Intake',
    'DN4': 'Bessacarr & Balby',
    'DN5': 'Bentley & Sprotbrough',
    'S1': 'Sheffield City Centre',
    'S2': 'Norfolk Park & Park Hill',
    'S3': 'Kelham & Netherthorpe',
    'S4': 'Burngreave & Fir Vale',
    'S5': 'Firth Park & Parson Cross',
    'S6': 'Hillsborough & Walkley',
    'S7': 'Nether Edge & Millhouses',
    'S8': 'Woodseats & Meersbrook',
    'S9': 'Darnall & Tinsley',
    'S10': 'Broomhill & Fulwood',
    'S11': 'Ecclesall & Greystones',
    'S12': 'Gleadless & Birley',
    'S13': 'Woodhouse & Handsworth',
    'S14': 'Gleadless Valley',
    'S17': 'Dore & Totley',
    'S60': 'Rotherham Central & Brinsworth',
    'S61': 'Kimberworth & Greasborough',
    'S65': 'East Dene & Thrybergh',
    'S70': 'Barnsley Town & Worsbrough',
    'S71': 'Athersley & Monk Bretton',
    'S75': 'Mapplewell & Darton',
}
NAME_OVERRIDES_BY_CITY['tyneandwear'] = {
    # NE26, NE29 and NE33 keep their post towns: each IS the centre of Whitley
    # Bay, North Shields and South Shields respectively, and the neighbouring
    # district in each pair is the one carrying a distinct name.
    'NE1': 'Newcastle City Centre',
    'NE2': 'Jesmond',
    'NE3': 'Gosforth & Kenton',
    'NE4': "Elswick & Arthur's Hill",
    'NE5': 'Westerhope & Blakelaw',
    'NE6': 'Byker & Walkergate',
    'NE7': 'High Heaton & Benton',
    'NE8': 'Gateshead Town & Bensham',
    'NE9': 'Low Fell & Wrekenton',
    'NE10': 'Felling & Heworth',
    'NE11': 'Dunston & Lobley Hill',
    'NE12': 'Longbenton & Killingworth',
    'NE13': 'Wideopen & Great Park',
    'NE15': 'Lemington & Newburn',
    'NE25': 'Monkseaton & Seaton Delaval',
    'NE30': 'Tynemouth & Cullercoats',
    'NE34': 'Whiteleas & Cleadon Park',
    'NE37': 'Concord & Sulgrave',
    'NE38': 'Washington Town Centre',
    'SR2': 'Hendon & Ryhope',
    'SR3': 'Silksworth & Herrington',
    'SR4': 'Pallion & Pennywell',
    'SR5': 'Southwick & Town End Farm',
    'SR6': 'Seaburn & Monkwearmouth',
}
NAME_OVERRIDES_BY_CITY['bristol'] = {
    # BA1 and BA2 keep the post town: they split Bath north/south of the Avon
    # with no single recognised area name on either side. BS23 IS Weston-super-
    # Mare's own centre, so it keeps the post town and its two neighbours carry
    # the distinct names.
    'BS1': 'Bristol City Centre',
    'BS2': 'St Pauls & St Werburghs',
    'BS3': 'Bedminster & Southville',
    'BS4': 'Brislington & Knowle',
    'BS5': 'Easton & St George',
    'BS6': 'Redland & Cotham',
    'BS7': 'Bishopston & Horfield',
    'BS8': 'Clifton',
    'BS9': 'Westbury-on-Trym & Stoke Bishop',
    'BS10': 'Henbury & Southmead',
    'BS11': 'Avonmouth & Shirehampton',
    'BS13': 'Hartcliffe & Withywood',
    'BS14': 'Hengrove & Stockwood',
    'BS15': 'Kingswood & Hanham',
    'BS16': 'Fishponds & Emersons Green',
    'BS22': 'Worle',
    'BS24': 'Hutton & Locking',
    'BS30': 'Longwell Green & Oldland Common',
}
NAME_OVERRIDES_BY_CITY['leicester'] = {
    'LE1': 'Leicester City Centre',
    'LE2': 'Clarendon Park & Knighton',
    'LE3': 'Westcotes & Braunstone',
    'LE4': 'Belgrave & Rushey Mead',
    'LE5': 'Evington & Thurnby Lodge',
}
NAME_OVERRIDES_BY_CITY['teesside'] = {
    # The three Darlington districts and TS26 keep their post towns: no single
    # area name is widely recognised for any of them.
    'TS1': 'Middlesbrough Town Centre',
    'TS3': 'Berwick Hills & Park End',
    'TS4': 'Beechwood & Easterside',
    'TS5': 'Linthorpe & Acklam',
    'TS6': 'Eston & South Bank',
    'TS18': 'Stockton Town Centre',
    'TS19': 'Hardwick & Roseworth',
    'TS20': 'Norton',
    'TS21': 'Sedgefield & Stillington',
    'TS24': 'Headland & Old Town',
    'TS25': 'Seaton Carew & Owton Manor',
    'TS27': 'Blackhall & Elwick',
}

# Share of a city's published rows `--check` must actually re-derive before it
# is allowed to report ok. Per CITY, and a share rather than a count, because a
# global `compared > 0` is satisfied by one district in one city - the failure
# mode this repo has hit five times.
CHECK_MIN_SHARE = 0.95

# A median under this many transactions is not reported. 30 is a judgement,
# stated rather than hidden: it keeps every district whose median moves less
# than ~5% when the highest and lowest sale are removed, checked on the 2025
# data at build time and printed in the summary.
DEFAULT_MIN_SALES = 30

# A district less than half inside the city publishing it is dropped, not
# published (2026-08-12).
#
# WHY THIS EXISTS. Transactions are bucketed by the LAND REGISTRY `district`
# field, which is a LOCAL AUTHORITY, but an entry is published as a POSTCODE
# DISTRICT, which is Royal Mail. Those two geographies do not nest, and until
# today nothing asked how much of a postcode district we actually held.
#
# WA8 was the case that exposed it. **4%** of its 1,591 live postcodes are in
# Knowsley; 1,500 are in Halton, which Sky Score does not cover at all. So the
# entry carried the label "Widnes" (the post town of the 94% we do not price),
# the borough Knowsley (true of the 4%), a median of GBP345k resting on 32
# sales from that 4% - which made it Merseyside's FOURTH PRICIEST entry - and a
# centroid averaged over all 1,591 postcodes, placing the marker in the middle
# of Widnes, in Halton. Every step was arithmetically right; the join was wrong.
#
# 34 of 501 districts were under 75% contained, 8 under 20%.
#
# The floor is 50% so the claim is checkable and worth stating: every district
# published is MAJORITY INSIDE the city publishing it. Same spirit as
# DEFAULT_MIN_SALES - drop rather than estimate, and print every drop, because a
# silent cap reads as full coverage.
#
# Note this cannot be fixed by better maths. The price and the centroid are both
# repaired below by restricting them to covered postcodes, but the LABEL cannot
# be: the covered slice of WA8 has no name of its own, and "Widnes" is the only
# name the district has.
DEFAULT_MIN_CONTAINMENT = 0.50

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NSPL_PATH = os.path.join(REPO, 'data', 'nspl.csv')
OUT_PATH = os.path.join(REPO, 'data', 'manchester-neighbourhoods.json')
CACHE_DIR = os.path.join(REPO, 'data')


def outward(postcode):
    """'M20 2RN' -> 'M20'. Returns None for anything that is not a UK postcode."""
    pc = (postcode or '').strip().upper()
    if ' ' not in pc:
        return None
    out = pc.split(' ', 1)[0]
    return out if 2 <= len(out) <= 4 else None


def fetch_ppd(year, cache_dir):
    """Download pp-<year>.csv unless already cached. Returns the local path.

    Cached under data/, which is gitignored file-by-file, so these large files
    never enter the repo. That gitignore behaviour is the same one that kept
    manchester-boroughs.json out of git until it was un-ignored explicitly.
    """
    path = os.path.join(cache_dir, f'pp-{year}.csv')
    if os.path.exists(path) and os.path.getsize(path) > 1_000_000:
        print(f'  pp-{year}.csv cached ({os.path.getsize(path) / 1024 / 1024:.0f} MB)')
        return path
    url = PPD_URL.format(year=year)
    print(f'  downloading {url} ...')
    req = urllib.request.Request(url, headers={'User-Agent': 'sky-score-build/1.0'})
    tmp = path + '.part'
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, 'wb') as fh:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
    os.replace(tmp, path)
    print(f'  saved {os.path.getsize(path) / 1024 / 1024:.0f} MB')
    return path


def collect_sales(paths, borough_maps):
    """Stream the PPD CSVs once, bucketing rows by city.

    ONE pass for every city, not one per city. The bulk CSV is 162 MB and the
    NSPL scan below is 806 MB; doing both per city turned a three-minute build
    into a twenty-minute one when this went from Greater Manchester alone to
    seven cities. `borough_maps` is {city: {normalised district: borough}}.

    Returns {city: {outward: {'prices': [...], 'boroughs': {...}, 'localities': {...}}}}
    """
    lookup = {}
    for city, boroughs in borough_maps.items():
        for norm, borough in boroughs.items():
            # A district belongs to exactly one of our cities, so a collision
            # here is a registry error worth failing on rather than resolving
            # arbitrarily.
            if norm in lookup:
                sys.exit(f'district {norm!r} claimed by both {lookup[norm][0]} and {city}')
            lookup[norm] = (city, borough)

    per_city = {city: defaultdict(
        lambda: {'prices': [], 'boroughs': defaultdict(int), 'localities': defaultdict(int)}
    ) for city in borough_maps}
    seen = kept = dropped_b = 0
    for path in paths:
        with open(path, newline='', encoding='utf-8', errors='replace') as fh:
            for row in csv.reader(fh):
                seen += 1
                if len(row) <= C_DISTRICT:
                    continue
                hit = lookup.get(_norm_district(row[C_DISTRICT]))
                if not hit:
                    continue
                city, borough = hit
                out = outward(row[C_POSTCODE])
                if not out:
                    continue
                if len(row) <= C_CATEGORY or row[C_CATEGORY].strip().upper() != PPD_CATEGORY_A:
                    # Category B. See PPD_CATEGORY_A - this is the filter that
                    # puts the neighbourhood median on the same basis as the
                    # borough avgPrice the HPI gate already validates.
                    dropped_b += 1
                    continue
                try:
                    price = int(row[C_PRICE])
                except (ValueError, TypeError):
                    continue
                if price <= 0:
                    continue
                rec = per_city[city][out]
                rec['prices'].append(price)
                rec['boroughs'][borough] += 1
                loc = (row[C_LOCALITY] or '').strip().title()
                town = (row[C_TOWN] or '').strip().title()
                name = loc or town
                if name:
                    rec['localities'][name] += 1
                kept += 1
    total = sum(len(v) for v in per_city.values())
    print(f'  scanned {seen:,} transactions, kept {kept:,} across {total} districts in {len(per_city)} cities')
    print(f'  dropped {dropped_b:,} rows outside PPD category {PPD_CATEGORY_A} (see PPD_CATEGORY_A)')
    if kept and not dropped_b:
        # Category B is 16.5% of the national file. Zero of them in a scan that
        # kept anything means the column moved or the file changed shape, and
        # the medians would silently go back onto the mixed basis this filter
        # exists to remove.
        sys.exit('FAIL: kept transactions but dropped no category-B rows - check column C_CATEGORY.')
    return per_city


def collect_centroids(wanted):
    """Mean lat/lon per outward code from NSPL, live postcodes only.

    NSPL is ~806 MB and is scanned once. `doterm` (date of termination) is
    non-empty for retired postcodes; including them would drag a centroid
    toward wherever the estate used to be.

    Also tallies each district's MSOA21 codes on the SAME pass, which is what
    `--check-names` corroborates the curated labels against. A second 806 MB
    scan to collect one more column is the kind of thing that turns a
    three-minute build into a six-minute one for no reason.

    Returns (centroids, msoa_counts).
    """
    if not os.path.exists(NSPL_PATH):
        sys.exit(
            f'NSPL not found at {NSPL_PATH}.\n'
            'It is gitignored and local-only. Without it there are no coordinates,\n'
            'and a neighbourhood with no lat/lon cannot be scored for quiet at all.'
        )
    # Keyed by (district, LAD) rather than district alone, so a centroid can be
    # taken over the covered part only. Blending the whole district put WA8's
    # marker in Halton while its price described Knowsley.
    sums = defaultdict(lambda: [0.0, 0.0, 0])
    msoa = defaultdict(lambda: defaultdict(int))
    with open(NSPL_PATH, newline='', encoding='utf-8', errors='replace') as fh:
        reader = csv.DictReader(fh)
        cols = {c.lower(): c for c in (reader.fieldnames or [])}
        c_pcds = cols.get('pcds') or cols.get('pcd')
        c_lat, c_long = cols.get('lat'), cols.get('long')
        c_term = cols.get('doterm')
        c_msoa = cols.get('msoa21cd')
        c_lad = cols.get('lad25cd') or next(
            (cols[c] for c in cols if re.fullmatch(r'lad\d\dcd', c)), None
        )
        if not (c_pcds and c_lat and c_long):
            sys.exit(f'NSPL columns not as expected: {reader.fieldnames[:12]}')
        if not c_lad:
            sys.exit(
                'NSPL has no lad**cd column, so district containment cannot be\n'
                'measured and a district 4% inside its city would publish silently.'
            )
        if not c_msoa:
            sys.exit(
                'NSPL has no msoa21cd column, so the curated area names cannot be\n'
                'corroborated. A vintage roll that drops or renames it must not\n'
                'silently downgrade the check to nothing.'
            )
        for row in reader:
            if c_term and (row.get(c_term) or '').strip():
                continue
            out = outward(row.get(c_pcds))
            if out not in wanted:
                continue
            code = (row.get(c_msoa) or '').strip()
            if code:
                msoa[out][code] += 1
            try:
                lat, lon = float(row[c_lat]), float(row[c_long])
            except (ValueError, TypeError):
                continue
            # NSPL uses 99.999999 for postcodes with no grid reference.
            if lat > 90 or lat < 49:
                continue
            s = sums[(out, (row.get(c_lad) or '').strip())]
            s[0] += lat
            s[1] += lon
            s[2] += 1
    by_lad = defaultdict(dict)
    for (out, lad), v in sums.items():
        by_lad[out][lad] = v
    return by_lad, msoa


def lad_codes_for_city(city):
    """{LAD code: borough} for one city, from the score Lambda's registry."""
    import importlib.util

    path = os.path.join(REPO, 'backend', 'lambdas', 'score', 'app.py')
    spec = importlib.util.spec_from_file_location('score_app_lads', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {code: borough for code, (c, borough) in module.LAD_TO_BOROUGH.items() if c == city}


def containment(by_lad, out, city_lads):
    """(share inside the city, covered centroid, covered count, total count).

    The centroid is the mean of the COVERED postcodes only. A district we hold
    part of should be plotted where we hold it, not at the middle of a town we
    do not cover.
    """
    per_lad = by_lad.get(out) or {}
    total = sum(v[2] for v in per_lad.values())
    if not total:
        return 0.0, None, 0, 0
    lat = lon = 0.0
    n = 0
    for lad, v in per_lad.items():
        if lad in city_lads:
            lat += v[0]
            lon += v[1]
            n += v[2]
    if not n:
        return 0.0, None, 0, total
    return n / total, (lat / n, lon / n), n, total


# The evidence the curated labels are checked against.
#
# `msoa-names-2.1.csv` is the House of Commons Library's MSOA Names dataset -
# a human-readable name for all 7,264 English and Welsh 2021 MSOAs, published
# under the Open Government Licence. It is the ONLY published source that gives
# statistical geographies the names people actually use; ONS's own `msoa21nm` is
# "Bristol 023".
#
# `district-msoa-names.json` is the small derived join of it against NSPL, and
# is CHECKED IN deliberately: `--check-names` has to run in preflight on a
# machine with no 806 MB NSPL and no network. The 663 KB source CSV is not
# needed at check time and stays gitignored.
MSOA_NAMES_URL = 'https://houseofcommonslibrary.github.io/msoanames/MSOA-Names-2.1.csv'
MSOA_NAMES_PATH = os.path.join(REPO, 'data', 'msoa-names-2.1.csv')
DISTRICT_MSOA_PATH = os.path.join(REPO, 'data', 'district-msoa-names.json')

# Words a curated label may contain WITHOUT appearing in the district's MSOA
# names. Two kinds only: bare compass and civic words, which describe a position
# rather than assert a place; and the district's own post town, which is a Royal
# Mail fact already in hand from the Price Paid data. Everything else has to be
# corroborated. Keep this list SHORT - each entry is a word the check can no
# longer see, and a long list would quietly turn the check green.
GENERIC_LABEL_WORDS = {
    'and', 'the', 'city', 'centre', 'center', 'town', 'village', 'north',
    'south', 'east', 'west', 'central', 'upper', 'lower', 'inner', 'outer',
}


def load_msoa_names():
    """{msoa21cd: human-readable name} from the House of Commons Library file."""
    if not os.path.exists(MSOA_NAMES_PATH):
        sys.exit(
            f'{os.path.basename(MSOA_NAMES_PATH)} not found. Fetch it with:\n'
            f'  curl -sS -A "Mozilla/5.0" -o {MSOA_NAMES_PATH} {MSOA_NAMES_URL}'
        )
    with open(MSOA_NAMES_PATH, newline='', encoding='utf-8-sig') as fh:
        rows = list(csv.DictReader(fh))
    if not rows or 'msoa21cd' not in rows[0]:
        sys.exit(f'{MSOA_NAMES_PATH} is not the 2021 MSOA names file (needs msoa21cd)')
    return {r['msoa21cd']: r['msoa21hclnm'].strip() for r in rows if r['msoa21hclnm'].strip()}


def write_district_msoa_index(msoa_counts, post_towns):
    """Persist the per-district evidence `--check-names` reads.

    Names are ordered by how many of the district's postcodes fall in them, so
    the file doubles as the thing to read when WRITING a label: the recognisable
    area name is usually right there at the top.
    """
    names = load_msoa_names()
    out = {}
    unnamed = set()
    for district, codes in msoa_counts.items():
        agg = defaultdict(int)
        for code, n in codes.items():
            name = names.get(code)
            if not name:
                unnamed.add(code)
                continue
            agg[name] += n
        if not agg:
            continue
        total = sum(agg.values())
        out[district] = {
            'postTown': post_towns.get(district, ''),
            'postcodes': total,
            'msoa': [n for n, _ in sorted(agg.items(), key=lambda kv: (-kv[1], kv[0]))],
        }
    payload = {
        'generatedBy': 'scripts/build_city_neighbourhoods.py',
        'purpose': 'evidence for --check-names; NOT a scoring input',
        'msoaNameSource': 'House of Commons Library MSOA Names v2.1 (2021 MSOAs)',
        'postcodeSource': 'ONS National Statistics Postcode Lookup (live postcodes)',
        'licence': 'Open Government Licence v3.0',
        'districts': out,
    }
    with open(DISTRICT_MSOA_PATH, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, indent=1, sort_keys=True)
        fh.write('\n')
    if unnamed:
        # Welsh and Scottish MSOAs have no HoC name; anything else is a vintage
        # mismatch between NSPL and the names file and is worth seeing.
        print(f'  {len(unnamed)} MSOA codes had no published name (Wales/Scotland or a vintage skew)')
    print(f'  wrote MSOA evidence for {len(out)} districts to {os.path.basename(DISTRICT_MSOA_PATH)}')


def _label_words(label):
    return re.findall(r"[A-Za-z][A-Za-z'\-]*", label)


def check_names(publishable=None):
    """Corroborate every curated label against its own district's MSOA names.

    THE RULE: each word of a curated label must appear somewhere in that
    district's published MSOA names, or be its post town, or be a bare compass
    or civic word. Nothing else passes.

    WHY THIS AND NOT A SIMILARITY SCORE. The failure being guarded against is a
    label that sounds right and belongs somewhere else - "BS8: Didsbury",
    "L8: Chelsea" - and a threshold on string distance would rank those as
    confidently wrong rather than wrong. Word containment answers the only
    question that matters: does any published source put this name in this
    district?

    It cannot see a bad compass claim ("Darlington East" for a western
    district), which is why the compass words are only ever allowed ALONGSIDE
    a post town rather than as a whole label. Returns the number of failures.

    `publishable` is city -> the outward codes THIS build will publish, and it
    exists because a label for a district we no longer publish is dead config,
    not a false claim: it reaches no user, and there is nothing to corroborate
    it against, since the evidence file only covers published districts. Four
    labels became exactly that on 2026-09-01 when the category-A filter dropped
    L2, L28, SR1 and B7 below the 30-sale floor - the floor working, reported by
    the name check as four failures.

    The inverse hazard is why this is a SET and not a blanket skip: a district
    that IS published and has no evidence is a real gap and still fails. Pass
    None (standalone --check-names) and every curated label must corroborate,
    which is the stricter reading and the right one when there is no build to
    say what will ship.
    """
    if not os.path.exists(DISTRICT_MSOA_PATH):
        sys.exit(
            f'{os.path.basename(DISTRICT_MSOA_PATH)} not found. It is written by a\n'
            'full build: python scripts/build_city_neighbourhoods.py'
        )
    with open(DISTRICT_MSOA_PATH, encoding='utf-8') as fh:
        evidence = json.load(fh)['districts']

    failures = 0

    # A dict keyed by a city that does not exist is looked up by nobody and
    # corroborates perfectly, which is the worst of both: every name in it
    # passes this check and none of them ever reaches a label. Four of the eight
    # dicts written on 2026-08-12 were keyed `west_midlands` / `south_yorkshire`
    # when the builder's own keys are `westmidlands` / `southyorkshire`, and the
    # check reported all 285 names corroborated while 163 of them were dead.
    unknown = sorted(set(NAME_OVERRIDES_BY_CITY) - set(DEFAULT_CITIES))
    if unknown:
        print(f'  UNKNOWN CITY KEYS: {", ".join(unknown)}')
        print(f'     generated cities are: {", ".join(DEFAULT_CITIES)}')
        failures += len(unknown)
    for city in sorted(NAME_OVERRIDES_BY_CITY):
        overrides = NAME_OVERRIDES_BY_CITY[city]
        bad, unused = [], []
        for district, label in sorted(overrides.items()):
            rec = evidence.get(district)
            if not rec:
                if publishable is not None and district not in publishable.get(city, set()):
                    unused.append((district, label))
                    continue
                bad.append((district, label, ['no MSOA evidence for this district']))
                continue
            haystack = ' '.join(rec['msoa'] + [rec['postTown']]).lower()
            unmatched = [
                w for w in _label_words(label)
                if w.lower() not in GENERIC_LABEL_WORDS and w.lower() not in haystack
            ]
            if unmatched:
                bad.append((district, label, unmatched))
        n = len(overrides)
        suffix = f', {len(unused):3} unused' if unused else ''
        print(f'  {city:16} {n:3} curated, {n - len(bad) - len(unused):3} corroborated, '
              f'{len(bad):3} unmatched{suffix}')
        for district, label in unused:
            print(f'     {district:6} {label!r} - district no longer published (below a floor)')
        for district, label, unmatched in bad:
            top = ', '.join(evidence.get(district, {}).get('msoa', [])[:4]) or '(none)'
            print(f'     {district:6} {label!r} - no source for {unmatched}')
            print(f'            {district} MSOAs: {top}')
        failures += len(bad)
    return failures


INDEX_PATH = os.path.join(REPO, 'index.html')


def markers(city):
    """Marker pair delimiting one city's generated block in index.html.

    Uniform per city. Greater Manchester's were `GM-NEIGHBOURHOODS` while it was
    the only generated city; a one-off name is the kind of special case that
    bites the day a second city arrives, which is today.
    """
    tag = city.upper()
    return f'/* {tag}-NEIGHBOURHOODS:START */', f'/* {tag}-NEIGHBOURHOODS:END */'


def write_index(city, entries, payload):
    """Rewrite index.html between this city's NEIGHBOURHOODS markers.

    Inline rather than fetched, because London's and NYC's neighbourhood tables
    are inline too and a fourth network request on first paint is not worth
    ~11 KB. Marker-delimited so a rebuild cannot drift from the JSON: this is
    the file `data/*` gitignore taught us to distrust hand-syncing.
    """
    mark_start, mark_end = markers(city)
    prefix = city.upper()
    with open(INDEX_PATH, encoding='utf-8') as fh:
        src = fh.read()
    a, b = src.find(mark_start), src.find(mark_end)
    if a < 0 or b < 0:
        sys.exit(f'markers not found in index.html - expected {mark_start} ... {mark_end}')

    area, detail = {}, {}
    for label, e in entries.items():
        area[label] = {'code': e['outward'], 'lat': e['lat'], 'lon': e['lon'], 'borough': e['borough']}
        detail[label] = {
            'price': e['price'],
            'crime': e['crime'],
            'lat': e['lat'],
            'lon': e['lon'],
            'borough': e['borough'],
            'sales': e['sales'],
        }
    block = (
        f'{mark_start}\n'
        f'      // GENERATED by scripts/build_city_neighbourhoods.py - do not hand-edit.\n'
        f'      // {len(entries)} postcode districts. price = MEDIAN of real HM Land Registry\n'
        f'      // Price Paid transactions ({payload["priceVintage"]}), sales = how many that median rests on,\n'
        f'      // coordinates = mean of live ONS NSPL postcodes in the district.\n'
        f'      // crime is 0 for every entry and is NOT a measurement - sub-borough crime\n'
        f'      // is not published at this geography. renderGroup discloses this.\n'
        f'      const {prefix}_NEIGHBOURHOOD_VINTAGE = {json.dumps(payload["priceVintage"])};\n'
        f'      const {prefix}_NEIGHBOURHOOD_MIN_SALES = {payload["minSales"]};\n'
        f'      Object.assign({prefix}_AREA_MAP, {json.dumps(area, sort_keys=True)});\n'
        f'      Object.assign({prefix}_NEIGHBOURHOOD_DETAIL, {json.dumps(detail, sort_keys=True)});\n'
        f'      '
    )
    out = src[:a] + block + src[b:]
    with open(INDEX_PATH, 'w', encoding='utf-8', newline='') as fh:
        fh.write(out)
    return len(block)


def _cities_with_markers():
    """Every city index.html has a <CITY>-NEIGHBOURHOODS block for.

    DERIVED, not listed. This was a hardcoded list of seven, and on 2026-08-11
    Leicester and Teesside were added to index.html with markers in place and
    this script reported "448 neighbourhoods across 7 cities" - a confident
    success that had silently skipped both. The markers ARE the contract, since
    they are what --write-index rewrites between, so reading them cannot drift
    from the file being written.

    London and New York are absent by design: their neighbourhood tables are
    CURATED inline, not generated from Price Paid.
    """
    with open('index.html', encoding='utf-8') as fh:
        src = fh.read()
    return sorted(m.lower() for m in re.findall(r'([A-Z]+)-NEIGHBOURHOODS:START', src))


DEFAULT_CITIES = _cities_with_markers()


def published_entries(city):
    """One city's generated neighbourhood rows, read back out of index.html.

    Joined across the two blocks the writer emits: AREA_MAP carries the outward
    code, DETAIL carries the price and the sale count, and the label is the key
    shared by both. Read from index.html rather than the JSON by-product in
    `data/`, because index.html is the file that is DEPLOYED - a check against
    the by-product would agree with itself while the site published anything.
    """
    prefix = city.upper()
    with open(INDEX_PATH, encoding='utf-8') as fh:
        src = fh.read()
    out = {}
    for name, target in (('area', 'AREA_MAP'), ('detail', 'NEIGHBOURHOOD_DETAIL')):
        needle = f'Object.assign({prefix}_{target}, '
        a = src.find(needle)
        if a < 0:
            sys.exit(f'FAIL: {prefix}_{target} block not found in index.html')
        start = a + len(needle)
        depth, i = 0, start
        while i < len(src):
            if src[i] == '{':
                depth += 1
            elif src[i] == '}':
                depth -= 1
                if depth == 0:
                    break
            i += 1
        out[name] = json.loads(src[start:i + 1])
    rows = {}
    for label, area in out['area'].items():
        detail = out['detail'].get(label)
        if detail is None:
            sys.exit(f'FAIL: {label} is in {prefix}_AREA_MAP with no DETAIL row')
        rows[label] = {'outward': area['code'], 'price': detail['price'], 'sales': detail['sales']}
    return rows


def check_prices(cities, args):
    """Re-derive every published median from Price Paid and compare.

    THE GATE THIS REPLACES DID NOT EXIST. `preflight.sh` claimed a wrong price
    would red `prices == HM Land Registry`; that stage compares BOROUGH avgPrice
    against the HPI and never touches a postcode district, so the neighbourhood
    medians - 485 published numbers driving ~31% of the ranked "best value"
    list - were derived by a script nothing checked. They spent months on a
    mixed A+B basis with every gate green.

    No NSPL pass: containment and coordinates are not re-derived, only the
    price and the count of sales it rests on. That is the half that can be
    wrong without any other surface noticing, and it keeps the check to one
    scan of the Price Paid file.

    THE FLOOR IS PER CITY, and per city it is a SHARE of that city's published
    rows, not a count. This repo has now been bitten five times by a global
    `compared > 0`: it is satisfied by 104 of 114 bands, by 9 of 10 boroughs,
    and here it would be satisfied by one district in one of nine cities.
    """
    missing = [y for y in args.years if not os.path.exists(os.path.join(CACHE_DIR, f'pp-{y}.csv'))]
    if missing:
        # Not a pass. A gate whose input is absent has measured nothing, and
        # this file is a 155 MB gitignored download, so absent is the normal
        # state on a fresh clone - which is exactly why the preflight stage
        # that runs this is advisory rather than blocking.
        print(f'INCONCLUSIVE: Price Paid cache missing for {missing}. Nothing compared.')
        print('  Run `python scripts/build_city_neighbourhoods.py` once to populate data/pp-<year>.csv.')
        return 2

    borough_maps = {c: boroughs_for_city(c) for c in cities}
    per_city = collect_sales([os.path.join(CACHE_DIR, f'pp-{y}.csv') for y in args.years], borough_maps)

    total_compared = total_differ = 0
    failed_cities = []
    for city in cities:
        rows = published_entries(city)
        compared = differ = unresolved = 0
        for label, row in sorted(rows.items()):
            rec = per_city[city].get(row['outward'])
            if rec is None or not rec['prices']:
                # A published district we cannot re-derive at all. Reported, not
                # skipped: "no rows" is what a broken district join looks like.
                unresolved += 1
                print(f'  {city}: {label} published price {row["price"]}k, no category-A rows found')
                continue
            compared += 1
            want_price = round(statistics.median(rec['prices']) / 1000)
            want_sales = len(rec['prices'])
            if want_price != row['price'] or want_sales != row['sales']:
                differ += 1
                print(
                    f'  {city}: {label} publishes {row["price"]}k on {row["sales"]} sales, '
                    f'Price Paid category A gives {want_price}k on {want_sales}'
                )
        total_compared += compared
        total_differ += differ + unresolved
        share = compared / len(rows) if rows else 0.0
        status = 'ok' if (share >= CHECK_MIN_SHARE and not differ and not unresolved) else 'FAIL'
        print(f'  {city}: {compared} of {len(rows)} rows compared ({share:.0%}), {differ} differ, {unresolved} unresolved [{status}]')
        if status == 'FAIL':
            failed_cities.append(city)

    print('')
    print(f'compared {total_compared} published medians across {len(cities)} cities')
    if failed_cities:
        print(f'FAIL: {", ".join(failed_cities)}.')
        print('A published median that does not reproduce from category-A Price Paid is')
        print('either a stale index.html or a changed basis. Re-run with --write-index.')
        return 1
    print(f'OK: every published median reproduces from HM Land Registry category-A Price Paid ({args.years}).')
    return 0


def build_city(city, keep_by_city, placement, dropped_thin, args):
    """Turn one city's kept districts into entries, JSON and an index block."""
    name_overrides = NAME_OVERRIDES_BY_CITY.get(city, {})
    entries = {}
    no_coords = []
    for out, rec in sorted(keep_by_city[city].items()):
        placed = placement.get((city, out))
        if not placed:
            # Separate causes, separate messages. A containment drop is already
            # reported by main() with its share; lumping it in here as "no NSPL
            # coordinates" would describe a district that has plenty of them.
            if out not in dropped_thin:
                no_coords.append(out)
            continue
        (lat, lon), pc_count, share = placed
        prices = rec['prices']
        borough = max(rec['boroughs'].items(), key=lambda kv: kv[1])[0]
        # Display name: a curated postal-district label where one is widely
        # recognised, else the Royal Mail locality most transactions use, else
        # the outward code itself rather than a name we invent.
        locality = max(rec['localities'].items(), key=lambda kv: kv[1])[0] if rec['localities'] else out
        label = f'{name_overrides.get(out, locality)} ({out})'
        entries[label] = {
            'outward': out,
            'borough': borough,
            'price': round(statistics.median(prices) / 1000),
            'sales': len(prices),
            'lat': round(lat, 5),
            'lon': round(lon, 5),
            # Both counted over the COVERED part of the district only, which is
            # the part the price describes. `postcodes` used to count the whole
            # district, so WA8 reported 1,591 against a median drawn from 32
            # sales in the 4% of it we hold.
            'postcodes': pc_count,
            'containment': round(share, 3),
            # Sub-borough crime is NOT SOURCED. Zero here means "no modifier
            # applied", never "average crime". The site says so.
            'crime': 0,
        }

    if no_coords:
        print(f'  {len(no_coords)} districts had sales but no NSPL coordinates: {", ".join(sorted(no_coords))}')

    payload = {
        'generatedBy': 'scripts/build_city_neighbourhoods.py',
        'city': city,
        'priceSource': 'HM Land Registry Price Paid Data',
        'priceVintage': ', '.join(str(y) for y in args.years),
        'priceBasis': (
            'median sale price per postcode district, HM Land Registry PPD '
            'category A only (the basis HM Land Registry and the UK HPI use)'
        ),
        'coordinateSource': 'ONS National Statistics Postcode Lookup (live postcodes, mean centroid)',
        'nameSource': (
            'Royal Mail locality most transactions use, or a curated postal-district '
            'label corroborated against House of Commons Library MSOA Names v2.1 '
            '(see --check-names). Names are labels, not measurements, and enter no score.'
        ),
        'crimeSourced': False,
        'crimeNote': (
            'Sub-borough crime is not published at this geography; ONS Table C4 is '
            'Community Safety Partnership level, which here is the borough. No '
            'per-neighbourhood crime modifier is applied.'
        ),
        'minSales': args.min_sales,
        'licence': 'Open Government Licence v3.0',
        'neighbourhoods': entries,
    }
    out_path = os.path.join(REPO, 'data', f'{city}-neighbourhoods.json')
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, indent=1, sort_keys=False)
        fh.write('\n')
    print(f'  wrote {len(entries)} neighbourhoods to {os.path.basename(out_path)}')

    if args.write_index:
        n = write_index(city, entries, payload)
        print(f'  rewrote {n} bytes between the {city.upper()}-NEIGHBOURHOODS markers')

    # Every borough must contribute at least one district. A borough with none
    # is nearly always a district-name mismatch rather than a real absence, and
    # a silent miss reads as "this borough has no neighbourhoods".
    counts = defaultdict(int)
    for e in entries.values():
        counts[e['borough']] += 1
    expected = set(boroughs_for_city(city).values())
    missing = sorted(expected - set(counts))
    for b in sorted(counts):
        print(f'     {b:<28} {counts[b]}')
    if missing:
        print(f'  BOROUGHS WITH NO NEIGHBOURHOOD: {", ".join(missing)}')
    return len(entries), missing


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--years', nargs='+', type=int, default=[2025])
    ap.add_argument('--min-sales', type=int, default=DEFAULT_MIN_SALES)
    ap.add_argument('--city', help='one city key; default is every generated city')
    ap.add_argument(
        '--write-index',
        action='store_true',
        help="also rewrite index.html between each city's NEIGHBOURHOODS markers",
    )
    ap.add_argument(
        '--min-containment',
        type=float,
        default=DEFAULT_MIN_CONTAINMENT,
        metavar='SHARE',
        help='drop a district less than this share inside the publishing city',
    )
    ap.add_argument(
        '--check-names',
        action='store_true',
        help='corroborate the curated area labels against published MSOA names and exit',
    )
    ap.add_argument(
        '--check',
        action='store_true',
        help='re-derive every published median from Price Paid and compare; no writes',
    )
    args = ap.parse_args()

    if args.check_names:
        print('Curated area names vs House of Commons Library MSOA Names v2.1')
        failures = check_names()
        if failures:
            print(
                f'\nFAIL: {failures} curated names could not be corroborated.\n'
                'Either the name belongs to a different district, or no published\n'
                'source puts it in this one. Correct it or drop it back to the post town.'
            )
            return 1
        total = sum(len(v) for v in NAME_OVERRIDES_BY_CITY.values())
        print(f'\nOK: all {total} curated names corroborated.')
        return 0

    cities = [args.city] if args.city else list(DEFAULT_CITIES)

    if args.check:
        print('Published neighbourhood medians vs HM Land Registry Price Paid (category A)')
        print(f'  cities: {", ".join(cities)}; vintage {", ".join(str(y) for y in args.years)}')
        return check_prices(cities, args)

    print(f'Neighbourhoods from HM Land Registry Price Paid for: {", ".join(cities)}')
    print(f'  vintage: {", ".join(str(y) for y in args.years)}')

    borough_maps = {c: boroughs_for_city(c) for c in cities}
    paths = [fetch_ppd(y, CACHE_DIR) for y in args.years]
    per_city = collect_sales(paths, borough_maps)

    # Threshold BEFORE the NSPL scan, so we only look up coordinates we use.
    keep_by_city = {}
    wanted = set()
    for city in cities:
        keep, dropped = {}, []
        for out, rec in per_city[city].items():
            if len(rec['prices']) < args.min_sales:
                dropped.append((out, len(rec['prices'])))
                continue
            keep[out] = rec
        keep_by_city[city] = keep
        wanted |= set(keep)
        print(f'  {city}: {len(keep)} districts at or above {args.min_sales} sales; {len(dropped)} dropped')

    if not wanted:
        sys.exit('FAIL: no districts met the threshold for any city. Check the district names.')

    # ONE NSPL pass for every city. It is 806 MB.
    print('  scanning NSPL for coordinates, LADs and MSOAs (this is the slow part) ...')
    by_lad, msoa_counts = collect_centroids(wanted)

    # How much of each district do we actually hold, and where is that part?
    print(f'\n  containment (floor {args.min_containment:.0%} of live postcodes)')
    placement = {}
    shares = {}
    dropped_thin = []
    for city in cities:
        city_lads = lad_codes_for_city(city)
        for out in keep_by_city[city]:
            share, centre, covered, total = containment(by_lad, out, city_lads)
            shares[(city, out)] = share
            if centre is None:
                continue
            if share < args.min_containment:
                dropped_thin.append((share, city, out, total))
                continue
            placement[(city, out)] = (centre, covered, share)

    # A postcode district belongs to exactly ONE city. WN4 and WN5 straddle the
    # Wigan/St Helens line and were published TWICE - same coordinates, and for
    # WN5 two different names GBP70k apart ("Pemberton & Orrell" at GBP165k in
    # Greater Manchester, "Billinge" at GBP235k in Merseyside). Whichever city
    # holds more of it wins; the loser is dropped and printed.
    #
    # At the DEFAULT floor this cannot fire, because two cities cannot each hold
    # a majority of the same district - the floor already resolves it, and WN4
    # and WN5 leave Merseyside at 15% and 13% while staying in Wigan at 85% and
    # 87%. It is kept because --min-containment can be lowered below 0.5, where
    # the ambiguity returns and would otherwise publish two prices for one point.
    by_out = defaultdict(list)
    for (city, out) in placement:
        by_out[out].append(city)
    for out, owners in sorted(by_out.items()):
        if len(owners) < 2:
            continue
        winner = max(owners, key=lambda c: shares[(c, out)])
        for city in owners:
            if city != winner:
                del placement[(city, out)]
                print(f'    {out} claimed by {city} ({shares[(city, out)]:.0%}) and '
                      f'{winner} ({shares[(winner, out)]:.0%}); kept in {winner}')

    thin_by_city = defaultdict(set)
    for share, city, out, total in sorted(dropped_thin):
        thin_by_city[city].add(out)
        print(f'    DROPPED {out:6} {share:4.0%} inside {city} '
              f'({total:,} live postcodes) - majority lies outside')
    print(f'    {len(placement)} districts placed, {len(dropped_thin)} below the floor')

    # Post town per district, the one label word a curated name may use without
    # MSOA corroboration. Same modal locality `build_city` labels with.
    post_towns = {}
    for city in cities:
        for out, rec in keep_by_city[city].items():
            if rec['localities']:
                post_towns[out] = max(rec['localities'].items(), key=lambda kv: kv[1])[0]

    # ONLY on a full build. A --city run scans NSPL for that city's districts
    # alone, so writing the evidence here would replace all 501 districts with
    # that city's 59 - and every other city's labels would then fail the check
    # for "no MSOA evidence" while nothing was actually wrong with them. That
    # is not hypothetical: a --city merseyside run did exactly this on
    # 2026-08-12 and preflight went red on 239 perfectly good names.
    if args.city:
        print(f'  leaving {os.path.basename(DISTRICT_MSOA_PATH)} alone: a single-city')
        print('  build has evidence for one city only and would truncate it')
    else:
        write_district_msoa_index(msoa_counts, post_towns)

    # BEFORE anything is written. An uncorroborated label is the one output of
    # this script that cannot be caught downstream - a wrong price shows up in
    # --check against HPI, a wrong borough shows up as a borough with no
    # neighbourhoods, but "L8: Chelsea" would simply render. A single city build
    # cannot see the other cities' evidence, so it is skipped there rather than
    # reported as a pile of false failures.
    if not args.city:
        print('')
        print('Corroborating curated area names against MSOA names')
        publishable = {
            city: {out for out in keep_by_city[city] if (city, out) in placement}
            for city in cities
        }
        failures = check_names(publishable)
        if failures:
            print(
                f'\nFAIL: {failures} curated names could not be corroborated; nothing written.\n'
                'Correct the name or drop it back to the post town.'
            )
            return 1

    total = 0
    any_missing = []
    for city in cities:
        print(f'\n{city}')
        n, missing = build_city(city, keep_by_city, placement, thin_by_city[city], args)
        total += n
        any_missing += [f'{city}.{b}' for b in missing]

    print(f'\n{total} neighbourhoods across {len(cities)} cities')
    if any_missing:
        print(f'BOROUGHS WITH NO NEIGHBOURHOOD: {", ".join(any_missing)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
