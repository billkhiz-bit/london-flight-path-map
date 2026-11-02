#!/usr/bin/env python3
"""How high, how fast and at what engine power a flight passes: N65 step 4 (docs/lessons/n65.md).

WHY THIS EXISTS (2026-11-01)
----------------------------
scripts/n65_doc29.py reads a flight's noise from the noise tables at an engine POWER (corrected net thrust per engine,
as EASA tabulates it). ADS-B tells us where a flight was, never its power. This module supplies the power the way
ECAC Doc 29 (5th edition, May 2026, Volume 2 Appendix B) does when no flight data are available: it flies each ANP
aircraft's DEFAULT procedure (its "procedural steps": take-off, climb at constant speed, accelerate and retract flaps;
descend, level off, land, brake) through the aircraft's own engine and flap coefficients, for the day's air and wind,
and returns the profile points Doc 29 calls a fixed-point profile: distance along the track, height above the field,
true airspeed and corrected net thrust per engine. Where ANP gives a fixed-point profile instead (aircraft without
performance coefficients), that is returned as published.

Step 5 asks profile() for a flight's points and interpolate() for its height, speed and power at any distance, and
converts the thrust to the noise table's own power parameter with npd_power().

NOTHING HERE IS EASA'S DATA. Every coefficient arrives from the gitignored ANP tables (or EASA's newer release kept
outside the repo) through load_anp(); the tests use ECAC's hypothetical reference aircraft (from the gitignored
Volume 3 workbook) and made-up ones. EASA's terms forbid publishing ANP figures.

UNITS: as Appendix B, feet, knots, pounds and degrees Celsius (Doc 29 B2 warns its results are only reproduced in
these units); n65_doc29 takes metres, so convert at the boundary (FT).

HELD TO ECAC'S OWN WORKED RESULTS: Doc 29 Volume 3 Part 2's 26 flight-profile reference cases, every point
(tests/test_n65_profiles.py). Two of the readings below were settled by them, against the text as printed.

WHERE DOC 29 IS SILENT OR SLIPS, the reading taken is said beside the code and in docs/lessons/n65.md:
- B-41's ((TAS - w) / cos g) is read with TAS the horizontal airspeed, i.e. TAS - w / cos g (Volume 3's results).
- B-21's speed for a propeller's thrust is the true airspeed at mid-step height, not the RMS (Volume 3's results).
- B-58 adds 2*S_D*Decel where B-57's sign needs a subtraction (otherwise ISA would not return the input speed).
- B-57/B-58 give the headwind in ft/s and in knots for the same formula; it is ft/s here (the speeds are ft/s).
- B-18's acceleration needs knots in ft/s (k), which the text leaves out.
- Thrust in pounds is turned into "% of maximum static thrust" for the aircraft whose noise tables use it.
- The idle steps' non-ISA adjustments take the next point's computed speed (and, for the reference, the next step's
  input values); a Descend-Idle followed by anything but a Descend, Descend-Idle, Level, Level-Idle or Land is not
  adjusted (Doc 29 names only those).
- An Accelerate step's end values are those of its final altitude estimate, its distance the last iteration's.
- Turns are not flown in the profile (bank 0, as Vol 2 s3.6.1 allows); n65_doc29 takes the bank from the track.
"""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

FT = 0.3048  # metres per foot (Vol 2 B2.2)
KT_FTS = 1.68781  # k: knots to feet per second (B-24)
G_FTS2 = 32.174  # standard gravity, ft/s2 (B2.1)
P0_INHG = 29.92  # standard sea-level pressure as Appendix B fixes it (B-4, footnote 30)
T0_R = 518.67  # standard sea-level temperature, degrees Rankine (B-3)
LAPSE_F_PER_FT = 0.003566  # ISA temperature lapse, degrees F per foot (B-2)
BARO_EXP = 5.256  # B-4, B-6
REFERENCE_HEADWIND_KT = 8.0  # the ANP coefficients' own headwind (Vol 2 G3.1)
TRANSITION_FT = 1000.0  # a thrust change is spread over this much track (B-34, B-43)
FIRST_ACCEL_GUESS_FT = 250.0  # B6.1.3: the iteration starts 250 ft above the step's start
ACCEL_CONVERGED_FT = 1.0  # ... and stops when two estimates are within a foot
ACCEL_HEADWIND = 0.95  # B-24: the 8 kt headwind's effect on an accelerating climb at 160 kt
MIN_ACCEL_G = 0.02  # B6.1.3 note: keep at least 0.02 g for accelerating
MIN_GRADIENT = 0.01  # ... and below this gradient the procedure cannot be flown
BREAKPOINT_C = 30.0  # B-11: the flat-rating breakpoint assumed without high-temperature coefficients
APPROACH_WEIGHT_SHARE = 0.9  # B-40: the approach weight is 90% of the maximum landing weight
DESCENT_HEADWIND_FACTOR = 1.03  # B-40, B-48, B-76
ENGINE_OUT_GRADIENT_PCT = {2: 1.2, 3: 1.5, 4: 1.7}  # B-13: G' by number of engines

# Thrust ratings are matched case- and punctuation-free ("MaxTake-off" = "MaxTakeoff" = "MaxTakeOff"); ANP names the
# rating above the temperature breakpoint by these (Vol 2 G3.2), else by the rating plus "HiTemp".
HIGH_TEMP = {
    'maxtakeoff': 'maxtkoffhitemp',
    'maxclimb': 'maxclimbhitemp',
    'idleapproach': 'idleapproachhitemp',
    'reducetakeoff': 'redutkoffhitemp',
    'maxcontinuous': 'maxconthitemp',
    'reduceclimb': 'reduceclimbhitemp',
}
IDLE = 'idleapproach'
DEPARTURE_STEPS = ('takeoff', 'climb', 'accelerate', 'level', 'levelaccelerate')
APPROACH_STEPS = ('descend', 'descenddecel', 'descendidle', 'level', 'leveldecel', 'levelidle', 'land', 'decelerate')
DESCENDING = ('descend', 'descenddecel', 'descendidle')


def _norm(text) -> str:
    return re.sub(r'[^a-z0-9]', '', _text(text).lower())


