# DRAFT — console runbook. §3 is DONE; §1 then §2 are still pending, in that order.

**Status: updated 2026-07-29. Untracked scratch file. Delete it once §1 and §2 are done.**

**What changed on 2026-07-29:** the push is no longer being held. It was held on the principle
that the repo is public and the document must not describe a gap as closed while it is open —
but the text sitting on `origin/master` was the *false* "default 90-day retention" claim, and
the honest correction was the thing being withheld. Holding the push was preserving the false
statement, so the principle inverted and the 24 commits went out with the gap described as
**open, dated, and blocked**. `SECURITY.md` will need one more edit once §1 is actually done.

**§3 was already applied** — `SECURITY.md` line ~72 has said "270 tests" since the 26 Jul
doc-correction pass. Do not re-apply it. (This is the second time this file has been stale
against the tree; verify each section against `SECURITY.md` before acting on it.)

**§1 below is still the live runbook** and is unchanged: the 13 log groups were re-verified as
`retentionInDays: None` on 2026-07-29, so none of the console work has happened yet.

---

## 1. Do the console work first

Region **eu-west-2**, account **072674217857**, signed in as root/admin. `flightmap-dev` cannot
do any of this — it lacks `logs:PutRetentionPolicy` and `logs:DeleteLogGroup`.

### Delete these 7 log groups

**Read the suffixes, not the function names.** As of 2026-08-06 there are two `ChatFunction`
groups and only one of them is dead — `chat` was restored that evening as a retrieval-only
function, so `ChatFunction-LuxoNSLxJMva` is **live and must be kept**. Deleting by eye, on the
name `ChatFunction`, takes out the wrong one.

Five below belong to Lambdas that no longer exist. `ChatFunction-wzeXuMdafiCz` is a stale
generation of a function that does still exist. The seventh, Signup, is the GDPR fix: applying
30-day retention to it would *preserve* the raw-email entries from 26 Jun – 23 Jul rather than
remove them, so deleting the group is what actually clears them.

```
/aws/lambda/london-flight-map-AnalyzeDocumentFunction-WGYkSBln0Rii
/aws/lambda/london-flight-map-AnalyzeImageFunction-BYNUmNi4Lxbq
/aws/lambda/london-flight-map-ChatFunction-wzeXuMdafiCz     <- DEAD, delete
/aws/lambda/london-flight-map-LiveFlightsFunction-inXEwZXJB5hG
/aws/lambda/london-flight-map-MultiAgentFunction-0BaKRcMkZzE6
/aws/lambda/london-flight-map-ReportFunction-bnFAI9UXiDBI
/aws/lambda/london-flight-map-SignupFunction-vLApmPCZyQTD
```

Do **not** delete `/aws/lambda/london-flight-map-ChatFunction-LuxoNSLxJMva`. It is the live one.

The signup group will be recreated automatically, empty, on the next invocation. That is
expected and is the point — set its retention afterwards.

### Set 30-day retention on these 7

Score, Favourites, Transport, Epc, SoldPrices, Nhs and **Chat** (`ChatFunction-LuxoNSLxJMva`,
new to this list on 2026-08-07) — plus the freshly recreated Signup group, making 8.

**The known silent failure:** *Actions → Edit retention setting* opens a modal whose dropdown
appears to take effect immediately. It does not. Closing the modal without pressing **Save**
discards the change with no warning and the list still shows *Never Expire*. Re-read the
retention column after saving each one.

### Verify before editing the doc

`flightmap-dev` *can* call `logs:DescribeLogGroups`, so verification does not need admin:

```bash
AWS_PROFILE=flightmap aws logs describe-log-groups \
  --log-group-name-prefix /aws/lambda/london-flight-map \
  --region eu-west-2 \
  --query 'logGroups[].[logGroupName,retentionInDays]' --output table
```

Expected after the work: **8 rows, every one showing 30** (7 functions plus the recreated
Signup group). Anything reading `None`, or any of the 6 deleted groups still listed, means it
did not take.

