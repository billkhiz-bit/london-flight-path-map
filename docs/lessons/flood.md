# Flood risk: georeferencing and its gates

> Moved verbatim from `CLAUDE.md` on 2026-10-17 to keep the session-start file small.
> The 10-of-11-cities georeferencing fix, check_flood_georef.py sampling, the content cache.
> Statements are dated as written; re-measure a number before relying on it, and when a
> rule here changes, update the one-line rule in `CLAUDE.md` too.

<!-- CLAUDE.md lines 128-185 (2026-10-16) -->
> ## FLOOD WAS MIS-GEOREFERENCED IN 10 OF 11 CITIES - FIXED 2026-08-30 (audit F24/F39)
>
> `fetch_ea_flood_risk.py` clipped edge tiles to the city bbox but **requested
> every tile at 2000x2000 px** whatever ground it covered, then mosaicked at a
> uniform 10 m/px. A 5 km-wide edge tile rendered at 2.5 m/px and was pasted as
> if 10 m/px - **stretched up to 5x**, dragging flood polygons kilometres out of
> position. **London was the worst city, not a footnote: 6 of 12 tiles clipped,
> 5.00x.** Only Nottingham (40x40 km) is an exact multiple of the 20 km tile.
>
> **The fix is `tile_px()`**: request each tile at its real extent, so every tile
> is genuinely 10 m/px and the mosaic's existing assumption becomes true. The
> bbox is snapped to 1 km, so the division is always exact. Verified by
> simulation before any fetch: all 11 cities tile their mosaic with **zero holes
> and zero overlaps**.
>
> **The cache key had to change too, or the fix does nothing.** Tiles were named
> `flood_{e}_{n}.npy` - origin only, no extent - and `fetch_tile` skips on
> existence, so the stale 2000x2000 renders would have been served forever. The
> name now carries the extent.
>
> **Two more defects surfaced while fixing it, both the same class:**
> - **Bristol's edge tile was cached ALL-ZERO** from before the blank-render
>   guard existed - 2000x2000 of code 0, "surveyed, no flood risk", over 220 km².
>   Exactly what that guard's own comment predicted would outlive the outage.
> - **The mosaic initialised to `np.zeros`**, and code 0 is a REAL READING
>   meaning no risk. It is `255` (Unavailable) now. Unreachable while a failed
>   tile aborted the city; load-bearing the moment partial mosaics became legal.
>
> **A city is no longer abandoned for one bad tile.** Bristol and Teesside are
> each held by one near-all-sea tile the service renders blank at every
> resolution tried (10, 5.5 and 5 m/px - measured, not assumed). Bristol's lies
> outside all four boroughs; Teesside's clips one corner of Redcar. The gap is
> carried as Unavailable and reported by `floodCoverage`.
>
> **Effect, measured against the pre-fix file:** 37 of 81 boroughs moved, **13
> changed band**, none lost. Sefton **31.39 -> 0.27** `high -> low` (the audit
> predicted 0.28 by hand), South Tyneside **10.94 -> 0.11**, Doncaster
> **24.38 -> 6.39**. **Teesside GAINED flood for the first time**, so coverage
> is **86 of 91, up from 81**.
>
> ### The gate: `scripts/check_flood_georef.py`, blocking, `net_check`
>
> `build_borough_bands.py --check` could never see this - it re-derives from the
> same mosaic, so the two things it compares are the file and itself. The new
> gate asks the **EA's own GetFeatureInfo** what `risk_band` it publishes at a
> BNG coordinate. It asserts MEDIUM-OR-HIGH (the scored quantity), **in both
> directions**, because "where we say flood, the service agrees" passes a mosaic
> that has lost its polygons entirely.
>
> **Its first version PASSED the known-bad mosaic 9 of 9**, and that is the part
> worth remembering. Uniform sampling proves nothing here: measured against the
> pre-fix London file, the **six interior tile blocks were byte-identical** and
> only the top row and right column had moved, so half the samples could not
> fire. `spread_samples()` draws one sample per grid cell, **periphery first**,
> because a tiling error accumulates at the edges by construction. Re-proven
> red at **33%** on the same file. **Sampling was the whole gate; the network
> call was the easy half.**

<!-- CLAUDE.md lines 1988-2005 (2026-10-16) -->
**THE FLOOD GATE IS CONTENT-CACHED SINCE 2026-09-09, and the guards are the
point.** A cold run is **17m28s**, a warm one **1m24s** - measured back to
back. Keyed on each mosaic's sha256 **plus `--per-class` and `--seed`**,
because a cached run at 4 samples says nothing about one at 12. `--no-cache`
forces a full run; `.flood-georef-cache.json` is gitignored.

