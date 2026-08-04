# The airport term treats London City like Heathrow

**Date:** 2026-08-04 · **Status:** RESOLVED — the blocking fact was checked and it reverses the headline finding
**Found by:** measuring the raster/Haversine gap before choosing how to close it (`METHODOLOGY.md` §4.5, quarantine condition 3)

---

## 0. Resolution, added the same day — read this first

**The blocking question in §4 was answered, and the answer overturns §1's original conclusion.**
This document first read *"the site penalises London City as if it were Heathrow, and 2,007
postcodes DEFRA maps below WHO's guideline are shown at ~2.5/10"*. **That is retracted as evidence
of a site defect.** The measurements below are all correct; the inference drawn from them was not.

**DEFRA Round 4 maps the situation during 2021, and DEFRA's own Noise Action Plan documentation
describes the result as *"a highly anomalous situation"* influenced by COVID travel restrictions.**
Major airports were even *designated* on the basis of exceeding 50,000 movements **during 2021**.

For London City specifically (CAA / airport statistics):

| year | aircraft movements |
|---|---|
| 2019 | **80,751** |
| 2020 | 18,850 |
| **2021 (the mapped year)** | **12,921** |
| 2022 | 44,731 |
| 2023 | 52,101 |

2021 traffic was **16% of 2019**. Sound energy sums logarithmically, so
`10·log10(12,921 / 80,751)` = **−8.0 dB**. **DEFRA's Round 4 contours understate a normal year at
London City by roughly 8 dB.**

Heathrow was hit far less hard (roughly 449k movements in 2019 against a substantially reduced but
much larger 2021 figure), so its deficit is a few dB at most. **That differential is almost
exactly what the measurement found:**

- measured gap differential, LCY vs LHR: **+4.03 − 1.97 = 2.06 points**
- the v3.6 curve runs 10 points over 18 dB, so 2.06 points ≈ **3.7 dB**
- predicted differential from the traffic figures: **~4–6 dB**

So the LCY/LHR split this document was built on is **substantially or wholly a COVID artefact in
the raster**, not evidence that the site's airport weighting is wrong. **The raster was the
unreliable side, exactly as §4 warned it might be.**

**What survives:** §5's observation stands on its own terms — the airport term really is
distance-only while the heliport term in the same function really is movement-weighted, and that
inconsistency is worth resolving. But **its magnitude is now unmeasured**, because the yardstick
used to size it has been disqualified. Do not cite the 2,007-postcode figure.

**What this cost:** the same mistake the rest of this repo has been correcting all week — a source
was used without checking its vintage. The 2021 reference year was one search away and was not
checked before the finding was written up.

---

## 1. Original conclusion — RETRACTED, see §0

> The consumer site's `quiet` score penalises proximity to **any** airport by distance alone.
> `calc_postcode_quiet` computes `nearest_ap_dist = min(...)` across all five airports and applies
> one distance ladder to the result, so **London City contributes exactly the same penalty as
> Heathrow at the same distance**.

The mechanism above is **correct and confirmed in source**. The inference that it produces a large
live error is what does not survive §0.

---

## 2. What was measured (unchanged, still valid)

All **18,862** live London postcodes with a genuine DEFRA sample, scored both ways using the real
Lambda functions (`lden_db_to_quiet` and `calc_postcode_quiet`), not reimplementations.

| | raster (v3.6 curve) | Haversine (what the site serves) |
|---|---|---|
| mean quiet | **6.33** | **3.25** |

The raster reads quieter for **84.4%** of them; the two agree within ±0.5 for only 11.7%.

| nearest airport | postcodes | mean DEFRA dB | raster quiet | site quiet | mean gap | >2.0 apart |
|---|---|---|---|---|---|---|
| **LCY** | 10,192 | 48.5 | 7.77 | 3.74 | **+4.03** | **65.0%** |
| LHR | 8,670 | 54.7 | 4.65 | 2.68 | +1.97 | 41.3% |

**These numbers are sound.** What changed is their interpretation: the gap measures how much the
2021 contours understate normal traffic, more than it measures a modelling error in the site.

---

## 3. Why the mechanism is still plausible in principle

London City is not a small Heathrow, and under Lden specifically:

- **Fewer movements**, and sound energy sums logarithmically — the reasoning the heliport term in
  this very file already applies.
- **No night flights.** Lden applies a **+10 dB** penalty to the night period, so an airport with
  no night operations gets nothing from the term that dominates Lden around Heathrow.
- **Restricted weekend operation** (closed Saturday afternoon to Sunday morning).
- **Short-field aircraft only**, on a 5.5° approach that keeps arrivals higher than a standard 3°
  glideslope.

None of this is visible to a distance-only ladder. It remains a real design gap; it is simply no
longer quantified.

---

## 4. The blocking fact — ANSWERED

DEFRA's own methodology page does not state a reference year, and says aircraft mapping is carried
out by *"the relevant airport operators and in some cases, the Department for Transport"* rather
than by DEFRA's geospatial model. The answer came from the Round 4 dataset documentation and from
Noise Action Plans adopted under it:

> Round 4 (2022) strategic noise mapping **represents the situation during 2021**. Major airports
> were identified as those exceeding **50,000 aircraft movements per year during 2021**. The
> results *"are influenced by Covid travel restrictions, and as such the results of the 2021
> mapping show **a highly anomalous situation**"*.

Note the second sentence's consequence for this project: **London City recorded 12,921 movements
in 2021 and would not have met the 50,000 threshold.** Whatever contours exist near it in the
Round 4 raster should be treated with corresponding care, including the possibility that they
originate from a different designation or a different source than assumed here.

---

## 5. What is safe to conclude regardless

**The airport term's uniformity is an internal inconsistency in its own right.** The same function
weights heliports by movements on a stated logarithmic derivation and weights airports by distance
alone. That is worth fixing on its own merits — but **not on the strength of this document's
measurements**, and not until there is a yardstick that is not COVID-anomalous.

---

## 6. Options, revised

1. **Do not act on the LCY weighting yet.** The evidence that motivated it has been disqualified.
   Revisit when DEFRA Round 5 (~2027) maps a normal traffic year, or against a non-DEFRA source.
2. **Treat the whole raster as vintage-suspect**, not just around LCY. This is broader than this
   document and is tracked as a separate finding — see `AUDIT_REPORT.md` A-0804-2. It affects the
   quarantine decision, the site's DEFRA contour overlay, and the prototype's published dB values.
3. **Quarantine condition 3 is unchanged**, and is now better justified: the raster should not
   become the API's answer while its inputs are anomalous.

---

## 7. What this does not cover

- **The size of the residual gap after adjustment.** Adding ~8 dB to `E6 5QS` (44.8 → ~52.8 dB)
  gives ~5.7 on the v3.6 curve against the site's 1.0 — so a gap may well remain. That rests on an
  **estimated** adjustment, not a measurement, and is not a basis for changing scores.
- **Which airports Round 4 actually mapped.** Stansted and Luton have no covered postcodes in this
  sample; whether that is genuine absence or non-designation was not checked, and the same question
  now applies to LCY.
- **Gatwick was not examined.** No sampled London postcode had LGW as its nearest airport.
- **The flight-path term was not separated from the airport term.** Both feed `noise_score`.
- **No dose-response validation of the v3.6 curve itself** — see `METHODOLOGY.md` §4.6.
