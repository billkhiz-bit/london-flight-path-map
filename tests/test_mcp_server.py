"""Tests for mcp-server/sky_score_mcp.py, the local MCP server over the live API (2026-10-22).

Offline: the network is stubbed at urlopen, so these hold what the server sends and what it says, not the API.
Every tool is read-only; the key travels only in the X-Api-Key header and never appears in an error; bad input
is refused before a request is made; an uncovered place is said to be NOT COVERED YET, never scored; compare
asks once per place and carries every source; and the server's instructions keep the product's wording rules.
"""

import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / 'mcp-server'))
import sky_score_mcp as s  # noqa: E402
from mcp.shared.memory import create_connected_server_and_client_session  # noqa: E402

FAKE_KEY = 'k' * 40


class Wire:
    """A stub for urlopen: records each request and answers from a queue of (status, body)."""

    def __init__(self, *answers):
        self.answers, self.requests = list(answers), []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        status, body = self.answers.pop(0)
        raw = json.dumps(body).encode()
        if status >= 400:
            raise urllib.error.HTTPError(req.full_url, status, 'error', {}, io.BytesIO(raw))
        return io.BytesIO(raw)


REGIONS = {'cities': [
    {'id': 'london', 'boroughs': ['Hounslow', 'Kensington and Chelsea']},
    {'id': 'manchester', 'boroughs': ['Salford', 'Trafford']},
    {'id': 'teesside', 'boroughs': ['Stockton-on-Tees']},
    {'id': 'elsewhere', 'boroughs': ['Trafford']},  # a name two cities share
]}


@pytest.fixture
def wire(monkeypatch):
    monkeypatch.setenv(s.KEY_VAR, FAKE_KEY)
    monkeypatch.setattr(s, '_regions', None)  # read once a session: each test is its own session

    def install(*answers):
        w = Wire(*answers)
        monkeypatch.setattr(s.urllib.request, 'urlopen', w)
        return w
    return install


@pytest.fixture
def anyio_backend():
    return 'asyncio'


async def call(tool, args):
    async with create_connected_server_and_client_session(s.mcp._mcp_server) as c:
        return await c.call_tool(tool, args)


def text(result):
    return ' '.join(c.text for c in result.content if hasattr(c, 'text'))


SCORE = {'score': 4.1, 'components': {'quiet': {'score': 3.2}}, 'sources': ['UK AIP (NATS)', 'DfT NaPTAN']}


@pytest.mark.anyio
async def test_every_tool_is_read_only():
    async with create_connected_server_and_client_session(s.mcp._mcp_server) as c:
        tools = (await c.list_tools()).tools
    assert {t.name for t in tools} == {'score_area', 'compare_areas', 'list_regions', 'score_changes', 'environment_at'}
    assert all(t.annotations.readOnlyHint and not t.annotations.destructiveHint for t in tools)


@pytest.mark.anyio
async def test_a_postcode_is_scored_with_the_key_in_the_header_only(wire):
    w = wire((200, SCORE))
    r = await call('score_area', {'place': 'tw9 3pz', 'persona': 'family'})
    assert not r.isError and r.structuredContent == SCORE
    req = w.requests[0]
    assert req.full_url.startswith(s.API_BASE + '/v1/score?')
    assert 'postcode=TW9+3PZ' in req.full_url and 'persona=family' in req.full_url
    # the key rides only on this request, never on a redirect to wherever it points
    assert req.unredirected_hdrs.get('X-api-key') == FAKE_KEY and 'X-api-key' not in req.headers
    assert FAKE_KEY not in req.full_url


@pytest.mark.anyio
async def test_a_name_is_asked_for_as_a_borough(wire):
    w = wire((200, REGIONS), (200, SCORE))
    await call('score_area', {'place': 'Stockton-on-Tees', 'city': 'teesside', 'compare_previous': True})
    url = w.requests[1].full_url
    assert 'borough=Stockton-on-Tees' in url and 'city=teesside' in url and 'compare=previous' in url
    assert 'postcode=' not in url


@pytest.mark.anyio
async def test_a_borough_with_no_city_is_asked_in_the_city_that_lists_it(wire):
    # the API defaults to London, so Salford asked without its city read NOT COVERED YET (code review)
    w = wire((200, REGIONS), (200, SCORE))
    r = await call('score_area', {'place': 'salford'})
    assert not r.isError and 'city=manchester' in w.requests[1].full_url
    assert w.requests[0].full_url.endswith('/v1/regions') and w.requests[0].get_header('X-api-key') is None


