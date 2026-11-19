"""Shared test set-up for the backend suite.

AIR MEASURED NEARBY (2026-11-18). /v1/environment reads the site's own sensor and monitor files over HTTPS
(app.build_air_nearby). No test may reach the network for them, and the tests written before the block existed
assert their responses' notices exactly, so every test gets a stub that answers "nothing nearby" (no block, no
notice): their responses are what they were. Several suites load the score Lambda under their own module names,
so the stub goes on every loaded module that carries the block's builder.

A module imported DURING a test (test_handlers re-imports each Lambda as `app`) is not loaded yet when the stub
goes on, so it would read the real files. For that case `urllib.request.urlopen` is guarded too: a module imported
inside a test binds the guarded one, and a read of either file fails the test by name instead of going out.

backend/tests/test_air_nearby.py sets USES_REAL_AIR_NEARBY and tests the real code against the repo's own files.
"""

import sys
import urllib.request

import pytest

AIR_PATHS = ('/data/breathe-london-sensors.json', '/data/aurn-sites.json')


@pytest.fixture(autouse=True)
def _no_air_files_from_the_network(request, monkeypatch):
    if getattr(request.module, 'USES_REAL_AIR_NEARBY', False):
        yield
        return
    for mod in list(sys.modules.values()):
        if getattr(mod, 'AIR_FILES', None) is not None and callable(getattr(mod, 'build_air_nearby', None)):
            monkeypatch.setattr(mod, 'build_air_nearby', lambda *a, **k: (None, []))
    real = urllib.request.urlopen

    def guarded(req, *args, **kwargs):
        url = getattr(req, 'full_url', req)
        if isinstance(url, str) and url.endswith(AIR_PATHS):
            raise AssertionError(f'a test reached the network for {url}: stub build_air_nearby on the module it imported')
        return real(req, *args, **kwargs)

    monkeypatch.setattr(urllib.request, 'urlopen', guarded)
    yield
