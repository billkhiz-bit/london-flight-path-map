# What this is

This is one of ~80 memory files the coding agent (Claude Code) keeps for this
project, between sessions. It is a real file, copied unedited into
`3-memory-file-VERBATIM.md` beside this one. This excerpt is the top of it
plus the newest entry, sized to be read from the back of a room.

Notice what it records: not "the preflight passes" (a fact), but "here is how
a check can be green and still check nothing, and here is what to do about
it" (a check). That is the third takeaway - **don't record a fact, record a
check.**

---

    name: feedback-checks-that-cannot-fail
    description: "Twelve Sky Score gates were green because they couldn't
      fail, not because things passed - audit a check by asking what it
      would MISS, not by reading what it runs"
    type: feedback

**Found twice in one session, 2026-07-27, in unrelated systems.** Both gates
reported green for months. Neither could have gone red.

1. **`/preflight` reported success while running nothing.** `make` is not
   installed in Git Bash here, and every check was piped to `tail` - a shell
   pipeline exits with the status of its LAST stage, so `anything | tail`
   is always 0.

2. **The a11y scan covered one page in eight and failed on `critical` only.**
   Every real defect found was `serious`, so even scanning the other pages
   would have passed. Two reasonable narrowings multiplied into a check
   that could not fail.

**Why:** every narrowing was reasonable in isolation. Nobody chose to
disable a gate; it decayed into decoration one sensible decision at a time.

**How to apply:**
- **Audit a check by asking what it would MISS, not by reading what it runs.**
- **Prove a gate can fail.** Inject a defect, confirm red, remove it,
  confirm green.
- **Never pipe a command whose exit code matters.**
- **A permanently-red gate is an ignored gate.** Honest amber beats
  decorative green and beats permanent red.

    ... ten more instances, 4 Aug to 11 Sep, each a different way
        a check can be green without checking ...

## 2026-09-19: a FLOOR that trails the real count

A deploy check asserts it compared at least N data files - a floor, so a
broken parse that silently checks nothing goes red. An 18th file was added
on 18 Sep and **the floor stayed at 17 for a day**. It still passed, because
18 >= 17, so nothing pointed at it.

**What it could no longer catch is the thing it exists to catch.** At 17,
the new file could have been dropped from the deploy entirely and the check
would have reported agreement. A floor at N-1 is not a weaker check - it is
no check for that one item.

**How to apply:** raise a floor in the same commit that raises the real
count. Found by the write-up after the deploy, not by the gate: the gate was
green. Same lesson as the top of this file - **audit by what it would MISS**.
