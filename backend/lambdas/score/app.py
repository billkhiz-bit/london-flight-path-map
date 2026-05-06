"""
Sky Score B2B API.

Endpoints:
  GET  /v1/score          — single-postcode/borough score
  POST /v1/score/batch    — bulk lookup (up to 100 queries per call)
  OPTIONS for both        — browser CORS preflight (open to any origin
                            since the GET/POST are API-key gated anyway)

Methodology: see METHODOLOGY.md at the project root. The scoring values and
formulas in this file are anchored to that document; any change to weights,
thresholds, or component formulas should bump METHODOLOGY_VERSION and be
documented in the methodology changelog.
"""

import json
import logging
import math
import os
import re
from collections import OrderedDict
from datetime import datetime, timezone
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _make_lru(maxsize):
    """OrderedDict-backed LRU cache that does NOT cache None results.

    `functools.lru_cache` caches every return value including None, which
    means a transient outage of an upstream (postcodes.io, DDB) poisons
    the cache for the lifetime of the warm container (~15 min on AWS
    Lambda). This implementation only stores truthy values, so the next
    request after an outage retries upstream instead of serving None.
    """
    cache = OrderedDict()

    def get(key):
        if key not in cache:
            return None
        cache.move_to_end(key)
        return cache[key]

    def put(key, value):
        if value is None:
            return  # Never cache misses / errors
        if key in cache:
            cache.move_to_end(key)
        cache[key] = value
        while len(cache) > maxsize:
            cache.popitem(last=False)

    return get, put

CORS_ORIGIN = os.environ.get('CORS_ORIGIN', '*')
METHODOLOGY_URL = 'https://github.com/billkhiz-bit/london-flight-path-map/blob/master/METHODOLOGY.md'
METHODOLOGY_VERSION = '3.1'
API_VERSION = '1.0'
MAX_BATCH_SIZE = 100
# Parallel workers for /v1/score/batch. Each query is mostly waiting on
# postcodes.io (network-bound), so ~10 workers gives near-linear speedup
# on the typical 30-50 postcode batch without saturating any upstream.
BATCH_PARALLELISM = int(os.environ.get('BATCH_PARALLELISM', '10'))

SCHOOL_SCORE = {'outstanding': 10, 'excellent': 9, 'good': 6, 'mixed': 3}
TRANSPORT_SCORE = {'excellent': 10, 'good': 7, 'moderate': 4, 'poor': 2}
HEALTH_SCORE = {'excellent': 10, 'good': 7, 'moderate': 4}
IMPACT_TO_QUIET = {
    'low': 10.0, 'low-moderate': 7.5, 'moderate': 5.0,
    'moderate-high': 3.0, 'high': 1.5, 'severe': 0.0,
}

PERSONAS = {
    'balanced':  {'quiet': 0.30, 'afford': 0.25, 'growth': 0.20, 'live': 0.25},
    'family':    {'quiet': 0.20, 'afford': 0.20, 'growth': 0.10, 'live': 0.50},
    'investor':  {'quiet': 0.10, 'afford': 0.30, 'growth': 0.40, 'live': 0.20},
    'firsttime': {'quiet': 0.15, 'afford': 0.40, 'growth': 0.20, 'live': 0.25},
    'quietlife': {'quiet': 0.50, 'afford': 0.20, 'growth': 0.10, 'live': 0.20},
}

