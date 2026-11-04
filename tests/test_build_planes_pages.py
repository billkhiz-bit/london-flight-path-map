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
import re
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
    assert '<td><span>15 on an edge</span><div class="bands"' in html  # west: every postcode an edge across the bands
    assert '30 of its 40 postcodes measured, the ones in Richmond upon Thames' in html
    assert 'On an edge: the postcode is on the edge of a flight path' in html
    assert '<form class="check" action="/" method="get">' in html and 'name="postcode"' in html
    assert '<link rel="canonical" href="https://skyscore.co.uk/planes-overhead/tw9/" />' in html
    assert '<a href="/area/london/richmond-upon-thames/">' in html
    assert '<a href="/planes-overhead/tw10/">TW10</a>' in html
    # one script that runs (the counter) and one that does not: the breadcrumb for search engines (2026-11-02)
    assert html.count('<script') == 2 and html.count('<script type="application/ld+json">') == 1
    assert '<script type="module" src="/js/count.mjs"></script>' in html


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


# ----------------------------------------------------------------- the area pages' links (2026-11-01)

def _lads(**shares):
    return {'lads': Counter(shares), 'city': 'london', 'at': (0.0, 0.0)}


def test_a_district_is_linked_from_each_council_holding_a_tenth_of_it():
    ctx = {'TW4': _lads(E09000018=85, E09000027=15),  # split: linked from both sides
           'TW3': _lads(E09000018=100),
           'UB2': _lads(E09000009=95, E09000018=5)}   # grazes Hounslow: linked from Ealing only
    index = bpp.council_index(['TW4', 'TW3', 'UB2'], ctx)
    assert index['councils'] == {'E09000009': ['UB2'], 'E09000018': ['TW3', 'TW4'], 'E09000027': ['TW4']}
    assert index['link_from'] == bpp.LINK_FROM == 0.10


def test_a_tenth_exactly_is_linked_and_just_under_is_not():
    on = bpp.council_index(['TW1'], {'TW1': _lads(E09000027=90, E09000018=10)})['councils']
    under = bpp.council_index(['TW1'], {'TW1': _lads(E09000027=91, E09000018=9)})['councils']
    assert on == {'E09000018': ['TW1'], 'E09000027': ['TW1']}
    assert under == {'E09000027': ['TW1']}


def test_only_districts_with_a_page_are_linked_in_postcode_order():
    ctx = {d: _lads(E09000027=50) for d in ('TW10', 'TW9', 'TW2', 'TW15')}
    index = bpp.council_index(['TW10', 'TW9', 'TW2'], ctx)  # TW15 has no page
    assert index['councils'] == {'E09000027': ['TW2', 'TW9', 'TW10']}


def test_check_councils_finds_a_missing_or_stale_index_and_ignores_line_endings(tmp_path):
    index = bpp.council_index(['TW9'], {'TW9': _lads(E09000027=40)})
    path = tmp_path / 'planes-districts-by-council.json'
    assert bpp.check_councils(index, path) == ['missing: data/planes-districts-by-council.json']
    path.write_bytes(bpp.councils_text(index).replace('\n', '\r\n').encode('utf-8'))  # a Windows checkout
    assert bpp.check_councils(index, path) == []
    moved = bpp.council_index(['TW9', 'TW10'], {'TW9': _lads(E09000027=40), 'TW10': _lads(E09000027=40)})
    assert 'does not match the built pages' in bpp.check_councils(moved, path)[0]


# ----------------------------------------------------------------- the index, grouped by council (2026-11-01)

def _elsewhere():
    """A council outside London, read from the registry (never typed), for a second city region."""
    return next(lad for lad, (city, _) in sorted(bpp.area.app.LAD_TO_BOROUGH.items()) if city != 'london')


def _index_page(ctx):
    models = [{'district': d, 'periods': ['January to August 2026']} for d in ctx]
    return bpp.render_index(models, bpp.council_index(list(ctx), ctx))


def _councils_listed(page):
    """{council: [district links]} from the index's own list items."""
    return {m.group(1): re.findall(r'<a href="/planes-overhead/([a-z0-9]+)/">', m.group(2))
            for m in re.finditer(r'<li><strong>([^<]+)</strong> (.*?)</li>', page)}


