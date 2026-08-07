#!/usr/bin/env sh
# Assert that CloudWatch log retention matches what privacy.html promises.
#
# WHY THIS EXISTS (2026-08-05). privacy.html §2d told visitors, in the notice
# that carries actual legal weight, that server logs were "retained for 7 days
# then automatically deleted". Every log group in the account was set to
# `retentionInDays: None` — never expire — and had been for the life of the
# project. The claim was not stale, it had never been true. Underneath it sat a
# Signup log group holding raw email addresses from 26 Jun to 23 Jul 2026.
#
# WHAT CHANGED (2026-08-06). The first version of this script hardcoded
# WANT_DAYS=30 and never opened privacy.html, despite being named
# "log retention == privacy.html". That meant it could only ever be satisfied
# one way: by the console work landing. Switching §2d to the honest interim
# wording — which makes the page TRUE — left the gate RED, so the only route to
# green was the route the CLI cannot take. DRAFT_security_retention_passage.md
# §2b flagged this as a known limitation and asked for exactly this fix.
#
# It now reads the claim out of privacy.html and asserts that AWS matches
# WHATEVER THE PAGE SAYS. That is strictly stronger than the old behaviour: it
# still goes red on "page promises 30, AWS says None", and it additionally goes
# red on "page promises indefinite, AWS says 30" — a direction the old script
# could not see at all. The invariant is agreement, not a particular number.
#
# WHAT CHANGED AGAIN (2026-08-07). The orphan list was hand-maintained, and it
# named `ChatFunction`. Restoring chat on 2026-08-06 made that entry false:
# there are now TWO chat log groups, the dead Bedrock one and the live
# retrieval-only one, and the fragment match classified BOTH as orphans. The
# live Lambda — the only one that receives free-text user input — was therefore
# downgraded to a WARN and never asserted against the page at all. Benign under
# the current "indefinite" claim, and a silent hole the moment Version A lands.
#
# The list is now DERIVED from backend/template.yaml, which is the thing that
# actually decides whether a function exists. A hand-copied list of a fact that
# lives somewhere else goes stale on the first change to the real source, and
# does so silently, because nothing fails when a list is merely out of date.
#
# `flightmap-dev` CAN call logs:DescribeLogGroups — that grant exists and is
# what makes this checkable without admin credentials. It CANNOT call
# logs:PutRetentionPolicy or logs:DeleteLogGroup, so changing the
# infrastructure is console work; see DRAFT_security_retention_passage.md §1.
#
#   sh scripts/check_log_retention.sh

set -u

REGION="eu-west-2"
PREFIX="/aws/lambda/london-flight-map"
PROFILE="${AWS_PROFILE_NAME:-flightmap}"
PRIVACY="$(dirname "$0")/../privacy.html"
TEMPLATE="$(dirname "$0")/../backend/template.yaml"

# Git Bash rewrites a leading-slash argument into a Windows path unless this is
# set, which turns the prefix into something that matches nothing and would make
# this check pass vacuously — the exact failure mode it exists to prevent.
export MSYS_NO_PATHCONV=1

# --- 1. Read the claim out of privacy.html -------------------------------
#
# The passage wraps across source lines, so flatten whitespace before matching.
# Without this the <strong> tag and the sentence around it sit on different
# lines and every pattern below misses, which would look like "unparseable"
# rather than "no claim".
if [ ! -r "$PRIVACY" ]; then
  echo "FAIL: cannot read $PRIVACY, so the claim is UNKNOWN." >&2
  echo "      An unreadable notice is not a passing one." >&2
  exit 1
fi

FLAT=$(tr '\n' ' ' < "$PRIVACY" | tr -s ' ')

if echo "$FLAT" | grep -q 'Execution logs are currently retained <strong>indefinitely</strong>'; then
  CLAIM="indefinite"
  CLAIM_TEXT="retained indefinitely"
  WANT="None"
