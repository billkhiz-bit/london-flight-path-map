"""The published sample street report has no text under 8 pt, chart labels included (audit M-6, 2026-11-13).

The measure is scripts/report_text_floor.py, the one holder: scripts/address_noise_report.mjs refuses any report that
breaks the floor, and this holds the copy every visitor downloads. pdfium's unit is checked before its floor is
trusted (the body must read 10.5 pt), and the reader must see the near-floor chart labels, or a floor that reads
nothing would pass.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import report_text_floor as floor  # noqa: E402

SAMPLES = sorted((ROOT / 'home' / 'reports').glob('sample-street-report-*.pdf'))


class SampleReportTextFloorTests(unittest.TestCase):
    def test_there_is_a_sample_to_check(self):
        self.assertTrue(SAMPLES, 'no home/reports/sample-street-report-*.pdf: the floor checked nothing')

    def test_the_unit_is_points(self):
        # Body, tables and notes are 10.5 pt (Bill's three-page build). If pdfium ever reports points rather than
        # Chrome's CSS px, this reads 7.875 and the floor below would be measuring the wrong thing.
        for pdf in SAMPLES:
            with self.subTest(pdf=pdf.name):
                self.assertEqual(floor.body_size(floor.char_sizes(pdf)), 10.5)

    def test_nothing_under_8_pt(self):
        for pdf in SAMPLES:
            with self.subTest(pdf=pdf.name):
                runs = floor.runs_under(floor.char_sizes(pdf))
                self.assertEqual(runs, [], f'{pdf.name}: text under 8 pt: {runs[:6]}')

    def test_the_reader_sees_the_labels_nearest_the_floor(self):
        # The chart labels sit within 0.25 pt of the floor: a floor raised to 8.3 must find some on every sample,
        # pictures included, or the reader is blind to exactly the text this rule is for.
        for pdf in SAMPLES:
            with self.subTest(pdf=pdf.name):
                self.assertTrue(floor.runs_under(floor.char_sizes(pdf), 8.3), f'{pdf.name}: nothing read near 8 pt')

    def test_runs_are_split_by_page_and_by_size(self):
        sizes = [(1, 7.0, 'a'), (1, 7.5, 'b'), (1, 10.5, 'c'), (1, 7.0, 'd'), (2, 7.0, 'e'), (2, 7.96, 'f')]
        self.assertEqual(floor.runs_under(sizes), [(1, 7.0, 'ab'), (1, 7.0, 'd'), (2, 7.0, 'e')])


if __name__ == '__main__':
    unittest.main()
