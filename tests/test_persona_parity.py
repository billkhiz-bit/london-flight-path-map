"""The persona weights exist twice — keep them identical.

`index.html` scores entirely client-side and carries its own copy of PERSONAS;
the score Lambda carries the authoritative one. Nothing linked them, so the two
could drift silently and the site would quietly disagree with its own API about
what a place scores. That is the worst kind of bug for this product: both
answers look confident and neither is flagged.

Added 2026-07-30 alongside methodology v3.3, which had to edit both copies by
hand to move growth out of every persona except `investor`.
"""

import os
import re

import pytest

from .conftest import load_lambda

INDEX_HTML = os.path.normpath(os.path.join(os.path.dirname(__file__), os.pardir, "index.html"))

score_app = load_lambda("score", "score_app_personas")


def _frontend_personas():
    """Parse the PERSONAS literal out of index.html.

    Deliberately a regex over the source rather than a JS engine: the block is a
    flat object literal, and requiring node to run this test would make it easy
    to skip.
    """
    with open(INDEX_HTML, encoding="utf-8") as handle:
        source = handle.read()
    match = re.search(r"const PERSONAS = \{(.*?)\n      \};", source, re.S)
    assert match, "could not locate the PERSONAS block in index.html"
    block = match.group(1)
    found = {}
    # `env` joined at methodology v3.9, 2026-08-26. The keys are NOT optional
    # in this pattern on purpose: making the new one optional would let a
    # frontend copy that silently lost `env` still parse, and this file's whole
    # job is that the two copies cannot diverge quietly. A missing key fails
    # test_frontend_parses below with "the regex needs updating", which is the
    # loud failure - the alternative is a persona parsing to four weights,
    # comparing equal on those four, and passing while the site scores a
    # component the API does not.
    pattern = re.compile(
        r"(\w+):\s*\{.*?weights:\s*\{\s*quiet:\s*([\d.]+),\s*afford:\s*([\d.]+),"
        r"\s*growth:\s*([\d.]+),\s*live:\s*([\d.]+),\s*env:\s*([\d.]+)\s*\}",
        re.S,
    )
    for entry in pattern.finditer(block):
        found[entry.group(1)] = {
            "quiet": float(entry.group(2)),
            "afford": float(entry.group(3)),
            "growth": float(entry.group(4)),
            "live": float(entry.group(5)),
            "env": float(entry.group(6)),
        }
    return found


def test_frontend_parses():
    assert len(_frontend_personas()) >= 8, "persona parsing broke; the regex needs updating"


def test_same_persona_names_in_both():
    assert set(_frontend_personas()) == set(score_app.PERSONAS)


@pytest.mark.parametrize("persona", sorted(score_app.PERSONAS))
def test_weights_match_backend(persona):
    frontend = _frontend_personas()[persona]
    backend = score_app.PERSONAS[persona]
    assert frontend == pytest.approx(backend), (
        f"{persona} differs: index.html={frontend} lambda={backend}. "
        "Both copies must be edited together."
    )


@pytest.mark.parametrize("persona", sorted(score_app.PERSONAS))
def test_weights_sum_to_one_in_frontend(persona):
    assert sum(_frontend_personas()[persona].values()) == pytest.approx(1.0, abs=0.005)


def test_only_investor_weights_growth():
    """Methodology v3.3. Growth described the market, not the property, and was
    responsible for 87% of all score movement in the Q1->Q2 refresh while nothing
    physical about any borough changed. It is weighted only where expected return
    is the actual question being asked.
    """
    for name, weights in score_app.PERSONAS.items():
        if name == "investor":
            assert weights["growth"] > 0, "investor must still weight growth"
        else:
            assert weights["growth"] == 0, f"{name} should not weight growth under v3.3"
