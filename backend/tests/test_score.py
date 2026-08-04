"""Unit tests for the score Lambda's pure functions.

Run from project root:
    python -m unittest backend.tests.test_score

These tests cover the deterministic pure functions only (no network, no
AWS, no postcodes.io). The handler integration is tested via live curl
calls in the deploy-time smoke tests.

Adding tests here is cheap insurance against regressions when the score
Lambda evolves (bulk endpoint, future per-postcode noise sampling, etc.).
"""

import json
import os
import re
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

# Allow `python -m unittest backend.tests.test_score` from project root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambdas', 'score'))

import app  # noqa: E402 # pylint: disable=wrong-import-position


class CrimeToScoreTests(unittest.TestCase):
    """The crime → score formula is calibrated against London medians.
    Score = max(0, min(10, 10 - (rate - 50) / 15))."""

    def test_low_crime_clipped_to_ten(self):
        self.assertEqual(app.crime_to_score(20), 10.0)
        self.assertEqual(app.crime_to_score(50), 10.0)

    def test_london_median_around_seven_five(self):
        # London-wide median ~88 → score ~7.47, displayed as 7.5
        self.assertAlmostEqual(app.crime_to_score(88), 7.4666, places=2)

    def test_high_crime_clipped_to_zero(self):
        self.assertEqual(app.crime_to_score(200), 0.0)
        self.assertEqual(app.crime_to_score(500), 0.0)

    def test_none_returns_neutral_five(self):
        self.assertEqual(app.crime_to_score(None), 5.0)

    def test_calibration_anchors(self):
        # Documented in METHODOLOGY.md §4.4: rate=50 → 10, rate=125 → 5
        self.assertEqual(app.crime_to_score(50), 10.0)
        self.assertEqual(app.crime_to_score(125), 5.0)


class ParseWeightsTests(unittest.TestCase):
    """Custom weights override must sum to 1.0 ±0.01 across exactly four keys."""

    def test_valid_string(self):
        result = app.parse_weights('quiet:0.5,afford:0.2,growth:0.1,live:0.2')
        self.assertEqual(result, {'quiet': 0.5, 'afford': 0.2, 'growth': 0.1, 'live': 0.2})

    def test_invalid_sum_returns_none(self):
        # Sum 1.5, outside tolerance, falls back
        self.assertIsNone(app.parse_weights('quiet:0.5,afford:0.5,growth:0.3,live:0.2'))

    def test_missing_key_returns_none(self):
        self.assertIsNone(app.parse_weights('quiet:0.5,afford:0.5'))

    def test_extra_key_returns_none(self):
        self.assertIsNone(app.parse_weights('quiet:0.3,afford:0.3,growth:0.2,live:0.1,extra:0.1'))

    def test_within_tolerance(self):
        # Sum 1.005, within 1% tolerance, accepted
        result = app.parse_weights('quiet:0.305,afford:0.25,growth:0.20,live:0.25')
        self.assertIsNotNone(result)

    def test_empty_returns_none(self):
        self.assertIsNone(app.parse_weights(''))
        self.assertIsNone(app.parse_weights(None))

    def test_malformed_returns_none(self):
        self.assertIsNone(app.parse_weights('not-a-weight-spec'))

    def test_negative_weight_returns_none(self):
        # Sums to 1.0 but individual weights outside [0, 1] are pathological
        # (A-0724-M11) — must be rejected, not scored.
        self.assertIsNone(app.parse_weights('quiet:-1,afford:2,growth:0,live:0'))

    def test_weight_above_one_returns_none(self):
        self.assertIsNone(app.parse_weights('quiet:1.5,afford:-0.2,growth:-0.2,live:-0.1'))

    def test_full_single_weight_accepted(self):
        # Boundary: a single component at exactly 1.0 is legitimate.
        result = app.parse_weights('quiet:1,afford:0,growth:0,live:0')
        self.assertEqual(result, {'quiet': 1.0, 'afford': 0.0, 'growth': 0.0, 'live': 0.0})


class TrendsFeatureTests(unittest.TestCase):
    """?compare=previous on /v1/score + GET /v1/changes (2026-07-24).

    All offline: borough-name queries skip postcodes.io entirely."""

    def test_compare_previous_london_borough(self):
        body, status = app.resolve_query({'borough': 'Wandsworth', 'compare': 'previous'})
        self.assertEqual(status, 200)
        comp = body['comparison']
        self.assertEqual(comp['previousVintage'], '2026-Q1')
        self.assertEqual(comp['currentVintage'], '2026-Q2')
        self.assertEqual(comp['previousAvgPriceGbp'], 680000)
        self.assertEqual(body['context']['avgPriceGbp'], 660000)
        self.assertEqual(comp['scoreChange'], round(body['score'] - comp['previousScore'], 1))
        # Under v3.3 the balanced persona does not weight growth, so
        # Wandsworth's dead growth signal no longer moves its score. The
        # movement must still be REPORTED as unweighted rather than vanish —
        # otherwise "the market moved and my score didn't" is unexplained.
        self.assertEqual(comp['scoreChange'], 0.0)
        self.assertEqual([u['factor'] for u in comp['why']['unweighted']], ['growth'])
        self.assertIn('did not change the score', comp['why']['unweighted'][0]['note'])

    def test_compare_absent_without_param(self):
        body, status = app.resolve_query({'borough': 'Wandsworth'})
        self.assertEqual(status, 200)
        self.assertNotIn('comparison', body)

    def test_compare_nyc_reports_zero_change(self):
        # NYC had no quarterly refresh between vintages: previous == current
        # and the comparison must honestly say nothing moved.
        body, status = app.resolve_query({'borough': 'Manhattan', 'city': 'nyc', 'compare': 'previous'})
        self.assertEqual(status, 200)
        self.assertEqual(body['comparison']['scoreChange'], 0.0)
        self.assertIn('previousAvgPriceUsd', body['comparison'])

    def test_include_filter_can_select_comparison(self):
        body, status = app.resolve_query(
            {'borough': 'Camden', 'compare': 'previous', 'include': 'score,comparison'}
        )
        self.assertEqual(status, 200)
        self.assertIn('comparison', body)
        self.assertIn('score', body)
        self.assertNotIn('components', body)

    def test_changes_endpoint_shape(self):
        resp = app.handle_changes({})
        self.assertEqual(resp['statusCode'], 200)
        body = json.loads(resp['body'])
        self.assertEqual(body['summary']['boroughs'], 33)
        self.assertEqual(body['currentVintage'], '2026-Q2')
        changes = body['changes']
        self.assertEqual(len(changes), 33)
        deltas = [abs(c['scoreChange']) for c in changes]
        self.assertEqual(deltas, sorted(deltas, reverse=True))
        for key in ('borough', 'score', 'previousScore', 'scoreChange', 'priceChangePct', 'trendPct'):
            self.assertIn(key, changes[0])
        self.assertEqual(
            body['summary']['risers'] + body['summary']['fallers'],
            len([c for c in changes if c['scoreChange'] != 0]),
        )

    # --- v3.3: growth is weighted only for `investor`, so the growth-explanation
    # coverage below runs against that persona. /v1/changes is balanced-only, so
    # these call build_why directly rather than going through the endpoint.
    def _investor_why(self, borough):
        inv = app.PERSONAS['investor']
        prev_set = app.previous_dataset('london')
        cur = app.calc_score(borough, 'london', inv)
        prev = app.calc_score(borough, 'london', inv, boroughs_override=prev_set)
        return app.build_why(
            cur, prev, 'london', inv, borough,
            app.benchmarks(app.CITIES['london']['boroughs']),
            app.benchmarks(prev_set),
            app.growth_ranks(app.CITIES['london']['boroughs']),
            app.growth_ranks(prev_set),
        )

    def test_changes_routed_from_handler(self):
        resp = app.handler({'httpMethod': 'GET', 'path': '/v1/changes'}, None)
        self.assertEqual(resp['statusCode'], 200)
        self.assertIn('changes', json.loads(resp['body']))

    def test_attribution_contributions_reconcile_to_score_change(self):
        """The whole value of the attribution is that the parts add up.

        Contributions come from the published 1dp components, so they reconcile
        to within rounding rather than exactly — but the gap must stay small and
        must equal the roundingResidual the API reports, or the explanation is
        quietly wrong.
        """
        body = json.loads(app.handle_changes({})['body'])
        for c in body['changes']:
            total = round(sum(f['contribution'] for f in c['attribution']), 2)
            self.assertAlmostEqual(total, c['attributionSum'], places=2, msg=c['borough'])
            self.assertAlmostEqual(
                c['roundingResidual'], round(c['scoreChange'] - total, 2), places=2, msg=c['borough']
            )
            # Rounding of four 1dp components can only drift so far; anything
            # larger means a factor is missing from the decomposition.
            self.assertLess(abs(c['roundingResidual']), 0.2, msg=f"{c['borough']} residual too large")

    def test_attribution_only_cites_factors_that_moved(self):
        # Only price and trend move between quarterly vintages, so noise and
        # liveability must never appear as drivers.
        body = json.loads(app.handle_changes({})['body'])
        cited = {f['factor'] for c in body['changes'] for f in c['attribution']}
        self.assertTrue(cited.issubset({'afford', 'growth'}), cited)
        for c in body['changes']:
            for f in c['attribution']:
                self.assertNotEqual(f['change'], 0, f"{c['borough']} cites an unmoved factor")
                self.assertAlmostEqual(
                    f['contribution'], round((f['after'] - f['before']) * f['weight'], 2), places=2
                )

    def test_attribution_sorted_by_influence(self):
        body = json.loads(app.handle_changes({})['body'])
        for c in body['changes']:
            sizes = [abs(f['contribution']) for f in c['attribution']]
            self.assertEqual(sizes, sorted(sizes, reverse=True), msg=c['borough'])

    def test_explanation_names_the_direction_and_the_driver(self):
        # Ealing's trend went +4.1% -> -0.3%, crossing into negative. Under the
        # investor view (the only one that weights growth since v3.3) the
        # explanation must say the score fell, name growth, and disclose the
        # scoring model.
        ealing = self._investor_why('Ealing')
        self.assertIn('fell', ealing['summary'])
        self.assertIn('Growth', ealing['summary'])
        # The flat string must still disclose the model, not only the structured
        # form — a caller reading `explanation` alone should not lose it.
        # v3.4: the model is the 5.0 flat-market anchor plus the tail benchmark,
        # where v3.2 disclosed a floor at 0.
        self.assertIn('flat market', ealing['summary'])
        self.assertIn('steepest fall', ealing['summary'])
        # Newham's price fell, so affordability improved even though the overall
        # score dropped. The explanation must not flatten every factor into the
        # same direction as the headline.
        newham = self._investor_why('Newham')
        afford = next(d for d in newham['drivers'] if d['factor'] == 'afford')
        self.assertGreater(afford['change'], 0, 'affordability improved')
        self.assertIn('9.3 → 9.5', afford['title'])
        self.assertTrue(any('price here fell' in st for st in afford['steps']), afford['steps'])

    def test_changes_publishes_weights_so_attribution_is_checkable(self):
        body = json.loads(app.handle_changes({})['body'])
        self.assertEqual(body['weights'], app.PERSONAS['balanced'])
        self.assertIn('attributionNote', body)

    def test_explanation_survives_json_round_trip(self):
        # The explanation is the first place a currency symbol enters a JSON
        # string field. json.dumps escapes it, so the wire format stays ASCII
        # and must decode back to the real character.
        raw = app.handle_changes({})['body']
        self.assertTrue(raw.isascii())
        decoded = json.loads(raw)
        with_symbol = [c for c in decoded['changes'] if '£' in c['explanation']]
        self.assertTrue(with_symbol, 'expected at least one explanation to quote a price')

    def test_market_context_explains_the_city_wide_move(self):
        """The most useful sentence about this vintage pair is not about one borough.

        Mean trend fell and the count of falling boroughs rose; without that
        framing, 25 of 33 dropping looks like a scoring fault.
        """
        body = json.loads(app.handle_changes({})['body'])
        m = body['marketContext']
        self.assertEqual(m['areas'], 33)
        self.assertLess(m['meanTrendPct'], m['previousMeanTrendPct'])
        self.assertEqual(m['previousFallingAreas'], 0)
        self.assertEqual(m['fallingAreas'], 14)
        self.assertEqual(m['benchmarks']['strongestGrowthArea'], 'Waltham Forest')
        self.assertEqual(m['previousBenchmarks']['strongestGrowthArea'], 'Barking and Dagenham')
        self.assertIn('market fell', m['summary'])

    def test_why_shows_its_workings_for_relative_factors(self):
        # Growth and affordability are scored relative to other boroughs, so the
        # sum must be shown or a large swing looks arbitrary.
        newham = self._investor_why('Newham')
        growth = next(d for d in newham['drivers'] if d['factor'] == 'growth')
        # Names the benchmark and reproduces the arithmetic. v3.4 anchors a flat
        # market at 5.0 and scales the rising tail across 5-10, so Newham's
        # +1.2% against Waltham Forest's +5.0% gives 5.0 + (1.2/5.0)*5 = 6.2
        # (it was 2.4 under the v3.2 single-anchor formula).
        self.assertIn('Waltham Forest', growth['workings'])
        self.assertIn('= 6.2', growth['workings'])
        afford = next(d for d in newham['drivers'] if d['factor'] == 'afford')
        self.assertIn('= 9.5', afford['workings'])
        # The cheapest/dearest endpoints are named in the prose steps, so the
        # reader knows what the scale runs between.
        steps = ' '.join(afford['steps'])
        self.assertIn('cheapest', steps)
        self.assertIn('dearest', steps)

    def test_why_states_units_and_meaning(self):
        """"Growth fell from 10.0 to 1.8" was read as a percentage.

        Every driver must say it is a score out of 10 and say what the factor
        actually measures.
        """
        body = json.loads(app.handle_changes({})['body'])
        for c in body['changes']:
            for d in c['why']['drivers']:
                self.assertIn('out of 10', d['title'], c['borough'])
                self.assertTrue(d['meaning'], f"{c['borough']}/{d['factor']} has no plain-English meaning")
                self.assertTrue(d['steps'], f"{c['borough']}/{d['factor']} has no steps")
                # The last step always states the effect on the headline score.
                self.assertIn('of the overall score', d['steps'][-1])

    def test_why_avoids_internal_jargon(self):
        # "vintage" is our word for a data snapshot; a reader has never seen it.
        body = json.loads(app.handle_changes({})['body'])
        for c in body['changes']:
            blob = json.dumps(c['why']).lower()
            self.assertNotIn('vintage', blob, c['borough'])

    def test_why_uses_rank_to_explain_the_drop(self):
        """Rank is the intuitive anchor the earlier wording talked around."""
        barking = self._investor_why('Barking and Dagenham')
        growth = next(d for d in barking['drivers'] if d['factor'] == 'growth')
        self.assertEqual(growth['previousRank'], 1)
        self.assertEqual(growth['rank'], 17)
        self.assertEqual(growth['rankOf'], 33)
        steps = ' '.join(growth['steps'])
        self.assertIn('1st of 33 to 17th of 33', steps)

    def test_why_explains_amplification_when_area_was_the_benchmark(self):
        """The main reason a fall looks extreme: it WAS the yardstick.

        Barking scored 10/10 in Q1 by being the fastest grower — a ceiling, not
        a margin — so it could only move down.
        """
        barking = self._investor_why('Barking and Dagenham')
        growth = next(d for d in barking['drivers'] if d['factor'] == 'growth')
        steps = ' '.join(growth['steps'])
        # v3.4 replaced the pure "league table" model with a flat-market anchor;
        # the amplification explanation it wraps must survive that change.
        self.assertIn('flat market', steps)
        self.assertIn('took the full 10', steps)
        self.assertIn('only direction available was down', steps)
        self.assertIn('Barking and Dagenham', steps)
        # And it must say prices are still RISING — the score fell for a
        # relative reason, which is the whole confusion being addressed.
        self.assertTrue(
            any('still rising' in s.lower() for s in growth['steps']),
            'must say prices are still rising, just more slowly',
        )
        self.assertTrue(any('did not get worse in absolute terms' in cv for cv in barking['caveats']))

    def test_why_names_the_borough_not_a_placeholder(self):
        # A previous version patched only the flattened summary, leaving the
        # structured drivers the page renders saying "This area".
        body = json.loads(app.handle_changes({})['body'])
        for c in body['changes']:
            self.assertNotIn('This area', json.dumps(c['why']), c['borough'])

    def test_growth_separates_mild_falls_from_severe_ones(self):
        """v3.4 regression guard, replacing test_why_flags_the_growth_floor_as_a_caveat.

        That test asserted the *defect*: under v3.2 every falling borough scored
        0, so the API had to publish a caveat admitting the factor "cannot tell a
        slight dip apart from a steep fall". 14 of 33 London boroughs shared one
        value and the component carried no signal for 42% of the map.

        The dual anchor scales the falling tail across 5-0 against the steepest
        faller, so the depth of a fall must now survive into the score. If this
        ever collapses back onto a shared floor, that is the v3.2 bug returning.
        """
        inv = app.PERSONAS['investor']

        def growth_of(borough):
            return app.calc_score(borough, 'london', inv)['components']['growth']

        # -0.3%, -9.5% and -28.2% respectively: strictly ordered by depth of fall.
        ealing, kc, col = growth_of('Ealing'), growth_of('Kensington and Chelsea'), growth_of('City of London')
        self.assertLess(col, kc)
        self.assertLess(kc, ealing)
        # All are falling, so all sit below the 5.0 flat-market anchor.
        self.assertLess(ealing, 5.0)
        # Only the steepest faller in the cohort may sit on the floor.
        self.assertEqual(col, 0.0)

        # The workings must name the benchmark the tail is scaled against rather
        # than assert a floor that no longer exists.
        kc_why = self._investor_why('Kensington and Chelsea')
        growth = next(d for d in kc_why['drivers'] if d['factor'] == 'growth')
        self.assertIn('steepest fall', growth['workings'])
        self.assertNotIn('floored at 0', growth['workings'])

        # Retained from the test this replaces: K&C's RANK improved (33rd -> 30th)
        # while its own prices got worse, because others fell further. Left
        # unexplained that looks like a bug. Ranks come from the raw trend order,
        # so v3.4 does not move them.
        self.assertEqual((growth['previousRank'], growth['rank']), (33, 30))
        self.assertTrue(any('moved UP the growth table' in cv for cv in kc_why['caveats']))

        # And no borough may still publish the retired limitation as a caveat.
        body = json.loads(app.handle_changes({})['body'])
        for c in body['changes']:
            for caveat in c['why']['caveats']:
                self.assertNotIn('cannot tell a slight dip', caveat, c['borough'])

    def test_why_summary_matches_flat_explanation(self):
        body = json.loads(app.handle_changes({})['body'])
        for c in body['changes']:
            self.assertEqual(c['explanation'], c['why']['summary'], c['borough'])

    def test_compare_previous_includes_attribution(self):
        body, status = app.resolve_query({'borough': 'Ealing', 'compare': 'previous'})
        self.assertEqual(status, 200)
        comp = body['comparison']
        self.assertIn('attribution', comp)
        self.assertIn('explanation', comp)
        total = round(sum(f['contribution'] for f in comp['attribution']), 2)
        self.assertLess(abs(comp['scoreChange'] - total), 0.2)