Better than reading the table by eye, `sh scripts/preflight.sh` runs
`scripts/check_log_retention.sh`, which derives the expected set from `backend/template.yaml`
and names anything that does not belong. It reports the stale generations and orphans as
warnings today; once §2d carries Version A it asserts the 30 and fails on any group that
missed it.

Do not trust a dashboard glance for this. On 26 Jul the work was reported done and was verified
unchanged — the tell was the signup group's `creationTime` still reading 2026-05-06 13:23, which
settles it independently of any console caching question.

### While you are in there: apply the pending IAM grants

**IAM → Policies → `FlightMapDeployPolicy` → Edit → JSON.** All of these are already written into
`backend/iam-policy.json`, but **that file is not the live policy** — it has to be pasted in. Doing
it in the same session saves a second recovery-and-sign-in cycle.

> **Do NOT paste `backend/iam-policy.json` verbatim (learned the hard way 2026-08-07).** It is
> sanitised for the public repo: **8 ARNs carry the literal string
> `REPLACE_WITH_YOUR_AWS_ACCOUNT_ID`**. An ARN's account field must be 12 digits or empty, so the
> console rejects the whole document with **"The policy failed legacy parsing"** — an error
> message that says nothing about account IDs and sends you looking for a JSON syntax error.
>
> Substitute the real account ID first, and write the result **outside the repo** so it is never
> committed:
>
> ```bash
> python -c "import pathlib; p=pathlib.Path('backend/iam-policy.json'); \
>   open('/tmp/policy.json','w',newline='').write(p.read_text().replace('REPLACE_WITH_YOUR_AWS_ACCOUNT_ID','072674217857'))"
> ```
>
> The failed save is harmless — AWS validates before storing, so the live policy is untouched and
> deploys keep working. Verify afterwards by probing rather than by reading the console: a
> `delete-log-group` against a **non-existent** group name returns `AccessDenied` while the grant
> is missing and `ResourceNotFoundException` once it lands, and it cannot delete anything either way.
>
> Note the sanitising is inconsistent: the same account ID appears in cleartext in six other
> committed files, so the placeholder buys nothing and costs a failed save each time.

**1. Add two actions to the `DynamoDB` statement** (`dynamodb:BatchWriteItem` is the ~25× NSPL
loader speedup; a vintage roll that still takes ~6 hours is the signal this never landed):

```json
"dynamodb:BatchWriteItem",
```

**2. Add two actions to the `CloudFrontHosting` statement.** Found 2026-07-27 during the
score-demo deploy: `flightmap-dev` can *create* an invalidation but not read its status, so
`aws cloudfront wait invalidation-completed` fails with AccessDenied and a deploy cannot
self-verify. Both are read-only:

```json
"cloudfront:GetInvalidation",
"cloudfront:ListInvalidations"
```

**3. Add this whole statement** (makes `/aws-debug` work and retires this console trip permanently
— with `PutRetentionPolicy` and `DeleteLogGroup` granted, the retention work above becomes two CLI
commands next time):

```json
{
    "Sid": "CloudWatchLogsOperateOwnGroups",
    "Effect": "Allow",
    "Action": [
        "logs:DescribeLogStreams",
        "logs:FilterLogEvents",
        "logs:GetLogEvents",
        "logs:PutRetentionPolicy",
        "logs:DeleteLogGroup"
    ],
    "Resource": "arn:aws:logs:eu-west-2:072674217857:log-group:/aws/lambda/london-flight-map-*"
}
```

**The trailing wildcard on that Resource is load-bearing.** IAM evaluates `PutRetentionPolicy`
against an ARN ending `:log-stream:` even though the action operates on the group — confirmed from
the denial message on 2026-07-27. An exactly-scoped group ARN would be **silently insufficient**,
which is the same failure shape as the signup outage: a permission that looks complete and is not.

---

## 2. Then replace the passage

In `SECURITY.md`, under **Operational visibility**, replace the bullet beginning
`- **Log retention is currently unlimited — corrected 2026-07-26.**` with:

