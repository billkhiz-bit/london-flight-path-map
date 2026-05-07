# AWS billing alarm — one-time setup

The Sky Score AWS account should have a billing alarm so any future cost-abuse defect (the kind we caught today via smoke test, but at a future moment when smoke testing didn't catch it) surfaces within hours instead of at month-end.

The runtime IAM user (`flightmap-dev`) deliberately doesn't have CloudWatch alarm permissions — least-privilege. So this is a one-time admin-credential task.

## Prerequisite

Enable billing alerts in the AWS account (one-time, account-wide):

1. Sign in to AWS Console as the account root or an admin user.
2. Top-right username → **Billing and Cost Management**.
3. Left sidebar → **Billing preferences**.
4. Tick **Receive Billing Alerts**. Save.

(Alarms can't be created on `EstimatedCharges` until this is on. Free.)

## Create the alarm

Run with admin credentials (NOT `flightmap-dev`). Billing data only exists in `us-east-1` so the alarm must live there.

```bash
# Replace the SNS topic ARN with one you control, OR omit --alarm-actions
# entirely to create an alarm with no notification (only useful if you
# also set up a daily check elsewhere).

aws cloudwatch put-metric-alarm \
  --region us-east-1 \
  --alarm-name 'sky-score-billing-over-20-usd' \
  --alarm-description 'Estimated AWS charges over $20. Investigate Bedrock / API Gateway abuse before month-end.' \
  --metric-name EstimatedCharges \
  --namespace AWS/Billing \
  --statistic Maximum \
  --period 21600 \
  --threshold 20 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --dimensions Name=Currency,Value=USD \
  --treat-missing-data notBreaching \
  --alarm-actions 'arn:aws:sns:us-east-1:072674217857:billing-alerts'
```

Threshold rationale: at idle, Sky Score's monthly cost is ~$1-5 (mostly DynamoDB on-demand + a small CloudWatch Logs bill). A $20 threshold gives ~4× headroom for normal traffic growth without false positives, and would have fired within hours of today's "AI Lambda routes left open" defect (where 10 RPS on `/multi-agent` could have burned $2,500/day in Nova Pro).

## Setting up the SNS topic (optional but recommended)

```bash
# 1. Create topic
aws sns create-topic --region us-east-1 --name billing-alerts

# 2. Subscribe your email
aws sns subscribe --region us-east-1 \
  --topic-arn arn:aws:sns:us-east-1:072674217857:billing-alerts \
  --protocol email \
  --notification-endpoint billkhiz@gmail.com

# 3. Confirm via the email AWS sends
```

## Verify the alarm was created

```bash
aws cloudwatch describe-alarms --region us-east-1 \
  --alarm-names sky-score-billing-over-20-usd \
  --query 'MetricAlarms[0].{Name:AlarmName,State:StateValue,Threshold:Threshold}' \
  --output table
```

`State: OK` means the alarm is armed and below threshold.

## Why this isn't in `template.yaml`

Billing alarms must live in `us-east-1` (AWS hardcoding, not our choice). The Sky Score SAM stack is in `eu-west-2`. Cross-region resources from a single stack require StackSets or custom resources — overkill for one alarm. Manual one-time setup is cheaper than the indirection.

## Threshold tuning

If $20 is too sensitive (alarm fires on legitimate growth), bump the threshold or add more granular alarms by service:

```bash
# Bedrock-specific (catches the Lambda exposure pattern)
aws cloudwatch put-metric-alarm --region us-east-1 \
  --alarm-name 'sky-score-bedrock-spend-over-5-usd' \
  --metric-name EstimatedCharges --namespace AWS/Billing \
  --dimensions Name=ServiceName,Value=AmazonBedrock Name=Currency,Value=USD \
  --statistic Maximum --period 21600 --threshold 5 \
  --comparison-operator GreaterThanThreshold --evaluation-periods 1 \
  --treat-missing-data notBreaching
```
