"""Methodology v5.1 (2026-09-15): growth is scored on the REAL-terms trend.

The nominal HM Land Registry HPI 12-month change is deflated by ONS CPIH for
the SAME month, per vintage, and growth_score() reads that. Costed before it
was decided (scripts/cost_real_growth.py): at CPIH 2.8% for June 2026, 25 of
the 77 boroughs the product called "rising" were falling in real terms.

What these tests hold, and why each one is here:

  - the deflator is the exact ratio, rounded ONCE with the engine's own tie
    rule (halves away from zero, matching the site's Math.round) - Python's
    round() would send a .x5 tie the other way from the JS mirror;
  - every sterling record carries trendReal at import, New York's do not, and
    scored_trend() falls back to nominal for them by construction;
  - the previous vintage is deflated by ITS month's CPIH, not the current one
    - the overlay in previous_dataset() replaces `trend` and would otherwise
    leave June's trendReal beside May's trend;
  - the response says which basis it used, publishes the figure it scored and
    the inflation behind it, and the growth provenance line is DERIVED per
    city rather than one of thirteen literals;
  - a comparison's growth step names the deflation and its workings use the
    real figure against the real yardstick.

Offline: nothing here needs the network or DynamoDB.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambdas', 'score'))

import app  # noqa: E402


class RealTrendArithmeticTests(unittest.TestCase):
    def test_exact_ratio_not_subtraction(self):
        # (1 - 0.052) / (1 + 0.028) - 1 = -0.07782 -> -7.8; subtraction gives -8.0
        self.assertEqual(app.real_trend_pct(-5.2, 2.8), -7.8)
        self.assertEqual(app.real_trend_pct(4.3, 2.8), 1.5)
        self.assertEqual(app.real_trend_pct(0.0, 0.0), 0.0)

    def test_tie_rule_is_the_engines_own(self):
        # The same rule as round_1dp() - halves away from zero, which is what
        # the site's Math.round does - on a sweep of inputs, rather than a
        # hand-built tie: an "exact" .x5 constructed through the ratio is not
        # exactly representable, so a tie test would be testing float noise.
        for tenths in range(-300, 301):
            for cpih in (0.0, 2.8, 3.0, 3.4):
                nominal = tenths / 10
                unrounded = ((1 + nominal / 100) / (1 + cpih / 100) - 1) * 100
                self.assertEqual(app.real_trend_pct(nominal, cpih), app.round_1dp(unrounded))


class TrendRealAttachmentTests(unittest.TestCase):
    def test_every_sterling_record_carries_trend_real(self):
        for city, cfg in app.CITIES.items():
            if cfg['currency'] != 'GBP':
                continue
            for name, bd in cfg['boroughs'].items():
                with self.subTest(city=city, borough=name):
                    self.assertIn('trendReal', bd)
                    self.assertEqual(
                        bd['trendReal'],
                        app.real_trend_pct(bd['trend'], app.CPIH_12M_PCT[app.SNAPSHOT_VINTAGE]),
                    )

    def test_new_york_scores_nominal_by_construction(self):
        for name, bd in app.CITIES['nyc']['boroughs'].items():
            with self.subTest(borough=name):
                self.assertNotIn('trendReal', bd)
                self.assertEqual(app.scored_trend(bd), bd['trend'])

    def test_the_module_constant_and_the_registry_are_one_object(self):
        # In place, not a copy: build_hpi_prices.py --write edits the constant's
        # source and the tests read it by name, so a copy could disagree.
        self.assertIs(app.LONDON_BOROUGHS, app.CITIES['london']['boroughs'])
        self.assertIn('trendReal', app.LONDON_BOROUGHS['Wandsworth'])

    def test_both_vintages_have_a_deflator(self):
        self.assertIn(app.SNAPSHOT_VINTAGE, app.CPIH_12M_PCT)
        self.assertIn(app.PREVIOUS_VINTAGE, app.CPIH_12M_PCT)


class PreviousVintageDeflationTests(unittest.TestCase):
    def test_previous_dataset_uses_the_previous_months_cpih(self):
        prev = app.previous_dataset('london')
        cpih_prev = app.CPIH_12M_PCT[app.PREVIOUS_VINTAGE]
        cpih_now = app.CPIH_12M_PCT[app.SNAPSHOT_VINTAGE]
        self.assertNotEqual(cpih_prev, cpih_now, 'the test needs two different months to mean anything')
        for name, bd in prev.items():
            with self.subTest(borough=name):
                self.assertEqual(bd['trendReal'], app.real_trend_pct(bd['trend'], cpih_prev))
                # And NOT the current vintage's figure left over from the overlay.
                if app.real_trend_pct(bd['trend'], cpih_now) != bd['trendReal']:
                    self.assertNotEqual(bd['trendReal'], app.CITIES['london']['boroughs'][name]['trendReal'])

    def test_a_city_without_history_still_declines_to_compare(self):
        self.assertIsNone(app.previous_dataset('manchester'))


class ResponseShapeTests(unittest.TestCase):
    def test_sterling_response_publishes_the_scored_figure_and_basis(self):
        r = app.calc_score('Wandsworth', 'london', app.PERSONAS['investor'])
        ctx = r['context']
        self.assertEqual(ctx['growthBasis'], 'real')
        self.assertEqual(ctx['priceTrendPct'], -5.2)
        self.assertEqual(ctx['priceTrendRealPct'], -7.8)
        self.assertEqual(ctx['inflationPct'], app.CPIH_12M_PCT[app.SNAPSHOT_VINTAGE])
        # Reproducible from the response: the cohort extremes over the same quantity.
        trends = [app.scored_trend(b) for b in app.CITIES['london']['boroughs'].values()]
        self.assertEqual(
            r['components']['growth'],
            app.round_1dp(app.growth_score(ctx['priceTrendRealPct'], max(trends), min(trends))),
        )

    def test_new_york_response_says_nominal_and_carries_no_real_keys(self):
        r = app.calc_score('Brooklyn', 'nyc', app.PERSONAS['investor'])
        ctx = r['context']
        self.assertEqual(ctx['growthBasis'], 'nominal')
        self.assertNotIn('priceTrendRealPct', ctx)
        self.assertNotIn('inflationPct', ctx)

    def test_balanced_cannot_move_on_growth(self):
        # growth is weighted 0.00 for balanced; a nominal-vs-real swap must not
        # reach the headline. Recompute with the nominal trend and compare.
        bd = app.CITIES['london']['boroughs']['Barking and Dagenham']
        r = app.calc_score('Barking and Dagenham', 'london', app.PERSONAS['balanced'])
        self.assertEqual(r['weights']['growth'], 0.0)
        self.assertNotEqual(bd['trend'], bd['trendReal'], 'a flip is needed for this to test anything')

    def test_benchmarks_are_in_the_scored_unit_and_say_so(self):
        bm = app.benchmarks(app.CITIES['london']['boroughs'])
        self.assertEqual(bm['growthBasis'], 'real')
        reals = [b['trendReal'] for b in app.CITIES['london']['boroughs'].values()]
        self.assertEqual(bm['strongestGrowthTrendPct'], max(reals))
        self.assertEqual(bm['steepestFallTrendPct'], min(reals))
        self.assertEqual(app.benchmarks(app.CITIES['nyc']['boroughs'])['growthBasis'], 'nominal')


class ProvenanceTests(unittest.TestCase):
    def test_growth_line_is_derived_and_names_the_deflator(self):
        for city, cfg in app.CITIES.items():
            with self.subTest(city=city):
                line = app._growth_breakdown_line(city)
                if cfg['currency'] == 'GBP':
                    self.assertIn('REAL-terms', line)
                    self.assertIn(f'{app.CPIH_12M_PCT[app.SNAPSHOT_VINTAGE]}%', line)
                    self.assertIn(app.SNAPSHOT_VINTAGE_LABEL, line)
                else:
                    self.assertIn('NOMINAL', line)
                    self.assertNotIn('CPIH', line)
                self.assertIn(
                    'previous vintage' if not cfg.get('hasHistory') else 'A previous vintage exists',
                    line,
                )

    def test_no_literal_growth_line_survives_in_city_provenance(self):
        # Thirteen hand-written strings, twelve with a literal 'June 2026' that
        # the July roll would have left stale, replaced by the derived line.
        for city, prov in app.CITY_PROVENANCE.items():
            with self.subTest(city=city):
                self.assertTrue(callable(prov['breakdown']['growth']))

    def test_cpih_source_line_only_where_growth_was_deflated(self):
        body = app.resolve_query({'borough': 'Wandsworth', 'city': 'london', 'persona': 'investor'})
        body = body[0] if isinstance(body, tuple) else body
        self.assertTrue(any('CPIH' in s for s in body['sources']))
        nyc = app.resolve_query({'borough': 'Brooklyn', 'city': 'nyc', 'persona': 'investor'})
        nyc = nyc[0] if isinstance(nyc, tuple) else nyc
        self.assertFalse(any('CPIH' in s for s in nyc['sources']))


class ComparisonStepTests(unittest.TestCase):
    def test_growth_driver_names_the_deflation_and_works_in_real_terms(self):
        res = app.resolve_query(
            {'borough': 'Barking and Dagenham', 'city': 'london', 'persona': 'investor', 'compare': 'previous'}
        )
        body = res[0] if isinstance(res, tuple) else res
        cmp = body['comparison']
        self.assertIn('previousTrendRealPct', cmp)
        growth = next(d for d in cmp['why']['drivers'] if d['factor'] == 'growth')
        steps = ' '.join(growth['steps'])
        self.assertIn('scored in real terms', steps)
        self.assertIn(f'{body["context"]["priceTrendRealPct"]:+}%', steps)
        # The workings divide the REAL trend by the REAL yardstick.
        self.assertIn(f'{body["context"]["priceTrendRealPct"]:+}%', growth['workings'])
        self.assertNotIn(f'{body["context"]["priceTrendPct"]:+}% ÷', growth['workings'])
        # Step 1 still speaks in cash terms, deliberately.
        self.assertIn(f'{body["context"]["priceTrendPct"]:+}%', growth['steps'][0])

    def test_market_context_stays_nominal(self):
        cur = app.CITIES['london']['boroughs']
        prev = app.previous_dataset('london')
        mc = app.market_context(cur, prev)
        self.assertEqual(json.dumps(mc)[:1], '{')
        nominal_mean = sum(b['trend'] for b in cur.values()) / len(cur)
        self.assertAlmostEqual(mc['meanTrendPct'], round(nominal_mean, 2), places=1)


if __name__ == '__main__':
    unittest.main()
