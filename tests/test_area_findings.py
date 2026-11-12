"""The area pages' findings (Bill's pick, 2026-11-04: Stitch's layout, the site's colours).

The score bands, Progress 8 bands and crime thresholds are the map's, copied into the builder because it is Python. A copy
drifts, so each is read back out of index.html here and held equal. A fact with no place on the page stops the build:
gather() can grow a row, and a table would have shown it where a fixed layout silently would not.
"""
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
sys.path.insert(0, str(REPO / 'backend' / 'lambdas' / 'score'))
spec = importlib.util.spec_from_file_location('build_area_pages', REPO / 'scripts' / 'build_area_pages.py')
pages = importlib.util.module_from_spec(spec)
sys.modules['build_area_pages'] = pages
spec.loader.exec_module(pages)

MAP = (REPO / 'index.html').read_text(encoding='utf-8')


def between(start, end):
    a = MAP.index(start)
    return MAP[a:MAP.index(end, a)]


def test_score_colours_are_the_maps():
    body = between('function scoreColor(v)', '}')
    high, mid, low = re.findall(r"'(#[0-9A-Fa-f]{6})'", body)
    cuts = [float(c) for c in re.findall(r'v >= ([\d.]+)', body)]
    assert cuts == [7, 4]
    assert [pages.score_colour(s) for s in (7, 6.9, 4, 3.9)] == [high.lower(), mid.lower(), mid.lower(), low.lower()]


def test_school_bands_are_the_maps():
    body = between('function schoolBandFromP8(p8)', 'function schoolBadge')
    rules = re.findall(r"p8 >= (-?[\d.]+)\) return \{ label: '([^']+)'", body)
    last = re.search(r"return \{ label: '([^']+)', cls: 'rating-high' \};\s*\}", body).group(1)
    assert len(rules) == 4
    for cut, label in rules:
        assert pages.school_band(float(cut)) == label
    assert pages.school_band(float(rules[-1][0]) - 0.01) == last


def test_crime_thresholds_are_the_maps():
    body = between('function crimeNote(extra', 'const distinctive')  # its options follow (2026-11-08)
    assert 'ratio >= 1.15' in body and 'ratio <= 0.85' in body
    median = pages.london_crime_median()
    assert pages.crime_against_london(median) == 'close to the London median'
    assert pages.crime_against_london(median * 1.14) == 'close to the London median'
    assert pages.crime_against_london(median * 1.6) == '1.6 times the London median'
    assert pages.crime_against_london(median * 0.5) == '2.0 times lower than the London median'


def test_the_median_is_the_maps():
    # Runs the map's own function, read out of index.html, so a change to what it counts reds here. Its parity with the
    # data file is tests/test_borough_data_parity.py's.
    body = between('function londonCrimeMedian()', 'function crimeNote')
    script = f'const BOROUGH_EXTRA = JSON.parse(require("fs").readFileSync(0, "utf8"));{body}console.log(londonCrimeMedian());'
    out = subprocess.run(['node', '-e', script], input=json.dumps(pages._BOROUGH_EXTRA['london']),  # noqa: S603, S607  (node, fixed args)
                         capture_output=True, text=True, encoding='utf-8', check=True).stdout
    assert float(out) == pages.london_crime_median()


FACT = {'label': 'Recorded crime', 'value': '87.6', 'note': 'ONS Table C4, per 1,000 residents per year'}


def test_a_figure_gets_words_a_first_time_reader_can_use():
    html = pages.finding(FACT, True)
    assert 'Recorded crime is close to the London median' in html
    assert '87.6 recorded offences per 1,000 residents a year' in html
    assert 'ONS Table C4' in html


def test_new_york_is_never_read_against_london():
    html = pages.finding({'label': 'Recorded crime', 'value': '78', 'note': None}, False)
    assert 'London' not in html and '78 recorded offences' in html


def test_schools_read_as_their_band_and_keep_the_figure():
    html = pages.finding({'label': 'Progress 8', 'value': '0.45', 'note': 'DfE KS4 2023/24 revised, 0.0 is the national average'}, True)
    assert 'Schools are above average' in html and 'Progress 8 is 0.45.' in html and 'DfE KS4' in html