class NormaliseBoroughTests(unittest.TestCase):
    def test_canonical_london(self):
        self.assertEqual(app.normalise_borough('Wandsworth', 'london'), 'Wandsworth')

    def test_alias_barking(self):
        self.assertEqual(app.normalise_borough('Barking', 'london'), 'Barking and Dagenham')

    def test_alias_city_of_london(self):
        self.assertEqual(app.normalise_borough('City of London Corporation', 'london'), 'City of London')

    def test_unknown_returns_none(self):
        self.assertIsNone(app.normalise_borough('Atlantis', 'london'))

    def test_canonical_nyc(self):
        self.assertEqual(app.normalise_borough('Manhattan', 'nyc'), 'Manhattan')

    def test_nyc_unknown_returns_none(self):
        self.assertIsNone(app.normalise_borough('Hackney', 'nyc'))


class NycZipDetectionTests(unittest.TestCase):
    """The US_ZIP_PATTERN regex must accept 5-digit and ZIP+4 formats only."""

    def test_five_digit_matches(self):
        self.assertIsNotNone(app.US_ZIP_PATTERN.match('10001'))
        self.assertIsNotNone(app.US_ZIP_PATTERN.match('11201'))

    def test_zip_plus_four_matches(self):
        self.assertIsNotNone(app.US_ZIP_PATTERN.match('10001-1234'))

    def test_uk_postcode_does_not_match(self):
        self.assertIsNone(app.US_ZIP_PATTERN.match('SW11 1AA'))
        self.assertIsNone(app.US_ZIP_PATTERN.match('SW111AA'))
        self.assertIsNone(app.US_ZIP_PATTERN.match('N1 7SX'))

    def test_nyc_zip_lookup_population(self):
        # Sanity check: ~180 ZIPs across 5 boroughs (residential + general use,
        # excluding PO Box / single-building ZIPs)
        self.assertGreaterEqual(len(app.NYC_ZIP_TO_BOROUGH), 180)
        self.assertEqual(set(app.NYC_ZIP_TO_BOROUGH.values()), set(app.NYC_BOROUGHS.keys()))

    def test_known_zip_to_borough(self):
        self.assertEqual(app.NYC_ZIP_TO_BOROUGH.get('10001'), 'Manhattan')
        self.assertEqual(app.NYC_ZIP_TO_BOROUGH.get('11201'), 'Brooklyn')
        self.assertEqual(app.NYC_ZIP_TO_BOROUGH.get('11375'), 'Queens')
        self.assertEqual(app.NYC_ZIP_TO_BOROUGH.get('10451'), 'Bronx')
        self.assertEqual(app.NYC_ZIP_TO_BOROUGH.get('10301'), 'Staten Island')

    def test_non_nyc_zip_not_in_lookup(self):
        self.assertIsNone(app.NYC_ZIP_TO_BOROUGH.get('90210')) # Beverly Hills
        self.assertIsNone(app.NYC_ZIP_TO_BOROUGH.get('60601')) # Chicago


class CalcScoreTests(unittest.TestCase):
    """End-to-end score computation for a known borough.

    Anchored to the worked example in METHODOLOGY.md §6 (SW11 1AA / Wandsworth):
    quiet=5.0, afford=6.6, growth=3.6, live=8.7 → balanced score 6.1.
    """

    def test_wandsworth_balanced(self):
        # Pinned to the 2026-Q2 (May 2026 UK HPI) snapshot + methodology v3.4.
        # v3.3 dropped growth from the balanced persona, so the component is
        # computed and published but carries no weight here — which is why the
        # headline rose from the v3.2 value of 5.3.
        #
        # The growth COMPONENT moved 0.0 -> 4.3 in v3.4 (dual-anchor: Wandsworth
        # is falling, but only mildly, so it now sits just below the 5.0
        # flat-market anchor instead of collapsing onto the floor). v3.3's zero
        # weighting means a growth-formula change cannot move the balanced score,
        # which is what this fixture exists to guard.
        #
        # 6.7 -> 6.4 and live 8.7 -> 7.9 when schools moved from the editorial
        # Ofsted band to DfE Progress 8. Wandsworth was banded 'excellent'
        # (SCHOOL_SCORE 9) but measures P8 +0.33 against a London median of
        # +0.30 -- a shade above average, not exceptional. The drop is the
        # correction the metric change exists to make, not a regression.
        weights = app.PERSONAS['balanced']
        result = app.calc_score('Wandsworth', 'london', weights)
        self.assertEqual(result['score'], 6.4)
        self.assertEqual(result['components']['quiet'], 5.0)
        self.assertEqual(result['components']['afford'], 6.7)
        self.assertEqual(result['components']['growth'], 4.3)
        # live 7.9 -> 8.0 on 2026-08-03, when the crime rates were re-verified
        # against ONS Table C4 in full rather than by spot check. Wandsworth held
        # 82 per 1,000 against a published 76.4, so crime_to_score moves 7.87 ->
        # 8.24 and, at 30% of the liveability composite, carries `live` up by
        # 0.11. 29 of 33 boroughs moved; Wandsworth's was among the smaller
        # corrections. Not a regression — the previous figure was never in the
        # source it cited.
        self.assertEqual(result['components']['live'], 8.0)
        self.assertEqual(result['context']['avgPriceGbp'], 660000)
        self.assertEqual(result['context']['noiseImpactBand'], 'moderate')

    def test_growth_clamped_to_scale(self):
        """Methodology v3.2: no component or total score may leave the 0-10
        scale, however negative a borough's trend is (the 2026-Q2 refresh
        introduced falling boroughs; the pre-clamp formula went sub-zero)."""
        for persona in app.PERSONAS.values():
            for borough in app.LONDON_BOROUGHS:
                result = app.calc_score(borough, 'london', persona)
                self.assertGreaterEqual(result['components']['growth'], 0.0, borough)
                self.assertLessEqual(result['components']['growth'], 10.0, borough)
                self.assertGreaterEqual(result['score'], 0.0, borough)
                self.assertLessEqual(result['score'], 10.0, borough)

    def test_hounslow_severe_noise(self):
        # Hounslow is 'severe' Lden band → quiet should be 0.0 regardless of persona
        weights = app.PERSONAS['quietlife']
        result = app.calc_score('Hounslow', 'london', weights)
        self.assertEqual(result['components']['quiet'], 0.0)

    def test_nyc_uses_usd_currency(self):
        weights = app.PERSONAS['balanced']
        result = app.calc_score('Manhattan', 'nyc', weights)
        self.assertIn('avgPriceUsd', result['context'])
        self.assertNotIn('avgPriceGbp', result['context'])