A cache is also how a gate quietly stops checking, which is the risk the
decision named, so it fails toward MORE verification and every guard was
proven rather than asserted: **one ROTATING city is verified every run**
whatever the cache says (date-keyed, so it advances daily and covers all
eleven in eleven days); the cache **hard-expires at 7 days**, per entry;
**only passes are cached**; a corrupt, wrong-shaped or expired cache returns
**zero** entries; a tampered key re-verified that city alone and left the
other ten cached; and **the run FAILS if no city reached the EA service**,
which the rotation makes unreachable by construction - asserted because the
construction is what a future edit would remove. Skipped cities print **in
their own position**, never as an end-of-run summary.

### A confirmation too small to say so (2026-11-05)

Preflight went red on Tyne and Wear at 12/14 (86%) on the 16-a-class confirmation, the day's rotating city, with no flood file changed. Seeds 23 and 37 on the same
mosaic read 13/14 and 16/16, so the map had not drifted; the seed is fixed, so the same cells would have failed all day, and again at its next turn. Changing the seed to go green is
no answer, and neither is waiting for the rotation. At 16 the confirmation allows one miss, so a true 95% class fails about one run in five.

The first fix was 48 at the same 90%, chosen from the binomial: fairer to an honest class, harder on a bad edge at 81%. **An independent review showed that formula was the wrong
instrument, and Bill was told the wrong thing from it ("harder on a real defect") until it was measured.** The sampler is not independent draws. It goes cell by cell, so a small cell repeats its pixels, and a sparse class has far fewer
places than samples (Tyne and Wear's medium-or-high class has 197 interior pixels in 7 cells: 48 draws are about 32 places). And 4 misses in 48 is a looser bar than 1 in 16.

Measured on all 12 mosaics' medium-or-high class, over 12 seeds, with a bad edge (one row or column of the grid) agreeing a third and the rest 97%, working over distinct pixels. Each figure is how often the confirmation passes:

| Design | True 95% class | True 93% class | Bad edge, mean | Bad edge, worst city |
|---|---|---|---|---|
| 16 at 90% (was) | 81% | 69% | 31% | 75% |
| 48 at 90% | 89% | 75% | 26% | 62% |
| 48 at 92% | 77% | 58% | 15% | 36% |
| 64 at 90% | 93% | 82% | 30% | 60% |
| **64 at 92% (chosen)** | **87%** | **71%** | **19%** | **41%** |
| 80 at 92% | 86% | 68% | 17% | 42% |
| 96 at 92% | 86% | 65% | 15% | 38% |

The test for a change here is city by city, not the mean: a design must be no easier on a bad edge in ANY city and no harder on a true 95% class in any. 48 at 90% failed it (London 40 to 48%,
West Yorkshire 39 to 49%, Teesside 40 to 50%), 64 at 90% worse, 48 at 92% failed the other way. 64 at 92% is the smallest of those tried that passes (at a true 93% class Manchester is one point down, 69 to 68%). It allows 5 misses in 64.
A confirmed miss now adds about 21 minutes, on a miss only. This does not make sparse classes reliable: a bad edge on Tyne and Wear still passes about a third of the time, as it did. It says so here rather than in a promise.

**Do not draw without replacement.** The review's first suggestion, and it looks like a plain bug: 48 draws of Tyne and Wear are about 32 places. Measured, distinct draws take a bad edge from 32% to 96% there (Teesside 50 to 96%, Manchester 62 to 91%),
because a small edge cell runs out and stops counting. The repeats are what keep it seen. `spread_samples` now says so.

Left as they are, knowingly: top-ups stay uniform (a confirmation under its floor is topped up from the whole class, which dilutes an edge; the ratio is unchanged from 16 and 12, and a run must lose a quarter of its samples to reach it). The cache key does not name the confirmation's
size, so a pass under the old rule stands to its 7 days: it was an honest pass under the rule of its day. A direct `--per-class 64` now meets the confirmation's bar (`bars_for`), where it had the plain 80%.

### A sample too small to fail on (2026-11-04)

Preflight went red on Merseyside at 3/4 (75%) with no change to any flood file. At 4 cells a class, ONE miss is under the
80% bar; the seed is fixed and Merseyside was the day's rotating city, so the same cell would have failed every run that
day. Re-measured at 16 a class with another seed: 15/16 and 15/15, 13-16 cells. So a class under the bar on fewer than
`CONFIRM_PER_CLASS` (16) a class is now re-sampled at 16 and judged on that (`needs_confirming`), at a HIGHER bar: 90%, with
12 cells reached. The first version kept 80%, and a review caught it: 4 samples are all edge cells but 16 take the whole
4x4 grid, so one bad edge reading a third scores about 81% and would pass and be cached, while a whole-mosaic proof could
never show that. An unreachable or untested class never reaches the re-sample, so a throttled run cannot be re-run into a
pass (`tests/test_check_flood_georef.py`). Because this makes a gate more forgiving it was proven red: a copy of Merseyside's
mosaic moved 2.5 km with its georeferencing kept (`--mosaic-dir`) read 3/14 (21%) on the bigger sample and exits 1, and one with only its top quarter moved read 11/14 (79%) and exits 1, while the true mosaic read 14/15 (93%) and 15/15. A confirmed miss adds about five minutes.