def _text(v) -> str:
    """A cell as text: None blank, a whole-number float as an integer (a workbook's flap 5.0 is ANP's '5')."""
    if v is None:
        return ''
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


# ----------------------------------------------------------------- the air (Vol 2 B3)


@dataclass(frozen=True)
class Atmosphere:
    """The aerodrome's air and wind: elevation (ft above mean sea level), surface temperature (C), sea-level pressure
    (QNH, inHg) and the headwind (kt, positive into the aircraft's face) assumed along the whole profile."""

    elevation_ft: float = 0.0
    temperature_c: float = 15.0
    qnh_inhg: float = P0_INHG
    headwind_kt: float = REFERENCE_HEADWIND_KT

    def temp_f(self, alt_ft: float) -> float:
        """B-2: the temperature (F) at `alt_ft` above mean sea level."""
        return self.temperature_c * 9 / 5 + 32 - LAPSE_F_PER_FT * (alt_ft - self.elevation_ft)

    def temp_c(self, alt_ft: float) -> float:
        return (self.temp_f(alt_ft) - 32) * 5 / 9  # B-1

    def theta(self, alt_ft: float) -> float:
        return (459.67 + self.temp_f(alt_ft)) / T0_R  # B-3

    def delta(self, alt_ft: float) -> float:
        return ((self.qnh_inhg / P0_INHG) ** (1 / BARO_EXP) - LAPSE_F_PER_FT * alt_ft / T0_R) ** BARO_EXP  # B-4

    def sigma(self, alt_ft: float) -> float:
        return self.delta(alt_ft) / self.theta(alt_ft)  # B-5

    def pressure_altitude(self, alt_ft: float) -> float:
        return T0_R / LAPSE_F_PER_FT * (1 - self.delta(alt_ft) ** (1 / BARO_EXP))  # B-6


# The conditions the ANP coefficients and the idle steps' inputs are given for (Vol 2 G3.1, B7.1.2, B7.1.4).
REFERENCE = Atmosphere()


# ----------------------------------------------------------------- the aircraft and its steps


@dataclass(frozen=True)
class Performance:
    """One ANP aircraft's performance data. `jet` maps a normalised thrust rating to (E, F, Ga, Gb, H); `prop` to
    (propeller efficiency, installed net propulsive power hp); `aero` maps (op 'A'/'D', flap) to {'B','C','D','R'}
    (absent coefficients missing); `weights` a stage length to the take-off weight (lb)."""

    acft_id: str
    engines: int
    max_landing_weight_lb: float
    max_static_thrust_lb: float
    power_parameter: str = 'CNT (lb)'
    jet: dict = field(default_factory=dict)
    prop: dict = field(default_factory=dict)
    aero: dict = field(default_factory=dict)
    weights: dict = field(default_factory=dict)

    def flap(self, op: str, flap_id: str, coefficient: str) -> float:
        value = self.aero.get((op, _text(flap_id)), {}).get(coefficient)
        if value is None:
            raise KeyError(f'{self.acft_id}: no {coefficient} for flap {flap_id!r} ({op})')
        return value


@dataclass(frozen=True)
class Step:
    """One procedural step, as ANP's Default_*_Procedural_Steps tables give it (blank fields None)."""

    kind: str  # normalised: 'takeoff', 'climb', 'accelerate', 'level', 'levelaccelerate', 'descend', ...
    flap: str = ''
    rating: str = ''  # normalised thrust rating (departures)
    end_altitude_ft: float | None = None
    rate_of_climb_fpm: float | None = None
    end_cas_kt: float | None = None
    accel_pct: float | None = None
    distance_ft: float | None = None
    start_altitude_ft: float | None = None
    start_cas_kt: float | None = None
    descent_angle_deg: float | None = None
    touchdown_roll_ft: float | None = None
    start_thrust_pct: float | None = None

    def __post_init__(self):  # 'Descend-Idle' = 'descendidle', 'MaxTakeOff' = 'maxtakeoff', flap 5.0 = '5'
        object.__setattr__(self, 'kind', _norm(self.kind))
        object.__setattr__(self, 'rating', _norm(self.rating))
        object.__setattr__(self, 'flap', _text(self.flap))


@dataclass(frozen=True)
class Point:
    """A profile point: ground distance (ft; departures from brake release, approaches negative before touchdown),
    height above the field (ft), true airspeed (kt) and the power: corrected net thrust per engine (lb) for a
    synthesised profile, the table's own power parameter for a published fixed-point profile."""

    distance_ft: float
    height_ft: float
    tas_kt: float
    thrust: float
    step: str = ''


# ----------------------------------------------------------------- engine thrust (Vol 2 B4)


def _jet(coeffs, vc, h, t_c):
    e, f, ga, gb, hh = coeffs
    return e + f * vc + ga * h + gb * h * h + hh * t_c  # B-9


def rated_thrust(
    perf: Performance, rating: str, atm: Atmosphere, alt_ft: float, vc_kt: float, vt_kt: float, departure: bool = True
) -> float:
    """Corrected net thrust per engine (lb) at a thrust rating, at `alt_ft` above sea level, calibrated airspeed
    `vc_kt` (jets) or true airspeed `vt_kt` (propellers): B4.1 for jets (the lower of the normal and high-temperature
    values; B-11 stands in for missing high-temperature coefficients on departures, and the normal value on approach),
    B-12 for propellers."""
    key = _norm(rating)
    if key in perf.jet:
        h, t_c = atm.pressure_altitude(alt_ft), atm.temp_c(alt_ft)
        cnt = _jet(perf.jet[key], vc_kt, h, t_c)
        hi = perf.jet.get(HIGH_TEMP.get(key, key + 'hitemp'))
        if hi is not None:
            cnt_hi = _jet(hi, vc_kt, h, t_c)  # B-10
        elif departure:
            e, f, _ga, _gb, hh = perf.jet[key]
            cnt_hi = f * vc_kt + (e + hh * BREAKPOINT_C) * (1 - 0.006 * t_c) / (1 - 0.006 * BREAKPOINT_C)  # B-11
        else:
            cnt_hi = cnt
        return min(cnt, cnt_hi)
    if key in perf.prop:
        efficiency, hp = perf.prop[key]
        return 326 * efficiency * hp / vt_kt / atm.delta(alt_ft)  # B-12
    raise KeyError(f'{perf.acft_id}: no engine coefficients for thrust rating {rating!r}')


