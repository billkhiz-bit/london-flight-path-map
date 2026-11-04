"""When a flood sample is too small to fail on (scripts/check_flood_georef.py needs_confirming).

The network half is proven by hand on a shifted mosaic (docs/lessons/flood.md): this holds the decision, which is the
part that could quietly weaken the gate. Each result is (agree, compared, unreachable, rate).
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'scripts'))
pytest.importorskip('rasterio')
import check_flood_georef as gate  # noqa: E402


def result(agree, compared, unreachable=0):
    return (agree, compared, unreachable, agree / compared if compared else 0.0)


def test_one_miss_in_four_asks_for_a_bigger_sample():
    assert gate.needs_confirming({'medium-or-high': result(3, 4), 'not-moh': result(4, 4)}, 4)


def test_a_clean_sample_goes_no_further():
    assert not gate.needs_confirming({'medium-or-high': result(4, 4), 'not-moh': result(4, 4)}, 4)


def test_the_bigger_sample_is_final():
    """Otherwise a failing mosaic would be re-sampled for ever and never reported."""
    assert not gate.needs_confirming({'medium-or-high': result(5, 16)}, gate.CONFIRM_PER_CLASS)


def test_too_few_compared_stays_inconclusive_and_is_never_re_run_into_a_pass():
    assert not gate.needs_confirming({'medium-or-high': result(1, 2, unreachable=2)}, 4)


def test_a_class_with_no_interior_stays_untested():
    assert not gate.needs_confirming({'medium-or-high': None, 'not-moh': result(4, 4)}, 4)


def test_no_mosaic_stays_a_failure():
    assert not gate.needs_confirming(None, 4)


def test_the_bar_did_not_move():
    assert gate.MIN_AGREE == 0.80
    assert gate.CONFIRM_PER_CLASS >= 4 * 4, 'a confirmation must be a much bigger sample than the one it questions'


def test_a_confirmation_lets_one_honest_miss_through_and_stops_one_bad_edge():
    """16 samples take the whole 4x4 grid, so a bad edge is diluted: its bar must sit between these two."""
    one_boundary_cell, one_bad_edge = 15 / 16, 13 / 16
    assert one_bad_edge < gate.CONFIRM_AGREE <= one_boundary_cell
    assert one_bad_edge >= gate.MIN_AGREE, 'the plain bar would have passed it: why the confirmation has its own'


def test_a_throttled_confirmation_cannot_overrule_a_failure():
    assert gate.CONFIRM_MIN_COMPARED >= gate.CONFIRM_PER_CLASS * 3 / 4
