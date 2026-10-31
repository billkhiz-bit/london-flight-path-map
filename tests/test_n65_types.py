"""N65 step 3: which ANP aircraft models a flight (scripts/n65_types.py).

Every aircraft, code and level here is MADE UP (ZZ01, PROXY-A, 80.0 dB...): EASA's tables never enter this public
repo, so the rules are held on a synthetic database shaped like the real one (the v2.3 CSVs and the v9 workbooks).
They hold Bill's 28 Oct order: own data over a proxy; the engine from the registration where a registry knows it;
else the LOUDER candidate judged on levels plus deltas, never on deltas alone; and a later release replacing an
earlier one's aircraft whole. Offline only.
"""
import csv
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load(name):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, REPO / 'scripts' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


t = _load('n65_types')
LEVELS = ['L_200ft', 'L_400ft', 'L_630ft', 'L_1000ft', 'L_2000ft']


def _write_v23(d: Path, aircraft: dict, npd: dict):
    """aircraft {ACFT_ID: NPD_ID}; npd {(NPD_ID, op): {power: level at 1,000 ft}} -> the v2.3 CSV shape."""
    d.mkdir(parents=True, exist_ok=True)
    with open(d / 'ANP2.3_Aircraft.csv', 'w', encoding='latin-1', newline='') as fh:
        w = csv.writer(fh, delimiter=';')
        w.writerow(['ACFT_ID', 'Description', 'NPD_ID'])
        for a, n in aircraft.items():
            w.writerow([a, f'made-up {a}', n])
    with open(d / 'ANP2.3_NPD_data.csv', 'w', encoding='latin-1', newline='') as fh:
        w = csv.writer(fh, delimiter=';')
        w.writerow(['NPD_ID', 'Noise Metric', 'Op Mode', 'Power Setting', *LEVELS])
        for (n, op), curves in npd.items():
            for power, lv in curves.items():
                w.writerow([n, 'LAmax', op, power, lv + 12, lv + 7, lv + 3, lv, lv - 6])
                w.writerow([n, 'SEL', op, power, lv + 20, lv + 15, lv + 11, lv + 8, lv + 2])  # never read


def _cand(icao, anp_id, dep=0.0, app=0.0, engine='', source='proxy'):
    return t.Candidate(icao, anp_id, dep, app, engine, source)


@pytest.fixture()
def anp(tmp_path):
    _write_v23(tmp_path / 'v23',
               {'PROXY-A': 'NA', 'PROXY-B': 'NB', 'OWN-C': 'NC', 'OLD-D': 'ND'},
               {('NA', 'D'): {10000: 80.0, 20000: 84.0}, ('NA', 'A'): {3000: 70.0},
                ('NB', 'D'): {10000: 81.0, 20000: 83.0}, ('NB', 'A'): {3000: 72.0},
                ('NC', 'D'): {20000: 79.0}, ('NC', 'A'): {3000: 69.0},
                ('ND', 'D'): {20000: 90.0}, ('ND', 'A'): {3000: 80.0}})
    return t.load_anp(tmp_path / 'v23')


def test_reads_lamax_at_1000ft_at_the_highest_power_and_ignores_sel(anp):
    assert anp['npd'][('NA', 'D')] == {10000.0: 80.0, 20000.0: 84.0}
    assert t.reference_level(anp, _cand('ZZ01', 'PROXY-A', dep=-2.0), 'D') == pytest.approx(82.0)
    assert t.reference_level(anp, _cand('ZZ01', 'PROXY-A', app=1.5), 'A') == pytest.approx(71.5)
    assert t.reference_level(anp, _cand('ZZ01', 'NOT-THERE'), 'D') is None


def test_one_proxy_is_used_with_its_label(anp):
    idx = t.index_candidates([_cand('ZZ01', 'PROXY-A', dep=-1.0)])
    r = t.resolve('zz01', 'G-ABCD', 'D', idx, anp)
    assert (r.how, r.candidate.anp_id) == ('proxy', 'PROXY-A')


def test_own_data_for_any_engine_beats_every_proxy_even_a_louder_one(anp):
    idx = t.index_candidates([_cand('ZZ02', 'PROXY-B', dep=+9.0, engine=r'\bCFM'),
                              _cand('ZZ02', 'OWN-C', source='own')])
    r = t.resolve('ZZ02', '', 'D', idx, anp)
    assert (r.how, r.candidate.anp_id) == ('own', 'OWN-C')


