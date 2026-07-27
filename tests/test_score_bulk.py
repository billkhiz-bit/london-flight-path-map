"""Tests for scripts/score_bulk.py, the offline city-scale bulk scorer.

Offline only: no AWS, no network, no boto3. The scorer imports the score
Lambda lazily inside _load_score_app(), so importing this module at
collection time touches nothing.

WHAT IS ACTUALLY WORTH TESTING HERE. The scoring itself is not — it belongs
to backend/lambdas/score/app.py and is covered by that suite; this script
deliberately owns no scoring logic. What this script owns is the CONTRACT
WITH THE CUSTOMER, and that is where the defects would be invisible and
expensive:

  * every input row appears in the output (the 2026-07-27 decision), because
    a silently short CSV looks complete and is not;
  * a customer's own columns survive, and can never overwrite ours;
  * the `not_found` note never asserts a cause we cannot observe.
"""

import csv
import importlib.util
import io
import os
import sys
import threading

import pytest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), os.pardir))


def _load_script(alias, path):
    if alias in sys.modules:
        return sys.modules[alias]
    spec = importlib.util.spec_from_file_location(alias, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


score_bulk = _load_script(
    "score_bulk", os.path.join(REPO_ROOT, "scripts", "score_bulk.py")
)


# ---------------------------------------------------------------------------
# Response fixtures, shaped exactly as resolve_query returns them. Captured
# from real calls on 2026-07-27 rather than invented, so a change to the API
# body shape breaks these tests instead of silently emptying a column.
# ---------------------------------------------------------------------------

SCORED_BODY = {
    'score': 6.8,
    'components': {'quiet': 10.0, 'afford': 6.7, 'growth': 0.0, 'live': 8.7},
    'context': {
        'avgPriceGbp': 660000,
        'priceTrendPct': -4.2,
        'noiseImpactBand': 'moderate',
        'quietResolution': 'raster',
    },
    'location': {
        'city': 'london',
        'postcode': 'SW11 1AA',
        'borough': 'Wandsworth',
        'latitude': 51.46,
        'longitude': -0.17,
    },
    'methodologyVersion': '3.2',
}

NOT_FOUND_BODY = {'error': 'Postcode not recognised by postcodes.io: BR1 1HB'}

OUTSIDE_BOROUGH_BODY = {
    'error': 'Borough not currently supported in london.',
    'attemptedBorough': None,
    'supportedBoroughs': ['Barnet', 'Camden', 'Wandsworth'],
}

NAMED_BOROUGH_BODY = dict(OUTSIDE_BOROUGH_BODY, attemptedBorough='Slough')

UNSUPPORTED_ZIP_BODY = {
    'error': 'ZIP not currently supported: 99999',
    'note': 'Sky Score supports NYC ZIPs only at present.',
    'supportedNycBoroughs': ['Bronx', 'Brooklyn', 'Manhattan'],
}

BAD_QUERY_BODY = {'error': 'Unsupported city: atlantis', 'supportedCities': ['london']}


class TestClassifyOutcome:
    """The 2026-07-27 decision: emit every row, explain every failure."""

    def test_scored_row_carries_every_component(self):
        row = score_bulk.classify_outcome('SW11 1AA', SCORED_BODY, 200)
        assert row['status'] == 'scored'
        assert row['score'] == 6.8
        assert row['borough'] == 'Wandsworth'
        assert row['matched_postcode'] == 'SW11 1AA'
        assert (row['quiet'], row['afford'], row['growth'], row['live']) == (10.0, 6.7, 0.0, 8.7)
        assert row['quiet_resolution'] == 'raster'
        assert row['methodology_version'] == '3.2'
        assert row['note'] == ''

    def test_nyc_price_lands_in_the_same_column(self):
        """avgPriceUsd and avgPriceGbp share one column; `city` disambiguates.
        A separate column per currency would be empty for most of any book."""
        body = dict(SCORED_BODY, context={'avgPriceUsd': 1_200_000})
        body['location'] = dict(SCORED_BODY['location'], city='nyc')
        row = score_bulk.classify_outcome('10001', body, 200)
        assert row['avg_price_gbp'] == 1_200_000
        assert row['city'] == 'nyc'

    @pytest.mark.parametrize('body,status,expected', [
        (NOT_FOUND_BODY, 404, 'not_found'),
        (OUTSIDE_BOROUGH_BODY, 404, 'outside_supported_boroughs'),
        (UNSUPPORTED_ZIP_BODY, 404, 'unsupported_zip'),
        (BAD_QUERY_BODY, 400, 'invalid_query'),
        ({'error': 'TypeError: boom'}, 500, 'error'),
    ])
    def test_every_failure_shape_gets_its_own_status(self, body, status, expected):
        row = score_bulk.classify_outcome('X', body, status)
        assert row['status'] == expected
        assert row['note'], 'an unscored row with no explanation is the failure mode'

    def test_not_found_note_never_asserts_termination(self):
        """A 404 for a retired postcode is byte-identical to one that never
        existed — the wording is a deliberate public API surface (audit L5) and
        resolve_query does not tell us which occurred. The note may SUGGEST a
        retired postcode; asserting it would be a claim we cannot observe."""
        note = score_bulk.classify_outcome('BR1 1HB', NOT_FOUND_BODY, 404)['note']
        assert 'may be a retired postcode' in note
        assert '--include-terminated' in note, 'tell them how to find out'
        assert not note.startswith('Terminated')

    def test_unmapped_district_does_not_print_none_at_a_customer(self):
        row = score_bulk.classify_outcome('EH1 1YZ', OUTSIDE_BOROUGH_BODY, 404)
        assert 'None' not in row['note']
        assert row['borough'] == ''

    def test_named_district_is_named(self):
        row = score_bulk.classify_outcome('SL1 1AA', NAMED_BOROUGH_BODY, 404)
        assert 'Slough' in row['note']
        assert row['borough'] == 'Slough'

    def test_no_outcome_ever_omits_the_row(self):
        """classify_outcome may return None to drop a row. Under the 27 Jul
        decision nothing does — this guards a later edit from quietly
        reintroducing option (a)."""
        for body, status in [
            (SCORED_BODY, 200), (NOT_FOUND_BODY, 404), (OUTSIDE_BOROUGH_BODY, 404),
            (UNSUPPORTED_ZIP_BODY, 404), (BAD_QUERY_BODY, 400),
        ]:
            assert score_bulk.classify_outcome('X', body, status) is not None

    def test_keys_are_all_declared_columns(self):
        """A key outside OUTPUT_COLUMNS is silently dropped by DictWriter
        (extrasaction='ignore'), so a typo here empties a column with no error."""
        row = score_bulk.classify_outcome('SW11 1AA', SCORED_BODY, 200)
        assert set(row) <= set(score_bulk.OUTPUT_COLUMNS)


class TestReadPostcodes:
    """Input handling. A book arrives as whatever the customer exports."""

    def _write(self, tmp_path, name, text):
        path = tmp_path / name
        path.write_text(text, encoding='utf-8')
        return path

    def test_plain_text_one_per_line(self, tmp_path):
        path = self._write(tmp_path, 'book.txt', 'SW11 1AA\n\nE1 6AN\n\n')
        extra, rows = score_bulk.read_postcodes(path)
        assert extra == []
        assert [pc for _n, pc, _p in rows] == ['SW11 1AA', 'E1 6AN']

    def test_csv_postcode_column_is_found_case_insensitively(self, tmp_path):
        path = self._write(tmp_path, 'book.csv', 'Ref,POSTCODE\nP-1,SW11 1AA\n')
        extra, rows = score_bulk.read_postcodes(path)
        assert extra == ['Ref']
        assert [pc for _n, pc, _p in rows] == ['SW11 1AA']

    def test_customer_columns_are_carried_through(self, tmp_path):
        path = self._write(
            tmp_path, 'book.csv',
            'property_ref,postcode,tenure\nP-001,SW11 1AA,Freehold\n')
        extra, rows = score_bulk.read_postcodes(path)
        assert extra == ['property_ref', 'tenure']
        _n, _pc, passthrough = next(iter(rows))
        assert passthrough == {'property_ref': 'P-001', 'tenure': 'Freehold'}

    def test_colliding_column_is_renamed_not_dropped(self, tmp_path):
        """A customer column called `score` must neither overwrite the computed
        score nor vanish. It becomes src_score."""
        path = self._write(tmp_path, 'book.csv', 'postcode,score\nSW11 1AA,THEIRS\n')
        extra, rows = score_bulk.read_postcodes(path)
        assert extra == ['src_score']
        _n, _pc, passthrough = next(iter(rows))
        assert passthrough == {'src_score': 'THEIRS'}
        assert 'score' not in passthrough

    def test_bom_does_not_hide_the_header(self, tmp_path):
        """Excel writes UTF-8 with BOM by default, and a book almost always
        comes out of Excel. A BOM on the first header cell would make the
        postcode column unfindable and silently reroute to plain-text mode."""
        path = tmp_path / 'book.csv'
        path.write_text('postcode,ref\nSW11 1AA,P-1\n', encoding='utf-8-sig')
        extra, rows = score_bulk.read_postcodes(path)
        assert extra == ['ref']
        assert [pc for _n, pc, _p in rows] == ['SW11 1AA']

    def test_rows_with_a_blank_postcode_are_skipped(self, tmp_path):
        path = self._write(
            tmp_path, 'book.csv', 'postcode,ref\nSW11 1AA,P-1\n,P-2\nE1 6AN,P-3\n')
        _extra, rows = score_bulk.read_postcodes(path)
        assert [pc for _n, pc, _p in rows] == ['SW11 1AA', 'E1 6AN']


class _FakeApp:
    """Stands in for the score Lambda. Returns a canned (body, status) per
    postcode, and raises for one specific input so the run-survives-a-bad-row
    guarantee is exercised rather than assumed."""

    def __init__(self, responses, explode=None):
        self.responses = responses
        self.explode = explode
        self.calls = []

    def resolve_query(self, query):
        postcode = query['postcode']
        self.calls.append(query)
        if postcode == self.explode:
            raise RuntimeError('upstream exploded')
        return self.responses.get(postcode, (NOT_FOUND_BODY, 404))


class TestScoreBook:
    """End-to-end over the writer, with the engine stubbed."""

    def _run(self, app, rows, fieldnames=None):
        sink = io.StringIO()
        writer = csv.DictWriter(
            sink, fieldnames=fieldnames or score_bulk.OUTPUT_COLUMNS,
            extrasaction='ignore')
        writer.writeheader()
        counters = score_bulk.score_book(
            app, rows, writer, threading.Lock(), workers=2, progress=False)
        sink.seek(0)
        return counters, list(csv.DictReader(sink))

    def test_every_input_row_reaches_the_output(self):
        """THE invariant behind the 27 Jul decision. A customer must be able to
        reconcile our CSV against theirs row for row."""
        app = _FakeApp({'SW11 1AA': (SCORED_BODY, 200)})
        rows = [(i, pc, {}) for i, pc in enumerate(
            ['SW11 1AA', 'BR1 1HB', 'EH1 1YZ', 'ZZ99 9ZZ'], start=1)]
        counters, out = self._run(app, rows)
        assert len(out) == 4
        assert counters['scored'] == 1
        assert counters['failed'] == 3
        assert counters['omitted'] == 0
        assert {r['input_postcode'] for r in out} == {
            'SW11 1AA', 'BR1 1HB', 'EH1 1YZ', 'ZZ99 9ZZ'}

    def test_one_exploding_row_does_not_kill_the_run(self):
        """A 100k run must not lose 99,999 good rows to one bad one. The failure
        is recorded as a row, not swallowed."""
        app = _FakeApp({'SW11 1AA': (SCORED_BODY, 200)}, explode='E1 6AN')
        rows = [(1, 'SW11 1AA', {}), (2, 'E1 6AN', {}), (3, 'SW11 1AA', {})]
        counters, out = self._run(app, rows)
        assert len(out) == 3
        assert counters['scored'] == 2
        exploded = next(r for r in out if r['input_postcode'] == 'E1 6AN')
        assert exploded['status'] == 'error'
        assert 'RuntimeError' in exploded['note']

    def test_passthrough_cannot_overwrite_a_computed_column(self):
        """read_postcodes renames collisions, but score_book applies passthrough
        after classify_outcome — so if that renaming ever regressed, the
        customer's value would land in our column. Pin the ordering guarantee."""
        app = _FakeApp({'SW11 1AA': (SCORED_BODY, 200)})
        rows = [(1, 'SW11 1AA', {'src_score': 'THEIRS', 'ref': 'P-1'})]
        _c, out = self._run(
            app, rows, fieldnames=score_bulk.OUTPUT_COLUMNS + ['src_score', 'ref'])
        assert out[0]['score'] == '6.8'
        assert out[0]['src_score'] == 'THEIRS'
        assert out[0]['ref'] == 'P-1'

    def test_query_defaults_reach_the_engine(self):
        """persona / city / includeTerminated are set once in main() and read by
        the worker closure. A regression there would silently score every book
        as 'balanced' in London regardless of the flags."""
        app = _FakeApp({'SW11 1AA': (SCORED_BODY, 200)})
        original = dict(score_bulk.app_query_defaults)
        try:
            score_bulk.app_query_defaults.update(
                {'persona': 'family', 'city': 'london', 'includeTerminated': True})
            self._run(app, [(1, 'SW11 1AA', {})])
        finally:
            score_bulk.app_query_defaults.clear()
            score_bulk.app_query_defaults.update(original)
        assert app.calls[0]['persona'] == 'family'
        assert app.calls[0]['includeTerminated'] is True
