#!/usr/bin/env python3
"""Extract every city's airports and flight paths from index.html into JSON.

WHY A SCRIPT AND NOT A COPY
---------------------------
CLAUDE.md is explicit that frontend constants are GENERATED, not copied: the two
holders use different dialects for the same geometry - `coords` against
`coordinates`, `(lat, lon)` against `[lon, lat]` - and each mismatch has already
caused a production defect. Porting a corridor block by hand once threw
"Cannot read properties of undefined (reading 'map')" in five cities at once.

So `design/` reads a file derived from index.html rather than a second
transcription of it. Re-run this whenever the airport or flight-path constants
move.

WHAT IT PARSES
--------------
London's constants are unprefixed (`AIRPORTS`, `FLIGHT_PATHS`); every other city
is `<CITY>_AIRPORTS` / `<CITY>_FLIGHT_PATHS`. The literals are plain JS object
notation - bare identifier keys, single-quoted strings, numbers, booleans and
arrays - so a small transform to JSON is enough. Anything that fails to parse
raises rather than being skipped, because a silently dropped city would render
as an airport-free map, which is a real state for South Yorkshire and would be
indistinguishable from a bug.
"""

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / 'index.html'
OUT = REPO / 'design' / 'airports-paths.json'
OUT_RAW = REPO / 'design' / 'borough-raw.json'

# The frontend city keys, and the constant prefix each one uses.
CITY_PREFIX = {
    'london': '', 'nyc': 'NYC', 'westmidlands': 'WESTMIDLANDS',
    'westyorkshire': 'WESTYORKSHIRE', 'southyorkshire': 'SOUTHYORKSHIRE',
    'merseyside': 'MERSEYSIDE', 'tyneandwear': 'TYNEANDWEAR',
    'leicester': 'LEICESTER', 'teesside': 'TEESSIDE', 'bristol': 'BRISTOL',
    'manchester': 'MANCHESTER',
}


def slice_literal(text, name):
    """Return the array literal assigned to `const <name> = [ ... ];`."""
    m = re.search(r'const\s+' + re.escape(name) + r'\s*=\s*\[', text)
    if not m:
        return None
    i = m.end() - 1  # at the opening bracket
    depth, in_str, quote, esc = 0, False, '', False
    for j in range(i, len(text)):
        ch = text[j]
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == quote:
                in_str = False
            continue
        if ch in '"\'':
            in_str, quote = True, ch
        elif ch in '[{':
            depth += 1
        elif ch in ']}':
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
    raise SystemExit(f'unbalanced literal for {name}')


def slice_literal_obj(text, name):
    """Return the OBJECT literal assigned to `const <name> = { ... };`.

    Deliberately separate from slice_literal rather than generalised over the
    opening character: a wrong opener then fails to match instead of quietly
    slicing the wrong span, which is the harder bug to notice.
    """
    m = re.search(r'const\s+' + re.escape(name) + r'\s*=\s*\{', text)
    if not m:
        return None
    i = m.end() - 1
    depth, in_str, quote, esc = 0, False, '', False
    quotes = (chr(34), chr(39))
    for j in range(i, len(text)):
        ch = text[j]
        if in_str:
            if esc:
                esc = False
            elif ch == chr(92):
                esc = True
            elif ch == quote:
                in_str = False
            continue
        if ch in quotes:
            in_str, quote = True, ch
        elif ch in '[{':
            depth += 1
        elif ch in ']}':
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
    raise SystemExit('unbalanced object literal for ' + name)