def test_unknown_engine_takes_the_louder_variant_judged_on_levels_not_deltas(anp):
    # Deltas and levels disagree on purpose: deltas alone say PROXY-B (-0.5 > -1.0), levels say PROXY-A
    # (84 - 1.0 = 83.0 against 83 - 0.5 = 82.5, each at its highest power). The rule must take A.
    idx = t.index_candidates([_cand('ZZ03', 'PROXY-A', dep=-1.0, engine=r'\bCFM'),
                              _cand('ZZ03', 'PROXY-B', dep=-0.5, engine=r'\bPW')])
    r = t.resolve('ZZ03', 'G-NONE', 'D', idx, anp)
    assert (r.how, r.candidate.anp_id) == ('louder-variant', 'PROXY-A')
    # And per operation: on approach B is louder (72 - 0 > 70 - 0).
    assert t.resolve('ZZ03', 'G-NONE', 'A', idx, anp).candidate.anp_id == 'PROXY-B'


def test_the_registration_decides_where_a_registry_knows_the_engine(anp):
    idx = t.index_candidates([_cand('ZZ03', 'PROXY-A', dep=-1.0, engine=r'\bCFM|LEAP'),
                              _cand('ZZ03', 'PROXY-B', dep=-0.5, engine=r'\bPW')])
    registry = {'G-PRAT': 'PW1127G-JM', 'G-LEAP': 'LEAP-1A26', 'G-ODDS': 'unknown maker X1'}
    assert t.resolve('ZZ03', 'g-prat', 'D', idx, anp, registry).candidate.anp_id == 'PROXY-B'
    r = t.resolve('ZZ03', 'G-LEAP', 'D', idx, anp, registry)
    assert (r.how, r.candidate.anp_id) == ('by-registration', 'PROXY-A')
    # An engine the rows do not name falls back to the louder, said as such.
    assert t.resolve('ZZ03', 'G-ODDS', 'D', idx, anp, registry).how == 'louder-variant'


def test_own_data_replaces_the_proxy_for_the_same_engine_before_louder_is_asked(anp):
    # The PW proxy is louder than the PW own data, and the CFM proxy is quieter than both. Own PW must stand for PW,
    # so the choice is between own PW (79) and the CFM proxy (84 - 6 = 78): own PW, never the PW proxy (90).
    idx = t.index_candidates([_cand('ZZ04', 'OLD-D', engine=r'\bPW'),
                              _cand('ZZ04', 'OWN-C', engine=r'\bPW', source='own'),
                              _cand('ZZ04', 'PROXY-A', dep=-6.0, engine=r'\bCFM')])
    r = t.resolve('ZZ04', '', 'D', idx, anp)
    assert (r.how, r.candidate.anp_id) == ('louder-variant', 'OWN-C')
    # With the engine known as PW, own data again, by registration.
    r = t.resolve('ZZ04', 'G-PW00', 'D', idx, anp, {'G-PW00': 'PW1130G'})
    assert (r.how, r.candidate.anp_id) == ('by-registration', 'OWN-C')


def test_absence_is_said_never_guessed(anp):
    idx = t.index_candidates([_cand('ZZ05', 'NOT-IN-ANY-RELEASE')])
    assert t.resolve('', 'G-ABCD', 'D', idx, anp).how == 'type-unknown'
    assert t.resolve('ZZ99', 'G-ABCD', 'D', idx, anp).how == 'no-candidate'
    r = t.resolve('ZZ05', 'G-ABCD', 'D', idx, anp)
    assert (r.how, r.candidate) == ('not-in-database', None)