```markdown
- **Log retention: 30 days on every active Lambda log group** (set 2026-07-DD). Log groups created
  implicitly by Lambda carry *no* retention policy by default — they never expire — and this section
  wrongly described that default as "90-day" until 2026-07-26. All 13 groups in the account were
  audited: the 6 orphaned by removed functions (the five Bedrock Lambdas and `live_flights`) were
  deleted outright, and the 7 active groups now carry a 30-day policy. The signup Lambda logged raw
  email addresses between 2026-06-26 and 2026-07-23; the log group holding those entries was deleted
  rather than aged out, so they are gone rather than merely expiring. Retention is applied in the
  console because the deploy user is intentionally not granted `logs:PutRetentionPolicy`.
```

Set `2026-07-DD` to the actual date you do it.

### Why it is worded that way

- It states the **previous claim was wrong**, not merely stale. That distinction is the whole point
  of the 26 Jul doc-correction pass, and quietly dropping it would be the same class of error again.
- It says the signup group was **deleted, not aged out**. Under GDPR storage limitation those are
  different remedies and only one of them actually removes the personal data.
- It keeps the absence of `logs:PutRetentionPolicy` framed as **deliberate scoping**, which it is —
  that is a defensible least-privilege posture, not an operational gap, and a reader who has just
  been told about one real gap deserves to know which constraints are chosen.

---

## 2b. THE BIGGER ONE: `privacy.html` §2d is publicly false (found 2026-08-05)

`SECURITY.md` is a trust document. **`privacy.html` is the legally operative
notice**, and it currently carries three false statements in one paragraph.
Re-verified live on 2026-08-05: all 13 groups still `None`.

| §2d says | Reality |
|---|---|
| "retained for **7 days** then automatically deleted" | Never expire |
| "**API Gateway logs** include ... source IPs, and user agents" | **No API Gateway log groups exist at all**, and `backend/template.yaml` has no `AccessLogSetting`. What exists is 13 **Lambda execution** log groups |
| Subprocessor table: "**Anonymous** request logs (7-day retention)" | The Signup group held raw email addresses 26 Jun – 23 Jul and still holds 8,730 bytes |

Under UK GDPR this is an Art 13(2)(a) transparency problem sitting on top of an
Art 5(1)(e) storage-limitation one. It also means `privacy.html` and
`SECURITY.md` now **contradict each other in public**: SECURITY.md honestly
describes the gap as open, privacy.html claims it is solved.

> **CHOSEN AND APPLIED 2026-08-05: Version A.** `privacy.html` §2d and the AWS
> subprocessor row now read 30 days. **The claim is currently false**, and that
> is deliberately safe rather than accidentally forgotten: a new blocking
> preflight check, `scripts/check_log_retention.sh`, compares the document to
> AWS and **fails until §1 below is actually done**. Preflight is red until then,
> so this cannot be committed or pushed unnoticed. If §1 is not going to happen
> soon, swap §2d to Version B and preflight goes green honestly.

### Version A — apply AFTER §1 is done (preferred)

Replace §2d's final two sentences with:

```html
<p>
  <strong>2d. Server logs (AWS)</strong> Sky Score's backend runs on AWS Lambda +
  API Gateway in the <code>eu-west-2</code> region (London). Each Lambda function
  writes an execution log containing request timestamps, paths, response codes and
  error traces. We do not enable API Gateway access logging, so no separate access
  log of source IPs and user agents is kept. Execution logs are retained for
  30 days and then deleted automatically. They are used solely for debugging and
  to investigate suspected abuse, and we do not link them to identities.
</p>
```

Then correct the AWS subprocessor row from `Anonymous request logs (7-day
retention)` to `Lambda execution logs (30-day retention)`. Dropping the word
"anonymous" is deliberate: it was not true of the signup group.