class PersonaCoverageTests(unittest.TestCase):
    """Every documented persona must produce a valid score and have weights
    summing to 1.0 within the 1% tolerance enforced at request time."""

    def test_all_personas_sum_to_one(self):
        for name, weights in app.PERSONAS.items():
            total = sum(weights.values())
            self.assertAlmostEqual(total, 1.0, places=2,
                                   msg=f'{name!r} sums to {total}')

    def test_all_personas_have_four_keys(self):
        expected = {'quiet', 'afford', 'growth', 'live'}
        for name, weights in app.PERSONAS.items():
            self.assertEqual(set(weights.keys()), expected,
                             msg=f'{name!r} keys: {set(weights.keys())}')

    def test_renter_growth_is_zero(self):
        # Renters do not realise capital growth.
        self.assertEqual(app.PERSONAS['renter']['growth'], 0.0)

    def test_each_persona_produces_valid_score(self):
        for name in app.PERSONAS:
            result = app.calc_score('Wandsworth', 'london', app.PERSONAS[name])
            self.assertGreaterEqual(result['score'], 0.0, name)
            self.assertLessEqual(result['score'], 10.0, name)

    def test_new_personas_present(self):
        for name in ('renter', 'commuter', 'laterlife'):
            self.assertIn(name, app.PERSONAS)

    def test_legacy_persona_keys_removed(self):
        # Wave 12.10: 'downsizer' renamed to 'laterlife'. The old key must
        # not silently come back; if it does, two persona keys map to the
        # same weights and clients get unpredictable behaviour.
        self.assertNotIn('downsizer', app.PERSONAS)


# ---------------------------------------------------------------------------
# ONS NSPL local postcode-resolution fixtures.
#
# Every one of these is a REAL row from the 2026-02 NSPL edition
# (data/nspl.csv), mapped through scripts/load_nspl.py's item shape and kept
# in DynamoDB low-level JSON so the stub returns byte-identical structures to
# a live GetItem response. Optional attributes are omitted exactly as the
# loader omits them, because absence is meaningful: no `b` means "not one of
# the 33 London boroughs", no `dt` means "live", no `q` means "building-level".
# ---------------------------------------------------------------------------
_NSPL_SW11_1AA = {
    'postcode': {'S': 'SW111AA'},
    'lat': {'N': '51.464444'},
    'lon': {'N': '-0.164298'},
    'lad': {'S': 'E09000032'},
    'b': {'S': 'Wandsworth'},
    'rgn': {'S': 'London'},
}

# Boundary fixture: E1 6AN is City of London, NOT Tower Hamlets.
_NSPL_E1_6AN = {
    'postcode': {'S': 'E16AN'},
    'lat': {'N': '51.518887'},
    'lon': {'N': '-0.078479'},
    'lad': {'S': 'E09000001'},
    'b': {'S': 'City of London'},
    'rgn': {'S': 'London'},
}

# The sentinel trap: a legitimate negative-near-zero longitude. Postcodes sit
# on both sides of the Greenwich meridian, so longitude 0 is real data.
_NSPL_SE10_9NF = {
    'postcode': {'S': 'SE109NF'},
    'lat': {'N': '51.480285'},
    'lon': {'N': '-0.006020'},
    'lad': {'S': 'E09000011'},
    'b': {'S': 'Greenwich'},
    'rgn': {'S': 'London'},
}

# Terminated (doterm 198412) AND coarse-positioned (gridind 8, pre-Gridlink).
_NSPL_BR1_1HB = {
    'postcode': {'S': 'BR11HB'},
    'lat': {'N': '51.404506'},
    'lon': {'N': '0.014262'},
    'lad': {'S': 'E09000006'},
    'b': {'S': 'Bromley'},
    'rgn': {'S': 'London'},
    'dt': {'S': '198412'},
    'q': {'N': '8'},
}

# Non-London England. No `b` attribute, which is what keeps the existing
# "Borough not currently supported" 404 firing unchanged.
_NSPL_M1_1AE = {
    'postcode': {'S': 'M11AE'},
    'lat': {'N': '53.483487'},
    'lon': {'N': '-2.231182'},
    'lad': {'S': 'E08000003'},
    'rgn': {'S': 'North West'},
}


class _LocalTierFixture:
    """setUp + DynamoDB stubbing shared by every test that exercises the
    local NSPL tier. A plain mixin, not a TestCase, so it is never collected
    as a test class in its own right."""

    def setUp(self):
        # 1. The postcode LRU is a module-level closure pair now serving BOTH
        #    tiers, so a positive result leaks into later tests: they pass in
        #    isolation and fail in a different order. Rebuild it per test.
        self._saved_cache = (app._postcode_cache_get, app._postcode_cache_put)
        app._postcode_cache_get, app._postcode_cache_put = app._make_lru(512)
        # 2. POSTCODE_TABLE is read ONCE at module import, so setting the
        #    environment variable cannot work. Set the attribute instead.
        #    Tests that need it unset override this to '' themselves.
        self._saved_table = app.POSTCODE_TABLE
        app.POSTCODE_TABLE = 'london-flight-map-postcodes'
        self.ddb_factory = None
        # 3. Restore both however the test exits.
        self.addCleanup(self._restore_module_state)

    def _restore_module_state(self):
        app._postcode_cache_get, app._postcode_cache_put = self._saved_cache
        app.POSTCODE_TABLE = self._saved_table

    def _stub_ddb(self, item):
        """Patch the shared DynamoDB client factory with a stub whose
        get_item returns *item*, or a table miss when *item* is None.

        Returns the client mock so tests can assert on the calls it
        received; the factory mock itself is on self.ddb_factory."""
        ddb = MagicMock()
        ddb.get_item.return_value = {'Item': item} if item is not None else {}
        patcher = patch.object(app, '_get_ddb_client', return_value=ddb)
        self.ddb_factory = patcher.start()
        self.addCleanup(patcher.stop)
        return ddb

    def _stub_ddb_rows(self, rows):
        """As _stub_ddb, but backed by a {clean postcode: item} table so a
        batch of mixed queries resolves each key to its own row. Anything
        not in *rows* is a table miss."""
        ddb = MagicMock()

        def _get_item(**kwargs):
            key = kwargs['Key']['postcode']['S']
            item = rows.get(key)
            return {'Item': item} if item is not None else {}

        ddb.get_item.side_effect = _get_item
        patcher = patch.object(app, '_get_ddb_client', return_value=ddb)
        self.ddb_factory = patcher.start()
        self.addCleanup(patcher.stop)
        return ddb

    @staticmethod
    def _no_network():
        """Patch _fetch_postcode to fail loudly. Every test in these classes
        is meant to be served entirely by the local tier; a postcodes.io call
        is a defect, not a slow test."""
        def _boom(clean):
            raise AssertionError(f'postcodes.io was called for {clean!r}')

        return patch.object(app, '_fetch_postcode', _boom)


