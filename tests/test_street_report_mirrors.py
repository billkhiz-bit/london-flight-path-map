"""js/street_report.mjs holds two mirrors of index.html, and they must not drift.

Why this exists (2026-10-06): the street report became something a visitor makes
in the browser, and a browser cannot read index.html for the two facts the report
had always taken from it - DEFRA's Lden band colours (NOISE_SCALE_DEFRA_LDEN,
which the map's legend reads) and the box London's DEFRA picture was rendered
for (LONDON_AIRCRAFT_BBOX). So the module holds copies. The PDF script compares
them with index.html on every run and refuses to print on a difference; this
holds them in preflight, where a change to either holder is caught on the day
it is made rather than the day someone prints a report. The front page's engine
imports the module's copies, so this also guards the map picture on /.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def read(rel):
    return (REPO / rel).read_text(encoding='utf-8')


def bands(text, const):
    block = re.search(rf'const {const} = \[(.*?)\]', text, re.S)
    assert block, f'{const} not found: the holder moved'
    return [
        (int(f), c.upper()) for f, c in re.findall(r"from:\s*(\d+),\s*colour:\s*'(#[0-9A-Fa-f]{6})'", block.group(1))
    ]


def box(text, pattern):
    block = re.search(pattern, text, re.S)
    assert block, f'{pattern} not found: the holder moved'
    return {k: float(v) for k, v in re.findall(r'(minLon|maxLon|minLat|maxLat):\s*(-?[\d.]+)', block.group(1))}


def test_the_report_draws_defra_bands_in_the_colours_the_map_legend_shows():
    site = bands(read('index.html'), 'NOISE_SCALE_DEFRA_LDEN')
    module = bands(read('js/street_report.mjs'), 'DEFRA_LDEN_SCALE')
    assert len(site) >= 5, f'only {len(site)} DEFRA bands parsed from index.html'
    assert module == site, f'js/street_report.mjs DEFRA_LDEN_SCALE {module} != index.html {site}'


def test_the_report_places_londons_picture_where_the_map_does():
    site = box(read('index.html'), r'const LONDON_AIRCRAFT_BBOX = \{(.*?)\}')
    module = box(read('js/street_report.mjs'), r'export const LONDON_RASTER = \{.*?bbox: \{(.*?)\}')
    assert set(site) == {'minLon', 'maxLon', 'minLat', 'maxLat'}, site
    assert module == site, f'js/street_report.mjs LONDON_RASTER.bbox {module} != index.html {site}'