else
  DAYS_CLAIM=$(echo "$FLAT" \
    | grep -oE 'Execution logs are retained for <strong>[0-9]+ days</strong>' \
    | grep -oE '[0-9]+' \
    | head -1)
  if [ -n "${DAYS_CLAIM:-}" ]; then
    CLAIM="days"
    CLAIM_TEXT="retained for ${DAYS_CLAIM} days"
    WANT="$DAYS_CLAIM"
  else
    echo "FAIL: could not find a retention claim in privacy.html §2d." >&2
    echo "      This check asserts that AWS matches the page. If the sentence" >&2
    echo "      has been reworded, update the patterns here in the same commit" >&2
    echo "      — a claim this script cannot read is a claim nothing verifies," >&2
    echo "      which is how the original false statement survived for months." >&2
    exit 1
  fi
fi

echo "privacy.html §2d claims: ${CLAIM_TEXT}"

# --- 1b. The page must not contradict itself ------------------------------
#
# Added 2026-08-07 after §2d was corrected to 30 days and a SECOND retention
# claim, in the sub-processor table at privacy.html:263, was left reading
# "currently retained indefinitely". The check passed: it parses §2d and nothing
# else, so a page that stated both 30 days and indefinitely in two places was
# green. A document can be internally inconsistent and still satisfy a check
# that only ever reads one sentence of it.
CONTRADICTION=0

if [ "$CLAIM" = "days" ]; then
  if echo "$FLAT" | grep -qi 'retained indefinitely\|retention[^.<]\{0,20\}indefinit'; then
    echo "FAIL: §2d says ${CLAIM_TEXT}, but privacy.html also says retention is indefinite somewhere." >&2
    CONTRADICTION=1
  fi
  # Every "N-day retention" elsewhere on the page must agree with §2d.
  for N in $(echo "$FLAT" | grep -oiE '[0-9]+[- ]day retention' | grep -oE '[0-9]+'); do
    if [ "$N" != "$WANT" ]; then
      echo "FAIL: §2d says $WANT days, but privacy.html also states a ${N}-day retention." >&2
      CONTRADICTION=1
    fi
  done
else
  if echo "$FLAT" | grep -qiE '[0-9]+[- ]day retention|retained for (<strong>)?[0-9]+ days'; then
    echo "FAIL: §2d says retention is indefinite, but privacy.html also states a specific period." >&2
    CONTRADICTION=1
  fi
fi

if [ "$CONTRADICTION" != "0" ]; then
  echo "      Fix every mention, not just §2d. The sub-processor table at" >&2
  echo "      privacy.html:263 is the one that was missed on 2026-08-07." >&2
  exit 1
fi

# --- 2. Derive which functions are supposed to exist ----------------------
#
# Logical IDs of every AWS::Serverless::Function in the SAM template. A log
# group is named /aws/lambda/<stack>-<LogicalId>-<random suffix>, so the logical
# ID is recoverable from the group name and is stable across redeploys, while
# the suffix is not.
#
# Matching only the FIRST `Type:` line after a logical ID is deliberate: a
# looser pattern would also match a `Type:` nested inside some other resource's
# properties and silently widen the active set.
if [ ! -r "$TEMPLATE" ]; then
  echo "FAIL: cannot read $TEMPLATE, so 'which functions are active' is UNKNOWN." >&2
  exit 1
fi

