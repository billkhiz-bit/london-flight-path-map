"""Per-field provenance (2026-10-23): every value a response carries says which source answered, how that source
made it, at what resolution and for what period.

The fixtures are LIVE responses captured on 2026-10-23 from the API (before provenance existed): London at all three
quiet tiers (raster TW3 4LB, geometry EC1A 1BB, the Hounslow borough band), Manchester, Cardiff, Norwich, Teesside,
New York and /v1/environment. Captured, not written, so a rule is tested against what the API really says
(feedback: self-authored fixtures are circular). The periods are held to the loaders by tests/test_provenance_periods.py.

`score-bayarea-city.json` (Palo Alto) is the one exception: the API does not score the Bay Area live yet (release 2
deploys after 2026-10-29), so it is this branch's own `resolve_query` output, captured the same day. It is here
because without it the Bay Area's aircraft line matched NEW YORK's pattern and Palo Alto would have credited the
Port Authority's monitors, and seven of its ten credit lines matched nothing.
"""

import copy
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambdas', 'score'))

import app  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'provenance'
UK_BODIES = ('hmlr-', 'ons-', 'defra-', 'ea-', 'dfe-', 'dft-', 'nhs-', 'uk-aip', 'postcodes-io')


def fixtures():
    return {f.stem: json.loads(f.read_text(encoding='utf-8')) for f in sorted(FIXTURES.glob('*.json'))}


class EveryValueHasItsSource(unittest.TestCase):
    def test_the_fixtures_are_all_there(self):
        self.assertEqual(len(fixtures()), 10)

    def test_every_credit_line_is_known(self):
        unknown = {(name, line[:60]) for name, body in fixtures().items()
                   for line in body.get('sources', []) if isinstance(line, str) and app.provenance_line_ids(line) is None}
        self.assertEqual(unknown, set())

    def test_every_value_names_a_source_and_a_method(self):
        empty = set()
        for name, body in fixtures().items():
            prov, _ = app.build_provenance(body)
            empty |= {(name, k) for k, e in prov.items() if not e.get('sources') or e.get('method') not in app.PROVENANCE_METHODS}
        self.assertEqual(empty, set())

    def test_every_value_in_the_body_has_an_entry(self):
        # The SET of value fields a body carries == the set provenance describes: a new context field with no rule
        # shows up here by name instead of going out uncredited.
        for name, body in fixtures().items():
            prov, _ = app.build_provenance(body)
            section = 'context' if 'context' in body else 'environment'
            values = {f'{section}.{k}' for k in body[section]
                      if not k.endswith(('Source', 'Resolution', 'Coverage')) and k not in app._DESCRIBES_ITSELF}
            values |= {f'components.{k}' for k in body.get('components', {})}
            values |= {'score'} if 'score' in body else set()
            self.assertEqual(values - set(prov), set(), name)

    def test_the_index_holds_exactly_the_sources_used(self):
        for name, body in fixtures().items():
            prov, index = app.build_provenance(body)
            used = {i for e in prov.values() for i in e['sources'] + [e.get('fittedTo')] if i}
            self.assertEqual(set(index), used, name)
            self.assertTrue(set(index) <= set(app.PROVENANCE_SOURCES), name)


