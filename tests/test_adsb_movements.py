"""The movement counter behind "how often planes pass" (2026-10-15).

`scripts/adsb_movements.py` turns community flight tracks into take-offs and
landings per runway, so the tracks can be checked against the CAA's official
movement counts before anything per-home is built on them. These tests fly
synthetic aircraft down Heathrow's REAL runways (data/flight-procedures.json),
one rule at a time.

The holding-point test is the regression for the first run's defect: an aircraft
silent at the holding point for over RUN_GAP_S split its time on the ground into
two low runs, both saw the same climb, and one take-off was counted twice. On
2026-10-14 that put take-offs above landings at almost every airport (Stansted
380 against 288) and Heathrow at 100.1% of the CAA's day for the wrong reason;
bounded by the neighbouring runs, Stansted read 283 against 277 and Heathrow
97.6%.
"""
import datetime as dt
import importlib.util
import math
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / 'scripts'


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


mv = _load('adsb_movements')
ax = _load('adsb_extract')

FIELD = 0      # the field's pressure level used throughout
T0 = 1_000_000.0


def offset(lat, lon, bearing, km):
    """The point `km` from (lat, lon) on `bearing`."""
    d, b = km / 6371.0, math.radians(bearing)
    p1, l1 = math.radians(lat), math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(b))
    l2 = l1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(p1),
                         math.cos(d) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), math.degrees(l2)


def pt(t, lat, lon, alt, track):
    # [epoch_s, lat, lon, alt_baro, alt_geom, gs, track, baro_rate, flags, callsign]
    return [t, lat, lon, alt, None, 140, track, None, 0, 'TEST1']


class Heathrow:
    ap = mv.load_airports()['LHR']
    thr27r, brg27 = ap['runways']['27R']
    thr27l, _ = ap['runways']['27L']

    @classmethod
    def approach(cls, thr, t, km_out=12, step_km=0.5):
        """A 3-degree final into `thr` from the east, ending at touchdown."""
        pts, n = [], int(km_out / step_km)
        for i in range(n, -1, -1):
            km = i * step_km
            lat, lon = offset(thr[0], thr[1], (cls.brg27 + 180) % 360, km)
            alt = round(km * 1000 * math.tan(math.radians(3)) * 3.28084)
            pts.append(pt(t, lat, lon, alt, cls.brg27))
            t += 13
        return pts, t

    @classmethod
    def climb_out(cls, thr, t, km_out=12, step_km=0.5):
        """Lift-off from 1.5 km down `thr`'s runway, climbing west at ~8%."""
        pts = []
        for i in range(int(km_out / step_km) + 1):
            km = 1.5 + i * step_km
            lat, lon = offset(thr[0], thr[1], cls.brg27, km)
            pts.append(pt(t, lat, lon, round(i * step_km * 1000 * 0.08 * 3.28084), cls.brg27))
            t += 10
        return pts, t

    @classmethod
    def ground(cls, thr, t, n=4, step_s=20):
        lat, lon = offset(thr[0], thr[1], cls.brg27, 1.0)
        return [pt(t + i * step_s, lat, lon, 'ground', cls.brg27) for i in range(n)], t + n * step_s


def count(points):
    moves, _ = mv.movements({'pts': points}, Heathrow.ap, FIELD)
    return [(kind, rw) for kind, rw, _ in moves]