@pytest.mark.anyio
async def test_a_postcode_never_carries_a_city(wire):
    w = wire((200, SCORE))
    await call('score_area', {'place': 'SW11 1AA', 'city': 'manchester'})
    assert 'city=' not in w.requests[0].full_url


@pytest.mark.anyio
async def test_a_name_two_cities_share_asks_which_and_scores_nothing(wire):
    w = wire((200, REGIONS))
    r = await call('score_area', {'place': 'Trafford'})
    assert r.isError and 'manchester' in text(r) and 'elsewhere' in text(r) and len(w.requests) == 1


@pytest.mark.anyio
async def test_a_listed_borough_asked_in_the_wrong_city_is_never_not_covered(wire):
    wire((200, REGIONS), (404, {'error': 'Borough not currently supported in london.'}))
    r = await call('score_area', {'place': 'Salford', 'city': 'london'})
    assert r.isError and 'NOT COVERED YET' not in text(r) and 'manchester' in text(r)


@pytest.mark.anyio
async def test_a_name_no_city_lists_is_not_covered_yet(wire):
    wire((200, REGIONS), (404, {'error': 'Borough not currently supported in london.'}))
    r = await call('score_area', {'place': 'Exeter'})
    assert r.isError and 'NOT COVERED YET' in text(r)


@pytest.mark.anyio
async def test_compare_takes_boroughs_from_different_cities(wire):
    w = wire((200, REGIONS), (200, SCORE), (200, {**SCORE, 'score': 6.0}))
    r = await call('compare_areas', {'places': ['Hounslow', 'Salford']})
    assert not r.isError
    assert 'city=london' in w.requests[1].full_url and 'city=manchester' in w.requests[2].full_url


@pytest.mark.anyio
async def test_compares_city_settles_only_a_shared_name(wire):
    w = wire((200, REGIONS), (200, SCORE), (200, SCORE))
    r = await call('compare_areas', {'places': ['Hounslow', 'Trafford'], 'city': 'manchester'})
    assert not r.isError
    assert 'city=london' in w.requests[1].full_url and 'city=manchester' in w.requests[2].full_url


@pytest.mark.anyio
@pytest.mark.parametrize('args', [
    {'place': 'DROP TABLE; --'},
    {'place': '<script>'},
    {'place': 'SW11 1AA', 'city': '../admin'},
    {'place': 'x' * 80},
])
async def test_bad_input_is_refused_before_any_request(wire, args):
    w = wire()
    r = await call('score_area', args)
    assert r.isError and w.requests == []


@pytest.mark.anyio
async def test_an_uncovered_place_is_not_covered_yet_never_a_score(wire):
    wire((404, {'error': 'Borough not currently supported in london.'}))
    r = await call('score_area', {'place': 'EX1 1HS'})
    assert r.isError and 'NOT COVERED YET' in text(r) and 'no score' in text(r)


@pytest.mark.anyio
@pytest.mark.parametrize('status, body', [
    (403, {'message': f'Forbidden for key {FAKE_KEY}'}),  # an API that echoed the key must not leak it here
    (429, {}),
    (500, {'error': 'internal'}),
    (502, None),  # a JSON body that is not an object still reports the status
    (503, ['busy']),
])
async def test_an_api_error_is_a_tool_error_and_never_carries_the_key(wire, status, body):
    wire((status, body))
    r = await call('score_area', {'place': 'SW11 1AA'})
    assert r.isError and str(status) in text(r)
    assert FAKE_KEY not in text(r)


@pytest.mark.anyio
async def test_a_missing_key_says_what_to_set_and_makes_no_request(wire, monkeypatch):
    w = wire()
    monkeypatch.delenv(s.KEY_VAR)
    monkeypatch.setattr(s, 'REPO', Path('/nonexistent'))
    r = await call('score_area', {'place': 'SW11 1AA'})
    assert r.isError and s.KEY_VAR in text(r) and w.requests == []


@pytest.mark.anyio
async def test_compare_asks_once_a_place_and_carries_every_source(wire):
    other = {**SCORE, 'score': 5.1, 'sources': ['DfT NaPTAN', 'ONS NSPL']}
    w = wire((200, SCORE), (200, other))
    r = await call('compare_areas', {'places': ['TW9 3PZ', 'SW11 1AA']})
    d = r.structuredContent
    assert [p['score'] for p in d['places']] == [4.1, 5.1] and len(w.requests) == 2
    assert d['sources'] == ['UK AIP (NATS)', 'DfT NaPTAN', 'ONS NSPL']


@pytest.mark.anyio
@pytest.mark.parametrize('places', [['TW9 3PZ'], ['A1 1AA', 'B1 1AA', 'C1 1AA', 'D1 1AA', 'E1 1AA', 'F1 1AA']])
async def test_compare_takes_two_to_five(wire, places):
    w = wire()
    r = await call('compare_areas', {'places': places})
    assert r.isError and w.requests == []


