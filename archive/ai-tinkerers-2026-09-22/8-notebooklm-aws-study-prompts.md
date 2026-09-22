# Studying for AWS Solutions Architect with Sky Score as the worked example

NotebookLM prompts. Written 2026-09-21. Everything in the "verified inventory"
below was checked against `backend/template.yaml`, the deployment and the
repo's operations notes the same day, so the notebook starts from facts rather
than guesses.

---

## Step 1 - what to upload as sources (in this order)

From `OneDrive/Desktop/ai-tinkerers-demo/`:
1. `7-what-happens-when-you-type-a-postcode.pdf`  - the plain-English tour of every service and why
2. `5-how-it-works-plain-english.md`               - the fuller version, incl. the eight data inputs

From the repo `C:\Users\bilal\projects\london-flight-path-map\`:
3. `backend/template.yaml`        - the SAM blueprint: every Lambda, table, usage plan, throttle, timeout
4. `backend/iam-policy.json`      - the deploy user's permissions (least privilege, as applied)
5. `OPERATIONS.md`                - runbooks: deploy, log retention, IAM, data residency, incident notes
6. `Makefile`                     - the deploy targets (S3 keys, cache-control, invalidations)
7. `privacy.html`                 - the data-residency and retention promises the architecture must keep
8. `scripts/cloudfront_badge_behaviour.py` and `scripts/cloudfront_security_headers.py`
                                  - CloudFront as an edge cache and a security-headers layer
9. `README.md`

Optional, if you want the "why we cut the AI" story as a cost case:
10. The commit message of `69905ee` (7 May 2026) - `git show -s 69905ee > commit-69905ee.txt` and upload that.

Then paste the master prompt.

---

## Step 2 - the master prompt (paste into NotebookLM's chat)

```
You are my AWS Solutions Architect Associate study tutor. The sources are a
real, deployed product called Sky Score. Use it as the WORKED EXAMPLE for the
exam: teach each AWS concept by showing where Sky Score uses it, what
decision was made, and what the exam would expect me to know about that
decision - including the alternatives Sky Score did NOT choose and why.

Ground rules:
- Only state Sky Score facts that appear in the sources. If a source is
  silent, say "the sources do not say" rather than assuming.
- Map everything to the four exam domains: (1) Design Secure Architectures,
  (2) Design Resilient Architectures, (3) Design High-Performing
  Architectures, (4) Design Cost-Optimized Architectures - and to the six
  Well-Architected pillars where relevant.
- I am not from a technical background. Define every term the first time it
  appears, in one plain sentence, then use it normally.
- Prefer "here is the decision, here is the trade-off, here is the exam
  angle" over long descriptions.

Verified inventory of Sky Score's AWS estate (2026-09-21), so you can
anchor answers:
- Region eu-west-2 (London) for everything except Amazon Bedrock, called in
  us-east-1 (Virginia) for the Nova 2 Lite model. No VPC, no EC2, no RDS, no
  load balancer, no Auto Scaling: the design is fully serverless.
- Static site on S3, served by CloudFront (distribution EGSSPJKLFL33M). A
  CloudFront Function rewrites extensionless paths to <path>/index.html. A
  response-headers policy carries the security headers on the site behaviour
  (on 18 Sep the /badge behaviour was found to have none; the script that
  repoints it waits on an IAM permission). A second cache
  behaviour for /badge uses the API as a second origin, keyed on the
  postcode query string, honouring Cache-Control. index.html and the data
  files are uploaded with Cache-Control: no-cache; fonts with max-age 1 year.
- API Gateway REST API with two usage plans: a free tier (10,000 requests /
  month, rate 2, burst 5) and a demo plan (5,000 / month). API keys authorise
  per STAGE, so /v1/score/batch is denied to those plans via a per-method
  throttle of RateLimit 0. Every unauthenticated route has its own
  per-method throttle sized from measured CloudWatch traffic; the stage-wide
  ceiling is 50 RPS / 100 burst. An edge-optimised custom domain
  api.skyscore.co.uk uses an ACM certificate in us-east-1; DNS is Cloudflare.
