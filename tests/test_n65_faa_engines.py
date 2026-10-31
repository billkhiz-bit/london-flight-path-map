"""N65 step 3: the FAA register's engines (scripts/n65_faa_engines.py), on a MADE-UP register in the FAA's shape.

Holds that only registration and engine leave the register (MASTER also carries owners' names and addresses), that
the engine code is resolved to maker + model, and that a row with no known engine is skipped, never guessed.
"""
import csv
import importlib.util
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('n65_faa_engines', REPO / 'scripts' / 'n65_faa_engines.py')
fe = importlib.util.module_from_spec(spec)
sys.modules['n65_faa_engines'] = fe
spec.loader.exec_module(fe)


def test_only_registration_and_engine_leave_the_register(tmp_path):
    z = tmp_path / 'ReleasableAircraft.zip'
    with zipfile.ZipFile(z, 'w') as zf:
        zf.writestr('ENGINE.txt', '﻿CODE,MFR,MODEL,TYPE,\n11111,MADE-UP MOTORS,ZX-100,5,\n22222,OTHER CO,QQ-7,5,\n')
        zf.writestr('MASTER.txt', '﻿N-NUMBER,SERIAL NUMBER,MFR MDL CODE,ENG MFR MDL,NAME,STREET,CITY,\n'
                                  '1AB  ,SN1,X,11111,A PRIVATE PERSON,1 SECRET ROAD,SOMEWHERE,\n'
                                  '22CD,SN2,X,99999,ANOTHER OWNER,2 ROAD,PLACE,\n'
                                  '3EF,SN3,X,22222,THIRD OWNER,3 ROAD,TOWN,\n')
    out = tmp_path / 'faa-engines.csv'
    assert fe.build(z, out) == (3, 2)
    text = out.read_text(encoding='utf-8')
    assert list(csv.reader(text.splitlines())) == [
        ['registration', 'engine'], ['N1AB', 'MADE-UP MOTORS ZX-100'], ['N3EF', 'OTHER CO QQ-7']]
    for owner_detail in ('PERSON', 'SECRET', 'SOMEWHERE', 'OWNER', 'SN1', 'N22CD'):
        assert owner_detail not in text