@pytest.mark.anyio
async def test_the_open_endpoints_send_no_key(wire):
    w = wire((200, {'cities': {}}), (200, {'boroughs': []}), (200, {'environment': {}}))
    await call('list_regions', {})
    await call('score_changes', {})
    await call('environment_at', {'lat': 51.46, 'lon': -0.30})
    assert [r.get_header('X-api-key') for r in w.requests] == [None, None, None]
    assert w.requests[2].full_url.endswith('/v1/environment?lat=51.460000&lon=-0.300000')


@pytest.mark.anyio
async def test_a_coordinate_off_the_globe_is_refused(wire):
    w = wire()
    r = await call('environment_at', {'lat': 95, 'lon': 0})
    assert r.isError and w.requests == []


def test_the_instructions_keep_the_wording_rules():
    rules = s.INSTRUCTIONS
    for phrase in ('ESTIMATE', 'how OFTEN', 'POSTCODES', 'never fill the gap', 'sources', 'UK AIP (NATS)',
                   '"as is"', 'not advice'):
        assert phrase in rules, phrase


def test_the_key_is_read_from_dotenv_when_not_in_the_environment(tmp_path, monkeypatch):
    monkeypatch.delenv(s.KEY_VAR, raising=False)
    (tmp_path / '.env').write_text(f'OTHER=x\n{s.KEY_VAR}={FAKE_KEY}\n', encoding='utf-8')
    monkeypatch.setattr(s, 'REPO', tmp_path)
    assert s.api_key() == FAKE_KEY


# --- the audit of 2026-10-22 ---------------------------------------------------------------------------------

def test_loose_names_mirror_the_api():
    # The server finds a city by the API's own loose key, or it asks the wrong city: held against the Lambda's
    # function over every borough it serves and the spellings ONS and postcodes.io use.
    sys.path.insert(0, str(REPO_ROOT / 'backend' / 'lambdas' / 'score'))
    import app  # noqa: E402
    names = [b for cfg in app.CITIES.values() for b in cfg['boroughs']]
    names += ['Bristol', 'Bristol, City of', 'Nottingham', 'the Wirral', 'St. Helens', 'Stockton-on-Tees', 'Palo Alto']
    for name in names:
        assert s.loose(name) == app._norm_borough_key(name), name


@pytest.mark.anyio
async def test_a_name_the_api_would_find_finds_its_city(wire):
    regions = {'cities': [*REGIONS['cities'], {'id': 'bristol', 'boroughs': ['City of Bristol']},
                          {'id': 'bayarea', 'boroughs': ['Palo Alto']}]}
    w = wire((200, regions), (200, SCORE), (200, SCORE))
    r = await call('score_area', {'place': 'Bristol'})
    assert not r.isError and 'city=bristol' in w.requests[1].full_url
    r = await call('score_area', {'place': 'Palo Alto'})
    assert not r.isError and 'city=bayarea' in w.requests[2].full_url


@pytest.mark.anyio
async def test_compare_rows_keep_coverage_and_weights(wire):
    # the coverage notices are how Claude learns an input is withheld; a comparison must not drop them
    scored = {**SCORE, 'weights': {'quiet': 0.5}, 'coverage': {'notices': ['Flood risk is withheld here: x.']}}
    wire((200, scored), (200, scored))
    d = (await call('compare_areas', {'places': ['TW9 3PZ', 'SW11 1AA']})).structuredContent
    assert all(p['coverage']['notices'] and p['weights'] for p in d['places'])


@pytest.mark.anyio
@pytest.mark.parametrize('base', ['http://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod',
                                  'https://localhost:9000', 'https://stage.example.com'])
async def test_the_key_goes_only_to_the_api_over_https(wire, monkeypatch, base):
    monkeypatch.setattr(s, 'API_BASE', base)
    w = wire()
    r = await call('score_area', {'place': 'SW11 1AA'})
    assert r.isError and 'not sent' in text(r) and w.requests == []


@pytest.mark.anyio
async def test_a_refusal_with_a_way_round_says_it_and_not_not_covered(wire):
    # a Bay Area ZIP: the API refuses it but scores the city by name, so "NOT COVERED YET" would be false
    wire((404, {'error': 'ZIP not currently supported: 94301',
                'note': 'San Francisco Bay Area cities are scored by name: borough=<city>&city=bayarea.'}))
    r = await call('score_area', {'place': '94301'})
    assert r.isError and 'scored by name' in text(r) and 'NOT COVERED YET' not in text(r)