def js_to_json(src):
    """Convert a plain JS array literal to JSON.

    Handles what these constants actually contain and nothing more: bare
    identifier keys, single-quoted strings, trailing commas, and COMMENTS -
    FLIGHT_PATHS carries fifteen line comments, including the note recording
    that two Gatwick and Luton approaches were removed on 2026-05-07 because
    their inner-London portions sit at FL90+ where DEFRA shows no contour.
    Deliberately not a JS parser: if the constants ever grow expressions this
    should fail loudly rather than guess.
    """
    out, i, n = [], 0, len(src)
    while i < n:
        ch = src[i]
        # Comments are skipped OUTSIDE strings only; the string branches below
        # consume their own content, so a '//' inside a name cannot reach here.
        if ch == '/' and i + 1 < n and src[i + 1] == '/':
            j = src.find(chr(10), i)   # chr(10), not an escape: keeps this
                                       # readable through any quoting layer
            i = n if j == -1 else j + 1
            continue
        if ch == '/' and i + 1 < n and src[i + 1] == '*':
            j = src.find('*/', i + 2)
            i = n if j == -1 else j + 2
            continue
        if ch == "'":                       # single-quoted string -> double
            j, buf = i + 1, []
            while j < n and src[j] != "'":
                if src[j] == '\\':
                    buf.append(src[j:j + 2])
                    j += 2
                    continue
                buf.append('\\"' if src[j] == '"' else src[j])
                j += 1
            out.append('"' + ''.join(buf) + '"')
            i = j + 1
            continue
        if ch == '"':                       # already double-quoted, copy through
            j = i + 1
            while j < n and src[j] != '"':
                j += 2 if src[j] == '\\' else 1
            out.append(src[i:j + 1])
            i = j + 1
            continue
        m = re.match(r'([A-Za-z_$][\w$]*)\s*:', src[i:])
        if m:                               # bare key -> quoted key
            out.append('"' + m.group(1) + '":')
            i += m.end()
            continue
        out.append(ch)
        i += 1
    text = ''.join(out)
    text = re.sub(r',(\s*[\]}])', r'\1', text)   # trailing commas
    return json.loads(text)


def main():
    text = SRC.read_text(encoding='utf-8')
    data, report = {}, []
    for city, prefix in CITY_PREFIX.items():
        a_name = f'{prefix}_AIRPORTS' if prefix else 'AIRPORTS'
        p_name = f'{prefix}_FLIGHT_PATHS' if prefix else 'FLIGHT_PATHS'
        a_src, p_src = slice_literal(text, a_name), slice_literal(text, p_name)
        if a_src is None or p_src is None:
            raise SystemExit(f'{city}: could not find {a_name} or {p_name}')
        airports, paths = js_to_json(a_src), js_to_json(p_src)
        data[city] = {'airports': airports, 'flightPaths': paths}
        coords = sum(len(p.get('coordinates') or []) for p in paths)
        report.append((city, len(airports), len(paths), coords))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1), encoding='utf-8', newline='\n')

    # Also lift <CITY>_BOROUGH_DATA_RAW: impact band, avg_price and trend.
    # These live ONLY in index.html - borough-extra.json does not carry price -
    # so a design page showing a real price has to read them from here.
    #
    # NOTE THE DIALECT: this holder spells it `avg_price`, the Lambda spells it
    # `avgPrice`. CLAUDE.md records that exact split as a repeated source of
    # production defects, which is why this is extracted rather than retyped.
    raw, raw_report = {}, []
    for city, prefix in CITY_PREFIX.items():
        name = f'{prefix}_BOROUGH_DATA_RAW' if prefix else 'BOROUGH_DATA_RAW'
        src = slice_literal_obj(text, name)
        if src is None:
            raw_report.append((city, 0))
            continue
        recs = js_to_json(src)
        raw[city] = recs
        raw_report.append((city, len(recs)))
    OUT_RAW.write_text(json.dumps(raw, indent=1), encoding='utf-8')
    total_b = sum(n for _, n in raw_report)
    if total_b == 0:
        print('FAIL: no borough raw records parsed - a parser fault, not a data fact.')
        return 1
    print('wrote ' + str(OUT_RAW.relative_to(REPO)) + ': '
          + ', '.join(f'{c} {n}' for c, n in raw_report if n))


    print(f'{"city":<16}{"airports":>9}{"paths":>7}{"coords":>8}')
    for city, a, p, c in report:
        note = '   <- no airports, a real case (Doncaster Sheffield closed 2022)' if a == 0 else ''
        print(f'{city:<16}{a:>9}{p:>7}{c:>8}{note}')
    total_a = sum(r[1] for r in report)
    if total_a == 0:
        print('\nFAIL: not one airport parsed. That is a parser fault, not a data fact.')
        return 1
    print(f'\nwrote {OUT.relative_to(REPO)} ({OUT.stat().st_size / 1000:.1f} KB), '
          f'{total_a} airports and {sum(r[2] for r in report)} paths across {len(report)} cities')
    return 0


if __name__ == '__main__':
    sys.exit(main())
