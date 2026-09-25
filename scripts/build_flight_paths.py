"""Derive the scored flight-path corridors from the UK AIP, not from a sketch.

WHY THIS EXISTS
---------------
Until 2026-09-26 London's corridors were HAND-DRAWN, and several were wrong in
a way anyone who flies would spot at once (a Reddit reply said so: "look up the
SIDs and arrival charts... nobody turns that early"). Ockham and Bovingdon ran
due north-south straight into two east-west runways; real arrivals are
radar-vectored from the holds onto a straight-in final. The departures fanned
off the runway end where the published routes run straight ahead first.

Every corridor is now derived from the UK Aeronautical Information Publication,
the document pilots fly, and the procedure it came from travels with it in
`data/flight-procedures.json` (checked in, so `--check` needs no network):

  * FINAL APPROACHES, every runway end: the extended centreline from the
    runway threshold out to where an aircraft on the published glide path
    passes FINAL_TOP_FT. Threshold, true bearing and glide angle all come from
    the airport's AD 2.12 / AD 2.19 tables. Heathrow's 3.0 deg gives 9.4 NM,
    between the AIP's own 2,500 ft day and 10 NM night joining rules; London
    City's 5.5 deg gives 5.1 NM.
  * DEPARTURES: the published route, cut at DEPARTURE_KM along track.
    - RNAV airports (London City and most of the UK): the SID CODING TABLES,
      which list every waypoint with its coordinates in the order flown.
    - Heathrow: its SIDs are conventional, so the Noise Preferential Routes in
      AD 2.21 paragraph 8 are geometrised from their wording ("straight ahead
      to intercept LON VOR R255 until LON D7, then turn right..."). Radials
      are magnetic, corrected by the AIP's own published variation.
  * ARRIVALS BETWEEN THE HOLD AND THE FINAL ARE NOT DRAWN, and that is the
    honest answer rather than an omission: EGLL AD 2.22 says that segment is
    "flown under direction from the Radar Controller". There is no published
    track, so drawing one would reinstate the defect this file removes.

WHAT IT CANNOT KNOW
-------------------
Above 4,000 ft ATC may turn a departure off its route, so real tracks fan out
beyond these lines; DEPARTURE_KM keeps only the part the routes govern. The
geometry carries no traffic share either - a route flown twice a day and one
flown every two minutes are the same line. The corridor PENALTY is fitted
against DEFRA's measured postcodes separately (CORRIDOR_WEIGHT in the score
Lambda), which is where the size of the effect is decided.

Usage
-----
    python scripts/build_flight_paths.py --fetch    # network: AIP -> data/flight-procedures.json
    python scripts/build_flight_paths.py --check    # offline, blocking: both holders == the file
    python scripts/build_flight_paths.py --write    # offline: rewrite both holders from the file
"""

from __future__ import annotations

import argparse
import html as html_lib
import io
import json
import math
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROCEDURES = ROOT / 'data' / 'flight-procedures.json'
LAMBDA = ROOT / 'backend' / 'lambdas' / 'score' / 'app.py'
SITE = ROOT / 'index.html'

AIRAC = '2026-09-03'
EAIP = f'https://www.aurora.nats.co.uk/htmlAIP/Publications/{AIRAC}-AIRAC/html/eAIP/'
GRAPHICS = f'https://www.aurora.nats.co.uk/htmlAIP/Publications/{AIRAC}-AIRAC/graphics/'
# The host answers 403 without a browser User-Agent, like DEFRA's.
UA = {'User-Agent': 'Mozilla/5.0'}

NM_KM = 1.852
FT_KM = 0.0003048
STEP_KM = 1.0  # every corridor in the repo is resampled to 1 km; see CLAUDE.md
DEPARTURE_KM = 20.0
FINAL_TOP_FT = 3000.0

# Airports, and the city whose corridor list each one feeds. The city key is
# the score Lambda's; the constants are the two holders' names for its list.
AIRPORTS = {
    'LHR': {'city': 'london', 'icao': 'EGLL', 'departures': 'npr-text'},
    'LCY': {'city': 'london', 'icao': 'EGLC', 'departures': 'rnav-coding'},
}
HOLDERS = {
    'london': {'lambda': 'FLIGHT_PATHS_LONDON', 'site': 'FLIGHT_PATHS'},
}
# How often each final is in use cannot be read from the AIP; it only sets the
# stroke width on the map. Heathrow and London City both land westerly on
# roughly 70% of days, so the westerly final is drawn heavier.
BUSY_FINALS = {'27', '27L', '27R'}