def minimum_thrust(
    perf: Performance, weight_lb: float, atm: Atmosphere, alt_ft: float, vc_kt: float, r: float, bank_rad: float = 0.0
) -> float:
    """B-13: the deepest cutback allowed, the thrust that would hold the engine-out climb gradient G' on one engine
    fewer, applied with all engines running. Not for single-engined aircraft."""
    n = perf.engines
    if n < 2:
        raise ValueError(f'{perf.acft_id}: a minimum (engine-out) thrust needs two or more engines')
    g_out = ENGINE_OUT_GRADIENT_PCT.get(n, ENGINE_OUT_GRADIENT_PCT[4])
    k = 1.01 if vc_kt <= 200 else 0.95
    return weight_lb / atm.delta(alt_ft) / (n - 1) * (math.sin(math.atan(0.01 * g_out)) / k + r / math.cos(bank_rad))


def npd_power(perf: Performance, thrust_lb: float) -> float:
    """The noise tables' power for a corrected net thrust per engine in pounds. Most ANP aircraft tabulate noise against
    thrust in pounds; some propeller aircraft against a percentage of their maximum sea-level static thrust (their noise
    rows run 23 to 150). Doc 29 does not spell the conversion out (a reading: the percentage is of the Aircraft table's
    static thrust, as B-79 uses it the other way). Aircraft tabulated against RPM have only fixed-point profiles, whose
    power is already in the table's unit, so they never come here."""
    unit = perf.power_parameter.lower()
    if '%' in unit:
        return 100.0 * thrust_lb / perf.max_static_thrust_lb
    if 'lb' in unit:
        return thrust_lb
    raise ValueError(f'{perf.acft_id}: cannot express thrust in pounds as {perf.power_parameter!r}')


# ----------------------------------------------------------------- departures (Vol 2 B6)