class MovementRuleTests(unittest.TestCase):
    def test_a_landing_is_one_landing_on_its_runway(self):
        approach, t = Heathrow.approach(Heathrow.thr27r, T0)
        rollout, _ = Heathrow.ground(Heathrow.thr27r, t)
        self.assertEqual(count(approach + rollout), [('landing', '27R')])

    def test_a_take_off_is_one_take_off(self):
        roll, t = Heathrow.ground(Heathrow.thr27l, T0)
        climb, _ = Heathrow.climb_out(Heathrow.thr27l, t)
        self.assertEqual(count(roll + climb), [('take-off', '27L')])

    def test_a_silent_wait_at_the_holding_point_is_not_a_second_take_off(self):
        taxi, t = Heathrow.ground(Heathrow.thr27l, T0)
        lined_up, t = Heathrow.ground(Heathrow.thr27l, t + mv.RUN_GAP_S + 240)
        climb, _ = Heathrow.climb_out(Heathrow.thr27l, t)
        self.assertEqual(count(taxi + lined_up + climb), [('take-off', '27L')])

    def test_a_silent_turnaround_is_one_landing_then_one_take_off(self):
        approach, t = Heathrow.approach(Heathrow.thr27r, T0)
        rollout, t = Heathrow.ground(Heathrow.thr27r, t)
        later, t = Heathrow.ground(Heathrow.thr27l, t + 3600)
        climb, _ = Heathrow.climb_out(Heathrow.thr27l, t)
        self.assertEqual(count(approach + rollout + later + climb),
                         [('landing', '27R'), ('take-off', '27L')])

    def test_a_circuit_counts_as_the_caa_counts_it(self):
        """Touch-and-go: down, up to circuit height, down again, away."""
        approach, t = Heathrow.approach(Heathrow.thr27r, T0, km_out=6)
        touch, t = Heathrow.ground(Heathrow.thr27r, t, n=2)
        climb, t = Heathrow.climb_out(Heathrow.thr27r, t, km_out=4)   # ~1,050 ft
        again, t = Heathrow.approach(Heathrow.thr27r, t + 300, km_out=6)
        stop, t = Heathrow.ground(Heathrow.thr27r, t, n=2)
        away, _ = Heathrow.climb_out(Heathrow.thr27r, t)
        kinds = [k for k, _ in count(approach + touch + climb + again + stop + away)]
        self.assertEqual(kinds, ['landing', 'take-off', 'landing', 'take-off'])

    def test_a_low_pass_that_never_comes_down_is_not_a_movement(self):
        lat, lon = Heathrow.ap['centre']
        pts = [pt(T0 + i * 10, *offset(lat, lon, 0, -3 + i * 0.5), 1500, 0) for i in range(13)]
        self.assertEqual(count(pts), [])

    def test_the_centreline_decides_between_parallel_runways(self):
        for thr, want in ((Heathrow.thr27r, '27R'), (Heathrow.thr27l, '27L')):
            approach, t = Heathrow.approach(thr, T0)
            rollout, _ = Heathrow.ground(thr, t)
            self.assertEqual(count(approach + rollout), [('landing', want)])


class CircuitTests(unittest.TestCase):
    """Circuits are movements by the CAA's definition ("Touch and go operations
    are counted as two movements") and airports report them unevenly, so they
    are counted in their own column (2026-10-15, East Midlands)."""

    def test_a_touch_and_go_is_two_circuit_movements_and_a_full_stop_is_none(self):
        approach, t = Heathrow.approach(Heathrow.thr27r, T0, km_out=6)
        touch, t = Heathrow.ground(Heathrow.thr27r, t, n=2)
        climb, t = Heathrow.climb_out(Heathrow.thr27r, t, km_out=4)   # ~1,050 ft
        again, t = Heathrow.approach(Heathrow.thr27r, t + 300, km_out=6)
        stop, t = Heathrow.ground(Heathrow.thr27r, t)
        later, t = Heathrow.ground(Heathrow.thr27l, t + 3600)
        away, _ = Heathrow.climb_out(Heathrow.thr27l, t)
        moves, _ = mv.movements({'pts': approach + touch + climb + again + stop + later + away},
                                Heathrow.ap, FIELD)
        self.assertEqual([k for k, _, _ in moves], ['landing', 'take-off', 'landing', 'take-off'])
        self.assertEqual(mv.circuit_movements(moves), 2)

    def test_one_bad_altitude_reading_is_not_a_circuit(self):
        """Code review 2026-10-15: a single 5,000 ft report on short final split
        one landing into a landing, a take-off and a landing 13 s apart, and the
        pair was set aside as a circuit where the ceiling could not see it."""
        approach, t = Heathrow.approach(Heathrow.thr27r, T0)
        rollout, _ = Heathrow.ground(Heathrow.thr27r, t)
        pts = approach + rollout
        low = [i for i, p in enumerate(pts) if isinstance(p[3], int) and p[3] <= mv.LOW_ABOVE_FT]
        spike = list(pts[low[1]])
        spike[0], spike[3] = (pts[low[1]][0] + pts[low[2]][0]) / 2, 5000
        moves, _ = mv.movements({'pts': pts[:low[1] + 1] + [spike] + pts[low[1] + 1:]}, Heathrow.ap, FIELD)
        self.assertGreater(len(moves), 1)             # the glitch still splits the run
        self.assertEqual(mv.circuit_movements(moves), 0)

    def test_a_turnaround_is_not_a_circuit(self):
        approach, t = Heathrow.approach(Heathrow.thr27r, T0)
        rollout, t = Heathrow.ground(Heathrow.thr27r, t)
        later, t = Heathrow.ground(Heathrow.thr27l, t + 3600)
        climb, _ = Heathrow.climb_out(Heathrow.thr27l, t)
        moves, _ = mv.movements({'pts': approach + rollout + later + climb}, Heathrow.ap, FIELD)
        self.assertEqual(len(moves), 2)
        self.assertEqual(mv.circuit_movements(moves), 0)


