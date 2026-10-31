"""Planes overhead by postcode district, as pages a search engine reads (2026-10-28).

`scripts/build_planes_pages.py` writes /planes-overhead/<district>/ from the planes files the front page reads. These
tests hold, on synthetic districts: a sector read in bands, an edge postcode counted in a band when both its ends are
in it and "on an edge" only when they are not (Bill's option C); the line above a table naming the busiest figure; a
postcode the files do not list under an airport read as under 1, never as missing; which districts get no page
(under PAGE_FROM, mostly outside the covered councils, mostly large users, too few postcodes); an airport under
PAGE_FROM given one line, never a table; labels and airport names read from the site's own modules, and the per-day
wording equal to js/planes.mjs; and --check catching a missing, stale or extra page and a manifest or sitemap out of
step, with each sitemap date the day its page last changed. Offline only (Node for the wording parity).
"""
import importlib.util
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load(name):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, REPO / 'scripts' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


bpp = _load('build_planes_pages')
ORDER = [('westerly', 'Flying west'), ('mixed', 'Both ways'), ('easterly', 'Flying east')]
META = {
    'classes': ['westerly', 'easterly', 'mixed'],
    'airports': {code: {'share_pct': {'westerly': 56, 'easterly': 29, 'mixed': 15}, 'months': ['202601', '202608']}
                 for code in ('LCY', 'LHR')},
    'definition': 'Overhead means more than halfway up the sky.', 'direction_rule': 'A day counts as one way.',
    'credits': ['Flight tracks: adsb.lol (ODbL 1.0)'], 'licence': 'Open Database License (ODbL) 1.0',
}
NAMES = {'LHR': 'Heathrow', 'LCY': 'London City'}


def _district(name='TW9', n=30, lhr=(317, 2, 190), lcy=None):
    """A district file: n postcodes in sectors 1 and 2, each under LHR (and LCY, if given) with the same figures."""
    pcs = [f'{name} {1 + k % 2}A{chr(65 + k // 2)}' for k in range(n)]
    listed = {pc: {**({'LHR': list(lhr)} if lhr else {}), **({'LCY': list(lcy)} if lcy else {})} for pc in pcs}
    return {'district': name, 'postcodes': {pc: v for pc, v in listed.items() if v},
            'none': [pc for pc, v in listed.items() if not v], 'approx': [], 'other': []}


def _ctx(n):
    return {'lads': Counter({'E09000027': n}), 'city': 'london', 'at': (0.0, 0.0)}


# ----------------------------------------------------------------- the reading (option C)

def test_a_sector_is_counted_in_bands():
    figs = [317, 317, [2, 317], [150, 317], '<1', 5, 0, 40, ['<1', 4]]
    assert bpp.sector_reading(figs) == '3 at 100+, 1 at 10 to 99, 1 on an edge, 4 under 10'


def test_a_cell_is_one_band_per_line_and_counts_carry_commas():
    assert bpp.sector_parts([5] * 1108 + [317]) == ['1 at 100+', '1,108 under 10']  # SK8 west read "1108" (28 Oct)


def test_an_edge_counts_in_a_band_when_both_its_ends_are_in_it():
    assert bpp.sector_reading([[150, 317]]) == '1 at 100+'
    assert bpp.sector_reading([[12, 60]]) == '1 at 10 to 99'
    assert bpp.sector_reading([[0, 9]]) == '1 under 10'
    assert bpp.sector_reading([[9, 20], [60, 120]]) == '2 on an edge'


def test_the_line_above_a_table_names_the_busiest_figure():
    assert bpp.overall_reading([317, [2, 318], '<1']) == \
        'up to 318 a day; of its 3 postcodes, 1 at 100+, 1 on an edge, 1 under 10'
    assert bpp.overall_reading(['<1', 0]) == 'under 1 a day at all 2 of its postcodes'


def test_a_postcode_not_listed_under_an_airport_reads_under_one():
    f = {'postcodes': {'A1 1AA': {'LHR': [5, 1, 2]}, 'A1 1AB': {'LCY': [12, 0, 3]}}, 'none': ['A1 1AD']}
    figs = bpp.figures_by_airport(f)
    assert figs['LHR'] == {'A1 1AA': [5, 1, 2], 'A1 1AB': ['<1'] * 3, 'A1 1AD': ['<1'] * 3}
    assert figs['LCY'] == {'A1 1AA': ['<1'] * 3, 'A1 1AB': [12, 0, 3], 'A1 1AD': ['<1'] * 3}