# London borough dataset — sourced from index.html BOROUGH_DATA_RAW + BOROUGH_EXTRA.
# Schema: impact (DEFRA Lden band), avgPrice (GBP), trend (% YoY),
# schools/transport/healthcare (categorical), crimeRate (per 1,000 ONS).
LONDON_BOROUGHS = {
    'Hounslow':              {'impact': 'severe',         'avgPrice': 465000,  'trend': 3.2, 'schools': 'good',      'crimeRate': 89,  'transport': 'good',      'healthcare': 'good'},
    'Hillingdon':            {'impact': 'severe',         'avgPrice': 480000,  'trend': 2.8, 'schools': 'good',      'crimeRate': 72,  'transport': 'good',      'healthcare': 'good'},
    'Richmond upon Thames':  {'impact': 'high',           'avgPrice': 825000,  'trend': 1.5, 'schools': 'excellent', 'crimeRate': 58,  'transport': 'good',      'healthcare': 'good'},
    'Ealing':                {'impact': 'high',           'avgPrice': 540000,  'trend': 4.1, 'schools': 'good',      'crimeRate': 88,  'transport': 'excellent', 'healthcare': 'good'},
    'Wandsworth':            {'impact': 'moderate',       'avgPrice': 680000,  'trend': 2.1, 'schools': 'excellent', 'crimeRate': 82,  'transport': 'excellent', 'healthcare': 'good'},
    'Lambeth':               {'impact': 'moderate',       'avgPrice': 560000,  'trend': 3.5, 'schools': 'good',      'crimeRate': 115, 'transport': 'excellent', 'healthcare': 'good'},
    'Lewisham':              {'impact': 'low-moderate',   'avgPrice': 445000,  'trend': 4.8, 'schools': 'good',      'crimeRate': 91,  'transport': 'good',      'healthcare': 'good'},
    'Greenwich':             {'impact': 'moderate',       'avgPrice': 430000,  'trend': 5.2, 'schools': 'good',      'crimeRate': 93,  'transport': 'good',      'healthcare': 'good'},
    'Tower Hamlets':         {'impact': 'low-moderate',   'avgPrice': 495000,  'trend': 2.0, 'schools': 'good',      'crimeRate': 120, 'transport': 'excellent', 'healthcare': 'excellent'},
    'Camden':                {'impact': 'low',            'avgPrice': 780000,  'trend': 1.2, 'schools': 'excellent', 'crimeRate': 130, 'transport': 'excellent', 'healthcare': 'excellent'},
    'Islington':             {'impact': 'low',            'avgPrice': 720000,  'trend': 1.8, 'schools': 'good',      'crimeRate': 125, 'transport': 'excellent', 'healthcare': 'good'},
    'Hackney':               {'impact': 'low',            'avgPrice': 590000,  'trend': 3.0, 'schools': 'good',      'crimeRate': 112, 'transport': 'excellent', 'healthcare': 'good'},
    'Barnet':                {'impact': 'low-moderate',   'avgPrice': 560000,  'trend': 3.1, 'schools': 'excellent', 'crimeRate': 74,  'transport': 'good',      'healthcare': 'good'},
    'Croydon':               {'impact': 'moderate',       'avgPrice': 395000,  'trend': 4.5, 'schools': 'good',      'crimeRate': 98,  'transport': 'good',      'healthcare': 'good'},
    'Bromley':               {'impact': 'low',            'avgPrice': 480000,  'trend': 3.8, 'schools': 'excellent', 'crimeRate': 65,  'transport': 'moderate',  'healthcare': 'good'},
    'Newham':                {'impact': 'moderate-high',  'avgPrice': 410000,  'trend': 5.8, 'schools': 'good',      'crimeRate': 108, 'transport': 'excellent', 'healthcare': 'good'},
    'Southwark':             {'impact': 'low-moderate',   'avgPrice': 530000,  'trend': 2.5, 'schools': 'good',      'crimeRate': 118, 'transport': 'excellent', 'healthcare': 'excellent'},
    'Hammersmith and Fulham':{'impact': 'moderate-high',  'avgPrice': 750000,  'trend': 1.0, 'schools': 'excellent', 'crimeRate': 96,  'transport': 'excellent', 'healthcare': 'good'},
    'Kensington and Chelsea':{'impact': 'moderate',       'avgPrice': 1350000, 'trend': 0.5, 'schools': 'excellent', 'crimeRate': 95,  'transport': 'excellent', 'healthcare': 'excellent'},
    'Brent':                 {'impact': 'low-moderate',   'avgPrice': 490000,  'trend': 4.0, 'schools': 'good',      'crimeRate': 92,  'transport': 'good',      'healthcare': 'good'},
    'Haringey':              {'impact': 'low',            'avgPrice': 545000,  'trend': 3.5, 'schools': 'good',      'crimeRate': 99,  'transport': 'good',      'healthcare': 'moderate'},
    'Waltham Forest':        {'impact': 'low',            'avgPrice': 480000,  'trend': 4.2, 'schools': 'good',      'crimeRate': 88,  'transport': 'good',      'healthcare': 'moderate'},
    'Merton':                {'impact': 'low-moderate',   'avgPrice': 560000,  'trend': 2.8, 'schools': 'good',      'crimeRate': 70,  'transport': 'good',      'healthcare': 'good'},
    'Redbridge':             {'impact': 'low',            'avgPrice': 445000,  'trend': 3.9, 'schools': 'excellent', 'crimeRate': 83,  'transport': 'good',      'healthcare': 'good'},
    'Enfield':               {'impact': 'low',            'avgPrice': 430000,  'trend': 4.3, 'schools': 'good',      'crimeRate': 85,  'transport': 'moderate',  'healthcare': 'moderate'},
    'Kingston upon Thames':  {'impact': 'low-moderate',   'avgPrice': 550000,  'trend': 2.0, 'schools': 'excellent', 'crimeRate': 62,  'transport': 'good',      'healthcare': 'good'},
    'Sutton':                {'impact': 'low',            'avgPrice': 415000,  'trend': 3.5, 'schools': 'excellent', 'crimeRate': 60,  'transport': 'moderate',  'healthcare': 'good'},
    'Westminster':           {'impact': 'moderate',       'avgPrice': 980000,  'trend': 0.8, 'schools': 'good',      'crimeRate': 175, 'transport': 'excellent', 'healthcare': 'excellent'},
    'City of London':        {'impact': 'low-moderate',   'avgPrice': 850000,  'trend': 1.0, 'schools': 'good',      'crimeRate': 190, 'transport': 'excellent', 'healthcare': 'good'},
    'Barking and Dagenham':  {'impact': 'low',            'avgPrice': 340000,  'trend': 5.8, 'schools': 'good',      'crimeRate': 105, 'transport': 'good',      'healthcare': 'moderate'},
    'Havering':              {'impact': 'low',            'avgPrice': 400000,  'trend': 4.0, 'schools': 'good',      'crimeRate': 72,  'transport': 'moderate',  'healthcare': 'good'},
    'Bexley':                {'impact': 'low',            'avgPrice': 380000,  'trend': 4.5, 'schools': 'good',      'crimeRate': 68,  'transport': 'moderate',  'healthcare': 'good'},
    'Harrow':                {'impact': 'low',            'avgPrice': 490000,  'trend': 3.2, 'schools': 'excellent', 'crimeRate': 70,  'transport': 'good',      'healthcare': 'good'},
}

# NYC borough dataset — sourced from index.html NYC_BOROUGH_DATA_RAW + NYC_BOROUGH_EXTRA.
# avgPrice in USD (not GBP). Crime rates use the same per-1,000 convention but
# are derived from NYPD CompStat / NYC ONS-equivalent denominators; cross-city
# comparison should be approached with caution (different methodologies).
NYC_BOROUGHS = {
    'Queens':         {'impact': 'severe',       'avgPrice': 620000,  'trend': 4.5, 'schools': 'good',      'crimeRate': 78,  'transport': 'excellent', 'healthcare': 'good'},
    'Brooklyn':       {'impact': 'high',         'avgPrice': 850000,  'trend': 3.8, 'schools': 'good',      'crimeRate': 82,  'transport': 'excellent', 'healthcare': 'excellent'},
    'Manhattan':      {'impact': 'moderate',     'avgPrice': 1200000, 'trend': 2.0, 'schools': 'excellent', 'crimeRate': 95,  'transport': 'excellent', 'healthcare': 'excellent'},
    'Bronx':          {'impact': 'low-moderate', 'avgPrice': 420000,  'trend': 5.5, 'schools': 'good',      'crimeRate': 110, 'transport': 'good',      'healthcare': 'good'},
    'Staten Island':  {'impact': 'low',          'avgPrice': 550000,  'trend': 3.0, 'schools': 'good',      'crimeRate': 52,  'transport': 'poor',      'healthcare': 'moderate'},
}

CITIES = {
    'london': {'boroughs': LONDON_BOROUGHS, 'currency': 'GBP'},
    'nyc':    {'boroughs': NYC_BOROUGHS,    'currency': 'USD'},
}