> **KNOWN LIMITATION of `scripts/check_log_retention.sh` (noted 2026-08-05).**
> It asserts that AWS retention **is 30 days**, full stop — it does not read
> `privacy.html` and compare. So if you switch §2d to **Version B** (honest
> interim: "currently retained indefinitely"), the gate stays **RED even though
> the documents would then be truthful**. That is wrong, and it should be fixed
> by having the script parse the retention figure out of `privacy.html` and
> assert only that AWS matches whatever the page claims. Left as-is because
> Version A was chosen and the console work is intended — but do not spend an
> hour puzzling over a red gate on a Version B tree.

### Version B — apply NOW if §1 will not happen within a few days

Same paragraph, but the retention sentence becomes:

```html
  Execution logs are currently retained indefinitely. We are applying a 30-day
  retention policy across all log groups; until that work completes this page
  will continue to say so rather than describe an intention as a fact.
```

**Version B is worse PR and better law.** The 2026-07-29 note at the top of this
file already settled the principle for `SECURITY.md`: holding an honest
correction back was preserving a false statement. The same reasoning applies
here with more force, because this is the notice a data subject relies on.

**Do not leave the "7 days" text in place as a third option.** That is the only
choice that is wrong under both readings.

---

## 3. Second correction, same edit

`SECURITY.md` line ~72 currently says `/preflight` runs "the unittest suite (**60 tests**)".

That is stale by a factor of four and a half. Verified 2026-07-27:

- backend: **125 passed, 8 subtests**
- root: **145 passed** (140 before today's NSPL batch-write coverage added 5)

Suggested: `the Python test suite (270 tests across backend and root)`.

Worth folding into the same commit — it is a factual claim in a customer-facing document, and the
whole point of the exercise is that this file can be trusted.

Note also that the preflight bullet lists Prettier as blocking. It currently is not passing:
`npm run format:check` flags `index.html`. See the session notes — reformatting an 8,200-line
hand-maintained file is a decision, not a chore, and was deliberately left alone.

---

## 4. Then push

```bash
git add SECURITY.md
git commit -m "Security: close the log-retention gap the docs described as open"
git push origin master
```

`npm run trigger:ios` *is* `git push origin master`, so the push also kicks off a Codemagic iOS
build. That is fine, but know it is happening rather than discovering it from an email.

---

## 5. The durable fix, NOT yet done: declare retention in `template.yaml`

§1 is complete, but it was done **by hand**, and hand-applied retention does not survive the
thing most likely to undo it. **Lambda recreates a deleted log group on the next invocation with
no retention policy at all.** `SignupFunction`'s group was deleted on 2026-08-07, so the next
person who signs up recreates it at *Never Expire*, `privacy.html` immediately overstates the
position again, and `scripts/check_log_retention.sh` goes red — blocking commits for a reason
that is a customer action rather than a defect. That is the same shape as the API-quota failure
the same day, and it is worth removing rather than living with.

**The fix** is an explicit `AWS::Logs::LogGroup` per function:

```yaml
ScoreFunctionLogGroup:
  Type: AWS::Logs::LogGroup
  Properties:
    LogGroupName: !Sub "/aws/lambda/${ScoreFunction}"
    RetentionInDays: 30
```

**Why it is not done yet, and what to watch for.** CloudFormation *creates* the group, so a
declaration for a group that already exists fails the whole stack update with
`already exists`. Seven of the eight groups exist right now; only `SignupFunction`'s does not,
because we deleted it. So this cannot simply be added in one pass. The options, in order of
preference:

1. **Resource import** — bring the seven existing groups under stack management, then add
   `RetentionInDays`. Correct and non-destructive, but a multi-step console/CLI flow.
2. **Delete then declare** — delete each group and let the stack create it. Now much cheaper
   than it was, since the most we lose is 30 days rather than the project's entire history, and
   `flightmap-dev` finally has `logs:DeleteLogGroup`. Destructive, and it discards whatever the
   logs currently hold.
3. **Declare for `SignupFunction` only** — legal today and fixes the one group actually at risk,
   but leaves the template inconsistent, which is its own trap for the next reader.

Whichever is chosen, do it as a **deliberate deploy**, not folded into an unrelated change: it
touches every function in the stack, and a failed stack update on this template takes the whole
API down with it.
