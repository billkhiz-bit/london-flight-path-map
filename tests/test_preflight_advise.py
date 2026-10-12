"""preflight.sh's advisory runner must tell a CRASHED gate from one that measured a deviation.

On 2026-10-12 `fit_airport_shape.py --check` died on a tuple unpack, and `advise()`
printed it as "deviates" inside a PASSing preflight, because a traceback and a
measured disagreement both exit 1 and the runner read only the exit code (Bill's
2026-09-04 ruling: read the output). These run the REAL functions, cut out of
scripts/preflight.sh, against real crashing and real deviating commands.
"""
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / 'scripts' / 'preflight.sh'
# The shell preflight itself runs under. Missing means these cannot run, which
# must fail, not skip: a skipped test of a gate is a gate nobody tested.
SH = shutil.which('sh')
if SH is None:
    raise RuntimeError('no `sh` on PATH; tests/test_preflight_advise.py runs preflight.sh functions in it')


def functions():
    """advise() and advisory_verdict(), exactly as preflight.sh defines them."""
    text = PREFLIGHT.read_text(encoding='utf-8').replace('\r\n', '\n')
    out = []
    for name in ('advise', 'advisory_verdict'):
        m = re.search(rf'^{name}\(\) \{{\n.*?^\}}\n', text, re.S | re.M)
        if not m:
            raise AssertionError(f'{name}() not found in {PREFLIGHT}')
        out.append(m.group(0))
    return '\n'.join(out)


def advise(*cmd):
    """Run advise() on one command; return (printed text, INCONCLUSIVE, ADVISORY)."""
    script = (
        'ADVISORY=""; INCONCLUSIVE=""\n' + functions() +
        '\nadvise "stage" "$@"\nprintf "\\nINC=%s\\nADV=%s\\n" "$INCONCLUSIVE" "$ADVISORY"\n'
    )
    # sh on PATH, functions cut from our own preflight.sh and commands this file
    # wrote: fixed, not untrusted, input.
    res = subprocess.run(  # noqa: S603
        [SH, '-c', script, 'sh', *cmd], capture_output=True, text=True, check=True
    )
    body, inc, adv = res.stdout.rsplit('\n', 3)[0], *res.stdout.strip().splitlines()[-2:]
    return body, inc.removeprefix('INC='), adv.removeprefix('ADV=')


PY = sys.executable
NODE = shutil.which('node') or 'node'


class AdviseTests(unittest.TestCase):
    def test_a_python_crash_is_crashed_not_deviates(self):
        body, inc, adv = advise(PY, '-c', 'rows = [(1, 2, 3)]\nfor a, b in rows: pass')
        self.assertIn('CRASHED', body)
        self.assertIn('ValueError', body)  # the line that says why
        self.assertEqual(inc, '|stage (crashed)')
        self.assertEqual(adv, '')

    def test_a_node_crash_is_crashed_sync_and_async(self):
        for code in ("throw new Error('boom')", "await Promise.reject(new Error('later'))"):
            with self.subTest(code=code):
                body, inc, adv = advise(NODE, '--input-type=module', '-e', code)
                self.assertIn('CRASHED', body)
                self.assertEqual(inc, '|stage (crashed)')
                self.assertEqual(adv, '')

    def test_a_measured_deviation_stays_deviates(self):
        body, inc, adv = advise(PY, '-c', 'print("3 of 9 boroughs differ"); raise SystemExit(1)')
        self.assertIn('deviates', body)
        self.assertEqual((inc, adv), ('', '|stage'))

    def test_a_deviation_quoting_a_stack_line_is_not_a_crash(self):
        # A gate may print a location in its report; only the crash markers count.
        body, _, adv = advise(PY, '-c', 'print("    at check (tests/x.mjs:12:5)"); raise SystemExit(1)')
        self.assertIn('deviates', body)
        self.assertEqual(adv, '|stage')

    def test_a_pass_and_an_inconclusive_are_unchanged(self):
        self.assertIn('ok', advise(PY, '-c', 'print("all agree")')[0])
        body, inc, _ = advise(PY, '-c', 'print("INCONCLUSIVE: no raster on disk")')
        self.assertIn('INCONCLUSIVE', body)
        self.assertEqual(inc, '|stage')


if __name__ == '__main__':
    unittest.main()
