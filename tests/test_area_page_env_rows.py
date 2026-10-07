"""A scored environment input is never left off its area page (website audit I16, 2026-10-07).

The road noise, air quality and flood rows printed BANDS, and the bands live in
data/borough-extra.json alone, which leaves the API-only cities out on purpose. So the 11
Cardiff, Nottingham and Norwich pages showed none of the three while the Lambda held the
continuous figure behind each and the Environment score used it. Nothing could see it:
tests/area-pages.mjs reads only the HTML, and `area builder == its outputs` compares the
builder with itself.

This asks the question from the Lambda's side, for every borough of every city: if the
scoring record holds the figure, the page carries the row. A borough with a band keeps its
band; one without prints the figure as held, never re-banded (bands are cut on the
unrounded share and the Lambda holds the rounded one).

    python -m pytest tests/test_area_page_env_rows.py
"""

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location('build_area_pages', REPO_ROOT / 'scripts' / 'build_area_pages.py')
pages = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pages)
app = pages.app

# The page labels gather() prints for each MEASURED_FIELD key. Mirrored, not imported: the
# labels sit in a loop literal, and a renamed label should fail here rather than move silently.
LABEL = {'roadNoise': 'Road noise', 'airQuality': 'Air quality', 'flood': 'Flood risk'}


def _cases():
    for city, cfg in app.CITIES.items():
        if cfg.get('country') != 'United Kingdom':
            continue
        for borough in cfg['boroughs']:
            yield city, borough


CASES = list(_cases())


def test_the_label_mirror_covers_every_measured_field():
    assert set(LABEL) == set(pages.MEASURED_FIELD)


def test_the_cases_reach_the_api_only_cities():
    # The defect lived only in cities absent from borough-extra.json; a case list that never
    # reaches one would pass while testing nothing.
    absent = {city for city, _ in CASES if city not in pages._BOROUGH_EXTRA}
    assert {'cardiff', 'nottingham', 'norwich'} <= absent, absent


@pytest.mark.parametrize(('city', 'borough'), CASES)
def test_a_held_environment_figure_reaches_the_page(city, borough):
    data = pages.gather(city, borough)
    assert data is not None, f'{city}/{borough} produced no page'
    rows = {f['label']: f['value'] for f in data['facts']}
    record = app.CITIES[city]['boroughs'][borough]
    painted = pages._painted_for(city, borough)
    for key, field in pages.MEASURED_FIELD.items():
        held = record.get(field)
        if not isinstance(held, (int, float)):
            continue
        assert LABEL[key] in rows, (
            f'{city}/{borough}: the Lambda holds {field}={held} and the page has no {LABEL[key]} row'
        )
        if not painted.get(key):
            # No band to print, so the figure itself, exactly as the score used it.
            assert rows[LABEL[key]] == pages.measured_value(key, held)
            assert f'{held:g}' in rows[LABEL[key]]


def test_measured_value_reads_as_held_and_refuses_an_unknown_key():
    assert pages.measured_value('airQuality', 1.49) == '1.49 × the WHO 2021 guideline'
    assert pages.measured_value('roadNoise', 48.9) == '48.9% of addresses'
    assert pages.measured_value('flood', 0.5) == '0.5% of addresses'
    with pytest.raises(KeyError):
        pages.measured_value('transport', 50.0)
