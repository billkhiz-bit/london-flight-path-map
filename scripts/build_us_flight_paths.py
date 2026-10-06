"""US flight paths from the FAA's Coded Instrument Flight Procedures (CIFP).

    python scripts/build_us_flight_paths.py --fetch          # download the current cycle, write the record
    python scripts/build_us_flight_paths.py --from-zip X.zip # write the record from a zip already on disk
    python scripts/build_us_flight_paths.py --check          # is the checked-in record sound, and current with its zip?

WHY THIS EXISTS (2026-10-02)
----------------------------
The sibling of build_flight_paths.py, for the United States. New York's
corridors are hand-drawn, which is what London's were until a reader caught
Ockham and Bovingdon running due north-south into two east-west runways. The
San Francisco Bay Area is next (EXPANSION.md), and it should start derived.

The UK builder reads the AIP, where six of twelve airports publish their
departures as chart drawings a script cannot read. The FAA publishes one file,
in ARINC 424, that CODES every runway, every ILS and every departure procedure
at every US airport. So this builder is a parser, not a scraper, and what it
writes has the same shape as data/flight-procedures.json: per airport, each
runway's threshold, true bearing and glide angle, and each departure as its
sequence of named fixes.

THIS WRITES THE RECORD ONLY. Nothing here touches the score Lambda or
index.html. New York's holders stay hand-drawn until the derived routes have
been measured against the scores they would move, which is its own change.

WHAT IT REFUSES TO GUESS
------------------------
  - A leg with no fix (a heading to an altitude, a heading to intercept) adds
    no point. The line goes from the runway to the first NAMED fix, as the UK
    coding-table routes do. Nothing is invented for where a climbing aircraft
    reaches 520 ft.
  - A route STOPS where radar vectors begin (VM / FM), and says so
    (`vectored`). Oakland's COAST9 flies a heading until a controller turns
    it, then resumes at a fix 90 km away; a line from the runway to that fix
    would be drawn by nobody but us. The same goes for an initial fix (IF)
    the coded route has not reached: how the aircraft gets there is not in
    the file. A departure that is vectors from the runway has no waypoints.
  - A fix that only ANCHORS a course is not a point on the line. FA and FM
    legs fly a course FROM a fix, often a beacon the aircraft never crosses
    (San Jose's SUNOL1 names the Oakland VOR, 48 km away). Only legs that end
    at a fix (TF, DF, CF, AF, RF) add one.
  - A procedure the FAA has not coded is NAMED, from the Not_In_CIFP list in
    the same zip. Kennedy's and Newark's main departures (JFK5, EWR5) are
    radar-vector procedures and are not in the file at all; a record that
    listed only what it could draw would read as though they did not exist.
  - A runway with no ILS glide slope AND no approach vertical angle gets
    `glide_deg: null` and the reason. San Francisco's 01L and 01R are the
    case. It is not given 3 degrees because most runways are. And the reason
    says WHICH kind of absence it is: Kennedy's 13R has a published approach
    the file does not code, which is not "none published".
  - True bearing is MEASURED between a runway's two thresholds, not taken
    from the published magnetic bearing; the two are then compared, and a
    disagreement over MAG_TOLERANCE_DEG fails the build.

COLUMNS
-------
ARINC 424 is fixed-width, 132 characters. The slices below were read off the
real file (KSJC, KSFO), not from memory of the specification, and
tests/test_us_flight_paths.py pins them against a real excerpt.

The FAA page answers 403 without a browser User-Agent, like the UK AIP host.
"""

import argparse
import io
import json
import math
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / 'data' / 'us-flight-procedures.json'
CACHE = ROOT / 'data' / 'cifp'  # gitignored (data/*): the zip is 9 MB and re-fetchable
PAGE = 'https://www.faa.gov/air_traffic/flight_info/aeronav/digital_products/cifp/download/'
ZIP_URL = re.compile(r'https://aeronav\.faa\.gov/Upload_313-d/cifp/CIFP_(\d{6})\.zip')
MEMBER = 'FAACIFP18'
NOT_CODED = 'Not_In_CIFP.xlsx'
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36'}
WIDTH = 132

# Airports, and the city whose corridors each will feed. `bayarea` is
# provisional: the city key is stage 2's decision (EXPANSION.md).
AIRPORTS = {
    'SFO': {'icao': 'KSFO', 'cities': ['bayarea']},
    'OAK': {'icao': 'KOAK', 'cities': ['bayarea']},
    'SJC': {'icao': 'KSJC', 'cities': ['bayarea']},
    'JFK': {'icao': 'KJFK', 'cities': ['nyc']},
    'LGA': {'icao': 'KLGA', 'cities': ['nyc']},
    'EWR': {'icao': 'KEWR', 'cities': ['nyc']},
    'TEB': {'icao': 'KTEB', 'cities': ['nyc']},
}

