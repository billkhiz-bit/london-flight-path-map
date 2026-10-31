"""Which ANP aircraft models a flight's noise: N65 step 3 (docs/lessons/n65.md).

An ADS-B record names its type by ICAO designator (`t`, e.g. A20N) and its registration (`r`). Doc 29 needs an
aircraft from EASA's ANP database. This module chooses one, by rules only: every table it reads is passed in by
path, because EASA's tables (levels AND the ICAO-to-ANP mapping) stay out of this public repo
(data/n65/, or the full database kept outside the repo).

THE ORDER OF PREFERENCE (Bill's rulings, 28 Oct 2026):
  1. The aircraft's OWN ANP data (no adjustment) over a proxy plus EASA's dB deltas.
  2. Where a type's candidates differ by engine, the engine read from the REGISTRATION, when a registry knows it.
  3. Otherwise the LOUDER candidate, so a map that errs errs loud, judged on LEVELS (the candidate's NPD level at the
     reference distance plus its delta), never on the deltas alone: candidates use different proxy aircraft.
A type with no candidate, or a record with no type, is said (`how`), never guessed.

THE DATABASES. EASA's legacy tables v2.3 (Oct 2020, 155 aircraft) and the v9 release EASA sent on 29 Oct 2026 (14
aircraft, 13 of them newer types such as the A320neo and the 787-9, with NPD tables of their own) are ONE database:
`load_anp()` reads both and an id present in both is taken from the later one.

CANDIDATES come from two gitignored CSVs with the same columns (see CANDIDATE_COLUMNS): EASA's substitution table
(phase 0's `anp-substitutions-by-icao-code.csv`, proxies with deltas) and a hand-kept list of types the database
models directly (`own-data-by-icao.csv`, deltas 0). `engine_match` is a regular expression tested against a
registry's engine text (case-insensitive); blank means the row applies whatever the engine.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

CANDIDATE_COLUMNS = ('ICAO_CODE', 'ANP_ID', 'DELTA_DEP_dB', 'DELTA_APP_dB', 'ENGINE_MATCH', 'SOURCE', 'NOTE')
OPS = ('D', 'A')  # departure, approach: Doc 29's NPD op modes
REFERENCE_FT = 'L_1000ft'  # where "louder" is judged: NPD LAmax at 1,000 ft (a 65 dB contour lies near it)


@dataclass(frozen=True)
class Candidate:
    icao: str
    anp_id: str
    delta_dep: float
    delta_app: float
    engine_match: str  # regex, '' = any engine
    source: str  # 'own' (deltas 0) or 'proxy'

    def delta(self, op: str) -> float:
        return self.delta_dep if op == 'D' else self.delta_app


@dataclass(frozen=True)
class Resolution:
    icao: str
    op: str
    candidate: Candidate | None
    how: str  # one of HOW
    candidates: int


HOW = ('own', 'proxy', 'by-registration', 'louder-variant', 'no-candidate', 'not-in-database', 'type-unknown')


def _clean(v) -> str:
    return '' if v is None else str(v).strip()


def read_candidates(path: Path) -> list[Candidate]:
    """One candidate per row. The phase 0 substitution CSV names its proxy ANP_PROXY and has no ENGINE_MATCH/SOURCE:
    it is read as proxies, its AIRCRAFT_VARIANT text kept for engine_match_from_variant()."""
    out = []
    with open(path, encoding='utf-8-sig', newline='') as fh:
        for r in csv.DictReader(fh):
            anp_id = _clean(r.get('ANP_ID') or r.get('ANP_PROXY'))
            icao = _clean(r.get('ICAO_CODE')).upper()
            if not icao or not anp_id:
                continue
            match = _clean(r.get('ENGINE_MATCH'))
            if not match and 'ENGINE_MATCH' not in r:
                match = engine_match_from_variant(_clean(r.get('AIRCRAFT_VARIANT')))
            # A maker's NAME stands for its regex, so a hand-kept row and EASA's proxy row for the same engine group
            # together in _collapse() (they must be the identical string).
            match = dict(ENGINE_MAKERS).get(match, match)
            out.append(Candidate(icao, anp_id, float(r.get('DELTA_DEP_dB') or 0), float(r.get('DELTA_APP_dB') or 0),
                                 match, _clean(r.get('SOURCE')) or 'proxy'))
    return out


# Engine makers as EASA's substitution table names them in AIRCRAFT_VARIANT, and as a registry may write them.
# IAE is listed with Pratt & Whitney because the A320neo's PW1100G-JM is built by IAE LLC (and the 2018 table calls
# the neo's Pratt engines "IAE"); the A320ceo's V2500 is IAE's too.
ENGINE_MAKERS = (
    ('CFM', r'\bCFM|LEAP'),
    ('IAE|PW', r'\bIAE\b|V2500|\bPW\d|\bPW\b|PRATT|JT8D|JT9D'),
    ('RR', r'ROLLS|\bRR\b|TRENT|RB211|\bBR7\d\d|TAY\b|SPEY'),
    ('GE', r'GENERAL ELECTRIC|\bGE\b|\bGE\d|GENX|\bCF6|\bCF34|GE90'),
)


def engine_match_from_variant(variant_text: str) -> str:
    """A regex for the engine maker a substitution row's variant text names, '' if it names none (or several)."""
    text = variant_text.upper()
    hits = [rx for _name, rx in ENGINE_MAKERS if re.search(rx, text)]
    return hits[0] if len(hits) == 1 else ''


