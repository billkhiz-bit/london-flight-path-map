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

# THE CONNECTION POOL MUST BE AT LEAST AS WIDE AS THE EXECUTOR (2026-09-10).
#
# Both DEFRA loaders write each batch of 25 through a ThreadPoolExecutor of 25,
# and their docstrings say that gives throughput "comparable to BatchWriteItem".
# It did the opposite. boto3's default pool is 10 connections, so 15 of the 25
# threads found the pool full on every batch, urllib3 discarded their
# connections and each call paid a fresh TLS handshake. Measured against the
# live table with this exact client, a batch of 25 GetItems:
#
#   sequential, one thread     17 ms each  ->  ~60/s
#   25 threads, pool of 10   1995 ms/batch ->   13/s     (the loaders, until now)
#   25 threads, pool of 25     37 ms/batch ->  675/s
#
# Fifty-fold from one field, and the executor was making things FIVE TIMES
# SLOWER than no executor at all. Every bulk load this repo has run paid it:
# the "~1 hour" road pass, the air-quality runs that died at 14 h and 18 h
# (they had to be running long enough to meet a laptop sleep), the 17-minute
# Nottingham road load that should have been under two. The docstring number
# was never measured - feedback-numbers-in-justifying-comments-expire, again.
#
# One holder for the width, so the executor and the pool cannot drift apart:
# a loader that raises its worker count without the pool following silently
# reinstates the churn. Both loaders import this rather than writing 25.
MAX_WORKERS = 25


def make_client(region):
    """A DynamoDB client configured to survive a multi-hour run.

    The pool is sized to MAX_WORKERS, and that is the load-bearing line - see
    the comment above it. Adaptive retry is the other half: it backs off on
    throttling rather than dying, which a bare client did twice.
    """
    import boto3
    from botocore.config import Config

    return boto3.client(
        'dynamodb',
        region_name=region,
        config=Config(retries=RETRY_CONFIG, max_pool_connections=MAX_WORKERS),
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
