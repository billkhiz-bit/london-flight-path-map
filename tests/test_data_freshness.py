"""Offline tests for scripts/check_data_freshness.py.

The registry's network half is advisory, but the parsing that turns a
publisher's page into "what is newest" is pure, and a parser that quietly finds
nothing would read as "current" forever. These pin each one against the shapes
measured on 2026-10-01, including the irregular file naming that broke the
crime script's URL.
"""

import datetime

from .conftest import load_script

fresh = load_script('check_data_freshness')


def test_crime_editions_newest_first_whatever_the_file_is_called():
    # Real hrefs from ONS's dataset page: the FILE names are irregular (this is
    # what made a URL built from EDITION 404); the folder names are not.
    html = ''.join(
        f'href="/file?uri=/peoplepopulationandcommunity/crimeandjustice/datasets/'
        f'policeforceareadatatables/{folder}/{file}"'
        for folder, file in [
            ('yearendingdecember2025', 'pfatablesyedec2025.xlsx'),
            ('yearendingmarch2026', 'pfatablesyemarch2026.xlsx'),
            ('yearendingseptember2025', 'policeforceareatablesyesep25.xlsx'),
            ('yearendingjune2025', 'policeforceareatablesyejune25final.xlsx'),
        ]
    )
    assert fresh.crime_editions(html) == [
        'yearendingmarch2026', 'yearendingdecember2025', 'yearendingseptember2025', 'yearendingjune2025',
    ]
    assert fresh.crime_editions('<html>no links</html>') == []


def test_nspl_editions_ignore_guides_and_feature_services():
    results = [
        {'title': 'National Statistics Postcode Lookup (August 2026) for the United Kingdom (Hosted Table)',
         'type': 'Feature Service'},
        {'title': 'National Statistics Postcode Lookup (August 2026) User Guide', 'type': 'CSV Collection'},
        {'title': 'National Statistics Postcode Lookup (August 2026)', 'type': 'CSV Collection'},
        {'title': 'National Statistics Postcode Lookup (May 2026)', 'type': 'CSV Collection'},
        {'title': 'National Statistics Postcode Lookup (February 2026)', 'type': 'CSV Collection'},
    ]
    assert fresh.nspl_editions(results) == ['2026-08', '2026-05', '2026-02']


def test_ks4_release_without_progress8_is_information_not_a_roll():
    assert fresh.ks4_status('2023/24', '2023/24') == 'current'
    assert fresh.ks4_status('2023/24', '2024/25') == 'info'
    assert fresh.ks4_status('2023/24', '2025/26') == 'info'
    assert fresh.ks4_status('2023/24', '2026/27') == 'NEWER'


def test_airac_steps_in_28_day_cycles():
    assert fresh.airac_current('2026-09-03', datetime.date(2026, 9, 30)) == '2026-09-03'
    assert fresh.airac_current('2026-09-03', datetime.date(2026, 10, 1)) == '2026-10-01'
    assert fresh.airac_current('2026-09-03', datetime.date(2026, 11, 28)) == '2026-11-26'


def test_latest_complete_year_skips_the_year_to_date_file():
    published = {2024, 2025, 2026}  # pp-2026 exists but is year-to-date
    probe = published.__contains__
    assert fresh.latest_complete_year(2025, datetime.date(2026, 10, 1), probe) == 2025
    assert fresh.latest_complete_year(2024, datetime.date(2026, 10, 1), probe) == 2025
    # Even the served year's file has gone: the probe refuses, it does not say "current".
    assert fresh.latest_complete_year(2025, datetime.date(2026, 10, 1), lambda y: False) is None


def test_every_checked_row_reads_its_served_version_from_a_holder():
    # The registry must not retype what is served: each row's function reads a
    # constant in the script that loads the data. A rename there must fail here,
    # not turn the row into a permanent INCONCLUSIVE.
    assert fresh.build_hpi_prices.DEFAULT_VINTAGE
    assert fresh.refresh_crime_from_ons.EDITION and fresh.refresh_crime_from_ons.XLSX_FILE
    assert fresh.load_nspl.NSPL_VINTAGE
    assert fresh.load_defra_air_quality.PCM_YEAR
    assert fresh.build_progress8.VINTAGE
    assert fresh.build_flight_paths.AIRAC
    assert fresh.build_us_flight_paths.RECORD.exists() and fresh.build_us_flight_paths.ZIP_URL
    assert fresh.build_city_neighbourhoods.PPD_YEARS
    assert fresh.CHECKED and all(callable(f) for _, f in fresh.CHECKED)


def test_a_faa_outage_is_inconclusive_and_a_page_with_no_zip_is_broken(monkeypatch):
    # An outage must raise, so main() reports INCONCLUSIVE as it does for every
    # other row. The first version caught it and printed BROKEN "links no CIFP
    # zip" for a timeout, which blames the page for the network.
    import urllib.error

    import pytest

    def down(url):
        raise urllib.error.URLError('timed out')

    monkeypatch.setattr(fresh, 'fetch_text', down)
    with pytest.raises(urllib.error.URLError):
        fresh.cifp()

    monkeypatch.setattr(fresh, 'fetch_text', lambda url: '<html>no links today</html>')
    assert fresh.cifp()[2] == 'BROKEN'

    link = 'https://aeronav.faa.gov/Upload_313-d/cifp/CIFP_991231.zip'
    monkeypatch.setattr(fresh, 'fetch_text', lambda url: f'<a href="{link}">')
    assert fresh.cifp()[1:3] == ('2099-12-31', 'NEWER')