# ----------------------------------------------------------------- which districts

def test_which_districts_get_no_page_and_why():
    page = _district(n=30)
    assert bpp.verdict(page, (40, 0)) is None
    assert 'busiest postcode 9 a day' in bpp.verdict(_district(n=30, lhr=(9, 1, [2, 9])), (40, 0))
    assert 'in the covered councils' in bpp.verdict(page, (61, 0))  # 30 of 61: under half
    assert 'large users' in bpp.verdict(page, (40, 21))
    assert 'postcodes measured' in bpp.verdict(_district(n=bpp.MIN_POSTCODES - 1), (bpp.MIN_POSTCODES - 1, 0))
    # An edge whose TOP reaches PAGE_FROM is a postcode shown PAGE_FROM a day (reaches_one's rule).
    assert bpp.verdict(_district(n=30, lhr=([2, 10], 0, 0)), (30, 0)) is None


def test_more_measured_than_nspl_lists_is_the_wrong_edition():
    with pytest.raises(SystemExit, match="not the averages' edition"):
        bpp.verdict(_district(n=30), (29, 0))


# ----------------------------------------------------------------- what a page says

def _page(f, live=None, nearby=('TW10',)):
    n = len(f['postcodes']) + len(f['none'])
    m = bpp.model(f['district'], f, META, _ctx(n), (live or n, 0), NAMES, list(nearby), ORDER)
    return m, bpp.render(m)


def test_a_quiet_airport_gets_one_line_not_a_table():
    m, html = _page(_district(n=30, lhr=(317, 2, 190), lcy=(3, 1, 2)))
    assert [t['code'] for t in m['tables']] == ['LHR']
    assert m['also'] == [{'name': 'London City', 'most': '3 a day'}]
    assert '<h2 id="lhr">From Heathrow</h2>' in html and 'From London City' not in html
    assert 'London City, at most 3 a day over any of its postcodes' in html


def test_a_page_reads_its_sectors_and_says_how_much_was_measured():
    f = _district(n=30, lhr=([2, 317], 2, 190))
    m, html = _page(f, live=40)
    assert [row[0] for row in m['tables'][0]['rows']] == ['TW9 1', 'TW9 2']
    assert '<td><span>15 on an edge</span></td>' in html  # west: every postcode an edge across the bands
    assert '30 of its 40 postcodes measured, the ones in Richmond upon Thames' in html
    assert 'On an edge: the postcode is on the edge of a flight path' in html
    assert '<form class="check" action="/" method="get">' in html and 'name="postcode"' in html
    assert '<link rel="canonical" href="https://skyscore.co.uk/planes-overhead/tw9/" />' in html
    assert '<a href="/area/london/richmond-upon-thames/">' in html
    assert '<a href="/planes-overhead/tw10/">TW10</a>' in html
    assert html.count('<script') == 1 and '<script type="module" src="/js/count.mjs"></script>' in html


def test_the_edge_note_only_where_a_cell_says_on_an_edge():
    _, html = _page(_district(n=30, lhr=([150, 317], 2, 190)))  # ranges, all inside 100+
    assert 'on an edge' not in html.lower()


def test_labels_and_names_are_read_from_the_site():
    assert bpp.kinds() == ORDER
    names = bpp.airport_names()
    for code in ('BHX', 'BRS', 'EMA', 'LBA', 'LCY', 'LGW', 'LHR', 'LTN', 'MAN', 'STN'):
        assert names.get(code), code
    assert names['LHR'] == 'Heathrow'


def test_a_changed_kinds_line_stops_the_build(tmp_path):
    js = tmp_path / 'planes.mjs'
    js.write_text("const KINDS = [['westerly', 'Flying west', 'west']];\n", encoding='utf-8')
    with pytest.raises(SystemExit, match='changed shape'):
        bpp.kinds(js)


