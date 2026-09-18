#!/bin/sh
# Rotate the EPC bearer token: deploy the value now in .env to the EPC Lambda
# and verify /epc from the origin. Written 2026-09-18, when the token had been
# "pending rotation" on ROADMAP's critical path since May and had been printed
# into a session transcript the day before. Run from the repo root in Git Bash:
#
#     sh scripts/rotate_epc_token.sh
#
# THE ORDER IS THE WHOLE POINT. Regenerating the token on the MHCLG dashboard
# (My account on get-energy-performance-data.communities.gov.uk) retires the old
# one, so between "regenerate" and "deploy" every /epc call answers
# `available: false`. Do the three steps back to back:
#
#     1. regenerate on the dashboard          (Bill, browser)
#     2. paste it into .env as EPC_BEARER_TOKEN=...   (never into chat)
#     3. sh scripts/rotate_epc_token.sh        (this file)
#
# WHY THE VERIFY READS THE BODY. A rejected token is NOT an error to a caller:
# backend/lambdas/epc/app.py answers 200 with `available: false` and a message,
# on purpose, so a dead token hides the EPC panel instead of breaking the
# property page. A status check therefore passes a dead token. The check below
# asserts `available: true` AND `count > 0` on a postcode that HAS certificates
# (N1 7SX returned 72 on the day the migration was verified). "Graceful failure
# hides broken" - memory/feedback-graceful-failure-hides-broken.md.
#
# WHY IT REFUSES AN UNCHANGED TOKEN. `sam deploy` writes the last parameter
# overrides into backend/samconfig.toml (gitignored, line 1 of .gitignore), so
# that file always holds the token the LIVE stack has. A .env that still equals
# it means step 2 was skipped, and a deploy would report success having rotated
# nothing.
#
# WHY IT REFUSES A DIRTY backend/. A SAM deploy ships the working tree, not
# HEAD. A rotation is a pure parameter change; anything else in backend/ going
# out under its name is an unreviewed deploy.
set -eu
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."

API="https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod"
PROBE="N1+7SX"

step() { printf '\n### %s\n' "$*"; }

# Prints "<available> <count>" for the probe postcode, or "error 0" if the
# endpoint did not answer JSON. Never prints the body: it is not the token,
# but the habit of printing nothing you do not need is the one that keeps
# secrets out of transcripts.
epc_state() {
  curl -s -m 30 "$API/epc?postcode=$PROBE" | python -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("error 0"); sys.exit(0)
print("true" if d.get("available") else "false", int(d.get("count") or 0))
' 2>/dev/null || echo "error 0"
}

step "0. preconditions"
[ -f .env ] || { echo "no .env at the repo root"; exit 1; }
set -a; . ./.env; set +a
[ -n "${EPC_BEARER_TOKEN:-}" ] || { echo "EPC_BEARER_TOKEN is empty in .env"; exit 1; }
[ "$EPC_BEARER_TOKEN" != "your_bearer_token_here" ] || { echo "EPC_BEARER_TOKEN is still the .env.example placeholder"; exit 1; }
if [ -f backend/samconfig.toml ]; then
  last=$(sed -n 's/^EpcBearerToken = "\(.*\)"$/\1/p' backend/samconfig.toml | tr -d '\r')
  if [ -n "$last" ] && [ "$last" = "$EPC_BEARER_TOKEN" ]; then
    echo "EPC_BEARER_TOKEN in .env is the SAME value the last deploy used (backend/samconfig.toml)."
    echo "Nothing has been rotated. Regenerate on the dashboard and update .env first."
    exit 1
  fi
fi
if git status --short -- backend/ | grep -q .; then
  echo "backend/ has uncommitted changes; a rotation must be a pure parameter deploy. Commit or stash them first:"
  git status --short -- backend/
  exit 1
fi
echo "token present, differs from the last deploy, backend/ clean"

step "1. baseline: /epc before the deploy"
before=$(epc_state)
echo "$PROBE now: available=${before% *} count=${before#* }"
echo "(available=false here means the old token is already retired at the dashboard - deploy anyway)"

step "2. backend (SAM) - the changeset should name EpcFunction and nothing else"
( cd backend && rm -rf .aws-sam \
  && AWS_PROFILE=flightmap sam build \
  && AWS_PROFILE=flightmap sam deploy --no-confirm-changeset --no-fail-on-empty-changeset \
       --parameter-overrides EpcBearerToken="$EPC_BEARER_TOKEN" )

step "3. verify FROM THE ORIGIN, never from the exit code above"
after=$(epc_state)
avail=${after% *}; count=${after#* }
if [ "$avail" = "true" ] && [ "$count" -gt 0 ]; then
  echo "PASS: /epc serves $count certificates for $PROBE on the new token"
else
  echo "FAIL: /epc answers available=$avail count=$count for $PROBE after the deploy."
  echo "      The new token is not accepted (or the probe postcode lost its certificates -"
  echo "      check CloudWatch for 'EPC bearer token rejected' on the EPC function first)."
  exit 1
fi

step "4. what to do with the old token"
echo "It is retired at the dashboard by the regeneration itself. Copies on THIS machine:"
echo "  backend/samconfig.toml  - now overwritten with the new value by sam deploy"
echo "  .env                    - you just edited it"
echo "Any transcript or scrollback that held the old value is now harmless."