class _Departure:
    def __init__(self, perf, weight_lb, atm, bank_rad):
        self.perf, self.w, self.atm, self.bank = perf, weight_lb, atm, bank_rad
        self.e = atm.elevation_ft
        self.points: list[Point] = []

    def thrust(self, step, alt, vc, vt):
        if step.rating.startswith('minimum'):
            return minimum_thrust(self.perf, self.w, self.atm, alt, vc, self.r(step), self.bank)
        return rated_thrust(self.perf, step.rating, self.atm, alt, vc, vt, departure=True)

    def r(self, step):
        return self.perf.flap('D', step.flap, 'R')

    def sigma(self, height):
        return self.atm.sigma(self.e + height)

    def takeoff(self, step):
        """B6.1.1: brake release and the equivalent take-off distance, where the initial climb meets the runway."""
        perf, atm, e, w = self.perf, self.atm, self.e, self.w
        vc_to = perf.flap('D', step.flap, 'C') * math.sqrt(w)  # B-15
        tas = vc_to / math.sqrt(atm.sigma(e))  # B-7
        cnt2 = self.thrust(step, e, vc_to, tas)
        cnt1 = self.thrust(step, e, 0.0, tas)  # standing; B-12's speed is the rotation speed (B6.1.1)
        s8 = perf.flap('D', step.flap, 'B') * atm.theta(e) * (w / atm.delta(e)) ** 2 / (perf.engines * cnt2)  # B-16
        hw = atm.headwind_kt
        s = s8 * (vc_to - hw) ** 2 / (vc_to - REFERENCE_HEADWIND_KT) ** 2  # B-17
        self.points += [Point(0.0, 0.0, 0.0, cnt1, 'takeoff'), Point(s, 0.0, tas, cnt2, 'takeoff')]

    def climb(self, step):
        """B6.1.2: constant calibrated airspeed to the step's end altitude."""
        p1 = self.points[-1]
        h1, h2 = p1.height_ft, step.end_altitude_ft
        if h2 <= h1:
            return None  # B6.1.3: an accelerate step can overshoot a later climb's altitude; that climb is skipped
        tas2 = p1.tas_kt * math.sqrt(self.sigma(h1)) / math.sqrt(self.sigma(h2))  # B-19
        vc = tas2 * math.sqrt(self.sigma(h2))  # B-20
        cnt2 = self.thrust(step, self.e + h2, vc, tas2)
        mid = self.e + (h1 + h2) / 2
        # B-21 gives a propeller's B-12 speed as the root mean square of the end speeds; ECAC's Volume 3 propeller
        # cases (8, 28, 56, 68) are reproduced with the true airspeed at the mid-step height instead (the RMS reads
        # every climb up to 0.15% long, 545 ft by 10,000 ft). Jets are unaffected (their thrust takes the CAS).
        cnt_mid = self.thrust(step, mid, vc, vc / math.sqrt(self.atm.sigma(mid)))
        k = 1.01 if vc <= 200 else 0.95
        sin_g = k * (self.perf.engines * cnt_mid / (self.w / self.atm.delta(mid)) - self.r(step) / math.cos(self.bank))
        if sin_g <= 0:
            raise ValueError(f'{self.perf.acft_id}: not enough thrust to climb on step {step}')
        gamma = math.asin(sin_g)  # B-21
        hw = self.atm.headwind_kt
        gamma_w = gamma * (vc - REFERENCE_HEADWIND_KT) / (vc - hw)  # B-22
        p2 = Point(p1.distance_ft + (h2 - h1) / math.tan(gamma_w), h2, tas2, cnt2, 'climb')  # B-23
        return p2, 'climb'

    def accelerate(self, step, level=False):
        """B6.1.3 (and B6.1.5 when level): to the end calibrated airspeed while climbing at the step's rate of climb or
        energy share, iterating the end altitude to within a foot."""
        p1 = self.points[-1]
        perf, atm, e, w, g = self.perf, self.atm, self.e, self.w, G_FTS2
        h1, tas1, vc2 = p1.height_ft, p1.tas_kt, step.end_cas_kt
        r = self.r(step) / math.cos(self.bank)
        # Energy share ahead of rate of climb when both are given (B6.1.3; Vol 2 G3.6 footnote 42).
        esf = step.accel_pct
        h2 = h1 + (0.0 if level else FIRST_ACCEL_GUESS_FT)
        for _ in range(200):
            alt2 = e + h2
            tas2 = vc2 / math.sqrt(atm.sigma(alt2))
            mid = (e + h1 + alt2) / 2
            vt = math.sqrt((tas1**2 + tas2**2) / 2)
            cnt = self.thrust(step, mid, vt * math.sqrt(atm.sigma(mid)), vt)
            a_max = g * (perf.engines * cnt / (w / atm.delta(mid)) - r)
            if level:
                grad = 0.0  # B-31, B-32: a Level-Accelerate step is an Accelerate step that does not climb
            elif esf is not None:
                grad = a_max / g * (1 - esf / 100)  # B-25
            else:
                grad = (step.rate_of_climb_fpm or 0.0) / (60 * KT_FTS * vt)
            if not level and a_max - grad * g < MIN_ACCEL_G * g:
                grad = a_max / g - MIN_ACCEL_G  # B6.1.3 note: give up climb to keep accelerating
                if grad < MIN_GRADIENT:
                    raise ValueError(f'{perf.acft_id}: not enough thrust to accelerate and climb on step {step}')
            if a_max - grad * g <= 0:
                raise ValueError(f'{perf.acft_id}: not enough thrust to accelerate on step {step}')
            s_seg = ACCEL_HEADWIND * KT_FTS**2 * (tas2**2 - tas1**2) / (2 * (a_max - grad * g))  # B-24, B-32
            alt2_new = e + h1 + s_seg * grad / ACCEL_HEADWIND  # B-26
            converged = abs(alt2_new - alt2) <= ACCEL_CONVERGED_FT
            h2 = alt2_new - e
            if converged:
                break
        else:
            raise ValueError(f'{perf.acft_id}: the accelerate step did not converge: {step}')
        # The step ends at the last altitude estimate (B6.1.3: "defined by the values corresponding to Alt_P2'"), with
        # the last iteration's distance (whose climb gradient produced that altitude).
        tas2 = vc2 / math.sqrt(atm.sigma(e + h2))  # B-27
        cnt2 = self.thrust(step, e + h2, vc2, tas2)
        vt = math.sqrt((tas1**2 + tas2**2) / 2)
        hw = atm.headwind_kt
        s_w = s_seg * (vt - hw) / (vt - REFERENCE_HEADWIND_KT)  # B-28, B-33
        return Point(p1.distance_ft + s_w, h2, tas2, cnt2, 'level-accelerate' if level else 'accelerate'), 'accelerate'

    def level(self, step):
        """B6.1.4: constant height and speed for the step's distance, at the thrust that holds them."""
        p1 = self.points[-1]
        wd = self.w / self.atm.delta(self.e + p1.height_ft)
        cnt = self.r(step) * wd / (self.perf.engines * math.cos(self.bank))  # B-30
        return Point(p1.distance_ft + step.distance_ft, p1.height_ft, p1.tas_kt, cnt, 'level'), 'level'

    def transition(self, step, how, p2):
        """B6.1.6: a thrust change is spread over the first min(L/2, 1,000 ft) of the step, on the step's own gradient,
        the thrust at its end already the new rating's."""
        p1 = self.points[-1]
        length = p2.distance_ft - p1.distance_ft
        di = min(length / 2, TRANSITION_FT)  # B-34
        hi = p1.height_ft + (p2.height_ft - p1.height_ft) * di / length  # B-35, the whole step's gradient
        if how == 'climb':
            tas = p1.tas_kt * math.sqrt(self.sigma(p1.height_ft)) / math.sqrt(self.sigma(hi))  # B-36
        elif how == 'level':
            tas = p1.tas_kt
        else:
            tas = math.sqrt(p1.tas_kt**2 + (p2.tas_kt**2 - p1.tas_kt**2) / length * di)
        if how == 'level':
            cnt = p2.thrust  # the adapted thrust holds along the whole step
        else:
            cnt = self.thrust(step, self.e + hi, tas * math.sqrt(self.sigma(hi)), tas)  # B-37, B-38
        return Point(p1.distance_ft + di, hi, tas, cnt, 'transition')


def departure(
    perf: Performance, steps: list[Step], weight_lb: float, atm: Atmosphere = REFERENCE, bank_rad: float = 0.0
) -> list[Point]:
    """A departure's fixed-point profile from its procedural steps (Vol 2 B6) at take-off weight `weight_lb`."""
    d = _Departure(perf, weight_lb, atm, bank_rad)
    rating = None
    for step in steps:
        if step.kind == 'takeoff':
            d.takeoff(step)
            rating = step.rating
            continue
        if not d.points:
            raise ValueError(f'{perf.acft_id}: a departure must start with a take-off step')
        if step.kind == 'climb':
            made = d.climb(step)
        elif step.kind == 'accelerate':
            made = d.accelerate(step)
        elif step.kind == 'levelaccelerate':
            made = d.accelerate(step, level=True)
        elif step.kind == 'level':
            made = d.level(step)
        else:
            raise ValueError(f'{perf.acft_id}: unknown departure step {step.kind!r}')
        if made is None:
            continue
        p2, how = made
        if how == 'level' or step.rating != rating:  # B6.1.4: a Level step always starts with a transition
            d.points.append(d.transition(step, how, p2))
        d.points.append(p2)
        rating = step.rating
    return d.points


# ----------------------------------------------------------------- approaches (Vol 2 B7)


def _single_point(step: Step, nxt: Step) -> bool:
    """B7.1.1-B7.1.4 Case 1: the step needs no end point of its own (its thrust runs on into the next step)."""
    if step.kind in ('descend', 'descenddecel'):
        return nxt.kind == step.kind and nxt.flap == step.flap and nxt.descent_angle_deg == step.descent_angle_deg
    if step.kind in ('level', 'leveldecel'):
        return nxt.kind == step.kind and nxt.flap == step.flap
    return nxt.kind in ('descendidle', 'levelidle')  # the idle steps