# SID route types (ARINC 424 5.7). Runway transitions and the common route are
# drawn; enroute transitions begin where the common route ends, hundreds of km
# from the homes this product scores, and are left out.
RUNWAY_TRANSITION = set('14FT')
COMMON_ROUTE = set('25M')
# STAR route types (5.7) run the other way: an enroute transition comes FIRST,
# from hundreds of km out, then the common route, then a runway transition. The
# same two kinds are kept, for the same reason. Read off the real file: SFO,
# OAK and SJC use 1-6 only.
STAR_RUNWAY_TRANSITION = set('369S')
STAR_COMMON_ROUTE = set('258M')
# An approach's TRANSITIONS (route type A) lead from where an arrival ends to
# the start of its final approach, and are coded leg by leg like a STAR.
APPROACH_TRANSITION = 'A'
# Path terminators that END at a named fix, so the aircraft is there. The rest
# fly a heading (VA, VI, VD, VR), a course with no fix (CA, CI, CD, CR), or a
# course FROM a fix that only anchors it (FA, FC, FD): none adds a point.
ENDS_AT_A_FIX = {'TF', 'DF', 'CF', 'AF', 'RF'}
# "Until a controller says otherwise." The coded route stops here.
VECTORS = {'VM', 'FM'}
# A procedure ident that is an APPROACH (I13, R28RU, J19L), as against a
# departure or arrival (JFK5, NIMI6). Not_In_CIFP lists both without saying which.
APPROACH_IDENT = re.compile(r'^[A-Z]\d\d')

# Which approach's vertical angle stands in for a runway with no ILS glide
# slope: an RNAV (GPS) approach first, then RNP, then a localizer approach.
APPROACH = re.compile(r'^([A-Z])(\d\d)([LRC-]?)([A-Z]?)$')
APPROACH_PRIORITY = {'R': 0, 'H': 1, 'L': 2}
GLIDE_RANGE = (2.5, 3.6)
# FAA magnetic bearings lag the true variation by a degree or so at some
# fields. Beyond this the thresholds or the reciprocal pairing are wrong.
MAG_TOLERANCE_DEG = 2.0
MAX_ROUTE_KM = 600.0
FIRST_FIX_KM = 80.0
MAX_ALT_FT = 45000  # no STAR or approach altitude is published above FL450


def dms(s):
    """'N37214678' / 'W121554303' -> decimal degrees (hundredths of a second)."""
    m = re.fullmatch(r'([NS])(\d{2})(\d{2})(\d{4})|([EW])(\d{3})(\d{2})(\d{4})', s)
    if not m:
        raise ValueError(f'unreadable coordinate {s!r}')
    hemi, d, mi, sec = (m[1], m[2], m[3], m[4]) if m[1] else (m[5], m[6], m[7], m[8])
    v = int(d) + int(mi) / 60 + int(sec) / 360000
    return -v if hemi in 'SW' else v


def latlon(line, at=32):
    return (round(dms(line[at : at + 9]), 6), round(dms(line[at + 9 : at + 19]), 6))


def variation(s):
    """'E0130' -> +13.0 (east positive), 'W0125' -> -12.5."""
    m = re.fullmatch(r'([EW])(\d{4})', s)
    if not m:
        raise ValueError(f'unreadable magnetic variation {s!r}')
    v = int(m[2]) / 10
    return v if m[1] == 'E' else -v


def bearing(a, b):
    """True bearing from a to b, degrees, on a sphere."""
    la1, lo1, la2, lo2 = (math.radians(x) for x in (a[0], a[1], b[0], b[1]))
    y = math.sin(lo2 - lo1) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(lo2 - lo1)
    return math.degrees(math.atan2(y, x)) % 360


