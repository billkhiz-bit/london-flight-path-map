"""One ONS crime edition, said the same way everywhere (2026-10-23, the first quarterly crime roll).

Before the roll the edition was typed in fifteen places: `EDITION` in refresh_crime_from_ons.py, the site's
`crimeVintage` label that script wrote ('ONS Table C4, year ending March 2026', a literal), and thirteen credit
lines in the score Lambda. Rolling EDITION alone would have published June's rates under March's name on every
site panel and in every API response. Now the script derives the words (`edition_label`), the site's labels are
written from them, and the Lambda's lines read one constant, `CRIME_EDITION_LABEL`.
"""

import json
import os
import re
import sys

import pytest

REPO = os.path.normpath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, os.path.join(REPO, 'scripts'))
sys.path.insert(0, os.path.join(REPO, 'backend', 'lambdas', 'score'))

import app  # noqa: E402
import refresh_crime_from_ons as crime  # noqa: E402

AN_EDITION = re.compile(r'year ending (January|February|March|April|May|June|July|August|September|October|November|'
                        r'December) 20\d\d')


def test_the_label_is_derived_from_the_folder_name():
    assert crime.edition_label('yearendingjune2026') == 'year ending June 2026'
    assert crime.edition_label('yearendingdecember2025') == 'year ending December 2025'
    with pytest.raises(SystemExit):
        crime.edition_label('current')  # the ONS page's moving folder: never an edition


def test_the_lambda_names_the_scripts_edition():
    assert app.CRIME_EDITION_LABEL == crime.edition_label()


def test_every_site_label_names_the_scripts_edition():
    with open(os.path.join(REPO, 'data', 'borough-extra.json'), encoding='utf-8') as fh:
        extra = json.load(fh)
    labels = {rec['crimeVintage'] for city in extra.values() for rec in city.values()
              if isinstance(rec, dict) and 'crimeVintage' in rec}
    assert labels == {f'ONS Table C4, {crime.edition_label()}'}


def test_no_code_line_in_the_lambda_types_an_edition():
    # Comments may record history ("March 2026 until the roll"); code reads CRIME_EDITION_LABEL.
    with open(os.path.join(REPO, 'backend', 'lambdas', 'score', 'app.py'), encoding='utf-8') as fh:
        typed = [i for i, line in enumerate(fh, 1)
                 if AN_EDITION.search(line) and not line.lstrip().startswith('#')
                 and not line.startswith('CRIME_EDITION_LABEL = ')]
    assert typed == []
