---
name: feedback-checks-that-cannot-fail
description: "Twelve Sky Score gates were green because they couldn't fail, not because things passed — including one in no runner at all, one whose stub never fired, and one whose key list was BOTH the write set and the compare set, and one FLOOR left one below the real count — audit a check by asking what it would MISS, not by reading what it runs"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 7cc805e0-c991-41f5-aac0-93edcdb00da1
  modified: 2026-08-09T15:33:32.759Z
---

**Found twice in one session, 2026-07-27, in unrelated systems.** Both gates reported green for months. Neither could have gone red.

1. **`/preflight` reported success while running nothing.** `make` is not installed in Git Bash here, and every check was piped to `tail` — **a shell pipeline exits with the status of its LAST stage**, so `anything | tail` is always 0. Two further defects in the same gate: the **167-test root suite was never in it at all** (only `backend/tests` ran), and `pip-audit` looped over `backend/lambdas/*/requirements.txt`, a glob matching nothing, with `|| true` on the end.

2. **The a11y scan covered one page in eight and failed on `critical` only.** It ran against `/` — already hardened by three a11y waves — so it reported a clean sweep while the B2B funnel had never been scanned. And **every real defect found was `serious`**, so even scanning those pages would have passed under the old threshold. Two independently defensible narrowings multiplied into a check that could not fail.

**Why:** every narrowing was reasonable in isolation. Pipe to `tail` to keep output readable. Scan the main page first. Fail only on critical to avoid noise. Nobody chose to disable a gate; it decayed into decoration one sensible decision at a time.

**How to apply:**
- **Audit a check by asking what it would MISS, not by reading what it runs.** Both of these were found that way; neither would have been found by re-reading the config.
- **Prove a gate can fail.** Inject a defect, confirm red, remove it, confirm green. `scripts/preflight.sh` was verified this way — do the same for any gate you touch.
- **Never pipe a command whose exit code matters.** Read the output, or use `${PIPESTATUS[0]}`.
- **Compare the check's coverage to its implied claim.** "No accessibility violations" reads as *the site is accessible*; it meant *one page of eight, critical only*.
- **A permanently-red gate is an ignored gate.** Prettier fails on every file here and reformatting `index.html` is a 19,205-line diff, so it is now explicitly **advisory and labelled as such** rather than left blocking-and-ignored. Honest amber beats decorative green *and* beats permanent red.
- **Executable beats descriptive.** The old checks were fenced code blocks in a skill markdown file — unrunnable, untestable, and drifted from the Makefile which had itself drifted from reality. Both claimed to be "preflight"; neither ran the same thing and one ran nothing.

## 2026-08-04: test the SCOPE of a guard, not only its logic

Three more instances in one day, same shape, and one new rule that would have
caught all of them.

- **`_CATEGORICAL_FIELDS` validated 3 of 4 categorical borough fields.** The
  missing one, `impact`, is the noise band — it feeds
  `IMPACT_TO_QUIET.get(bd['impact'], 5.0)`, so a typo like `sever` silently
  scores **5.0 where `severe` scores 0.0**, upgrading a severe-noise borough on
  the headline component. Existing tests all asserted the guard *works*
  (feed bad data → raises). **None asserted what it covers**, so a missing field
  was invisible to a passing suite.
- **`backend/tests/` was outside every ruff target** — the suite guarding the
  score engine was the one directory nothing linted. It held 4 import-order
  errors and an S105.
- **`web-deploy-all` covered 4 of 15 public surfaces** while being named "all",
  so eleven live files had no deploy command. A `make web-deploy-all` that day
  would have skipped two files edited minutes earlier and still reported
  success.

**The new rule: for any guard, write a test that asserts its COVERAGE.** Not
"does it reject bad input" but "does it look at everything it claims to". One
such test now exists (`test_every_scoring_lookup_table_is_actually_guarded`) and
it is the only thing that would have caught `impact`. Generalises to lint
targets, deploy targets and scan targets — **anything with a list of things it
processes needs a test that the list is complete**, because the list is where
these decay, never the logic.

**Corollary seen the same day:** a name that overstates scope (`web-deploy-all`,
"no accessibility violations") is itself the warning sign. Read every gate's
name as a claim and check the claim.

## 2026-08-07: a list decays when a NAME stops being unique, not only when it omits