class FeedOutageTests(unittest.TestCase):
    """adsb.lol's archive has holes (6 of 31 days in August 2026). Each is
    measured from the feed, never from an airport's counts."""

    DAY = dt.date(2026, 8, 3)

    @staticmethod
    def month(n_days=15, usual=100):
        start = dt.date(2026, 8, 1)
        return {start + dt.timedelta(days=i): [usual] * 144 for i in range(n_days)}

    def test_the_profile_counts_each_aircraft_once_per_window_per_region(self):
        t0 = dt.datetime(2026, 8, 3, tzinfo=dt.UTC).timestamp()
        lhr = Heathrow.ap['centre']
        traces = [{'pts': [pt(t0 + s, *lhr, 2000, 0) for s in (0, 5, 9, 3001)]},
                  {'pts': [pt(t0 + 1, 40.64, -73.78, 2000, 0)]}]       # JFK
        prof = mv.feed_profile(traces, self.DAY)
        self.assertEqual((prof['uk'][0], prof['uk'][5], prof['us'][0]), (1, 1, 1))
        self.assertEqual(sum(prof['uk']) + sum(prof['us']), 3)

    def test_an_empty_stretch_marks_the_day(self):
        profiles = self.month()
        profiles[self.DAY][60:66] = [0] * 6          # an hour of nothing, as on 19 Aug
        gaps = mv.feed_gaps(profiles)
        self.assertEqual(gaps[self.DAY], 6)
        self.assertEqual(sum(gaps.values()), 6)

    def test_a_thinned_feed_with_no_gap_is_an_outage_too(self):
        """1 Aug 2026: 16:00-24:00 carried ~5% of the usual aircraft and not one
        silent minute, so a test for gaps passes it. Proven red with
        FEED_OUT_RATIO at 0.04, i.e. a test that only sees silence."""
        profiles = self.month()
        profiles[self.DAY][96:144] = [6] * 48
        self.assertEqual(mv.feed_gaps(profiles)[self.DAY], 48)

    def test_a_quiet_but_healthy_day_is_not_an_outage(self):
        """The lowest window on any healthy August day read 0.56 of usual
        (UK, 27 Aug); a bank-holiday dip must not cost a day."""
        profiles = self.month()
        profiles[self.DAY] = [56] * 144
        self.assertEqual(mv.feed_gaps(profiles)[self.DAY], 0)

    def test_a_clock_change_is_not_an_outage(self):
        """Timetables run on local time. Compared in UTC alone, August's healthy
        UK days moved an hour later read false outages on 24 of 25 days, which
        is every day of the week after the October change. 25 Oct 2026: BST
        ends, so the same local morning arrives an hour later in UTC."""
        def day_of_traffic(offset_bins):
            local = [10] * 36 + [100] * 108             # quiet to 06:00 local, busy after
            return local[offset_bins:] + local[:offset_bins]   # UTC window b holds local b + offset
        profiles = {}
        for i in range(-10, 7):
            day = dt.date(2026, 10, 25) + dt.timedelta(days=i)
            profiles[day] = day_of_traffic(mv.clock_offset_bins(day, 'uk'))
        self.assertEqual(mv.clock_offset_bins(dt.date(2026, 10, 24), 'uk'), 6)
        self.assertEqual(mv.clock_offset_bins(dt.date(2026, 10, 25), 'uk'), 0)
        gaps = mv.feed_gaps(profiles, 'uk')
        self.assertEqual({d: n for d, n in gaps.items() if n}, {})

    def test_too_few_days_to_know_usual_are_not_judged(self):
        gaps = mv.feed_gaps(self.month(n_days=mv.FEED_MIN_REFERENCE_DAYS - 1))
        self.assertTrue(all(v is None for v in gaps.values()))

    def test_every_airport_is_judged_by_its_own_region(self):
        regions = {code: ap['region'] for code, ap in mv.load_airports().items()}
        self.assertTrue(all(regions[c] == 'uk' for c in mv.CAA_NAMES.values()))
        self.assertEqual({regions[c] for c in ('JFK', 'SFO', 'TEB')}, {'us'})