def _groundspeed(tas_fts, wind_fts, gamma):
    """The speed along a descending path into a headwind, ft/s (B-57)."""
    return math.sqrt(tas_fts**2 - (wind_fts * math.sin(gamma)) ** 2) - wind_fts * math.cos(gamma)


def _tas_from_groundspeed(gs_fts, wind_fts, gamma):
    return math.sqrt((gs_fts + wind_fts * math.cos(gamma)) ** 2 + (wind_fts * math.sin(gamma)) ** 2)  # B-58


class _Approach:
    def __init__(self, perf, weight_lb, atm, bank_rad):
        self.perf, self.w, self.atm, self.bank = perf, weight_lb, atm, bank_rad
        self.e = atm.elevation_ft

    def sigma(self, h):
        return self.atm.sigma(self.e + h)

    def delta(self, h):
        return self.atm.delta(self.e + h)

    def idle(self, h, tas):
        return rated_thrust(self.perf, IDLE, self.atm, self.e + h, tas * math.sqrt(self.sigma(h)), tas, departure=False)

    def headwind_correction(self, h, gamma, vc):
        """B-48, B-77: the change from the coefficients' 8 kt headwind to the day's."""
        hw = self.atm.headwind_kt
        return (
            DESCENT_HEADWIND_FACTOR
            * self.w
            / self.delta(h)
            * math.sin(gamma)
            * (hw - REFERENCE_HEADWIND_KT)
            / (self.perf.engines * vc)
        )

    def step(self, step: Step, nxt_step: Step, nxt: Point, nxt_ref: tuple[float, float]) -> list[Point]:
        """Point1 (and Point2 where the thrust changes into the next step) of one airborne step, from the first point
        of the step after it. `nxt_ref` is that point's (height ft, CAS kt) on the ISA sea-level reference day."""
        perf, atm, w, n = self.perf, self.atm, self.w, self.perf.engines
        kind, hw = step.kind, atm.headwind_kt
        h1 = step.start_altitude_ft
        if step.start_cas_kt is None and kind == 'level':
            # Two of ANP's Level steps give no speed (between Level-Idle steps at one height). Doc 29 has none to
            # offer; a Level step flies at constant speed, so it holds the speed of the point it runs into (a reading).
            tas1 = nxt.tas_kt
        else:
            tas1 = step.start_cas_kt / math.sqrt(self.sigma(h1))  # B-39, B-49, B-61, B-67, B-71
        if kind in DESCENDING:
            gamma = math.radians(step.descent_angle_deg)
            if kind == 'descendidle':
                h1, tas1 = self.descend_idle_non_isa(step, nxt_step, nxt, nxt_ref, gamma, h1, tas1)
            if h1 <= nxt.height_ft:
                raise ValueError(f'{perf.acft_id}: a descent that does not descend: {step}')
            length = (h1 - nxt.height_ft) / math.tan(gamma)  # B-42, B-44, B-51
        else:
            gamma = 0.0
            length = step.distance_ft
            if kind == 'levelidle':
                length = self.level_idle_non_isa(step, nxt, nxt_ref, length)
        r = perf.flap('A', step.flap, 'R') if kind not in ('descendidle', 'levelidle') else None
        wd1 = w / self.delta(h1)
        cos_e = math.cos(self.bank)
        if kind == 'descend':
            cnt1 = wd1 / n * (r / cos_e - math.sin(gamma) / DESCENT_HEADWIND_FACTOR)  # B-40
            cnt1 += self.headwind_correction(h1, gamma, tas1 * math.sqrt(self.sigma(h1)))  # B-48
        elif kind == 'descenddecel':
            path = (h1 - nxt.height_ft) / math.sin(gamma)
            # B-41 writes ((TAS - w) / cos(gamma)); ECAC's Volume 3 results are reproduced when its TAS is the
            # HORIZONTAL true airspeed, TAS cos(gamma): ((TAS cos(gamma) - w) / cos(gamma)) = TAS - w / cos(gamma), the
            # path speed less the wind (a reading). Read literally, every Descend-Decel thrust of cases 2B, 2D and 6B
            # comes out up to 9 lb low (the deceleration too large by 1/cos^2); with w alone, 6B's 0.1 to 0.2 lb low.
            w_path = hw / math.cos(gamma)
            a = KT_FTS**2 * ((nxt.tas_kt - w_path) ** 2 - (tas1 - w_path) ** 2) / (2 * path)
            cnt1 = wd1 / n * (r * math.cos(gamma) / cos_e - math.sin(gamma) + a / G_FTS2)  # B-41
        elif kind == 'level':
            cnt1 = wd1 / n * (r / cos_e)  # B-62
        elif kind == 'leveldecel':
            a = KT_FTS**2 * ((nxt.tas_kt - hw) ** 2 - (tas1 - hw) ** 2) / (2 * length)
            cnt1 = wd1 / n * (r / cos_e + a / G_FTS2)  # B-63
        else:
            cnt1 = self.idle(h1, tas1)  # B7.1.2, B7.1.4: the IdleApproach rating
        p1 = Point(nxt.distance_ft - length, h1, tas1, cnt1, kind)
        if _single_point(step, nxt_step):
            return [p1]
        di = min(length / 2, TRANSITION_FT)  # B-43, B-53, B-65, B-70
        h2 = nxt.height_ft + di * math.tan(gamma) if kind in DESCENDING else h1  # B-45, B-54
        tas2 = tas1 if kind == 'level' else math.sqrt(nxt.tas_kt**2 + di / length * (tas1**2 - nxt.tas_kt**2))  # B-46
        if kind in ('descend', 'descenddecel'):
            cnt2 = self.delta(h1) / self.delta(h2) * cnt1  # B-47
        elif kind in ('level', 'leveldecel'):
            cnt2 = cnt1
        else:
            cnt2 = self.idle(h2, tas2)
        return [p1, Point(nxt.distance_ft - di, h2, tas2, cnt2, 'transition')]

    def descend_idle_non_isa(self, step, nxt_step, nxt, nxt_ref, gamma, h1, tas1):
        """B7.1.2: hold the step's deceleration on the ISA sea-level reference day; move its start speed (next step
        Level, Level-Idle or Land) or its start height (next step Descend or Descend-Idle). An identity on the
        reference day. Doc 29 names no other next step: then the inputs stand (a reading)."""
        wind = self.atm.headwind_kt * KT_FTS  # ft/s: B-57 says so, B-58 says kt for the same quantity (a reading)
        ref_h, ref_cas = nxt_ref
        s_ref = (step.start_altitude_ft - ref_h) / math.sin(gamma)
        gs_n = _groundspeed(KT_FTS * ref_cas / math.sqrt(REFERENCE.sigma(ref_h)), wind, gamma)
        gs_1 = _groundspeed(
            KT_FTS * step.start_cas_kt / math.sqrt(REFERENCE.sigma(step.start_altitude_ft)), wind, gamma
        )
        decel = (gs_n**2 - gs_1**2) / (2 * s_ref)  # B-57 (negative while slowing)
        gs_next = _groundspeed(KT_FTS * nxt.tas_kt, wind, gamma)  # the next point's speed on the day (a reading)
        if nxt_step.kind in ('level', 'levelidle', 'land'):
            s_d = (h1 - nxt.height_ft) / math.sin(gamma)
            # B-58 as printed adds 2*S_D*Decel; with B-57's sign that would not return the input speed on the
            # reference day, so the sign that does is used (a reading).
            gs1 = math.sqrt(max(gs_next**2 - 2 * s_d * decel, 0.0))
            return h1, _tas_from_groundspeed(gs1, wind, gamma) / KT_FTS
        if nxt_step.kind in ('descend', 'descendidle') and decel != 0:
            s_new = (gs_next**2 - _groundspeed(KT_FTS * tas1, wind, gamma) ** 2) / (2 * decel)  # B-59
            return nxt.height_ft + s_new * math.sin(gamma), tas1  # B-60 (TAS kept as computed at the input height)
        return h1, tas1

    def level_idle_non_isa(self, step, nxt, nxt_ref, length):
        """B-73, B-74: hold the reference day's deceleration by changing the step's length."""
        hw, h = self.atm.headwind_kt, step.start_altitude_ft
        s_ref, s_act = math.sqrt(REFERENCE.sigma(h)), math.sqrt(self.sigma(h))
        decel = ((KT_FTS * (nxt_ref[1] / s_ref - hw)) ** 2 - (KT_FTS * (step.start_cas_kt / s_ref - hw)) ** 2) / (
            2 * length
        )
        if decel == 0:
            return length
        return ((KT_FTS * (nxt.tas_kt - hw)) ** 2 - (KT_FTS * (step.start_cas_kt / s_act - hw)) ** 2) / (2 * decel)


