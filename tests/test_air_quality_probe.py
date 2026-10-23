"""DEFRA's maintenance page is not a PCM file (2026-10-23).

On 23 October uk-air.defra.gov.uk answered every datastore URL, real or not, with `200 OK` and a 2,038-byte
"Website Maintenance" HTML page, and scripts/check_air_quality_vintage.py reported PCM 2026 as published (it read
the status, never the body). The served year's files "resolved" the same way, so its guard against a broken probe
could not fire either. A real file answers the probe's one-byte range with 206 and a CSV byte.
"""

import os
import sys
import urllib.error
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, 'scripts'))

import check_air_quality_vintage as probe  # noqa: E402

# The first bytes DEFRA actually served on 2026-10-23 for mapno22026.csv, which does not exist.
MAINTENANCE = b'<html><head>  <title>Website Maintenance</title>'


class FakeResponse:
    def __init__(self, status, content_type, body):
        self.status, self.headers, self._body = status, {'Content-Type': content_type}, body

    def read(self, n=-1):
        return self._body[:n] if n >= 0 else self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def answering(status, content_type, body):
    return mock.patch.object(probe.urllib.request, 'urlopen', return_value=FakeResponse(status, content_type, body))


def test_a_maintenance_page_is_not_a_published_file():
    with answering(200, 'text/html', MAINTENANCE), pytest.raises(urllib.error.URLError):
        probe.exists('https://uk-air.defra.gov.uk/datastore/pcm/mapno22026.csv')


def test_a_web_page_without_its_content_type_is_still_caught():
    with answering(200, 'application/octet-stream', MAINTENANCE), pytest.raises(urllib.error.URLError):
        probe.exists('https://uk-air.defra.gov.uk/datastore/pcm/mapno22026.csv')


def test_a_real_file_answers_the_range_with_its_first_byte():
    with answering(206, 'text/csv', b'L'):
        assert probe.exists('https://uk-air.defra.gov.uk/datastore/pcm/mapno22024.csv') is True


def test_during_maintenance_the_newest_year_is_not_known_rather_than_2026():
    def page(url):
        with answering(200, 'text/html', MAINTENANCE):
            return probe.exists(url)
    with pytest.raises(urllib.error.URLError):
        probe.latest_published(2024, 2026, probe=page)