def test_a_band_reads_as_a_word_and_a_figure_never_does():
    assert 'Road noise is moderate' in pages.finding({'label': 'Road noise', 'value': 'Moderate', 'note': None}, True)
    assert 'Aircraft noise is severe' in pages.finding({'label': 'Aircraft noise band', 'value': 'Severe', 'note': None}, True)
    measured = pages.finding({'label': 'Road noise', 'value': '48.9% of postcodes', 'note': None}, True)
    assert 'Road noise is' not in measured and '48.9% of postcodes' in measured


def test_a_fact_with_no_place_stops_the_build():
    with pytest.raises(ValueError, match='Sewage'):
        pages.findings_html([{'label': 'Sewage', 'value': 'x', 'note': None}], True)


def test_two_facts_under_one_label_stop_the_build():
    fact = {'label': 'Road noise', 'value': 'Low', 'note': None}
    with pytest.raises(ValueError, match='share a label'):
        pages.findings_html([fact, dict(fact)], True)


def test_every_fact_of_every_page_reaches_it():
    built = 0
    for city, cfg in pages.app.CITIES.items():
        for borough in cfg['boroughs']:
            data = pages.gather(city, borough)
            if not data or len(data['facts']) < pages.MIN_FACTS:
                continue
            html = pages.render(data)
            built += 1
            assert html.count(' data-fact') == len(data['facts']), (city, borough)
            for f in data['facts']:
                if f.get('note'):
                    assert pages.e(f['note']) in html, (city, borough, f['label'])
            assert '<span class="n">' in html  # tests/area-page-freshness.mjs reads the score here
    assert built > 100


def test_a_group_with_nothing_to_say_leaves_no_heading():
    _, groups = pages.findings_html([{'label': 'Average price', 'value': '£1', 'note': None}], True)
    assert 'Property' in groups and 'Noise and planes' not in groups and 'Living here' not in groups


# THE VISUALS (Bill's pick B, 2026-11-04): a bar for a true number, a strip for a rating, nothing for a figure not held.
def hounslow():
    return pages.gather('london', 'Hounslow')


def widths(html):
    return [float(w) for w in re.findall(r'width:([\d.]+)%', html)]


def test_the_air_guidelines_are_the_sites_and_the_apis():
    report = (REPO / 'js' / 'street_report.mjs').read_text(encoding='utf-8')
    held = re.search(r'AIR_WHO_2021 = \{ no2: (\d+), pm25: (\d+) \}', report)
    assert {'no2': int(held[1]), 'pm25': int(held[2])} == pages.AIR_WHO
    api = (REPO / 'backend' / 'lambdas' / 'score' / 'app.py').read_text(encoding='utf-8')
    assert re.search(r"env\['no2WhoGuidelineUgm3'\] = (\d+)", api)[1] == str(pages.AIR_WHO['no2'])
    assert re.search(r"env\['pm25WhoGuidelineUgm3'\] = (\d+)", api)[1] == str(pages.AIR_WHO['pm25'])


def test_a_share_is_drawn_true_to_its_whole():
    html = pages.share_bar(62.7, 'Postcodes over the WHO guideline')
    assert widths(html) == [62.7] and '62.7%' in html


def test_a_tiny_share_stays_visible_and_says_its_true_figure():
    html = pages.share_bar(0.33, 'Postcodes at medium or high risk')
    assert widths(html) == [0.6] and '0.33%' in html


def test_two_bars_keep_the_true_ratio_from_zero():
    a, b = widths(pages.pair_bars([('Here', 142.4, '142.4', False), ('London median', 87.6, '87.6', True)]))
    assert abs(a / b - 142.4 / 87.6) < 0.01
    assert a < 100


def test_a_strip_lights_exactly_its_own_rating():
    html = pages.step_strip(pages.RATING_STEPS, 'Good')
    assert re.findall(r'<span class=on>(\w+)</span>', html) == ['Good']
    assert pages.step_strip(pages.RATING_STEPS, 'Superb') == ''