def test_a_later_release_replaces_an_aircraft_whole(tmp_path):
    _write_v23(tmp_path / 'old', {'SHARED': 'N-OLD', 'SAME-NPD': 'N-SAME'},
               {('N-OLD', 'D'): {20000: 90.0}, ('N-SAME', 'D'): {20000: 91.0, 30000: 95.0}})
    _write_v23(tmp_path / 'new', {'SHARED': 'N-NEW', 'ONLY-NEW': 'N-X', 'SAME-NPD': 'N-SAME'},
               {('N-NEW', 'D'): {20000: 70.0}, ('N-X', 'D'): {20000: 75.0}, ('N-SAME', 'D'): {20000: 71.0}})
    anp = t.load_anp(tmp_path / 'old', tmp_path / 'new')
    assert anp['aircraft']['SHARED'] == 'N-NEW'
    assert t.reference_level(anp, _cand('ZZ06', 'SHARED'), 'D') == pytest.approx(70.0)
    assert 'ONLY-NEW' in anp['aircraft']
    # The same NPD id in both releases: the later one's curves, whole (the old 30,000 power setting is not kept).
    assert anp['npd'][('N-SAME', 'D')] == {20000.0: 71.0}


def test_engine_makers_read_from_easas_variant_text():
    assert t.engine_match_from_variant('A320neo CFM engines') == t.ENGINE_MAKERS[0][1]
    assert t.engine_match_from_variant('A320neo IAE engines') == t.ENGINE_MAKERS[1][1]
    assert t.engine_match_from_variant('Trent 1000 engines') == t.ENGINE_MAKERS[2][1]
    assert t.engine_match_from_variant('GEnx engines') == t.ENGINE_MAKERS[3][1]
    assert t.engine_match_from_variant('') == ''
    assert t.engine_match_from_variant('CFM or IAE engines') == ''  # names two makers: no engine condition
    # The A320neo's Pratt engines are IAE LLC's (PW1100G-JM): a registry writing either finds the same rows.
    import re
    assert re.search(t.ENGINE_MAKERS[1][1], 'PW1127G-JM', re.I)
    assert re.search(t.ENGINE_MAKERS[1][1], 'IAE V2527-A5', re.I)
    assert not re.search(t.ENGINE_MAKERS[0][1], 'PW1127G-JM', re.I)


def test_phase0_substitution_csv_reads_as_proxies_with_engine_conditions(tmp_path):
    p = tmp_path / 'subs.csv'
    p.write_text('AIRFRAME_MANUFACTURER,ICAO_CODE,AIRCRAFT_VARIANT,ANP_PROXY,DELTA_DEP_dB,DELTA_APP_dB\n'
                 'MADEUP,ZZ07,ZZ7neo CFM engines,PROXY-A,-1.5,-0.5\n'
                 'MADEUP,ZZ07,ZZ7neo IAE engines,PROXY-B,-2.5,-1.0\n'
                 'MADEUP,ZZ08,,PROXY-A,0.5,0\n', encoding='utf-8')
    rows = t.read_candidates(p)
    assert [(c.icao, c.anp_id, c.delta_dep, c.source) for c in rows] == [
        ('ZZ07', 'PROXY-A', -1.5, 'proxy'), ('ZZ07', 'PROXY-B', -2.5, 'proxy'), ('ZZ08', 'PROXY-A', 0.5, 'proxy')]
    assert rows[0].engine_match == t.ENGINE_MAKERS[0][1] and rows[2].engine_match == ''


def test_a_hand_kept_own_row_names_its_engine_maker_and_groups_with_easas_proxy(tmp_path, anp):
    own = tmp_path / 'own.csv'
    own.write_text('ICAO_CODE,ANP_ID,DELTA_DEP_dB,DELTA_APP_dB,ENGINE_MATCH,SOURCE,NOTE\n'
                   'ZZ07,OWN-C,0,0,IAE|PW,own,made-up\n', encoding='utf-8')
    subs = tmp_path / 'subs.csv'
    subs.write_text('AIRFRAME_MANUFACTURER,ICAO_CODE,AIRCRAFT_VARIANT,ANP_PROXY,DELTA_DEP_dB,DELTA_APP_dB\n'
                    'MADEUP,ZZ07,ZZ7neo IAE engines,OLD-D,0,0\n', encoding='utf-8')
    own_rows = t.read_candidates(own)
    assert own_rows[0].engine_match == t.ENGINE_MAKERS[1][1] and own_rows[0].source == 'own'
    # Same engine group: the own row replaces EASA's louder proxy (OLD-D, 90 dB) without "louder" being asked.
    r = t.resolve('ZZ07', '', 'D', t.index_candidates(t.read_candidates(subs), own_rows), anp)
    assert (r.how, r.candidate.anp_id) == ('own', 'OWN-C')