class ItCreditsWhatAnswered(unittest.TestCase):
    def test_a_raster_postcode_credits_defra_alone_for_quiet(self):
        # TW3 4LB's `sources` also lists the UK AIP, which did not answer here.
        prov, _ = app.build_provenance(fixtures()['score-london-raster'])
        self.assertEqual(prov['components.quiet'], {'sources': ['defra-noise-aircraft'], 'method': 'derived', 'basis': 'raster'})

    def test_the_geometry_tier_is_an_estimate_fitted_to_defra(self):
        prov, _ = app.build_provenance(fixtures()['score-teesside'])
        self.assertEqual(prov['components.quiet']['method'], 'estimated')
        self.assertEqual(prov['components.quiet']['fittedTo'], 'defra-noise-aircraft')
        self.assertNotIn('defra-noise-aircraft', prov['components.quiet']['sources'])

    def test_new_york_credits_no_uk_body(self):
        _, index = app.build_provenance(fixtures()['score-nyc-zip'])
        self.assertEqual({i for i in index if i.startswith(UK_BODIES)}, set())

    def test_each_us_metro_credits_its_own_aircraft_estimate(self):
        # The Bay Area's line once matched New York's pattern ("ESTIMATED from the FAA..."), crediting Palo Alto's
        # Quiet Skies to the Port Authority's monitors. Each metro names only its own.
        _, nyc = app.build_provenance(fixtures()['score-nyc-zip'])
        _, bay = app.build_provenance(fixtures()['score-bayarea-city'])
        self.assertEqual({i for i in nyc if i.endswith('-faa-estimate')}, {'nyc-faa-estimate'})
        self.assertEqual({i for i in bay if i.endswith('-faa-estimate')}, {'bayarea-faa-estimate'})
        self.assertEqual({i for i in bay if i.startswith(UK_BODIES + ('nyc-', 'nypd-'))}, set())

    def test_a_bay_area_trend_credits_its_own_county_index(self):
        prov, _ = app.build_provenance(fixtures()['score-bayarea-city'])
        self.assertEqual(prov['context.priceTrendPct']['sources'], ['fhfa-hpi'])
        self.assertEqual(prov['context.avgPriceUsdAtLeast']['sources'], ['census-acs-b25077'])

    def test_defra_and_the_ea_are_modelled_and_nothing_in_a_score_is_measured(self):
        # Only an instrument's reading is "measured"; /v1/score serves none today (AURN and Breathe London are
        # display only). When one is scored, this test changes WITH the methodology, on purpose.
        for name, body in fixtures().items():
            prov, index = app.build_provenance(body)
            self.assertFalse(any(e.get('method') == 'measured' for e in prov.values()), name)
            for i in index:
                if i.startswith(('defra-', 'ea-')):
                    self.assertEqual(index[i]['method'], 'modelled', i)

    def test_a_period_agrees_with_the_line_the_same_response_carries(self):
        # The prose beside a figure and its provenance are two holders of one year: they must not disagree.
        pairs = (('roadNoiseLdenDb', 'roadNoiseSource'), ('no2AnnualMeanUgm3', 'airQualitySource'),
                 ('aircraftNoiseLdenDb', 'aircraftNoiseSource'))
        checked = 0
        for name, body in fixtures().items():
            prov, _ = app.build_provenance(body)
            section = 'context' if 'context' in body else 'environment'
            for value, line in pairs:
                if value in body[section]:
                    self.assertIn(prov[f'{section}.{value}']['period'], body[section][line], (name, value))
                    checked += 1
        self.assertGreater(checked, 5)


class ItDescribesOnlyWhatWasSent(unittest.TestCase):
    def test_an_include_filter_drops_the_provenance_of_what_it_drops(self):
        body = copy.deepcopy(fixtures()['score-london-raster'])
        full, _ = app.build_provenance(body)
        sent = app.with_provenance(body, app.filter_response(body, {'score'}))
        self.assertEqual(set(sent['provenance']), {'score'})
        # The headline still credits what its components came from, though the components were not sent.
        self.assertEqual(sent['provenance']['score'], full['score'])
        self.assertTrue(sent['provenance']['score']['sources'])
        self.assertEqual(set(sent['sourceIndex']), set(full['score']['sources']))

    def test_provenance_and_the_index_can_be_asked_for_by_name(self):
        self.assertTrue({'provenance', 'sourceIndex'} <= app.RESPONSE_FIELDS)

    def test_existing_fields_are_untouched(self):
        body = fixtures()['score-london-raster']
        before = copy.deepcopy(body)
        after = app.with_provenance(copy.deepcopy(body))
        self.assertEqual({k: v for k, v in after.items() if k not in ('provenance', 'sourceIndex')}, before)



class ABatchCarriesOneIndex(unittest.TestCase):
    def test_the_index_is_lifted_to_the_top_and_every_id_resolves_there(self):
        answers = [app.with_provenance(copy.deepcopy(fixtures()[n])) for n in ('score-london-raster', 'score-nyc-zip')]
        queue = iter(answers)
        with patch.object(app, 'resolve_query', side_effect=lambda q: (copy.deepcopy(next(queue)), 200)):
            event = {'httpMethod': 'POST', 'body': json.dumps({'queries': [{'postcode': 'TW3 4LB'}, {'zip': '10001'}]})}
            body = json.loads(app.handle_batch(event, None)['body'])
        self.assertEqual(body['successCount'], 2)
        self.assertEqual([r for r in body['results'] if 'sourceIndex' in r], [])
        used = {i for r in body['results'] for e in r['provenance'].values() for i in e['sources'] + [e.get('fittedTo')] if i}
        self.assertEqual(set(body['sourceIndex']), used)
        self.assertEqual(body['sourceIndex'], {**answers[0]['sourceIndex'], **answers[1]['sourceIndex']})



class TheSpecSaysTheSameWords(unittest.TestCase):
    def test_the_method_enums_in_the_api_reference_are_the_lambdas(self):
        import yaml  # noqa: PLC0415 - only this test reads the spec
        spec = Path(__file__).resolve().parents[2] / 'score-demo' / 'openapi.yaml'
        schemas = yaml.safe_load(spec.read_text(encoding='utf-8'))['components']['schemas']
        for name in ('ProvenanceEntry', 'Source'):
            self.assertEqual(set(schemas[name]['properties']['method']['enum']), set(app.PROVENANCE_METHODS), name)


if __name__ == '__main__':
    unittest.main()
