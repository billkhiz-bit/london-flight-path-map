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

