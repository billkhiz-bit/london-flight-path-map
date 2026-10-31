"""The /area/ index compares each city's areas in one table (2026-10-25).

A reader in Poland opened 24 London area pages one at a time from /area/, going back to it 22 times, because the
index listed names only. Each city now has one table: the Sky Score, its five parts and the average price, read
from the facts each area's own page publishes (`compare_cell`), never recomputed.

What can go wrong, and is held here:
  - a label renamed in gather() would turn its whole column into dashes, silently: every column must be a label
    some page prints;
  - a figure a page does not publish must read as a dash that says so, never a number (CLAUDE.md: absence must
    never render as a measurement);
  - New York's affordability and growth are scored among its own boroughs: its table says it is not comparable
    with UK scores, and a UK table says nothing of the kind.

    python -m pytest tests/test_area_index_table.py
"""

import importlib.util
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location('build_area_pages', REPO_ROOT / 'scripts' / 'build_area_pages.py')
pages = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pages)


def _page(city, borough):
    data = pages.gather(city, borough)
    assert data is not None, f'{city}/{borough} has no page'
    return f'{pages.slug(city)}/{pages.slug(borough)}', data


def test_every_column_is_a_label_some_page_prints():
    printed = set()
    for city, cfg in pages.app.CITIES.items():
        if city in pages.app.SITE_FACTS_ONLY_CITIES:
            continue
        for borough in cfg['boroughs']:
            data = pages.gather(city, borough)
            if data:
                printed |= {f['label'] for f in data['facts']}
    missing = [c for c in pages.COMPARE_COLUMNS if c not in printed]
    assert not missing, f'no area page prints {missing}: a renamed label in gather() empties its column'


def test_a_figure_not_published_is_a_dash_never_a_number():
    # Cardiff's pages publish no Environment score (no `env` for the Welsh cities).
    _, data = _page('cardiff', 'Cardiff')
    assert 'Environment' not in {f['label'] for f in data['facts']}, 'Cardiff now publishes Environment: pick another'
    cell = pages.compare_cell('Environment', data['facts'])
    assert 'none published' in cell
    assert not re.search(r'\d', re.sub(r'<[^>]+>', '', cell)), cell


def test_a_published_figure_is_the_pages_own():
    _, data = _page('london', 'Hackney')
    published = next(f['value'] for f in data['facts'] if f['label'] == 'Sky Score')
    cell = pages.compare_cell('Sky Score', data['facts'])
    assert re.sub(r'<[^>]+>', '', cell) == published.removesuffix(' / 10')


def test_only_us_tables_say_they_are_not_comparable_with_uk_scores():
    nyc = pages.compare_table('nyc', [_page('nyc', 'Brooklyn')])
    london = pages.compare_table('london', [_page('london', 'Hackney')])
    assert 'not comparable with UK scores' in nyc
    assert 'not comparable' not in london
