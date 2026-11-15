"""Rule 7 of N65's frozen method (Bill, 2026-11-15): the field level from the published elevation and the METAR QNH
(scripts/n65_day.py published_field() and day_field()).

The counter (scripts/adsb_movements.py) sets its field level from aircraft heard touching down; before Heathrow's
receiver came online (7 Oct 2025) that was too few on 94 of 177 days, and N65 refused every such day. N65 now reads the
published elevation (AD 2.2) moved through the day by the METAR QNH, as the counter's own FieldLevel moves, and keeps the
counter's level beside it only as a check. The METAR month here is MADE UP (two reports, 10 hPa apart). Offline only.
"""
import datetime as dt
import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import n65_day as nd  # noqa: E402

DAY = dt.date(2025, 7, 15)
MIDNIGHT = dt.datetime(2025, 7, 15, tzinfo=dt.UTC).timestamp()
NOON = MIDNIGHT + 12 * 3600


@pytest.fixture
def am():
    """The counter module n65_day will import when called: tests/test_adsb_movements.py loads its own copy into
    sys.modules, so a module bound at this file's import could be a different object from the one patched."""
    return importlib.import_module('adsb_movements')


@pytest.fixture
def metar(am, tmp_path, monkeypatch):
    """A made-up EGLL month: QNH 1013.25 hPa at midnight UTC on DAY, 1023.25 at noon (in inHg, as the cache holds it)."""
    def write(rows):
        with open(tmp_path / 'EGLL-2025-07.csv', 'w', encoding='utf-8', newline='') as fh:
            fh.write('station,valid,alti\n')
            for when, hpa in rows:
                fh.write(f'EGLL,{when},{hpa / 33.8639:.6f}\n')
        am._metar_month.cache_clear()
    monkeypatch.setattr(am, 'METAR_DIR', tmp_path)
    yield write
    am._metar_month.cache_clear()


def test_the_field_is_the_published_elevation_moved_by_the_qnh(am, metar):
    metar([('2025-07-15 00:00', 1013.25), ('2025-07-15 12:00', 1023.25)])
    field, how = nd.published_field('LHR', DAY)
    assert field.shaped and 'published elevation 83 ft (AD 2.2), shaped by METAR (2 reports)' == how
    assert nd.field_refusal(field, how) is None
    # At 1013.25 hPa the field's pressure altitude IS its elevation; 10 hPa higher it reads 273 ft lower.
    assert am.field_at(field, MIDNIGHT) == pytest.approx(83.0, abs=0.05)
    assert am.field_at(field, NOON) == pytest.approx(83.0 - 10 * am.FT_PER_HPA, abs=0.05)


def test_too_few_reports_or_no_elevation_refuses_the_day(metar):
    metar([('2025-07-15 06:00', 1013.25)])
    field, how = nd.published_field('LHR', DAY)
    assert field is None and '1 METAR report(s) cached for LHR' in how
    assert nd.field_refusal(field, how) is not None
    metar([])
    assert nd.published_field('LHR', DAY)[0] is None
    metar([('2025-07-15 00:00', 1013.25), ('2025-07-15 12:00', 1023.25)])
    field, how = nd.published_field('LGW', DAY)  # no ELEVATION_FT row (rule 5: Gatwick waits)
    assert field is None and 'no aerodrome elevation for LGW' in how


def test_what_the_counter_heard_is_a_check_beside_never_the_field(am, metar, monkeypatch):
    metar([('2025-07-15 00:00', 1013.25), ('2025-07-15 12:00', 1023.25)])
    # The counter's own reading of the day (here a fallback 500 ft) is reported against ours and changes nothing.
    monkeypatch.setattr(am, 'field_level', lambda traces, ap: (500.0, 'p10 of 520 in-zone minima (no surface reports)'))
    field, how, check = nd.day_field('LHR', DAY, [], {})
    assert am.field_at(field, NOON) == pytest.approx(83.0 - 10 * am.FT_PER_HPA, abs=0.05)
    assert check == {'how': 'p10 of 520 in-zone minima (no surface reports)',
                     'minus_published_ft': pytest.approx(500.0 - (83.0 - 10 * am.FT_PER_HPA), abs=0.1)}
    assert nd.field_refusal(field, how) is None  # the counter's fallback no longer refuses the day
    monkeypatch.setattr(am, 'field_level', lambda traces, ap: (None, 'too few aircraft'))
    assert nd.day_field('LHR', DAY, [], {})[2] == {'how': 'too few aircraft', 'minus_published_ft': None}