`scripts/check_log_retention.sh` kept a hand-written list of removed Lambdas and
matched log groups against it **by name fragment**. It named `ChatFunction`.
Restoring `chat` on 6 Aug did not remove anything from the list — the entry was
still *there* and still *matched* — but there were now **two** ChatFunction log
groups, the dead Bedrock one and the live retrieval-only one, and the fragment
caught both. The one Lambda receiving free-text user input was silently
reclassified as an orphan, downgraded to a WARN, and **never compared against
`privacy.html` at all**. The gate printed a clean summary and exited 0.

Two things make this worth its own entry:

- **The coverage-test rule above would NOT have caught it.** A test asserting
  "the list covers every removed Lambda" passes: the list is complete. The
  defect is that an entry became *ambiguous*, matching a thing it was never
  meant to match. Completeness and unambiguity are different properties.
- **The fix is derivation, not a better list.** The active set now comes from
  `backend/template.yaml` — the artefact that actually decides whether a
  function exists — so restoring a Lambda updates the check automatically.
  Prefer deriving from the source of truth over any test that a copy still
  agrees with it.

Generalises: **anything matched by substring against a shared namespace is one
redeploy away from matching two things.** CloudFormation appends a fresh random
suffix on every create, so a function deleted and later restored leaves two
groups differing only in suffix — invisible to any check keyed on the name.

## 2026-08-08: existence is not liveness, and a scraped number cannot say how old it is

`scripts/load_status.sh` reported **both DEFRA loaders RUNNING, with progress
bars, while neither process existed** — road dead 38 hours, air quality 14. It
branched on whether the checkpoint FILE EXISTED, and the loaders delete that
file only on a *clean full finish*, so every interrupted run leaves one behind
forever. The one state worth reporting was the one rendered as health.

It also printed `rate 25.27it/s, elapsed 3:19:34` — scraped from a tqdm frame in
a log nothing had written to since 6 August. **A tqdm frame carries no
timestamp**, so a rate read from a dead run is indistinguishable from a live one.

Three transferable rules:

- **Liveness comes from a value CHANGING, not from an artefact existing.** Fixed
  by reading the checkpoint's mtime. Any "is it running" check keyed on a file,
  a lock, a PID file or a status row has this bug latent.
- **Derive the threshold from the measured cadence, never from what feels
  reasonable.** The checkpoint writes every 1,000 rows, and the road pass was
  measured at ~15 rows/s — so a *healthy* loader is silent for ~65s. The 30-60s
  threshold instinct suggests would have flagged the running loader as dead on
  nearly every invocation, which is how a check earns being switched off.
- **Print the raw input beside the verdict.** The age now prints on every line
  whatever the verdict says, so a reader can disagree with the threshold. A bare
  `RUNNING` gave them nothing to doubt.

**Same day, in the extension e2e:** the suite asserted the EPC section's
*heading* existed and nothing about its contents, so a new chart was invisible to
29 passing checks. Adding assertions surfaced two more instances of this family —
Playwright's `innerText` **refuses SVG outright** (`SVGElement` is not an
`HTMLElement`), and reading a *missing* element auto-waits 30s then **throws**,
aborting the run and taking the other 20 assertions with it. So the first
red-proof produced **no output at all** rather than one FAIL. **A test that
cannot survive the failure it tests for reports nothing on the day it matters** —
read through `count()` first. A `SKIP` state was added too, because folding "did
not run" into PASS is the original defect in miniature.

## 2026-08-09: a test that READS the constant it checks cannot disagree with it

Fifth instance, and the first found *during* the red-proof rather than months
later — which is the whole argument for doing the proof.

`tests/test_ddb_write.py` guards `FATAL_CODES`, the list of DynamoDB errors a
bulk loader must raise on rather than wait out. Get it wrong in one direction
and a 27-hour run dies on a blip; wrong in the other and an IAM denial stalls
every item for 30 minutes, silently. So the test was written first and the
constant emptied to prove it went red.

It did not go red. It reported **`7 passed, 1 skipped`**. The test was
`@pytest.mark.parametrize('code', sorted(ddb_write.FATAL_CODES))`, so emptying
the constant parametrised over an empty list and pytest **deleted the test**
instead of failing it. The one guard written to catch an empty fatal list was
erased by an empty fatal list.

- **New sub-shape.** Not omission (2026-08-04) and not ambiguity (2026-08-07),
  but **self-reference**: the expectation was derived from the artefact under
  test, so the two could never disagree. Any assertion sourcing its expected
  values from the code it checks is decorative, however elaborate.
