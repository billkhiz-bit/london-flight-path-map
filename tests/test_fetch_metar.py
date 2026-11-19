"""scripts/fetch_metar.py keeps only the archive's CSV (2026-10-23).

The same day DEFRA's maintenance page answered every URL with 200 and read as two new years of air-quality data,
so the METAR fetcher refuses anything but IEM's CSV header, and refuses a station the archive holds nothing for
(a wrong id), naming the airport, rather than caching an empty month the counter would read as "no shape".
"""

import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, 'scripts'))

import fetch_metar  # noqa: E402


class Answer:
    def __init__(self, body):
        self._body = body.encode('utf-8')

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def answering(body):
    return mock.patch.object(fetch_metar.urllib.request, 'urlopen', return_value=Answer(body))


def test_the_archives_csv_is_read():
    with answering('station,valid,alti\nEGGW,2026-02-13 06:50,29.92\nEGGW,2026-02-13 07:50,M\n'):
        assert fetch_metar.fetch('EGGW', '2026-02', '2026-02') == [('2026-02-13 06:50', '29.92')]


def test_a_web_page_is_refused():
    with answering('<html><head><title>Website Maintenance</title>'), pytest.raises(SystemExit, match='EGGW'):
        fetch_metar.fetch('EGGW', '2026-02', '2026-02')


def test_a_station_with_no_readings_is_refused():
    with answering('station,valid,alti\n'), pytest.raises(SystemExit, match='wrong station id'):
        fetch_metar.fetch('KXXX', '2026-02', '2026-02')


def test_a_request_runs_to_the_last_day_of_its_last_month():
    # IEM's end date is exclusive (18 Nov 2026): asking for the 30th of September returned up to 29 Sep 23:59, so the
    # last month of every request lost its last day. The end is the first of the month after, December into January.
    asked = []

    def urlopen(req, timeout):
        asked.append(dict(fetch_metar.urllib.parse.parse_qsl(fetch_metar.urllib.parse.urlsplit(req.full_url).query)))
        return Answer('station,valid,alti\nEGLL,2025-09-30 23:50,30.33\n')

    with mock.patch.object(fetch_metar.urllib.request, 'urlopen', urlopen):
        fetch_metar.fetch('EGLL', '2025-09', '2025-09')
        fetch_metar.fetch('EGLL', '2025-01', '2025-12')
    ends = [(q['year2'], q['month2'], q['day2']) for q in asked]
    assert ends == [('2025', '10', '1'), ('2026', '1', '1')]
    assert [(q['year1'], q['month1'], q['day1']) for q in asked] == [('2025', '9', '1'), ('2025', '1', '1')]


def test_every_counted_airport_has_a_station():
    import adsb_movements as mv
    assert set(mv.load_airports()) == set(mv.METAR_STATION)


def test_a_month_still_running_is_fetched_again():
    import datetime as dt
    today = dt.date(2026, 10, 24)
    assert fetch_metar.finished(2026, 9, today)
    assert not fetch_metar.finished(2026, 10, today)  # cached on the 24th, it would keep only 24 days for good