ACTIVE_IDS=$(awk '
  /^  [A-Za-z0-9]+:[[:space:]]*$/ { name = $1; sub(/:$/, "", name); next }
  /^    Type:[[:space:]]/ {
    if (name != "" && $2 == "AWS::Serverless::Function") print name
    name = ""
  }
' "$TEMPLATE")

# Collapse to a space-separated list for `case` membership tests.
ACTIVE_LIST=$(echo $ACTIVE_IDS)

if [ -z "$ACTIVE_LIST" ]; then
  echo "FAIL: parsed zero functions out of $TEMPLATE." >&2
  echo "      Every group would then look like an orphan and be waved through" >&2
  echo "      as a WARN, so this check would pass while asserting nothing." >&2
  echo "      If the template's indentation changed, fix the awk above." >&2
  exit 1
fi

echo "template.yaml declares: $(echo "$ACTIVE_IDS" | wc -l | tr -d ' ') functions"

# --- 3. Read what AWS actually does --------------------------------------

RAW=$(AWS_PROFILE="$PROFILE" aws logs describe-log-groups \
        --log-group-name-prefix "$PREFIX" \
        --region "$REGION" \
        --query 'logGroups[].[logGroupName,retentionInDays,creationTime,storedBytes]' \
        --output text 2>&1)
AWS_STATUS=$?

if [ $AWS_STATUS -ne 0 ]; then
  echo "FAIL: could not read log groups, so retention is UNVERIFIED." >&2
  echo "      This is a failure, not a skip. privacy.html makes a retention" >&2
  echo "      claim and an unverifiable claim is the thing this check exists" >&2
  echo "      to stop." >&2
  echo "      aws said: $RAW" >&2
  exit 1
fi

if [ -z "$RAW" ]; then
  echo "FAIL: zero log groups matched '$PREFIX'." >&2
  echo "      A prefix that matches nothing passes every per-group assertion" >&2
  echo "      below, so this is treated as a failure rather than a clean run." >&2
  exit 1
fi

# --- 4. Sort the groups into orphans and live generations -----------------
#
# `tr -d '\r'` is load-bearing on Windows. The AWS CLI here emits CRLF, so the
# retention field arrives as "None\r" and never string-equals "None" — every
# group compared unequal against a value it visibly matched. This one failed
# safe (a false RED), but the identical bug on the name-matching side would
# have silently skipped the orphan checks instead, which fails green.
#
# Both loops read from a redirect, NOT a pipe. A piped `while` runs in a
# subshell whose variable assignments are discarded, which an earlier version
# worked around by writing the verdict to a file inside the loop — a workaround
# that silently skipped its own write on any iteration that hit `continue`.
TMP="${TMPDIR:-/tmp}/.skyscore_retention_$$"
ROWS="${TMPDIR:-/tmp}/.skyscore_retention_rows_$$"
printf '%s\n' "$RAW" | tr -d '\r' > "$TMP"
: > "$ROWS"

FAILED=0
ORPHANS_FOUND=0
STALE_FOUND=0
SIGNUP_BYTES=""

while IFS="$(printf '\t')" read -r NAME DAYS CREATED BYTES; do
  [ -z "$NAME" ] && continue

  # /aws/lambda/london-flight-map-ScoreFunction-AQH1Sxwg3LaF -> ScoreFunction
  LOGICAL=$(printf '%s' "$NAME" | sed "s|^${PREFIX}-||" | cut -d'-' -f1)

  case " $ACTIVE_LIST " in
    *" $LOGICAL "*)
      # creationTime is epoch millis; kept so the current generation of a
      # redeployed function can be told from its predecessors.
      printf '%s %s %s %s\n' "$LOGICAL" "$CREATED" "$NAME" "$DAYS" >> "$ROWS"
      [ "$LOGICAL" = "SignupFunction" ] && SIGNUP_BYTES="$BYTES"
      ;;
    *)
      # WARN, not FAIL. Under an "indefinite" claim these groups do not
      # contradict the page — they are retained indefinitely, exactly as stated.
      # They are still wrong to exist, but deleting them needs logs:DeleteLogGroup
      # which flightmap-dev does not have, so blocking here would gate every
      # commit in the repo on a console action. Tracked in
      # DRAFT_security_retention_passage.md §1 instead.
      echo "WARN orphan: $NAME (retention=$DAYS) — no $LOGICAL in template.yaml"
      ORPHANS_FOUND=$((ORPHANS_FOUND + 1))
      ;;
  esac
done < "$TMP"

# --- 5. Compare each live function against the page -----------------------
#
# POLICY DECISION, currently a no-op — see the note in the commit that added it.
#
# A function declared in template.yaml with NO log group at all has never been
# invoked in this account. That is either completely fine (it was deployed
# minutes ago and nothing has called it yet) or a real finding (an endpoint
# nobody has ever reached, which is how /sold-prices stayed broken for its
# entire existence while returning HTTP 200).
#
# Today this ignores the case, which is what the previous version did by
# accident rather than by choice. The alternatives are to WARN — surfaces the
# dead endpoint, stays green on a fresh deploy — or to FAIL, which is honest
# about an unverifiable claim but reds the gate on every new function until
# something calls it.
check_missing_group() {
  : "${1:?logical id}"
}

