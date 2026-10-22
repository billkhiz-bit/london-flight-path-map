"""New York must not be the only US city the code can imagine.

New York was the only US city for long enough that "is this New York?" came
to stand in for several different questions: is this a UK city the UK-only
services know, is its noise picture a tile service, does it have Progress 8,
which ZIP table applies. A second US city (the Bay Area, EXPANSION.md "What a
second US city must touch") falls into whichever branch each test leaves it
in: the UK's by default, New York's by accident, and nothing is raised either
way. That survey found the places by reading; this is the ratchet.

Every test of New York BY NAME that remains in the page and in the score
Lambda is DECLARED below with the reason it is still by name. The build fails
on one that is not declared (a new one must be a question asked of the
registry, or be added here with its reason), and on a declared one that has
gone (so the list cannot rot into a list of things already fixed).

Comments are skipped: the files explain their own history at length, and a
sentence about `city === 'nyc'` is not a branch.
"""

import os
import re
from collections import Counter

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), os.pardir))

# The page. Six left on 2026-10-03, every one carrying New York's own CONTENT
# rather than asking what kind of city this is; each goes when the Bay Area's
# equivalent exists and the content moves into the registry.
PAGE_DECLARED = {
    # handleUsZipSearch(): New York's static ZIP table decides the city.
    "if (currentCity !== 'nyc') await switchCity('nyc');": 1,
    # Two functions open with this line: crimeNote()'s NYPD wording and
    # buildPropertyLinks()'s StreetEasy links. (A third, the altitude bands keyed
    # on JFK, EWR and LGA, went on 2026-10-07: the FAA's glide paths replaced it.)
    "if (currentCity === 'nyc') {": 2,
    # The sold-prices fallback: New York's listing links or the UK's.
    "currentCity === 'nyc' ? nycLinks : ukLinks": 1,
    # The "check flight tracking" advice, which names JFK, LaGuardia and Newark.
    "currentCity === 'nyc'": 1,
}

# The score Lambda. One left: a New York ZIP asked of another city (below).
LAMBDA_DECLARED = {
    # ("if city != 'nyc'" left on 2026-10-16: the UK outside-coverage loop chooses UK
    # cities by country now, so the Bay Area cannot slip into it either. The four
    # "is this the UK's liveability shape" tests left on 2026-10-18 for uk_shape(),
    # a registry question; all 816 scores byte-identical across the change. "if city ==
    # 'nyc':" in _postcode_coverage_notice left on 2026-10-22, when the Bay Area got its own
    # notice: a non-UK city's sentence is now chosen by registry, `postcode-<city>`.)
    # A New York ZIP asked of another city: the ZIP table IS New York's, so the question is
    # whether the caller named New York, and no registry field answers it more honestly.
    "if zip5 in NYC_ZIP_TO_BOROUGH and named_city and named_city != 'nyc' and not uk_shape(named_city):": 1,
}


def by_name_tests(rel, pattern, comment_starts):
    found = Counter()
    with open(os.path.join(REPO_ROOT, rel), encoding='utf-8') as fh:
        for line in fh:
            code = line.strip()
            if code.startswith(comment_starts):
                continue
            if re.search(pattern, code):
                found[code] += 1
    return found


def explain(found, declared):
    new = found - Counter(declared)
    gone = Counter(declared) - found
    lines = []
    for code, n in sorted(new.items()):
        lines.append(f'  NOT DECLARED ({n}): {code}')
    for code, n in sorted(gone.items()):
        lines.append(f'  DECLARED BUT GONE ({n}): {code}')
    return '\n'.join(lines)


def test_the_page_tests_for_new_york_by_name_only_where_declared():
    found = by_name_tests('index.html', r"(===|!==)\s*'nyc'", ('//', '*', '/*'))
    assert sum(found.values()) > 0, 'no by-name test found at all: the pattern is reading nothing'
    assert found == Counter(PAGE_DECLARED), (
        'index.html tests for New York by name somewhere this file does not '
        'declare, or a declared test has gone. A new branch should ask the '
        'registry (isUkCity, paintsNoiseFromTiles, a CITY_DATA field); a '
        'removed one should leave this list.\n' + explain(found, PAGE_DECLARED))


def test_the_lambda_tests_for_new_york_by_name_only_where_declared():
    found = by_name_tests('backend/lambdas/score/app.py', r"(==|!=)\s*'nyc'", ('#',))
    assert sum(found.values()) > 0, 'no by-name test found at all: the pattern is reading nothing'
    assert found == Counter(LAMBDA_DECLARED), (
        'the score Lambda tests for New York by name somewhere this file does '
        'not declare, or a declared test has gone.\n' + explain(found, LAMBDA_DECLARED))


def test_the_registry_questions_exist_and_do_not_name_a_city():
    with open(os.path.join(REPO_ROOT, 'index.html'), encoding='utf-8') as fh:
        page = fh.read()
    shapes = {
        'isUkCity': r'function isUkCity\(cityKey\) \{\s*return ([^;]+);',
        'paintsNoiseFromTiles': r'const paintsNoiseFromTiles = \(id\) => ([^;]+);',
    }
    for name, shape in shapes.items():
        definitions = re.findall(shape, page)
        # Exactly one: a second declaration of either name is a SyntaxError
        # that stops the whole inline script, which is how this test came to
        # count them (2026-10-03).
        assert len(definitions) == 1, (
            f'{name} should be defined exactly once in index.html in the shape '
            f'this test reads; found {len(definitions)}')
        assert len(re.findall(rf'(?:const|let|var|function) {name}\b', page)) == 1, (
            f'{name} is declared more than once in index.html')
        assert "'nyc'" not in definitions[0] and "'london'" not in definitions[0], (
            f'{name} names a city; it exists to ask the registry instead')
