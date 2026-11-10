"""A <meta> Content-Security-Policy cannot carry frame-ancestors.

Browsers ignore that directive in a meta tag and log an error on every load, and the page reads as protected when it is
not. What refuses framing is CloudFront's X-Frame-Options: DENY, held by scripts/check_deploy_drift.sh. Ten pages carried
it until 2026-11-06.
"""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
META_CSP = re.compile(r'<meta\b[^>]*Content-Security-Policy[^>]*>', re.I)


def pages():
    listed = subprocess.run(['git', 'ls-files', '*.html'], cwd=ROOT, capture_output=True,  # noqa: S603, S607  (git, fixed arguments)
                            text=True, check=True).stdout
    return [ROOT / name for name in listed.splitlines() if not name.startswith('tests/')]


def test_it_reads_real_policies():
    assert sum(bool(META_CSP.search(p.read_text(encoding='utf-8'))) for p in pages()) >= 10


def test_no_meta_csp_carries_frame_ancestors():
    found = [p.relative_to(ROOT).as_posix() for p in pages() if any('frame-ancestors' in m for m in META_CSP.findall(p.read_text(encoding='utf-8')))]
    assert found == []


# /api/ writes typed text and API answers into the page, so it refuses inline script (audit M-8, 2026-11-09). Its one inline
# script was a click tracker, now js/api-page-events.mjs. Held both ways: the policy, and nothing inline it would refuse.
INLINE_SCRIPT = re.compile(r'<script(?![^>]*\bsrc=)(?![^>]*application/ld\+json)[^>]*>', re.I)


def test_the_api_page_refuses_inline_script():
    page = (ROOT / 'api' / 'index.html').read_text(encoding='utf-8')
    policy = META_CSP.search(page).group(0)
    script_src = re.search(r"script-src([^;]*)", policy).group(1)
    assert "'unsafe-inline'" not in script_src, script_src
    assert INLINE_SCRIPT.findall(page) == []
    assert '/js/api-page-events.mjs' in page
