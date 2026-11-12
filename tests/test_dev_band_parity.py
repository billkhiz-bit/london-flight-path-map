"""The developers band looks and reads the same on the front page and on /api/ (2026-11-05).

One module drives both (js/dev-demo.mjs), and both pages carry its ids, so a style or a sample changed on one page alone
would leave the module driving two different bands. Neither page can share a stylesheet without a new request on the
front page, so the rules are copied and held here: every rule the band needs must exist on both pages, word for word.

The list is of the rules, not of a pattern: a new band rule on one page must be added here, or it is not held.
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOME = 'home/index.html'
API = 'api/index.html'

RULES = (
    '.ans-tile', '.ans-tile b',
    'section.dev .code', '.code-tabs', '.code-tabs[hidden]', '.code-tabs button', '.code-tabs button:hover',
    ".code-tabs button[aria-selected='true']", "section.dev [role='tabpanel'] + [role='tabpanel']",
    "section.dev .is-tabbed [role='tabpanel'] + [role='tabpanel']", 'section.dev pre', '.code-foot',
    'section.dev button.copy', 'section.dev button.copy:hover', 'section.dev .copy-status', '.code-note',
    '.dev-wire', '.dev-wire::before', '.dev-run.is-waiting:not(.is-answered) .dev-wire',
    '.dev-run.is-waiting:not(.is-answered) .dev-wire::before', '.dev-ln', '.dev-run.is-waiting .dev-ln:not(.is-on)',
    '.dev-n', '.dev-n.is-lit', '.dev-rest', '.dev-caret', '.dev-page', '.dev-page-head', '.dev-tiles',
    '.dev-tiles .ans-tile', '.dev-tiles .ans-tile b', '.dev-tiles .ans-tile b.is-empty', '.dev-tiles .ans-tile.is-lit',
    '.dev-tiles .ans-tile small',
    # The postcode box's list: one module (js/place-box.mjs) on both pages.
    '.pc-list', '.pc-list[hidden]', '.pc-head', '.pc-foot', '.pc-foot:first-child', '.pc-opt', '.pc-opt small', '.pc-opt mark',
    ".pc-opt:hover, .pc-opt[aria-selected='true']", '.pc-live',
)

# Tokens a held rule reads: a page with its own value would change the band without touching a rule.
TOKENS = ('--dark', '--mid', '--paper', '--orange', '--tint', '--font-body', '--font-display', '--font-mono')

# What the module reads by id or selector: a page missing one has a band that half works, in silence.
IDS = ('dev-env', 'dev-env-py', 'dev-env-js', 'dev-run', 'dev-res', 'dev-tiles', 'dev-replay', 'copy-status',
       'code-tab-curl', 'code-tab-py', 'code-tab-js', 'code-curl', 'code-py', 'code-js')


def read(page):
    return (REPO / page).read_text(encoding='utf-8').replace('\r\n', '\n')


def style(page):
    return '\n'.join(re.findall(r'<style>(.*?)</style>', read(page), re.S))


def rule(page, selector):
    found = re.findall(r'^\s*' + re.escape(selector) + r' \{([^\n]*)\}$', style(page), re.M)
    assert len(found) == 1, f'{page}: {len(found)} rules for {selector}'
    return found[0].strip()


def token(page, name):
    found = re.findall(r'(?:^|[\s;{])' + re.escape(name) + r':\s*([^;]+);', style(page), re.M)
    assert found, f'{page}: no {name}'
    return found[0].strip()


def samples(page):
    """Each request as a reader sees it, in the order the page shows them."""
    text = read(page)
    return [re.search(r'<pre[^>]*id="' + name + r'"[^>]*>(.*?)</pre>', text, re.S).group(1) for name in IDS[:3]]


@pytest.mark.parametrize('selector', RULES)
def test_both_pages_style_the_band_alike(selector):
    assert rule(API, selector) == rule(HOME, selector)


@pytest.mark.parametrize('name', TOKENS)
def test_both_pages_give_the_band_the_same_values(name):
    assert token(API, name) == token(HOME, name)


@pytest.mark.parametrize('name', IDS)
def test_both_pages_carry_what_the_module_reads(name):
    for page in (HOME, API):
        assert read(page).count(f'id="{name}"') == 1, f'{page}: id {name}'


def test_both_pages_start_from_the_same_samples():
    assert samples(API) == samples(HOME)


def test_the_samples_stay_on_the_route_that_needs_no_key():
    # /v1/score would spend the public demo key on every visit (js/api-demo.mjs).
    for sample in samples(API):
        assert '/v1/environment' in sample and 'X-Api-Key' not in sample and '/v1/score' not in sample


def test_a_new_band_rule_is_not_left_unheld():
    # Written as a list on purpose, so this is what catches a rule added to one page and not listed.
    for page in (HOME, API):
        selectors = re.findall(r'^\s*((?:\.dev-|\.code-|section\.dev \.code|section\.dev pre|section\.dev button)[^{@/]*?) \{', style(page), re.M)
        assert sorted(set(selectors) - set(RULES)) == ([] if page == API else ['.dev-free', '.dev-free b'])
