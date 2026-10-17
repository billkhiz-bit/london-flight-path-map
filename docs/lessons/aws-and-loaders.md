# AWS resources and the data loaders

> Moved verbatim from `CLAUDE.md` on 2026-10-17 to keep the session-start file small.
> Resource IDs, DynamoDB tables, NSPL rolls, loader speed and write policy, detached runs.
> Statements are dated as written; re-measure a number before relying on it, and when a
> rule here changes, update the one-line rule in `CLAUDE.md` too.

<!-- CLAUDE.md lines 1751-1839 (2026-10-16) -->
## AWS Resources

- **API Gateway**: `https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/`
- **CloudFront**: `https://d1oe4ftwutjpf.cloudfront.net` (distribution EGSSPJKLFL33M)
- **S3 bucket**: `london-flight-map-frontend` (eu-west-2)
- **DynamoDB tables** (4, all PAY_PER_REQUEST, eu-west-2): `london-flight-map-favourites`, `london-flight-map-signups`, `london-flight-map-noise-raster` (DEFRA Lden samples, loader `scripts/load_defra_raster.py`), `london-flight-map-postcodes` (ONS NSPL index, loader `scripts/load_nspl.py` — **rolled to the August 2026 edition on 2026-09-09: 2,704,825 rows in 58 minutes on the BatchWriteItem path.** (This said "roll to the August 2026 edition when it ships" until 2026-09-11, two days after the roll completed and directly above a block headed "THE 2026-08 ROLL IS COMPLETE" - the bullet is what a session reads first.) Next: the November edition, ~mid-late Nov). Both loaders run locally, not in Lambda, and both tables are forward-compatible: the score Lambda works correctly when they are absent or empty and upgrades silently once data lands, so **loading never needs a second deploy**.

  > ## THE NSPL GEOGRAPHY COLUMNS CARRY A YEAR SUFFIX AND IT MOVES (2026-09-09)
  >
  > February 2026 publishes `lad25cd` / `ctry25cd` / `rgn25cd`; **August 2026
  > publishes `lad26cd` / `ctry26cd` / `rgn26cd`**, and the file went 36 columns
  > to 35. `load_nspl.py`'s docstring called the read columns *"stable across
  > NSPL editions"*. They are not. **The CODES are unchanged** - all 94
  > `LAD_TO_BOROUGH` entries appear in both editions and both hold 363 distinct
  > LADs - so only the header moved, and no borough mapping needed touching.
  >
  > **FOUR scripts read these columns, and only one survived the rename.**
  > `build_city_neighbourhoods.py` already resolved by prefix and exits if it
  > cannot; the other three were pinned to `lad25cd`. All resolve by prefix now
  > (`re.fullmatch(r'lad\d\dcd', c)`), copying that existing idiom rather than
  > inventing a second one. **Do not pin the suffix again** - it moves every
  > February.
  >
  > **`build_borough_bands.py` was the dangerous one, and it FAILED SILENTLY.**
  > The loader hard-fails on a schema change, but the bands builder read
  > `row.get('lad25cd', '')` - and `.get` with a default **returns `''` rather
  > than raising**. Every postcode would have failed to match a borough, an
  > empty map would have been returned, and the only symptom was a line reading
  > `0 live postcodes across 0 cities`. Its floor was `if seen and not retired`,
  > which **never fires when `seen` is 0**. This is the script that WRITES both
  > score holders. There is a `if not seen` floor now, and it names the column
  > it resolved. *A `.get` with a default is a silent skip wearing a guard's
  > clothes.*
  >
  > **The download is not one file.** The Geoportal zip (~185 MB, item
  > `9d8364ebae8b4439aa66cda440e54fc8`) carries BOTH a combined
  > `Data/NSPL_AUG_2026_UK.csv` (964 MB) and a `Data/multi_csv/` split of 182
  > per-area files. The loader wants the COMBINED one, saved as `data/nspl.csv`.
  > Fetch it from
  > `https://www.arcgis.com/sharing/rest/content/items/<itemId>/data`; find the
  > current itemId through the ArcGIS Hub API rather than scraping the page.

  **THE 2026-08 ROLL, MEASURED BEFORE LOADING (2026-09-09).** Feb -> Aug, on the
  fields this product uses: **+5,494 postcodes and 0 removed**; live postcodes
  1,807,729 -> **1,810,364 (+2,635)**; 4,236 newly terminated and 1,827
  un-terminated; **72,554 positions refined**, median move **20.5 m**, 83%
  within 100 m, p99 1.5 km; and **81 LAD reassignments touching a borough we
  score** (77 of them live), which is 0.004% of live postcodes. A routine
  currency roll, not a re-basing.

  **Compare COORDINATES, not the string.** A first pass comparing the lat/long
  text reported **597,960** changed, which would have implied a national
  re-grid; comparing as numbers gives 72,554. The difference is trailing-zero
  formatting, and the wrong number was the alarming one.

  **NSPL loader speed - `BatchWriteItem` IS GRANTED as of 2026-09-09, re-probed.** This entry said the grant was "in `backend/iam-policy.json` and not yet applied to the live policy", and that **a ~6 hour roll is the signal the grant never landed**. It landed: `batch-write-item` with an empty `--request-items` returns **`ValidationException`, not `AccessDeniedException`**, and authorisation precedes validation. So the next roll runs the fast `_flush_batch` path (25 items per call), not the ~129 rows/s per-item fallback that took 5.80 hours on 2026-07-26.

  The likeliest cause is the 2026-09-04 restore, which pasted the whole of `backend/iam-policy.json` back after the 3 Sep console edit had REPLACED it - the same event that fixed `/aws-debug`. **Re-probe before planning around either figure**: a permission is a timestamp, not a property, and this one has now been recorded wrong in both directions. `scripts/check_aws_permissions.py` deliberately does NOT cover `BatchWriteItem` (it is a stateful write), so probe it the way that probe does - send a deliberately invalid request and classify on the ERROR CODE.

  Verify a load with `get-item`, never `describe-table`'s `ItemCount` (it refreshes ~6-hourly and reads 0 throughout).

  **THE 2026-08 ROLL IS COMPLETE (table 2026-09-09, derived shares 2026-09-10).** The table held the 2026-02 edition (2,699,394 rows, measured live) and was rewritten from `NSPL_AUG_2026_UK.csv` in 58 minutes at the batch-write rate - 2,704,825 rows. `NSPL_VINTAGE` in `load_nspl.py` was moved to `'2026-08'` AFTER the run, deliberately - **it is metadata written into the checkpoint payload, not read from the file**, so it does not self-correct, and the loader refuses to resume a checkpoint whose vintage disagrees with the constant, so editing it mid-run forces a restart from row 0. The `__META__` row was stamped `2026-02` from the running process's memory for the same reason and re-stamped by hand. **The re-derivation that followed moved 240 numeric fields across both holders, none of the four scored shares by more than 0.5, six `Environment` components by 0.1, ONE headline score (Merton 6.0 -> 5.9) and ONE band** - Dudley road noise `moderate -> low` on an unrounded share crossing 50% under a printed `50.0` that did not move. Bands are cut on the unrounded share BY DESIGN (METHODOLOGY s7.1, same rule as s6's round-once); 4 of 258 published band/figure pairs sit on a boundary that way, three of them pre-dating the roll. Do not band from the rounded figure to "fix" it.

  **The load is an UPSERT and that is safe here only because nothing was removed.** August adds 5,494 postcodes and removes none, so no row is orphaned. A future edition that DROPS postcodes would leave them behind in the table, still resolving, with no pass that deletes them - check `REMOVED` in the delta before assuming otherwise.

  **The derived shares are NOT updated by the load.** `transportWithin800mPct`, `airQualityWhoRatio`, `roadNoiseAboveWhoPct` and `floodMediumOrHighPct` all come from a scan of `data/nspl.csv` by `build_borough_bands.py`, not from DynamoDB - so a load leaves them describing the PREVIOUS edition's geography until `--check` and then `--write --write-lambda` are re-run - which is what happened between 22:33 on 9 Sep and the morning of 10 Sep. Rolling the table and not the bands leaves the two describing different vintages, and nothing but the advisory `borough bands == sources` stage says so. **And the bands are not the only readers**: eight scripts read `nspl.csv`, and the per-postcode DEFRA tiers (aircraft table, air-quality table, the two client quiet datasets) and the neighbourhood centroids all sample at POSITIONS - after the August roll 1,520 new live postcodes had no air-quality row and 154 sat on an aircraft contour but scored from geometry, with NOTHING saying so. A roll is done when every reader of the file has run; `HANDOVER.md` s0 step 7 is the list.

  **Loader write policy is SHARED, in `scripts/ddb_write.py` (2026-08-09).** Both DEFRA loaders import it; do not paste the retry logic into a third loader, and do not fork `FATAL_CODES` — two copies drift into one loader waiting out an error the other raises on, visible only during a multi-hour run nobody is watching. It exists because both DEFRA loaders kept dying mid-run with a bare boto3 client: sleep at 21:28:12 on 8 Aug, checkpoint stopped at 21:27. Sleep does not kill the process, it kills the in-flight connections, and an unguarded `ex.map` turns that into a fatal. The 30-minute wait is **bounded on purpose** — unbounded, an IAM denial spins forever, which is what `load_nspl.py` did when `BatchWriteItem` was refused. Covered by `tests/test_ddb_write.py` (13 tests, both failure directions proven red).

  **`scripts/load_aircraft_rasters.sh` is the chained aircraft-raster runbook (2026-08-12).** It waits for the air-quality loader's checkpoint to disappear, loads the seven per-airport coverages in sequence, and **gates the frontend deploy on all seven succeeding**. Resumable — each raster keeps its own checkpoint, so re-running after any death continues. `SKIP_WAIT=1` to skip the wait, `NO_DEPLOY=1` to load only. Check progress with `tail aircraftload.log`.

  **`Start-Process -ArgumentList '-lc','<command string>'` SILENTLY RUNS ONLY THE FIRST WORD.** PowerShell joins ArgumentList elements without quoting, so `sh -lc 'cd X && run.sh'` becomes `sh -lc cd X && run.sh` — sh takes `cd` as the whole command, exits 0 in milliseconds, and leaves two empty redirect files and no log. It looks exactly like a script that crashed before its first line. Pass the SCRIPT PATH as the argument and let `-WorkingDirectory` do the `cd`.

  **Run long loads detached and unbuffered**, or the next death is as undiagnosable as the last two — neither left a log, and the cause had to be read out of `Get-WinEvent -ProviderName Microsoft-Windows-Kernel-Power`. Use PowerShell `Start-Process` with `python -u` and redirected output so the run outlives the session. Check liveness with `sh scripts/load_status.sh` (reads checkpoint *mtime*, not file existence); a stopped loader resumes by re-running the same command. **`Start-Process sh.exe` inherits a bare Windows PATH** - no `dirname`, `tee` or `date` - so a runbook dies in a second with the only trace in the stderr file; prepend `C:\Program Files\Git\usr\bin` to `$env:PATH` in the launching PowerShell first (2026-09-10).

  **EVERY BULK LOAD IN THIS REPO'S HISTORY RAN ~50x SLOWER THAN IT SHOULD HAVE, FIXED 2026-09-10.** Both DEFRA loaders write each batch of 25 through a 25-thread executor, and their docstrings said that gives throughput "comparable to BatchWriteItem". **boto3's default connection pool is 10**, so 15 threads found the pool full on every batch, urllib3 discarded their connections, and each call paid a fresh TLS handshake. Measured against the live table with the loaders' own client: **sequential 17 ms/call (~60/s); 25 threads on a pool of 10, 13/s; 25 threads on a pool of 25, 675/s.** The executor was making things FIVE TIMES SLOWER than no executor. That is the untold half of the 14 h and 18 h air-quality deaths (they had to be running long enough to meet a laptop sleep), the "~1 hour" estimates that never came true, and Nottingham's road tier taking 17 minutes when Teesside's took 37 seconds after the fix. `ddb_write.MAX_WORKERS` is now the ONE holder for the width, `make_client` sizes `max_pool_connections` to it, both loaders import it rather than writing `25`, and `tests/test_ddb_write.py` reads the pool off the CONSTRUCTED client and fails if it is narrower. **The docstring number was never measured** - `feedback-numbers-in-justifying-comments-expire`, except this one was wrong the day it was written.

  **Coverage lands alphabetically, and central London is LAST.** NSPL is scanned in postcode order, so the first `SW` row is at ~85% of a full pass and the first `W` at ~93%. A partial run therefore looks healthy from an outer-London spot check while the West End holds nothing — exactly how road coverage came to be published as "99.2%" while `W`, `WC` and `WD` had never been served a reading.
- **Bedrock models** (only relevant if the dormant Bedrock Lambdas are ever restored from git history): `us.amazon.nova-2-lite-v1:0` (simple) + `us.amazon.nova-pro-v1:0` (complex/multimodal)
- **API custom domain**: `api.skyscore.co.uk` — APIGW edge custom domain (created 2026-07-23, cert = the us-east-1 wildcard, base-path mapping → `prod`). Serves once Cloudflare has `CNAME api → d1pr4crjutz9z8.cloudfront.net` (DNS only / grey cloud). The raw execute-api URL keeps working regardless.
- **IAM**: `flightmap-dev` user, `FlightMapDeployPolicy`
- **Region**: eu-west-2 (London)

## Key Conventions

- All Lambda handlers follow the same pattern: `def lambda_handler(event, context)` with CORS headers
- Frontend communicates with backend via fetch to API Gateway endpoints
- SAM stack name: `london-flight-map`

