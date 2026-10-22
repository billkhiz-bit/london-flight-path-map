"""The San Francisco Bay Area's API contract (release 2, 2026-10-22: the API scores it, the site shows facts).

What only the Bay Area's records can get wrong, held on every one of the 50 cities: a top-coded price is never
published as a price; growth is not scored and says so; a withheld input names itself and its reason and is
credited nowhere; a component below its floor is credited nowhere; the "few residents" note sits beside an
unchanged rate. Plus the request paths the release changed: a Bay Area ZIP, a New York ZIP asked of another
city, a UK postcode in no covered city, and weights that fall only on what a place cannot score.
"""

import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambdas', 'score'))

import app  # noqa: E402

CITY = 'bayarea'
BOROUGHS = app.CITIES[CITY]['boroughs']


def score(borough, **query):
    body, status = app.resolve_query({'city': CITY, 'borough': borough, **query})
    assert status == 200, (borough, status, body)
    return body


class BayAreaContractTests(unittest.TestCase):
    def test_a_top_coded_price_is_never_published_as_a_price(self):
        capped = [b for b, bd in BOROUGHS.items() if bd['priceTopCoded']]
        self.assertTrue(capped)
        for b, bd in BOROUGHS.items():
            ctx = score(b)['context']
            if bd['priceTopCoded']:
                self.assertNotIn('avgPriceUsd', ctx, b)
                self.assertEqual(ctx['avgPriceUsdAtLeast'], app.US_PRICE_TOP_CODE, b)
                self.assertIs(ctx['priceTopCoded'], True)
            else:
                self.assertEqual(ctx['avgPriceUsd'], bd['avgPrice'], b)
                self.assertIs(ctx['priceTopCoded'], False)
        # the floor is the pool's 95th percentile, so a capped city sits at the least affordable end
        for b in capped:
            self.assertEqual(score(b)['components']['afford'], 0.0, b)
        line = score(capped[0])['sourceBreakdown']['afford']
        self.assertNotIn(f'{app.US_PRICE_TOP_CODE + 1:,}', line)  # the encoding never reads as a price

    def test_growth_is_not_scored_and_says_so_under_every_persona(self):
        for persona in app.PERSONAS:
            for b in BOROUGHS:
                body = score(b, persona=persona)
                self.assertNotIn('growth', body['components'], (b, persona))
                self.assertNotIn('growth', body['weights'], (b, persona))
                self.assertAlmostEqual(sum(body['weights'].values()), 1.0, places=5)
                ctx = body['context']
                self.assertEqual(ctx['growthBasis'], 'not scored')
                self.assertNotIn('growthRankInCity', ctx)
                self.assertIn('County', ctx['priceTrendArea'])
                self.assertTrue(any(n.startswith('Growth is not scored here') for n in body['coverage']['notices']))

    def test_a_withheld_input_names_itself_and_is_credited_nowhere(self):
        withheld = {b: bd['withheld'] for b, bd in BOROUGHS.items() if bd.get('withheld')}
        self.assertEqual(len(withheld), 15)
        for b in BOROUGHS:
            body = score(b)
            ctx, notices = body['context'], body['coverage']['notices']
            if b not in withheld:
                self.assertNotIn('inputsWithheld', ctx, b)
                continue
            self.assertEqual(ctx['inputsWithheld'], {app._WITHHELD_INPUT_OF[f]: r for f, r in withheld[b].items()})
            for name, reason in ctx['inputsWithheld'].items():
                self.assertIn(f'{app._INPUT_LABEL[name]} is withheld here: {reason}.', notices)
            if 'flood' in ctx['inputsWithheld']:
                self.assertFalse([s for s in body['sources'] if s.startswith('Flood risk:')], b)

    def test_a_component_below_its_floor_is_scored_and_credited_nowhere(self):
        for b in BOROUGHS:
            body = score(b)
            if 'live' not in body['components']:
                self.assertTrue(body['context']['liveResolution'].startswith('unavailable'), b)
                self.assertTrue(any('NOT scored here' in s for s in body['sources'] if s.startswith('Liveability')), b)
            if 'env' not in body['components']:
                self.assertTrue(body['context']['environmentResolution'].startswith('unavailable'), b)
                self.assertFalse([s for s in body['sources'] if s.startswith(('Road noise:', 'Flood risk:'))], b)

    def test_the_few_residents_note_sits_beside_an_unchanged_rate(self):
        flagged = {b for b, bd in BOROUGHS.items() if bd['crimeFewResidents']}
        self.assertEqual(flagged, {'Colma', 'Emeryville'})
        for b in BOROUGHS:
            self.assertEqual('crimeNote' in score(b)['context'], b in flagged, b)
        plain = copy.deepcopy(BOROUGHS['Colma'])
        plain['crimeFewResidents'] = False
        self.assertEqual(app.live_component_scores(plain, english=False),
                         app.live_component_scores(BOROUGHS['Colma'], english=False))

    def test_no_uk_dataset_is_planned_for_a_us_city(self):
        self.assertNotIn('plannedComponents', score('Palo Alto'))
        self.assertNotIn('plannedComponents', app.resolve_query({'city': 'nyc', 'borough': 'Brooklyn'})[0])
        self.assertIn('plannedComponents', app.resolve_query({'city': 'london', 'borough': 'Hounslow'})[0])