class PostcodeTableTests(_LocalTierFixture, unittest.TestCase):
    """The local NSPL tier must be a drop-in for postcodes.io: same dict
    shape, None for anything it cannot answer confidently, and a silent
    no-op when POSTCODE_TABLE is unset so the API behaves identically
    before and after the data lands."""

    def test_table_unset_returns_none_without_building_a_client(self):
        # The forward-compatibility guarantee. With no table wired — the
        # default in every test environment, and true until the deploy
        # happens — the new code must not even reach for a boto3 client.
        app.POSTCODE_TABLE = ''
        self._stub_ddb(_NSPL_SW11_1AA)
        self.assertIsNone(app._lookup_postcode_local('SW111AA'))
        self.ddb_factory.assert_not_called()

    def test_local_hit_returns_postcodes_io_shape(self):
        self._stub_ddb(_NSPL_SW11_1AA)
        result = app._lookup_postcode_local('SW111AA')
        self.assertEqual(result['postcode'], 'SW11 1AA')
        self.assertEqual(result['admin_district'], 'Wandsworth')
        self.assertEqual(result['latitude'], 51.464444)
        self.assertEqual(result['longitude'], -0.164298)
        self.assertEqual(result['region'], 'London')
        # Numbers, not the DynamoDB strings they arrived as: resolve_query
        # feeds these straight into the Haversine flight-path layer.
        self.assertIsInstance(result['latitude'], float)
        self.assertIsInstance(result['longitude'], float)

    def test_local_hit_does_not_call_postcodes_io(self):
        # The whole point of the build. Lowercase input with a space also
        # exercises the shared key normalisation on the way through.
        ddb = self._stub_ddb(_NSPL_SW11_1AA)

        def _boom(clean):
            raise AssertionError(f'postcodes.io was called for {clean!r}')

        with patch.object(app, '_fetch_postcode', _boom):
            result = app.lookup_postcode('sw11 1aa')
        self.assertEqual(result['postcode'], 'SW11 1AA')
        self.assertEqual(result['admin_district'], 'Wandsworth')
        # Exactly TableName + Key and nothing else. A ProjectionExpression
        # here would raise ValidationException on a reserved word, which is
        # a ClientError, which the resolver swallows to None — the table
        # would appear to work while silently never being used.
        ddb.get_item.assert_called_once_with(
            TableName='london-flight-map-postcodes',
            Key={'postcode': {'S': 'SW111AA'}},
        )

    def test_ddb_key_format_matches_the_loader(self):
        # `.strip().replace(' ', '').upper()` — byte-identical to the key
        # scripts/load_nspl.py writes and to london-flight-map-noise-raster.
        # Diverging silently misses every single row.
        ddb = self._stub_ddb(_NSPL_SW11_1AA)
        for raw in ('SW11 1AA', 'sw111aa', '  sw11 1aa  ', 'Sw11 1Aa'):
            # Fresh LRU per spelling, or the second lookup is a cache hit
            # and never reaches DynamoDB at all.
            app._postcode_cache_get, app._postcode_cache_put = app._make_lru(512)
            ddb.get_item.reset_mock()
            app.lookup_postcode(raw)
            self.assertEqual(
                ddb.get_item.call_args.kwargs['Key'],
                {'postcode': {'S': 'SW111AA'}},
                msg=f'input {raw!r} produced the wrong DDB key',
            )

    def test_table_miss_falls_back_to_postcodes_io(self):
        # A miss must NEVER become a 404 — postcodes.io is demoted, not
        # removed, and it still answers postcodes newer than this vintage.
        self._stub_ddb(None)
        sentinel = {'postcode': 'SW11 1AA', 'admin_district': 'Wandsworth'}
        with patch.object(app, '_fetch_postcode', return_value=sentinel) as fetch:
            result = app.lookup_postcode('SW11 1AA')
        self.assertIs(result, sentinel)
        fetch.assert_called_once_with('SW111AA')

    def test_ddb_client_error_falls_back(self):
        from botocore.exceptions import ClientError
        ddb = self._stub_ddb(None)
        ddb.get_item.side_effect = ClientError(
            {'Error': {'Code': 'ProvisionedThroughputExceededException', 'Message': 'x'}},
            'GetItem',
        )
        sentinel = {'postcode': 'SW11 1AA', 'admin_district': 'Wandsworth'}
        # Nothing may escape: _lookup_postcode_local runs inside a 10-worker
        # pool over batches of up to 100, and one exception 500s the lot.
        with patch.object(app, '_fetch_postcode', return_value=sentinel):
            result = app.lookup_postcode('SW11 1AA')
        self.assertIs(result, sentinel)

    def test_unusable_centroid_defers_to_fallback(self):
        # Never a partial dict: a borough without a centroid would resolve
        # the query but silently downgrade the quiet score from the
        # per-postcode Haversine layer to the borough-aggregate band.
        broken = {k: v for k, v in _NSPL_SW11_1AA.items() if k != 'lat'}
        self._stub_ddb(broken)
        self.assertIsNone(app._lookup_postcode_local('SW111AA'))

    def test_negative_near_zero_longitude_survives(self):
        # SE10 9NF is -0.006020. Any truthiness or `== 0` test anywhere in
        # the chain would corrupt Greenwich.
        self._stub_ddb(_NSPL_SE10_9NF)
        result = app._lookup_postcode_local('SE109NF')
        self.assertEqual(result['longitude'], -0.00602)
        self.assertEqual(result['admin_district'], 'Greenwich')

    def test_terminated_row_hidden_by_default(self):
        # Tri-state since audit L4. The local tier answers POSTCODE_TERMINATED
        # rather than None, because "terminated" is a DEFINITIVE answer:
        # postcodes.io 404s these too, so the fallback round trip is a
        # guaranteed miss. lookup_postcode converts the sentinel back to None,
        # so the caller still gets exactly the 404 it got before — one HTTP
        # call, one 5s timeout risk and one worker-second cheaper.
        self._stub_ddb(_NSPL_BR1_1HB)
        self.assertIs(app._lookup_postcode_local('BR11HB'), app.POSTCODE_TERMINATED)
        with patch.object(app, '_fetch_postcode') as fetch:
            # `assertIsNone`, not merely falsey: the sentinel is truthy, so a
            # leak would sail past an `assertFalse` and reach resolve_query.
            self.assertIsNone(app.lookup_postcode('BR1 1HB'))
        fetch.assert_not_called()

    def test_terminated_short_circuit_still_404s_after_one_getitem(self):
        # The saving must be invisible from outside: same status, same body,
        # and the one GetItem that told us the answer is the only round trip.
        ddb = self._stub_ddb(_NSPL_BR1_1HB)
        with self._no_network():
            body, status = app.resolve_query({'postcode': 'BR1 1HB'})
        self.assertEqual(status, 404)
        self.assertEqual(body['error'], 'Postcode not recognised by postcodes.io: BR1 1HB')
        self.assertEqual(ddb.get_item.call_count, 1)

    def test_terminated_row_served_when_opted_in(self):
        self._stub_ddb(_NSPL_BR1_1HB)
        result = app._lookup_postcode_local('BR11HB', include_terminated=True)
        self.assertIs(result['_terminated'], True)
        self.assertEqual(result['_dotermMonth'], '1984-12')
        self.assertEqual(result['_gridInd'], 8)
        self.assertEqual(result['admin_district'], 'Bromley')

    def test_terminated_result_is_not_cached(self):
        # The cache key is the postcode alone, so caching an opt-in result
        # would leak it to a later caller that did not opt in. The follow-up
        # call must re-run the local tier — which answers POSTCODE_TERMINATED
        # a second time — rather than serving the cached opt-in dict.
        self._stub_ddb(_NSPL_BR1_1HB)
        opted_in = app.lookup_postcode('BR1 1HB', include_terminated=True)
        self.assertIs(opted_in['_terminated'], True)
        with patch.object(app, '_fetch_postcode') as fetch:
            self.assertIsNone(app.lookup_postcode('BR1 1HB'))
        # And the sentinel path takes the fallback off the table entirely
        # (audit L4), so the no-leak guarantee no longer depends on
        # postcodes.io happening to 404 the same postcode.
        fetch.assert_not_called()

    def test_negative_result_is_not_cached(self):
        self._stub_ddb(None)
        with patch.object(app, '_fetch_postcode', return_value=None):
            self.assertIsNone(app.lookup_postcode('SW11 1AA'))
        # A cached None would re-serve the miss for the whole ~15-minute
        # warm-container lifetime, turning a transient DDB throttle or a
        # postcodes.io blip into a sticky 404.
        sentinel = {'postcode': 'SW11 1AA', 'admin_district': 'Wandsworth'}
        with patch.object(app, '_fetch_postcode', return_value=sentinel):
            self.assertIs(app.lookup_postcode('SW11 1AA'), sentinel)

    def test_non_london_row_returns_dict_with_null_admin_district(self):
        # The subtle trap. Returning None here would treat "no borough" as a
        # local miss and send every non-London UK postcode back to
        # postcodes.io — restoring the fair-use problem for most of a
        # national back-book.
        self._stub_ddb(_NSPL_M1_1AE)
        with patch.object(app, '_fetch_postcode') as fetch:
            result = app.lookup_postcode('M1 1AE')
        self.assertIsNotNone(result)
        self.assertIsNone(result['admin_district'])
        self.assertEqual(result['postcode'], 'M1 1AE')
        self.assertEqual(result['region'], 'North West')
        self.assertEqual(result['_ladCode'], 'E08000003')
        fetch.assert_not_called()

    def test_boundary_borough_name_indexes_the_dataset(self):
        # E1 6AN is City of London, NOT Tower Hamlets. The `b` string the
        # loader writes must be the exact canonical LONDON_BOROUGHS key:
        # normalise_borough is a case-sensitive dict membership test and
        # calc_score then indexes boroughs[name] directly, so a stray '&' or
        # a 'City of London Corporation' would 404 the entire borough — and
        # a local hit never falls back, so postcodes.io cannot rescue it.
        self._stub_ddb(_NSPL_E1_6AN)
        body, status = app.resolve_query({'postcode': 'E1 6AN'})
        self.assertEqual(status, 200)
        self.assertEqual(body['location']['borough'], 'City of London')

    def test_resolve_query_404_unchanged_for_non_london(self):
        # postcodes.io returns admin_district='Manchester' -> normalise ->
        # None; the local table returns admin_district=None -> normalise ->
        # None. Same 404, same attemptedBorough, byte-identical body.
        self._stub_ddb(_NSPL_M1_1AE)
        body, status = app.resolve_query({'postcode': 'M1 1AE'})
        self.assertEqual(status, 404)
        self.assertEqual(body['error'], 'Borough not currently supported in london.')
        self.assertIsNone(body['attemptedBorough'])

    def test_resolve_query_surfaces_terminated_status(self):
        self._stub_ddb(_NSPL_BR1_1HB)
        body, status = app.resolve_query(
            {'postcode': 'BR1 1HB', 'includeTerminated': 'true'}
        )
        self.assertEqual(status, 200)
        location = body['location']
        self.assertEqual(location['borough'], 'Bromley')
        self.assertEqual(location['postcodeStatus'], 'terminated')
        self.assertEqual(location['postcodeTerminatedDate'], '1984-12')
        # gridind 8 is pre-Gridlink, which can sit far enough out to cross a
        # noise contour band. Saying so is the honest thing to do.
        self.assertEqual(location['positionQuality'], 'approximate')

    def test_live_response_location_keys_unchanged(self):
        # Regression guard on the published OpenAPI Location schema: every
        # request that returns 200 today must keep exactly its six keys.
        self._stub_ddb(_NSPL_SW11_1AA)
        body, status = app.resolve_query({'postcode': 'SW11 1AA'})
        self.assertEqual(status, 200)
        self.assertEqual(
            set(body['location']),
            {'city', 'postcode', 'borough', 'longitude', 'latitude', 'region'},
        )

    def test_source_line_switches_on_actual_local_service(self):
        self.assertEqual(
            app._postcode_source_line(False),
            'Postcode resolution: postcodes.io (Open Government Licence v3.0)',
        )
        served = app._postcode_source_line(True)
        self.assertIn('ONS National Statistics Postcode Lookup', served)
        self.assertIn('fallback', served)

    def test_sources_credits_ons_only_once_local_has_served(self):
        # The honesty guarantee: `sam deploy` sets POSTCODE_TABLE and creates
        # the table in one change set, so there is a ~40-minute window while
        # the loader runs where the table exists but every lookup still goes
        # to postcodes.io. Crediting ONS during that window would be a false
        # provenance claim in the array B2B customers audit.
        original = app._LOCAL_POSTCODE_SERVED
        try:
            app._LOCAL_POSTCODE_SERVED = False
            self.assertIn('postcodes.io', app.build_sources()[2])
            self.assertNotIn('ONS National Statistics', app.build_sources()[2])

            app._LOCAL_POSTCODE_SERVED = True
            self.assertIn('ONS National Statistics', app.build_sources()[2])
        finally:
            app._LOCAL_POSTCODE_SERVED = original

    def test_every_city_has_its_own_provenance(self):
        """Adding a city without provenance must fail here, not in production.

        The defect this guards: `sources` and `sourceBreakdown` were single
        module constants emitted on every response, so New York shipped
        crediting MHCLG, HM Land Registry, ONS, the Home Office, DfE, TfL, NHS
        and DEFRA under Open Government Licence v3.0 — none of which has any
        New York remit, and OGL covers UK Crown copyright only. A new city
        would silently inherit the same false claim.
        """
        for city in app.CITIES:
            self.assertIn(city, app.CITY_PROVENANCE,
                          f'{city} is scoreable but has no provenance entry')
            self.assertTrue(app.build_sources(city), city)
            self.assertEqual(
                set(app.build_source_breakdown(city)),
                {'quiet', 'afford', 'growth', 'live'},
                f'{city} breakdown must cover every scored component',
            )

        # Distinct cities must not share provenance text.
        blobs = {c: json.dumps(app.build_source_breakdown(c)) for c in app.CITIES}
        self.assertEqual(len(set(blobs.values())), len(blobs),
                         'two cities publish identical provenance')

    def test_non_uk_city_never_credits_uk_bodies(self):
        body, status = app.resolve_query({'city': 'nyc', 'borough': 'Brooklyn'})
        self.assertEqual(status, 200)
        lines = body['sources'] + list(body['sourceBreakdown'].values())
        for term in ('MHCLG', 'HM Land Registry', 'Home Office',
                     'Department for Education', 'DfE', 'TfL', 'NHS', 'DEFRA'):
            for line in lines:
                if term in line:
                    # Permitted only as an explicit disclaimer.
                    self.assertIn('NOT', line,
                                  f'NYC response credits {term}: {line}')
        licence = [ln for ln in body['sources'] if 'Open Government Licence' in ln]
        self.assertTrue(licence, 'NYC must address the OGL question, not omit it')
        for ln in licence:
            self.assertIn('does NOT apply', ln)

    def test_fully_sourced_city_carries_no_partial_disclosure(self):
        # The Manchester half of this test lives on the Core Cities branch,
        # where a partially-sourced city actually exists. What master can and
        # must assert is the other side of the same guarantee: a city with all
        # four liveability inputs reports 'measured' and carries no PARTIAL
        # caveat, so the disclosure means something when it does appear.
        lon, status = app.resolve_query({'city': 'london', 'borough': 'Hounslow'})
        self.assertEqual(status, 200)
        self.assertEqual(lon['context']['liveResolution'], 'measured')
        self.assertNotIn('PARTIAL', lon['sourceBreakdown']['live'])
        self.assertIn('Progress 8', lon['sourceBreakdown']['live'])

    def test_city_of_london_does_not_credit_bodies_that_supply_nothing(self):
        """The one borough where both national credits are wrong asserted them hardest.

        ONS declines to publish a recorded-crime rate for the City of London
        (Table C4 note 8, small resident population) and DfE has no Progress 8
        figure for it. The response nevertheless credited both, and reported
        liveResolution 'measured' - the field METHODOLOGY 4.4 says exists so a
        defaulted component cannot read as a measurement.
        """
        bd = app._borough_record('london', 'City of London')
        self.assertIsNotNone(bd)
        line = [x for x in app.build_sources('london', bd=bd) if 'Borough metadata' in x][0]
        self.assertIn('Sky Score estimate', line)
        self.assertNotIn(
            'Table C4', line,
            'City of London credits ONS Table C4 for a rate ONS explicitly suppresses',
        )
        # Note the line legitimately contains the words "Progress 8" while
        # DENYING it ("no Progress 8 figure published for this area"), so assert
        # on the credit itself rather than the phrase.
        self.assertNotIn(
            'Department for Education', line,
            'City of London credits DfE when no Progress 8 figure is published for it',
        )
        self.assertIn('partial', app.live_resolution(bd))

        # A borough with real data must be unaffected.
        camden = app._borough_record('london', 'Camden')
        cline = [x for x in app.build_sources('london', bd=camden) if 'Borough metadata' in x][0]
        self.assertIn('Table C4', cline)
        self.assertIn('Progress 8', cline)
        self.assertEqual(app.live_resolution(camden), 'measured')

    def test_london_sources_credit_only_bodies_that_answered(self):
        """The coarse `sources` line must track the data, not lag behind it.

        v3.5 moved the crime rate from Home Office recorded crime to ONS Table
        C4, but `sources` kept crediting the Home Office for ~24 hours after the
        deploy while `sourceBreakdown` already named ONS. A stale credit here is
        the same defect class as the NYC/OGL bug that motivated CITY_PROVENANCE
        — crediting on configuration rather than on what actually answered —
        and it is the harder one to notice, because the detailed breakdown
        sitting next to it is correct.
        """
        body, status = app.resolve_query({'city': 'london', 'borough': 'Camden'})
        self.assertEqual(status, 200)
        joined = ' '.join(body['sources'])
        self.assertNotIn(
            'Home Office', joined,
            'London sources credit the Home Office, which no longer supplies any '
            'component: crime is ONS Table C4 and schools are DfE Progress 8',
        )
        # The bodies that DO answer must still be named.
        self.assertIn('ONS', joined)
        self.assertIn('Department for Education', joined)

    def test_unknown_city_does_not_inherit_london_provenance(self):
        srcs = app.build_sources('atlantis')
        self.assertNotIn('MHCLG', ' '.join(srcs))
        self.assertEqual(app.build_source_breakdown('atlantis'), {})

    def test_batch_spanning_cities_labels_each_source(self):
        ev = {'body': json.dumps({'queries': [
            {'city': 'london', 'borough': 'Wandsworth'},
            {'city': 'nyc', 'borough': 'Brooklyn'},
        ]})}
        body = json.loads(app.handle_batch(ev)['body'])
        self.assertTrue(all(s.startswith('[') for s in body['sources']))
        self.assertTrue(any(s.startswith('[london]') for s in body['sources']))
        self.assertTrue(any(s.startswith('[nyc]') for s in body['sources']))
        # Single-city batches stay unprefixed, so the common case is unchanged.
        ev1 = {'body': json.dumps({'queries': [{'borough': 'Wandsworth'}]})}
        body1 = json.loads(app.handle_batch(ev1)['body'])
        self.assertEqual(body1['sources'], app.build_sources('london'))

    def test_spaced_form_derivation(self):
        # `pcds` is derived, not stored: the inward code is always the final
        # three characters, verified across all 2,723,596 rows of the loaded
        # edition. This mirrors scripts/load_nspl.py's own invariant check so
        # the two implementations can never drift apart.
        ddb = self._stub_ddb(None)
        for clean, spaced in (
            ('E16AN', 'E1 6AN'),
            ('SW1A1AA', 'SW1A 1AA'),
            ('SE109NF', 'SE10 9NF'),
            ('TW62GA', 'TW6 2GA'),
        ):
            ddb.get_item.return_value = {
                'Item': {
                    'postcode': {'S': clean},
                    'lat': {'N': '51.500000'},
                    'lon': {'N': '-0.100000'},
                    'lad': {'S': 'E09000033'},
                }
            }
            result = app._lookup_postcode_local(clean)
            self.assertEqual(result['postcode'], spaced, msg=f'key {clean!r}')

    def test_404_wording_is_the_shipped_string(self):
        # Audit L5 was resolved by RESTORING the pre-NSPL wording rather than
        # making it table-aware. This string is a public API surface — it is
        # what score-demo/openapi.yaml documents for 404 — and the feature's
        # whole forward-compatibility promise is that an unset POSTCODE_TABLE
        # leaves behaviour byte-identical. Rewording it is a breaking change
        # and must ship together with the OpenAPI description, so pin both.
        self._stub_ddb(None)
        with patch.object(app, '_fetch_postcode', return_value=None):
            body, status = app.resolve_query({'postcode': 'ZZ99 9ZZ'})
        self.assertEqual(status, 404)
        self.assertEqual(body['error'], 'Postcode not recognised by postcodes.io: ZZ99 9ZZ')

        spec = os.path.join(
            os.path.dirname(__file__), '..', '..', 'score-demo', 'openapi.yaml',
        )
        with open(spec, encoding='utf-8') as fh:
            self.assertIn('Postcode not recognised by postcodes.io', fh.read())