# NYC ZIP-to-borough mapping. ZIPs grouped per borough and flattened into a
# dict for O(1) lookup. Sourced from NYC OpenData ZCTA boundaries + USPS.
# Covers ~230 ZIPs across the 5 boroughs (residential + general use ZIPs;
# excludes some PO Box / single-building ZIPs that wouldn't be typed by a
# user). 9-digit ZIP+4 inputs are reduced to first 5 digits before lookup.
_NYC_ZIPS_BY_BOROUGH = {
    'Manhattan': [
        '10001','10002','10003','10004','10005','10006','10007','10009','10010',
        '10011','10012','10013','10014','10016','10017','10018','10019','10020',
        '10021','10022','10023','10024','10025','10026','10027','10028','10029',
        '10030','10031','10032','10033','10034','10035','10036','10037','10038',
        '10039','10040','10044','10065','10069','10075','10128','10280','10282',
    ],
    'Bronx': [
        '10451','10452','10453','10454','10455','10456','10457','10458','10459',
        '10460','10461','10462','10463','10464','10465','10466','10467','10468',
        '10469','10470','10471','10472','10473','10474','10475',
    ],
    'Staten Island': [
        '10301','10302','10303','10304','10305','10306','10307','10308','10309',
        '10310','10311','10312','10314',
    ],
    'Brooklyn': [
        '11201','11203','11204','11205','11206','11207','11208','11209','11210',
        '11211','11212','11213','11214','11215','11216','11217','11218','11219',
        '11220','11221','11222','11223','11224','11225','11226','11228','11229',
        '11230','11231','11232','11233','11234','11235','11236','11237','11238',
        '11239','11249',
    ],
    'Queens': [
        '11004','11005','11101','11102','11103','11104','11105','11106','11109',
        '11354','11355','11356','11357','11358','11359','11360','11361','11362',
        '11363','11364','11365','11366','11367','11368','11369','11370','11372',
        '11373','11374','11375','11377','11378','11379','11385','11411','11412',
        '11413','11414','11415','11416','11417','11418','11419','11420','11421',
        '11422','11423','11426','11427','11428','11429','11432','11433','11434',
        '11435','11436','11691','11692','11693','11694','11697',
    ],
}
NYC_ZIP_TO_BOROUGH = {
    zip5: borough
    for borough, zips in _NYC_ZIPS_BY_BOROUGH.items()
    for zip5 in zips
}

US_ZIP_PATTERN = re.compile(r'^\d{5}(-\d{4})?$')

# ---------------------------------------------------------------------------
# Airports + flight paths for per-postcode quiet calculation.
#
# Sourced verbatim from the consumer site (`index.html`) which has been
# scoring 290+ neighbourhoods in production for months. Lat/lon stored as
# (lat, lon) tuples for clean Haversine calls. Coordinates in the consumer
# site are [lon, lat] (GeoJSON convention); we transpose at port time so the
# Python code can call haversine_km(lat1, lon1, lat2, lon2) directly.
# ---------------------------------------------------------------------------

AIRPORTS_LONDON = [
    {'code': 'LHR', 'name': 'Heathrow',     'lat': 51.4700, 'lon': -0.4543},
    {'code': 'LGW', 'name': 'Gatwick',      'lat': 51.1537, 'lon': -0.1821},
    {'code': 'LCY', 'name': 'London City',  'lat': 51.5053, 'lon': 0.0553},
    {'code': 'STN', 'name': 'Stansted',     'lat': 51.8860, 'lon': 0.2389},
    {'code': 'LTN', 'name': 'Luton',        'lat': 51.8747, 'lon': -0.3684},
]

AIRPORTS_NYC = [
    {'code': 'JFK', 'name': 'John F. Kennedy', 'lat': 40.6413, 'lon': -73.7781},
    {'code': 'LGA', 'name': 'LaGuardia',       'lat': 40.7769, 'lon': -73.8740},
    {'code': 'EWR', 'name': 'Newark Liberty',  'lat': 40.6895, 'lon': -74.1745},
    {'code': 'TEB', 'name': 'Teterboro',       'lat': 40.8501, 'lon': -74.0608},
]

# Flight path geometry: list of paths, each with a sequence of (lat, lon)
# waypoints. Distance to nearest waypoint is used as proxy for distance to
# the corridor — same approach as the consumer site.
FLIGHT_PATHS_LONDON = [
    {'name': 'Lambourne Stack',  'airport': 'LHR', 'type': 'arrival',   'freq': 'high',   'coords': [(51.65,0.15),(51.62,0.08),(51.59,0.02),(51.565,-0.04),(51.54,-0.10),(51.52,-0.18),(51.505,-0.25),(51.495,-0.32),(51.485,-0.38),(51.4775,-0.428)]},
    {'name': 'Biggin Stack',     'airport': 'LHR', 'type': 'arrival',   'freq': 'high',   'coords': [(51.33,0.03),(51.35,-0.02),(51.37,-0.06),(51.39,-0.11),(51.41,-0.16),(51.425,-0.22),(51.44,-0.28),(51.45,-0.34),(51.46,-0.39),(51.4644,-0.428)]},
    {'name': 'Ockham Stack',     'airport': 'LHR', 'type': 'arrival',   'freq': 'high',   'coords': [(51.28,-0.45),(51.31,-0.44),(51.34,-0.435),(51.37,-0.435),(51.40,-0.435),(51.42,-0.435),(51.44,-0.435),(51.4644,-0.435)]},
    {'name': 'Bovingdon Stack',  'airport': 'LHR', 'type': 'arrival',   'freq': 'high',   'coords': [(51.72,-0.55),(51.68,-0.52),(51.64,-0.50),(51.60,-0.49),(51.56,-0.48),(51.53,-0.47),(51.505,-0.46),(51.4775,-0.45)]},
    {'name': 'Dep West',         'airport': 'LHR', 'type': 'departure', 'freq': 'high',   'coords': [(51.4775,-0.489),(51.48,-0.55),(51.485,-0.62),(51.49,-0.70),(51.495,-0.78)]},
    {'name': 'Dep SE (Detling)', 'airport': 'LHR', 'type': 'departure', 'freq': 'medium', 'coords': [(51.4775,-0.428),(51.47,-0.35),(51.46,-0.25),(51.445,-0.15),(51.43,-0.05),(51.41,0.05),(51.39,0.15)]},
    {'name': 'Dep NE (BPK)',     'airport': 'LHR', 'type': 'departure', 'freq': 'medium', 'coords': [(51.4775,-0.428),(51.49,-0.35),(51.51,-0.25),(51.53,-0.15),(51.55,-0.05),(51.57,0.05),(51.59,0.15)]},
    {'name': 'Approach East',    'airport': 'LCY', 'type': 'arrival',   'freq': 'medium', 'coords': [(51.48,0.20),(51.485,0.17),(51.488,0.14),(51.492,0.11),(51.497,0.09),(51.502,0.07),(51.5053,0.0553)]},
    {'name': 'Approach West',    'airport': 'LCY', 'type': 'arrival',   'freq': 'medium', 'coords': [(51.52,-0.02),(51.517,-0.005),(51.513,0.01),(51.51,0.025),(51.508,0.04),(51.5053,0.0553)]},
    {'name': 'Dep East',         'airport': 'LCY', 'type': 'departure', 'freq': 'medium', 'coords': [(51.5053,0.067),(51.505,0.09),(51.503,0.12),(51.498,0.16),(51.49,0.21)]},
    {'name': 'Approach N',       'airport': 'LGW', 'type': 'arrival',   'freq': 'medium', 'coords': [(51.35,-0.10),(51.32,-0.12),(51.28,-0.14),(51.23,-0.16),(51.19,-0.17),(51.1537,-0.182)]},
    {'name': 'Approach S',       'airport': 'LTN', 'type': 'arrival',   'freq': 'medium', 'coords': [(51.60,-0.30),(51.65,-0.32),(51.70,-0.34),(51.75,-0.35),(51.80,-0.36),(51.8747,-0.368)]},
]

