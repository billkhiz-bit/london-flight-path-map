"""Every link the front page makes reaches something, and every link back to it lands (Bill, 2026-11-04: "make sure
everything is linked and connected correctly to the rest of the website").

The front page is rebuilt from time to time and the rest of the site is not, so the two can part without anything
failing: a page renamed, a heading's id changed, a section moved. A fragment that misses does not even error: the
browser opens the page at the top. So this reads the sources, the way a visitor's click would resolve:

  * each same-site link in home/index.html and in the scripts that write links into it reaches a file the site ships;
  * each fragment on such a link is an id on that page (or a fragment the engine reads, HASH_ROUTES);
  * each link from another tracked page back to the front page lands on an id, or on a query the engine reads.

/planes-overhead/ is a gitignored build, so its pages are held to the tracked index they are built from. Links to other
sites are checked after a deploy, from the live page, never here: a gate must not turn red on someone else's server.
"""
import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOME = REPO / 'home' / 'index.html'
ENGINE = REPO / 'js' / 'home-engine.mjs'
COUNCILS = REPO / 'data' / 'planes-districts-by-council.json'
# The scripts that write links into the front page.
SCRIPTS = ('js/home-engine.mjs', 'js/home-sections.mjs', 'js/planes.mjs')

# A fragment the engine acts on with no id of that name, and how: the test holds the engine to it.
HASH_ROUTES = {'find': "location.hash === '#find'"}
# The queries bootFromQuery() reads. Anything else in a link back to the front page would be ignored.
QUERY_KEYS = {'city', 'postcode', 'borough'}

HREF = re.compile(r'''\bhref=(?:"([^"]+)"|'([^']+)')''')
# A site path written as a string in a script: '/how-it-works/#planes-overhead', `/map/`.
SCRIPT_PATH = re.compile(r'''['"`](/(?:map|pricing|privacy|terms|changes|api|about|area|reports|how-it-works|planes-overhead|open-data|bay-area|score-demo)[^'"`$\s]*)['"`]''')
ID = re.compile(r'''\bid=(?:"([^"]+)"|'([^']+)')''')


def split(link: str) -> tuple[str, str, str]:
    """(path, query, fragment) of a same-site link."""
    rest, _, fragment = link.partition('#')
    path, _, query = rest.partition('?')
    return path, query, fragment


def same_site(link: str) -> bool:
    return link.startswith(('/', '#')) and not link.startswith('//')


def source_of(path: str) -> Path | None:
    """The tracked file that serves a site path, or None. The front page's own folder is deployed at the site's root."""
    clean = path.strip('/')
    if not clean:
        return HOME
    if clean == 'map':
        return REPO / 'index.html'
    for root in (REPO, REPO / 'home'):
        for candidate in (root / clean / 'index.html', root / f'{clean}.html', root / clean):
            if candidate.is_file():
                return candidate
    return None


def planes_pages() -> set[str]:
    """Every /planes-overhead/ path the tracked index promises."""
    index = json.loads(COUNCILS.read_text(encoding='utf-8'))
    pages = {'/planes-overhead/'}
    consultation = index.get('consultation') or {}
    if consultation.get('hub'):
        pages.add(consultation['hub'])
    pages.update(consultation.get('councils', {}).values())
    return pages


def ids_in(page: Path) -> set[str]:
    return {a or b for a, b in ID.findall(page.read_text(encoding='utf-8'))}


def links_on_home() -> set[str]:
    page = HOME.read_text(encoding='utf-8')
    links = {a or b for a, b in HREF.findall(page)}
    for script in SCRIPTS:
        links |= set(SCRIPT_PATH.findall((REPO / script).read_text(encoding='utf-8')))
    return {link for link in links if same_site(link)}


def problem_with(link: str, pages: set[str]) -> str | None:
    """Why a same-site link goes nowhere, or None when it lands."""
    path, _query, fragment = split(link)
    if path.startswith('/planes-overhead/'):
        return None if path in pages else f'{link}: not a page the planes index lists'
    target = HOME if not path else source_of(path)
    if target is None:
        return f'{link}: no tracked file serves {path}'
    if fragment and fragment not in HASH_ROUTES and target.suffix == '.html' and fragment not in ids_in(target):
        return f'{link}: {target.relative_to(REPO).as_posix()} has no id "{fragment}"'
    return None


def test_the_front_page_makes_a_good_many_links():
    """A pattern that stopped matching would pass every test below."""
    links = links_on_home()
    assert len(links) >= 25, sorted(links)
    assert {'/map/', '/pricing', '/how-it-works/', '/about/', '#pc', '#planes-band'} <= links


def test_every_link_on_the_front_page_lands():
    pages = planes_pages()
    problems = sorted(filter(None, (problem_with(link, pages) for link in links_on_home())))
    assert not problems, '\n'.join(problems)


def test_every_page_of_the_heathrow_pack_on_the_front_page_is_one_the_index_lists():
    """The dark band's links are generated: this is the join between it and the pack."""
    pages = planes_pages()
    pack = {link for link in links_on_home() if link.startswith('/planes-overhead/heathrow-consultation/')}
    assert pack <= pages, sorted(pack - pages)


def test_every_link_back_to_the_front_page_lands():
    tracked = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '*.html'], cwd=REPO, capture_output=True, text=True, check=True).stdout.split()  # noqa: S607
    # design/ holds old mock-ups and preview/ test pages: nothing a visitor reaches.
    pages = [REPO / name for name in tracked if not name.startswith(('design/', 'preview/', 'prototype/', 'mobile/'))]
    home_ids = ids_in(HOME)
    problems, seen = [], 0
    for page in pages:
        for a, b in HREF.findall(page.read_text(encoding='utf-8')):
            path, query, fragment = split(a or b)
            if path != '/' or not (fragment or query):
                continue
            seen += 1
            name = page.relative_to(REPO).as_posix()
            if fragment and fragment not in home_ids and fragment not in HASH_ROUTES:
                problems.append(f'{name}: {a or b}: the front page has no id "{fragment}"')
            unknown = {pair.partition('=')[0] for pair in query.split('&') if pair} - QUERY_KEYS
            if unknown:
                problems.append(f'{name}: {a or b}: the front page reads no {sorted(unknown)}')
    assert seen >= 2, 'no link back to the front page found: the pattern has stopped matching'
    assert not problems, '\n'.join(problems)


def test_the_fragments_the_engine_reads_are_still_read():
    engine = ENGINE.read_text(encoding='utf-8')
    for fragment, code in HASH_ROUTES.items():
        assert code in engine, f'#{fragment}: the engine no longer reads it'
    for key in QUERY_KEYS:
        assert f"'{key}'" in engine, f'?{key}=: the engine no longer reads it'
