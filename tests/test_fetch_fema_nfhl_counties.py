"""Tests for scripts/fetch_fema_nfhl_counties.py, FEMA's county-wide NFHL downloads fetched on a US runner.

FEMA cannot be reached from this machine and GDAL is not installed here, so the guards are tested against a
stubbed network and a stubbed ogr2ogr: the counties follow the committed place and trend files, a reset is
retried and a 404 is not, a reply that is not a zip fails quoting it, an archive member that climbs out of
its folder is refused, the layer is found as a shapefile, a geodatabase or one zip down, and the output is
read by build_bayarea_flood.py's OWN reader and point test, not by a copy of them. Offline only.
"""

import gzip
import importlib.util
import io
import json
import urllib.error
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / 'scripts' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fc = _load('fetch_fema_nfhl_counties')
bf = _load('build_bayarea_flood')


def _real(path):
    return json.loads(path.read_text(encoding='utf-8'))


def test_the_counties_follow_the_place_and_trend_files():
    want = fc.counties(_real(fc.PLACES), _real(fc.TREND))
    names = {p['county'] for p in _real(fc.PLACES)['places'] if p['kind'] in ('city', 'town')}
    assert {n for n, _ in want} == names
    assert all(f.startswith('06') and len(f) == 5 for _, f in want)


def test_a_county_without_a_fips_row_fails_rather_than_being_skipped():
    places = {'places': [{'kind': 'city', 'county': 'Alameda'}, {'kind': 'city', 'county': 'Marin'}]}
    trend = {'counties': [{'county': 'Alameda', 'fips': '06001'}]}
    with pytest.raises(SystemExit, match='Marin'):
        fc.counties(places, trend)


def test_a_place_that_is_not_scored_does_not_add_a_county():
    places = {'places': [{'kind': 'city', 'county': 'Alameda'}, {'kind': 'cdp', 'county': 'Marin'}]}
    assert fc.counties(places, {'counties': [{'county': 'Alameda', 'fips': '06001'}]}) == [('Alameda', '06001')]


class _Reply(io.BytesIO):
    def __init__(self, body, headers=None):
        super().__init__(body)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def test_a_reset_is_retried_and_the_download_recorded(tmp_path):
    calls, waits = [], []

    def opener(req, timeout):
        calls.append(req.full_url)
        if len(calls) < 3:
            raise urllib.error.URLError(ConnectionResetError('connection reset by peer'))
        return _Reply(b'PK\x03\x04rest', {'Content-Disposition': 'attachment; filename="NFHL_06001C_20250101.zip"'})

    size, sha, name = fc.download('https://x/NFHL_06001C', tmp_path / 'a.zip', opener, waits.append)
    assert (size, name, len(calls)) == (8, 'NFHL_06001C_20250101.zip', 3)
    assert waits == [fc.PAUSE_S, fc.PAUSE_S * 2]
    assert len(sha) == 64 and (tmp_path / 'a.zip').read_bytes() == b'PK\x03\x04rest'


def test_a_404_is_fema_s_answer_and_is_not_retried(tmp_path):
    calls = []

    def opener(req, timeout):
        calls.append(1)
        raise urllib.error.HTTPError(req.full_url, 404, 'Not Found', {}, None)

    with pytest.raises(SystemExit, match='404'):
        fc.download('https://x/NFHL_06999C', tmp_path / 'a.zip', opener, lambda s: None)
    assert calls == [1]


def test_an_unreachable_county_fails_after_every_try(tmp_path):
    def opener(req, timeout):
        raise TimeoutError('timed out')

    with pytest.raises(fc.NetworkError, match=f'after {fc.TRIES} tries'):
        fc.download('https://x/NFHL_06001C', tmp_path / 'a.zip', opener, lambda s: None)