FLIGHT_PATHS_NYC = [
    {'name': 'JFK 31L Arrival',          'airport': 'JFK', 'type': 'arrival',   'freq': 'high',   'coords': [(40.60,-73.60),(40.61,-73.64),(40.62,-73.68),(40.63,-73.72),(40.64,-73.76),(40.6413,-73.7781)]},
    {'name': 'JFK 13R Departure',        'airport': 'JFK', 'type': 'departure', 'freq': 'high',   'coords': [(40.6413,-73.7781),(40.62,-73.76),(40.60,-73.74),(40.58,-73.72),(40.56,-73.70)]},
    {'name': 'JFK 22L Arrival (ILS)',    'airport': 'JFK', 'type': 'arrival',   'freq': 'medium', 'coords': [(40.70,-73.70),(40.69,-73.72),(40.68,-73.74),(40.66,-73.76),(40.6413,-73.7781)]},
    {'name': 'LGA 31 Arrival',           'airport': 'LGA', 'type': 'arrival',   'freq': 'high',   'coords': [(40.72,-73.80),(40.73,-73.82),(40.74,-73.84),(40.76,-73.86),(40.7769,-73.8740)]},
    {'name': 'LGA 4 Departure',          'airport': 'LGA', 'type': 'departure', 'freq': 'high',   'coords': [(40.7769,-73.8740),(40.79,-73.87),(40.81,-73.86),(40.83,-73.85),(40.86,-73.84)]},
    {'name': 'LGA Expressway Visual 31', 'airport': 'LGA', 'type': 'arrival',   'freq': 'medium', 'coords': [(40.78,-73.95),(40.78,-73.93),(40.78,-73.91),(40.78,-73.89),(40.7769,-73.8740)]},
    {'name': 'EWR 4R Arrival',           'airport': 'EWR', 'type': 'arrival',   'freq': 'high',   'coords': [(40.62,-74.10),(40.64,-74.12),(40.66,-74.14),(40.68,-74.16),(40.6895,-74.1745)]},
    {'name': 'EWR 22L Departure',        'airport': 'EWR', 'type': 'departure', 'freq': 'medium', 'coords': [(40.6895,-74.1745),(40.68,-74.18),(40.66,-74.19),(40.64,-74.20),(40.62,-74.22)]},
]

CITY_GEOMETRY = {
    'london': {'airports': AIRPORTS_LONDON, 'paths': FLIGHT_PATHS_LONDON, 'major_airport': 'LHR', 'secondary_airport': None},
    'nyc':    {'airports': AIRPORTS_NYC,    'paths': FLIGHT_PATHS_NYC,    'major_airport': 'JFK', 'secondary_airport': 'LGA'},
}

# NYC ZIP-to-centroid lookup. Sourced from index.html NYC_AREA_MAP — first
# neighbourhood per ZIP used as a representative centroid. Where multiple
# neighbourhoods share a ZIP (e.g. 10012 SoHo / NoHo / Nolita), we keep the
# first encountered and accept ~1km of within-ZIP imprecision.
# Coverage: ~110 ZIPs across the 5 NYC boroughs. ZIPs in NYC_ZIP_TO_BOROUGH
# that aren't here fall back to borough-aggregate scoring.
NYC_ZIP_CENTROIDS = {
    # Queens
    '11102': (40.7724, -73.9234), '11101': (40.7443, -73.9249), '11354': (40.7596, -73.8303),
    '11372': (40.7465, -73.8915), '11375': (40.7185, -73.8448), '11432': (40.7028, -73.7925),
    '11104': (40.7434, -73.9126), '11377': (40.7454, -73.9028), '11373': (40.7360, -73.8780),
    '11368': (40.7465, -73.8623), '11374': (40.7263, -73.8616), '11415': (40.7084, -73.8272),
    '11361': (40.7621, -73.7716), '11365': (40.7348, -73.7911), '11357': (40.7927, -73.8085),
    '11356': (40.7862, -73.8398), '11385': (40.7043, -73.8963), '11378': (40.7233, -73.9126),
    '11379': (40.7176, -73.8811), '11414': (40.6571, -73.8430), '11416': (40.6844, -73.8464),
    '11420': (40.6748, -73.8120), '11418': (40.6995, -73.8313), '11421': (40.6888, -73.8564),
    '11435': (40.7088, -73.8151), '11362': (40.7663, -73.7498), '11363': (40.7637, -73.7327),
    '11693': (40.5864, -73.8158), '11691': (40.6027, -73.7551), '11423': (40.7118, -73.7617),
    '11412': (40.6896, -73.7610), '11422': (40.6605, -73.7358), '11105': (40.7780, -73.9112),
    # Brooklyn
    '11211': (40.7128, -73.9530), '11215': (40.6710, -73.9777), '11201': (40.7033, -73.9887),
    '11221': (40.6905, -73.9252), '11231': (40.6734, -73.9999), '11216': (40.6810, -73.9418),
    '11213': (40.6694, -73.9340), '11238': (40.6773, -73.9650), '11217': (40.6848, -73.9835),
    '11205': (40.6897, -73.9625), '11222': (40.7274, -73.9510), '11209': (40.6340, -74.0286),
    '11220': (40.6454, -74.0104), '11214': (40.6025, -73.9939), '11219': (40.6341, -73.9916),
    '11226': (40.6453, -73.9597), '11218': (40.6385, -73.9722), '11235': (40.5912, -73.9445),
    '11224': (40.5755, -73.9707), '11234': (40.6177, -73.9210), '11236': (40.6388, -73.8968),
    '11207': (40.6594, -73.8827), '11225': (40.6592, -73.9518), '11230': (40.6209, -73.9600),
    '11228': (40.6215, -74.0093),
    # Manhattan
    '10027': (40.8116, -73.9465), '10021': (40.7694, -73.9595), '10011': (40.7418, -74.0002),
    '10014': (40.7336, -74.0027), '10012': (40.7233, -73.9985), '10013': (40.7163, -74.0086),
    '10003': (40.7265, -73.9815), '10002': (40.7157, -73.9863), '10019': (40.7644, -73.9835),
    '10024': (40.7870, -73.9754), '10033': (40.8472, -73.9377), '10034': (40.8677, -73.9212),
    '10005': (40.7075, -74.0089), '10280': (40.7112, -74.0155), '10010': (40.7367, -73.9844),
    '10016': (40.7416, -73.9783), '10025': (40.8100, -73.9626), '10031': (40.8253, -73.9476),
    '10029': (40.7918, -73.9432), '10028': (40.7765, -73.9504), '10001': (40.7542, -74.0005),
    # Bronx
    '10471': (40.8968, -73.9094), '10454': (40.8057, -73.9176), '10458': (40.8615, -73.8885),
    '10461': (40.8527, -73.8332), '10451': (40.8202, -73.9231), '10474': (40.8093, -73.8817),
    '10452': (40.8366, -73.9271), '10453': (40.8535, -73.9199), '10463': (40.8788, -73.9037),
    '10468': (40.8712, -73.8886), '10470': (40.8959, -73.8674), '10466': (40.8938, -73.8551),
    '10475': (40.8743, -73.8273), '10465': (40.8228, -73.8209), '10462': (40.8524, -73.8546),
    '10473': (40.8265, -73.8568), '10457': (40.8468, -73.9006), '10464': (40.8469, -73.7868),
    # Staten Island
    '10301': (40.6433, -74.0764), '10314': (40.6016, -74.1132), '10306': (40.5734, -74.1162),
    '10308': (40.5545, -74.1516), '10307': (40.5078, -74.2382), '10304': (40.6266, -74.0794),
    '10302': (40.6343, -74.1361), '10310': (40.6270, -74.1165), '10312': (40.5450, -74.1644),
    '10305': (40.6028, -74.0841),
}