def approach(
    perf: Performance,
    steps: list[Step],
    atm: Atmosphere = REFERENCE,
    weight_lb: float | None = None,
    bank_rad: float = 0.0,
) -> list[Point]:
    """An approach's fixed-point profile from its procedural steps (Vol 2 B7), built backwards from touchdown (each
    step ends where the next begins). Weight 90% of the maximum landing weight unless given (B-40)."""
    w = APPROACH_WEIGHT_SHARE * perf.max_landing_weight_lb if weight_lb is None else weight_lb
    a = _Approach(perf, w, atm, bank_rad)
    lands = [i for i, s in enumerate(steps) if s.kind == 'land']
    if len(lands) != 1 or lands[0] == 0:
        raise ValueError(f'{perf.acft_id}: an approach needs one Land step after at least one airborne step')
    li = lands[0]
    land, before, decels = steps[li], steps[li - 1], steps[li + 1 :]
    if before.descent_angle_deg is None:
        raise ValueError(f'{perf.acft_id}: the step before Land must give a descent angle (B-76)')
    gamma = math.radians(before.descent_angle_deg)  # B-76: the descent before landing
    sig = atm.sigma(a.e)
    vc_td = perf.flap('A', land.flap, 'D') * math.sqrt(w)  # B-75
    cnt_td = (
        w / atm.delta(a.e) / perf.engines * (perf.flap('A', land.flap, 'R') - math.sin(gamma) / DESCENT_HEADWIND_FACTOR)
    )
    cnt_td += a.headwind_correction(0.0, gamma, vc_td)  # B-76, B-77
    touchdown = Point(0.0, 0.0, vc_td / math.sqrt(sig), cnt_td, 'land')
    ground, dist = [touchdown], land.touchdown_roll_ft or 0.0
    for j, nxt in enumerate([*decels, None]):
        # B-78/B-79 (the end of the Land roll) and B-80/B-81: each point takes the NEXT decelerate step's start values.
        if j > 0 and not decels[j - 1].distance_ft:
            continue  # B7.1.6: the last decelerate step (distance 0) makes no point
        if nxt is None:
            raise ValueError(f'{perf.acft_id}: the landing roll ends without a final (zero-distance) decelerate step')
        dist += decels[j - 1].distance_ft if j > 0 else 0.0
        thrust = nxt.start_thrust_pct * perf.max_static_thrust_lb / 100
        ground.append(Point(dist, 0.0, nxt.start_cas_kt / math.sqrt(sig), thrust, 'decelerate'))
    airborne: list[Point] = []
    nxt_pt, nxt_step, nxt_ref = touchdown, land, (0.0, vc_td)
    for step in reversed(steps[:li]):
        made = a.step(step, nxt_step, nxt_pt, nxt_ref)
        airborne = made + airborne
        ref_cas = step.start_cas_kt if step.start_cas_kt is not None else nxt_ref[1]
        nxt_pt, nxt_step, nxt_ref = made[0], step, (step.start_altitude_ft, ref_cas)
    return airborne + ground


# ----------------------------------------------------------------- along the profile (Vol 2 s3.6)


