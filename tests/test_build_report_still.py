"""The front page's picture of the sample street report is the current PDF's (scripts/build_report_still.py, 2026-11-03).

Each way out of step is proven red on copies: the PDF regenerated without the picture, the picture swapped or edited by
hand, the page sizing it wrongly or no longer showing it. And the committed picture passes, as preflight's --check reads.
"""
import importlib.util
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_report_still', REPO / 'scripts' / 'build_report_still.py')
brs = importlib.util.module_from_spec(spec)
sys.modules['build_report_still'] = brs
spec.loader.exec_module(brs)


def _copies(tmp_path):
    pdf, still, home = tmp_path / 'a.pdf', tmp_path / 'a.webp', tmp_path / 'index.html'
    shutil.copy(brs.PDF, pdf)
    shutil.copy(brs.STILL, still)
    shutil.copy(brs.HOME, home)
    return pdf, still, home


def test_the_committed_picture_is_the_current_pdfs():
    assert brs.problems(brs.read_manifest()) == []


def test_a_regenerated_pdf_reds_until_write(tmp_path):
    pdf, still, home = _copies(tmp_path)
    pdf.write_bytes(pdf.read_bytes() + b'\n% regenerated')
    found = brs.problems(brs.read_manifest(), pdf, still, home)
    assert any('has changed since the picture was made' in p for p in found)


def test_a_picture_edited_by_hand_reds(tmp_path):
    pdf, still, home = _copies(tmp_path)
    still.write_bytes(still.read_bytes() + b'\0')
    assert any('is not the picture --write made' in p for p in brs.problems(brs.read_manifest(), pdf, still, home))


def test_the_page_must_show_it_at_its_size(tmp_path):
    pdf, still, home = _copies(tmp_path)
    m = brs.read_manifest()
    html = home.read_text(encoding='utf-8')
    home.write_text(html.replace(f'width="{m["width"]}" height="{m["height"]}"', 'width="900" height="600"'), encoding='utf-8')
    assert any('sizes the picture 900x600' in p for p in brs.problems(m, pdf, still, home))
    home.write_text(html.replace(brs.SERVED, '/reports/other.webp'), encoding='utf-8')
    assert any('no longer shows' in p for p in brs.problems(m, pdf, still, home))


def test_no_manifest_or_no_picture_is_said(tmp_path):
    pdf, still, home = _copies(tmp_path)
    assert brs.problems(None, pdf, still, home) == [f'missing: data/{brs.MANIFEST.name} (run --write)']
    still.unlink()
    assert brs.problems(brs.read_manifest(), pdf, still, home)[0].startswith('missing:')


def test_the_manifest_names_the_files_it_holds():
    m = json.loads(brs.MANIFEST.read_text(encoding='utf-8'))
    assert (m['pdf'], m['still']) == ('home/reports/sample-street-report-kew.pdf', 'home/reports/sample-street-report-kew-top.webp')