def test_the_index_lists_each_district_under_each_council_holding_a_tenth_of_it():
    away = _elsewhere()
    page = _index_page({'TW4': _lads(E09000018=85, E09000027=15), 'TW3': _lads(E09000018=100),
                        'UB2': _lads(E09000009=95, E09000018=5), 'XX1': _lads(**{away: 100})})
    listed = _councils_listed(page)
    assert listed['Hounslow'] == ['tw3', 'tw4']          # postcode order, lower-case paths
    assert listed['Richmond upon Thames'] == ['tw4']     # the boundary district under both
    assert listed['Ealing'] == ['ub2']                   # UB2 grazes Hounslow (5%): Ealing only
    assert listed[bpp.area.app.LAD_TO_BOROUGH[away][1]] == ['xx1']
    # Every district with a page is linked at least once, so a search engine still reaches all of them.
    assert {d for ds in listed.values() for d in ds} == {'tw3', 'tw4', 'ub2', 'xx1'}


def test_the_jump_list_names_each_city_region_heading_on_the_page():
    page = _index_page({'TW3': _lads(E09000018=100), 'XX1': _lads(**{_elsewhere(): 100})})
    jump = re.search(r'<nav class="jump"[^>]*>(.*?)</nav>', page).group(1)
    targets = re.findall(r'href="#([a-z0-9-]+)"', jump)
    assert targets == re.findall(r'<h2 id="([a-z0-9-]+)">', page)
    assert len(targets) == 2 and targets == sorted(targets)
    assert '<form class="check" action="/" method="get">' in page  # the postcode box above it


def test_the_index_stops_rather_than_drop_a_district_or_link_a_missing_page():
    ctx = {'TW3': _lads(E09000018=100)}
    with pytest.raises(ValueError, match='under no council'):
        bpp.render_index([{'district': 'TW3', 'periods': []}, {'district': 'TW9', 'periods': []}],
                         bpp.council_index(['TW3'], ctx))
    with pytest.raises(ValueError, match='no page'):
        bpp.render_index([], bpp.council_index(['TW3'], ctx))


def test_the_index_never_says_how_often_planes_pass():
    wording = _load_wording()
    page = _index_page({'TW3': _lads(E09000018=100), 'TW4': _lads(E09000018=60, E09000027=40)})
    for pattern in wording.FREQUENCY:
        assert not re.search(pattern, page, re.IGNORECASE), pattern


# ----------------------------------------------------------------- the consultation pack (2026-11-01)

LINK = 'https://www.heathrow.com/expansion/consultation'
OPEN = {'href': LINK, 'until': '2026-12-22'}
HOUNSLOW = 'E09000018'


def _model(name, lads, lhr=(317, 2, 190), lcy=None, n=30):
    f = _district(name, n=n, lhr=lhr, lcy=lcy)
    ctx = {'lads': Counter(lads), 'city': 'london', 'at': (0.0, 0.0)}
    return bpp.model(name, f, META, ctx, (n, 0), NAMES, [], ORDER), ctx


def _facts(drop=()):
    """build_area_pages.gather()'s shape: the four the pack repeats, and a price it must not."""
    facts = [{'label': 'Aircraft noise band', 'value': 'Severe', 'note': 'Estimated from the routes'},
             {'label': 'Road noise', 'value': 'Moderate', 'note': None},
             {'label': 'Air quality', 'value': 'Moderate', 'note': None},
             {'label': 'Flood risk', 'value': 'Low', 'note': None},
             {'label': 'Average price', 'value': '£528,051', 'note': None}]
    sources = ['Aviation noise context: DEFRA', 'Flight routes: UK AIP (NATS)', 'Road noise: DEFRA road',
               'Air quality: DEFRA PCM', 'Flood risk: EA', 'Prices: HM Land Registry']
    return {'facts': [f for f in facts if f['label'] not in drop], 'sources': sources}


# THE BAND BAR (declutter, 2026-11-03): a cell SHOWS the busiest band it reaches and draws every band as one bar,
# each band's width its count; the bar's label says every count. Still bands, never a middle figure.

