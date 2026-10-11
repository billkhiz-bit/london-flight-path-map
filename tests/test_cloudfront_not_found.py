"""The not-found mapping covers origin 403 alone, never 404 (audit 2026-10-09 I-2).

From 7 Oct to 11 Oct CloudFront mapped origin 403 AND 404 to /404.html. Error responses are
distribution-wide, and the bucket can never answer 404 (its policy grants GetObject and no
ListBucket), so the 404 entry caught exactly one thing: the badge's "Not covered" SVG, which the
Lambda answers with status 404 on purpose. A partner's <img> then got an HTML page, a broken
image. scripts/cloudfront_not_found.py --verify checks the live side (the policy, and an
uncovered badge at the site origin); this holds the script's own table offline.

    python -m pytest tests/test_cloudfront_not_found.py
"""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / 'scripts' / 'cloudfront_not_found.py'


@pytest.fixture(scope='module')
def nf():
    pytest.importorskip('boto3')  # imported at the script's top; nothing here calls AWS
    spec = importlib.util.spec_from_file_location('cloudfront_not_found', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_only_403_is_mapped(nf):
    codes = [i['ErrorCode'] for i in nf.WANT['Items']]
    assert codes == [403], f'mapped {codes}: a 404 entry replaces the badge\'s own "Not covered" SVG'
    assert nf.WANT['Quantity'] == len(nf.WANT['Items'])


def test_the_page_answers_404_not_200(nf):
    # A not-found page answering 200 is a "soft 404": search engines index the mistyped address.
    assert all(i['ResponseCode'] == '404' and i['ResponsePagePath'] == '/404.html' for i in nf.WANT['Items'])


def test_verify_fetches_an_uncovered_badge(nf):
    # --verify fetched a COVERED badge only on 7 Oct, which is why it passed over the defect.
    source = SCRIPT.read_text(encoding='utf-8')
    assert "fetch(f'{SITE}/badge?postcode={UNCOVERED}')" in source
    assert nf.UNCOVERED == 'EX11HS'