ACTIVE=0

for ID in $ACTIVE_LIST; do
  MATCHES=$(awk -v id="$ID" '$1 == id' "$ROWS" | sort -k2 -nr)

  if [ -z "$MATCHES" ]; then
    # A declared function with no log group at all. See the policy note below.
    check_missing_group "$ID"
    continue
  fi

  # Newest creationTime is the current generation. A redeployed function gets a
  # fresh group; an older group for the same logical ID can only be a previous
  # generation, so this ordering does not depend on how much traffic either saw.
  CURRENT=$(printf '%s\n' "$MATCHES" | head -1)
  CUR_NAME=$(printf '%s' "$CURRENT" | cut -d' ' -f3)
  CUR_DAYS=$(printf '%s' "$CURRENT" | cut -d' ' -f4)

  ACTIVE=$((ACTIVE + 1))
  if [ "$CUR_DAYS" != "$WANT" ]; then
    echo "FAIL $CUR_NAME retention=$CUR_DAYS, but privacy.html says $CLAIM_TEXT (expected $WANT)"
    FAILED=1
  fi

  # Older generations of a live function: same console fix as an orphan, same
  # reason for warning rather than failing.
  printf '%s\n' "$MATCHES" | tail -n +2 | while read -r LINE; do
    [ -z "$LINE" ] && continue
    echo "WARN stale generation of $ID: $(printf '%s' "$LINE" | cut -d' ' -f3)"
  done
  STALE_HERE=$(printf '%s\n' "$MATCHES" | tail -n +2 | grep -c . || true)
  STALE_FOUND=$((STALE_FOUND + STALE_HERE))
done

rm -f "$TMP" "$ROWS"

if [ "$ACTIVE" -eq 0 ]; then
  echo "FAIL: no live log groups matched any function in template.yaml." >&2
  echo "      Every assertion above was vacuous, so this is a failure." >&2
  exit 1
fi

if [ "$FAILED" != "0" ]; then
  echo ""
  echo "privacy.html §2d and the AWS account disagree. Either apply the"
  echo "retention policy (console: DRAFT_security_retention_passage.md §1) or"
  echo "correct §2d so the page describes what is actually configured."
  exit 1
fi

echo "$ACTIVE live log groups match privacy.html (${CLAIM_TEXT})."

if [ "$STALE_FOUND" -gt 0 ]; then
  echo ""
  echo "WARNING: $STALE_FOUND stale generation(s) of a live function remain."
  echo "  These belong to a previous deployment of a function that still"
  echo "  exists, so they are invisible to any check keyed on function names."
fi

if [ "$ORPHANS_FOUND" -gt 0 ]; then
  echo ""
  echo "WARNING: $ORPHANS_FOUND orphaned log group(s) from removed Lambdas remain."
  echo "  Console steps: DRAFT_security_retention_passage.md section 1."
fi

# The signup group is NOT an orphan — signup is a live function — so this
# warning is emitted on its own terms rather than folded into the count above,
# which is where the previous version misfiled it. The byte figure is read from
# AWS rather than quoted from a document, so it cannot drift.
if [ -n "$SIGNUP_BYTES" ] && [ "$SIGNUP_BYTES" != "0" ] && [ "$SIGNUP_BYTES" != "None" ]; then
  echo ""
  echo "WARNING: the Signup log group holds $SIGNUP_BYTES bytes."
  echo "  It contains raw email addresses from 26 Jun - 23 Jul 2026, in a"
  echo "  location privacy.html does not disclose (2b names DynamoDB and API"
  echo "  key metadata, not CloudWatch). Setting retention on it PRESERVES"
  echo "  those entries for the window rather than removing them; deleting the"
  echo "  group is what clears them. It is recreated empty on next invocation."
fi

exit 0