def test_a_cell_shows_its_busiest_band_and_draws_every_band():
    html = bpp.cell_html(['up to 317 a day', '137 at 100+', '1,200 on an edge', '450 under 10'], top=True)
    assert re.findall(r'<span(?: class="top")?>(.*?)</span>', html) == ['up to 317 a day', '137 at 100+']
    assert html.startswith('<span class="top">up to 317 a day</span>')
    assert re.findall(r'<i class="(b\w+)" style="flex-grow:(\d+)"></i>', html) == \
        [('b100', '137'), ('bedge', '1200'), ('b0', '450')]  # each width its count, the thousands comma gone
    label = re.search(r'aria-label="([^"]*)"', html)[1]
    assert label == 'Postcodes by planes a day: 137 at 100+, 1,200 on an edge, 450 under 10'  # every count
    assert f'title="{label}"' in html and 'role="img"' in html


def test_a_cell_without_bands_draws_no_bar():
    for parts in (['not measured'], ['under 1 a day', 'at all 2 postcodes']):
        html = bpp.cell_html(parts)
        assert 'class="bands"' not in html and re.findall(r'<span>(.*?)</span>', html) == parts


def test_a_sector_cell_leads_with_the_busiest_band_it_reaches():
    shown = lambda figs: re.findall(r'<span>(.*?)</span>', bpp.cell_html(bpp.sector_parts(figs)))  # noqa: E731
    assert shown([317, 20, 5]) == ['1 at 100+']
    assert shown([20, 30, 5]) == ['2 at 10 to 99']  # none at 100+: the next band leads
    assert shown([[9, 20], 5]) == ['1 on an edge']
    assert shown([5, '<1']) == ['2 under 10']


def test_the_key_names_only_the_bands_its_bars_draw():
    key = bpp.band_key(bpp.bands_in([['3 at 100+', '4 under 10'], ['up to 2 a day', '2 under 10'], ['not measured']]))
    assert re.findall(r'<i class="(b\w+)"></i>', key) == ['b100', 'b0'] and 'on an edge' not in key
    assert 'aria-hidden="true"' in key  # the words above it say the bands


def test_the_band_colours_are_the_full_maps_planes_layer():
    bpl = _load('build_planes_layer')
    step = {start: bpl.COLOURS[i + 1] for i, start in enumerate(bpl.STEPS)}
    assert [start for start, _ in bpp.BANDS[:2]] == [100, 10]  # the bands start where two of the layer's steps do
    assert bpp.BAND_COLOURS == {'at 100+': step[100], 'at 10 to 99': step[10]}
    css = bpp.STYLE.replace('{{', '{').replace('}}', '}')
    assert f'.b100 {{ background:{step[100]}; }}' in css and f'.b10 {{ background:{step[10]}; }}' in css


def test_a_whole_district_cell_heads_with_its_busiest_figure():
    assert bpp.district_cell([317, [2, 318], '<1']) == ['up to 318 a day', '1 at 100+', '1 on an edge', '1 under 10']
    assert bpp.district_cell(['<1', 0]) == ['under 1 a day', 'at all 2 postcodes']
    assert bpp.district_cell([None, None]) == ['not measured']  # not measured is never a zero


def test_the_link_and_its_closing_day_are_read_from_have_your_say(tmp_path):
    js = tmp_path / 'street_report.mjs'
    js.write_text("export const HAVE_YOUR_SAY = {\n  LHR: [\n"
                  f"    {{ text: 'x', href: '{LINK}', until: '2026-12-22' }},\n"
                  "    { text: 'y', href: 'https://webtrak.emsbk.com/lhr6' },\n  ],\n  LCY: [\n  ],\n};\n",
                  encoding='utf-8')
    assert bpp.consultation(js) == OPEN
    js.write_text("export const HAVE_YOUR_SAY = {\n  LHR: [\n"
                  "    { text: 'y', href: 'https://webtrak.emsbk.com/lhr6' },\n  ],\n};\n", encoding='utf-8')
    assert bpp.consultation(js) is None
    assert bpp.pack_pages([], {'councils': {}}, '2026-11-01', None) == {}  # no dated link, no pack


def test_the_page_says_open_until_its_closing_day_and_closed_after_it():
    assert bpp.pack_state('2026-12-22', '2026-12-22') == 'open until 22 December 2026'
    assert bpp.pack_state('2026-12-22', '2026-12-23') == 'which closed on 22 December 2026'