class UsableShareTests(unittest.TestCase):
    """An outage day is left out and the official figure scaled to the rest."""

    PERIOD = {dt.date(2026, 2, 1) + dt.timedelta(days=i) for i in range(28)}   # four weeks

    @staticmethod
    def timetable(day):
        return {5: 25, 6: 75}.get(day.weekday(), 100)        # London City's weekly shape

    def test_a_lost_saturday_costs_a_saturday_not_an_average_day(self):
        lost = min(d for d in self.PERIOD if d.weekday() == 5)
        kept = {d: self.timetable(d) for d in self.PERIOD if d != lost}
        whole = sum(self.timetable(d) for d in self.PERIOD)
        self.assertAlmostEqual(mv.usable_share(kept, self.PERIOD), (whole - 25) / whole)

    def test_a_weekday_never_kept_cannot_be_estimated(self):
        kept = {d: self.timetable(d) for d in self.PERIOD if d.weekday() != 2}
        self.assertIsNone(mv.usable_share(kept, self.PERIOD))


class FieldLevelTests(unittest.TestCase):
    def test_measured_from_touchdowns_when_the_surface_is_heard(self):
        traces = []
        for k in range(mv.MIN_TOUCHDOWNS):
            approach, t = Heathrow.approach(Heathrow.thr27r, T0 + k * 1000)
            approach[-1][3] = -300 + k          # QNH puts the field near -300 ft
            rollout, _ = Heathrow.ground(Heathrow.thr27r, t)
            traces.append({'pts': approach + rollout})
        level, how = mv.field_level(traces, Heathrow.ap)
        self.assertEqual(level, -298)
        self.assertIn('touchdown', how)


class PublishFloorTests(unittest.TestCase):
    """coverage_verdict() is the gate on every per-home figure (2026-10-15)."""

    def test_close_to_the_official_count_over_the_same_period_passes(self):
        self.assertTrue(mv.coverage_verdict(9_900, 10_000, same_period=True)[0])

    def test_a_shortfall_fails_because_it_would_understate(self):
        ok, why = mv.coverage_verdict(9_000, 10_000, same_period=True)
        self.assertFalse(ok)
        self.assertIn('understate', why)

    def test_an_excess_fails_because_not_every_count_is_a_movement(self):
        self.assertFalse(mv.coverage_verdict(11_000, 10_000, same_period=True)[0])

    def test_too_little_traffic_is_not_judged(self):
        ok, why = mv.coverage_verdict(46, 46, same_period=True)
        self.assertFalse(ok)
        self.assertIn('too little', why)

    def test_a_month_with_an_unmeasured_day_cannot_pass(self):
        """Code review 2026-10-15: 28 measured days against a 31-day figure,
        with a rule over-counting by ~10%, landed inside the floor and printed
        PUBLISHABLE."""
        ok, why = mv.period_verdict(10_000, 10_000, same_period=True, missing_days=3)
        self.assertFalse(ok)
        self.assertIn('unmeasured', why)
        self.assertTrue(mv.period_verdict(10_000, 10_000, same_period=True, missing_days=0)[0])

    def test_circuits_an_airport_leaves_out_do_not_breach_the_ceiling(self):
        """East Midlands, August 2026: 105.5% with its circuits, 96.6% without,
        against a CAA month holding 62 training movements."""
        self.assertTrue(mv.coverage_verdict(10_550, 10_000, same_period=True, circuits=890)[0])
        self.assertFalse(mv.coverage_verdict(10_550, 10_000, same_period=True)[0])

    def test_circuits_never_lift_a_shortfall(self):
        """The floor counts every movement: a circuit is real, and loud."""
        ok, why = mv.coverage_verdict(9_400, 10_000, same_period=True, circuits=2_000)
        self.assertFalse(ok)
        self.assertIn('understate', why)

    def test_an_airport_must_fit_one_reading_of_its_return_at_both_ends(self):
        """Code review 2026-10-15: 110% with circuits and 80% without passed,
        the floor read one way and the ceiling the other. If the return holds
        the circuits, that is a 10% over-count; if not, a 20% shortfall."""
        ok, why = mv.coverage_verdict(11_000, 10_000, same_period=True, circuits=3_000)
        self.assertFalse(ok)
        self.assertIn('neither', why)
        self.assertTrue(mv.coverage_verdict(9_960, 10_000, True, circuits=3_000)[0])   # Cardiff
        self.assertTrue(mv.coverage_verdict(10_550, 10_000, True, circuits=890)[0])    # East Midlands

    def test_a_month_mostly_lost_to_outages_cannot_pass(self):
        ok, why = mv.period_verdict(10_000, 10_000, True, 0, kept_days=22, period_len=31)
        self.assertFalse(ok)
        self.assertIn('too few', why)
        self.assertTrue(mv.period_verdict(10_000, 10_000, True, 0, kept_days=25, period_len=31)[0])

    def test_an_official_count_that_cannot_be_scaled_cannot_pass(self):
        ok, why = mv.period_verdict(10_000, None, True, 0, kept_days=31, period_len=31)
        self.assertFalse(ok)
        self.assertIn('weekday', why)

    def test_different_periods_never_pass_however_close(self):
        """One day against 2025's average day mixes coverage with traffic change."""
        ok, why = mv.coverage_verdict(1_315, 1_315, same_period=False)
        self.assertFalse(ok)
        self.assertTrue(why.startswith('provisional'))


