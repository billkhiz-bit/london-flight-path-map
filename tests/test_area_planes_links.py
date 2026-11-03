"""Each area page links the planes overhead pages of the districts it covers (2026-11-01).

`scripts/build_area_pages.py` reads `data/planes-districts-by-council.json`, which `scripts/build_planes_pages.py`
writes (council_index), and adds a "Planes overhead" block of links to each borough page. What is held here:
  - the block links each district's page, lower case, in the index's order, and names no figure (an area page
    never says how often planes pass: tests/test_public_wording.py's own patterns are run on it);
  - it is keyed on the ONS council code, never the borough's name;
  - a borough no district page covers gets no block at all, and its page is byte-identical to one built before
    the block existed (so its sitemap date does not move);
  - the sitemap dates a page by the day its change reached master: a page merged from a branch was dated by the
    branch commit, the day it was written (/area/ read 26 Oct for tables that went live on 31 Oct).

    python -m pytest tests/test_area_planes_links.py
"""

import importlib.util
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pages = _load('build_area_pages', REPO_ROOT / 'scripts' / 'build_area_pages.py')
wording = _load('test_public_wording', REPO_ROOT / 'tests' / 'test_public_wording.py')

HOUNSLOW = 'E09000018'


@pytest.fixture
def index(monkeypatch):
    """Point the builder at a made-up index instead of the tracked one (with no consultation, unless given)."""
    def use(councils, consultation=None):
        whole = {'councils': councils} | ({'consultation': consultation} if consultation else {})
        monkeypatch.setattr(pages, '_planes_index', lambda: whole)
        monkeypatch.setattr(pages, '_planes_by_council', lambda: councils)
    return use


PACK = {'airport': 'LHR', 'until': '2026-12-22', 'hub': '/planes-overhead/heathrow-consultation/',
        'councils': {HOUNSLOW: '/planes-overhead/heathrow-consultation/hounslow/'}}


def test_a_council_in_the_pack_links_its_own_pack_page_while_the_consultation_is_open(index):
    # Bill, 2026-11-02: "make the links clear and easy to navigate". Until then the pack was reached only from the
    # planes index; the area page now says the consultation is open and goes straight to the council's own page.
    index({HOUNSLOW: ['TW3']}, PACK)
    line = pages.consultation_line('london', 'Hounslow', today='2026-11-02')
    assert re.findall(r'href="([^"]+)"', line) == ['/planes-overhead/heathrow-consultation/hounslow/']
    assert 'open until 22 December 2026' in line
    assert pages.consultation_line('london', 'Hounslow', today='2026-12-22')  # its last day still offers it
    assert pages.consultation_line('london', 'Hounslow', today='2026-12-23') == ''  # closed: never offered
    assert pages.consultation_line('london', 'Ealing', today='2026-11-02') == ''  # no page in the pack, no link
    for pattern in wording.FREQUENCY:
        assert not re.search(pattern, line, re.IGNORECASE), pattern


def test_no_consultation_in_the_index_means_no_line(index):
    index({HOUNSLOW: ['TW3']})
    assert pages.consultation_line('london', 'Hounslow', today='2026-11-02') == ''


def test_the_block_links_each_district_in_the_index_order(index):
    index({HOUNSLOW: ['TW3', 'TW14', 'UB2']})
    block = pages.planes_section('london', 'Hounslow')
    assert block.startswith('<h2>Planes overhead</h2>\n')
    hrefs = re.findall(r'href="([^"]+)"', block)
    assert hrefs == ['/planes-overhead/tw3/', '/planes-overhead/tw14/', '/planes-overhead/ub2/']
    assert 'Hounslow' in block


def test_the_block_never_says_how_often_planes_pass(index):
    index({HOUNSLOW: ['TW3', 'TW14']})
    block = pages.planes_section('london', 'Hounslow')
    for pattern in wording.FREQUENCY:
        assert not re.search(pattern, block, re.IGNORECASE), pattern


def test_a_borough_with_two_council_codes_is_in_postcode_order(index, monkeypatch):
    monkeypatch.setattr(pages.app, 'LAD_TO_BOROUGH', {HOUNSLOW: ('london', 'Hounslow'), 'E09000099': ('london', 'Hounslow')})
    index({'E09000099': ['TW14', 'TW4'], HOUNSLOW: ['TW3', 'TW4', 'UB2']})
    assert pages.planes_links('london', 'Hounslow') == ['TW3', 'TW4', 'TW14', 'UB2']


def test_it_is_keyed_on_the_ons_code_never_the_name(index):
    index({'Hounslow': ['TW3'], 'hounslow': ['TW3']})
    assert pages.planes_section('london', 'Hounslow') == ''


def test_a_borough_no_district_page_covers_has_no_block_and_an_unchanged_page(index):
    data = pages.gather('london', 'Hounslow')
    index({})
    without = pages.render(data)
    assert 'Planes overhead' not in without
    # The block sits between the map box and the sources: with none, the two are exactly as they were.
    assert '</div>\n\n<h2>Where these numbers come from</h2>' in without
    index({HOUNSLOW: ['TW3']})
    with_links = pages.render(data)
    assert with_links.replace(pages.planes_section('london', 'Hounslow'), '') == without


def _git(cwd, *args, date=None):
    # Isolated from the machine's own git setup (global and system config: signing, hooks, templates), so a
    # signing key or a global hook cannot fail this test for reasons that are not the code's.
    env = {**os.environ, 'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1',
           'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.invalid',
           'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@example.invalid'}
    if date:
        env['GIT_AUTHOR_DATE'] = env['GIT_COMMITTER_DATE'] = date
    # Literal arguments this test builds, in its own temporary repo; nothing user-supplied.
    subprocess.run(['git', '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=' + os.devnull, *args],  # noqa: S603, S607
                   cwd=cwd, env=env, check=True, capture_output=True)


def test_a_page_merged_from_a_branch_is_dated_the_day_of_the_merge(tmp_path, monkeypatch):
    _git(tmp_path, 'init', '-q', '-b', 'master')
    _git(tmp_path, 'config', 'core.autocrlf', 'false')
    (tmp_path / 'page.html').write_text('one\n', encoding='utf-8')
    _git(tmp_path, 'add', 'page.html')
    _git(tmp_path, 'commit', '-q', '-m', 'first', date='2026-10-01T12:00:00Z')
    _git(tmp_path, 'checkout', '-q', '-b', 'tables')
    (tmp_path / 'page.html').write_text('two\n', encoding='utf-8')
    _git(tmp_path, 'commit', '-q', '-am', 'written on a branch', date='2026-10-26T12:00:00Z')
    _git(tmp_path, 'checkout', '-q', 'master')
    (tmp_path / 'other.txt').write_text('x\n', encoding='utf-8')
    _git(tmp_path, 'add', 'other.txt')
    _git(tmp_path, 'commit', '-q', '-m', 'master moves on', date='2026-10-28T12:00:00Z')
    _git(tmp_path, 'merge', '-q', '--no-ff', 'tables', '-m', 'merged and live', date='2026-10-31T12:00:00Z')
    monkeypatch.setattr(pages, 'REPO', tmp_path)
    assert pages.last_changed(['page.html']) == {'page.html': '2026-10-31'}