def test_a_council_gets_a_page_only_where_one_of_its_district_pages_counts_heathrow():
    tw3, c3 = _model('TW3', {HOUNSLOW: 30})
    se1, c1 = _model('SE1', {'E09000028': 30}, lhr=None, lcy=(120, 3, 40))  # London City only
    ub2, c2 = _model('UB2', {'E09000009': 27, HOUNSLOW: 3})  # a tenth in Hounslow: under both
    index = bpp.council_index(['TW3', 'SE1', 'UB2'], {'TW3': c3, 'SE1': c1, 'UB2': c2})
    packs = bpp.pack_councils([tw3, se1, ub2], index)
    assert {lad: [m['district'] for m in ms] for lad, ms in packs.items()} == {
        'E09000009': ['UB2'], HOUNSLOW: ['TW3', 'UB2']}
    pages = bpp.pack_pages([tw3, se1, ub2], index, '2026-11-01', OPEN, gather=lambda city, borough: _facts())
    assert sorted(pages) == ['planes-overhead/heathrow-consultation/ealing/index.html',
                             'planes-overhead/heathrow-consultation/hounslow/index.html',
                             bpp.PACK_HUB_PATH]


def test_a_heathrow_district_page_links_its_councils_pack_pages_while_the_consultation_is_open():
    # Bill, 2026-11-02: "make the links clear and easy to navigate". The pack was reached only from the index; a
    # district page with Heathrow figures now links the pack page of each council listing it, while it is open.
    tw3, c3 = _model('TW3', {HOUNSLOW: 30})
    se1, c1 = _model('SE1', {'E09000028': 30}, lhr=None, lcy=(120, 3, 40))  # London City only
    ub2, c2 = _model('UB2', {'E09000009': 27, HOUNSLOW: 3})  # under Ealing and Hounslow both
    index = bpp.council_index(['TW3', 'SE1', 'UB2'], {'TW3': c3, 'SE1': c1, 'UB2': c2})
    by = bpp.pack_councils([tw3, se1, ub2], index)
    packs, until = bpp.district_packs('UB2', by, OPEN, '2026-11-01')
    assert packs == [('Ealing', '/planes-overhead/heathrow-consultation/ealing/'),
                     ('Hounslow', '/planes-overhead/heathrow-consultation/hounslow/')]
    html = bpp.render(ub2, packs, until)
    line = re.search(r'<p class="respond">.*?</p>', html)[0]
    assert re.findall(r'href="([^"]+)"', line) == [p for _, p in packs]
    assert 'open until 22 December 2026' in line and '.respond { font-weight:600; }' in html
    for pattern in _load_wording().FREQUENCY:
        assert not re.search(pattern, line, re.IGNORECASE), pattern
    assert bpp.district_packs('SE1', by, OPEN, '2026-11-01') == ([], '')  # no Heathrow figures, no line
    assert bpp.district_packs('UB2', by, OPEN, '2026-12-23') == ([], '')  # closed: the line goes
    assert bpp.district_packs('UB2', by, None, '2026-11-01') == ([], '')  # no pack built
    # Without the line a page is byte for byte what it was before the line existed: no .respond rule either.
    plain = bpp.render(tw3)
    assert 'class="respond"' not in plain and '.respond' not in plain and plain == bpp.render(tw3, [], '')


def test_the_index_names_each_council_page_in_the_pack_for_the_area_pages_and_the_front_page():
    tw3, c3 = _model('TW3', {HOUNSLOW: 30})
    se1, c1 = _model('SE1', {'E09000028': 30}, lhr=None, lcy=(120, 3, 40))
    ub2, c2 = _model('UB2', {'E09000009': 27, HOUNSLOW: 3})
    index = bpp.council_index(['TW3', 'SE1', 'UB2'], {'TW3': c3, 'SE1': c1, 'UB2': c2})
    pages = bpp.pack_pages([tw3, se1, ub2], index, '2026-11-01', OPEN, gather=lambda city, borough: _facts())
    assert bpp.consultation_entry(index, pages, OPEN) == {
        'airport': 'LHR', 'until': '2026-12-22', 'hub': '/planes-overhead/heathrow-consultation/',
        'councils': {'E09000009': '/planes-overhead/heathrow-consultation/ealing/',
                     HOUNSLOW: '/planes-overhead/heathrow-consultation/hounslow/'}}  # Southwark: no page, not named
    assert bpp.consultation_entry(index, {}, OPEN) is None  # no pages built, nothing named
    assert bpp.consultation_entry(index, pages, None) is None


