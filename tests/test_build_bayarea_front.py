"""The Bay Area's front-page cards (2026-11-07): data/us-bayarea-front.json says what the score engine says.

Bill's call: the cards are scored, from the same records as the full map, never typed. This file holds the
committed file to the engine (every city, every component), to the records builder's words for each input (with
its source and year) and to its US-scales line, and proves the --check red on a hand-edited score. Offline.
"""

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / 'scripts'))
sys.path.insert(0, str(REPO_ROOT / 'backend' / 'lambdas' / 'score'))
SPEC = importlib.util.spec_from_file_location('build_bayarea_front', REPO_ROOT / 'scripts' / 'build_bayarea_front.py')
front = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(front)
import app  # noqa: E402
import build_bayarea_records as records  # noqa: E402


def committed():
    return json.loads(front.OUT.read_text(encoding='utf-8'))


def test_the_file_is_what_the_engine_gives():
    assert front.OUT.read_text(encoding='utf-8').replace('\r\n', '\n') == front.dump(front.document())


def test_every_city_carries_the_engines_score_and_components():
    rows = {r['borough']: r for r in committed()['rows']}
    assert set(rows) == set(app.CITIES['bayarea']['boroughs'])
    for name, row in rows.items():
        body, status = app.resolve_query({'borough': name, 'city': 'bayarea'})
        assert status == 200 and row['score'] == body['score'], name
        for k in ('quiet', 'afford', 'growth', 'live', 'env'):
            assert row[k] == body['components'].get(k, ''), (name, k)
        assert row['growth'] == '', 'growth is not scored for the Bay Area'


def test_the_cards_words_are_the_records_builders():
    doc = committed()
    assert doc['us_scales'] == records.us_scales(len(doc['rows']))
    sources = set(records.input_sources().values())
    for row in doc['rows']:
        assert row['facts'] and all(source in sources for _, _, source in row['facts']), row['borough']


def test_the_check_reds_an_edited_score(tmp_path, monkeypatch, capsys):
    doc = committed()
    doc['rows'][0]['score'] = round(doc['rows'][0]['score'] + 0.1, 1)
    stand_in = tmp_path / 'us-bayarea-front.json'
    stand_in.write_text(front.dump(doc), encoding='utf-8')
    monkeypatch.setattr(front, 'OUT', stand_in)
    monkeypatch.setattr(sys, 'argv', ['build_bayarea_front.py', '--check'])
    assert front.main() == 1
    assert 'stale against the engine' in capsys.readouterr().out