class ParseBoolFlagTests(unittest.TestCase):
    """audit L1a — `includeTerminated` arrives as a string from API Gateway's
    query-string map and as a native JSON type from a POST body. The shipped
    code did `(query.get('includeTerminated') or '').strip()`, so a JSON
    `true` raised AttributeError inside a batch worker and 500'd all 100
    queries. parse_bool_flag must therefore coerce every JSON type and never
    call a string method on an unvalidated value."""

    def test_native_booleans_pass_through(self):
        # isinstance(raw, bool) is checked FIRST on purpose: bool subclasses
        # int, so an int-first implementation would still be correct here but
        # for the wrong reason, and would silently change if the int branch
        # ever grew a range check.
        self.assertIs(app.parse_bool_flag(True), True)
        self.assertIs(app.parse_bool_flag(False), False)

    def test_string_forms_from_the_query_string(self):
        for raw in ('1', 'true', 'TRUE', ' True ', 'yes', 'Y', 'on'):
            self.assertTrue(app.parse_bool_flag(raw), msg=repr(raw))
        for raw in ('0', 'false', 'no', 'off', '', '   ', 'maybe'):
            self.assertFalse(app.parse_bool_flag(raw), msg=repr(raw))

    def test_numeric_forms(self):
        self.assertTrue(app.parse_bool_flag(1))
        self.assertTrue(app.parse_bool_flag(2))
        self.assertTrue(app.parse_bool_flag(1.5))
        self.assertFalse(app.parse_bool_flag(0))
        self.assertFalse(app.parse_bool_flag(0.0))

    def test_hostile_types_are_falsey_and_never_raise(self):
        # The actual crash class. A caller can put anything in a JSON body,
        # and every one of these used to reach `.strip()`.
        for raw in (None, {}, {'nested': 1}, [], ['true'], object()):
            self.assertFalse(app.parse_bool_flag(raw), msg=repr(raw))

    def test_truthy_flags_are_lower_case(self):
        # parse_bool_flag lower-cases before the membership test, so an
        # upper-case entry in the set would be permanently unreachable.
        self.assertEqual(app.TRUTHY_FLAGS, {f.lower() for f in app.TRUTHY_FLAGS})


class BatchIsolationTests(_LocalTierFixture, unittest.TestCase):
    """audit L1 — /v1/score/batch promises, in score-demo/openapi.yaml, that
    "failures do not abort the batch". Both halves of L1 broke that promise
    in the same way: one bad query took down its 99 siblings and the caller
    got a bare 500 with no indication of which query was at fault."""

    def _post(self, queries):
        return app.handler(
            {'httpMethod': 'POST', 'body': json.dumps({'queries': queries})}, None,
        )

    def test_json_native_boolean_flag_does_not_500_the_batch(self):
        # THE regression. Before parse_bool_flag this exact body returned
        # statusCode 500 / {"error": "Internal server error"} with an
        # AttributeError ('bool' object has no attribute 'strip') escaping
        # run_one, through ex.map, into the handler's catch-all.
        self._stub_ddb_rows({'BR11HB': _NSPL_BR1_1HB, 'SW111AA': _NSPL_SW11_1AA})
        queries = [{'postcode': 'BR1 1HB', 'includeTerminated': True}]
        queries += [{'postcode': 'SW11 1AA'} for _ in range(99)]

        with self._no_network():
            resp = self._post(queries)

        self.assertEqual(resp['statusCode'], 200)
        body = json.loads(resp['body'])
        self.assertEqual(body['totalQueries'], 100)
        self.assertEqual(body['successCount'], 100)
        self.assertEqual(body['errorCount'], 0)
        # The flag was not merely tolerated, it was honoured.
        self.assertEqual(body['results'][0]['location']['postcodeStatus'], 'terminated')
        self.assertEqual(body['results'][0]['location']['postcodeTerminatedDate'], '1984-12')
        # ...and the 99 siblings that did NOT opt in are unaffected by it.
        self.assertTrue(all(r['status'] == 200 for r in body['results'][1:]))
        self.assertNotIn('postcodeStatus', body['results'][1]['location'])

    def test_integer_and_hostile_flag_types_also_survive(self):
        # Integer 1 failed identically to `true` before the fix; a dict is the
        # shape a fuzzing client sends and must simply read as False.
        self._stub_ddb_rows({'BR11HB': _NSPL_BR1_1HB, 'SW111AA': _NSPL_SW11_1AA})
        queries = [
            {'postcode': 'BR1 1HB', 'includeTerminated': 1},
            {'postcode': 'SW11 1AA', 'includeTerminated': {'nested': True}},
            {'postcode': 'SW11 1AA', 'includeTerminated': ['true']},
            {'postcode': 'SW11 1AA', 'includeTerminated': None},
        ]
        with self._no_network():
            resp = self._post(queries)

        self.assertEqual(resp['statusCode'], 200)
        body = json.loads(resp['body'])
        self.assertEqual(body['successCount'], 4)
        self.assertEqual(body['results'][0]['location']['postcodeStatus'], 'terminated')

    def test_one_exploding_query_does_not_abort_its_siblings(self):
        # audit L1b. resolve_query has several parameters that still do
        # `(query.get(x) or '').strip()` (compare, city, persona, postcode,
        # borough), so a JSON POST body of {"city": 123} still raises today.
        # That is deliberately left as pre-existing behaviour — but the blast
        # radius must be one slot, not the whole batch. Simulated here with a
        # synthetic raise so the test does not encode which parameter happens
        # to be brittle this week.
        self._stub_ddb_rows({'SW111AA': _NSPL_SW11_1AA})
        real_parse_weights = app.parse_weights

        def exploding_parse_weights(raw):
            if raw == 'synthetic-boom':
                raise RuntimeError('synthetic per-query failure')
            return real_parse_weights(raw)

        queries = [{'postcode': 'SW11 1AA', 'weights': 'synthetic-boom'}]
        queries += [{'postcode': 'SW11 1AA'} for _ in range(99)]

        with self._no_network(), \
             patch.object(app, 'parse_weights', exploding_parse_weights), \
             self.assertLogs(app.logger, level='ERROR') as logs:
            resp = self._post(queries)

        self.assertEqual(resp['statusCode'], 200)
        body = json.loads(resp['body'])
        self.assertEqual(body['successCount'], 99)
        self.assertEqual(body['errorCount'], 1)
        # Exactly the per-item shape the result-assembly loop already emits
        # for a 400 or a 404, so no client needs to learn a new envelope.
        self.assertEqual(
            body['results'][0],
            {'queryIndex': 0, 'status': 500, 'error': 'Internal server error'},
        )
        # The failure is diagnosable from CloudWatch...
        self.assertTrue(any('synthetic' in line for line in logs.output))
        # ...and from nowhere else. No traceback, no exception message, no
        # internal detail reaches the caller.
        self.assertNotIn('synthetic', resp['body'])
        self.assertNotIn('RuntimeError', resp['body'])

    def test_non_dict_query_is_a_per_item_400(self):
        # The pre-existing guard, pinned so the new try/except around
        # resolve_query cannot quietly turn a clear 400 into a vague 500.
        self._stub_ddb_rows({'SW111AA': _NSPL_SW11_1AA})
        with self._no_network():
            resp = self._post([{'postcode': 'SW11 1AA'}, 'not-an-object', None])

        self.assertEqual(resp['statusCode'], 200)
        body = json.loads(resp['body'])
        self.assertEqual(body['successCount'], 1)
        self.assertEqual(body['errorCount'], 2)
        self.assertEqual(body['results'][1]['status'], 400)
        self.assertEqual(body['results'][1]['error'], 'Query must be an object.')

    def test_results_stay_in_submission_order(self):
        # Callers zip results back onto their own input rows by position, so
        # the per-query error path must not reorder anything.
        self._stub_ddb_rows({'SW111AA': _NSPL_SW11_1AA})
        queries = [{'postcode': 'SW11 1AA'} for _ in range(20)]
        queries[7] = {'city': 'atlantis', 'borough': 'Wandsworth'}
        with self._no_network():
            resp = self._post(queries)

        body = json.loads(resp['body'])
        self.assertEqual([r['queryIndex'] for r in body['results']], list(range(20)))
        self.assertEqual(body['results'][7]['status'], 400)