# DynamoDB table for v3.1 DEFRA Lden raster samples. When populated by the
# offline data-loader script (see scripts/load_defra_raster.py — to add),
# the calc_score path checks this table first for postcode-level Lden values
# sampled directly from DEFRA's GeoTIFF. If the DynamoDB lookup misses or the
# table isn't yet populated, falls back to v3.0 Haversine. This means the
# Lambda code path is forward-compatible: it works with or without the
# raster data loaded, and silently upgrades when the data lands.
NOISE_RASTER_TABLE = os.environ.get('NOISE_RASTER_TABLE', '')


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two (lat, lon) points in kilometres.
    Standard Haversine formula; used for airport and flight-path proximity."""
    r = 6371.0
    p = math.pi / 180.0
    a = (
        0.5 - math.cos((lat2 - lat1) * p) / 2
        + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    )
    return r * 2 * math.asin(math.sqrt(a))


_raster_cache_get, _raster_cache_put = _make_lru(2048)


def _lookup_lden_raster(postcode_clean):
    """v3.1 — Look up DEFRA Lden raster sample for a postcode in DynamoDB.

    Returns the Lden value (in dB) if the table is populated and contains
    this postcode; returns None otherwise. The table is populated by an
    offline data-loader script that samples the DEFRA GeoTIFF at every UK
    postcode centroid (one-time batch, ~1.7M postcodes, runs overnight).

    Negative results (no NOISE_RASTER_TABLE configured, item missing,
    DDB error) are NOT cached — see _make_lru. Positive results live for
    the warm-container lifetime (~15 min) up to 2048 entries LRU.
    """
    if not NOISE_RASTER_TABLE or not postcode_clean:
        return None
    cached = _raster_cache_get(postcode_clean)
    if cached is not None:
        return cached

    try:
        import boto3  # local import — only needed when raster table configured
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        return None

    try:
        ddb = boto3.client('dynamodb', region_name=os.environ.get('AWS_REGION', 'eu-west-2'))
        result = ddb.get_item(
            TableName=NOISE_RASTER_TABLE,
            Key={'postcode': {'S': postcode_clean}},
            ProjectionExpression='ldenDb',
        )
    except (BotoCoreError, ClientError) as exc:
        logger.warning('DDB raster lookup failed for %s: %s', postcode_clean, exc)
        return None

    item = result.get('Item') or {}
    lden = item.get('ldenDb', {}).get('N')
    if not lden:
        return None
    try:
        value = float(lden)
    except (TypeError, ValueError):
        return None
    _raster_cache_put(postcode_clean, value)
    return value


def lden_db_to_quiet(lden):
    """Convert dB Lden to a 0-10 quiet score using the same band mapping
    documented in METHODOLOGY.md §4.1. Used by v3.1 raster path."""
    if lden is None:
        return None
    if lden < 55:  return 10.0
    if lden < 60:  return 7.5
    if lden < 65:  return 5.0
    if lden < 70:  return 3.0
    if lden < 75:  return 1.5
    return 0.0


def calc_postcode_quiet(lat, lon, city, postcode_clean=None):
    """Per-postcode quiet score (0-10).

    Resolution chain (highest to lowest precision):
      1. v3.1 DEFRA raster sample from DynamoDB (when table populated)
      2. v3.0 Haversine to airports + flight-path geometry
      3. Borough-aggregate Lden band (caller's fallback if this returns None)

    Returns the quiet score as a float, or None if the city has no
    geometry data. The caller (calc_score) uses the borough-aggregate as
    final fallback when this returns None.
    """
    # v3.1 first: direct raster sample if available
    raster_lden = _lookup_lden_raster(postcode_clean) if postcode_clean else None
    if raster_lden is not None:
        return lden_db_to_quiet(raster_lden)

    # v3.0: Haversine to airports + flight paths
    geo = CITY_GEOMETRY.get(city)
    if not geo:
        return None

    # 1. Distance to nearest airport
    airport_dists = [
        (ap['code'], haversine_km(lat, lon, ap['lat'], ap['lon']))
        for ap in geo['airports']
    ]
    nearest_ap_dist = min(d for _, d in airport_dists)

    noise_score = 0.0
    if   nearest_ap_dist < 3:  noise_score += 5
    elif nearest_ap_dist < 6:  noise_score += 4
    elif nearest_ap_dist < 10: noise_score += 3
    elif nearest_ap_dist < 15: noise_score += 2
    elif nearest_ap_dist < 20: noise_score += 1

    # 2. Distance to nearest flight path waypoint
    min_path_dist = float('inf')
    for path in geo['paths']:
        for plat, plon in path['coords']:
            d = haversine_km(lat, lon, plat, plon)
            if d < min_path_dist:
                min_path_dist = d

    if   min_path_dist < 1: noise_score += 4
    elif min_path_dist < 2: noise_score += 3
    elif min_path_dist < 4: noise_score += 2
    elif min_path_dist < 6: noise_score += 1

    # 3. Major-airport bonus (matches consumer site)
    major_dist = next((d for code, d in airport_dists if code == geo['major_airport']), None)
    if major_dist is not None and major_dist < 15:
        noise_score += 2

    secondary = geo.get('secondary_airport')
    if secondary:
        secondary_dist = next((d for code, d in airport_dists if code == secondary), None)
        if secondary_dist is not None and secondary_dist < 10:
            noise_score += 1

    quiet = max(0.0, min(10.0, 10.0 - noise_score))
    return quiet

# Aliases for boroughs whose canonical name differs from postcodes.io's
# admin_district output, or common variants.
BOROUGH_ALIASES = {
    'Barking and Dagenham': 'Barking and Dagenham',
    'Barking': 'Barking and Dagenham',
    'City of London Corporation': 'City of London',
    'Westminster City': 'Westminster',
}

SOURCES = [
    'EPC data: MHCLG, Open Government Licence v3.0',
    'Sold prices: HM Land Registry, Open Government Licence v3.0',
    'Postcode resolution: postcodes.io (Open Government Licence v3.0)',
    'Borough metadata: ONS, Home Office, Department for Education (Open Government Licence v3.0)',
    'Aviation noise context: DEFRA strategic noise mapping, Open Government Licence v3.0',
]

# Per-component data lineage. Auditable provenance for each scoring input —
# B2B audit teams ask "where did this number come from" component-by-component
# and this surfaces the answer at the response level. The /v1/score endpoint
# does NOT call OpenSky directly (consumer site does); aviation noise context
# for the API comes from pre-computed DEFRA borough-aggregate Lden bands.
SOURCE_BREAKDOWN = {
    'quiet': 'DEFRA Strategic Noise Mapping (Round 4, 2022). Resolution chain: v3.1 direct raster sample at postcode centroid (when populated) → v3.0 Haversine to airports + flight-path geometry → v2.x borough-aggregate Lden band. The chosen resolution is reported in context.quietResolution.',
    'afford': 'HM Land Registry House Price Index (HPI) — borough cohort min-max scaling',
    'growth': 'HM Land Registry House Price Index (HPI) — annualised price trend, cohort-relative',
    'live': 'ONS + Home Office + DfE + TfL + NHS — composite weighted (schools 35% + crime 30% + transport 25% + healthcare 10%); methodologically aligned with English Indices of Deprivation domains',
}


def crime_to_score(rate):
    if rate is None:
        return 5.0
    return max(0.0, min(10.0, 10.0 - (rate - 50) / 15.0))


def get_live_score(bd):
    sch = SCHOOL_SCORE.get(bd.get('schools'), 5)
    crm = crime_to_score(bd.get('crimeRate'))
    trn = TRANSPORT_SCORE.get(bd.get('transport'), 5)
    hlt = HEALTH_SCORE.get(bd.get('healthcare'), 5)
    return round((sch * 0.35 + crm * 0.30 + trn * 0.25 + hlt * 0.10) * 10) / 10


def calc_score(borough_name, city, weights, lat=None, lon=None, postcode_clean=None):
    """Compute Sky Score for a borough/postcode.

    Resolution chain for the quiet component:
      v3.1 — DEFRA raster sample at postcode centroid (if table populated)
      v3.0 — Haversine to airports + flight-path geometry (if lat/lon given)
      v2.x — Borough-aggregate Lden band lookup (always available as fallback)

    See METHODOLOGY.md §4.1 (borough), §4.5 (postcode Haversine), §4.6 (raster).
    """
    boroughs = CITIES[city]['boroughs']
    bd = boroughs[borough_name]

    borough_quiet = IMPACT_TO_QUIET.get(bd['impact'], 5.0)
    quiet_source = 'borough'

    if lat is not None and lon is not None:
        # Try raster first (v3.1), Haversine second (v3.0), borough last
        raster_lden = _lookup_lden_raster(postcode_clean) if postcode_clean else None
        if raster_lden is not None:
            quiet = lden_db_to_quiet(raster_lden)
            quiet_source = 'raster'
        else:
            postcode_quiet = calc_postcode_quiet(lat, lon, city, postcode_clean)
            if postcode_quiet is not None:
                quiet = postcode_quiet
                quiet_source = 'postcode'
            else:
                quiet = borough_quiet
    else:
        quiet = borough_quiet

    prices = [b['avgPrice'] for b in boroughs.values()]
    max_price, min_price = max(prices), min(prices)
    if max_price == min_price:
        afford = 5.0
    else:
        afford = ((max_price - bd['avgPrice']) / (max_price - min_price)) * 10

    trends = [b['trend'] for b in boroughs.values()]
    max_trend = max(trends) or 1.0
    growth = (bd['trend'] / max_trend) * 10

    live = get_live_score(bd)

    total = (
        quiet * weights['quiet']
        + afford * weights['afford']
        + growth * weights['growth']
        + live * weights['live']
    )

    currency_field = 'avgPriceUsd' if CITIES[city]['currency'] == 'USD' else 'avgPriceGbp'

    return {
        'score': round(total * 10) / 10,
        'components': {
            'quiet': round(quiet * 10) / 10,
            'afford': round(afford * 10) / 10,
            'growth': round(growth * 10) / 10,
            'live': round(live * 10) / 10,
        },
        'context': {
            currency_field: bd['avgPrice'],
            'priceTrendPct': bd['trend'],
            'noiseImpactBand': bd['impact'],
            'quietResolution': quiet_source,
        },
    }


_postcode_cache_get, _postcode_cache_put = _make_lru(512)


def _fetch_postcode(clean):
    """Fetch from postcodes.io — no caching, no normalisation. Returns
    parsed result dict on success, None on transient/permanent failure."""
    if not clean:
        return None
    url = f'https://api.postcodes.io/postcodes/{quote(clean)}'
    req = Request(url, headers={'Accept': 'application/json'})
    try:
        with urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read().decode())
    except (HTTPError, URLError, TimeoutError) as exc:
        logger.warning('postcodes.io lookup failed for %s: %s', clean, exc)
        return None
    except json.JSONDecodeError as exc:
        logger.warning('postcodes.io returned non-JSON for %s: %s', clean, exc)
        return None
    if payload.get('status') != 200:
        return None
    return payload.get('result')


def lookup_postcode(postcode):
    """Resolve UK postcode → admin_district via postcodes.io (free, OGL).

    Cached per warm container (~15 min). Misses and errors are NOT cached
    so a transient postcodes.io outage does not poison the cache."""
    clean = postcode.strip().replace(' ', '').upper()
    if not clean:
        return None
    cached = _postcode_cache_get(clean)
    if cached is not None:
        return cached
    result = _fetch_postcode(clean)
    if result is not None:
        _postcode_cache_put(clean, result)
    return result


def normalise_borough(name, city):
    if not name:
        return None
    boroughs = CITIES[city]['boroughs']
    if name in boroughs:
        return name
    aliased = BOROUGH_ALIASES.get(name)
    if aliased and aliased in boroughs:
        return aliased
    return None


def parse_weights(raw):
    """Parse '?weights=quiet:0.5,afford:0.2,growth:0.1,live:0.2'.

    Returns dict, or None if unparsable. Sum must be ~1 (within 1%).
    """
    if not raw:
        return None
    if isinstance(raw, dict):
        result = raw
    else:
        try:
            parts = raw.split(',')
            result = {}
            for part in parts:
                key, value = part.split(':')
                result[key.strip()] = float(value.strip())
        except (ValueError, AttributeError):
            return None

    if set(result.keys()) != {'quiet', 'afford', 'growth', 'live'}:
        return None
    try:
        result = {k: float(v) for k, v in result.items()}
    except (ValueError, TypeError):
        return None
    total = sum(result.values())
    if not (0.99 <= total <= 1.01):
        return None
    return result


RESPONSE_FIELDS = {
    'score', 'components', 'context', 'location', 'persona', 'weights',
    'methodologyVersion', 'methodologyUrl', 'apiVersion', 'generatedAt',
    'sources', 'sourceBreakdown', 'plannedComponents',
}


def parse_include(raw):
    """Parse `?include=score,components,context` into a set of allowed
    response fields. Returns None when no filter (full response). Unknown
    fields are ignored silently. Always-included meta fields stay regardless."""
    if not raw:
        return None
    requested = {p.strip() for p in raw.split(',') if p.strip()}
    if not requested:
        return None
    return requested & RESPONSE_FIELDS


def filter_response(body, include):
    """Apply an include-filter to a response body. Always retains meta
    fields (apiVersion, methodologyVersion, generatedAt, sources)."""
    if not include:
        return body
    always = {'apiVersion', 'methodologyVersion', 'methodologyUrl', 'generatedAt', 'sources'}
    keep = include | always
    return {k: v for k, v in body.items() if k in keep}


def resolve_query(query):
    """Run a single score query. Returns the response body or an error dict."""
    postcode = (query.get('postcode') or '').strip()
    borough_input = (query.get('borough') or '').strip()
    city = (query.get('city') or 'london').strip().lower()
    persona = (query.get('persona') or 'balanced').strip().lower()
    weights_override = parse_weights(query.get('weights'))
    include = parse_include(query.get('include'))

    if city not in CITIES:
        return {
            'error': f'Unsupported city: {city}',
            'supportedCities': sorted(CITIES.keys()),
        }, 400

    if not postcode and not borough_input:
        return {
            'error': 'Provide either postcode or borough.',
            'example': '/v1/score?postcode=SW11+1AA',
        }, 400

    location_meta = {'city': city}
    if postcode:
        # US ZIP auto-detection — 5 digits with optional +4 suffix.
        # If detected and in the NYC map, override city to 'nyc' and use
        # the static lookup (skipping the UK-only postcodes.io call).
        if US_ZIP_PATTERN.match(postcode):
            zip5 = postcode[:5]
            if zip5 in NYC_ZIP_TO_BOROUGH:
                city = 'nyc'
                borough = NYC_ZIP_TO_BOROUGH[zip5]
                location_meta = {
                    'city': 'nyc',
                    'postcode': postcode,
                    'borough': borough,
                    'region': 'New York City',
                }
                # v3.1 — if we have a centroid for this ZIP, surface lat/lon
                # so the per-postcode Haversine layer kicks in for NYC too.
                centroid = NYC_ZIP_CENTROIDS.get(zip5)
                if centroid:
                    location_meta['latitude'] = centroid[0]
                    location_meta['longitude'] = centroid[1]
            else:
                return {
                    'error': f'ZIP not currently supported: {postcode}',
                    'note': 'Sky Score supports NYC ZIPs only at present (Manhattan, Brooklyn, Queens, Bronx, Staten Island).',
                    'supportedNycBoroughs': sorted(NYC_BOROUGHS.keys()),
                }, 404
        else:
            # UK postcode path — postcodes.io resolves to a London borough.
            if city != 'london':
                return {
                    'error': f'Postcode resolution is UK-only for non-NYC ZIPs. For {city} use ?borough=, or pass a 5-digit US ZIP for NYC auto-detection.',
                }, 400
            pc = lookup_postcode(postcode)
            if not pc:
                return {
                    'error': f'Postcode not recognised by postcodes.io: {postcode}',
                }, 404
            borough = normalise_borough(pc.get('admin_district'), city)
            location_meta.update({
                'postcode': pc.get('postcode'),
                'borough': borough,
                'longitude': pc.get('longitude'),
                'latitude': pc.get('latitude'),
                'region': pc.get('region'),
            })
    else:
        borough = normalise_borough(borough_input, city)
        location_meta['borough'] = borough

    if not borough or borough not in CITIES[city]['boroughs']:
        return {
            'error': f'Borough not currently supported in {city}.',
            'attemptedBorough': borough_input or location_meta.get('borough'),
            'supportedBoroughs': sorted(CITIES[city]['boroughs'].keys()),
        }, 404

    if weights_override:
        weights = weights_override
        persona_label = 'custom'
    elif persona in PERSONAS:
        weights = PERSONAS[persona]
        persona_label = persona
    else:
        weights = PERSONAS['balanced']
        persona_label = 'balanced'

    # Per-postcode quiet uses the resolved lat/lon when available
    # (postcodes.io for UK postcodes, NYC_ZIP_CENTROIDS for NYC ZIPs).
    lat = location_meta.get('latitude')
    lon = location_meta.get('longitude')
    # postcode_clean is used by the v3.1 raster lookup as the DynamoDB key
    pc_clean = (location_meta.get('postcode') or postcode or '').strip().upper().replace(' ', '')
    score_data = calc_score(borough, city, weights, lat=lat, lon=lon, postcode_clean=pc_clean)

    body = {
        **score_data,
        'location': location_meta,
        'persona': persona_label,
        'weights': weights,
        'methodologyVersion': METHODOLOGY_VERSION,
        'methodologyUrl': METHODOLOGY_URL,
        'apiVersion': API_VERSION,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'sources': SOURCES,
        'sourceBreakdown': SOURCE_BREAKDOWN,
    }
    # Roadmap-visible placeholder components — let prospects see what's planned
    # before they ask. Each entry has a status flag so integrators don't try
    # to consume placeholder data as if it were live.
    body['plannedComponents'] = {
        'flood': {'status': 'planned', 'source': 'Environment Agency Flood Map for Planning (planned, OGL v3.0)', 'eta': 'roadmap'},
        'airQuality': {'status': 'planned', 'source': 'DEFRA Daily Air Quality Index (planned, OGL v3.0)', 'eta': 'roadmap'},
        'epcDistribution': {'status': 'planned', 'source': 'MHCLG Get Energy Performance Data (currently in /epc; planned in /v1/score)', 'eta': 'roadmap'},
        'crimeBreakdown': {'status': 'planned', 'source': 'ONS LSOA-level crime by category (planned, OGL v3.0)', 'eta': 'roadmap'},
    }
    return filter_response(body, include), 200


def handle_options():
    """CORS preflight response. Open to any origin — the GET/POST are
    API-key gated, so origin restriction adds no security."""
    return {
        'statusCode': 200,
        'headers': cors_headers(),
        'body': '',
    }


def handle_regions(event):
    """GET /v1/regions — discovery endpoint listing supported geographies.
    Used by integrators to know what's queryable without scraping responses."""
    return response(200, {
        'cities': [
            {
                'id': 'london',
                'name': 'London',
                'country': 'United Kingdom',
                'currency': 'GBP',
                'postcodeFormat': 'UK postcode (e.g. SW11 1AA)',
                'postcodeResolver': 'postcodes.io',
                'boroughCount': len(LONDON_BOROUGHS),
                'boroughs': sorted(LONDON_BOROUGHS.keys()),
            },
            {
                'id': 'nyc',
                'name': 'New York City',
                'country': 'United States',
                'currency': 'USD',
                'postcodeFormat': '5-digit US ZIP (e.g. 10001), with optional +4 suffix',
                'postcodeResolver': 'static ZIP-to-borough lookup',
                'boroughCount': len(NYC_BOROUGHS),
                'boroughs': sorted(NYC_BOROUGHS.keys()),
                'supportedZipCount': len(NYC_ZIP_TO_BOROUGH),
            },
        ],
        'apiVersion': API_VERSION,
        'methodologyVersion': METHODOLOGY_VERSION,
        'methodologyUrl': METHODOLOGY_URL,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
    })


def handle_get(event):
    path = (event.get('path') or '').rstrip('/')
    if path.endswith('/regions'):
        return handle_regions(event)
    params = event.get('queryStringParameters') or {}
    body, status = resolve_query(params)
    return response(status, body)


def handle_batch(event):
    raw_body = event.get('body') or ''
    if event.get('isBase64Encoded'):
        import base64
        try:
            raw_body = base64.b64decode(raw_body).decode()
        except (ValueError, UnicodeDecodeError) as exc:
            logger.warning('Invalid base64 body: %s', exc)
            return response(400, {'error': 'Invalid base64-encoded body'})

    try:
        payload = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError:
        return response(400, {'error': 'Invalid JSON body'})

    queries = payload.get('queries')
    if not isinstance(queries, list):
        return response(400, {
            'error': 'Body must contain a "queries" array.',
            'example': {
                'queries': [
                    {'postcode': 'SW11 1AA', 'persona': 'balanced'},
                    {'postcode': 'TW3 4DX', 'persona': 'family'},
                    {'borough': 'Hackney', 'city': 'london',
                     'weights': {'quiet': 0.5, 'afford': 0.2, 'growth': 0.1, 'live': 0.2}},
                ],
            },
        })

    if len(queries) == 0:
        return response(400, {'error': 'queries array is empty.'})

    if len(queries) > MAX_BATCH_SIZE:
        return response(400, {
            'error': f'Batch size exceeds limit of {MAX_BATCH_SIZE} queries.',
            'submitted': len(queries),
            'limit': MAX_BATCH_SIZE,
        })

    # Parallel resolution. Each `resolve_query` call hits postcodes.io
    # (network-bound, ~100-500 ms p95). Sequential at MAX_BATCH_SIZE=100
    # would blow the 10s Lambda timeout above ~30 unique postcodes.
    # ThreadPoolExecutor with bounded workers gives us request-level
    # concurrency without overwhelming postcodes.io (which is generous
    # but unspecified on per-IP limits) or hitting Python GIL pressure.
    from concurrent.futures import ThreadPoolExecutor

    indexed_queries = list(enumerate(queries))

    def run_one(item):
        idx, query = item
        if not isinstance(query, dict):
            return idx, ({'error': 'Query must be an object.'}, 400)
        return idx, resolve_query(query)

    with ThreadPoolExecutor(max_workers=BATCH_PARALLELISM) as ex:
        outcomes = list(ex.map(run_one, indexed_queries))

    # Restore original order — ex.map preserves order so we don't strictly
    # need this, but being explicit makes future refactors safer.
    outcomes.sort(key=lambda kv: kv[0])

    results = []
    success = 0
    error = 0
    for idx, (body, status) in outcomes:
        result = {'queryIndex': idx, 'status': status}
        if status == 200:
            result.update(body)
            success += 1
        else:
            result['error'] = body.get('error', 'Unknown error')
            for k in ('attemptedBorough', 'supportedBoroughs', 'supportedCities', 'example'):
                if k in body:
                    result[k] = body[k]
            error += 1
        results.append(result)

    return response(200, {
        'totalQueries': len(queries),
        'successCount': success,
        'errorCount': error,
        'apiVersion': API_VERSION,
        'methodologyVersion': METHODOLOGY_VERSION,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'sources': SOURCES,
        'results': results,
    })


def handler(event, context):
    method = (event.get('httpMethod') or 'GET').upper()
    try:
        if method == 'OPTIONS':
            return handle_options()
        if method == 'POST':
            return handle_batch(event)
        return handle_get(event)
    except Exception as exc:  # final guard — never let internals leak
        logger.exception('Unhandled exception in score handler: %s', exc)
        return response(500, {'error': 'Internal server error'})


def cors_headers():
    return {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type,X-Api-Key',
        'Access-Control-Max-Age': '86400',
    }


def response(status, body):
    return {
        'statusCode': status,
        'headers': {
            'Content-Type': 'application/json',
            **cors_headers(),
        },
        'body': json.dumps(body),
    }