def test_a_page_instead_of_a_zip_fails_quoting_it(tmp_path):
    p = tmp_path / 'NFHL_06075C.zip'
    p.write_bytes(b'<!DOCTYPE html><html><body>No product found</body></html>')
    with pytest.raises(fc.NotAZip, match='not a zip.*No product found'):
        fc.require_zip(p)
    p.write_bytes(b"<script> var userName = ''; </script><html><head><title>\n  FEMA Flood Map Service Center |\n"
                  b"  Search </title></head><body>" + b'x' * 5000 + b'</body></html>')
    with pytest.raises(fc.NotAZip, match=r"'FEMA Flood Map Service Center \| Search'"):
        fc.require_zip(p)


def _zip(path, members):
    with zipfile.ZipFile(path, 'w') as z:
        for name, body in members.items():
            z.writestr(name, body)
    return path


@pytest.mark.parametrize('bad', ['../evil.shp', '/etc/evil', 'C:/evil.shp', 'a/../../evil'])
def test_a_member_that_climbs_out_is_refused(tmp_path, bad):
    with pytest.raises(SystemExit, match='refused'):
        fc.safe_extract(_zip(tmp_path / 'z.zip', {bad: b'x'}), tmp_path / 'out')
    assert not (tmp_path / 'evil.shp').exists() and not (tmp_path / 'out').exists()


def test_the_layer_is_found_as_a_shapefile(tmp_path):
    fc.safe_extract(_zip(tmp_path / 'z.zip', {'NFHL_06001C/S_FLD_HAZ_AR.shp': b'', 'NFHL_06001C/S_XS.shp': b''}),
                    tmp_path / 'u')
    assert fc.find_source(tmp_path / 'u').name == 'S_FLD_HAZ_AR.shp'


def test_the_layer_is_found_as_a_geodatabase(tmp_path):
    fc.safe_extract(_zip(tmp_path / 'z.zip', {'NFHL_06001C.gdb/a00000001.gdbtable': b''}), tmp_path / 'u')
    assert fc.find_source(tmp_path / 'u').name == 'NFHL_06001C.gdb'


def test_the_layer_is_found_one_zip_down(tmp_path):
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, 'w') as z:
        z.writestr('S_FLD_HAZ_AR.shp', b'')
    fc.safe_extract(_zip(tmp_path / 'z.zip', {'NFHL_06001C_20250101.zip': inner.getvalue()}), tmp_path / 'u')
    assert fc.find_source(tmp_path / 'u').name == 'S_FLD_HAZ_AR.shp'


def test_no_layer_and_two_layers_both_fail(tmp_path):
    fc.safe_extract(_zip(tmp_path / 'z.zip', {'readme.txt': b''}), tmp_path / 'none')
    with pytest.raises(SystemExit, match='no S_FLD_HAZ_AR'):
        fc.find_source(tmp_path / 'none')
    fc.safe_extract(_zip(tmp_path / 'y.zip', {'a/S_FLD_HAZ_AR.shp': b'', 'b.gdb/x': b''}), tmp_path / 'two')
    with pytest.raises(SystemExit, match='2 candidate'):
        fc.find_source(tmp_path / 'two')


def test_lines_among_the_zones_fail():
    with pytest.raises(SystemExit, match='LineString'):
        fc.esri_features({'features': [{'properties': {}, 'geometry': {'type': 'LineString', 'coordinates': []}}]})