def test_a_council_page_gives_each_district_its_own_figures_and_the_borough_its_own():
    tw3, _ = _model('TW3', {HOUNSLOW: 30})
    html = bpp.render_pack(HOUNSLOW, [tw3], OPEN, '2026-11-01', _facts())
    row = re.search(r'<tr role="row"><th scope="row" role="rowheader"><a href="/planes-overhead/tw3/">.*?</tr>', html)
    cells = [re.findall(r'<span(?: class="top")?>(.*?)</span>', td) for td in re.findall(r'<td [^>]*>(.*?)</td>', row[0])]
    assert cells == [['up to 317 a day', '30 at 100+'], ['up to 190 a day', '30 at 100+'], ['up to 2 a day', '30 under 10']]
    assert 'data-label="Flying west, 56% of days"' in row[0]  # a phone's stacked line names its column
    assert row[0].count('class="bands"') == 3  # each kind of day its bar
    assert re.findall(r'<i class="(b\w+)"></i>', re.search(r'<span class="key".*?</span></span>', html)[0]) == \
        ['b100', 'b0']  # the key names the two bands TW3's bars draw, never one they do not
    assert '<dt>Aircraft noise band</dt><dd>Severe<span class="note">Estimated from the routes</span></dd>' in html
    assert 'Average price' not in html and 'Prices: HM Land Registry' not in html  # the four, nothing else
    assert 'Aviation noise context: DEFRA' in html and 'Flood risk: EA' in html
    assert f'<a href="{LINK}">' in html and 'open until 22 December 2026' in html
    assert 'Sky Score takes no side in the consultation.' in html
    for pattern in _load_wording().FREQUENCY:
        assert not re.search(pattern, html, re.IGNORECASE), pattern


def test_a_missing_reading_is_said_and_its_source_is_not_credited():
    tw3, _ = _model('TW3', {HOUNSLOW: 30})
    html = bpp.render_pack(HOUNSLOW, [tw3], OPEN, '2026-11-01', _facts(drop=('Flood risk',)))
    assert '<dt>Flood risk</dt><dd>Not published for Hounslow</dd>' in html
    assert 'Flood risk: EA' not in html
    html = bpp.render_pack(HOUNSLOW, [tw3], OPEN, '2026-11-01', None)  # gather() found nothing
    assert html.count('<dd>Not published for Hounslow</dd>') == len(bpp.PACK_FACTS)


def test_the_pack_is_never_read_as_a_district():
    # The area pages' links and the index are built from the district pages only.
    assert bpp.is_district_page('planes-overhead/tw3/index.html')
    assert not bpp.is_district_page('planes-overhead/index.html')
    assert not bpp.is_district_page(bpp.PACK_HUB_PATH)
    assert not bpp.is_district_page('planes-overhead/heathrow-consultation/hounslow/index.html')


