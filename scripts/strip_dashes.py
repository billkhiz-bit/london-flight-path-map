"""
One-shot script to remove em dashes (U+2014) and en dashes (U+2013) from
user-facing repo files. Replaces them with idiomatic British-English
substitutes:

  ' — '     ->  ', '       (the most common pattern, e.g. "Sky Score — data")
  '—'       ->  ', '       (rare bare-em-dash form)
  ' – '     ->  '-'        (en dash with spaces, treat as hyphen)
  '–'       ->  '-'        (bare en dash)

After the substitution we collapse accidental double commas / spaces.

Scope:
  - All .md, .html, .yaml/.yml, .py, .json, .js, .txt files at any depth.
  - Excludes .git/, node_modules/, .aws-sam/, playwright-report/,
    test-results/, package-lock.json (auto-generated), and the script
    itself (would self-replace its own documentation patterns).

Run from project root:
  python scripts/strip_dashes.py [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

EXCLUDE_DIRS = {
    '.git', 'node_modules', '.aws-sam',
    'playwright-report', 'test-results', 'reports',
    '__pycache__', '.idea', '.vscode',
}
EXCLUDE_FILES = {
    'package-lock.json',
    'strip_dashes.py',  # self-exclusion so the script's docstring stays
}
INCLUDE_SUFFIXES = {'.md', '.html', '.yaml', '.yml', '.py', '.json', '.js', '.txt'}

EM = '—'
EN = '–'

# Order of replacements matters: handle the spaced forms first, then bare.
PATTERNS = [
    # Em dash with surrounding whitespace -> ", "
    (re.compile(rf'[ \t]*{EM}[ \t]+'), ', '),
    (re.compile(rf'[ \t]+{EM}[ \t]*'), ', '),
    # Bare em dash -> ", "
    (re.compile(EM), ', '),
    # En dash with surrounding whitespace -> "-"
    (re.compile(rf'[ \t]*{EN}[ \t]+'), '-'),
    (re.compile(rf'[ \t]+{EN}[ \t]*'), '-'),
    # Bare en dash -> "-"
    (re.compile(EN), '-'),
]

# Cleanup passes — applied per-line so we don't touch leading indentation.
# `re.compile(r'  +')` against the full file contents was the previous
# (catastrophic) approach: it collapsed Python's 4-space indentation into
# single spaces and broke every .py file. The line-by-line approach below
# only collapses double-spaces that appear AFTER the first non-space char.
COLLAPSE_DOUBLE_COMMA = re.compile(r',\s*(?:,\s*)+')
TRAILING_WS = re.compile(r'[ \t]+$', re.MULTILINE)
INNER_DOUBLE_SPACE = re.compile(r'(\S)  +')


def scan(root: Path):
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        if path.suffix.lower() not in INCLUDE_SUFFIXES:
            continue
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        if path.name in EXCLUDE_FILES:
            continue
        yield path


def transform(text: str) -> str:
    out = text
    for pat, repl in PATTERNS:
        out = pat.sub(repl, out)
    out = COLLAPSE_DOUBLE_COMMA.sub(', ', out)
    # Collapse only double-spaces that follow non-whitespace content. This
    # preserves indentation (leading whitespace) entirely. The (\S) capture
    # is preserved via backreference.
    out = INNER_DOUBLE_SPACE.sub(r'\1 ', out)
    out = TRAILING_WS.sub('', out)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true',
                        help='Report what would change without writing.')
    args = parser.parse_args()

    root = Path('.').resolve()
    total = 0
    touched = 0
    em_count = 0
    en_count = 0
    for path in scan(root):
        try:
            original = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue  # binary masquerading as text
        total += 1
        em_here = original.count(EM)
        en_here = original.count(EN)
        if not em_here and not en_here:
            continue
        em_count += em_here
        en_count += en_here
        new = transform(original)
        if new == original:
            continue  # transformation produced no change (already clean?)
        touched += 1
        rel = path.relative_to(root)
        print(f'  {rel}  ({em_here} em, {en_here} en)')
        if not args.dry_run:
            path.write_text(new, encoding='utf-8', newline='\n')

    verb = 'Would update' if args.dry_run else 'Updated'
    print(f'\n{verb} {touched} of {total} files. {em_count} em dashes, {en_count} en dashes total.')
    if args.dry_run:
        print('Run again without --dry-run to apply.')


if __name__ == '__main__':
    main()