class DdbClientTests(unittest.TestCase):
    """audit L2 + L3 — the shared DynamoDB client factory.

    These deliberately do NOT patch _get_ddb_client: it is the function under
    test. Every other DynamoDB test in this file stubs it out, which is what
    let both defects sit in a fully-covered file — a construction failure
    escaping _lookup_postcode_local's documented never-raises contract, and a
    60s/60s botocore default inside a 28s Lambda."""

    def setUp(self):
        self._saved_client = (app._DDB_CLIENT, app._DDB_IMPORT_FAILED)
        app._DDB_CLIENT = None
        app._DDB_IMPORT_FAILED = False
        self._saved_cache = (app._postcode_cache_get, app._postcode_cache_put)
        app._postcode_cache_get, app._postcode_cache_put = app._make_lru(512)
        self._saved_raster_cache = (app._raster_cache_get, app._raster_cache_put)
        app._raster_cache_get, app._raster_cache_put = app._make_lru(2048)
        self._saved_tables = (app.POSTCODE_TABLE, app.NOISE_RASTER_TABLE)
        app.POSTCODE_TABLE = 'london-flight-map-postcodes'
        app.NOISE_RASTER_TABLE = 'london-flight-map-noise-raster'
        self.addCleanup(self._restore_module_state)

    def _restore_module_state(self):
        app._DDB_CLIENT, app._DDB_IMPORT_FAILED = self._saved_client
        app._postcode_cache_get, app._postcode_cache_put = self._saved_cache
        app._raster_cache_get, app._raster_cache_put = self._saved_raster_cache
        app.POSTCODE_TABLE, app.NOISE_RASTER_TABLE = self._saved_tables

    @staticmethod
    def _patch_boto3_client(**kwargs):
        """Patch boto3.client itself — the call _get_ddb_client makes — rather
        than the factory around it."""
        import boto3

        return patch.object(boto3, 'client', **kwargs)

    def test_construction_failure_returns_none_instead_of_raising(self):
        # NoRegionError, a malformed endpoint override and a broken shared
        # config file all raise HERE, outside every `except (BotoCoreError,
        # ClientError)` the two lookup functions have.
        with self._patch_boto3_client(side_effect=RuntimeError('NoRegionError')):
            self.assertIsNone(app._get_ddb_client())
            self.assertIsNone(app._lookup_postcode_local('SW111AA'))
            self.assertIsNone(app._lookup_lden_raster('SW111AA'))

    def test_construction_failure_degrades_to_postcodes_io(self):
        # The behaviour that matters to a caller: the NSPL tier going dark
        # must be indistinguishable from a table miss.
        sentinel = {'postcode': 'SW11 1AA', 'admin_district': 'Wandsworth'}
        with self._patch_boto3_client(side_effect=RuntimeError('NoRegionError')), \
             patch.object(app, '_fetch_postcode', return_value=sentinel) as fetch:
            result = app.lookup_postcode('SW11 1AA')
        self.assertIs(result, sentinel)
        fetch.assert_called_once_with('SW111AA')

    def test_construction_failure_is_not_latched(self):
        # Deliberately unlike the ImportError, which IS latched. Construction
        # failures are usually environmental and often transient; latching one
        # would silently disable both DynamoDB tables for the whole ~15-minute
        # warm-container lifetime, which is exactly the failure this feature's
        # forward-compatible design makes hardest to notice.
        with self._patch_boto3_client(side_effect=RuntimeError('transient')):
            self.assertIsNone(app._get_ddb_client())
        self.assertFalse(app._DDB_IMPORT_FAILED)
        self.assertIsNone(app._DDB_CLIENT)

        recovered = MagicMock(name='ddb')
        with self._patch_boto3_client(return_value=recovered):
            self.assertIs(app._get_ddb_client(), recovered)

    def test_client_carries_bounded_timeouts(self):
        # audit L3. botocore defaults to 60s connect and 60s read; the
        # function's Timeout is 28s (backend/template.yaml), so a DynamoDB
        # stall used to blow the function timeout and return 502 instead of
        # quietly deferring to postcodes.io.
        captured = {}

        def _capture(service, **kwargs):
            captured['service'] = service
            captured.update(kwargs)
            return MagicMock(name='ddb')

        with self._patch_boto3_client(side_effect=_capture):
            self.assertIsNotNone(app._get_ddb_client())

        self.assertEqual(captured['service'], 'dynamodb')
        config = captured['config']
        self.assertEqual(config.connect_timeout, 1)
        self.assertEqual(config.read_timeout, 2)
        # total_max_attempts is a TOTAL (initial + retries), unlike
        # max_attempts which is the retry count — so this bound reads the same
        # whichever botocore retry mode is in force.
        attempts = config.retries['total_max_attempts']
        self.assertEqual(attempts, 2)
        # The arithmetic the comment in app.py claims: worst case must leave
        # room for the 5s postcodes.io fallback that follows a DDB failure.
        worst_case = attempts * (config.connect_timeout + config.read_timeout)
        self.assertLess(worst_case + 5, 28, 'DDB retry budget no longer fits the 28s timeout')

    def test_concurrent_cold_start_builds_exactly_one_client(self):
        # /v1/score/batch launches BATCH_PARALLELISM workers that now all
        # reach _get_ddb_client() on a cold container with no preceding I/O to
        # stagger them — the NSPL lookup is the first thing each worker does,
        # unlike the raster lookup which sat behind a ~200ms postcodes.io round
        # trip. boto3's module-level default session is documented as not
        # thread-safe. The sleep widens the window the double-checked lock
        # closes; without the lock this builds BATCH_PARALLELISM clients.
        built = []
        barrier = threading.Barrier(app.BATCH_PARALLELISM)

        def _slow_client(service, **kwargs):
            built.append(service)
            time.sleep(0.02)
            return MagicMock(name='ddb')

        clients = []

        def _worker():
            barrier.wait()
            clients.append(app._get_ddb_client())

        with self._patch_boto3_client(side_effect=_slow_client):
            threads = [threading.Thread(target=_worker) for _ in range(app.BATCH_PARALLELISM)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(len(built), 1)
        self.assertEqual(len(clients), app.BATCH_PARALLELISM)
        self.assertEqual(len({id(c) for c in clients}), 1)

    def test_warm_path_reuses_the_cached_client(self):
        first = MagicMock(name='ddb')
        with self._patch_boto3_client(return_value=first):
            self.assertIs(app._get_ddb_client(), first)
        # boto3.client is un-patched now, so a second construction would build
        # a real client and this identity check would fail.
        self.assertIs(app._get_ddb_client(), first)

    def test_table_unset_still_short_circuits_before_any_client(self):
        # The forward-compatibility guarantee, re-asserted against the real
        # factory: POSTCODE_TABLE is unset in production today.
        app.POSTCODE_TABLE = ''
        with self._patch_boto3_client(side_effect=AssertionError('client built')):
            self.assertIsNone(app._lookup_postcode_local('SW111AA'))


class LruConcurrencyTests(unittest.TestCase):
    """audit L6 — _make_lru's get() tested membership and then called
    move_to_end as separate bytecode sequences, so a concurrent put() whose
    popitem evicted the LRU tail in between raised KeyError on the very key
    get() had just found. /v1/score/batch runs BATCH_PARALLELISM threads over
    these shared caches, and the escaping KeyError turned 100 resolvable
    queries into one 500."""

    def test_get_and_put_are_safe_under_concurrent_access(self):
        # maxsize 8 against 8 threads keeps the cache permanently full and
        # evicting on nearly every put — the state a sustained 100k-postcode
        # backfill puts the real 512-entry cache into, and the state that
        # holds the race window open.
        get, put = app._make_lru(8)
        errors = []
        deadline = time.monotonic() + 0.4

        def _hammer(tid):
            i = 0
            try:
                while time.monotonic() < deadline:
                    put(f'{tid}-{i}', {'v': i})   # unique key, forces eviction
                    put('hot', {'v': i})          # shared key, forces move_to_end
                    get('hot')                    # the call that used to raise
                    get(f'{tid}-{i}')
                    i += 1
            except Exception as exc:  # noqa: BLE001 — recording the race IS the test
                errors.append(f'{tid}: {exc!r}')

        threads = [threading.Thread(target=_hammer, args=(t,)) for t in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f'LRU raced under concurrent access: {errors[:3]}')

    def test_none_is_still_never_cached(self):
        # The do-not-cache-None semantics must survive the locking change: a
        # cached None would re-serve a transient DDB throttle or a
        # postcodes.io blip as a sticky 404 for the warm-container lifetime.
        get, put = app._make_lru(4)
        put('k', None)
        self.assertIsNone(get('k'))
        put('k', {'v': 1})
        self.assertEqual(get('k'), {'v': 1})

    def test_eviction_is_still_least_recently_used(self):
        get, put = app._make_lru(2)
        put('a', 1)
        put('b', 2)
        get('a')      # 'a' is now the most recently used
        put('c', 3)   # so 'b' is the one evicted
        self.assertEqual(get('a'), 1)
        self.assertIsNone(get('b'))
        self.assertEqual(get('c'), 3)


class IndependentReviewRegressionTests(unittest.TestCase):
    """Regressions found by independent review of the 2026-07-25 fixes.

    Every case here is something a previous pass believed it had fixed. The
    signup outage ran for two and a half months because the suite asserted
    only that things fail correctly, never that they work — so each of these
    asserts the working behaviour, not the error path.
    """

    def setUp(self):
        self._served = app._LOCAL_POSTCODE_SERVED
        self._table = app.POSTCODE_TABLE
        self._raster = app.NOISE_RASTER_TABLE
        self._client = app._DDB_CLIENT

    def tearDown(self):
        app._LOCAL_POSTCODE_SERVED = self._served
        app.POSTCODE_TABLE = self._table
        app.NOISE_RASTER_TABLE = self._raster
        app._DDB_CLIENT = self._client

    def _count_raster_getitems(self, query):
        """Run a query against a stub DDB and count raster GetItem calls."""
        calls = []

        class _Stub:
            def get_item(self, **kw):
                calls.append(kw['TableName'])
                return {}

        app._DDB_CLIENT = _Stub()
        app.NOISE_RASTER_TABLE = 'london-flight-map-noise-raster'
        # The 2026-08-03 quarantine means the raster is never looked up, so
        # without this every count here would be 0. Lifting it for the duration
        # keeps these two tests guarding what they were written to guard — the
        # de-duplication that stops ?compare=previous making four GetItems and
        # timing out into a 502. Rewriting them to expect 0 would have been the
        # easy way to green and would have quietly retired both guards, leaving
        # nothing to catch the regression when the tier is eventually restored.
        with patch.object(app, '_raster_cache_get', lambda k: None), patch.object(
            app, 'RASTER_TIER_QUARANTINED', False
        ):
            app.resolve_query(dict(query))
        return len([c for c in calls if 'raster' in c])

    def test_raster_lookup_is_not_repeated_within_one_score(self):
        # calc_score resolves the raster, then calls calc_postcode_quiet,
        # which used to resolve it AGAIN for the same postcode. _make_lru
        # never caches a negative, so a miss really did hit DynamoDB twice.
        # On a stall that doubling is what pushed a ?compare=previous request
        # past the 28s Lambda timeout into a 502.
        self.assertEqual(self._count_raster_getitems({'postcode': 'SW11 1AA'}), 1)

    def test_compare_previous_does_not_quadruple_raster_lookups(self):
        # ?compare=previous runs calc_score twice, so the duplication above
        # cost four GetItems per request rather than two.
        self.assertEqual(
            self._count_raster_getitems({'postcode': 'SW11 1AA', 'compare': 'previous'}), 2
        )


class RasterQuarantineTests(unittest.TestCase):
    """Guards the 2026-08-03 quarantine of the DEFRA raster tier.

    The defect these exist for was invisible to this suite for over a week,
    because it lived in DynamoDB rather than in any function: every unit test
    ran with no raster table configured, took the Haversine tier, and passed
    while production served something else entirely. So these tests stub the
    table with the values it genuinely holds, rather than with tidy fixtures.
    """

    # TW6 1AP — inside Heathrow Airport (Heathrow Villages ward, Hillingdon).
    HEATHROW_LAT, HEATHROW_LON = 51.472385, -0.450939
    # What london-flight-map-noise-raster actually stores for it. Not invented.
    HEATHROW_STORED_LDEN = 58.2

    def setUp(self):
        self._raster = app.NOISE_RASTER_TABLE
        self._client = app._DDB_CLIENT
        self._cache = (app._raster_cache_get, app._raster_cache_put)
        app._raster_cache_get, app._raster_cache_put = app._make_lru(16)

    def tearDown(self):
        app.NOISE_RASTER_TABLE = self._raster
        app._DDB_CLIENT = self._client
        app._raster_cache_get, app._raster_cache_put = self._cache

    def _serve_raster(self, lden):
        """Point the raster tier at a stub table holding exactly `lden` dB."""

        class _Stub:
            def get_item(self, **kw):
                return {'Item': {'ldenDb': {'N': str(lden)}}}

        app._DDB_CLIENT = _Stub()
        app.NOISE_RASTER_TABLE = 'london-flight-map-noise-raster'

    def test_airport_postcode_is_never_scored_as_quiet(self):
        """A postcode inside Heathrow must not score as a quiet place.

        Deliberately absolute rather than comparative. "Heathrow scores worse
        than Finsbury Park" PASSES on the broken data — 7.5 against 10.0 — and
        that is precisely why the collapse survived a week in production: the
        ordering stayed plausible while the magnitudes stopped meaning anything.
        The defect is magnitude, so the assertion has to be about magnitude.

        The stub serves the real stored value, so this returns 7.5 and fails
        unless the quarantine short-circuits the lookup. Clearing
        RASTER_TIER_QUARANTINED without first reloading the table turns it red.
        """
        self._serve_raster(self.HEATHROW_STORED_LDEN)
        quiet = app.calc_postcode_quiet(
            self.HEATHROW_LAT, self.HEATHROW_LON, 'london', postcode_clean='TW61AP'
        )
        self.assertLessEqual(
            quiet,
            3.0,
            f'Heathrow Airport scored {quiet}/10 for quiet. The raster tier serves '
            f'~{self.HEATHROW_STORED_LDEN} dB Lden there, against DEFRA Round 4 '
            f'contours above 75 dB near the runways.',
        )

    def test_legacy_nodata_fill_is_treated_as_a_miss(self):
        """A stored 35.0 must not be served as a measurement.

        89.5% of London postcodes lie outside DEFRA's aircraft contours, and the
        loader used to write 35.0 for every one of them so that the score came
        out at a perfect 10.0. That turned "not measured" into "quiet" and put
        98% of the city on one value.

        Safe to treat as a sentinel rather than a guess: the raster's minimum
        real value is 40.0 dB, so 35.0 cannot be a genuine sample. Asserted with
        the quarantine lifted, because otherwise this passes for the wrong reason
        — the short-circuit would return None whatever the table held.
        """
        self._serve_raster(35.0)
        with patch.object(app, 'RASTER_TIER_QUARANTINED', False):
            self.assertIsNone(
                app._lookup_lden_raster('E18BL'),
                'legacy 35.0 nodata fill was served as a real Lden reading',
            )
            # A real sample must still come through.
            self._serve_raster(58.2)
            self.assertEqual(app._lookup_lden_raster('TW61AP'), 58.2)

    def test_quiet_still_discriminates_across_london(self):
        """Quiet must not collapse onto a handful of values.

        Third instance of one defect class: growth once floored fourteen
        boroughs onto a single value, schools published two distinct sub-scores
        across all of London, and the raster reduced quiet to exactly two (7.5
        and 10.0). A component that cannot separate places is not measuring one.
        """
        places = [
            (51.472385, -0.450939),  # Heathrow
            (51.4700, -0.3600),      # Hounslow, under the approach
            (51.5665, -0.1058),      # Finsbury Park
            (51.4650, -0.1680),      # Battersea
            (51.4060, 0.0150),       # Bromley
        ]
        scores = {
            app.calc_postcode_quiet(la, lo, 'london', postcode_clean=None, raster_lden=None)
            for la, lo in places
        }
        self.assertGreaterEqual(
            len(scores),
            3,
            f'quiet produced only {len(scores)} distinct values across Heathrow to '
            f'Bromley: {sorted(scores)}',
        )

    def test_json_native_parameter_types_do_not_error(self):
        # A GET query string is always strings, but a batch POST body carries
        # native JSON types. Each of these raised AttributeError, which the
        # per-query batch guard then turned into an opaque 500 for that query.
        for label, query in [
            ('include as a JSON array', {'postcode': 'SW11 1AA', 'include': ['score', 'components']}),
            ('include as a number', {'postcode': 'SW11 1AA', 'include': 5}),
            ('compare as a JSON boolean', {'postcode': 'SW11 1AA', 'compare': True}),
            ('compare as a JSON array', {'postcode': 'SW11 1AA', 'compare': ['previous']}),
        ]:
            with self.subTest(label):
                _body, status = app.resolve_query(dict(query))
                self.assertEqual(status, 200)

    def test_include_as_json_array_actually_filters(self):
        # Not just "does not raise" — it must behave like the comma string.
        body, status = app.resolve_query(
            {'postcode': 'SW11 1AA', 'include': ['score']}
        )
        self.assertEqual(status, 200)
        self.assertIn('score', body)
        self.assertNotIn('components', body)

    def test_regions_and_sources_agree_on_provenance(self):
        # Keying postcodeResolver on POSTCODE_TABLE (config) while
        # build_sources keyed on actual service let two endpoints of the same
        # API contradict each other for the whole ~40-minute load window.
        app.POSTCODE_TABLE = 'london-flight-map-postcodes'
        event = {'requestContext': {'http': {'method': 'GET'}}, 'rawPath': '/v1/regions', 'headers': {}}

        for served in (False, True):
            with self.subTest(served=served):
                app._LOCAL_POSTCODE_SERVED = served
                raw = app.handle_regions(event)['body']
                credits_ons_in_sources = 'ONS' in app.build_sources()[2]
                claims_nspl_in_regions = 'NSPL' in raw
                self.assertEqual(claims_nspl_in_regions, credits_ons_in_sources)
                self.assertEqual(credits_ons_in_sources, served)


class LdenBandMappingTests(unittest.TestCase):
    """v3.6 dB → quiet curve, re-derived 2026-08-04.

    The bands this replaces were not merely mis-tuned. They were derived for
    DEFRA's *published reporting bands*, which begin at 55 dB, and then applied
    to the *raster*, which begins at 40.0. Two repo documents recorded the
    premise backwards — AUDIT_REPORT.md as "every DEFRA value is above 55 dB",
    BAND_MAPPING_ANALYSIS.md as "there is no 45-55 dB contour to score against"
    — and both are refuted by the GeoTIFF itself.

    Measured over all 180,983 live London postcode centroids on 2026-08-04:
    18,862 covered, spanning 40.0-73.0 dB, of which the old table scored
    15,173 (80.4%) at a flat 10.0. These tests exist so that cannot recur
    silently.
    """

    # Real samples, read off data/defra_lden_2022.tif. Not fixtures.
    HEATHROW = 58.20        # TW6 1AP
    HOUNSLOW_APPROACH = 59.29  # TW3 4DX
    BEDFONT_LOUDEST = 72.97    # TW14 9QP, loudest covered postcode in London
    KEW = 55.96             # TW9 1AA
    BARNES = 52.46          # SW13 9AA
    RASTER_MIN = 40.0       # the raster's true floor

    def test_who_guideline_anchors_the_ceiling(self):
        """10.0 means "at or below WHO's 45 dB aircraft guideline".

        Not "below DEFRA's 55 dB reporting threshold", which is a statement
        about which maps must be published, not about anyone's health.
        """
        self.assertEqual(app.lden_db_to_quiet(45.0), 10.0)
        self.assertEqual(app.lden_db_to_quiet(self.RASTER_MIN), 10.0)
        self.assertLess(app.lden_db_to_quiet(45.1), 10.0)

    def test_none_is_preserved_as_no_sample(self):
        """None must survive: the caller reads it as "no raster sample", which
        is what routes an uncovered postcode down to the Haversine tier."""
        self.assertIsNone(app.lden_db_to_quiet(None))

    def test_airport_is_not_scored_quiet(self):
        """The invariant scripts/check_score_sanity.py enforces against the
        live API, asserted here where it is cheap to run.

        The old table returned 7.5 for this exact value — an airport reading
        as "fairly quiet" — and that is the assertion the quarantine exists
        to hold until it passes.
        """
        self.assertLessEqual(app.lden_db_to_quiet(self.HEATHROW), 3.0)
        self.assertLessEqual(app.lden_db_to_quiet(self.HOUNSLOW_APPROACH), 3.0)
        self.assertEqual(app.lden_db_to_quiet(self.BEDFONT_LOUDEST), 0.0)

    def test_curve_does_not_collapse_the_measured_range(self):
        """The 40-55 dB range must produce many values, not one.

        This is the defect in one assertion. Those 15,173 postcodes carry
        genuine measurements spanning ~15 dB — roughly a tripling of perceived
        loudness — and the old table handed every one of them a flat 10.0.
        A tier that cannot separate places is not measuring one.
        """
        values = {app.lden_db_to_quiet(db) for db in
                  [40.0, 43.0, 46.0, 48.0, 50.0, 52.0, 54.0]}
        self.assertGreaterEqual(
            len(values), 5,
            f'the 40-55 dB range collapsed to {len(values)} distinct value(s): '
            f'{sorted(values)}. This is the 2026-08-03 defect returning.')

    def test_curve_is_monotonic_non_increasing(self):
        """Louder can never score quieter. Guards a mis-ordered band edge."""
        prev = 10.0
        db = 40.0
        while db <= 90.0:
            cur = app.lden_db_to_quiet(db)
            self.assertLessEqual(
                cur, prev, f'quiet rose from {prev} to {cur} at {db} dB')
            prev = cur
            db += 0.5

    def test_named_places_keep_their_relative_order(self):
        """Ordering across real London places, quietest to loudest."""
        ordered = [self.BARNES, self.KEW, self.HEATHROW,
                   self.HOUNSLOW_APPROACH, self.BEDFONT_LOUDEST]
        scores = [app.lden_db_to_quiet(d) for d in ordered]
        self.assertEqual(scores, sorted(scores, reverse=True),
                         f'Barnes→Bedfont did not descend: {scores}')

    def test_saturation_at_the_loud_end_is_bounded(self):
        """The known limitation, pinned so it cannot widen unnoticed.

        Everything at or above the 63 dB floor reads 0.0, which costs
        discrimination among the loudest 1.8% of covered postcodes. Accepted
        and disclosed in METHODOLOGY.md §4.6 — but if a future edit drops the
        floor much lower, that 1.8% grows and this test should be the thing
        that objects.
        """
        self.assertEqual(app.lden_db_to_quiet(63.0), 0.0)
        self.assertGreater(app.lden_db_to_quiet(62.0), 0.0,
                           'saturation reached below the documented 63 dB floor')


class RasterPlausibilityGuardTests(unittest.TestCase):
    """The read-side guard widened 2026-08-04 from `== 35.0` to a range.

    Equality only ever caught the one sentinel we happened to have written.
    Any other (0, -1, -9999) would have passed through and, under the old
    bands, scored a perfect 10.0 — this project's most-repeated defect,
    absence of measurement rendered as a favourable measurement.
    """

    def setUp(self):
        self._raster = app.NOISE_RASTER_TABLE
        self._client = app._DDB_CLIENT
        self._cache = (app._raster_cache_get, app._raster_cache_put)
        app._raster_cache_get, app._raster_cache_put = app._make_lru(16)

    def tearDown(self):
        app.NOISE_RASTER_TABLE = self._raster
        app._DDB_CLIENT = self._client
        app._raster_cache_get, app._raster_cache_put = self._cache

    def _serve_raster(self, lden):
        class _Stub:
            def get_item(self, **kw):
                return {'Item': {'ldenDb': {'N': str(lden)}}}

        app._DDB_CLIENT = _Stub()
        app.NOISE_RASTER_TABLE = 'london-flight-map-noise-raster'

    def test_sentinels_below_the_raster_floor_are_misses(self):
        """Asserted with the quarantine lifted — otherwise every case passes
        for the wrong reason, since the short-circuit returns None regardless
        of what the table holds."""
        for sentinel in (35.0, 0.0, -1.0, -9999.0, 39.9):
            with self.subTest(sentinel=sentinel):
                self._serve_raster(sentinel)
                with patch.object(app, 'RASTER_TIER_QUARANTINED', False):
                    self.assertIsNone(
                        app._lookup_lden_raster(f'X{sentinel}'),
                        f'{sentinel} was served as a genuine Lden reading')

    def test_the_rasters_true_minimum_is_still_a_valid_reading(self):
        """40.0 is a real DEFRA value, not a sentinel. Widening the guard must
        not have swallowed the quietest genuine samples."""
        self._serve_raster(40.0)
        with patch.object(app, 'RASTER_TIER_QUARANTINED', False):
            self.assertEqual(app._lookup_lden_raster('TESTMIN'), 40.0)

    def test_unexpected_sentinel_is_logged_but_known_fill_is_not(self):
        """An unexpected value should surface; the 35.0 we already know about
        should not spam the alarm channel on 89.5% of London's postcodes."""
        self._serve_raster(-9999.0)
        with patch.object(app, 'RASTER_TIER_QUARANTINED', False):
            with patch.object(app, 'logger') as log:
                app._lookup_lden_raster('WEIRD1')
                self.assertTrue(log.warning.called,
                                'implausible Lden passed without a warning')

        self._serve_raster(35.0)
        with patch.object(app, 'RASTER_TIER_QUARANTINED', False):
            with patch.object(app, 'logger') as log:
                app._lookup_lden_raster('KNOWN1')
                self.assertFalse(log.warning.called,
                                 'the known 35.0 fill should not alarm')


class CoreCitiesAuditTests(unittest.TestCase):
    """Regressions for the 2026-07-31 cross-city audit findings.

    Each of these is written to be able to FAIL. A guard that cannot go red is
    the failure mode that let preflight report green while running nothing, so
    the vocabulary test below deliberately feeds bad data and asserts it raises,
    rather than only asserting the good data passes.
    """

    def test_vocabulary_guard_rejects_off_table_token(self):
        # 'poor' is a valid TRANSPORT_SCORE key but not a SCHOOL_SCORE one, so
        # it is the natural thing to write and the one that silently scored 5.0
        # — better than the real worst band, 'mixed' at 3.
        self.assertNotIn('poor', app.SCHOOL_SCORE)
        self.assertEqual(app.SCHOOL_SCORE.get('poor', 5), 5)
        self.assertLess(app.SCHOOL_SCORE['mixed'], 5)

        bad = {'testcity': {'boroughs': {'Testville': {'schools': 'poor'}}}}
        with self.assertRaises(ValueError) as ctx:
            app.validate_borough_vocabulary(bad)
        self.assertIn('schools', str(ctx.exception))
        self.assertIn('Testville', str(ctx.exception))

    def test_vocabulary_guard_rejects_off_table_noise_band(self):
        """`impact` was unguarded until 2026-08-04 (audit finding 28).

        The most consequential field to miss, and the last one added. It feeds
        `IMPACT_TO_QUIET.get(bd['impact'], 5.0)`, so a plausible typo does not
        raise — it silently scores 5.0 on the product's headline component, and
        the direction is always the same: a severe-noise borough is *upgraded*
        to middling. Erring quiet is the one direction a noise product cannot
        afford, which is what makes this worse than the schools case above.
        """
        self.assertIn('impact', app._CATEGORICAL_FIELDS)
        # 'sever' is the natural mistype of the real worst band, and it scores
        # 5.0 against 'severe' at 0.0 — a 5-point silent upgrade.
        self.assertNotIn('sever', app.IMPACT_TO_QUIET)
        self.assertEqual(app.IMPACT_TO_QUIET.get('sever', 5.0), 5.0)
        self.assertLess(app.IMPACT_TO_QUIET['severe'], 5.0)

        bad = {'testcity': {'boroughs': {'Testville': {'impact': 'sever'}}}}
        with self.assertRaises(ValueError) as ctx:
            app.validate_borough_vocabulary(bad)
        self.assertIn('impact', str(ctx.exception))
        self.assertIn('Testville', str(ctx.exception))

    def test_every_scoring_lookup_table_is_actually_guarded(self):
        """The guard's coverage, not just its behaviour.

        `impact` was missing for months while three sibling fields were
        covered, and nothing detected that because every test asserted the
        guard's *logic* rather than its *scope*. This asserts the scope: any
        categorical borough field the scoring engine reads through a
        `.get(value, default)` lookup must appear in _CATEGORICAL_FIELDS.
        """
        for field in ('impact', 'transport', 'healthcare'):
            with self.subTest(field=field):
                self.assertIn(
                    field, app._CATEGORICAL_FIELDS,
                    f'{field} is read from borough data through a defaulting '
                    f'lookup but is not validated at import, so a typo in it '
                    f'scores the default instead of failing.')

    def test_vocabulary_guard_allows_absent_fields(self):
        # A city part-way through sourcing is a known, handled state. Only a
        # PRESENT-but-unrecognised value is an error.
        app.validate_borough_vocabulary(
            {'testcity': {'boroughs': {'Testville': {'avgPrice': 1, 'trend': 0.0}}}}
        )

    def test_shipped_data_passes_its_own_guard(self):
        app.validate_borough_vocabulary(app.CITIES)

    def test_regions_announces_every_scoreable_city(self):
        # The discovery endpoint was a hand-written two-city literal, so adding
        # Greater Manchester to CITIES produced an API that scored a city it
        # would not admit to supporting.
        event = {'requestContext': {'http': {'method': 'GET'}}, 'rawPath': '/v1/regions', 'headers': {}}
        body = json.loads(app.handle_regions(event)['body'])
        announced = {c['id'] for c in body['cities']}
        self.assertEqual(announced, set(app.CITIES))
        for entry in body['cities']:
            self.assertEqual(entry['boroughCount'], len(app.CITIES[entry['id']]['boroughs']))

    def test_city_without_history_declines_to_compare(self):
        # Returning the current dataset made ?compare=previous fabricate a
        # measured zero change, byte-identical to NYC's honest zero.
        #
        # hasHistory defaults to False, so this asserts the guarantee for ANY
        # future city rather than only the one that exposed the bug. A city
        # added without declaring a baseline must decline to compare.
        self.assertIsNotNone(app.previous_dataset('london'))
        self.assertIsNotNone(app.previous_dataset('nyc'))
        app.CITIES['testville'] = {
            'boroughs': {'Testville': {'avgPrice': 1, 'trend': 0.0, 'impact': 'low'}},
            'currency': 'GBP', 'name': 'Testville', 'country': 'United Kingdom',
            'postcodeFormat': 'n/a', 'postcodeResolver': lambda: 'n/a',
        }
        try:
            self.assertIsNone(app.previous_dataset('testville'))
        finally:
            del app.CITIES['testville']

    def test_include_comparison_keeps_the_reason_there_is_none(self):
        filtered = app.filter_response(
            {'comparisonUnavailable': 'why', 'score': 1}, {'comparison'}
        )
        self.assertIn('comparisonUnavailable', filtered)

    def test_live_resolution_distinguishes_measured_from_placeholder(self):
        # 5.0 is below London's entire observed live range, so an unsourced city
        # is penalised rather than treated neutrally. The score cannot say that;
        # the resolution field can.
        london_live = [
            app.get_live_score(bd) for bd in app.CITIES['london']['boroughs'].values()
        ]
        self.assertGreater(min(london_live), 5.0)

        sourced = app.CITIES['london']['boroughs']['Hounslow']
        self.assertEqual(app.live_resolution(sourced), 'measured')

        unsourced = {'avgPrice': 1, 'trend': 0.0}
        self.assertEqual(app.get_live_score(unsourced), 5.0)
        self.assertIn('unavailable', app.live_resolution(unsourced))
        # A single genuinely-measured input is 'partial'.
        self.assertIn('partial', app.live_resolution({'p8': 0.1}))

        # But the legacy Ofsted band alone is NOT a measured schools input for an
        # English borough (changed 2026-08-03). It used to count, which is how the
        # City of London reported 'measured' while its schools input was the
        # retired editorial band and its crime rate was our own estimate. New York
        # is the reverse case: it has neither Ofsted nor DfE, so the curated tier
        # IS its source and still counts.
        self.assertIn('unavailable', app.live_resolution({'schools': 'good'}))
        self.assertIn('partial', app.live_resolution({'schools': 'good'}, english=False))


class ProgressEightTests(unittest.TestCase):
    """Schools moved from Ofsted editorial bands to DfE Progress 8, 2022/23."""

    def test_anchors_are_absolute_not_cohort_relative(self):
        # The whole point: 0.0 is the national average and +/-1.0 is a full
        # grade per subject. Neither depends on which cities are loaded, which
        # is what makes the scale comparable across cities and vintages.
        self.assertEqual(app.school_score(0.0), 5.0)
        self.assertEqual(app.school_score(1.0), 10.0)
        self.assertEqual(app.school_score(-1.0), 0.0)
        self.assertEqual(app.school_score(2.0), 10.0)   # clamped
        self.assertEqual(app.school_score(-2.0), 0.0)   # clamped

    def test_nothing_clamps_on_real_data(self):
        # Observed LA Progress 8 runs -0.90 to +0.73 nationally, so a clamp
        # would mean the anchors are wrong for the data they have to carry.
        # Iterates CITIES rather than a hardcoded city list so the assertion
        # keeps holding as cities are added, instead of silently skipping them.
        vals = [
            app.school_score(b['p8'])
            for cfg in app.CITIES.values()
            for b in cfg['boroughs'].values()
            if b.get('p8') is not None
        ]
        self.assertEqual(len(vals), 32)  # London's 33 less the City of London
        self.assertNotIn(0.0, vals)
        self.assertNotIn(10.0, vals)

    def test_it_discriminates_where_the_ofsted_stock_did_not(self):
        # The Ofsted measure put 11 London boroughs on an identical 100% Good
        # or Outstanding. A schools input that cannot separate places carries
        # no signal, which is the defect this change exists to fix.
        new = {
            app.school_score(b['p8'])
            for b in app.LONDON_BOROUGHS.values() if b.get('p8') is not None
        }
        old = {
            app.SCHOOL_SCORE.get(b.get('schools'), 5)
            for b in app.LONDON_BOROUGHS.values()
        }
        # London used exactly two of the four bands, so the old input could
        # place 33 boroughs in 2 buckets. Progress 8 puts them in 25.
        self.assertEqual(len(old), 2)
        self.assertGreater(len(new), 10 * len(old))

    def test_falls_back_where_progress_8_cannot_exist(self):
        # New York has neither Ofsted nor DfE. It keeps the curated tier, and
        # CITY_PROVENANCE is what stops that being passed off as DfE.
        queens = app.NYC_BOROUGHS['Queens']
        self.assertIsNone(queens.get('p8'))
        self.assertIsNotNone(app.get_live_score(queens))
        self.assertIn('Progress 8', app.build_source_breakdown('london')['live'])
        # NYC's text does contain the string 'DfE' -- inside the disclaimer
        # 'NOT ONS, Home Office, DfE, TfL or NHS'. So assert on the claim, not
        # on the substring: NYC must not claim Progress 8, and must carry the
        # explicit negation.
        nyc_live = app.build_source_breakdown('nyc')['live']
        self.assertNotIn('Progress 8', nyc_live)
        self.assertIn('NOT ONS, Home Office, DfE', nyc_live)

    def test_city_of_london_has_no_progress_8(self):
        # Not in the DfE local-authority release at all — it has essentially no
        # secondary schools. Third field to hit the same measured/missing/not-
        # calculable distinction, alongside its suppressed ONS crime rate.
        self.assertIsNone(app.LONDON_BOROUGHS['City of London'].get('p8'))


if __name__ == '__main__':
    unittest.main()


class SiteApiGeometryParityTests(unittest.TestCase):
    """The consumer site and this Lambda must score quiet from identical geometry.

    They did not, for three months. METHODOLOGY records that the London corridors
    were trimmed on 2026-05-07 to their noise-relevant portions and audited
    against the DEFRA raster; the trim landed in index.html and in
    scripts/audit_flight_paths.py but never here. The API kept 85 waypoints
    across 12 corridors against the site's 50 across 10, so it scored noisier
    wherever they differed - 34.6% of London measured over 7,239 live postcodes,
    and noisier in 100% of the disagreements.

    Nothing could have caught it: the unit suites only ever read this module, and
    the Playwright suite only ever reads the site. Each half was self-consistent.
    This test is the only thing that looks at both.
    """

    @staticmethod
    def _site_flight_paths():
        """Parse FLIGHT_PATHS out of index.html. Site stores [lon, lat]."""
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'index.html')
        src = open(os.path.abspath(path), encoding='utf-8').read()
        i = src.index('const FLIGHT_PATHS = [')
        start = i + src[i:].index('[')
        depth = 0
        for j in range(start, len(src)):
            if src[j] == '[':
                depth += 1
            elif src[j] == ']':
                depth -= 1
                if depth == 0:
                    break
        block = src[start:j + 1]
        out = {}
        for m in re.finditer(r"name:\s*'([^']+)'(.*?)(?=name:\s*'|\Z)", block, re.S):
            pts = re.findall(
                r'\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]', m.group(2)
            )
            out[m.group(1)] = [(float(lat), float(lon)) for lon, lat in pts]
        return out

    def test_flight_path_geometry_matches_the_site(self):
        site = self._site_flight_paths()
        api = {
            p['name']: [(float(a), float(b)) for a, b in p['coords']]
            for p in app.CITY_GEOMETRY['london']['paths']
        }
        self.assertTrue(site, 'could not parse FLIGHT_PATHS out of index.html')

        only_api = sorted(set(api) - set(site))
        only_site = sorted(set(site) - set(api))
        self.assertEqual(
            only_api, [],
            f'corridors in the API but not the audited site geometry: {only_api}. '
            'The 2026-05-07 trim removed Approach N and Approach S; if they are '
            'back here, this module was edited without index.html.',
        )
        self.assertEqual(only_site, [], f'corridors on the site but missing here: {only_site}')

        for name in sorted(site):
            self.assertEqual(
                api[name], site[name],
                f'{name}: geometry differs between index.html and this module. '
                f'site has {len(site[name])} waypoints, API has {len(api[name])}. '
                'More waypoints here means the API scores noisier than the site '
                'for the same postcode.',
            )

    def test_heliports_match_the_site(self):
        """Rotary sites and their weights must match index.html.

        The site scored heliports and the Lambda did not, which was the last
        site/API divergence after the flight-path trim and covered 14.1% of
        Greater London. Ported 2026-08-03. The weights are derived from published
        movement counts, so a silent edit on one side is a scoring change on one
        surface only.
        """
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'index.html')
        src = open(os.path.abspath(path), encoding='utf-8').read()
        i = src.index('const HELIPORTS = [')
        start = i + src[i:].index('[')
        depth = 0
        for j in range(start, len(src)):
            if src[j] == '[':
                depth += 1
            elif src[j] == ']':
                depth -= 1
                if depth == 0:
                    break
        block = src[start:j + 1]

        site = {}
        for m in re.finditer(r"\{\s*code:\s*'([^']+)',(.*?)\n        \}", block, re.S):
            body = m.group(2)
            co = re.search(r"coords:\s*\[\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\]", body)
            bd = re.search(r"bands:\s*\[\s*(\d+)\s*,\s*(\d+)\s*\]", body)
            site[m.group(1)] = {
                'lat': float(co.group(2)),
                'lon': float(co.group(1)),
                'bands': (int(bd.group(1)), int(bd.group(2))),
            }
        self.assertTrue(site, 'could not parse HELIPORTS out of index.html')

        api = {h['code']: h for h in app.CITY_GEOMETRY['london']['heliports']}
        self.assertEqual(
            set(api), set(site),
            f'heliport sets differ: API only {sorted(set(api) - set(site))}, '
            f'site only {sorted(set(site) - set(api))}',
        )
        for code in sorted(site):
            self.assertAlmostEqual(api[code]['lat'], site[code]['lat'], places=4, msg=f'{code} lat')
            self.assertAlmostEqual(api[code]['lon'], site[code]['lon'], places=4, msg=f'{code} lon')
            self.assertEqual(
                tuple(api[code]['bands']), site[code]['bands'],
                f'{code}: band weights differ between site and API. These are derived '
                'from published movement counts; changing one side alone changes scores '
                'on one surface only.',
            )

    def test_nyc_declares_no_heliports_explicitly(self):
        """An empty list, not a missing key, so a typo fails loudly."""
        self.assertIn('heliports', app.CITY_GEOMETRY['nyc'])
        self.assertEqual(app.CITY_GEOMETRY['nyc']['heliports'], [])

    def test_airports_match_the_site(self):
        """Same guard for the airport list, which feeds the other half of quiet."""
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'index.html')
        src = open(os.path.abspath(path), encoding='utf-8').read()
        i = src.index('const AIRPORTS = [')
        block = src[i:src.index('];', i)]
        site = {
            m.group(1): (float(m.group(3)), float(m.group(2)))
            for m in re.finditer(
                r"code:\s*'([A-Z]{3})'.*?coords:\s*\[\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\]",
                block, re.S,
            )
        }
        api = {a['code']: (a['lat'], a['lon']) for a in app.CITY_GEOMETRY['london']['airports']}
        self.assertEqual(set(api), set(site), 'airport sets differ between site and API')
        for code in sorted(site):
            self.assertAlmostEqual(api[code][0], site[code][0], places=4, msg=f'{code} lat')
            self.assertAlmostEqual(api[code][1], site[code][1], places=4, msg=f'{code} lon')
