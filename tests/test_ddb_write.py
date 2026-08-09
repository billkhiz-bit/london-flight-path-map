"""Tests for scripts/ddb_write.py, the shared bulk-loader write policy.

This code only ever runs during multi-hour offline loads, which is exactly why
it needs tests: every one of its decisions is invisible until a run has already
been going for hours, and both DEFRA loaders died twice before anyone looked at
it. The 2026-08-08 death cost 18 hours and was diagnosed from Windows power
events because the process left no other trace.

The two properties worth proving are opposites, and getting either backwards
reintroduces a real outage:

  - a TRANSIENT fault must be waited out, or a dropped connection ends the run
  - a FATAL fault must raise, or an IAM denial spins silently forever, which is
    what load_nspl.py did when BatchWriteItem was refused

Offline only: no AWS, no network. `guarded_put` takes an injectable `sleep` so
the backoff can be asserted without spending the wall-clock time it describes.
"""

import importlib.util
import os
import sys

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), os.pardir))


def _load_script(alias, path):
    if alias in sys.modules:
        return sys.modules[alias]
    spec = importlib.util.spec_from_file_location(alias, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


ddb_write = _load_script(
    'ddb_write_under_test', os.path.join(REPO_ROOT, 'scripts', 'ddb_write.py')
)


def _client_error(code):
    return ClientError({'Error': {'Code': code, 'Message': 'test'}}, 'UpdateItem')


class _Recorder:
    """Stands in for time.sleep, recording what the backoff asked for."""

    def __init__(self):
        self.delays = []

    def __call__(self, seconds):
        self.delays.append(seconds)

    @property
    def total(self):
        return sum(self.delays)


def test_success_first_try_never_sleeps():
    slept = _Recorder()
    calls = []

    assert ddb_write.guarded_put(calls.append, 'A', sleep=slept) is True
    assert calls == ['A']
    assert slept.delays == []


def test_transient_fault_is_waited_out():
    """A dropped connection must NOT end the run - this is the whole fix."""
    slept = _Recorder()
    attempts = {'n': 0}

    def flaky(_item):
        attempts['n'] += 1
        if attempts['n'] < 3:
            raise EndpointConnectionError(endpoint_url='https://dynamodb.test')

    assert ddb_write.guarded_put(flaky, 'A', sleep=slept) is True
    assert attempts['n'] == 3
    assert slept.delays == [5, 10]


def test_throttling_is_transient_not_fatal():
    """Throttling is the expected steady-state at 25 concurrent writers."""
    slept = _Recorder()
    attempts = {'n': 0}

    def throttled(_item):
        attempts['n'] += 1
        if attempts['n'] < 2:
            raise _client_error('ProvisionedThroughputExceededException')

    assert ddb_write.guarded_put(throttled, 'A', sleep=slept) is True
    assert attempts['n'] == 2


# Written out HERE rather than read from ddb_write.FATAL_CODES, and that is
# load-bearing. Parametrising over the constant under test was the first
# version, and emptying that constant made pytest report "1 skipped" instead of
# a failure - the guard written to catch an empty fatal list was DELETED by an
# empty fatal list. An expectation has to be able to disagree with the code.
EXPECTED_FATAL = [
    'AccessDeniedException',
    'InvalidSignatureException',
    'ResourceNotFoundException',
    'UnrecognizedClientException',
    'ValidationException',
]


def test_fatal_list_still_holds_every_expected_code():
    """Goes red if a code is dropped, which the parametrised test cannot."""
    assert set(EXPECTED_FATAL) == set(ddb_write.FATAL_CODES)


@pytest.mark.parametrize('code', EXPECTED_FATAL)
def test_fatal_codes_raise_immediately(code):
    """Every fatal code must raise WITHOUT sleeping.

    A single wrong entry here turns a loud failure into a silent 30-minute
    stall per item, which at 25 workers is a run that appears to hang.
    """
    slept = _Recorder()

    def denied(_item):
        raise _client_error(code)

    with pytest.raises(ClientError):
        ddb_write.guarded_put(denied, 'A', sleep=slept)
    assert slept.delays == []


def test_persistent_transient_fault_gives_up_and_reports_false():
    slept = _Recorder()

    def always_down(_item):
        raise EndpointConnectionError(endpoint_url='https://dynamodb.test')

    assert ddb_write.guarded_put(always_down, 'A', sleep=slept) is False
    # Bounded: it stopped rather than waiting forever, and did not overshoot by
    # more than one final backoff step.
    assert slept.total >= ddb_write.MAX_STALL_S
    assert slept.total < ddb_write.MAX_STALL_S + 300


def test_backoff_is_exponential_and_capped():
    slept = _Recorder()

    def always_down(_item):
        raise EndpointConnectionError(endpoint_url='https://dynamodb.test')

    ddb_write.guarded_put(always_down, 'A', sleep=slept)
    assert slept.delays[:6] == [5, 10, 20, 40, 80, 160]
    assert max(slept.delays) == 300, 'cap keeps one item from stalling the pool'


def test_record_failures_writes_names_not_a_count(tmp_path):
    """A tally cannot be re-run; the point is knowing WHICH postcodes."""
    path = tmp_path / 'failures'
    ddb_write.record_failures(path, ['SW1A1AA', 'E82JG'])
    ddb_write.record_failures(path, ['W1D3QU'])

    assert path.read_text(encoding='utf-8').split() == [
        'SW1A1AA',
        'E82JG',
        'W1D3QU',
    ]


def test_record_failures_no_op_on_empty(tmp_path):
    path = tmp_path / 'failures'
    ddb_write.record_failures(path, [])
    assert not path.exists(), 'a clean run must not leave a failures file'
