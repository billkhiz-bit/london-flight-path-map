"""Run a Makefile target without GNU Make.

Why this exists
---------------
`make` is on no PATH in Git Bash on this machine, and the Makefile is the ONE
holder of every deploy recipe. Without a runner the recipes were retyped -
which is how `OPERATIONS.md` s2 came to upload `privacy.html` to a dead key -
or expanded by hand into `scripts/deploy_hpi_roll.sh`, which then drifts from
the Makefile on the next edit. The 13 Sep expander that did that was wrong
twice before it was right (its variable regex excluded digits, so
`$(S3_BUCKET)` survived; it left make's `@` prefix on, so `data-deploy` died
on line 3 under `set -e`). Both are covered by `tests/test_make_runner.py`.

What it implements, and deliberately nothing more
-------------------------------------------------
- `NAME = v`, `NAME := v`, `NAME ?= v` (env wins over `?=`, as in make)
- `$(NAME)` / `${NAME}` expansion, recursive; `$$` -> `$`
- `target: dep dep` with tab-indented recipe lines, backslash continuations
- `@` (silent) and `-` (ignore failure) recipe prefixes
- deps run first, each once, depth-first

Not implemented, and the parser REFUSES rather than guessing: `$(shell ...)`,
`$(wildcard ...)`, any `$(func ...)`, `ifeq`/`ifdef`, `include`, `define`,
pattern rules, automatic variables. If the Makefile grows one of these, this
prints which line and exits 2 - do not "support" it here, install GNU Make.

Usage
-----
    python scripts/make.py web-deploy-all
    python scripts/make.py --dry-run data-deploy      # print, run nothing
    python scripts/make.py --list

Every recipe line runs through `sh -c` with MSYS_NO_PATHCONV=1, because Git
Bash rewrites '/index.html' into a Windows path and CloudFront rejects the
whole invalidation batch (CLAUDE.md, Build & Deploy).
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

VAR_RE = re.compile(r'\$\(([A-Za-z_][A-Za-z0-9_]*)\)|\$\{([A-Za-z_][A-Za-z0-9_]*)\}')
FUNC_RE = re.compile(
    r'\$\((shell|wildcard|foreach|call|if|patsubst|subst|filter|sort|dir|notdir|basename|addprefix|addsuffix|eval|value|origin|error|warning|info)\b'
)
ASSIGN_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)\s*(\?=|:=|=)\s*(.*)$')
TARGET_RE = re.compile(r'^([A-Za-z0-9_./-]+)\s*:(?!=)\s*(.*)$')
UNSUPPORTED_RE = re.compile(
    r'^(ifeq|ifneq|ifdef|ifndef|else|endif|include|-include|define|endef|export|unexport|vpath)\b'
)


class MakefileError(SystemExit):
    def __init__(self, line_no: int, text: str, why: str):
        super().__init__(f'Makefile:{line_no}: {why}: {text.strip()}')


def parse(text: str) -> tuple[dict[str, str], dict[str, tuple[list[str], list[str]]]]:
    """Return (variables, {target: (deps, recipe_lines)}).

    Recipe lines are raw (unexpanded, prefixes intact) so `--dry-run` shows
    what make would show and expansion happens once, at run time, against the
    final variable table.
    """
    variables: dict[str, str] = {}
    targets: dict[str, tuple[list[str], list[str]]] = {}
    current: str | None = None

    # Join backslash continuations first, keeping line numbers of the FIRST
    # physical line for error messages.
    logical: list[tuple[int, str]] = []
    buf, start = '', 0
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip('\r')
        if not buf:
            start = i
        if line.endswith('\\'):
            buf += line[:-1] + ' '
            continue
        logical.append((start, buf + line))
        buf = ''
    if buf:
        logical.append((start, buf))

    for line_no, line in logical:
        if line.startswith('\t'):
            if current is None:
                raise MakefileError(line_no, line, 'recipe line before any target')
            targets[current][1].append(line[1:])
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if UNSUPPORTED_RE.match(stripped):
            raise MakefileError(line_no, line, 'directive not supported by scripts/make.py')
        if FUNC_RE.search(stripped):
            raise MakefileError(line_no, line, 'make function not supported by scripts/make.py')
        if stripped.startswith('.PHONY'):
            current = None
            continue
        m = ASSIGN_RE.match(stripped)
        if m:
            name, op, value = m.groups()
            if op == '?=' and (name in variables or name in os.environ):
                continue
            variables[name] = value.strip()
            current = None
            continue
        m = TARGET_RE.match(stripped)
        if m:
            name, deps = m.groups()
            if name.startswith('.'):
                current = None
                continue
            targets[name] = (deps.split(), [])
            current = name
            continue
        raise MakefileError(line_no, line, 'line is neither assignment, target nor recipe')
    return variables, targets


_warned: set[str] = set()


def expand(value: str, variables: dict[str, str], _depth: int = 0) -> str:
    """Expand $(NAME)/${NAME} recursively; `$$` becomes a literal `$`.

    Precedence is make's: a Makefile assignment, else the environment, else
    empty. Empty is what make does too, but it is also how an empty bucket
    name in `s3://$(S3_BUCKET)/...` uploads to nowhere, so an undefined name
    is WARNED once on stderr rather than silently blanked (`IN`, `OUT`, `ARGS`
    and `KEYSTORE_PATH` are legitimately supplied per call as `NAME=value`).
    A leftover `$(` after expansion is a name the regex could not read at all,
    and that is an error.
    """
    if _depth > 20:
        raise SystemExit(f'variable expansion too deep in: {value!r}')
    placeholder = '\x00'
    value = value.replace('$$', placeholder)

    def sub(m: re.Match) -> str:
        name = m.group(1) or m.group(2)
        if name in variables:
            raw = variables[name]
        elif name in os.environ:
            raw = os.environ[name]
        else:
            raw = ''
            if name not in _warned:
                _warned.add(name)
                print(f'make.py: $({name}) is undefined and expands to nothing', file=sys.stderr)
        return expand(raw, variables, _depth + 1)

    out = VAR_RE.sub(sub, value)
    if '$(' in out or '${' in out:
        raise SystemExit(f'unexpandable reference left in: {out!r}')
    return out.replace(placeholder, '$')


def plan(target: str, targets: dict, seen: set[str] | None = None) -> list[str]:
    """Depth-first order of targets to run, each once."""
    seen = seen if seen is not None else set()
    if target in seen:
        return []
    if target not in targets:
        raise SystemExit(f'no such target: {target}')
    seen.add(target)
    order: list[str] = []
    for dep in targets[target][0]:
        order.extend(plan(dep, targets, seen))
    order.append(target)
    return order


def run_recipe(name: str, lines: list[str], variables: dict[str, str], dry_run: bool) -> None:
    env = dict(os.environ, MSYS_NO_PATHCONV='1')
    print(f'### {name}', flush=True)
    for raw in lines:
        cmd = expand(raw, variables)
        silent = ignore = False
        while cmd[:1] in ('@', '-'):
            silent |= cmd[0] == '@'
            ignore |= cmd[0] == '-'
            cmd = cmd[1:]
        cmd = cmd.strip()
        if not cmd or cmd.startswith('#'):
            continue
        if not silent or dry_run:
            print(cmd, flush=True)
        if dry_run:
            continue
        # The input is the repo's own Makefile, run on purpose; that is the
        # whole job of this file, not an injection surface.
        rc = subprocess.call(['sh', '-c', cmd], env=env)  # noqa: S603, S607
        if rc != 0 and not ignore:
            raise SystemExit(f'{name}: recipe failed (exit {rc}): {cmd}')


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Run Makefile targets without GNU Make.')
    ap.add_argument(
        'targets',
        nargs='*',
        metavar='TARGET|NAME=value',
        help='targets to run; NAME=value sets a variable, as with make',
    )
    ap.add_argument('-n', '--dry-run', action='store_true', help='print the expanded commands, run nothing')
    ap.add_argument('--list', action='store_true', help='list targets and exit')
    ap.add_argument('-f', '--file', default=str(Path(__file__).resolve().parent.parent / 'Makefile'))
    args = ap.parse_args(argv)

    makefile = Path(args.file)
    variables, targets = parse(makefile.read_text(encoding='utf-8'))
    os.chdir(makefile.parent)

    # `make score-book IN=a OUT=b`: a command-line assignment beats every
    # Makefile assignment, `?=` and `=` alike, exactly as in make.
    wanted: list[str] = []
    for arg in args.targets:
        m = ASSIGN_RE.match(arg)
        if m and m.group(2) == '=':
            variables[m.group(1)] = m.group(3)
        else:
            wanted.append(arg)

    if args.list:
        for name, (deps, _) in targets.items():
            print(f'{name}{"  <- " + " ".join(deps) if deps else ""}')
        return 0
    if not wanted:
        ap.error('name at least one target (or --list)')

    order: list[str] = []
    seen: set[str] = set()
    for t in wanted:
        order.extend(plan(t, targets, seen))
    for name in order:
        run_recipe(name, targets[name][1], variables, args.dry_run)
    return 0


if __name__ == '__main__':
    sys.exit(main())
