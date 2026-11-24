#!/bin/sh
# Two CloudWatch alarms on the account's SES reputation (audit I-4, 2026-11-23): nothing watched bounces or complaints,
# so 200 made-up addresses a day (the sign-up's send ceiling) could push the bounce rate to SES's review level, and then
# to a pause of ALL sending, confirmations included, without anyone hearing of it. SES publishes both rates to
# CloudWatch by itself (AWS/SES Reputation.BounceRate and Reputation.ComplaintRate, account-wide, no dimensions).
#
# RUN BY BILL (OPERATIONS.md s5): Claude Code refuses PutMetricAlarm as "audit tampering".
#   sh scripts/create_ses_alarms.sh          create or update both alarms (safe to run again: put-metric-alarm replaces)
#   sh scripts/create_ses_alarms.sh --test   then force each to ALARM and back to OK: four emails, proving the path
#
# THRESHOLDS: SES reviews an account at a 5% bounce rate and a 0.1% complaint rate (and may pause it at 10% and 0.5%).
# The alarms fire AT those levels, not below: at our volume (5 emails in the first 23 days of November) one bounce in
# 20 sends is already 5%, so a lower bar would email about every mistyped address. A flood of made-up addresses passes
# 5% within the hour; any complaint at all passes 0.1%. Like the others: an email on ALARM and on OK, a quiet account
# (no data) is not breaching, and the london-flight-map- prefix the deploy user's alarm permissions are scoped to.
set -eu

PROFILE="${AWS_PROFILE:-flightmap}"
REGION=eu-west-2
ACCOUNT=$(aws sts get-caller-identity --profile "$PROFILE" --query Account --output text | tr -d '\r')
TOPIC="arn:aws:sns:${REGION}:${ACCOUNT}:sky-score-alerts"

alarm() { # name metric threshold description
  aws cloudwatch put-metric-alarm --profile "$PROFILE" --region "$REGION" \
    --alarm-name "$1" --alarm-description "$4" \
    --namespace AWS/SES --metric-name "$2" --statistic Maximum \
    --period 3600 --evaluation-periods 1 --threshold "$3" \
    --comparison-operator GreaterThanOrEqualToThreshold \
    --treat-missing-data notBreaching \
    --alarm-actions "$TOPIC" --ok-actions "$TOPIC"
  echo "set: $1 ($2 >= $3)"
}

alarm london-flight-map-ses-bounce-rate Reputation.BounceRate 0.05 \
  "SES bounce rate at 5%, SES's review level. Check the signup Lambda's logs for a burst of sign-ups (audit I-4; OPERATIONS.md s5)."
alarm london-flight-map-ses-complaint-rate Reputation.ComplaintRate 0.001 \
  "SES complaint rate at 0.1%, SES's review level: someone marked our email as spam (audit I-4; OPERATIONS.md s5)."

aws cloudwatch describe-alarms --profile "$PROFILE" --region "$REGION" \
  --alarm-names london-flight-map-ses-bounce-rate london-flight-map-ses-complaint-rate \
  --query 'MetricAlarms[].[AlarmName,StateValue,Threshold]' --output table

if [ "${1:-}" = "--test" ]; then
  for name in london-flight-map-ses-bounce-rate london-flight-map-ses-complaint-rate; do
    aws cloudwatch set-alarm-state --profile "$PROFILE" --region "$REGION" --alarm-name "$name" \
      --state-value ALARM --state-reason "Path test (scripts/create_ses_alarms.sh --test)"
    aws cloudwatch set-alarm-state --profile "$PROFILE" --region "$REGION" --alarm-name "$name" \
      --state-value OK --state-reason "Path test done"
    echo "tested: $name (expect two emails)"
  done
fi