class CaaTableTests(unittest.TestCase):
    def test_every_uk_airport_we_draw_has_exactly_one_caa_name(self):
        uk = set(mv.load_airports((mv.PROCEDURE_FILES[0],)))
        self.assertEqual(set(mv.CAA_NAMES.values()), uk)

    def _write(self, header, period, name_value=None):
        """A CAA-shaped CSV holding every airport we name, in either layout."""
        import tempfile
        rows = [header]
        for i, name in enumerate(mv.CAA_NAMES):
            rows.append(f'01/01/2026 00:00,{period},Group,{name_value or name},{1000 + i}')
        tmp = tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False, encoding='utf-8-sig')
        tmp.write('\n'.join(rows) + '\n')
        tmp.close()
        self.addCleanup(Path(tmp.name).unlink)
        return Path(tmp.name)

    def test_reads_the_annual_and_the_monthly_layouts(self):
        annual = self._write('rundate,report_period,rpt_apt_grp_name,rpt_apt_name,grand_total', '2025')
        monthly = self._write('rundate,reporting_period,reporting_airport_group_name,'
                              'reporting_airport_name,grand_total', '202608')
        for path, period in ((annual, '2025'), (monthly, '202608')):
            got_period, totals = mv.caa_table(path)
            self.assertEqual(got_period, period)
            self.assertEqual(totals['LHR'], 1000 + list(mv.CAA_NAMES).index('HEATHROW'))

    def test_a_renamed_airport_fails_loudly(self):
        path = self._write('rundate,report_period,rpt_apt_grp_name,rpt_apt_name,grand_total', '2025',
                           name_value='SOMEWHERE ELSE')
        with self.assertRaises(SystemExit):
            mv.caa_table(path)

    def test_a_period_is_every_day_it_covers(self):
        self.assertEqual(len(mv.period_days('202608')), 31)
        self.assertEqual(len(mv.period_days('202402')), 29)
        self.assertEqual(len(mv.period_days('2024')), 366)


class ExtractFilterTests(unittest.TestCase):
    centres = ax.airport_centres()
    near = ax.boxes(centres, ax.REGION_KM)
    wide = ax.boxes(centres, ax.REGION_KM + ax.PREFILTER_MARGIN_KM)
    items = list(centres.items())

    def test_keeps_low_points_near_an_airport_and_drops_high_or_far_ones(self):
        lat, lon = self.centres['LHR']
        far = offset(lat, lon, 270, 100)        # Swindon: no airport we draw within reach
        self.assertTrue(all(ax.km_between(*far, *c) > ax.REGION_KM for c in self.centres.values()))
        doc = {'icao': 'abc123', 'timestamp': T0, 'trace': [
            [0, lat, lon, 3000, 150, 270, 0, -700, {'flight': 'BAW1  '}, 'adsb_icao', 3100],
            [5, lat, lon, ax.ALT_CEILING_FT + 500, 150, 270, 0, 0, None, 'adsb_icao', None],
            [9, far[0], far[1], 2000, 150, 270, 0, 0, None, 'adsb_icao', None],
            [12, lat, lon, 'ground', 10, 270, 0, None, None, 'adsb_icao', None],
        ]}
        rec = ax.filter_trace(doc, self.near, self.wide, self.items)
        self.assertEqual([p[3] for p in rec['pts']], [3000, 'ground'])
        self.assertEqual([p[9] for p in rec['pts']], ['BAW1', 'BAW1'])   # carried forward
        self.assertEqual(rec['pts'][0][0], T0)

    def test_a_trace_that_never_comes_near_is_dropped(self):
        doc = {'icao': 'abc124', 'timestamp': T0,
               'trace': [[i, 0.0, 0.0 + i * 0.01, 2000, 150, 90, 0, 0, None, 'adsb_icao', None]
                         for i in range(50)]}
        self.assertIsNone(ax.filter_trace(doc, self.near, self.wide, self.items))


if __name__ == '__main__':
    unittest.main()
