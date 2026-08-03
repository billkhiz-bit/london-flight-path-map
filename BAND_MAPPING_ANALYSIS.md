# Quiet band mapping: WHO 45 dB against DEFRA's 55 dB floor

**Date:** 2026-08-03 · **Status:** analysis, no code change recommended beyond a documentation correction
**Question:** METHODOLOGY §4.1 awards a perfect **10.0** to everything below **55 dB Lden**, while citing a WHO guideline of **45 dB**. Is the mapping wrong?

---

## 1. Conclusion first

**The bands are not wrong. The health claim attached to the lowest band is.**

The 5-dB buckets are correctly anchored to DEFRA's published reporting bands, and nothing about the 55/60/65/70/75 boundaries needs moving. But §4.1 labels the `< 55` band *"Below WHO health-impact threshold; not measurably affected"*, and that is false by the section's own citation: it states WHO recommends aviation stay below **45 dB Lden**, so a band spanning 45–55 dB is entirely **above** the threshold it claims to be below.

**Re-banding cannot fix this, because the data does not exist.** DEFRA publishes strategic noise mapping only from 55 dB upward — its own bands, quoted in §4.1, are `55-59, 60-64, 65-69, 70-74, ≥75`. There is no 45–55 dB contour to score against. Introducing one would be inventing precision the source does not provide.

**So the correct fix is to stop claiming what we cannot know.** `low` does not mean "not measurably affected". It means **"below the threshold at which DEFRA is required to map"** — which is a statement about the survey, not about the air.

This is the same defect class as four others found on 2026-08-03: the DEFRA raster nodata fill, `crime_to_score(None) → 5.0`, the Ofsted bands, and the growth floor. **Absence of measurement rendered as a favourable measurement.**

---

## 2. What was verified, and how

| Claim | Source | Verified |
|---|---|---|
| WHO 2018 strongly recommends aircraft **< 45 dB Lden** and **< 40 dB Lnight** | WHO Environmental Noise Guidelines for the European Region (2018), corroborated across three independent secondary sources | **Yes** — the figure in §4.1 is correct |
| DEFRA publishes bands only from 55 dB up | §4.1's own text quotes them: `55-59, 60-64, 65-69, 70-74, ≥75` | **Yes**, from the document itself |
| `< 55` is scored 10.0 and labelled "not measurably affected" | `METHODOLOGY.md` §4.1 table; `IMPACT_TO_QUIET` in `app.py:115` and `index.html:4949` | **Yes** |

The WHO figure was checked against the publisher rather than taken from the repo, because the repo asserting a number is not evidence that the number is right — three separate claims of that shape have failed this week.

---

## 3. What is actually live

Two mappings share these values, and only one of them answers today.

| Mapping | Where | Status |
|---|---|---|
| `lden_db_to_quiet` | `app.py:2181`, reached only from the raster path | **Dormant.** The raster tier is quarantined, so no request reaches it |
| `IMPACT_TO_QUIET` | `app.py:2670` and `index.html:4989`, borough-level | **Live** |

Postcode queries answer from the Haversine tier and touch neither. Borough queries answer from `IMPACT_TO_QUIET` — confirmed live: `?borough=Hounslow` returns `quietResolution: borough`.

**Live exposure: 13 of the 33 London boroughs sit in the `low` band**, so **39% of the borough cohort scores a perfect 10.0** on a justification that contradicts its own citation.

| Band | Boroughs | Score |
|---|---|---|
| low | **13** | **10.0** |
| low-moderate | 8 | 7.5 |
| moderate | 6 | 5.0 |
| moderate-high | 2 | 3.0 |
| high | 2 | 1.5 |
| severe | 2 | 0.0 |

---

## 4. Why re-anchoring to 45 dB is the wrong instinct

The obvious move is to shift the scale so 10.0 means "below 45 dB". Three reasons not to:

**There is no data.** DEFRA maps from 55 dB. A borough currently in `low` might be at 54 dB or at 30 dB; the source cannot tell us, and neither can we. A band boundary at 45 would be a boundary we cannot evaluate anyone against.

**It would import a penalty with no evidence.** Dropping the `low` band from 10.0 to, say, 6.0 asserts that those boroughs *are* affected. That is the mirror image of the current error — replacing an unevidenced reassurance with an unevidenced penalty. Both are claims about unmeasured air.

**The two thresholds answer different questions.** 55 dB is a *regulatory reporting* threshold under END 2002/49/EC: the level above which member states must produce strategic maps. 45 dB is a *health* threshold: the level above which WHO finds adverse effects. Neither is wrong; §4.1's error is treating one as the other.

---

## 5. Recommendation

**Do not change any score.** Correct the documentation, and disclose the limit.

1. **Relabel the `low` band honestly.** It is "below DEFRA's 55 dB mapping threshold", not "not measurably affected". State plainly that WHO's guideline is 45 dB and that the 45–55 dB range is **unmeasured by this source**, so a `low` borough may or may not exceed the WHO guideline.
2. **Keep 10.0.** It is the least-wrong value available: the component measures *aircraft noise as mapped by DEFRA*, and by that measure these boroughs are at the floor. Changing it would require data that does not exist.
3. **Record it in §11** as a declared limitation rather than leaving it implied.
4. **Revisit if DEFRA lowers its threshold.** Round 5 is expected around 2027 (§4.1). If it maps below 55, this becomes a data question rather than a disclosure one.

**This does not gate the raster quarantine.** The quarantine was previously described as blocked on this question. It is not: the raster's problem is coverage — 89.5% of London falls outside any contour — and that is unaffected by where the bands sit. The two are independent.

---

## 6. What this does not cover

- **No dose-response modelling.** Whether 10.0/7.5/5.0/3.0/1.5/0.0 is the right *spacing* between bands was not re-derived. §4.1 justifies the spacing as reflecting an inverse-square-ish dB-to-health relationship; that claim was not tested here.
- **Road and rail noise are out of scope.** Sky Score models aircraft noise only. WHO publishes separate, higher thresholds for road (53 dB) and rail (54 dB), and a resident experiences the sum. This analysis says nothing about total acoustic environment.
- **The 53 dB figure in §4.1 was not verified.** The section attributes "53 dB as the threshold above which annoyance and cardiovascular risk become measurable" to WHO. 53 dB is WHO's **road traffic** guideline; whether it is also the aircraft annoyance-onset figure was not established, and that sentence should be checked before it is relied on.
