"""The provenance periods in the score Lambda == the loaders' own holders (2026-10-23).

The Lambda cannot import the loader scripts, so `PROVENANCE_PERIODS` in backend/lambdas/score/app.py is a second
holder of each dataset's vintage. Read the holder, never retype it: when a loader rolls (a new PCM year, a new
crime edition, an AIRAC or FAA cycle), this goes red until the period an agent is told moves with it. The same
constants are what scripts/check_data_freshness.py compares with each publisher, so a roll it asks for and the
provenance it changes are one change.
"""

import datetime
import importlib
import json
import os
import sys

REPO = os.path.normpath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, os.path.join(REPO, 'scripts'))
sys.path.insert(0, os.path.join(REPO, 'backend', 'lambdas', 'score'))

import app  # noqa: E402

# DEFRA's strategic noise rounds and the year each MAPS (published the year after).
NOISE_ROUND_MAPS = {4: '2021'}


def holder(module, name):
    return getattr(importlib.import_module(module), name)


def test_every_period_equals_its_loader():
    p = app.PROVENANCE_PERIODS
    record = json.loads(holder('build_us_flight_paths', 'RECORD').read_text(encoding='utf-8'))
    edition = holder('refresh_crime_from_ons', 'EDITION')
    expected = {
        'defra-noise': NOISE_ROUND_MAPS[holder('check_data_freshness', 'NOISE_ROUND')],
        'defra-pcm': str(holder('load_defra_air_quality', 'PCM_YEAR')),
        'ons-crime-c4': p['ons-crime-c4'] if p['ons-crime-c4'].replace(' ', '').lower() == edition else f'<{edition}>',
        'dfe-ks4': holder('build_progress8', 'VINTAGE'),
        'ons-nspl': datetime.date.fromisoformat(holder('load_nspl', 'NSPL_VINTAGE') + '-01').strftime('%B %Y'),
        'uk-aip': f"AIRAC {holder('build_flight_paths', 'AIRAC')}",
        'faa-cifp': f"cycle {record['cycle']}, effective {record['effective']}",
    }
    assert p == expected


def test_every_period_reaches_its_source():
    # A period held here but read by no source would be dead config waving a stale year through.
    used = {s['period'] for s in app.PROVENANCE_SOURCES.values()}
    assert set(app.PROVENANCE_PERIODS.values()) <= used
