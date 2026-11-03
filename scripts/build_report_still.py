#!/usr/bin/env python3
"""The front page's picture of the sample street report: the top of its first page, made from the PDF itself.

WHY THIS EXISTS (front-page-v3, 2026-11-03). Step 05 of the front page's walkthrough SHOWS the report a visitor can
make (Bill, 3 Nov night: "a picture of the real sample report's first page, generated from the PDF, never a hand
copy"). A picture copied by hand goes stale unseen: the sample PDF itself went on saying the CAA's 2024 figure for two
days after the 1 Nov roll, until the wording gate learned to read PDFs. So the picture is MADE here, from
home/reports/sample-street-report-kew.pdf, and --check holds it to that file:

- the PDF's SHA-256 recorded when the picture was made must be the PDF's now (regenerate the sample, as ROADMAP's
  23 Dec TODO says, and this reds until --write);
- the picture's own SHA-256 must be the one recorded (a hand edit, or a file swapped in, reds);
- the front page's <img> must name the picture at its true width and height (no layout shift, no stretched page).

The check reads hashes only, so it needs no PDF renderer (preflight and CI run it); --write needs PyMuPDF and Pillow.

    python scripts/build_report_still.py --write   # render the picture and record both hashes
    python scripts/build_report_still.py --check   # offline, blocking: the picture is the current PDF's
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PDF = REPO / 'home' / 'reports' / 'sample-street-report-kew.pdf'
STILL = REPO / 'home' / 'reports' / 'sample-street-report-kew-top.webp'
MANIFEST = REPO / 'data' / 'report-still-manifest.json'
HOME = REPO / 'home' / 'index.html'
SERVED = '/reports/sample-street-report-kew-top.webp'  # home-deploy syncs home/reports/ to /reports/

WIDTH = 960       # pixels across: sharp at twice the walkthrough's ~470 px column
TOP_SHARE = 0.47  # the share of the first page shown, from its top: the title, the four figures, the map and its key
QUALITY = 82      # WebP quality


def rel(path: Path) -> str:
    """A path as the messages name it: repo-relative where it can be."""
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return path.as_posix()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(pdf: Path = PDF) -> tuple[bytes, int, int, str]:
    """(WebP bytes, width, height, renderer) of the top TOP_SHARE of the PDF's first page, WIDTH pixels across."""
    import fitz  # PyMuPDF: only --write needs it
    from PIL import Image

    doc = fitz.open(pdf)
    page = doc[0]
    zoom = WIDTH / page.rect.width
    clip = fitz.Rect(0, 0, page.rect.width, page.rect.height * TOP_SHARE)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
    img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    out = io.BytesIO()
    img.save(out, 'WEBP', quality=QUALITY, method=6)
    return out.getvalue(), img.width, img.height, f'PyMuPDF {fitz.VersionBind}'


def page_img(html: str) -> dict | None:
    """The front page's <img> for the picture: {width, height}, or None if the page does not show it."""
    m = re.search(r'<img\b[^>]*\bsrc="' + re.escape(SERVED) + r'"[^>]*>', html)
    if not m:
        return None
    size = {k: re.search(rf'\b{k}="(\d+)"', m.group(0)) for k in ('width', 'height')}
    return {k: int(v.group(1)) if v else None for k, v in size.items()}


def problems(manifest: dict | None, pdf: Path = PDF, still: Path = STILL, home: Path = HOME) -> list[str]:
    """Every way the picture can be out of step; empty means it passes."""
    if manifest is None:
        return [f'missing: data/{MANIFEST.name} (run --write)']
    out = []
    if not still.exists():
        return [f'missing: {rel(still)} (run --write)']
    if manifest.get('pdf_sha256') != sha256(pdf):
        out.append(f'{pdf.name} has changed since the picture was made from it: run --write')
    if manifest.get('still_sha256') != sha256(still):
        out.append(f'{still.name} is not the picture --write made (edited by hand?): run --write')
    shown = page_img(home.read_text(encoding='utf-8'))
    if shown is None:
        out.append(f'{rel(home)} no longer shows {SERVED}')
    elif (shown['width'], shown['height']) != (manifest.get('width'), manifest.get('height')):
        out.append(f'the front page sizes the picture {shown["width"]}x{shown["height"]}; it is '
                   f'{manifest.get("width")}x{manifest.get("height")}: set its width and height')
    return out


def read_manifest(path: Path = MANIFEST) -> dict | None:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write', action='store_true', help='render the picture from the PDF and record both hashes')
    mode.add_argument('--check', action='store_true', help='offline: the picture is the current PDF\'s')
    args = ap.parse_args(argv)
    if args.write:
        data, w, h, renderer = render()
        STILL.write_bytes(data)
        manifest = {
            'about': ('Written by scripts/build_report_still.py --write: the top of the sample street report\'s first '
                      'page, shown in the front page\'s walkthrough (step 05). Never edit by hand.'),
            'pdf': PDF.relative_to(REPO).as_posix(), 'pdf_sha256': sha256(PDF),
            'still': STILL.relative_to(REPO).as_posix(), 'still_sha256': sha256(STILL),
            'width': w, 'height': h, 'top_share': TOP_SHARE, 'renderer': renderer,
        }
        MANIFEST.write_text(json.dumps(manifest, indent=1) + '\n', encoding='utf-8', newline='\n')
        print(f'wrote {STILL.relative_to(REPO).as_posix()} ({w}x{h}, {len(data):,} bytes) and data/{MANIFEST.name}')
    found = problems(read_manifest())
    if found:
        print('FAIL:\n  ' + '\n  '.join(found))
        return 1
    print('ok: the report picture is the current sample PDF\'s, and the front page shows it at its size')
    return 0


if __name__ == '__main__':
    sys.exit(main())
