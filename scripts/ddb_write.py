"""Shared DynamoDB write policy for the long-running bulk loaders.

WHY THIS FILE EXISTS. Three loaders here write millions of rows over many
hours: load_nspl.py, load_defra_raster.py and load_defra_air_quality.py. The
first has always survived; the other two kept dying mid-run, and on 2026-08-09
the reason turned out to be configuration rather than data. load_nspl.py builds
its client with adaptive retry. The two DEFRA loaders built a bare client, so a
dropped connection raised, and neither had a `try` anywhere in its write path.

The proximate trigger was a laptop sleeping. Windows entered sleep at 21:28:12
on 2026-08-08; the air-quality checkpoint last moved at 21:27. Sleep does not
kill the process - the system resumed six seconds later - it kills the in-flight
HTTPS connections, and an unguarded update_item turns that into a fatal.

The policy lives HERE rather than being pasted into each loader because the
interesting part is FATAL_CODES, and a list that drifts between two copies is
worse than no list: one loader would wait out an error the other raises on, and
the difference would only show up during a multi-hour run nobody is watching.
"""

import time

# Errors that cannot succeed on a retry: a missing grant, a malformed item, a
# table that is not there, a bad signature. Waiting on any of these is the
# failure mode load_nspl.py hit when BatchWriteItem was denied - it made no
# progress and said nothing, so a run taking six hours was the only signal
# anything was wrong. These raise immediately instead.
FATAL_CODES = frozenset({
    'AccessDeniedException',
    'UnrecognizedClientException',
    'InvalidSignatureException',
    'ValidationException',
    'ResourceNotFoundException',
})

# How long ONE item may stall before it is declared failed and the run moves on.
# Sized to outlast a laptop sleep and a router reboot, not a regional outage.
#
# It is bounded on purpose. Waiting is the right default once boto3's retries
# are spent, but an unbounded wait swaps this failure for a worse one - a run
# that never finishes and never explains why.
MAX_STALL_S = 1800

# Retry config matching load_nspl.py, the only loader here that has ever run to
# completion (5.8h, 2.7M rows). Adaptive mode also backs off on throttling,
# which per-item writes at 25 threads will meet on a PAY_PER_REQUEST table.
RETRY_CONFIG = {'max_attempts': 10, 'mode': 'adaptive'}


def make_client(region):
    """A DynamoDB client configured to survive a multi-hour run."""
    import boto3
    from botocore.config import Config

    return boto3.client(
        'dynamodb',
        region_name=region,
        config=Config(retries=RETRY_CONFIG),
    )


def guarded_put(write, item, max_stall_s=MAX_STALL_S, sleep=time.sleep):
    """Run `write(item)`, waiting out a transient fault, raising on a real one.

    Reached only once boto3's ten attempts are already spent, so anything
    arriving here is sustained rather than a blip. Both DEFRA loaders write with
    UpdateItem + SET, which is idempotent, so replaying an item is always safe.

    Returns True if the write landed, False if it stalled past `max_stall_s`.
    Raises immediately on a FATAL_CODES error rather than waiting, because those
    will still be true in thirty minutes.

    `sleep` is injectable so the backoff can be tested without spending the
    wall-clock time it describes.
    """
    from botocore.exceptions import BotoCoreError, ClientError

    delay = waited = 0
    while True:
        try:
            write(item)
            return True
        except ClientError as exc:
            if exc.response.get('Error', {}).get('Code') in FATAL_CODES:
                raise
        except BotoCoreError:
            pass  # connection reset, timeout, endpoint gone: all retryable
        if waited >= max_stall_s:
            return False
        delay = min(delay * 2, 300) if delay else 5
        sleep(delay)
        waited += delay


def record_failures(path, postcodes):
    """Append stalled postcodes BY NAME, not as a count.

    A stalled postcode is ABSENT from the table, and absent is the state this
    project keeps misreading as measured-and-fine. A tally would say how many
    rows to worry about but not which ones, so it could not be re-run.
    """
    if not postcodes:
        return
    with open(path, 'a', encoding='utf-8') as fh:
        fh.write('\n'.join(postcodes) + '\n')