- 8 Lambda functions (Python 3.11), one SAM template, stack
  london-flight-map: score, chat, signup, favourites, epc, sold_prices,
  transport, nhs. Every timeout is under API Gateway's 29-second integration
  cap, deliberately, so a slow upstream reaches the function's own fallback
  branch instead of producing a raw 504. The assistant (chat) gets its data by
  invoking the score function DIRECTLY (lambda:InvokeFunction), not over HTTP.
- 5 DynamoDB tables, all PAY_PER_REQUEST (on-demand): postcodes (2.7M rows,
  the ONS NSPL index; loaded offline with BatchWriteItem), noise-raster (DEFRA
  per-postcode samples), favourites, signups, signup-pending. Access pattern
  is single-item GetItem by key; no scans, no GSIs needed.
- Bedrock: one model (us.amazon.nova-2-lite-v1:0), one caller (chat), max 400
  output tokens, temperature 0.2. Five earlier Bedrock-backed features were
  removed on 7 May 2026 - primary reason answer variance, secondary reason
  cost (~$80-115/month at modest traffic).
- CloudWatch Logs: one log group per Lambda, 30-day retention, matching the
  privacy page; a preflight check compares AWS to the page and fails on drift.
- IAM: a single deploy user (flightmap-dev) with one customer-managed policy;
  each Lambda's execution role is scoped to its job (only chat may call
  Bedrock). The policy file in the repo is the intended policy; a probe
  script exercises 18 read-only actions against the live account and, as of
  18 Sep, reports 5 recently added verbs (CloudFront response-headers and
  DynamoDB reads) not yet pasted into the console - "a permission is a
  timestamp, not a property".
- SES: a verification-email path is built but switched off behind a template
  parameter until the sending identity is verified and the account leaves
  the sandbox.
- Deployment: `sam build && sam deploy` for the backend; `aws s3 cp` +
  `create-invalidation` for the front end, driven from a Makefile. No CI/CD
  pipeline deploys to production; a human runs it.

