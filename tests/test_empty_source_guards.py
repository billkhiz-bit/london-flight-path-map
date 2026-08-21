"""An empty data source must produce NO band, never a reassuring one.

Audit findings C10 and C11, both fixed 2026-08-21. They are the same defect in
two builders, and it is the defect this repo has paid for more than any other:
an absence rendering as a confident measurement.

C10 - build_borough_bands.py
    `points_within()` returned `0.0` when the station or GP index was EMPTY, so
    `transport_band(0.0)` answered 'poor' and `health_band(0.0)` answered
    'moderate' for every borough in the country. `transport` is 0.25 of
    liveability, and `--write-lambda` copies the value into the score Lambda,
    so BOTH holders got the same wrong number and
    tests/test_borough_data_parity.py stayed green comparing them.

    The file-exists guards could not see it: a NaPTAN export with a renamed
    StopType or Easting column opens, parses, and yields nothing.

C11 - fetch_ea_flood_risk.py
    (255,255,255,0) is a KNOWN colour meaning 'not in any modelled risk
    polygon', so a fully transparent render passed classify() without raising
    and became 100% code 0 - 'low risk, fully surveyed'. Every way that service
    fails while still returning a valid PNG produces exactly that image. And it
    was permanent: the 4 MB .npy defeats the `st_size > 200` re-run skip.

Run: python -m pytest tests/test_empty_source_guards.py
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / 'scripts' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class EmptyIndexProducesNoBand(unittest.TestCase):
    """C10. An empty index is a failed read, not a country with no stations."""

    @classmethod
    def setUpClass(cls):
        cls.b = _load('build_borough_bands')

    POINTS = [(51.5074, -0.1278), (51.5155, -0.1410), (53.4808, -2.2426)]

    def test_empty_grid_returns_none_not_zero(self):
        # The defect itself. 0.0 here is what became 'poor' everywhere.
        self.assertIsNone(self.b.points_within({}, self.POINTS, 800))

    def test_none_share_produces_no_transport_band(self):
        share = self.b.points_within({}, self.POINTS, 800)
        self.assertIsNone(self.b.transport_band(share))

    def test_none_share_produces_no_health_band(self):
        share = self.b.points_within({}, self.POINTS, 1000)
        health_band = getattr(self.b, 'health_band', None)
        if health_band is None:
            self.skipTest('health_band not present in this build')
        self.assertIsNone(health_band(share))

    def test_a_populated_index_with_nothing_nearby_is_still_zero(self):
        """THE DISTINCTION THAT MATTERS, and the reason this is not a blanket
        'treat 0 as None'.

        A real index that genuinely has no station near these points is a
        MEASUREMENT of 0% - the borough really is poorly served, and that must
        still band as 'poor'. Only an EMPTY INDEX is unknown. Collapsing the two
        would swap one silent wrong answer for another.
        """
        # One node, far from every point above (Cornwall, in EPSG:27700).
        grid = {(160, 30): [(160000, 30000)]}
        share = self.b.points_within(grid, self.POINTS, 800)
        self.assertEqual(share, 0.0)
        self.assertEqual(self.b.transport_band(share), 'poor')

    def test_a_populated_index_with_a_hit_measures_it(self):
        # Trafalgar Square in EPSG:27700 is about (530034, 180381).
        grid = {(530, 180): [(530034, 180381)]}
        share = self.b.points_within(grid, [(51.5080, -0.1281)], 800)
        self.assertIsNotNone(share)
        self.assertGreater(share, 0.0)


class BlankFloodTileIsNotLowRisk(unittest.TestCase):
    """C11. A wholly unclassified render is an outage, not a safe area."""

    @classmethod
    def setUpClass(cls):
        cls.f = _load('fetch_ea_flood_risk')

    def test_transparent_is_a_known_colour_and_classifies_as_zero(self):
        """Why the bug existed at all: classify() cannot catch this.

        Transparent white is a LEGITIMATE code 0, so a blank tile is not an
        'unrecognised colour' and classify() has no reason to raise. The guard
        therefore has to live in fetch_tile, on the classified result.
        """
        import numpy as np
        blank = np.zeros((8, 8, 4), dtype='uint8')
        blank[:, :, 0:3] = 255  # (255,255,255,0)
        codes = self.f.classify(blank)
        self.assertEqual(int((codes > 0).sum()), 0)
        self.assertIn((255, 255, 255, 0), self.f.BAND_CODE)

    def test_fetch_tile_refuses_to_cache_a_blank_render(self):
        """The guard, driven through fetch_tile with a stubbed download."""
        import io as _io

        import numpy as np
        from PIL import Image

        img = Image.new('RGBA', (4, 4), (255, 255, 255, 0))
        buf = _io.BytesIO()
        img.save(buf, format='PNG')
        blank_png = buf.getvalue()

        saved = []
        target = REPO / 'tests' / '_tmp_blank_tile.npy'
        orig_fetch, orig_save, orig_sleep = self.f.fetch_bytes, np.save, self.f.time.sleep
        try:
            self.f.fetch_bytes = lambda url: blank_png
            np.save = lambda p, a: saved.append(p)
            self.f.time.sleep = lambda s: None
            ok = self.f.fetch_tile(target, (0, 0, 1, 1))
        finally:
            self.f.fetch_bytes, np.save, self.f.time.sleep = orig_fetch, orig_save, orig_sleep
            if target.exists():
                target.unlink()

        self.assertFalse(ok, 'a blank render must not report success')
        self.assertEqual(saved, [], 'a blank render must never be cached')

    def test_a_tile_with_real_risk_is_kept(self):
        """The other direction, so the guard cannot be satisfied by never saving."""
        import io as _io

        import numpy as np
        from PIL import Image

        img = Image.new('RGBA', (4, 4), (255, 255, 255, 0))
        # One pixel of High risk (3.3% annual chance or greater).
        img.putpixel((0, 0), (85, 91, 157, 255))
        buf = _io.BytesIO()
        img.save(buf, format='PNG')

        saved = []
        target = REPO / 'tests' / '_tmp_real_tile.npy'
        orig_fetch, orig_save = self.f.fetch_bytes, np.save
        try:
            self.f.fetch_bytes = lambda url: buf.getvalue()
            np.save = lambda p, a: saved.append(p)
            ok = self.f.fetch_tile(target, (0, 0, 1, 1))
        finally:
            self.f.fetch_bytes, np.save = orig_fetch, orig_save
            if target.exists():
                target.unlink()

        self.assertTrue(ok)
        self.assertEqual(len(saved), 1, 'a tile carrying real risk must be cached')


if __name__ == '__main__':
    unittest.main()
