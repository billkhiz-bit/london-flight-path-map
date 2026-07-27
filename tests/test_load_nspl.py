"""Tests for scripts/load_nspl.py, the offline ONS NSPL -> DynamoDB loader.

The loader never runs in Lambda and never runs in CI, but `_row_to_item` is
pure and holds every skip decision and every attribute name the score Lambda
later reads back. A defect there is invisible until 2.7M rows are already in
DynamoDB, so this is the cheapest high-value coverage in the feature.

Offline only: no AWS, no network, no boto3. The loader lazy-imports boto3 and
tqdm inside run_load, so importing the module at test-collection time is safe.
"""

import csv
import importlib.util
import json
import os
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from conftest import load_lambda  # noqa: E402

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), os.pardir))


def _load_script(alias, path):
    """Import a standalone script by path.

    conftest's load_lambda only knows backend/lambdas/<name>/app.py, and the
    loader deliberately lives outside that tree.
    """
    if alias in sys.modules:
        return sys.modules[alias]
    spec = importlib.util.spec_from_file_location(alias, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


load_nspl = _load_script("load_nspl", os.path.join(REPO_ROOT, "scripts", "load_nspl.py"))
score_app = load_lambda("score")


# ---------------------------------------------------------------------------
# Fixtures: real rows from the ONS NSPL 2026-02 edition (data/nspl.csv),
# reduced to the eight columns _row_to_item actually reads.
# ---------------------------------------------------------------------------
def _row(pcds, doterm, gridind, lad, ctry, rgn, lat, long):
    return {
        "pcds": pcds,
        "doterm": doterm,
        "gridind": gridind,
        "lad25cd": lad,
        "ctry25cd": ctry,
        "rgn25cd": rgn,
        "lat": lat,
        "long": long,
    }


# Live London, building-level.
ROW_SW11_1AA = _row("SW11 1AA", "", "1", "E09000032", "E92000001", "E12000007",
                    "51.464444", "-0.164298")
# Boundary: City of London, not Tower Hamlets.
ROW_E1_6AN = _row("E1 6AN", "", "1", "E09000001", "E92000001", "E12000007",
                  "51.518887", "-0.078479")
# Negative-near-zero longitude, the sentinel trap.
ROW_SE10_9NF = _row("SE10 9NF", "", "1", "E09000011", "E92000001", "E12000007",
                    "51.480285", "-0.00602")
# Terminated (1984-12) and coarse-positioned (gridind 8, pre-Gridlink).
ROW_BR1_1HB = _row("BR1 1HB", "198412", "8", "E09000006", "E92000001", "E12000007",
                   "51.404506", "0.014262")
# Non-London England.
ROW_M1_1AE = _row("M1 1AE", "", "1", "E08000003", "E92000001", "E12000002",
                  "53.483487", "-2.231182")
# Unpositioned: gridind 9 with the 99.999999 / 0 sentinel pair.
ROW_AB11_3AG = _row("AB11 3AG", "199707", "9", "", "", "", "99.999999", "0")
# Channel Islands, never positioned by ONS.
ROW_GY1_1AA = _row("GY1 1AA", "", "9", "L99999999", "L93000001", "L99999999",
                   "99.999999", "0")
# Scotland: live and positioned, but region is an England-only geography.
ROW_AB1_1EZ = _row("AB1 1EZ", "199606", "1", "S12000033", "S92000003", "S99999999",
                   "57.153735", "-2.103165")


class TestBoroughMap:
    """LONDON_LAD_TO_BOROUGH is the single point where a typo becomes a
    silent 404 for an entire borough, so it gets the strictest test here."""

    def test_map_matches_score_lambda_exactly(self):
        # normalise_borough does no case-folding, no trimming and no '&'
        # normalisation, and calc_score then indexes boroughs[name] directly.
        # 'Kensington & Chelsea' or 'Richmond Upon Thames' in the data would
        # 404 every postcode in that borough — and because a local hit never
        # falls back, postcodes.io would not rescue it either.
        assert len(load_nspl.LONDON_LAD_TO_BOROUGH) == 33
        assert len(score_app.LONDON_BOROUGHS) == 33
        assert set(load_nspl.LONDON_LAD_TO_BOROUGH.values()) == set(
            score_app.LONDON_BOROUGHS.keys()
        )

    def test_every_name_survives_normalise_borough(self):
        # Exact first-branch match: no name may depend on a BOROUGH_ALIASES
        # entry to resolve, because aliases are a convenience for callers,
        # not a correction layer for our own data.
        for name in load_nspl.LONDON_LAD_TO_BOROUGH.values():
            assert score_app.normalise_borough(name, "london") == name

    def test_lad_codes_are_the_33_e09_codes(self):
        expected = {f"E090000{i:02d}" for i in range(1, 34)}
        assert set(load_nspl.LONDON_LAD_TO_BOROUGH.keys()) == expected


class TestRowToItem:
    """_row_to_item is pure and owns every skip decision, so it is driven
    directly with the verified CSV fixtures rather than through run_load."""

    def test_live_london_row(self):
        item = load_nspl._row_to_item(ROW_SW11_1AA)
        assert item["postcode"] == {"S": "SW111AA"}
        assert item["lat"] == {"N": "51.464444"}
        assert item["lon"] == {"N": "-0.164298"}
        assert item["lad"] == {"S": "E09000032"}
        assert item["b"] == {"S": "Wandsworth"}
        assert item["rgn"] == {"S": "London"}
        # Absence is meaningful: no dt means live, no q means building-level.
        assert "dt" not in item
        assert "q" not in item
        # pcds is derived by the Lambda, never stored.
        assert "pcds" not in item

    def test_boundary_row_is_city_of_london(self):
        item = load_nspl._row_to_item(ROW_E1_6AN)
        assert item["b"] == {"S": "City of London"}

    def test_negative_near_zero_longitude_is_not_skipped(self):
        # THE SENTINEL TRAP. Any implementation testing `long == 0` (or the
        # truthiness of long) fails here: longitude 0 is a legitimate London
        # value and postcodes sit on both sides of the Greenwich meridian.
        item = load_nspl._row_to_item(ROW_SE10_9NF)
        assert item is not None
        assert item["lon"] == {"N": "-0.006020"}
        assert item["b"] == {"S": "Greenwich"}

    def test_terminated_and_coarse_row(self):
        item = load_nspl._row_to_item(ROW_BR1_1HB)
        assert item["dt"] == {"S": "198412"}
        assert item["q"] == {"N": "8"}
        assert item["b"] == {"S": "Bromley"}

    def test_live_building_level_row_omits_quality(self):
        # gridind 1 is the common case, so it carries no attribute at all.
        assert "q" not in load_nspl._row_to_item(ROW_E1_6AN)

    def test_unpositioned_row_is_skipped(self):
        assert load_nspl._row_to_item(ROW_AB11_3AG) is None

    def test_channel_islands_row_is_skipped(self):
        assert load_nspl._row_to_item(ROW_GY1_1AA) is None

    def test_excluded_country_is_skipped_independently_of_gridind(self):
        # Defence in depth for a future NSPL edition: in the 2026-02 file
        # every Channel Islands / Isle of Man row also carries gridind 9, so
        # the country test is not currently load-bearing. Force gridind 1 to
        # prove the country branch actually fires on its own.
        row = dict(ROW_GY1_1AA, gridind="1", lad25cd="L99999999", lat="49.45", long="-2.58")
        assert load_nspl._row_to_item(row) is None

    def test_blank_lad_is_skipped(self):
        assert load_nspl._row_to_item(dict(ROW_SW11_1AA, lad25cd="")) is None

    def test_non_london_england_row_has_no_borough(self):
        # This is what keeps the existing "Borough not currently supported"
        # 404 byte-identical: no `b` -> admin_district None -> same 404.
        item = load_nspl._row_to_item(ROW_M1_1AE)
        assert item is not None
        assert "b" not in item
        assert item["rgn"] == {"S": "North West"}
        assert item["lad"] == {"S": "E08000003"}

    def test_non_england_row_has_no_region(self):
        # Region is an England-only geography, so Scottish rows carry the
        # S99999999 placeholder and simply get no `rgn` attribute.
        item = load_nspl._row_to_item(ROW_AB1_1EZ)
        assert item is not None
        assert "rgn" not in item
        assert item["dt"] == {"S": "199606"}

    @pytest.mark.parametrize("bad", ["", "not-a-number", "N/A"])
    def test_unparsable_coordinates_are_skipped(self, bad):
        assert load_nspl._row_to_item(dict(ROW_SW11_1AA, lat=bad)) is None
        assert load_nspl._row_to_item(dict(ROW_SW11_1AA, long=bad)) is None

    def test_none_coordinates_are_skipped_not_raised(self):
        # csv.DictReader yields None for a short row's trailing fields. The
        # loader hardens its string columns against that; the coordinate
        # coercion must degrade the same way, because an exception escaping
        # the row loop kills a 40-minute run outright.
        assert load_nspl._row_to_item(dict(ROW_SW11_1AA, lat=None)) is None
        assert load_nspl._row_to_item(dict(ROW_SW11_1AA, long=None)) is None

    def test_missing_column_is_skipped_not_raised(self):
        row = dict(ROW_SW11_1AA)
        del row["gridind"]
        assert load_nspl._row_to_item(row) is None


class TestSpacedFormInvariant:
    """The Lambda derives `location.postcode` as key[:-3] + ' ' + key[-3:]
    instead of storing pcds. That is only sound while the inward code is
    always the final three characters."""

    def test_derivation_round_trips(self):
        for row in (ROW_SW11_1AA, ROW_E1_6AN, ROW_SE10_9NF, ROW_BR1_1HB,
                    ROW_M1_1AE, ROW_AB1_1EZ):
            pc = load_nspl._row_to_item(row)["postcode"]["S"]
            assert f"{pc[:-3]} {pc[-3:]}" == row["pcds"]

    def test_keys_are_at_most_seven_characters(self):
        # The measured maximum across all 2,723,596 rows. Longer keys would
        # not break DynamoDB, but they would mean the format assumption above
        # has drifted and the derivation needs re-verifying.
        for row in (ROW_SW11_1AA, ROW_E1_6AN, ROW_SE10_9NF, ROW_BR1_1HB,
                    ROW_M1_1AE, ROW_AB1_1EZ):
            assert len(load_nspl._row_to_item(row)["postcode"]["S"]) <= 7


# ---------------------------------------------------------------------------
# Checkpoint / resume harness (audit S1, S2, S3).
#
# These drive the REAL run_load() against a synthetic CSV with boto3 and tqdm
# monkeypatched out. Nothing here touches AWS, the network, or the 805 MB file.
#
# The defects these guard are the expensive kind: silent, invisible, and only
# observable 2.7M rows later as a handful of postcodes that resolve via
# postcodes.io forever because they were parsed but never written.
# ---------------------------------------------------------------------------
CSV_COLUMNS = ["pcds", "doterm", "gridind", "lad25cd", "ctry25cd", "rgn25cd", "lat", "long"]

# The 33 London LAD codes cycle so most rows carry a `b`, and every fourth
# block is a run of gridind-9 rows — the skip path that made the DEFRA
# loader's checkpoint unreachable (S3). The Channel Islands / Isle of Man
# rows in the real file skip in one contiguous 13,156-row block, so a run of
# skips is the realistic shape, not an isolated row.
def _synthetic_rows(count):
    rows = []
    for i in range(count):
        outward = f"SW{i // 26 + 1}"
        inward = f"{i % 10}{chr(ord('A') + i % 26)}{chr(ord('A') + (i * 7) % 26)}"
        skipped = (i % 40) >= 34  # a 6-row run of skips every 40 rows
        rows.append({
            "pcds": f"{outward} {inward}",
            "doterm": "198412" if i % 17 == 0 else "",
            "gridind": "9" if skipped else ("8" if i % 11 == 0 else "1"),
            "lad25cd": "" if skipped else f"E090000{(i % 33) + 1:02d}",
            "ctry25cd": "E92000001",
            "rgn25cd": "E12000007",
            "lat": "99.999999" if skipped else f"{51.4 + (i % 1000) / 10000:.6f}",
            "long": f"{-0.2 + (i % 997) / 10000:.6f}",
        })
    return rows


def _write_csv(path, rows):
    # utf-8-sig, because the real NSPL download is BOM-prefixed and run_load
    # opens with utf-8-sig — a plain utf-8 fixture would not exercise that.
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


class _FakeDdb:
    """A DynamoDB stand-in backed by a plain dict, so a killed run and its
    resume can share one `table` exactly as they share one real table.

    `kill_after` makes the Nth item write — and every write after it — raise
    KeyboardInterrupt: a faithful mid-flush Ctrl-C, and the same shape as
    _flush_batch's ex.map() re-raising a chunk failure. The counter advances
    per ITEM on both write paths, so an interrupt lands mid-chunk on the
    BatchWriteItem path exactly as it landed mid-batch on the PutItem one and
    the checkpoint-invariant tests keep their original meaning.

    `unprocessed_rounds` makes the first N BatchWriteItem calls return their
    last item in UnprocessedItems instead of storing it, modelling DynamoDB's
    partial success. That case is an HTTP 200, so nothing raises and only the
    loader's own retry loop can recover it.

    `deny` / `invalid` make batch_write_item raise the ClientError the loader
    is expected to absorb by falling back to per-item PutItem.
    """

    def __init__(self, table=None, kill_after=None, unprocessed_rounds=0,
                 deny=False, invalid=False):
        self.table = {} if table is None else table
        self.kill_after = kill_after
        self.unprocessed_rounds = unprocessed_rounds
        self.deny = deny
        self.invalid = invalid
        self.puts = 0
        self.batch_calls = 0
        # Imported here, not at module scope, for the same reason boto3 is
        # (see the fixture below): collection must not require the AWS SDK.
        from botocore.exceptions import ClientError
        self._client_error = ClientError
        self.exceptions = types.SimpleNamespace(ClientError=ClientError)

    def _store(self, item):
        self.puts += 1
        if self.kill_after is not None and self.puts >= self.kill_after:
            raise KeyboardInterrupt('simulated Ctrl-C mid-flush')
        self.table[item['postcode']['S']] = item

    def put_item(self, TableName, Item):  # noqa: N803 — botocore's own casing
        self._store(Item)

    def batch_write_item(self, RequestItems):  # noqa: N803 — botocore's own casing
        self.batch_calls += 1
        if self.deny:
            raise self._client_error(
                {'Error': {'Code': 'AccessDeniedException', 'Message': 'not authorised'}},
                'BatchWriteItem',
            )
        if self.invalid:
            raise self._client_error(
                {'Error': {'Code': 'ValidationException',
                           'Message': 'duplicate key in request'}},
                'BatchWriteItem',
            )

        requests = RequestItems[load_nspl.TABLE_NAME]
        held = []
        if self.unprocessed_rounds > 0 and requests:
            # Hold back the last item even when it is the ONLY item, so a
            # rounds count above BWI_MAX_ATTEMPTS models DynamoDB refusing
            # indefinitely. Skipping the single-item case would let every
            # retry succeed and the exhaustion path would be untestable.
            self.unprocessed_rounds -= 1
            requests, held = requests[:-1], requests[-1:]

        for request in requests:
            self._store(request['PutRequest']['Item'])

        return {'UnprocessedItems': {load_nspl.TABLE_NAME: held} if held else {}}

    def get_item(self, TableName, Key):  # noqa: N803 — botocore's own casing
        item = self.table.get(Key['postcode']['S'])
        return {'Item': item} if item is not None else {}

    @property
    def postcodes(self):
        return {k for k in self.table if k != load_nspl.META_KEY}


@pytest.fixture(autouse=True)
def _reset_batch_write_latch():
    """Clear the module-level AccessDenied latch between tests.

    _BATCH_WRITE_DENIED is sticky by design — one denial should not re-probe
    108,000 times in a real run — but that stickiness would otherwise leak out
    of the fallback tests and silently route every later test down the PutItem
    path, hiding a broken BatchWriteItem implementation behind green tests.
    """
    load_nspl._BATCH_WRITE_DENIED = False
    yield
    load_nspl._BATCH_WRITE_DENIED = False


@pytest.fixture
def loader_env(tmp_path, monkeypatch):
    """Point the loader at a temp CSV and checkpoint, shrink the batch and
    checkpoint intervals so a few hundred rows exercise many flushes, and
    replace the two lazy imports run_load makes.

    tqdm is stubbed by INJECTING a module rather than patching an installed
    one: CI installs `pytest pytest-mock boto3` and nothing else, and
    run_load's `from tqdm import tqdm` sits inside a try/except ImportError
    that calls sys.exit(1) — so depending on a real tqdm would turn these
    into an sys.exit in CI while passing on any dev machine that has it.
    """
    import boto3

    tqdm_stub = types.ModuleType('tqdm')
    tqdm_stub.tqdm = lambda it, **kw: it
    monkeypatch.setitem(sys.modules, 'tqdm', tqdm_stub)

    csv_path = tmp_path / 'nspl.csv'
    checkpoint = tmp_path / '.nspl_load_checkpoint'
    monkeypatch.setattr(load_nspl, 'NSPL_CSV_PATH', Path(csv_path))
    monkeypatch.setattr(load_nspl, 'CHECKPOINT_PATH', Path(checkpoint))
    monkeypatch.setattr(load_nspl, 'BATCH_SIZE', 5)
    monkeypatch.setattr(load_nspl, 'CHECKPOINT_EVERY', 10)

    holder = {}

    def _run(ddb):
        """Run the loader to completion (or to its interrupt) against *ddb*."""
        holder['ddb'] = ddb
        monkeypatch.setattr(boto3, 'client', lambda *a, **kw: ddb)
        # workers=1 keeps _flush_batch's ThreadPoolExecutor deterministic, so
        # "the Nth put" is a fixed point in the row order.
        load_nspl.run_load(limit=None, dry_run=False, workers=1)

    return {'csv': csv_path, 'checkpoint': checkpoint, 'run': _run, 'holder': holder}


def _expected_key_by_row(rows):
    """Row index -> the DynamoDB key that row produces, or None if skipped."""
    return [
        (item['postcode']['S'] if item is not None else None)
        for item in (load_nspl._row_to_item(row) for row in rows)
    ]


class TestCheckpointInvariant:
    """audit S1 + S3. The checkpoint recorded the CSV row index every 1,000
    rows with no dependency on the 500-item write buffer having flushed, so an
    interrupt left the checkpoint AHEAD of what was written and the resume's
    `idx < checkpoint: continue` skipped those parsed-but-never-written rows
    forever. Measured over the real file: 2,684 of the 2,701 checkpoints the
    old rule wrote had a mean of 267 and up to 499 items still in the buffer."""

    def test_checkpoint_never_runs_ahead_of_the_last_flush(self, loader_env, monkeypatch):
        # The invariant, asserted at the exact instant each checkpoint is
        # written: every item derived from a row at or before the recorded
        # index is already in the table.
        rows = _synthetic_rows(400)
        _write_csv(loader_env['csv'], rows)
        keys = _expected_key_by_row(rows)

        observed = []
        real_write = load_nspl._write_checkpoint

        def _spy(state):
            observed.append((state['row'], set(loader_env['holder']['ddb'].postcodes)))
            real_write(state)

        monkeypatch.setattr(load_nspl, '_write_checkpoint', _spy)
        loader_env['run'](_FakeDdb())

        assert len(observed) >= 5, 'fixture too small to exercise checkpointing'
        for row, written_then in observed:
            due = {k for idx, k in enumerate(keys) if k is not None and idx <= row}
            assert not (due - written_then), (
                f'checkpoint at row {row} ran ahead of the flush: '
                f'{len(due - written_then)} item(s) recorded as done but never written'
            )

    def test_a_run_of_skipped_rows_still_advances_the_checkpoint(self, loader_env, monkeypatch):
        # audit S3. The checkpoint used to sit below `if item is None: skipped
        # += 1; continue`, so a run of skipped rows wrote no checkpoint at all
        # — the DEFRA loader's remaining bug. Every row in this fixture is
        # skipped except a small live head, so a checkpoint can only appear if
        # the decision is reached on the skip path too.
        rows = _synthetic_rows(20)
        rows += [dict(r, gridind='9', lad25cd='', lat='99.999999') for r in _synthetic_rows(300)]
        _write_csv(loader_env['csv'], rows)

        observed = []
        real_write = load_nspl._write_checkpoint
        monkeypatch.setattr(
            load_nspl, '_write_checkpoint',
            lambda state: (observed.append(state['row']), real_write(state))[1],
        )
        loader_env['run'](_FakeDdb())

        assert observed, 'no checkpoint was written at all'
        # The checkpoint must reach deep into the skip block, not stall at the
        # last live row (row 19).
        assert max(observed) > 250

    @pytest.mark.parametrize("kill_after", [7, 19, 34, 61, 88, 137, 206])
    def test_interrupt_and_resume_loses_zero_rows(self, loader_env, kill_after):
        rows = _synthetic_rows(400)
        _write_csv(loader_env['csv'], rows)
        keys = _expected_key_by_row(rows)
        expected = {k for k in keys if k is not None}

        # One shared table, exactly as a killed run and its resume share one
        # real DynamoDB table.
        table = {}
        with pytest.raises(KeyboardInterrupt):
            loader_env['run'](_FakeDdb(table, kill_after=kill_after))

        if loader_env['checkpoint'].exists():
            state = json.loads(loader_env['checkpoint'].read_text(encoding='utf-8'))
            # The invariant that makes the resume safe, read straight off disk:
            # nothing at or before the recorded row is missing from the table.
            due = {k for idx, k in enumerate(keys) if k is not None and idx <= state['row']}
            assert not (due - set(table)), (
                f'checkpoint row {state["row"]} is ahead of the table by '
                f'{len(due - set(table))} item(s)'
            )
        else:
            # Killed before the first checkpoint could be written, so the
            # resume correctly restarts from row 0. Nothing is lost either
            # way. This fixture's first checkpoint lands on the 15th put.
            assert kill_after < 15

        loader_env['run'](_FakeDdb(table))

        missing = expected - {k for k in table if k != load_nspl.META_KEY}
        assert not missing, f'{len(missing)} row(s) lost across the interrupt: {sorted(missing)[:5]}'
        # A completed run clears its own resume state, both files.
        assert not loader_env['checkpoint'].exists()
        assert not (loader_env['checkpoint'].parent / '.nspl_load_checkpoint.tmp').exists()

    def test_resumed_run_records_whole_load_counts_in_meta(self, loader_env):
        # audit S2. __META__ used to be built from process-local counters
        # initialised to 0, so a resumed run recorded only its final segment
        # and overwrote the previous good record with it. The counters now
        # ride along in the checkpoint and are seeded on resume.
        rows = _synthetic_rows(400)
        _write_csv(loader_env['csv'], rows)
        keys = _expected_key_by_row(rows)

        table = {}
        with pytest.raises(KeyboardInterrupt):
            loader_env['run'](_FakeDdb(table, kill_after=34))
        loader_env['run'](_FakeDdb(table))

        meta = table[load_nspl.META_KEY]
        assert int(meta['rowsWritten']['N']) == sum(1 for k in keys if k is not None)
        assert int(meta['rowsSkipped']['N']) == sum(1 for k in keys if k is None)
        assert meta['vintage']['S'] == load_nspl.NSPL_VINTAGE

    def test_legacy_bare_integer_checkpoint_is_not_honoured(self, loader_env):
        # The old on-disk format was a bare row index, written without regard
        # to the buffer. Resuming from one is how holes appeared, so it must
        # restart from row 0 rather than be trusted.
        rows = _synthetic_rows(120)
        _write_csv(loader_env['csv'], rows)
        loader_env['checkpoint'].write_text('90', encoding='utf-8')

        table = {}
        loader_env['run'](_FakeDdb(table))
        expected = {k for k in _expected_key_by_row(rows) if k is not None}
        assert expected - {load_nspl.META_KEY} <= set(table)

    def test_checkpoint_from_another_vintage_is_not_honoured(self, loader_env):
        # A row index only means anything against the CSV it was counted from.
        rows = _synthetic_rows(120)
        _write_csv(loader_env['csv'], rows)
        loader_env['checkpoint'].write_text(
            json.dumps({'row': 90, 'written': 90, 'skipped': 0, 'terminated': 0,
                        'london': 0, 'mismatches': 0, 'countsComplete': True,
                        'vintage': '1999-01'}),
            encoding='utf-8',
        )

        table = {}
        loader_env['run'](_FakeDdb(table))
        expected = {k for k in _expected_key_by_row(rows) if k is not None}
        assert expected <= set(table)


class TestBatchWritePath:
    """2026-07-27. The write path moved from per-item PutItem to BatchWriteItem
    (~25x fewer signed round trips) to make the quarterly vintage roll a
    ~15-minute job instead of the measured 5.80 hours.

    Every test here guards a way the swap can lose rows while still reporting
    success, which is the only interesting risk: the loader's `written` counter
    credits a whole batch once _flush_batch returns without raising.
    """

    @pytest.fixture
    def _no_sleep(self, monkeypatch):
        """Collapse the retry backoff. Real delays double from 50ms and the
        retry tests would otherwise spend seconds asleep."""
        monkeypatch.setattr(load_nspl.time, 'sleep', lambda _: None)

    def test_uses_batch_write_item_by_default(self, loader_env):
        rows = _synthetic_rows(40)
        _write_csv(loader_env['csv'], rows)
        ddb = _FakeDdb()
        loader_env['run'](ddb)

        assert ddb.batch_calls > 0, 'still on the per-item path'
        expected = {k for k in _expected_key_by_row(rows) if k is not None}
        assert ddb.postcodes == expected

    def test_unprocessed_items_are_retried_not_dropped(self, loader_env, _no_sleep):
        """The one that matters. UnprocessedItems arrives on an HTTP 200, so
        nothing raises and boto3's adaptive retry never sees it — only the
        loader's own loop can recover those rows. Dropping them would leave a
        short table that every counter and the __META__ record call complete.
        """
        rows = _synthetic_rows(40)
        _write_csv(loader_env['csv'], rows)
        ddb = _FakeDdb(unprocessed_rounds=3)
        loader_env['run'](ddb)

        expected = {k for k in _expected_key_by_row(rows) if k is not None}
        assert ddb.postcodes == expected, 'rows held back in UnprocessedItems were lost'

    def test_persistent_unprocessed_items_raise_rather_than_undercount(self, _no_sleep):
        """Exhausting the retries must be fatal. Returning quietly would let
        run_load add the batch to `written` and checkpoint past rows that never
        landed — unrecoverable, because a resume starts after them."""
        ddb = _FakeDdb(unprocessed_rounds=load_nspl.BWI_MAX_ATTEMPTS + 5)
        items = [load_nspl._row_to_item(row) for row in _synthetic_rows(10)]

        with pytest.raises(RuntimeError, match='still unprocessed'):
            load_nspl._flush_batch(ddb, [i for i in items if i is not None], workers=1)

    def test_access_denied_falls_back_to_put_item_and_latches(self, loader_env):
        """The grant may not have landed yet. The loader must still complete on
        the old path, and must stop re-probing after the first refusal."""
        rows = _synthetic_rows(40)
        _write_csv(loader_env['csv'], rows)
        ddb = _FakeDdb(deny=True)
        loader_env['run'](ddb)

        expected = {k for k in _expected_key_by_row(rows) if k is not None}
        assert ddb.postcodes == expected, 'fallback did not complete the load'
        assert ddb.batch_calls == 1, (
            f'probed BatchWriteItem {ddb.batch_calls} times; the latch should '
            f'have stopped it after the first AccessDenied'
        )
        assert load_nspl._BATCH_WRITE_DENIED is True

    def test_validation_error_falls_back_without_latching(self, loader_env):
        """A duplicate key inside one 25-item window fails the WHOLE request,
        where PutItem would simply overwrite (last row wins — the semantics
        every earlier load had). That is per-chunk bad luck, not a missing
        permission, so it must not latch the whole run onto the slow path."""
        rows = _synthetic_rows(40)
        _write_csv(loader_env['csv'], rows)
        ddb = _FakeDdb(invalid=True)
        loader_env['run'](ddb)

        expected = {k for k in _expected_key_by_row(rows) if k is not None}
        assert ddb.postcodes == expected
        assert ddb.batch_calls > 1, 'a ValidationException should not latch'
        assert load_nspl._BATCH_WRITE_DENIED is False


class TestMetaGuards:
    """audit S2. `__META__` is provenance, and provenance is trusted — a wrong
    one is worse than none. _write_meta gained a `counts_complete` parameter,
    returns bool, and refuses in four cases rather than clobbering a good
    record with a degenerate one."""

    def test_clean_run_writes_the_record(self):
        ddb = _FakeDdb()
        assert load_nspl._write_meta(ddb, 2_699_393, 24_203, 0, True) is True
        assert ddb.table[load_nspl.META_KEY]['rowsWritten']['N'] == '2699393'

    def test_refuses_when_counters_are_unreconstructable(self, capsys):
        # Resumed from a checkpoint that carried a row index but no counters,
        # so the totals understate the load by an unknown amount.
        ddb = _FakeDdb({load_nspl.META_KEY: {
            'postcode': {'S': load_nspl.META_KEY}, 'rowsWritten': {'N': '2699393'},
        }})
        assert load_nspl._write_meta(ddb, 7_978, 22, 0, False) is False
        assert ddb.table[load_nspl.META_KEY]['rowsWritten']['N'] == '2699393'
        # The escape hatch: an operator who has checked the run should not have
        # to pay for another 35-minute reload to stamp the record.
        assert 'aws dynamodb put-item' in capsys.readouterr().out

    def test_refuses_zero_rows_written(self):
        # Schema drift. _row_to_item catches KeyError and returns None, so one
        # renamed column (lad25cd -> lad26cd) skips all 2.7M rows without
        # raising — and the table keeps its previous, still-correct contents.
        ddb = _FakeDdb({load_nspl.META_KEY: {
            'postcode': {'S': load_nspl.META_KEY}, 'rowsWritten': {'N': '2699393'},
        }})
        assert load_nspl._write_meta(ddb, 0, 2_723_596, 0, True) is False
        assert ddb.table[load_nspl.META_KEY]['rowsWritten']['N'] == '2699393'

    def test_refuses_a_materially_smaller_load(self):
        # A truncated download. NSPL has never shrunk between editions.
        ddb = _FakeDdb({load_nspl.META_KEY: {
            'postcode': {'S': load_nspl.META_KEY}, 'rowsWritten': {'N': '2699393'},
        }})
        assert load_nspl._write_meta(ddb, 1_000_000, 500, 0, True) is False

    def test_accepts_a_slightly_smaller_load(self):
        # The threshold is a judgement call, so pin which side of it a normal
        # quarterly edition falls on: 0.9 * previous is still acceptable.
        previous = 2_699_393
        ddb = _FakeDdb({load_nspl.META_KEY: {
            'postcode': {'S': load_nspl.META_KEY}, 'rowsWritten': {'N': str(previous)},
        }})
        assert load_nspl._write_meta(ddb, int(previous * 0.95), 500, 0, True) is True

    def test_refuses_when_the_incumbent_cannot_be_read(self):
        from botocore.exceptions import ClientError

        class _BlindDdb(_FakeDdb):
            def get_item(self, TableName, Key):  # noqa: N803
                raise ClientError(
                    {'Error': {'Code': 'ProvisionedThroughputExceededException', 'Message': 'x'}},
                    'GetItem',
                )

        ddb = _BlindDdb()
        assert load_nspl._write_meta(ddb, 2_699_393, 24_203, 0, True) is False
        assert load_nspl.META_KEY not in ddb.table

    def test_mismatch_count_is_only_recorded_when_non_zero(self):
        # Its presence is itself the alarm that the spaced-form invariant has
        # broken, so a zero must not be written.
        clean = _FakeDdb()
        load_nspl._write_meta(clean, 100, 0, 0, True)
        assert 'pcdsMismatches' not in clean.table[load_nspl.META_KEY]

        dirty = _FakeDdb()
        load_nspl._write_meta(dirty, 100, 0, 3, True)
        assert dirty.table[load_nspl.META_KEY]['pcdsMismatches'] == {'N': '3'}
