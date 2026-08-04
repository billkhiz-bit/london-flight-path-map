# The airport term treats London City like Heathrow

**Date:** 2026-08-04 · **Status:** measured, one blocking fact unresolved, no code change made
**Found by:** measuring the raster/Haversine gap before choosing how to close it (see `METHODOLOGY.md` §4.5, quarantine condition 3)

---

## 1. Conclusion first

The consumer site's `quiet` score penalises proximity to **any** airport by distance alone.
`calc_postcode_quiet` computes `nearest_ap_dist = min(...)` across all five airports and applies
one distance ladder to the result, so **London City contributes exactly the same penalty as
Heathrow at the same distance**.

The same function's **heliport** term *is* movement-weighted, with a derivation in the source:

> *"derived, not chosen: sound energy sums logarithmically, so annual movements…"*
> — `app.py:1485`, weighting Battersea (12,000/yr) against air-ambulance pads (~800/yr)

So the model already knows movements belong in the term. It applies that reasoning to
helicopters and not to aeroplanes.

**What is not yet established** is how large the resulting error is, because the obvious
yardstick — the DEFRA raster — has an unresolved vintage question. See §4. **No code has been
changed.**

---

## 2. What was measured

All **18,862** live London postcodes with a genuine DEFRA sample, scored both ways using the
real Lambda functions (`lden_db_to_quiet` and `calc_postcode_quiet`), not reimplementations.

| | raster (v3.6 curve) | Haversine (what the site serves) |
|---|---|---|
| mean quiet | **6.33** | **3.25** |

The raster reads **quieter** for **84.4%** of them; the two agree within ±0.5 for only 11.7%.

**The gap is not uniform — it is concentrated at one airport:**

| nearest airport | postcodes | mean DEFRA dB | raster quiet | site quiet | mean gap | >2.0 apart |
|---|---|---|---|---|---|---|
| **LCY** | 10,192 | 48.5 | 7.77 | 3.74 | **+4.03** | **65.0%** |
| LHR | 8,670 | 54.7 | 4.65 | 2.68 | +1.97 | 41.3% |

Around Heathrow the two methods broadly track each other — Hounslow approach differs by 0.1, Kew
by 0.1, Bedfont by 0.0. Around London City they do not.

**The sharpest cases**, all within LCY's catchment:

| postcode | DEFRA | km from LCY | raster | site shows |
|---|---|---|---|---|
| `E6 5QT` | 44.8 dB | 0.69 | 10.0 | **1.0** |
| `E6 5QS` | 44.8 dB | 0.73 | 10.0 | **1.0** |
| `E6 5TP` | 41.1 dB | 1.32 | 10.0 | **1.0** |
| `SE28 0FH` | 42.3 dB | 2.15 | 10.0 | **1.0** |
| `E13 8LU` | 43.0 dB | 2.52 | 10.0 | **1.0** |

**2,007 postcodes** in LCY's catchment are mapped by DEFRA at **or below WHO's 45 dB aircraft
guideline** — the threshold below which WHO finds no adverse effect — while the live site scores
them at a mean of **2.5/10**, worst **1.0**. That is Beckton, Silvertown, Custom House,
Thamesmead and Woolwich.

---

## 3. Why the mechanism is plausible

London City is not a small Heathrow. Under Lden specifically:

- **~1/6 the annual movements.** Sound energy sums logarithmically, so an order-of-magnitude
  movement gap is worth roughly 8 dB — which the heliport term in this very file already
  accounts for, and the airport term does not.
- **No night flights.** Lden applies a **+10 dB** penalty to the night period. An airport with no
  night operations gets nothing from the term that dominates Lden around Heathrow.
- **Restricted weekend operation** (closed Saturday afternoon to Sunday morning).
- **Short-field aircraft only** — no widebodies, and a 5.5° approach that keeps arrivals higher
  for longer than a standard 3° glideslope.

Every one of those cuts the same way, and none of them is visible to a distance-only ladder.

---

## 4. The one fact that decides this — UNRESOLVED

**Which side is wrong depends on the DEFRA raster's traffic year, and that is not established.**

`METHODOLOGY.md` §4.1 records Round 4 as *"published 2022, data current as of 2021"*. **2021 was
a COVID-suppressed year for UK aviation, and London City was among the worst affected** — it
closed entirely for part of 2020 and ran far below normal through 2021. If the contours reflect
that traffic, they understate a normal year and **the raster is the unreliable side**.

DEFRA's own methodology page was checked
(`gov.uk/government/publications/strategic-noise-mapping-2022/explaining-the-2022-noise-maps`)
and **does not state a reference year**. It does say aircraft mapping is carried out by *"the
relevant airport operators and in some cases, the Department for Transport"* rather than by
DEFRA's geospatial model — so the answer likely sits with LCY's own Round 4 submission, not with
DEFRA.

**Until that is answered, do not adopt raster values around LCY and do not conclude the site is
wrong by the full margin above.** Erring quiet is the direction this product cannot afford, and
a COVID-year contour is exactly how you would err quiet without noticing.

---

## 5. What is safe to conclude regardless

**The airport term's uniformity is an internal inconsistency in its own right**, and it does not
depend on the vintage question at all. The same function weights heliports by movements, on a
stated logarithmic derivation, and weights airports by distance alone. Whatever the correct
magnitude turns out to be, treating a ~1/6-movement, no-night-flights airport identically to
Heathrow is not defensible on the model's own reasoning.

---

## 6. Options, in the order they should be considered

1. **Resolve the vintage question first.** LCY's Round 4 noise submission, or its published
   contour maps, against a pre-2020 baseline. This is the cheapest step and it gates the rest.
2. **Movement-weight the airport term** the way heliports already are. Defensible independently
   of the raster, but it changes live consumer scores across east and southeast London and must
   land in `index.html` **and** the Lambda together, with a parity test — `index.html` holds its
   own copy of this geometry, and that is exactly how the three-month flight-path divergence
   happened.
3. **Only then** revisit quarantine condition 3 (site/API divergence), because the size of that
   divergence is partly an artefact of this defect rather than a real tier disagreement.

---

## 7. What this does not cover

- **No claim about which airports are mapped in Round 4.** Stansted and Luton have no covered
  postcodes in this sample; whether that is genuine absence or non-submission was not checked.
- **Gatwick was not examined.** No sampled London postcode had LGW as its nearest airport.
- **The flight-path term was not separated from the airport term.** Both feed `noise_score`; this
  analysis attributes the gap to the airport ladder on the strength of the LHR/LCY split, which
  is strong but is not a decomposition.
- **No dose-response validation of the v3.6 curve itself** — that curve is assumed correct here
  and is documented in `METHODOLOGY.md` §4.6.