def distance_km(a, b):
    la1, lo1, la2, lo2 = (math.radians(x) for x in (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(h))


def angle_between(a, b):
    """Smallest difference between two bearings, 0..180."""
    return abs((a - b + 180) % 360 - 180)


def reciprocal(rwy):
    """09L <-> 27R: the other end of the same strip."""
    n = (int(rwy[:2]) + 17) % 36 + 1
    return f'{n:02d}' + {'L': 'R', 'R': 'L', 'C': 'C'}.get(rwy[2:], '')


class Cifp:
    """The records this builder reads, indexed once."""

    def __init__(self, lines, wanted):
        self.cycle = None
        self.created = None
        self.airport = {}  # icao -> the airport's 'A' line
        self.by_airport = {icao: {'G': [], 'I': [], 'D': [], 'E': [], 'F': []} for icao in wanted}
        self.terminal = {}  # (airport icao, ident) -> (lat, lon)
        self.enroute = {}  # (ident, region) -> (lat, lon)
        self.navaid = {}  # (ident, region) -> (lat, lon)
        for n, line in enumerate(lines, 1):
            if line.startswith('HDR01'):
                # 'HDR01FAACIFP18      001P013203969192610  09-SEP-202612:03:55'
                m = re.search(r'(\d{4})\s+(\d{2}-[A-Z]{3}-\d{4})', line)
                if m:
                    self.cycle, self.created = m[1], m[2]
                continue
            if not line.startswith('S'):
                continue
            if len(line) != WIDTH:
                raise SystemExit(f'line {n} is {len(line)} characters, not {WIDTH}: this is not an ARINC 424 file')
            sec = line[4:6]
            if sec == 'P ':
                icao, sub = line[6:10], line[12]
                if sub == 'C' and line[21] in '01':
                    self.terminal[(icao, line[13:18].strip())] = latlon(line)
                if icao not in wanted:
                    continue
                if sub == 'A' and line[21] in '01':
                    self.airport[icao] = line
                elif sub in 'GI' and line[21] in '01':
                    self.by_airport[icao][sub].append(line)
                elif sub in 'DEF' and line[38] in '01':
                    self.by_airport[icao][sub].append(line)
            elif sec == 'EA' and line[21] in '01':
                self.enroute[(line[13:18].strip(), line[19:21])] = latlon(line)
            elif sec in ('D ', 'DB') and line[21] in '01':
                # A VOR's own position, or its DME's where the record has no VOR (a DME or TACAN).
                at = 32 if line[32:41].strip() else 55
                if line[at : at + 9].strip():
                    self.navaid[(line[13:17].strip(), line[19:21])] = latlon(line, at)
        if not self.cycle:
            raise SystemExit('no HDR01 record: the cycle cannot be read, so the record could not say what it describes')

    def fix(self, icao, ident, region, section):
        """Where a leg's fix is. Its section says which table to look in."""
        if section == 'PC':
            hit = self.terminal.get((icao, ident))
        elif section == 'EA':
            hit = self.enroute.get((ident, region))
        elif section in ('D ', 'DB'):
            hit = self.navaid.get((ident, region))
        elif section == 'PA':
            hit = latlon(self.airport[ident]) if ident in self.airport else None
        else:
            hit = None
        if hit is None:
            raise SystemExit(f'{icao}: fix {ident!r} (section {section!r}, region {region!r}) is not in the file')
        return hit


def read_runways(cifp, icao):
    """{designator: threshold, bearings} from the airport's runway records."""
    magvar = variation(cifp.airport[icao][51:56])
    raw = {}
    for line in cifp.by_airport[icao]['G']:
        rwy = line[13:18].strip()[2:]
        raw[rwy] = {'thr': latlon(line), 'mag_brg': int(line[27:31]) / 10}
    out = {}
    for rwy, r in sorted(raw.items()):
        other = raw.get(reciprocal(rwy))
        if not other:
            raise SystemExit(f'{icao}: runway {rwy} has no reciprocal {reciprocal(rwy)} in the file')
        true = bearing(r['thr'], other['thr'])
        if angle_between(true, r['mag_brg'] + magvar) > MAG_TOLERANCE_DEG:
            raise SystemExit(
                f'{icao} {rwy}: the bearing between its thresholds is {true:.1f} true, but the published '
                f'{r["mag_brg"]:.1f} magnetic with variation {magvar:+.1f} is {r["mag_brg"] + magvar:.1f}. '
                'The thresholds or the pairing are wrong.'
            )
        out[rwy] = {'thr': list(r['thr']), 'true_brg': round(true, 2), 'mag_brg': r['mag_brg']}
    if len(out) < 2:
        raise SystemExit(f'{icao}: {len(out)} runway records - the airport section was not read')
    return out, magvar


def runway_of_approach(ident):
    """'R13RZ' -> '13R', 'R29-T' -> '29', 'JFK5' -> None (not an approach)."""
    m = APPROACH.match(ident)
    return m[2] + (m[3] if m[3] in 'LRC' else '') if m else None


def no_glide_reason(rwy, uncoded):
    """Why a runway has no glide angle. Three different facts, three wordings.

    `uncoded` is the airport's Not_In_CIFP idents, or None when that list was
    not read. "None published" is a claim about the FAA, so it is made only
    when the list WAS read and names no approach to this runway. Kennedy's 13R
    and Teterboro's 01 have a published approach the file simply does not code,
    and the first version of this record said "none published" of both.
    """
    if uncoded is None:
        return 'none in the CIFP: no ILS glide slope and no approach vertical angle is coded'
    missing = sorted(p for p in uncoded if runway_of_approach(p) == rwy)
    if missing:
        return (
            f'not coded: the FAA publishes {", ".join(missing)} to this runway but this cycle does not code '
            f'{"it" if len(missing) == 1 else "them"}, and no other coded approach carries a vertical angle'
        )
    return 'none published: no ILS glide slope and no approach vertical angle in the CIFP, and none listed as uncoded'


NO_GLIDE_PREFIXES = ('none in the CIFP', 'not coded', 'none published')


def read_glide(cifp, icao, runways, uncoded=None):
    """A glide angle per runway, with where it came from, or None and why."""
    ils = {}
    for line in cifp.by_airport[icao]['I']:
        if line[87:90].strip():
            ils[line[27:32].strip()[2:]] = (int(line[87:90]) / 100, f'ILS glide slope {line[13:17].strip()}')
    vpa = {}
    for line in cifp.by_airport[icao]['F']:
        ident, angle = line[13:19].strip(), line[102:106].strip()
        rwy = runway_of_approach(ident)
        if not rwy or not angle or not int(angle):
            continue
        vpa.setdefault(rwy, set()).add((APPROACH_PRIORITY.get(ident[0], 9), ident, abs(int(angle)) / 100))
    for rwy, r in runways.items():
        if rwy in ils:
            angle, source = ils[rwy]
        elif rwy in vpa:
            _, ident, angle = sorted(vpa[rwy])[0]
            source = f'approach {ident} vertical angle'
        else:
            r['glide_deg'] = None
            r['glide_source'] = no_glide_reason(rwy, uncoded)
            continue
        if not GLIDE_RANGE[0] <= angle <= GLIDE_RANGE[1]:
            raise SystemExit(f'{icao} {rwy}: glide angle {angle} from {source} is outside {GLIDE_RANGE}')
        r['glide_deg'] = angle
        r['glide_source'] = f'CIFP {source}'


def describe(line):
    """One leg in words, for the record's `source`."""
    term, fix = line[47:49], line[29:34].strip()
    if fix:
        return f'{term} {fix}'
    course, alt = line[70:74].strip(), line[84:89].strip()
    bits = [term]
    if course.isdigit():
        bits.append(f'{int(course) / 10:.0f}M')
    if alt.isdigit():
        bits.append(f'to {int(alt)} ft')
    return ' '.join(bits)


def in_order(legs):
    return sorted(legs, key=lambda x: x[26:29])


def grouped(lines, runway_kinds, common_kinds):
    """{procedure: {(is_common, transition ident): legs}} for the two kinds of transition this builder draws."""
    out = {}
    for line in lines:
        kind = line[19]
        if kind in runway_kinds or kind in common_kinds:
            out.setdefault(line[13:19].strip(), {}).setdefault((kind in common_kinds, line[20:25].strip()), []).append(
                line
            )
    return out


def split_common(icao, name, groups):
    """(common legs every transition shares, {runway ident: common legs keyed to that runway alone}).

    A common route normally carries a blank or 'ALL' transition ident and goes
    with every runway transition. But the file also keys a common route to ONE
    runway (Oakland's SLNT3 is a single common-route record marked RW30, and
    San Francisco's SERFR4 arrival is one marked RW28B), and that one belongs
    to its runway alone. The first version sent every common route to every
    runway, and recorded SLNT3 as departing all eight, the two general-aviation
    runways included.
    """
    common_all, common_for = [], {}
    for (is_common, ident), legs in sorted(groups.items()):
        if not is_common:
            continue
        if ident.startswith('RW'):
            common_for.setdefault(ident, []).extend(in_order(legs))
        elif ident in ('', 'ALL'):
            common_all.extend(in_order(legs))
        else:
            raise SystemExit(f'{icao} {name}: a common route is keyed {ident!r}, neither a runway nor ALL')
    return common_all, common_for


def served_by(icao, name, trans, runways):
    """The runways a transition ident names: 'RW28B' is both 28s, 'ALL' every runway."""
    if trans == 'ALL':
        return sorted(runways)
    label = trans[2:]
    served = sorted(r for r in runways if r == label or (label.endswith('B') and r[:2] == label[:2]))
    if not served:
        raise SystemExit(f'{icao} {name}: transition {trans!r} matches no runway in {sorted(runways)}')
    return served


def feet(s):
    """'FL270' -> 27000, '06000' -> 6000, blank -> None."""
    s = s.strip()
    if not s:
        return None
    if s.startswith('FL') and s[2:].isdigit():
        return int(s[2:]) * 100
    if s.isdigit():
        return int(s)
    raise SystemExit(f'unreadable altitude {s!r}')


def altitude(line):
    """The altitude the FAA publishes at a leg's fix, as {'min_ft', 'max_ft'}, or None where it publishes none.

    ARINC 424 5.29, read off the real file: ' ' AT (both bounds), '+' at or
    ABOVE (a floor only), '-' at or BELOW (a ceiling only), 'B' between, where
    altitude 1 is the ceiling and altitude 2 the floor (DYAMD5's LAANE: B,
    FL260, FL220). A floor is not where aircraft fly - they are often higher -
    so the record keeps which bound was published and never collapses it to
    one number. Any other code is refused rather than read as one of these.
    """
    desc, a1, a2 = line[82], feet(line[84:89]), feet(line[89:94])
    if a1 is None:
        if desc != ' ':
            raise SystemExit(f'altitude description {desc!r} with no altitude: {line[13:34]!r}')
        return None
    if desc in (' ', '@'):
        return {'min_ft': a1, 'max_ft': a1}
    if desc == '+':
        return {'min_ft': a1, 'max_ft': None}
    if desc == '-':
        return {'min_ft': None, 'max_ft': a1}
    if desc == 'B':
        if a2 is None or a2 > a1:
            raise SystemExit(f'a "between" altitude whose floor {a2} is not under its ceiling {a1}: {line[13:34]!r}')
        return {'min_ft': a2, 'max_ft': a1}
    raise SystemExit(f'altitude description {desc!r} is not one this builder reads: {line[13:34]!r}')


def walk(cifp, icao, where, route, arriving):
    """A coded route's legs -> (waypoints, fixes, published altitudes, vectored).

    `arriving` is the one difference between the two directions. A departure
    starts at its runway, so an initial fix (IF) on it is a fix the route never
    reached: how the aircraft gets there is not coded, and the line does not go
    there. An arrival STARTS with an initial fix, and each later segment opens
    with an IF re-stating the fix the one before it ended at, which the
    same-point test below folds in.
    """
    waypoints, fixes, alts, vectored = [], [], [], False
    for line in route:
        term, ident = line[47:49], line[29:34].strip()
        if term in VECTORS:
            vectored = True
            break
        if term not in ENDS_AT_A_FIX and term != 'IF':
            continue
        if not ident:
            raise SystemExit(f'{icao} {where}: a {term} leg names no fix')
        p = list(cifp.fix(icao, ident, line[34:36], line[36:38]))
        if waypoints and waypoints[-1] == p:
            # The same fix again: the next segment's IF, or a repeated leg.
            # Keep an altitude only one of the two published.
            if alts[-1] is None:
                alts[-1] = altitude(line)
            continue
        if term == 'IF' and not (arriving and not waypoints):
            vectored = True
            break
        waypoints.append(p)
        fixes.append(ident)
        alts.append(altitude(line))
    return waypoints, fixes, alts, vectored


def read_departures(cifp, icao, runways):
    """Every SID runway transition, with the common route, as its named fixes."""
    out = []
    for name, groups in sorted(grouped(cifp.by_airport[icao]['D'], RUNWAY_TRANSITION, COMMON_ROUTE).items()):
        common_all, common_for = split_common(icao, name, groups)
        transitions = {t: in_order(legs) for (is_common, t), legs in groups.items() if not is_common}
        for ident in common_for:
            transitions.setdefault(ident, [])
        if not transitions:
            transitions = {'ALL': []}
        for trans, legs in sorted(transitions.items()):
            served = served_by(icao, name, trans, runways)
            route = legs + common_for.get(trans, []) + common_all
            waypoints, fixes, _, vectored = walk(cifp, icao, f'{name} {trans}', route, arriving=False)
            out.append(
                {
                    'name': name,
                    'runway': trans[2:].rstrip('B') if trans != 'ALL' else 'ALL',
                    'runways': served,
                    'source': f'FAA CIFP cycle {cifp.cycle}, {icao} SID {name} transition {trans}: '
                    + '; '.join(describe(x) for x in route),
                    'waypoints': waypoints,
                    'fixes': fixes,
                    'vectored': vectored,
                }
            )
    return out


def read_arrivals(cifp, icao, runways):
    """Every STAR: its common route, then each runway transition, as named fixes with published altitudes.

    Enroute transitions are left out, as they are for departures, and for the
    same reason: they begin hundreds of km out. A STAR that ends in radar
    vectors says so (`vectored`). One that ends at a fix is where an approach
    transition can take over (read_approach_transitions); the record keeps the
    two apart, as the FAA does, and the page decides what to join.
    """
    out = []
    for name, groups in sorted(grouped(cifp.by_airport[icao]['E'], STAR_RUNWAY_TRANSITION, STAR_COMMON_ROUTE).items()):
        common_all, common_for = split_common(icao, name, groups)
        transitions = {t: in_order(legs) for (is_common, t), legs in groups.items() if not is_common}
        for ident in common_for:
            transitions.setdefault(ident, [])
        if not transitions:
            transitions = {'ALL': []}
        for trans, legs in sorted(transitions.items()):
            served = served_by(icao, name, trans, runways)
            # Flown in this order: the shared route first, the runway's own last.
            route = common_all + common_for.get(trans, []) + legs
            waypoints, fixes, alts, vectored = walk(cifp, icao, f'{name} {trans}', route, arriving=True)
            out.append(
                {
                    'name': name,
                    'runway': trans[2:].rstrip('B') if trans != 'ALL' else 'ALL',
                    'runways': served,
                    'source': f'FAA CIFP cycle {cifp.cycle}, {icao} STAR {name} transition {trans}: '
                    + '; '.join(describe(x) for x in route),
                    'waypoints': waypoints,
                    'fixes': fixes,
                    'altitudes': alts,
                    'vectored': vectored,
                }
            )
    return out


def read_approach_transitions(cifp, icao, runways):
    """Each approach's transitions: from the fix an arrival can end at, to the start of the final approach.

    Kept per approach, as the FAA codes them, so the record says which
    approaches share a path; the ILS and RNAV approaches to one runway often
    do. An approach that names no runway (a circling approach) has no final for
    a transition to lead to, and is left out.
    """
    groups = {}
    for line in cifp.by_airport[icao]['F']:
        if line[19] == APPROACH_TRANSITION:
            groups.setdefault((line[13:19].strip(), line[20:25].strip()), []).append(line)
    out = []
    for (proc, trans), legs in sorted(groups.items()):
        rwy = runway_of_approach(proc)
        if rwy is None:
            continue
        if rwy not in runways:
            raise SystemExit(f'{icao} approach {proc}: runway {rwy} is not in {sorted(runways)}')
        route = in_order(legs)
        waypoints, fixes, alts, vectored = walk(cifp, icao, f'{proc} {trans}', route, arriving=True)
        out.append(
            {
                'approach': proc,
                'runway': rwy,
                'transition': trans,
                'source': f'FAA CIFP cycle {cifp.cycle}, {icao} approach {proc} transition {trans}: '
                + '; '.join(describe(x) for x in route),
                'waypoints': waypoints,
                'fixes': fixes,
                'altitudes': alts,
                'vectored': vectored,
            }
        )
    return out


def not_coded_of(zip_path, icaos):
    """{icao: procedure idents the FAA lists as NOT in this cycle's file}."""
    import openpyxl  # imported here so --check on a clone with no zip, and the tests, need no spreadsheet library

    with zipfile.ZipFile(zip_path) as z:
        book = openpyxl.load_workbook(io.BytesIO(z.read(NOT_CODED)), read_only=True)
    return not_coded_from_rows([list(sheet.iter_rows(values_only=True)) for sheet in book.worksheets], icaos)


NOT_CODED_HEADER = ('ARINC_ID', 'TERM_ID')


def not_coded_from_rows(sheets, icaos):
    """The sheets' rows -> {icao: idents}. Split from the workbook so it can be tested.

    Two floors, because a count of rows read says how many were parsed and
    never WHICH were lost. The header is asserted, so a column added in front
    fails here instead of reading airport codes out of the wrong column. And at
    least one of the wanted airports must appear: with Kennedy, LaGuardia and
    Newark among them, "none of ours is listed" is a change of format (codes
    written without the K, say), not good news.
    """
    out = {icao: [] for icao in icaos}
    for rows in sheets:
        header = tuple(str(c).strip() if c is not None else '' for c in (rows[0] if rows else ())[:2])
        if header != NOT_CODED_HEADER:
            raise SystemExit(
                f'{NOT_CODED} starts {header!r}, not {NOT_CODED_HEADER!r}: its layout has changed, '
                'and "nothing is uncoded" would be a guess'
            )
        for row in rows[1:]:
            if row and row[0] in out and row[1]:
                out[row[0]].append(str(row[1]).strip())
    if not any(out.values()):
        raise SystemExit(
            f'{NOT_CODED} names none of {sorted(icaos)}: its airport codes have changed form, '
            'and "nothing is uncoded" would be a guess'
        )
    return {icao: sorted(v) for icao, v in out.items()}


def build(lines, airports=None, effective=None, not_coded=None):
    """The record, from the lines of FAACIFP18.

    `not_coded` is not_coded_of()'s answer. Left as None (the tests pass lines
    alone) the record omits the key instead of claiming an empty list.
    """
    airports = airports or AIRPORTS
    cifp = Cifp(lines, {a['icao'] for a in airports.values()})
    out = {}
    for code, ap in airports.items():
        icao = ap['icao']
        if icao not in cifp.airport:
            raise SystemExit(f'{icao} has no airport record in this file')
        runways, magvar = read_runways(cifp, icao)
        read_glide(cifp, icao, runways, None if not_coded is None else not_coded[icao])
        out[code] = {
            'cities': ap['cities'],
            'icao': icao,
            'ref': list(latlon(cifp.airport[icao])),
            'magvar_deg': magvar,
            'departures_method': 'cifp-coded',
            'runways': runways,
            'departures': read_departures(cifp, icao, runways),
            'arrivals': read_arrivals(cifp, icao, runways),
            'approach_transitions': read_approach_transitions(cifp, icao, runways),
        }
        if not_coded is not None:
            # Departures or arrivals the FAA publishes but has not coded; its
            # list does not say which. Uncoded APPROACHES are not listed here:
            # where one leaves a runway with no glide angle, that runway's
            # `glide_source` names it (read_glide above).
            out[code]['procedures_not_coded'] = [p for p in not_coded[icao] if not APPROACH_IDENT.match(p)]
    return {
        'cycle': cifp.cycle,
        'effective': effective,
        'created': cifp.created,
        'publisher': 'FAA Coded Instrument Flight Procedures (CIFP), a work of the US government',
        'generator': 'scripts/build_us_flight_paths.py --fetch',
        'airports': out,
    }


def lines_of(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        return z.read(MEMBER).decode('latin-1').splitlines()


def effective_of(zip_path):
    """CIFP_261001.zip -> '2026-10-01', the day the cycle takes effect."""
    m = re.search(r'CIFP_(\d{2})(\d{2})(\d{2})', Path(zip_path).name)
    return f'20{m[1]}-{m[2]}-{m[3]}' if m else None


def fetch():
    req = urllib.request.Request(PAGE, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        page = r.read().decode('utf-8', 'replace')
    found = sorted(set(ZIP_URL.findall(page)))
    if not found:
        raise SystemExit('no CIFP zip linked from the FAA page: the page layout has changed')
    # The page lists the current cycle and, near a changeover, the next. Take the earliest: the one in effect.
    stamp = found[0]
    CACHE.mkdir(parents=True, exist_ok=True)
    dest = CACHE / f'CIFP_{stamp}.zip'
    if not dest.exists():
        url = f'https://aeronav.faa.gov/Upload_313-d/cifp/CIFP_{stamp}.zip'
        # Downloaded beside its final name and moved only once it opens as a
        # zip holding the file. `--check` is a blocking stage and re-derives
        # from whatever sits at the final name, so a download cut short there
        # would turn every later commit red until someone deleted it by hand.
        part = dest.with_suffix('.part')
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
            part.write_bytes(r.read())
        if not complete_zip(part):
            part.unlink()
            raise SystemExit(
                f'{url} did not arrive whole (no readable {MEMBER} inside): nothing was cached, run it again'
            )
        part.replace(dest)
        print(f'fetched {dest.name} ({dest.stat().st_size:,} bytes)')
    return dest


def complete_zip(path):
    """Is this a whole zip with both members this builder reads?"""
    if not zipfile.is_zipfile(path):
        return False
    with zipfile.ZipFile(path) as z:
        return {MEMBER, NOT_CODED} <= set(z.namelist()) and z.testzip() is None


def from_zip(zip_path):
    """The whole record from one CIFP zip: the coded file and the not-coded list."""
    effective = effective_of(zip_path)
    if not effective:
        # The effective date is read from the FAA's own file name, and --check
        # finds the cached zip by it. A renamed zip would write `effective:
        # null`, and re-derivation would then be skipped for good.
        raise SystemExit(
            f'{Path(zip_path).name}: the name does not carry the cycle date (CIFP_yymmdd.zip). '
            'Keep the name the FAA gave it.'
        )
    icaos = [a['icao'] for a in AIRPORTS.values()]
    return build(lines_of(zip_path), effective=effective, not_coded=not_coded_of(zip_path, icaos))


def dump(record):
    return json.dumps(record, indent=1, ensure_ascii=True) + '\n'


def check(record):
    """What must be true of the checked-in record. Returns the failures."""
    fails, compared = [], 0
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(record.get('effective'))):
        fails.append(f'effective is {record.get("effective")!r}, not a date: the cached zip cannot be found by it')
    for code, ap in record['airports'].items():
        rw = ap['runways']
        for rwy, r in rw.items():
            compared += 1
            other = rw.get(reciprocal(rwy))
            if not other:
                fails.append(f'{code} {rwy}: no reciprocal runway in the record')
                continue
            if abs(angle_between(r['true_brg'], other['true_brg']) - 180) > 0.5:
                fails.append(f'{code} {rwy}: {r["true_brg"]} is not opposite {reciprocal(rwy)} at {other["true_brg"]}')
            if angle_between(r['true_brg'], r['mag_brg'] + ap['magvar_deg']) > MAG_TOLERANCE_DEG:
                fails.append(f'{code} {rwy}: true bearing {r["true_brg"]} disagrees with magnetic {r["mag_brg"]}')
            if r['glide_deg'] is None:
                if not r['glide_source'].startswith(NO_GLIDE_PREFIXES):
                    fails.append(f'{code} {rwy}: no glide angle and no reason given')
            elif not GLIDE_RANGE[0] <= r['glide_deg'] <= GLIDE_RANGE[1]:
                fails.append(f'{code} {rwy}: glide angle {r["glide_deg"]} outside {GLIDE_RANGE}')
            elif not r['glide_source'].startswith('CIFP '):
                # An angle typed over a "none published" runway: in range, and invented.
                fails.append(f'{code} {rwy}: glide angle {r["glide_deg"]} but its source is {r["glide_source"]!r}')
        for dep in ap['departures']:
            compared += 1
            if not dep['runways'] or not set(dep['runways']) <= set(rw):
                fails.append(f'{code} {dep["name"]}: serves {dep["runways"]}, which are not all runways here')
            if len(dep['waypoints']) != len(dep['fixes']):
                fails.append(
                    f'{code} {dep["name"]}: {len(dep["waypoints"])} points for {len(dep["fixes"])} named fixes'
                )
            for i, p in enumerate(dep['waypoints']):
                d = distance_km(ap['ref'], p)
                if d > (FIRST_FIX_KM if i == 0 else MAX_ROUTE_KM):
                    fails.append(
                        f'{code} {dep["name"]} {dep["runway"]}: fix {dep["fixes"][i]} is {d:.0f} km from the airport'
                    )
        # Arrivals and approach transitions run TOWARDS the airport, so it is
        # their LAST fix that must be near it; the first may be far out.
        for kind, label in (('arrivals', 'name'), ('approach_transitions', 'approach')):
            for r in ap.get(kind, []):
                compared += 1
                where = f'{code} {r[label]} {r.get("transition") or r.get("runway")}'
                if not set(r['runways'] if 'runways' in r else [r['runway']]) <= set(rw):
                    fails.append(f'{where}: names a runway that is not here')
                if not len(r['waypoints']) == len(r['fixes']) == len(r['altitudes']):
                    fails.append(
                        f'{where}: {len(r["waypoints"])} points, {len(r["fixes"])} fixes and '
                        f'{len(r["altitudes"])} altitudes'
                    )
                    continue
                for i, p in enumerate(r['waypoints']):
                    d = distance_km(ap['ref'], p)
                    last = i == len(r['waypoints']) - 1
                    if d > (FIRST_FIX_KM if last else MAX_ROUTE_KM):
                        fails.append(f'{where}: fix {r["fixes"][i]} is {d:.0f} km from the airport')
                for fx, a in zip(r['fixes'], r['altitudes'], strict=True):
                    if a is None:
                        continue
                    lo, hi = a['min_ft'], a['max_ft']
                    if lo is None and hi is None:
                        fails.append(f'{where}: {fx} has an altitude with neither bound')
                    elif any(v is not None and not 0 < v <= MAX_ALT_FT for v in (lo, hi)) or (
                        lo is not None and hi is not None and lo > hi
                    ):
                        fails.append(f'{where}: {fx} altitude {a} is not a published altitude')
    if not compared:
        fails.append('the record holds no runway and no route: nothing was checked')
    return fails, compared


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--fetch', action='store_true', help='download the current cycle and write the record')
    ap.add_argument('--from-zip', metavar='ZIP', help='write the record from a CIFP zip already on disk')
    ap.add_argument('--check', action='store_true', help='verify the checked-in record')
    args = ap.parse_args()

    if args.fetch or args.from_zip:
        zip_path = Path(args.from_zip) if args.from_zip else fetch()
        record = from_zip(zip_path)
        fails, compared = check(record)
        if fails:
            sys.exit('NOT WRITTEN, the derived record fails its own check:\n  ' + '\n  '.join(fails))
        RECORD.write_text(dump(record), encoding='utf-8', newline='\n')
        deps = sum(len(a['departures']) for a in record['airports'].values())
        arrs = sum(len(a['arrivals']) for a in record['airports'].values())
        apps = sum(len(a['approach_transitions']) for a in record['airports'].values())
        print(
            f'wrote {RECORD.name}: cycle {record["cycle"]}, {len(record["airports"])} airports, {deps} departure, '
            f'{arrs} arrival and {apps} approach transitions'
        )
        return 0

    if args.check:
        if not RECORD.exists():
            sys.exit(f'FAIL: {RECORD.name} is missing')
        record = json.loads(RECORD.read_text(encoding='utf-8'))
        fails, compared = check(record)
        print(
            f'{RECORD.name}: cycle {record["cycle"]} (effective {record["effective"]}), '
            f'{compared} runways, departures, arrivals and approach transitions checked'
        )
        stamp = (record.get('effective') or '').replace('-', '')[2:]
        cached = CACHE / f'CIFP_{stamp}.zip'
        if cached.exists():
            again = from_zip(cached)
            if dump(again) != dump(record):
                fails.append(
                    f'the record differs from what {cached.name} derives: re-run --from-zip, or it was edited by hand'
                )
            else:
                print(f'  re-derived from {cached.name}: identical')
        elif not fails:
            # At the start of a line, where preflight looks for it: without the
            # zip this compared the record with itself, and that must not print
            # as a PASS (the zip is gitignored, so this is every fresh clone).
            print(
                f'UNVERIFIED: {cached.name} is not on disk, so the record was not re-derived from the FAA file. '
                'It was checked against itself only. Run --fetch to verify.'
            )
        if fails:
            for f in fails:
                print(f'  FAIL {f}')
            return 1
        print('  ok')
        return 0

    ap.print_help()
    return 2


if __name__ == '__main__':
    # Windows consoles default to cp1252; the record is ASCII, but be explicit.
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.exit(main())