Start by giving me a ONE-PAGE overview: a table with one row per AWS service
Sky Score uses - columns: service | what it is (one plain sentence) | what Sky
Score uses it for | the decision/trade-off | exam domain(s) it maps to. Then
list the five exam topics that Sky Score does NOT exercise at all (so I know
what to study elsewhere). End with three questions to check I understood.
```

---

## Step 3 - follow-up prompts, one per study session

Copy one at a time. Each builds on the master prompt.

### A. Per-service deep dive (repeat for each service)
```
Deep dive on [SERVICE] as Sky Score uses it. Cover: (1) what it is, plainly;
(2) exactly how Sky Score configures it, citing the source; (3) the
alternatives an architect would weigh and why Sky Score's choice fits its
traffic pattern (quiet most of the time, spiky on demos); (4) three exam-style
scenario questions where the right answer is what Sky Score did, and one
where it would be the WRONG answer for a different workload. Define terms on
first use.
```
Services to run this for: S3, CloudFront (incl. CloudFront Functions and
cache behaviours), API Gateway (usage plans, API keys, throttling, the
29-second cap, custom domains + ACM), Lambda (timeouts, cold starts,
execution roles, direct invoke vs HTTP), DynamoDB (on-demand vs provisioned,
key design, BatchWriteItem, TTL), Bedrock (regions, model choice, cost
controls), CloudWatch Logs (retention, metrics, the 1,440-datapoint cap),
IAM (least privilege, a single deploy identity, what "a permission is a
timestamp" means), CloudFormation/SAM (infrastructure as code, change sets,
drift), SES (sandbox, verified identities).

### B. Map it to the four exam domains
```
For each of the four SAA domains, list every Sky Score decision that
demonstrates it, as "decision -> pillar -> what the exam expects you to
know". Then, for each domain, name the ONE decision in Sky Score you would
challenge in a design review, and what the exam's preferred pattern would be.
```

### C. The gaps - what Sky Score never touches
```
The exam covers much that Sky Score does not use: VPCs, subnets, security
groups and NACLs; EC2 and Auto Scaling; ELB/ALB/NLB; RDS, Aurora and read
replicas; ElastiCache; SQS, SNS and EventBridge; Step Functions; Route 53
routing policies; KMS and Secrets Manager; Organizations and SCPs; Direct
Connect and VPN; EFS/FSx; Kinesis; Storage Gateway. For each, explain (1)
what it is in one sentence, (2) why Sky Score has no need for it, and (3)
what change to Sky Score would create the need - e.g. "if the postcode table
needed relational joins, RDS or Aurora Serverless". This is my map of what
to study outside these sources.
```

### D. Resilience walk-through
```
Walk one request through the API from the client to the answer and back,
naming every AWS component it touches and what happens if each one fails:
CloudFront edge, API Gateway, the Lambda (cold start, timeout, throttle),
DynamoDB (throttling on on-demand, a missing item), Bedrock (a throttle, a
region outage in Virginia), CloudWatch. For each failure say what Sky Score
does today per the sources, and what the exam's resilience answer would be
(retries with backoff, DLQs, multi-region, caching). Then do the same for a
website visit through CloudFront to S3.
```

### E. Cost model
```
Build a monthly cost model for Sky Score from the sources: per-service, at
three traffic levels (100, 10,000 and 1,000,000 API calls a month plus
matching site visits). Show the pricing dimension for each service (requests,
GB-months, GB transferred, read/write units, tokens) and which services are
free at the low end. Then explain, with numbers, why the May 2026 removal of
five Bedrock features saved ~$80-115/month, and why the replacement assistant
costs about 25p per 1,000 questions. Label any figure that is an estimate.
```

### F. Security review
```
Review Sky Score's security posture from the sources against the Secure
Architectures domain: identity (one deploy user, execution roles), data
protection (what crosses to us-east-1, retention), network (no VPC - is that a
weakness or not for this design?), edge (CloudFront headers, the badge SVG
served from the site's own origin), API abuse (keys per stage, RateLimit 0,
per-route throttles), secrets (the EPC bearer token as a NoEcho parameter).
For each: what is done, what the exam would expect, and what you would add
first (MFA, KMS, WAF, Secrets Manager, CloudTrail).
```

### G. Quiz me
```
Give me 10 exam-style multiple-choice questions (four options, one correct)
where the scenario is a disguised version of a Sky Score decision. Do not
name Sky Score in the questions. After I answer, explain each one, then tell
me which domain I am weakest in and give me 5 more on that domain.
```

### H. Flashcards
```
Make 40 flashcards from the sources: front = a plain question, back = a
two-sentence answer with the Sky Score example. Group them: 10 per exam
domain. Include the numbers that matter (29-second cap, 30-day retention,
10,000 free requests, 50 RPS ceiling, 5 tables, 8 functions).
```

### I. Explain it back
```
I am going to explain Sky Score's architecture to you in my own words, as if
to a colleague. Correct any mistake gently, fill any gap, and then ask me one
harder follow-up question about the same component. Here goes: [type your
explanation]
```

---

## Notes on using NotebookLM well

- It answers only from the sources. If it says "the sources do not say", that
  is the tool working, not failing - add the file that holds the answer.
- Ask it to cite. "Which source says that?" catches the moments it blends two
  documents.
- Its Audio Overview (the podcast feature) is a good commute listen for the
  one-page overview from Step 2; ask it to "focus on the trade-offs, not the
  product".
- Re-run prompt B after every study week: the "one decision I would
  challenge" answers are where exam marks live.
