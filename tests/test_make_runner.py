"""Tests for scripts/make.py, the GNU-Make-free Makefile runner.

Why these exist: the Makefile is the one holder of every deploy recipe, and
`make` is on no PATH in Git Bash here, so the recipes were being retyped or
hand-expanded. The 13 Sep throwaway expander was wrong twice before it was
right - its variable regex excluded digits (so `$(S3_BUCKET)` survived
unexpanded and its own leftover check, written with the same regex, said
clean) and it left make's `@` prefix on (so `data-deploy` died on its first
`@echo` under `set -e`). Both are pinned here, and the real Makefile is
parsed end to end so a construct the runner cannot handle fails this test
rather than a deploy.

Offline only: `--dry-run` runs nothing, and the real-Makefile checks only
expand text.
"""

import importlib.util
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location('make_runner', REPO_ROOT / 'scripts' / 'make.py')
mk = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mk)


def _parse(text):
    return mk.parse(textwrap.dedent(text).replace('    \t', '\t'))


# --- variables ----------------------------------------------------------------


def test_digits_in_variable_names_expand():
    # The 13 Sep expander's first bug: `[A-Za-z_]+` cannot see S3_BUCKET.
    v, _ = _parse('S3_BUCKET = london-flight-map-frontend\n')
    assert mk.expand('s3://$(S3_BUCKET)/x', v) == 's3://london-flight-map-frontend/x'


def test_recursive_expansion_and_dollar_escape():
    v, _ = _parse('A = one\nB = $(A)-two\n')
    assert mk.expand('$(B) costs $$5', v) == 'one-two costs $5'


def test_conditional_assignment_defers_to_environment(monkeypatch):
    monkeypatch.setenv('AWS_PROFILE_NAME', 'other')
    v, _ = _parse('AWS_PROFILE_NAME ?= flightmap\n')
    assert 'AWS_PROFILE_NAME' not in v
    assert mk.expand('$(AWS_PROFILE_NAME)', v) == 'other'


def test_plain_assignment_beats_environment(monkeypatch):
    monkeypatch.setenv('S3_BUCKET', 'wrong')
    v, _ = _parse('S3_BUCKET = right\n')
    assert mk.expand('$(S3_BUCKET)', v) == 'right'


def test_undefined_variable_expands_empty_with_a_warning(capsys, monkeypatch):
    monkeypatch.delenv('NOPE_UNDEFINED', raising=False)
    mk._warned.clear()
    assert mk.expand('[$(NOPE_UNDEFINED)]', {}) == '[]'
    assert 'NOPE_UNDEFINED' in capsys.readouterr().err


def test_command_line_assignment_wins(monkeypatch, tmp_path, capsys):
    mf = tmp_path / 'Makefile'
    mf.write_text('IN = default\nt:\n\techo $(IN)\n')
    mk.main(['-n', '-f', str(mf), 't', 'IN=given'])
    assert 'echo given' in capsys.readouterr().out


# --- recipes --------------------------------------------------------------------


def test_silent_and_ignore_prefixes_are_stripped_before_the_shell(tmp_path, capsys):
    # The 13 Sep expander's second bug: `@echo` reached sh as a command named
    # "@echo" and the target died on line 3 under set -e.
    mf = tmp_path / 'Makefile'
    mf.write_text('t:\n\t@echo hidden\n\t-false\n\techo shown\n')
    mk.main(['-n', '-f', str(mf), 't'])
    out = capsys.readouterr().out
    assert 'echo hidden' in out and '@echo' not in out
    assert 'false' in out and '-false' not in out


def test_ignore_prefix_lets_the_target_continue(tmp_path, capsys):
    mf = tmp_path / 'Makefile'
    mf.write_text('t:\n\t-exit 3\n\techo reached\n')
    mk.main(['-f', str(mf), 't'])
    assert 'reached' in capsys.readouterr().out


def test_failure_without_ignore_stops_the_target(tmp_path):
    mf = tmp_path / 'Makefile'
    mf.write_text('t:\n\texit 3\n\techo never\n')
    with pytest.raises(SystemExit) as e:
        mk.main(['-f', str(mf), 't'])
    assert 'exit 3' in str(e.value)