@pytest.mark.parametrize('p8, on', [(0.6, 'Well above'), (0.45, 'Above'), (0.0, 'Average'), (-0.3, 'Below'), (-0.7, 'Well below')])
def test_the_school_strip_follows_the_band(p8, on):
    data = {'borough': 'X', 'facts': [{'label': 'Progress 8', 'value': f'{p8:g}', 'note': None}]}
    strip, _ = pages.visuals(data, 'London', True)['Progress 8']
    assert re.findall(r'<span class=on>([\w ]+)</span>', strip) == [on]


def test_every_rating_in_the_data_has_its_step():
    for city in pages._BOROUGH_EXTRA.values():
        for record in city.values():
            if isinstance(record, dict):
                for key in ('transport', 'healthcare'):
                    if record.get(key):
                        assert pages.step_strip(pages.RATING_STEPS, record[key]), (key, record[key])


def test_a_figure_not_held_draws_nothing():
    drawn = pages.visuals({'borough': 'X', 'facts': [], 'figures': {}, 'avg_price': None, 'price_median': None}, 'London', True)
    assert drawn == {}


def test_new_york_is_never_drawn_against_london():
    data = {'borough': 'Queens', 'facts': [], 'figures': {'crimeRate': 78}}
    assert 'Recorded crime' not in pages.visuals(data, 'New York City', False)


def test_a_real_page_draws_what_b_shows():
    html = pages.render(hounslow())
    assert html.count('class="steps"') == 3
    assert 'Postcodes over the WHO guideline' in html and 'Postcodes at medium or high risk' in html
    assert 'Nitrogen dioxide' in html and 'Fine particles' in html and 'WHO guideline' in html
    assert html.count('London median') >= 3  # the words, the crime bar, the price bar
    assert not re.search(r'Aircraft noise is \w+</p><div class="(steps|vis)', html)  # nothing honest to draw it against


def test_a_true_zero_draws_nothing():
    assert widths(pages.share_bar(0, 'Postcodes at medium or high risk')) == [0]


def test_the_city_of_londons_figure_is_called_an_estimate_never_recorded():
    # ONS publishes no rate for it, so the sentence must carry that, not only the small print under it.
    data = pages.gather('london', 'City of London')
    crime = next(f for f in data['facts'] if f['label'] == 'Recorded crime')
    assert crime['estimated'] is True
    html = pages.finding(crime, True)
    assert 'Estimated crime is' in html and "Sky Score's estimate" in html.replace('&#x27;', "'")
    assert 'Recorded crime' not in html and 'recorded offences' not in html


def test_the_median_reads_the_same_in_the_sentence_and_the_bar():
    said = pages.london_median_said()
    sentence = pages.finding({'label': 'Recorded crime', 'value': '90', 'note': None}, True)
    data = {'borough': 'X', 'facts': [], 'figures': {'crimeRate': 90}}
    bars = pages.visuals(data, 'London', True)['Recorded crime'][1]
    assert f'the London median is {said}.' in sentence and f'<b>{said}</b>' in bars


def test_a_figure_the_sentence_gives_is_not_read_out_twice():
    data = {'borough': 'X', 'facts': [], 'figures': {'crimeRate': 90}}
    assert '<div class="vis" aria-hidden=true>' in pages.visuals(data, 'London', True)['Recorded crime'][1]
    data = {'borough': 'X', 'facts': [], 'figures': {'no2AnnualMeanUgm3': 18}}
    assert 'aria-hidden=true' not in pages.visuals(data, 'London', True)['Air quality'][1].split('<div class="bar"')[0]


def test_a_figure_its_bar_says_is_not_printed_twice():
    html = pages.finding({'label': 'Road noise', 'value': '48.9% of postcodes', 'note': None}, True, '', '<div class="vis">bar</div>')
    assert '48.9% of postcodes' not in html


def test_no_text_on_an_area_page_is_under_the_sites_12px():
    # "Raise, never shrink" (Bill, the site audit of 2026-11-01).
    assert not re.search(r'font-size:(?:\d|1[01])(?:\.\d+)?px', pages.PAGE)
