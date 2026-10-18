"""The US crime and road scales (Bill, 2026-10-18): LINEAR on a California anchor.

10 at zero, 5.0 at the anchor, 0 at double or more; None stays None. The anchors are read from the generated
Bay Area files (California's rate over every agency; its statewide road share), never typed here, and the checks
on those files are PROPERTIES of the scale, not today's figures for named cities, which change with each roll.
Not wired into any score until the Bay Area's release.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambdas', 'score'))

import app  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), '..', '..', 'data')


def _load(name):
    with open(os.path.join(DATA, name), encoding='utf-8') as fh:
        return json.load(fh)


class UsScaleTest(unittest.TestCase):
    def test_the_shape(self):
        self.assertEqual(app.us_anchored_to_score(0, 22.27), 10.0)
        self.assertEqual(app.us_anchored_to_score(22.27, 22.27), 5.0)
        self.assertEqual(app.us_anchored_to_score(44.54, 22.27), 0.0)
        self.assertEqual(app.us_anchored_to_score(469.3, 22.27), 0.0)  # Colma: clamped, not negative
        self.assertAlmostEqual(app.us_anchored_to_score(11.135, 22.27), 7.5)

    def test_absent_is_absent_and_an_anchor_must_be_real(self):
        self.assertIsNone(app.us_anchored_to_score(None, 22.27))
        for bad in (0, -1, None):
            with self.assertRaises(ValueError):
                app.us_anchored_to_score(5.0, bad)

    def _check_file(self, rows, anchor):
        scores = {name: app.us_anchored_to_score(v, anchor) for name, v in rows}
        self.assertTrue(scores)
        for name, v in rows:
            s = scores[name]
            self.assertTrue(0.0 <= s <= 10.0, name)
            self.assertEqual(s == 0.0, v >= 2 * anchor, name)   # 0 exactly at double or more
            self.assertEqual(s == 10.0, v == 0, name)           # 10 only with none at all
            self.assertEqual(s > 5.0, v < anchor, name)         # better than California only when lower
        ordered = sorted(rows, key=lambda r: r[1])
        self.assertEqual([scores[n] for n, _ in ordered], sorted(scores.values(), reverse=True))

    def test_crime_on_its_derived_anchor(self):
        doc = _load('us-bayarea-crime.json')
        anchor = doc['california']['per_1000']
        self.assertEqual(anchor, round(1000 * doc['california']['crimes'] / doc['california']['population'], 2))
        self._check_file([(r['name'], r['per_1000']) for r in doc['cities'] if r['per_1000'] is not None], anchor)
        # the sheriff-contract cities have no rate, so no score, never a stand-in
        self.assertTrue(all(app.us_anchored_to_score(r['per_1000'], anchor) is None
                            for r in doc['cities'] if r['per_1000'] is None))

    def test_road_on_its_derived_anchor(self):
        doc = _load('us-bayarea-road.json')
        self._check_file([(r['name'], r['share_at_or_above_45_db_pct']) for r in doc['cities']],
                         doc['california']['share_at_or_above_45_db_pct'])


if __name__ == '__main__':
    unittest.main()
