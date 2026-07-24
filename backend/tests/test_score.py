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
import sys
import unittest

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
        # Wandsworth's growth signal died between vintages — the score
        # change must be negative under identical (v3.2) formula rules.
        self.assertLess(comp['scoreChange'], 0)

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

    def test_changes_routed_from_handler(self):
        resp = app.handler({'httpMethod': 'GET', 'path': '/v1/changes'}, None)
        self.assertEqual(resp['statusCode'], 200)
        self.assertIn('changes', json.loads(resp['body']))


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
        # Pinned to the 2026-Q2 (May 2026 UK HPI) snapshot + methodology
        # v3.2 growth clamp. Wandsworth's trend is negative this vintage,
        # so growth floors at 0.
        weights = app.PERSONAS['balanced']
        result = app.calc_score('Wandsworth', 'london', weights)
        self.assertEqual(result['score'], 5.3)
        self.assertEqual(result['components']['quiet'], 5.0)
        self.assertEqual(result['components']['afford'], 6.7)
        self.assertEqual(result['components']['growth'], 0.0)
        self.assertEqual(result['components']['live'], 8.7)
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


if __name__ == '__main__':
    unittest.main()