# A square zone AE with a square hole, and a two-part zone X: the shapes FEMA's layer holds.
SQUARE = [[-122.30, 37.80], [-122.20, 37.80], [-122.20, 37.90], [-122.30, 37.90], [-122.30, 37.80]]
HOLE = [[-122.26, 37.84], [-122.24, 37.84], [-122.24, 37.86], [-122.26, 37.86], [-122.26, 37.84]]
GEOJSON = {'type': 'FeatureCollection', 'features': [
    {'properties': {'FLD_ZONE': 'AE', 'SFHA_TF': 'T', 'DFIRM_ID': '06001C'},
     'geometry': {'type': 'Polygon', 'coordinates': [SQUARE, HOLE]}},
    {'properties': {'FLD_ZONE': 'X', 'SFHA_TF': 'F', 'DFIRM_ID': '06001C'},
     'geometry': {'type': 'MultiPolygon', 'coordinates': [
         [[[-122.10, 37.80], [-122.00, 37.80], [-122.00, 37.90], [-122.10, 37.80]]],
         [[[-121.90, 37.80], [-121.80, 37.80], [-121.80, 37.90], [-121.90, 37.80]]]]}},
    {'properties': {'FLD_ZONE': 'D', 'SFHA_TF': 'F', 'DFIRM_ID': '06001C'}, 'geometry': None},
]}


def test_the_output_is_what_the_flood_reader_reads(tmp_path, monkeypatch):
    def get(url, dest):
        _zip(dest, {'NFHL/S_FLD_HAZ_AR.shp': b''})
        return dest.stat().st_size, 'f' * 64, dest.name

    def read(src, workdir):
        assert src.name == 'S_FLD_HAZ_AR.shp'
        return GEOJSON, 'Layer name: S_FLD_HAZ_AR\nGeometry: Polygon'

    monkeypatch.setattr(fc, 'download', get)
    monkeypatch.setattr(fc, 'read_layer', read)
    monkeypatch.setattr(fc, 'BETWEEN_S', 0)
    monkeypatch.setattr('sys.argv', ['x', '--out', str(tmp_path / 'out'), '--raw', str(tmp_path / 'raw')])
    assert fc.main() == 0

    monkeypatch.setattr(bf, 'RAW', tmp_path / 'out' / 'nfhl-bayarea.esrijson.gz')
    monkeypatch.setattr(bf, 'MANIFEST', tmp_path / 'out' / 'manifest.json')
    features, manifest = bf.read_raw()
    n = len(fc.counties(_real(fc.PLACES), _real(fc.TREND)))
    assert len(features) == 2 * n  # the geometry-less zone D is left out, and counted
    assert [p['without_geometry'] for p in manifest['products']] == [1] * n
    assert manifest['refused'] == {} and manifest['generalised_deg'] == {}
    blob = (tmp_path / 'out' / 'nfhl-bayarea.esrijson.gz').read_bytes()
    assert manifest['sha256_gz'] == __import__('hashlib').sha256(blob).hexdigest()
    assert json.loads(gzip.decompress(blob))['spatialReference'] == {'wkid': 4326}

    polys, cells = bf.zone_index(features)
    assert bf.classify(-122.28, 37.82, polys, cells) == 'sfha'       # in the AE square
    assert bf.classify(-122.25, 37.85, polys, cells) == 'unknown'    # in its hole, and in no other polygon
    assert bf.classify(-121.82, 37.81, polys, cells) == 'outside'    # in the SECOND part of the zone X
    assert bf.classify(-122.15, 37.85, polys, cells) == 'unknown'    # between the parts: no polygon


def test_a_county_with_no_polygons_fails_and_writes_nothing(tmp_path, monkeypatch):
    def get(url, dest):
        _zip(dest, {'S_FLD_HAZ_AR.shp': b''})
        return 1, 'f' * 64, None

    monkeypatch.setattr(fc, 'download', get)
    monkeypatch.setattr(fc, 'read_layer', lambda src, workdir: ({'features': []}, ''))
    monkeypatch.setattr(fc, 'BETWEEN_S', 0)
    monkeypatch.setattr('sys.argv', ['x', '--out', str(tmp_path / 'out'), '--raw', str(tmp_path / 'raw')])
    assert fc.main() == 1
    report = _real(tmp_path / 'out' / 'failed.json')
    assert report['failed'] and all('not "no flood"' in f['error'] for f in report['failed'])
    assert not (tmp_path / 'out' / 'nfhl-bayarea.esrijson.gz').exists()