def test_continuations_join_and_comment_lines_are_skipped(tmp_path, capsys):
    mf = tmp_path / 'Makefile'
    mf.write_text('t:\n\t# a comment in the recipe\n\techo one \\\n\t\ttwo\n')
    mk.main(['-n', '-f', str(mf), 't'])
    out = [line for line in capsys.readouterr().out.splitlines() if not line.startswith('###')]
    # One command, the comment gone, both halves of the continuation on it.
    assert len(out) == 1
    assert out[0].split() == ['echo', 'one', 'two']


def test_dependencies_run_first_each_once(tmp_path, capsys):
    mf = tmp_path / 'Makefile'
    mf.write_text('all: b c\nb: c\n\techo b\nc:\n\techo c\n')
    mk.main(['-n', '-f', str(mf), 'all'])
    heads = [line for line in capsys.readouterr().out.splitlines() if line.startswith('###')]
    assert heads == ['### c', '### b', '### all']


def test_unknown_target_is_an_error(tmp_path):
    mf = tmp_path / 'Makefile'
    mf.write_text('t:\n\techo\n')
    with pytest.raises(SystemExit, match='no such target'):
        mk.main(['-n', '-f', str(mf), 'nope'])


# --- refusals: what the runner must NOT pretend to understand ---------------------


@pytest.mark.parametrize(
    'line',
    [
        'FILES := $(wildcard data/*.json)',
        'NOW := $(shell date)',
        'ifeq ($(X),1)',
        'include other.mk',
        'define BLOCK',
    ],
)
def test_unsupported_constructs_are_refused_by_line(line):
    with pytest.raises(SystemExit) as e:
        mk.parse(f'{line}\nt:\n\techo\n')
    assert 'Makefile:1' in str(e.value)


# --- the real Makefile --------------------------------------------------------------


def test_the_real_makefile_parses_and_every_target_expands(monkeypatch):
    for name in ('IN', 'OUT', 'ARGS', 'KEYSTORE_PATH'):
        monkeypatch.setenv(name, 'x')
    v, targets = mk.parse((REPO_ROOT / 'Makefile').read_text(encoding='utf-8'))
    assert len(targets) >= 20
    for name, (deps, lines) in targets.items():
        for dep in deps:
            assert dep in targets, f'{name} depends on undeclared {dep}'
        for raw in lines:
            out = mk.expand(raw, v)
            assert '$(' not in out and '${' not in out, (name, out)


def test_web_deploy_all_ships_fonts_first():
    # Three font files are in sw.js SHELL_ASSETS and cache.addAll() is atomic:
    # sw.js before the fonts exist at the origin stops the service worker
    # installing for every city (CLAUDE.md, Build & Deploy).
    _, targets = mk.parse((REPO_ROOT / 'Makefile').read_text(encoding='utf-8'))
    order = mk.plan('web-deploy-all', targets)
    assert order[0] == 'fonts-deploy'
    assert order.index('data-deploy') < order.index('pwa-deploy')


def test_data_deploy_names_the_files_the_drift_gate_expects():
    # check_deploy_drift.sh derives its data list from this same target with a
    # floor of 17; the runner must see every one of them.
    v, targets = mk.parse((REPO_ROOT / 'Makefile').read_text(encoding='utf-8'))
    files = set()
    for raw in targets['data-deploy'][1]:
        files.update(tok for tok in mk.expand(raw, v).split() if tok.startswith('data/'))
    assert len(files) >= 17, sorted(files)
    assert 'data/borough-extra.json' in files


def test_deploy_hpi_roll_no_longer_retypes_web_recipes():
    # The whole point of the runner: the roll runbook calls the Makefile's
    # targets through it instead of carrying its own copy of the commands.
    text = (REPO_ROOT / 'scripts' / 'deploy_hpi_roll.sh').read_text(encoding='utf-8')
    assert 'scripts/make.py' in text
    assert 'aws s3 cp index.html' not in text
    assert 'aws s3 sync area/' not in text