def interpolate(points: list[Point], s_ft: float) -> tuple[float, float, float]:
    """(height ft, speed kt, power) at ground distance `s_ft` (3-2a to 3-2h): height linear in distance, speed and
    power linear in time (their squares in distance), with 3-2e to 3-2g where the power is negative. Beyond the profile
    the speed and power hold and the height carries on along the end segment's gradient (s3.6.6)."""
    if len(points) < 2:
        raise ValueError('a profile needs two points')
    i = 1
    while i < len(points) - 1 and points[i].distance_ft < s_ft:
        i += 1
    a, b = points[i - 1], points[i]
    span = b.distance_ft - a.distance_ft
    f = (s_ft - a.distance_ft) / span if span else 1.0
    z = a.height_ft + f * (b.height_ft - a.height_ft)
    if f < 0 or f > 1:  # outside: hold speed and power of the nearer end (s3.6.6)
        end = a if f < 0 else b
        return z, end.tas_kt, end.thrust
    v = math.sqrt(max(a.tas_kt**2 + f * (b.tas_kt**2 - a.tas_kt**2), 0.0))
    p1, p2 = a.thrust, b.thrust
    if p1 >= 0 and p2 >= 0:
        p = math.sqrt(p1**2 + f * (p2**2 - p1**2))  # 3-2d
    elif p1 < 0 and p2 < 0:
        p = -math.sqrt(p1**2 + f * (p2**2 - p1**2))  # 3-2e
    elif p1 < 0:
        p = p1 + (p2 - p1) * math.sqrt(f)  # 3-2f
    else:
        p = p2 + (p1 - p2) * math.sqrt(1 - f)  # 3-2g
    return z, v, p


def takeoff_roll(p1: Point, p2: Point) -> list[Point]:
    """s3.6.2: the take-off ground roll cut into int(1 + dV/10 m/s) segments of equal speed change at constant
    acceleration (3-3f to 3-3i; 3-3a to 3-3d from standing), power changing by equal steps (3-3e)."""
    v1, v2 = p1.tas_kt * KT_FTS * FT, p2.tas_kt * KT_FTS * FT  # m/s, as 3-3a counts in 10 m/s
    s = p2.distance_ft - p1.distance_ft
    n = int(1 + abs(v2 - v1) / 10)
    dv = (v2 - v1) / n
    out, travelled = [p1], 0.0
    for k in range(1, n + 1):
        travelled += (v1 + dv * (k - 0.5)) * 2 * s / ((v2 + v1) * n)  # 3-3i
        tas = (v1 + dv * k) / (KT_FTS * FT)
        out.append(Point(p1.distance_ft + travelled, 0.0, tas, p1.thrust + (p2.thrust - p1.thrust) * k / n, 'roll'))
    return out


# ----------------------------------------------------------------- EASA's tables


def _number(v):
    if v is None:
        return None
    text = str(v).strip()
    if text in ('', '-', 'n/a', 'N/A'):
        return None
    return float(text)


def _key(header) -> str:
    """A header made comparable across ANP v2.3, ANP v9 and ECAC's Volume 3: units in brackets dropped, then letters
    and digits only ('Start \\nThrust (%)' -> 'startthrust', 'Aircraft Identifier' -> 'acftid')."""
    s = re.sub(r'\([^)]*\)\)?', '', str(header or '')).lower()
    s = re.sub(r'[^a-z0-9]', '', s)
    for long, short in (('maximum', 'max'), ('identifier', 'id'), ('operation', 'op'), ('aircraft', 'acft')):
        s = s.replace(long, short)
    return s


def keyed(rows) -> list[dict]:
    """Rows with comparable keys (see _key) and stripped text."""
    out = []
    for r in rows:
        out.append({_key(k): (v.strip() if isinstance(v, str) else v) for k, v in r.items() if k is not None})
    return out


def performance_from_rows(aircraft: dict, jet=(), prop=(), aero=(), weights=()) -> Performance:
    """One aircraft's Performance from its keyed table rows (keyed()): ANP's or ECAC's reference ones alike."""
    acft = _text(aircraft['acftid'])
    jet_c = {
        _norm(r['thrustrating']): tuple(_number(r.get(c)) or 0.0 for c in ('e', 'f', 'ga', 'gb', 'h'))
        for r in jet
        if _text(r.get('acftid')) == acft
    }
    prop_c = {
        _norm(r['thrustrating']): (_number(r['propellerefficiency']), _number(r['installednetpropulsivepower']))
        for r in prop
        if _text(r.get('acftid')) == acft
    }
    aero_c = {}
    for r in aero:
        if _text(r.get('acftid')) != acft:
            continue
        op = _text(r['optype']).upper()[:1]
        cd = _number(r.get('cd'))  # ECAC's Volume 3 shares one column: C on departures, D on approaches
        coeffs = {'B': _number(r.get('b')), 'C': _number(r.get('c')), 'D': _number(r.get('d')), 'R': _number(r['r'])}
        if cd is not None:
            coeffs['C' if op == 'D' else 'D'] = cd
        aero_c[(op, _text(r['flapid']))] = {k: v for k, v in coeffs.items() if v is not None}
    weights_c = {
        _text(r['stagelength']): _number(r['weight'])
        for r in weights
        if _text(r.get('acftid')) == acft and _text(r.get('op', 'D')).upper() in ('D', '')
    }
    return Performance(
        acft,
        int(_number(aircraft['numberofengines'])),
        _number(aircraft['maxgrosslandingweight']),
        _number(aircraft['maxsealevelstaticthrust']),
        _text(aircraft.get('powerparameter')) or 'CNT (lb)',
        jet_c,
        prop_c,
        aero_c,
        weights_c,
    )


def steps_from_rows(rows) -> list[Step]:
    """Procedural steps from keyed rows of ONE profile (departure or approach), in step-number order."""
    out = []
    for r in sorted(rows, key=lambda r: _number(r['stepnumber'])):
        out.append(
            Step(
                kind=_norm(r['steptype']),
                flap=_text(r.get('flapid')),
                rating=_norm(r.get('thrustrating')),
                end_altitude_ft=_number(r.get('endpointaltitude')),
                rate_of_climb_fpm=_number(r.get('rateofclimb')),
                end_cas_kt=_number(r.get('endpointcas')),
                accel_pct=_number(r.get('accelpercentage')),
                distance_ft=_number(r.get('distance')),
                start_altitude_ft=_number(r.get('startaltitude')),
                start_cas_kt=_number(r.get('startcas')),
                descent_angle_deg=_number(r.get('descentangle')),
                touchdown_roll_ft=_number(r.get('touchdownroll')),
                start_thrust_pct=_number(r.get('startthrust')),
            )
        )
    return out