@pytest.mark.skipif(shutil.which('node') is None, reason='Node is not installed: the wording parity cannot run')
def test_per_day_and_period_say_what_the_front_page_says():
    values = [None, 0, '<1', 1, 317, [0, 4], ['<1', 9], [2, 317], [150, 317]]
    months = [['202601', '202608'], ['202511', '202602']]
    js = (f"import {{ perDay, period }} from '{(REPO / 'js' / 'planes.mjs').as_uri()}';\n"
          f'console.log(JSON.stringify([{json.dumps(values)}.map(perDay), {json.dumps(months)}.map(period)]));')
    run = subprocess.run(['node', '--input-type=module', '-e', js], capture_output=True, text=True,  # noqa: S603, S607
                         encoding='utf-8', check=True, cwd=REPO)
    said_js, periods_js = json.loads(run.stdout)
    assert [bpp.per_day(v) for v in values] == said_js
    assert [bpp.period(m) for m in months] == periods_js


# ----------------------------------------------------------------- write and check

def _pages():
    return {'planes-overhead/index.html': '<p>index</p>\n',
            'planes-overhead/tw9/index.html': '<p>TW9 £ °</p>\n',
            'planes-overhead/tw10/index.html': '<p>TW10</p>\n'}


def test_check_finds_every_way_out_of_step(tmp_path):
    pages = _pages()
    bpp.write(pages, root=tmp_path, today='2026-10-28')
    assert bpp.check(pages, root=tmp_path) == []

    (tmp_path / 'planes-overhead/tw9/index.html').write_text('<p>typed in</p>\n', encoding='utf-8')
    assert 'stale: planes-overhead/tw9/index.html' in bpp.check(pages, root=tmp_path)
    bpp.write(pages, root=tmp_path, today='2026-10-28')

    (tmp_path / 'planes-overhead/tw10/index.html').unlink()
    assert 'missing: planes-overhead/tw10/index.html' in bpp.check(pages, root=tmp_path)
    bpp.write(pages, root=tmp_path, today='2026-10-28')

    extra = tmp_path / 'planes-overhead/xx1/index.html'
    extra.parent.mkdir()
    extra.write_text('<p>old</p>\n', encoding='utf-8')
    assert 'no longer built: planes-overhead/xx1/index.html' in bpp.check(pages, root=tmp_path)
    bpp.write(pages, root=tmp_path, today='2026-10-28')
    assert not extra.parent.exists()

    sitemap = tmp_path / 'sitemap-planes.xml'
    sitemap.write_text(sitemap.read_text(encoding='utf-8').replace('tw10', 'tw11'), encoding='utf-8')
    assert 'sitemap-planes.xml does not match the manifest' in bpp.check(pages, root=tmp_path)

    changed = {**pages, 'planes-overhead/tw10/index.html': '<p>TW10, rolled</p>\n'}
    assert 'planes-pages-manifest.json does not match the built pages' in bpp.check(changed, root=tmp_path)


def test_a_sitemap_date_is_the_day_its_page_last_changed(tmp_path):
    pages = _pages()
    bpp.write(pages, root=tmp_path, today='2026-10-28')
    bpp.write({**pages, 'planes-overhead/tw10/index.html': '<p>TW10, rolled</p>\n'}, root=tmp_path,
              today='2026-11-15')
    manifest = json.loads((tmp_path / 'data/planes-pages-manifest.json').read_text(encoding='utf-8'))
    assert manifest['planes-overhead/tw9/index.html']['changed'] == '2026-10-28'
    assert manifest['planes-overhead/tw10/index.html']['changed'] == '2026-11-15'
    sitemap = (tmp_path / 'sitemap-planes.xml').read_text(encoding='utf-8')
    locs = [line.split('<loc>')[1].split('</loc>')[0] for line in sitemap.splitlines() if '<loc>' in line]
    assert locs == ['https://skyscore.co.uk/planes-overhead/', 'https://skyscore.co.uk/planes-overhead/tw9/',
                    'https://skyscore.co.uk/planes-overhead/tw10/']
    assert '/tw9/</loc><lastmod>2026-10-28<' in sitemap and '/tw10/</loc><lastmod>2026-11-15<' in sitemap