- **`skipped` is a third state and it reads as green.** `pytest -q` prints
  `7 passed, 1 skipped` and exits **0**. Same family as folding "did not run"
  into PASS, noted a day earlier in the extension e2e.
- **Fix: write the expectation out by hand** in the test, then assert set
  equality against the constant separately. That second assertion is what goes
  red on a dropped code; the parametrised bodies cannot.
- **Read a red-proof's OUTPUT, not just its exit code.** Exit 1 would have been
  reassuring here and exit 0 was the finding. The count of tests that ran is
  part of the result.

Related: [[feedback-playwright-parallel-false-failures]], [[feedback-gitbash-shell-gotchas]], [[project-signup-funnel-outage]] (a dead feature hiding behind a passing suite is the same shape), [[feedback-verify-by-running-not-reading]], [[project-legal-liability-gaps]], [[feedback-graceful-failure-hides-broken]], [[project-defra-loader-deaths]].

---

**Sixth and seventh instances, 2026-08-27, both in one file and neither about
an assertion.**

**Sixth: a test wired into NO gate.** `tests/failure-path.mjs` appeared in
`preflight.sh`, `package.json` and the Makefile exactly zero times. The file
dedicated to "the fallback shipped untested" was itself never run - so its
checks could not fail in the most literal sense available. It had also been
**crashing** for some time, which nobody could see (see
[[feedback-a-gate-that-cannot-go-green]]). **Grep for a test file's NAME across
the runners before trusting that it guards anything**; the existence of a
well-written test is not evidence it executes. Same family as
[[feedback-recorded-followups-are-not-guards]]: an artefact is not a gate.

**Seventh: a stub that was never used, hidden by being REALISTIC.** New checks
stubbed `/transport` with a Playwright glob, `'**/transport?**'`, that matched
nothing - so all three cases were quietly answered by the **live TfL API**, and
they looked correct, because the fixture values were plausible (SW11 1AA really
is ~420m from Clapham Junction on Southern). A deliberately absurd fixture would
have exposed it instantly; a realistic one cannot.
- **Fix: assert the stub answered.** A `stubHits` counter, reset per case and
  recorded as its own check. **A fixture cannot tell you it was never used, so
  make the harness say so.**
- **Prefer a URL predicate to a glob** for route interception - `(url) =>
  url.pathname.endsWith('/transport')` cannot silently match nothing.
- Sibling of [[feedback-self-authored-fixtures-are-circular]], one level up: there
  the fixture was real but authored by the thing it tested; here it was never
  consulted at all.

**Eighth, same session, and it is the assertion shape after all:** a check read
`!/Good Service/i.test(panelText)` while the fix's own copy said *"this is not a
report of good service"* - so a correct tree went red. **An assertion whose
pattern can match the prose it is checking is one edit from inverting.** It
counts rendered `.line-status` DOM rows now. Compare the self-reference sub-shape
above: there the expectation came from the code under test, here from the copy
under test.

---

**Ninth, 2026-08-31: the FILTER UPSTREAM of the check, not the check.**

`tests/a11y-source.mjs` declared `FAIL_MODERATE = {heading-order,
landmark-one-main, region, aria-allowed-role}` with a comment explaining that
these are structural, that axe rates them moderate, and that they must fail the
build. The filter function was correct. The set was correct. **Axe never ran
those four rules**, because all four are tagged `best-practice` only and the
builder asked for `wcag2a|wcag2aa|wcag21a|wcag21aa` - so they could never appear
in `results.violations` and `FAIL_MODERATE.has(v.id)` was dead code from the day
it was written.

- **New sub-shape.** Not omission, ambiguity, self-reference, no-runner, unused
  stub or invertible pattern. Everything the check *did* was right; the tool was
  never asked to produce the input it examined. **Look one layer up from the
  assertion: at what the tool was CONFIGURED to collect.**
- **Prove it at the taxonomy level, not against today's data.** One command -
  `node -e "require('axe-core').getRules().find(r=>r.ruleId==='landmark-one-main').tags"`
  returning `['cat.semantics','best-practice']` - shows the set could never fire
  on ANY page, present or future. A live scan would only have shown it did not
  fire today, which reads as "nothing wrong".
- **What it hid:** missing `<main>` landmarks on `privacy.html` and `terms.html`
  (the two LEGAL pages) and on all 100 pages under `area/`, which were in no
  accessibility or responsive gate at all. Widening the gate then found a third
  page nobody had listed - `score-demo/api-docs.html`, the B2B API reference.
  [[feedback-hardening-a-gate-finds-new-defects]], four for four.