class RequestPathTests(unittest.TestCase):
    def test_a_bay_area_zip_points_to_the_city_name(self):
        body, status = app.resolve_query({'postcode': '94301'})
        self.assertEqual(status, 404)
        self.assertIn('city=bayarea', body['note'])

    def test_a_new_york_zip_asked_of_another_us_city_is_refused(self):
        body, status = app.resolve_query({'postcode': '10001', 'city': 'bayarea'})
        self.assertEqual(status, 404)
        self.assertIn('New York City ZIP', body['error'])

    def test_a_new_york_zip_with_the_default_uk_city_still_scores(self):
        # scripts/score_bulk.py sends city=london on every row: refusing it failed every New York ZIP in a book
        body, status = app.resolve_query({'postcode': '10001', 'city': 'london'})
        self.assertEqual(status, 200)
        self.assertEqual(body['location']['city'], 'nyc')

    def test_a_uk_postcode_in_no_covered_city_says_not_covered_not_london(self):
        original = app.lookup_postcode
        app.lookup_postcode = lambda pc, include_terminated=False: {
            'postcode': 'EX1 1HS', 'admin_district': 'Exeter', '_ladCode': 'E07000041',
            'latitude': 50.72, 'longitude': -3.53, 'region': 'South West'}
        try:
            body, status = app.resolve_query({'postcode': 'EX1 1HS'})
        finally:
            app.lookup_postcode = original
        self.assertEqual(status, 404)
        self.assertTrue(body['error'].startswith('Not covered yet'))
        self.assertNotIn('london', body['error'])
        self.assertEqual(body['supportedCities'], sorted(app.CITIES))

    def test_weights_on_only_what_a_place_cannot_score_are_refused_not_zero(self):
        body, status = app.resolve_query({'city': CITY, 'borough': 'San Francisco',
                                          'weights': 'quiet:0,afford:0,growth:1,live:0'})
        self.assertEqual(status, 400)
        self.assertIn('afford', body['scoredComponents'])
        self.assertNotIn('growth', body['scoredComponents'])


class RecordGuardTests(unittest.TestCase):
    def _city(self, **record):
        cfg = copy.deepcopy(app.CITIES[CITY])
        cfg['usAnchors'] = app.US_CALIFORNIA_ANCHORS  # the guard asks for California's own, not a copy
        cfg['boroughs'] = {'Testville': {**copy.deepcopy(BOROUGHS['Palo Alto']), **record}}
        return {CITY: cfg}

    def test_each_misreadable_record_raises_at_import(self):
        app.validate_us_fields(self._city())  # a sound record passes
        for record, why in (
            ({'crimeRate': 30.0}, 'both'),                                  # a UK and a US field in one slot
            ({'avgPrice': 2_500_000, 'priceTopCoded': True}, 'top-coded'),  # the floor not encoded as the floor
            ({'withheld': {'transport': 'x'}}, 'withheld yet carries'),     # withheld with a value
            ({'transport': None, 'withheld': {'transport': ''}}, 'no reason'),
        ):
            with self.subTest(why=why), self.assertRaisesRegex(ValueError, why):
                app.validate_us_fields(self._city(**record))
        no_anchor = self._city()
        del no_anchor[CITY]['usAnchors']
        with self.assertRaisesRegex(ValueError, "California's anchor"):
            app.validate_us_fields(no_anchor)


if __name__ == '__main__':
    unittest.main()