def test_a_4xx_or_a_broken_zip_is_one_county_failing_not_the_run(tmp_path, monkeypatch):
    # Code review 2026-10-20: these raised past main(), so the counties after them were never tried and no
    # failed.json was written for the artifact.
    def get(url, dest):
        if url.endswith('NFHL_06001C'):
            raise SystemExit(f'{url}: FEMA answered 403 Forbidden')
        if url.endswith('NFHL_06075C'):
            dest.write_bytes(b'PK\x03\x04 truncated')
        else:
            _zip(dest, {'S_FLD_HAZ_AR.shp': b''})
        return dest.stat().st_size if dest.exists() else 0, 'f' * 64, None

    monkeypatch.setattr(fc, 'download', get)
    monkeypatch.setattr(fc, 'read_layer', lambda src, workdir: (GEOJSON, ''))
    monkeypatch.setattr(fc, 'BETWEEN_S', 0)
    monkeypatch.setattr('sys.argv', ['x', '--out', str(tmp_path / 'out'), '--raw', str(tmp_path / 'raw')])
    assert fc.main() == 1
    report = _real(tmp_path / 'out' / 'failed.json')
    assert [f['product_id'] for f in report['failed']] == ['NFHL_06001C', 'NFHL_06075C']
    assert '403' in report['failed'][0]['error']
    assert len(report['fetched']) == len(fc.counties(_real(fc.PLACES), _real(fc.TREND))) - 2


def test_past_the_deadline_no_county_is_started(tmp_path, monkeypatch):
    monkeypatch.setattr(fc, 'DEADLINE_S', -1)
    monkeypatch.setattr(fc, 'download', lambda url, dest: pytest.fail('a county was started past the deadline'))
    monkeypatch.setattr('sys.argv', ['x', '--out', str(tmp_path / 'out'), '--raw', str(tmp_path / 'raw')])
    assert fc.main() == 1
    assert all(f['error'].startswith('not tried') for f in _real(tmp_path / 'out' / 'failed.json')['failed'])


def test_a_county_sent_a_page_is_asked_again_then_recorded_and_the_rest_still_fetched(tmp_path, monkeypatch):
    # Run 39416950759: Alameda's download came whole, San Francisco's was the portal's page.
    asked = []

    def get(url, dest):
        asked.append(url.rsplit('=', 1)[1])
        if url.endswith('NFHL_06075C'):
            dest.write_bytes(b'<html><head><title>Search</title></head></html>')
        else:
            _zip(dest, {'S_FLD_HAZ_AR.shp': b''})
        return dest.stat().st_size, 'f' * 64, None

    monkeypatch.setattr(fc, 'download', get)
    monkeypatch.setattr(fc, 'read_layer', lambda src, workdir: (GEOJSON, ''))
    monkeypatch.setattr(fc, 'BETWEEN_S', 0)
    monkeypatch.setattr(fc, 'NOT_ZIP_PAUSE_S', 0)
    monkeypatch.setattr('sys.argv', ['x', '--out', str(tmp_path / 'out'), '--raw', str(tmp_path / 'raw')])
    assert fc.main() == 1
    want = [f'NFHL_{f}C' for _, f in fc.counties(_real(fc.PLACES), _real(fc.TREND))]
    assert asked == [p for p in want for _ in range(2 if p == 'NFHL_06075C' else 1)]
    report = _real(tmp_path / 'out' / 'failed.json')
    assert [f['product_id'] for f in report['failed']] == ['NFHL_06075C']
    assert [p['product_id'] for p in report['fetched']] == [p for p in want if p != 'NFHL_06075C']
    assert (tmp_path / 'out' / report['failed'][0]['reply_kept']).read_bytes().startswith(b'<html>')
    assert not (tmp_path / 'out' / 'nfhl-bayarea.esrijson.gz').exists()
    assert not (tmp_path / 'out' / 'manifest.json').exists()