TABLES = {
    'aircraft': 'aircraft',
    'jet': 'jetenginecoefficients',
    'prop': 'propellerenginecoefficients',
    'aero': 'aerodynamiccoefficients',
    'weights': 'defaultweights',
    'departure': 'defaultdepartureproceduralsteps',
    'approach': 'defaultapproachproceduralsteps',
    'fixed': 'defaultfixedpointprofiles',
}


def _read(d: Path, name: str) -> list[dict]:
    """One ANP table from a release folder: v2.3's ';'-separated latin-1 CSVs or v9's workbooks; [] if absent."""
    for p in sorted(d.iterdir()):
        stem = _norm(p.stem)
        if not (stem.endswith(name) or re.search(name + r'v\d+$', stem)):
            continue
        if p.suffix.lower() == '.csv':
            with open(p, encoding='latin-1', newline='') as fh:
                return keyed(csv.DictReader(fh, delimiter=';'))
        if p.suffix.lower() == '.xlsx':
            import openpyxl  # only the workbooks need it

            # read_only keeps the file open until close(): left open, Windows holds a lock on EASA's workbook.
            wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
            try:
                it = wb.worksheets[0].iter_rows(values_only=True)
                head = next(it)
                return keyed(dict(zip(head, row, strict=False)) for row in it if row and row[0] is not None)
            finally:
                wb.close()
    return []


@dataclass
class Profiles:
    """ANP's flight-performance tables, by aircraft: performance, departure steps by (acft, profile, stage), approach
    steps by (acft, profile), fixed-point profiles by (acft, op, profile, stage)."""

    performance: dict = field(default_factory=dict)
    departures: dict = field(default_factory=dict)
    approaches: dict = field(default_factory=dict)
    fixed: dict = field(default_factory=dict)


def load_anp(*dirs: Path) -> Profiles:
    """Read ANP releases in order; an aircraft in a later release replaces the earlier one's WHOLE (every table), as
    n65_types.load_anp() does for noise. The folders are gitignored or outside the repo; nothing read is kept."""
    out = Profiles()
    for d in dirs:
        t = {name: _read(Path(d), fname) for name, fname in TABLES.items()}
        fresh = {_text(a['acftid']) for a in t['aircraft'] if a.get('acftid')}
        for table in (out.performance, out.departures, out.approaches, out.fixed):
            for k in [k for k in table if (k if isinstance(k, str) else k[0]) in fresh]:
                del table[k]
        for a in t['aircraft']:
            if not a.get('acftid') or _number(a.get('numberofengines')) is None:
                continue
            perf = performance_from_rows(a, t['jet'], t['prop'], t['aero'], t['weights'])
            out.performance[perf.acft_id] = perf
        groups: dict = {}
        for r in t['departure']:
            groups.setdefault(('D', _text(r['acftid']), _text(r['profileid']), _text(r['stagelength'])), []).append(r)
        for r in t['approach']:
            groups.setdefault(('A', _text(r['acftid']), _text(r['profileid'])), []).append(r)
        for key, rows in groups.items():
            (out.departures if key[0] == 'D' else out.approaches)[key[1:]] = steps_from_rows(rows)
        for r in t['fixed']:
            stage = _text(r.get('stagelength')) or '1'
            key = (_text(r['acftid']), _text(r['optype']).upper(), _text(r['profileid']), stage)
            out.fixed.setdefault(key, []).append(r)
    for key, rows in out.fixed.items():
        if rows and isinstance(rows[0], dict):
            rows.sort(key=lambda r: _number(r['pointnumber']))
            out.fixed[key] = [
                Point(
                    _number(r['distance']),
                    _number(r['altitudeafe']),
                    _number(r['tas']),
                    _number(r['powersetting']),
                    'fixed',
                )
                for r in rows
            ]
    return out


def available(db: Profiles, acft_id: str, op: str) -> list[tuple[str, str, str]]:
    """What ANP offers for an aircraft and op ('D'/'A'): [(source 'steps'/'fixed', profile, stage)]. Which procedure
    stands for a flight (ICAO_A, ICAO_B, DEFAULT...) and which stage length is the caller's choice, said with the
    result."""
    out = []
    if op == 'D':
        out += [('steps', p, s) for (a, p, s) in db.departures if a == acft_id]
    else:
        out += [('steps', p, '1') for (a, p) in db.approaches if a == acft_id]
    out += [('fixed', p, s) for (a, o, p, s) in db.fixed if a == acft_id and o == op]
    return sorted(out)


def profile(
    db: Profiles, acft_id: str, op: str, profile_id: str = 'DEFAULT', stage: str = '1', atm: Atmosphere = REFERENCE
) -> tuple[list[Point], str]:
    """A flight's profile points and where they came from ('steps': synthesised by Appendix B for `atm`; 'fixed':
    ANP's published fixed-point profile, for its reference day, power in the noise table's own unit). Procedural steps
    are preferred where both exist: they answer to the day's air and wind."""
    perf = db.performance.get(acft_id)
    stage = str(stage)
    if op == 'D' and (acft_id, profile_id, stage) in db.departures and perf is not None:
        weight = perf.weights.get(stage)
        if weight is None:
            raise KeyError(f'{acft_id}: no default weight for stage length {stage}')
        return departure(perf, db.departures[(acft_id, profile_id, stage)], weight, atm), 'steps'
    if op == 'A' and (acft_id, profile_id) in db.approaches and perf is not None:
        return approach(perf, db.approaches[(acft_id, profile_id)], atm), 'steps'
    fixed = db.fixed.get((acft_id, op, profile_id, stage))
    if fixed:
        return fixed, 'fixed'
    raise KeyError(f'{acft_id}: no {op} profile {profile_id!r} at stage {stage}')
