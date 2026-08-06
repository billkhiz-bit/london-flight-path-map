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

# Git Bash rewrites a leading-slash argument into a Windows path unless this is
# set, which turns the prefix into something that matches nothing and would make
# this check pass vacuously — the exact failure mode it exists to prevent.
export MSYS_NO_PATHCONV=1

# Lambdas removed from template.yaml. Deleting a function does NOT delete its log
# group, so these linger with whatever they last held. Listed by function-name
# fragment rather than full ARN because CloudFormation assigns a fresh random
# suffix on every create.
ORPHANS="AnalyzeDocumentFunction AnalyzeImageFunction ChatFunction LiveFlightsFunction MultiAgentFunction ReportFunction"

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

# --- 2. Read what AWS actually does --------------------------------------

RAW=$(AWS_PROFILE="$PROFILE" aws logs describe-log-groups \
        --log-group-name-prefix "$PREFIX" \
        --region "$REGION" \
        --query 'logGroups[].[logGroupName,retentionInDays]' \
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

# --- 3. Compare -----------------------------------------------------------
#
# The loop reads from a redirect, NOT a pipe. A piped `while` runs in a subshell
# whose variable assignments are discarded, which the previous version worked
# around by writing the verdict to a file inside the loop — a workaround that
# silently skipped its own write on any iteration that hit `continue`. Reading
# from a file keeps the loop in this shell and lets FAILED just be a variable.
#
# `tr -d '\r'` is load-bearing on Windows. The AWS CLI here emits CRLF, so the
# retention field arrives as "None\r" and never string-equals "None" — every
# group compared unequal against a value it visibly matched. This one failed
# safe (a false RED), but the identical bug on the name-matching side would
# have silently skipped the orphan checks instead, which fails green.
TMP="${TMPDIR:-/tmp}/.skyscore_retention_$$"
printf '%s\n' "$RAW" | tr -d '\r' > "$TMP"

FAILED=0
ORPHANS_FOUND=0
ACTIVE=0

while IFS="$(printf '\t')" read -r NAME DAYS; do
  [ -z "$NAME" ] && continue

  IS_ORPHAN=0
  for ORPHAN in $ORPHANS; do
    case "$NAME" in
      *"$ORPHAN"*) IS_ORPHAN=1 ;;
    esac
  done

  if [ "$IS_ORPHAN" -eq 1 ]; then
    # WARN, not FAIL. Under an "indefinite" claim these groups do not
    # contradict the page — they are retained indefinitely, exactly as stated.
    # They are still wrong to exist, but deleting them needs logs:DeleteLogGroup
    # which flightmap-dev does not have, so blocking here would gate every
    # commit in the repo on a console action. Tracked in
    # DRAFT_security_retention_passage.md §1 instead.
    echo "WARN orphan group still present: $NAME (retention=$DAYS)"
    ORPHANS_FOUND=$((ORPHANS_FOUND + 1))
    continue
  fi

  ACTIVE=$((ACTIVE + 1))
  if [ "$DAYS" != "$WANT" ]; then
    echo "FAIL $NAME retention=$DAYS, but privacy.html says $CLAIM_TEXT (expected $WANT)"
    FAILED=1
  fi
done < "$TMP"

rm -f "$TMP"

if [ "$ACTIVE" -eq 0 ]; then
  echo "FAIL: no active (non-orphan) log groups found." >&2
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

echo "$ACTIVE active log groups match privacy.html (${CLAIM_TEXT})."

if [ "$ORPHANS_FOUND" -gt 0 ]; then
  echo ""
  echo "WARNING: $ORPHANS_FOUND orphaned log group(s) from removed Lambdas remain."
  echo "  The Signup group among them holds raw email addresses from"
  echo "  26 Jun - 23 Jul 2026, in a location privacy.html does not disclose"
  echo "  (2b names DynamoDB and API key metadata, not CloudWatch)."
  echo "  Setting retention on it would PRESERVE those entries for the window"
  echo "  rather than remove them; deleting the group is what clears them."
  echo "  Console steps: DRAFT_security_retention_passage.md section 1."
fi

exit 0
