"""A rank on an outreach sheet says a tie as a tie (audit M-16, 2026-11-09).

scripts/area_summary.mjs ranked boroughs by a sort's position, so a borough level with another took whichever place the
list order gave it: Hammersmith and Fulham, level with Newham at 20.4 ug/m3 of NO2, was printed "11th-highest". The rank
now comes from scripts/rank_place.mjs, run here through node on the borough file the sheets read.
"""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def place(values, value):
    js = (
        "import { placeAmong, placeWords } from './scripts/rank_place.mjs';"
        f'const p = placeAmong({json.dumps(values)}, {json.dumps(value)});'
        'console.log(JSON.stringify({ ...p, words: placeWords(p) }));'
    )
    out = subprocess.run(  # noqa: S603 - node with our own fixed script and numbers
        ['node', '--input-type=module', '-e', js],  # noqa: S607 - node from PATH, as preflight runs it
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return json.loads(out)


def london(field):
    extra = json.loads((ROOT / 'data' / 'borough-extra.json').read_text(encoding='utf-8'))
    boroughs = extra.get('london', extra)
    return {b: d[field] for b, d in boroughs.items() if isinstance(d, dict) and isinstance(d.get(field), (int, float))}


def test_a_borough_level_with_another_is_joint():
    no2 = london('no2AnnualMeanUgm3')
    assert len(no2) == 33
    hf = no2['Hammersmith and Fulham']
    level = sorted(b for b, v in no2.items() if v == hf)
    assert level == ['Hammersmith and Fulham', 'Newham'], level  # the case found; if the data moves, re-read the sheet
    p = place(list(no2.values()), hf)
    assert (p['rank'], p['tied'], p['words']) == (10, True, 'joint 10th')


def test_a_borough_with_no_equal_keeps_a_plain_place():
    no2 = london('no2AnnualMeanUgm3')
    p = place(list(no2.values()), no2['Kensington and Chelsea'])
    assert (p['rank'], p['tied'], p['words']) == (6, False, '6th')


def test_rank_counts_only_what_is_strictly_higher():
    assert place([5, 4, 4, 3], 4)['words'] == 'joint 2nd'
    assert place([5, 4, 4, 3], 3)['words'] == '4th'
    assert place([5, 4, 4, 3], 5)['words'] == '1st'
    assert place([7, 7], 7)['words'] == 'joint 1st'
    assert place(list(range(30, 0, -1)), 19)['words'] == '12th'
    assert place(list(range(30, 0, -1)), 9)['words'] == '22nd'