def load_anp(*dirs: Path) -> dict:
    """{'aircraft': {ACFT_ID: NPD_ID}, 'npd': {(NPD_ID, op): {power: level at REFERENCE_FT}}} (LAmax only).

    Each dir holds either the v2.3 CSVs (`ANP2.3_Aircraft.csv`, `ANP2.3_NPD_data.csv`, ';'-separated, latin-1) or the
    v9 workbooks (`*_Aircraft_v9.xlsx`, `*_NPD_Data_v9.xlsx`). Later dirs win on the same id."""
    aircraft, npd = {}, {}
    for d in dirs:
        d = Path(d)
        ac_rows, npd_rows = _table(d, 'Aircraft'), _table(d, 'NPD')
        for r in ac_rows:
            if _clean(r.get('ACFT_ID')):
                aircraft[_clean(r['ACFT_ID'])] = _clean(r.get('NPD_ID'))
        fresh = {}
        for r in npd_rows:
            if _clean(r.get('Noise Metric')).upper() != 'LAMAX' or _clean(r.get('Op Mode')).upper() not in OPS:
                continue
            key = (_clean(r['NPD_ID']), _clean(r['Op Mode']).upper())
            level = r.get(REFERENCE_FT)
            if level in (None, ''):
                continue
            fresh.setdefault(key, {})[float(r['Power Setting'])] = float(level)
        npd.update(fresh)  # an NPD id's curves come whole from one release, never mixed
    return {'aircraft': aircraft, 'npd': npd}


def _table(d: Path, kind: str) -> list[dict]:
    csvs = sorted(d.glob(f'ANP*_{kind}*data.csv')) + sorted(d.glob(f'ANP*_{kind}.csv'))
    if csvs:
        with open(csvs[0], encoding='latin-1', newline='') as fh:
            return [{k.strip(): v for k, v in r.items() if k} for r in csv.DictReader(fh, delimiter=';')]
    books = sorted(d.glob(f'*_{kind}*_v*.xlsx'))
    if not books:
        raise FileNotFoundError(f'no ANP {kind} table in {d}')
    import openpyxl  # only the v9 workbooks need it

    ws = openpyxl.load_workbook(books[0], read_only=True, data_only=True).worksheets[0]
    it = ws.iter_rows(values_only=True)
    head = [_clean(c) for c in next(it)]
    return [dict(zip(head, row, strict=False)) for row in it if any(c is not None for c in row)]  # rows can be ragged


def reference_level(anp: dict, candidate: Candidate, op: str) -> float | None:
    """The candidate's LAmax at REFERENCE_FT at its highest listed power for `op`, plus its delta. None if the
    database cannot say (no aircraft, no NPD curve): such a candidate is never chosen as the louder."""
    npd_id = anp['aircraft'].get(candidate.anp_id)
    curves = anp['npd'].get((npd_id, op)) if npd_id else None
    if not curves:
        return None
    return curves[max(curves)] + candidate.delta(op)


def resolve(icao: str, registration: str, op: str, candidates: dict[str, list[Candidate]], anp: dict,
            registry: dict[str, str] | None = None) -> Resolution:
    """Choose the ANP aircraft for one movement. `candidates` is by ICAO code (index_candidates()); `registry` maps a
    registration to its engine text, and may be empty."""
    icao = _clean(icao).upper()
    if not icao:
        return Resolution('', op, None, 'type-unknown', 0)
    rows = candidates.get(icao, [])
    if not rows:
        return Resolution(icao, op, None, 'no-candidate', 0)
    usable = [c for c in rows if c.anp_id in anp['aircraft']]
    if not usable:
        return Resolution(icao, op, None, 'not-in-database', len(rows))
    engine = (registry or {}).get(_clean(registration).upper(), '')
    if engine:
        fitting = [c for c in usable if c.engine_match and re.search(c.engine_match, engine, re.I)]
        if fitting:
            reps = _collapse(fitting)
            if len(reps) == 1:
                return Resolution(icao, op, reps[0], 'by-registration', len(rows))
            usable = reps
    reps = _collapse(usable)
    if len(reps) == 1:
        c = reps[0]
        return Resolution(icao, op, c, 'own' if c.source == 'own' else 'proxy', len(rows))
    known = [(lv, c) for lv, c in ((reference_level(anp, c, op), c) for c in reps) if lv is not None]
    if not known:
        return Resolution(icao, op, None, 'not-in-database', len(rows))
    return Resolution(icao, op, max(known, key=lambda t: t[0])[1], 'louder-variant', len(rows))


def _collapse(cands: list[Candidate]) -> list[Candidate]:
    """One representative per engine: own data replaces a proxy FOR THE SAME ENGINE before "louder" is ever asked
    (a proxy's delta never outvotes the aircraft's own tables). Own data with no engine condition models every
    engine, so it wins outright. Several proxies for one engine are all kept: the louder decides."""
    any_engine_own = [c for c in cands if c.source == 'own' and not c.engine_match]
    if any_engine_own:
        return any_engine_own[:1]
    groups: dict[str, list[Candidate]] = {}
    for c in cands:
        groups.setdefault(c.engine_match, []).append(c)
    reps = []
    for group in groups.values():
        own = [c for c in group if c.source == 'own']
        reps.extend(own[:1] if own else group)
    return reps


def index_candidates(*lists: list[Candidate]) -> dict[str, list[Candidate]]:
    out: dict[str, list[Candidate]] = {}
    for rows in lists:
        for c in rows:
            out.setdefault(c.icao, []).append(c)
    return out