- **And the fix created instance ten, caught by red-proofing it:** a backslash-b
  in the new guard's regex was collapsed by a Bash heredoc into a literal
  backspace character, so the guard could never match. `grep` renders it as
  though the backslash were there and `node --check` accepts it. **A check that
  cannot fail, created while removing checks that cannot fail.** See
  [[feedback-gitbash-shell-gotchas]] item 3a.

---

**Eleventh, 2026-09-11: ONE list was both the WRITE set and the COMPARE set, so
a key left both at once.**

`build_borough_bands.py` writes `data/borough-extra.json` — a deployed public
asset — and `--check` re-derives it as a gate. Both loops iterate the same
tuple, `DERIVED_KEYS`: `--write` assigns `for key in DERIVED_KEYS`, and
`--check` compares `for key in DERIVED_KEYS`. So renaming a field by editing
that tuple makes the old key stop being written **and** stop being compared on
the same edit. Its last-written value stays in the published holder, frozen,
with nothing looking at it — a number the product serves and no longer computes.

Renaming `healthcareWithin1kmPct` -> `healthcareWithin500mPct` (audit I2) would
have shipped both keys on all 86 boroughs. **`ROADMAP.md`'s own "if it goes
wrong" column asserted this check catches exactly that.** It cannot: the
existing `holder_only` counter asks *"the derivation produced nothing for a key
it owns — why?"* (absent raster, new city), which is a different question from
*"the holder publishes a key nobody owns."*

- **New sub-shape.** Not omission, ambiguity, self-reference, no-runner, unused
  stub, invertible pattern, or upstream filter. Here the coverage list and the
  action list were **the same object**, so they could not disagree — a change to
  one silently changed the other. **When a single constant drives both what a
  tool DOES and what it VERIFIES, verification is not independent of action.**
- **Fix: a declared complement.** `FOREIGN_KEYS` names the keys other scripts
  own (crime, Progress 8, curated notes), and anything in the holder that is in
  neither list fails the gate. Declared, not discovered — a set computed from
  the file agrees with the file by construction, the self-reference shape above.
- **Deliberately does not auto-delete.** Removing a field from a deployed asset
  is a product decision; the gate names the key and the borough count and makes
  a human choose. Same reasoning that keeps `holder_only` a report.
- **Red-proved by injecting the stale key on all 86 boroughs** (1 finding) and
  green on the fixed holder (0). The injection had to be the *realistic* one —
  exactly what `--write` alone would have produced.
- **The documented procedure was the hazard.** ROADMAP said "run `--write` so
  the holder follows". Following it would have caused the defect the same row
  promised the gate would catch. **A runbook step is a claim; check it the way
  you would check a comment.** [[feedback-recorded-findings-can-be-inverted]],
  [[feedback-numbers-in-justifying-comments-expire]].

## 2026-09-19: a FLOOR that trails the real count

`scripts/check_deploy_drift.sh` asserts it compared at least N deployed data
files - a floor, so that a broken parse which silently checks nothing goes
red. `data/stations.json` became the 18th file on 18 Sep and **the floor
stayed at 17 for a day**. It still passed, because 18 >= 17, so nothing
pointed at it.

**What it could no longer catch is the thing it exists to catch.** At a floor
of 17, `stations.json` could have been dropped from the `data-deploy` target
entirely: the pass would have compared 17 files, cleared the floor, and
**reported agreement** - while the live page fetched a file no longer being
deployed. The floor was one below reality, which is the same as absent for
exactly one file.

**Why it is easy to miss:** a floor is written as a MINIMUM precisely so it
does not need editing when a city's boundary file is added. That reasoning is
right, and it is why nobody re-reads it - but it only holds while the floor
and the real count move together. The comment above it even said "the Makefile
target declares 17", a number that had quietly stopped being true.

**How to apply:**
- **Raise a floor in the same commit that raises the real count.** Not after an
  incident, and not "next time someone touches it".
- **A floor at N-1 is not a weaker check, it is no check for that one item.**
  Ask which specific removal the floor would now wave through.
- **A number quoted in a guard's own comment expires** - see
  [[feedback-numbers-in-justifying-comments-expire]]. Here the comment and the
  constant were wrong together, so they corroborated each other.
- Found by the echo-work pass after a deploy, not by the gate: the gate was
  green. Same lesson as the top of this file - **audit by what it would MISS**.
