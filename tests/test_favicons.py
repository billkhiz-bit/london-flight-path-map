"""Every page carries the favicon, and the files it names exist in the shape browsers need (2026-10-08).

Until 2026-10-08 the site had almost no icon: the full map, privacy and terms drew the ✈ emoji
from an inline data: URI, the other 122 pages declared nothing, /favicon.ico answered 404 on
every page view, and the map's apple-touch-icon pointed at an SVG where Apple documents a PNG.
Now every deployed page carries the same three links:

    /favicon.ico               16/32/48 px, for browsers without SVG favicons and the root request
    /icons/favicon.svg         a simplified mark: the app icon's rings vanish at 16 px
    /icons/apple-touch-icon.png  180 px, the full app icon on solid ground (iOS fills alpha with black)

All three are rendered by scripts/build_favicons.mjs. Nothing else keeps 125 pages and two
generators in step, so this does, the way tests/test_goatcounter_pinned.py does for analytics.

    python -m pytest tests/test_favicons.py
"""

import re
import struct
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LINKS = {
    'ico': re.compile(r'<link\s+rel="icon"\s+href="/favicon\.ico"\s+sizes="32x32"\s*/?>'),
    'svg': re.compile(r'<link\s+rel="icon"\s+href="/icons/favicon\.svg"\s+type="image/svg\+xml"\s*/?>'),
    'touch': re.compile(r'<link\s+rel="apple-touch-icon"\s+href="/icons/apple-touch-icon\.png"\s*/?>'),
}
# Not deployed, or copies another build makes: design prototypes, archives, the native app's
# generated assets, agent worktrees, dependencies, test fixtures and local test reports.
SKIP = {'node_modules', 'archive', 'mobile', '.claude', 'design', 'tests', '.git',
        'playwright-report', 'test-results'}
GENERATORS = ('scripts/build_area_pages.py', 'scripts/build_bay_area_page.py')
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


def pages():
    for path in REPO.rglob('*.html'):
        if SKIP.isdisjoint(path.relative_to(REPO).parts):
            yield path


def head_of(path):
    text = path.read_text(encoding='utf-8')
    match = re.search(r'<head\b[^>]*>(.*?)</head>', text, re.S | re.I)
    return match.group(1) if match else ''


def png_size(data):
    """(width, height, colour type) from a PNG's IHDR chunk."""
    assert data[:8] == PNG_SIGNATURE, 'not a PNG'
    width, height = struct.unpack('>II', data[16:24])
    return width, height, data[25]


def test_the_scan_reaches_the_pages_that_count():
    found = {p.relative_to(REPO).as_posix() for p in pages()}
    # A walk that finds nothing would pass the checks below vacuously.
    assert len(found) >= 120, len(found)
    for page in ('index.html', 'home/index.html', 'pricing.html', 'bay-area/index.html',
                 'area/london/hounslow/index.html', '404.html'):
        assert page in found, f'{page} is not deployed any more, or the scan cannot see it'


def test_every_page_links_all_three_icons_in_its_head():
    missing = {}
    for path in pages():
        head = head_of(path)
        lacking = [name for name, pattern in LINKS.items() if len(pattern.findall(head)) != 1]
        if lacking:
            missing[path.relative_to(REPO).as_posix()] = lacking
    assert not missing, f'pages without exactly one of each favicon link in <head>: {missing}'


def test_no_page_keeps_an_old_icon():
    for path in pages():
        text = path.read_text(encoding='utf-8')
        rel = path.relative_to(REPO).as_posix()
        assert not re.search(r'rel="icon"\s+href="data:', text), f'{rel} still draws the inline emoji icon'
        assert not re.search(r'rel="apple-touch-icon"\s+href="[^"]*\.svg"', text), f'{rel} points iOS at an SVG'


def test_the_generators_write_them():
    # Area, open-data and Bay Area pages are generated: a hand fix would be undone by --write.
    for gen in GENERATORS:
        source = (REPO / gen).read_text(encoding='utf-8')
        for name, pattern in LINKS.items():
            assert pattern.search(source), f'{gen} does not write the {name} link'


def test_favicon_ico_holds_16_32_and_48_px_pngs():
    data = (REPO / 'favicon.ico').read_bytes()
    reserved, kind, count = struct.unpack('<HHH', data[:6])
    assert (reserved, kind) == (0, 1), 'not an ICO file'
    sizes = []
    for i in range(count):
        width, height, *_rest, length, offset = struct.unpack('<BBBBHHII', data[6 + 16 * i:22 + 16 * i])
        image = data[offset:offset + length]
        assert len(image) == length, f'entry {i} runs past the end of the file'
        assert png_size(image)[:2] == (width, height), f'entry {i} says {width}x{height}, holds another size'
        sizes.append(width)
    assert sorted(sizes) == [16, 32, 48], sizes


def test_the_touch_icon_is_a_180px_png_with_no_transparency():
    width, height, colour_type = png_size((REPO / 'icons' / 'apple-touch-icon.png').read_bytes())
    assert (width, height) == (180, 180)
    # 2 = truecolour, no alpha. With alpha, iOS paints the transparent corners black.
    assert colour_type == 2, f'PNG colour type {colour_type}, expected 2 (RGB, no alpha)'


def test_the_svg_favicon_exists():
    svg = (REPO / 'icons' / 'favicon.svg').read_text(encoding='utf-8')
    assert '<svg' in svg and 'viewBox=' in svg


def test_the_deploy_uploads_them_with_their_own_types():
    makefile = (REPO / 'Makefile').read_text(encoding='utf-8')
    assert re.search(r'aws s3 cp favicon\.ico[^\n]*\\\n[^\n]*\\\n[^\n]*--content-type "image/x-icon"', makefile)
    assert "'/favicon.ico'" in makefile, 'favicon.ico is uploaded but never invalidated'
    assert '--include "*.png" --content-type "image/png"' in makefile
    # The old recipe uploaded the whole folder as SVG, which would serve the PNG touch icon as SVG.
    assert not re.search(r'cp icons/[^\n]*\\\n[^\n]*\\\n\s*--recursive --content-type', makefile)
