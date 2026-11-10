"""`check_noise_legend.py --live` when DEFRA's style server does not answer.

On 8-9 Nov 2026 three full preflights went red on `noise legend == publishers` because DEFRA's GetStyles request timed
out (one probe answered in 0.2 s, the next hung 90 s); each time the check passed when run alone. A server that does not
answer says nothing about the legend, so it now gets one retry and then INCONCLUSIVE (preflight names it, never PASS).
Anything that IS an answer still fails: a 404, a page without the ColorMap, or a ColorMap that differs. That is how a
moved or restyled layer shows, and it must stay red.
"""

import importlib.util
import socket
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('check_noise_legend', ROOT / 'scripts' / 'check_noise_legend.py')
cnl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cnl)

DEFRA = cnl.scale_from_index('NOISE_SCALE_DEFRA_LDEN')
BTS = cnl.scale_from_index('NOISE_SCALE_BTS')


def sld_for(bands):
    """DEFRA's style as GetStyles writes it: each entry's quantity is its band's UPPER bound."""
    entries = [f'<ColorMapEntry color="#FFFFFF" opacity="0.5" quantity="{bands[0][0]}"/>']
    for i, (_, colour) in enumerate(bands):
        upper = bands[i + 1][0] if i + 1 < len(bands) else bands[i][0] + 5
        entries.append(f'<ColorMapEntry color="{colour}" opacity="1" quantity="{upper}"/>')
    return '<ColorMap>' + ''.join(entries) + '</ColorMap>'


def run(monkeypatch, capsys, answers):
    """main() --live with each DEFRA request taking the next of `answers` (an exception to raise, or text)."""
    calls = []

    def fake_fetch(url):
        calls.append(url)
        a = answers[len(calls) - 1]
        if isinstance(a, BaseException):
            raise a
        return a

    monkeypatch.setattr(cnl, 'fetch', fake_fetch)
    monkeypatch.setattr(cnl, 'check_png', lambda defra: [])
    monkeypatch.setattr(cnl, 'bts_painted_colours', lambda: ({c for _, c in BTS}, len(cnl.BTS_SAMPLES)))
    if hasattr(cnl, 'time'):  # the retry's pause; absent before the retry existed, so the red is on behaviour
        monkeypatch.setattr(cnl.time, 'sleep', lambda s: None)
    monkeypatch.setattr(cnl.sys, 'argv', ['check_noise_legend.py', '--live'])
    code = 0
    try:
        cnl.main()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    return code, capsys.readouterr().out, len(calls)


def test_the_parser_reads_its_own_fixture():
    # The fixture is only evidence if the real parser reads it back as the site's scale.
    import re

    entries = re.findall(r'ColorMapEntry color="(#[0-9A-Fa-f]{6})" opacity="[\d.]+" quantity="(\d+)"', sld_for(DEFRA))
    published = [
        (int(entries[i - 1][1]), entries[i][0].upper())
        for i in range(1, len(entries))
        if entries[i][0].upper() not in cnl.DEFRA_INVISIBLE
    ]
    assert published == DEFRA


def test_a_timeout_then_an_answer_is_ok(monkeypatch, capsys):
    code, out, calls = run(monkeypatch, capsys, [TimeoutError('The read operation timed out'), sld_for(DEFRA)])
    assert code == 0 and calls == 2
    assert 'ok   the legend describes the overlay' in out
    assert 'INCONCLUSIVE' not in out


def test_no_answer_twice_is_inconclusive_never_ok(monkeypatch, capsys):
    code, out, calls = run(
        monkeypatch, capsys, [ConnectionResetError('reset by peer'), urllib.error.URLError(TimeoutError('timed out'))]
    )
    assert code == 0 and calls == 2
    assert any(line.strip().startswith('INCONCLUSIVE') for line in out.splitlines())
    assert 'ok   the legend describes the overlay' not in out


def test_a_gateway_error_twice_is_inconclusive(monkeypatch, capsys):
    bad = urllib.error.HTTPError('https://environment.data.gov.uk', 502, 'Bad Gateway', {}, None)
    code, out, calls = run(monkeypatch, capsys, [bad, bad])
    assert code == 0 and calls == 2 and 'INCONCLUSIVE' in out


@pytest.mark.parametrize(
    'answer',
    [
        urllib.error.HTTPError('https://environment.data.gov.uk', 404, 'Not Found', {}, None),
        urllib.error.URLError(socket.gaierror(11001, 'getaddrinfo failed')),
        '<html>Service moved</html>',
        sld_for([(b, '#123456') for b, _ in DEFRA]),
    ],
)
def test_an_answer_that_is_wrong_still_fails(monkeypatch, capsys, answer):
    code, out, calls = run(monkeypatch, capsys, [answer, sld_for(DEFRA)])
    assert code == 1, out
    assert calls == 1, 'a real answer is not retried'
    assert 'FAIL' in out