def _load_wording():
    spec = importlib.util.spec_from_file_location('test_public_wording', REPO / 'tests' / 'test_public_wording.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ----------------------------------------------------------------- the front page's dark band (front-page-v3, 2026-11-03)

BAND_INDEX = {'councils': {}, 'consultation': {
    'airport': 'LHR', 'until': '2026-12-22', 'hub': '/planes-overhead/heathrow-consultation/',
    'councils': {HOUNSLOW: '/planes-overhead/heathrow-consultation/hounslow/',
                 'E09000009': '/planes-overhead/heathrow-consultation/ealing/'}}}


def _band_page(tmp_path, crlf=False):
    nl = '\r\n' if crlf else '\n'
    page = tmp_path / 'index.html'
    page.write_bytes(nl.join(['<main>', f'      {bpp.PILL_BEGIN}', f'      {bpp.PILL_END}', f'      {bpp.BAND_BEGIN}', '      <p>stale</p>',
                              f'      {bpp.BAND_END}', '</main>', ''])
                     .encode('utf-8'))
    return page


def test_the_band_names_each_council_page_in_the_pack_while_it_is_open():
    html = '\n'.join(bpp.home_band(BAND_INDEX, '2026-11-03'))
    assert html.index('>Ealing</a>') < html.index('>Hounslow</a>'), 'councils in name order'
    assert 'href="/planes-overhead/heathrow-consultation/hounslow/"' in html
    assert 'href="/planes-overhead/heathrow-consultation/"' in html, 'the hub is the button'
    assert 'each of the 2 councils' in html and 'The 2 councils' in html, "the count is the index's, never typed"
    assert 'open until 22 December 2026' in html
    assert 'not those of a third runway' in html and 'Sky Score takes no side in the consultation.' in html


def test_the_band_is_open_on_its_last_day_and_the_planes_pages_after_it():
    assert 'See the planes over your council.' in '\n'.join(bpp.home_band(BAND_INDEX, '2026-12-22'))
    after = '\n'.join(bpp.home_band(BAND_INDEX, '2026-12-23'))
    assert 'See the planes over your district.' in after and 'consultation' not in after.lower()
    assert f'href="{bpp.URL_ROOT}"' in after
    assert '\n'.join(bpp.home_band({'councils': {}}, '2026-11-03')) == after, 'no pack built: the planes pages band'


def test_the_band_says_how_often_planes_pass_nowhere():
    wording = _load_wording()
    for today in ('2026-11-03', '2026-12-23'):
        text = wording.shown_from_source('home/index.html', '\n'.join(bpp.home_band(BAND_INDEX, today)))[0]
        for pattern in wording.FREQUENCY:
            assert not re.search(pattern, text, re.I), (today, pattern)


def test_the_new_pill_points_at_the_band_and_goes_with_the_consultation(tmp_path):
    page = _band_page(tmp_path)
    assert bpp.write_home(BAND_INDEX, '2026-12-22', page) is True
    assert 'href="#planes-band"' in page.read_text(encoding='utf-8'), 'open: the pill leads to the band'
    assert 'id="planes-band"' in page.read_text(encoding='utf-8'), 'and the band it names is on the page'
    assert bpp.check_home(BAND_INDEX, '2026-12-23', page), 'the day after, the pill reds with the band'
    assert bpp.write_home(BAND_INDEX, '2026-12-23', page) is True
    held = bpp.band_held(page.read_text(encoding='utf-8'), bpp.PILL_BEGIN, bpp.PILL_END)
    assert held and held[1] == '', 'closed: the two markers and nothing between them'
    assert bpp.check_home(BAND_INDEX, '2026-12-23', page) == []


def test_a_page_without_the_pill_markers_is_refused(tmp_path):
    page = tmp_path / 'index.html'
    page.write_text('\n'.join([bpp.BAND_BEGIN, bpp.BAND_END, '']), encoding='utf-8')
    assert any('pill' in problem for problem in bpp.check_home(BAND_INDEX, '2026-11-03', page))


def test_check_home_reds_once_the_consultation_closes_until_write(tmp_path):
    page = _band_page(tmp_path, crlf=True)
    assert bpp.check_home(BAND_INDEX, '2026-11-03', page), 'a stale band reds'
    assert bpp.write_home(BAND_INDEX, '2026-11-03', page) is True
    assert bpp.check_home(BAND_INDEX, '2026-11-03', page) == []
    assert b'\r\n' in page.read_bytes() and b'\r\r' not in page.read_bytes(), 'the page keeps its line endings'
    assert bpp.check_home(BAND_INDEX, '2026-12-22', page) == [], 'its last day is still open'
    assert bpp.check_home(BAND_INDEX, '2026-12-23', page), 'the day after, the open band reds'
    assert bpp.write_home(BAND_INDEX, '2026-12-23', page) is True
    assert bpp.check_home(BAND_INDEX, '2026-12-23', page) == []
    assert bpp.write_home(BAND_INDEX, '2026-12-23', page) is False, 'nothing to change'


def test_check_home_needs_each_marker_once(tmp_path):
    page = tmp_path / 'index.html'
    page.write_text(f'{bpp.BAND_BEGIN}\n{bpp.BAND_BEGIN}\n{bpp.BAND_END}\n', encoding='utf-8')
    assert bpp.check_home(BAND_INDEX, '2026-11-03', page)


def test_the_committed_front_page_band_is_todays():
    # The real page against the committed index, as preflight's --check reads it (also when the tracks are missing).
    assert bpp.check_home(bpp.tracked_index(), bpp.datetime.now(bpp.UTC).strftime('%Y-%m-%d')) == []