# --------------------------------------------------------------------------
# Geometry: a local plane in km around a reference point is plenty at 25 km.
# --------------------------------------------------------------------------
class Plane:
    def __init__(self, lat0, lon0):
        self.lat0, self.lon0 = lat0, lon0
        self.kx = 111.32 * math.cos(math.radians(lat0))
        self.ky = 110.57

    def xy(self, lat, lon):
        return ((lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky)

    def ll(self, p):
        return (self.lat0 + p[1] / self.ky, self.lon0 + p[0] / self.kx)


def unit(brg):
    b = math.radians(brg)
    return (math.sin(b), math.cos(b))


def add(p, v, k=1.0):
    return (p[0] + v[0] * k, p[1] + v[1] * k)


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def norm(v):
    return math.hypot(v[0], v[1])


def bearing(a, b):
    d = sub(b, a)
    return math.degrees(math.atan2(d[0], d[1])) % 360


def intersect(p, dp, q, dq):
    """Point where p + t*dp meets q + s*dq."""
    det = dp[0] * -dq[1] - dp[1] * -dq[0]
    if abs(det) < 1e-12:
        raise ValueError('parallel tracks do not intersect')
    rx, ry = q[0] - p[0], q[1] - p[1]
    t = (rx * -dq[1] - ry * -dq[0]) / det
    return add(p, dp, t)


def at_range(p, d, centre, r_km):
    """Point along the ray p + t*d (t > 0) at r_km from centre."""
    fx, fy = p[0] - centre[0], p[1] - centre[1]
    a = d[0] ** 2 + d[1] ** 2
    b = 2 * (d[0] * fx + d[1] * fy)
    c = fx * fx + fy * fy - r_km * r_km
    disc = b * b - 4 * a * c
    if disc < 0:
        raise ValueError('track never reaches that range')
    return add(p, d, (-b + math.sqrt(disc)) / (2 * a))


def turn(p, hdg, target, right, radius=2.2, step=10):
    """Arc from heading hdg round to target. ~2.2 km is a rate-one turn at
    departure speeds; it only rounds the corner, it does not move the route."""
    pts, h = [], hdg
    while True:
        remaining = (target - h) % 360 if right else (h - target) % 360
        if remaining < step:
            return pts, h
        centre = add(p, unit(h + (90 if right else -90)), radius)
        h = h + step if right else h - step
        p = add(centre, unit(h + (-90 if right else 90)), radius)
        pts.append(p)


def resample(points, step=STEP_KM, max_km=None):
    """Waypoints every `step` km along a polyline, starting at its first point."""
    out, travelled, next_at = [points[0]], 0.0, step
    for a, b in zip(points, points[1:], strict=False):
        seg = norm(sub(b, a))
        while seg and next_at <= travelled + seg:
            if max_km is not None and next_at > max_km + 1e-9:
                return out
            k = (next_at - travelled) / seg
            out.append((a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k))
            next_at += step
        travelled += seg
    return out


# --------------------------------------------------------------------------
# AIP reading
# --------------------------------------------------------------------------
def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()
    except OSError as exc:
        raise SystemExit(f'could not fetch {url}: {exc}') from exc


def page(icao):
    url = f'{EAIP}EG-AD-2.{icao}-en-GB.html'
    raw = fetch(url).decode('utf-8', errors='replace')
    text = html_lib.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', raw)))
    return url, raw, text


def dms(s):
    """'512914.09N' / '0002759.54W' -> decimal degrees."""
    m = re.fullmatch(r'(\d{2,3})(\d{2})(\d{2}(?:\.\d+)?)([NSEW])', s)
    if not m:
        raise ValueError(f'unreadable coordinate {s!r}')
    v = int(m[1]) + int(m[2]) / 60 + float(m[3]) / 3600
    return -v if m[4] in 'SW' else v


def section(text, start, end):
    i = text.index(start)
    j = text.find(end, i)
    return text[i : j if j > 0 else None]


def read_runways(text):
    """{designator: {'thr': (lat, lon), 'true_brg': deg}} from AD 2.12."""
    sec = section(text, 'AD 2.12 RUNWAY PHYSICAL', 'AD 2.13')
    desig = re.findall(
        r'(\d\d[LRC]?) TRWY_DIRECTION;TXT_DESIG;\d+ (\d{3}\.\d+)\S* TRWY_DIRECTION;VAL_TRUE_BRG', sec
    )
    thr = re.findall(
        r'(\d{6}\.\d+[NS]) TRWY_CLINE_POINT;GEO_LAT;\d+ (\d{7}\.\d+[EW]) TRWY_CLINE_POINT;GEO_LONG', sec
    )
    if not desig or len(desig) != len(thr):
        raise SystemExit(
            f'AD 2.12 parse: {len(desig)} runway designators against {len(thr)} threshold '
            'coordinates. The table layout has changed; refusing to pair them by position.'
        )
    return {d: {'thr': (dms(la), dms(lo)), 'true_brg': float(b)} for (d, b), (la, lo) in zip(desig, thr, strict=True)}


def read_glide(text, runways):
    """{designator: glide angle} from AD 2.19. A runway without an ILS glide
    path is an error, not a default: a steep approach (London City, 5.5 deg)
    drawn at 3 deg would be nearly twice as long as the real one."""
    # Heathrow prints "(RWY 09L) 3 deg ILS Ref"; London City prints the runway
    # once, on the localiser row, and the angle alone on the glide-path row
    # after it. So walk both kinds of token in order and carry the last runway.
    sec = section(text, 'AD 2.19', 'AD 2.20')
    found, current = {}, None
    for m in re.finditer(r'\(RWY (\d\d[LRC]?)\)|(\d(?:\.\d+)?)\S? ILS Ref', sec):
        if m[1]:
            current = m[1]
        elif current and current not in found:
            found[current] = float(m[2])
    missing = sorted(set(runways) - set(found))
    if missing:
        raise SystemExit(f'no ILS glide angle published for runway(s) {missing}')
    return {d: found[d] for d in runways}


def read_magvar(text):
    m = re.search(r'(\d+(?:\.\d+)?)\S?([EW]) TILS_LLZ;VAL_MAG_VAR', text)
    if not m:
        raise SystemExit('no magnetic variation found in AD 2.19')
    return float(m[1]) if m[2] == 'E' else -float(m[1])


def chart_links(raw, pattern):
    """(title, pdf url) for every AD 2.24 chart whose title matches."""
    out = []
    for m in re.finditer(r'>([^<>]*' + pattern + r'[^<>]*)<', raw):
        tail = raw[m.end() : m.end() + 2000]
        pdf = re.search(r'href="\.\./\.\./graphics/(\d+\.pdf)"', tail)
        if pdf:
            out.append((html_lib.unescape(m[1]).strip(), GRAPHICS + pdf[1]))
    return out


def pdf_text(url):
    import pdfplumber  # imported here so --check needs no PDF library

    with pdfplumber.open(io.BytesIO(fetch(url))) as pdf:
        return '\n'.join(p.extract_text() or '' for p in pdf.pages)


# --------------------------------------------------------------------------
# Departures, method 1: RNAV SID coding tables (London City and most of the UK)
# --------------------------------------------------------------------------
ROW = re.compile(
    r'(\d{6}\.\d+[NS])[^\n]*\n\s*([A-Z]{3,5} ?\d[A-Z]) (\d{3}) ([A-Z]{2}) ([A-Z0-9]{3,5})\b[^\n]*\n\s*(\d{7}\.\d+[EW])'
)


def rnav_departures(raw, runways):
    tables = chart_links(raw, r'CODING TABLES')
    sids = {}
    for title, url in tables:
        if 'RWY' not in title or not re.search(r'\b\d[A-Z]\b', title):
            continue
        text = pdf_text(url)
        if 'Standard Instrument Departure' not in text:
            continue
        rwy_of = {re.sub(r'\s', '', m[2]): m[1] for m in re.finditer(r'Runway (\d\d[LRC]?) ([A-Z]{3,5} ?\d[A-Z])', text)}
        for m in ROW.finditer(text):
            name = re.sub(r'\s', '', m[2])
            sids.setdefault(name, {'runway': rwy_of.get(name), 'chart': url, 'fixes': []})
            sids[name]['fixes'].append((int(m[3]), m[5], dms(m[1]), dms(m[6])))
    if not sids:
        raise SystemExit('no SID coding table rows parsed - the chart layout has changed')
    out = []
    for name, sid in sorted(sids.items()):
        rwy = sid['runway']
        if rwy not in runways:
            raise SystemExit(f'{name}: runway {rwy!r} not in AD 2.12 {sorted(runways)}')
        fixes = [f for f in sorted(sid['fixes'])]
        out.append(
            {
                'name': name,
                'runway': rwy,
                'source': f'SID coding table, {sid["chart"]}',
                'waypoints': [[round(la, 6), round(lo, 6)] for _, _, la, lo in fixes],
                'fixes': [f[1] for f in fixes],
            }
        )
    return out


# --------------------------------------------------------------------------
# Departures, method 2: Heathrow's Noise Preferential Routes, from their text
# --------------------------------------------------------------------------
def heathrow_departures(text, runways, magvar, raw):
    """Geometrise EGLL AD 2.21 para 8. Each route below quotes the sentence it
    implements, so a reader can check the drawing against the words."""
    beacons = {
        m[1]: (dms(m[2]), dms(m[3]))
        for m in re.finditer(r'\b([A-Z]{3}) (?:VOR|NDB) (\d{6}\.\d+[NS]) (\d{7}\.\d+[EW])', text)
    }
    # OCK is not in the para 8 beacon note; its position is published in the
    # RNAV hold coding table (AD 2.EGLL-7-19).
    if 'OCK' not in beacons:
        for _title, url in chart_links(raw, r'HOLD CODING TABLES[^<]*OCK'):
            hit = re.search(r'\bOCK\b.{0,200}?(\d{6}\.\d+N).{0,200}?(\d{7}\.\d+[EW])', pdf_text(url), re.S)
            if hit:
                beacons['OCK'] = (dms(hit[1]), dms(hit[2]))
                break
    need = {'LON', 'EPM', 'BUR', 'CHT', 'WOD', 'MID', 'BPK', 'BIG', 'DET', 'OCK'}
    missing = sorted(need - set(beacons))
    if missing:
        raise SystemExit(f'Heathrow NPR beacons not found in the AIP: {missing}')

    lon0 = beacons['LON']
    pl = Plane(*lon0)
    B = {k: pl.xy(*v) for k, v in beacons.items()}
    LON = B['LON']

    def mag(m):  # magnetic track/radial -> true
        return (m + magvar) % 360

    def u(m):
        return unit(mag(m))

    def radial(fix, r, d_nm):
        return add(B[fix], u(r), d_nm * NM_KM)

    def dme(p, d, d_nm):
        return at_range(p, d, LON, d_nm * NM_KM)

    rw = {k: pl.xy(*v['thr']) for k, v in runways.items()}
    # 27 departures lift off near the WEST end (the 09 thresholds), 09
    # departures near the EAST end. One route per NPR from the midpoint of the
    # pair: the AIP gives 27R/27L variants that differ by at most 0.5 NM.
    W = ((rw['09L'][0] + rw['09R'][0]) / 2, (rw['09L'][1] + rw['09R'][1]) / 2)
    E = ((rw['27L'][0] + rw['27R'][0]) / 2, (rw['27L'][1] + rw['27R'][1]) / 2)
    west, east = unit(runways['27R']['true_brg']), unit(runways['09L']['true_brg'])
    hdg_w, hdg_e = runways['27R']['true_brg'], runways['09L']['true_brg']

    routes = {}

    def route(name, rwy, sentence, pts):
        routes[(name, rwy)] = (sentence, pts)

    # ---- westerly operations, runways 27 ----
    i255 = intersect(W, west, LON, u(255))
    d7 = radial('LON', 255, 7)
    arc, _ = turn(d7, mag(255), mag(268), True)
    route('Compton', '27', 'Straight ahead to intercept LON VOR R255 until LON D7, then turn right onto '
          'NDB WOD QDM 268, then to CPT VOR.', [W, i255, d7, *arc, B['WOD']])
    d5 = radial('LON', 255, 5)
    j = intersect(d5, u(205), B['BUR'], u(160))
    d12 = dme(j, u(160), 12)
    route('MAXIT', '27', 'Straight ahead to intercept LON VOR R255. At LON D5 turn left onto BUR NDB '
          'QDR 160. At LON D12 turn right onto MID VOR R010 and continue to MAXIT.',
          [W, i255, d5, j, d12, B['MID']])
    b4, b6 = dme(W, u(296), 4), dme(W, u(296), 6)
    arc1, h1 = turn(b6, mag(296), bearing(b6, B['CHT']), True)
    route('Brookmans Park', '27', 'Climb straight ahead to be established on BUR NDB QDM 296 by LON D4. '
          'At LON D6 turn right onto CHT NDB QDM 052. At CHT NDB turn right onto BPK VOR R243 to BPK VOR.',
          [W, b4, b6, *arc1, B['CHT'], B['BPK']])
    b7 = dme(W, u(296), 7)
    # LON D7 on this track falls about 1 NM short of BUR, so "turn right onto
    # BUR QDR 355" is drawn through the beacon and out along the radial.
    route('UMLAT', '27', 'Climb straight ahead to be established on BUR NDB QDM 296 by LON D4. At LON '
          'D7 turn right onto BUR NDB QDR 355, continue to UMLAT.',
          [W, b4, b7, B['BUR'], radial('BUR', 355, 20)])
    d2 = dme(W, west, 2)
    arc3, _ = turn(d2, hdg_w, bearing(d2, B['EPM']), False)
    route('Detling', '27', 'Straight ahead to LON D2, then turn left onto NDB EPM QDM 135, to EPM NDB, '
          'then continue on DET VOR R270 to DET VOR.', [W, d2, *arc3, B['EPM'], B['DET']])
    d13 = dme(d7, u(268), 13)
    route('GOGSI', '27', 'Straight ahead to intercept LON VOR R255 until LON D7, then turn right onto '
          'WOD NDB QDM 268. Turn left at LON D13 to intercept SAM VOR R032, then to GOGSI.',
          [W, i255, d7, *arc, d13, add(d13, u(212), 30)])
    # ---- easterly operations, runways 09 ----
    e15 = dme(E, east, 1.5)
    arc4, h4 = turn(e15, hdg_e, bearing(e15, B['WOD']), True)
    route('Compton', '09', 'Straight ahead to LON D1.5, then turn right onto NDB WOD QDM 280, continue '
          'to CPT VOR.', [E, e15, *arc4, B['WOD']])
    arc5, _ = turn(e15, hdg_e, mag(124), True)
    d35 = dme(arc5[-1], u(124), 3.5)
    arc6, _ = turn(d35, mag(124), bearing(d35, B['MID']), True)
    route('MODMI', '09', 'Straight ahead to LON D1.5, then turn right onto LON VOR R124 until LON D3.5, '
          'then turn right onto MID VOR R025, continue to MODMI.', [E, e15, *arc5, d35, *arc6, B['MID']])
    k = intersect(e15, u(49), LON, u(70))
    d10 = radial('LON', 70, 10)
    arc7, _ = turn(d10, mag(70), bearing(d10, B['BPK']), False)
    route('Brookmans Park', '09', 'Climb straight ahead to LON D1.5, then turn left onto track 049 to '
          'intercept LON VOR R070. Cross LON D10 and turn left onto BPK VOR R195, continue to BAPAG then '
          'BPK VOR.', [E, e15, k, d10, *arc7, B['BPK']])
    route('ULTIB', '09', 'Climb straight ahead to LON D1.5, then turn left onto track 049 to intercept '
          'LON VOR R070, cross LON D10 and turn left onto BIG VOR R328. Continue to ULTIB.',
          [E, e15, k, d10, add(d10, u(328), 30)])
    t4 = dme(e15, u(120), 4)
    route('Detling', '09', 'Straight ahead to LON D1.5, then turn right onto track 120. At LON D4 turn '
          'left to establish on DET VOR R282 by DET D34. Continue to DET VOR.',
          [E, e15, t4, radial('DET', 282, 34), B['DET']])
    d5e = dme(arc5[-1], u(124), 5)
    route('GASGU', '09', 'Straight ahead to LON D1.5, then turn right onto LON VOR R124 until LON D5, '
          'then turn right onto OCK VOR R041. At OCK VOR turn right onto OCK VOR R253 to GASGU.',
          [E, e15, *arc5, d5e, B['OCK']])

    out = []
    for (name, rwy), (sentence, pts) in sorted(routes.items()):
        out.append(
            {
                'name': name,
                'runway': rwy,
                'source': f'EGLL AD 2.21 para 8 (NPR), AIRAC {AIRAC}: "{sentence}"',
                'waypoints': [[round(c, 6) for c in pl.ll(p)] for p in pts],
            }
        )
    return out


# --------------------------------------------------------------------------
# --fetch
# --------------------------------------------------------------------------
def do_fetch():
    data = {
        'airac': AIRAC,
        'publisher': 'UK AIP, NATS Aeronautical Information Service',
        'generator': 'scripts/build_flight_paths.py --fetch',
        'airports': {},
    }
    for code, meta in AIRPORTS.items():
        url, raw, text = page(meta['icao'])
        runways = read_runways(text)
        glide = read_glide(text, runways)
        magvar = read_magvar(text)
        if meta['departures'] == 'rnav-coding':
            deps = rnav_departures(raw, runways)
        else:
            deps = heathrow_departures(text, runways, magvar, raw)
        data['airports'][code] = {
            'city': meta['city'],
            'icao': meta['icao'],
            'page': url,
            'magvar_deg': magvar,
            'runways': {
                d: {'thr': [round(r['thr'][0], 6), round(r['thr'][1], 6)], 'true_brg': r['true_brg'],
                    'glide_deg': glide[d]}
                for d, r in sorted(runways.items())
            },
            'departures': deps,
        }
        print(f'{code}: {len(runways)} runway ends, {len(deps)} departure routes, magvar {magvar:+.2f}')
    PROCEDURES.write_text(json.dumps(data, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(f'wrote {PROCEDURES.relative_to(ROOT)}')


# --------------------------------------------------------------------------
# Procedures -> corridors
# --------------------------------------------------------------------------
def reciprocal(d):
    n = (int(d[:2]) + 18 - 1) % 36 + 1
    side = {'L': 'R', 'R': 'L', 'C': 'C'}.get(d[2:], '')
    return f'{n:02d}{side}'


def corridors(data):
    """{city: [path, ...]} in the Lambda's dialect: (lat, lon) tuples, `coords`."""
    out = {}
    for code, ap in sorted(data['airports'].items()):
        rw = ap['runways']
        pl = Plane(*next(iter(rw.values()))['thr'])
        paths = []
        for d, r in sorted(rw.items()):
            thr = pl.xy(*r['thr'])
            length = FINAL_TOP_FT * FT_KM / math.tan(math.radians(r['glide_deg']))
            outer = add(thr, unit(r['true_brg'] + 180), length)
            pts = resample([outer, thr])
            if norm(sub(pts[-1], thr)) > 1e-6:
                pts.append(thr)
            paths.append({'name': f'{code} {d} final approach', 'airport': code, 'type': 'arrival',
                          'freq': 'high' if d in BUSY_FINALS else 'medium',
                          'coords': [pl.ll(p) for p in pts]})
        seen = set()
        for dep in ap['departures']:
            rwy = dep['runway']
            # A departure lifts off near the far end: the reciprocal threshold.
            ends = [r for r in rw if r[:2] == reciprocal(rwy)[:2]] if len(rwy) == 2 else [reciprocal(rwy)]
            starts = [pl.xy(*rw[e]['thr']) for e in ends]
            start = (sum(s[0] for s in starts) / len(starts), sum(s[1] for s in starts) / len(starts))
            wps = [pl.xy(*w) for w in dep['waypoints']]
            line = [start, *wps] if norm(sub(wps[0], start)) > 0.05 else wps
            pts = resample(line, max_km=DEPARTURE_KM)
            key = tuple((round(x, 2), round(y, 2)) for x, y in pts)
            if key in seen:  # e.g. SAXBI 1A is BPK 1A until beyond the cut
                continue
            seen.add(key)
            paths.append({'name': f'{code} {rwy} departure via {dep["name"]}', 'airport': code,
                          'type': 'departure', 'freq': 'medium', 'coords': [pl.ll(p) for p in pts]})
        out.setdefault(ap['city'], []).extend(paths)
    return {c: [{**p, 'coords': [(round(la, 4), round(lo, 4)) for la, lo in p['coords']]} for p in ps]
            for c, ps in out.items()}


# --------------------------------------------------------------------------
# Holders
# --------------------------------------------------------------------------
def marker(city, lang):
    tag = f'FLIGHT-PATHS-{city.upper()}'
    c = '#' if lang == 'py' else '//'
    return f'{c} {tag}:START (generated by scripts/build_flight_paths.py --write; do not hand-edit)', f'{c} {tag}:END'


def render_lambda(city, paths):
    name = HOLDERS[city]['lambda']
    lines = [f'{name} = [']
    for p in paths:
        lines += ['    {', f"        'name': {p['name']!r},", f"        'airport': {p['airport']!r},",
                  f"        'type': {p['type']!r},", f"        'freq': {p['freq']!r},", "        'coords': ["]
        lines += [f'            ({la}, {lo}),' for la, lo in p['coords']]
        lines += ['        ],', '    },']
    lines.append(']')
    return '\n'.join(lines)


def render_site(city, paths):
    # Frontend dialect: `coordinates`, [lon, lat]. build_city_frontend_block.py
    # records what mixing the two up cost; both conversions happen here, once.
    name = HOLDERS[city]['site']
    lines = [f'      const {name} = [']
    for p in paths:
        pts = ', '.join(f'[{lo}, {la}]' for la, lo in p['coords'])
        lines.append(f"        {{ name: '{p['name']}', airport: '{p['airport']}', type: '{p['type']}', "
                     f"freq: '{p['freq']}', coordinates: [{pts}] }},")
    lines.append('      ];')
    return '\n'.join(lines)


def replace_block(path, start, end, body, write):
    src = path.read_text(encoding='utf-8')
    crlf = '\r\n' in src
    text = src.replace('\r\n', '\n')
    i, j = text.find(start.split(' (')[0]), text.find(end)
    if i < 0 or j < 0:
        raise SystemExit(f'{path.name}: markers {start.split(" (")[0]!r} / {end!r} not found')
    line_start = text.rfind('\n', 0, i) + 1
    indent = text[line_start:i]
    new = f'{indent}{start}\n{body}\n{indent}{end}'
    old = text[line_start : j + len(end)]
    if old == new:
        return False
    if write:
        out = text[:line_start] + new + text[j + len(end):]
        path.write_text(out.replace('\n', '\r\n') if crlf else out, encoding='utf-8', newline='')
    return True


def do_check_or_write(write):
    if not PROCEDURES.exists():
        raise SystemExit(f'{PROCEDURES.relative_to(ROOT)} missing - run --fetch (network) first')
    data = json.loads(PROCEDURES.read_text(encoding='utf-8'))
    by_city = corridors(data)
    if not by_city:
        raise SystemExit('the procedures file produced no corridors - refusing to report a pass')
    stale = []
    for city, paths in by_city.items():
        if city not in HOLDERS:
            raise SystemExit(f'{city} has procedures but no holder constants in HOLDERS')
        n_pts = sum(len(p['coords']) for p in paths)
        for path, lang, body in (
            (LAMBDA, 'py', render_lambda(city, paths)),
            (SITE, 'js', render_site(city, paths)),
        ):
            start, end = marker(city, lang)
            if replace_block(path, start, end, body, write):
                stale.append(f'{path.name} ({city})')
        print(f'{city}: {len(paths)} corridors, {n_pts} waypoints from AIRAC {data["airac"]}')
    if stale and not write:
        print('STALE: ' + ', '.join(stale) + ' - run scripts/build_flight_paths.py --write')
        return 1
    print('rewrote ' + ', '.join(stale) if stale else 'both holders match data/flight-procedures.json')
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--fetch', action='store_true')
    g.add_argument('--check', action='store_true')
    g.add_argument('--write', action='store_true')
    a = ap.parse_args()
    if a.fetch:
        do_fetch()
        return 0
    return do_check_or_write(a.write)


if __name__ == '__main__':
    sys.exit(main())
