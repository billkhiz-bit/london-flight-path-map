"""preflight.sh's fixed log must never cost the gate its verdict (2026-11-08).

Every run tees its output to .preflight/last.log by running itself again through tee. A pipeline exits with its
LAST stage, tee, which is always 0: the exact lie the top of preflight.sh records (`anything | tail`). So the inner
run writes its exit code to .preflight/last.exit and the outer run exits with that. These tests run the real block,
cut from our own preflight.sh, in front of a stand-in for the checks, and hold:

- the outer run exits with the inner run's code, a failure included, and the log holds the run's output;
- the progress panel's pointer (only where ~/.claude/progress exists) is valid JSON naming that log, with the stage
  count and the duration read from the previous run, never typed;
- with no ~/.claude/progress, nothing is written outside the repo.

HOME is a temporary folder throughout, so a test run never touches a real panel.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PREFLIGHT = ROOT / 'scripts' / 'preflight.sh'
SH = shutil.which('sh')
pytestmark = pytest.mark.skipif(SH is None, reason='no `sh` on PATH')


def head_through_log_block() -> str:
    """preflight.sh from its first line to the end of the log block: options, cd, and the block itself."""
    lines = PREFLIGHT.read_text(encoding='utf-8').replace('\r\n', '\n').split('\n')
    start = next(i for i, line in enumerate(lines) if line.startswith('# ONE LOG FOR EVERY RUN'))
    end = next(i for i in range(start, len(lines)) if lines[i] == 'fi')
    return '\n'.join(lines[: end + 1]) + '\n'


def make_repo(tmp: Path, code: int) -> Path:
    """A folder laid out like the repo, whose preflight.sh is ours up to the block, then a stand-in for the checks."""
    repo = tmp / 'repo'
    (repo / 'scripts').mkdir(parents=True)
    body = (
        'echo "PREFLIGHT, stand-in"\n'
        'echo "  first stage                      PASS"\n'
        'echo "  second stage                     ok"\n'
        f'exit {code}\n'
    )
    (repo / 'scripts' / 'preflight.sh').write_text(head_through_log_block() + body, encoding='utf-8', newline='\n')
    return repo


def run(repo: Path, home: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, 'HOME': str(home)}
    env.pop('PREFLIGHT_INNER', None)
    # Our own script, in a temporary copy we wrote, run by the `sh` on PATH: no outside input reaches the command.
    return subprocess.run(  # noqa: S603
        [SH, 'scripts/preflight.sh'], cwd=repo, env=env, capture_output=True, text=True, timeout=60
    )


@pytest.mark.parametrize('code', [0, 1, 3])
def test_the_outer_run_exits_with_the_inner_runs_code(tmp_path, code):
    repo = make_repo(tmp_path, code)
    home = tmp_path / 'home'
    home.mkdir()
    done = run(repo, home)
    assert done.returncode == code, done.stderr
    log = (repo / '.preflight' / 'last.log').read_text(encoding='utf-8')
    assert 'first stage' in log and 'second stage' in log
    assert 'first stage' in done.stdout, 'the run still prints to its caller, not only to the log'
    assert (repo / '.preflight' / 'last.exit').read_text().strip() == str(code)


def test_the_panel_pointer_reads_the_previous_run(tmp_path):
    repo = make_repo(tmp_path, 0)
    home = tmp_path / 'home'
    (home / '.claude' / 'progress').mkdir(parents=True)
    run(repo, home)
    first = json.loads((home / '.claude' / 'progress' / 'job.json').read_text())
    # A first run has no previous log: no total and no expected time, rather than a guess.
    assert 'total' not in first and 'expectedMs' not in first
    assert first['log'].replace('\\', '/').endswith('/.preflight/last.log') and first['format'] == 'preflight'
    run(repo, home)
    second = json.loads((home / '.claude' / 'progress' / 'job.json').read_text())
    assert second['total'] == 2, "the stage count is the previous log's, as the panel counts them"
    assert second['expectedMs'] >= 0 and second['startedAt'] >= first['startedAt']


def test_no_panel_folder_means_nothing_written_outside_the_repo(tmp_path):
    repo = make_repo(tmp_path, 0)
    home = tmp_path / 'home'
    home.mkdir()
    run(repo, home)
    assert not any(home.rglob('*')), 'a machine without the panel gets no ~/.claude folder from preflight'
