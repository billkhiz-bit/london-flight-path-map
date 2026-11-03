# Cost of Living and the affordability score: feed, beside, or replace?

> Draft, 2026-11-03. Grounded in `backend/lambdas/score/app.py` (`afford_score`, `national_price_bounds`,
> `pool_of`, `PERSONAS`), METHODOLOGY §4.2, §5 and §10, and a measurement made for this note.

## Recommendation, in two sentences

**Sit beside, and replace one input for one view: the monthly cost is published in pounds inside the Affordability
section, never scored; separately, for the `renter` view only, ONS PIPR rent replaces the sold price as
affordability's input (methodology v5.8, a new `affordRent` component).** The total cannot be scored honestly (it
is London-only, household-specific and mostly flat across boroughs), but its rent line is national, varies, and
fixes a real weakness: renters are scored today on what homes SELL for.

## How affordability is computed today

- **Input:** each council area's `avgPrice`, HM Land Registry UK House Price Index (August 2026 vintage), all property
  types.
- **Formula (v5.0):** `afford = clamp((ln(p95) - ln(price)) / (ln(p95) - ln(p5)), 0, 1) x 10`, the percentiles taken
  over the POOL (`pool_of(city)`: the currency unless a city names its own; one pool per US metro). The sterling pool
  is 97 council areas; `national_price_bounds` gives p5 £159,100 and p95 £732,271 at the current vintage (computed
  from the Lambda's registry, 2026-11-03).
- **Within-city standing** is published separately as `context.priceRankInCity`.
- **Weights:** components are the same for every persona; only weights change. `afford` is 0.27 of `balanced`, 0.30
  of `renter`, 0.43 of `firsttime`, 0.14 of `laterlife`.
- **Commitments it carries:** §4.2 "What this is not" (not a price-to-earnings ratio) and §10 (no income or wealth
  input), kept because the customer set includes Sharia-compliant home-finance providers.
- **A trap for any new input:** `afford_score` returns **5.0** when `p95 <= p5` or `price <= 0`. A rent input must
  not inherit that: a missing rent is absent and said so (CLAUDE.md, "Absence must never render as a measurement").

## What was measured for this note

The same log p5-p95 rule applied to **PIPR all-property rents, September 2026**, over the same 97-area pool. Sky
Score's own computation, not a published figure:

| Measure | Result |
|---|---|
| Areas with a PIPR rent | 96 of 97 (the City of London has no row) |
| Rent p5 / p95 across the pool | £698 / £2,709 a month |
| Rank correlation, rent vs sold price (Spearman) | 0.93 across the pool; **0.79 within London** (32 boroughs) |
| Renter affordability moving by more than 1 point if rent replaced price | **32 of 96** areas (6 by more than 2); **11 of 32** London boroughs |
| Largest falls (dearer to rent than prices suggest) | Tower Hamlets 3.2 -> 0.7; Newcastle upon Tyne 8.1 -> 5.9; City of Bristol 4.8 -> 2.6; Manchester 6.9 -> 5.0; Newham 4.2 -> 2.5 |
| Largest rises | Melton 6.1 -> 8.9; Harborough 5.0 -> 7.5; Broadland 5.6 -> 7.8 |
| Annual rent as a share of average price, London (rough: the two describe different stocks of homes) | 3.5% (Richmond upon Thames) to 6.6% (Tower Hamlets) |

So rent and price agree on the broad national order but disagree inside London, where they matter most for a renter:
a borough can be cheap to buy relative to London and dear to rent, and the renter view cannot see it today.

## The three options

**A. Feed the total into `afford`.** Rejected, for six reasons:

1. **The pool rule.** Anchors are per pool (CLAUDE.md: "National anchors are per POOL"). The total exists for London
   only, so London's renter affordability would rest on a different quantity from the other twelve regions' in the
   same sterling pool, and a London score and a Manchester score would stop measuring the same thing: the
   cross-city comparability v5.0 bought (it took 1,619 inverted pairs of 4,371 to zero) would be given up.
2. **Most of it does not vary.** Energy is one Ofgem region for all of London and groceries are a London-wide
   constant; scoring the total is scoring rent plus council tax plus transport with a constant added, which a log
   scale then compresses.
3. **It is per household, and scores are per place.** Two households need two affordability values; personas weight
   components, they do not change them, and nothing in the engine has a household.
4. **It is built on editorial assumptions** (three commute days, low consumption, one-bedroom). METHODOLOGY anchors
   every threshold on a published source; a score that moves when an assumption is edited breaks that.
5. **It churns.** The cap changes quarterly and fares yearly; folding them in moves scores when nothing about the
   place changed, the argument v3.3 used to take growth out (87% of score movement in one refresh).
6. **The pounds are the product.** A 0-10 of a monthly cost throws away the figure a relocation firm or HR team
   actually wants.

**B. Sit beside, unscored.** Right for the total, for the reasons above, but on its own it leaves the renter view
scoring renters on sold prices, which the brief's "deepen, not sit beside" rightly objects to.

**C. Replace part.** Right for ONE part: rent, for the renter view. Rent is the one component with national coverage
(PIPR covers every English and Welsh council area), real spread, an ONS code key, a monthly official source and no
household assumption when taken across all properties, as `avgPrice` is.

## What the recommendation means in the engine (phase 3b)

- **A new component, `affordRent`**, same formula as `afford`, anchored on the pool's PIPR rents (`pool_of`), with its
  own `context.rentRankInCity`. `afford` is untouched for every other persona.
- **`renter` weights** become `{quiet 0.26, afford 0.00, affordRent 0.30, growth 0.00, live 0.30, env 0.14}`; every
  other persona carries `affordRent 0.00`. `?weights=` accepts the new key; rows still sum to 1.00
  (`test_every_persona_sums_to_one`); the published `weights` stays the APPLIED table.
- **Where rent is missing** (the City of London; New York; the Bay Area), a decision for the founder:
  (a) **recommended:** the renter view falls back to the price input and says so, `context.affordBasis: "price"`
  beside `"rent"` elsewhere, the precedent being `context.growthBasis: "nominal"` for New York; or
  (b) the current rule for a missing component, drop and rescale, which removes affordability from every New York
  and Bay Area renter score.
- **Both holders**: PIPR rent in the Lambda registry and `data/borough-extra.json`, held by
  `tests/test_borough_data_parity.py`; the site's engine computes `affordRent` too (`tests/borough-score-parity.mjs`,
  `tests/site-api-parity.mjs`, the persona parity test).
- **Provenance**: an `ons-pipr` source (publisher, dataset, OGL v3.0, method `statistic`, resolution "local
  authority", period the PIPR month) and a `PROVENANCE_PERIODS` row moved by each monthly roll.
- **Notice**: METHODOLOGY's 14-day rule is defined as a move of more than 0.5 "under default weights"; `balanced`
  is unchanged, so the rule does not strictly trigger, and the baked area pages do not move. The renter headline
  moves by up to about 0.76 (Tower Hamlets: 2.52 x 0.30), so give the notice anyway.
- **Version**: v5.8, a CHANGELOG and METHODOLOGY §4.2 / §5.2 entry with the measurement above re-run on the day.

## What stays in the cost layer

Everything in pounds: rent (one-bedroom), council tax, transport, energy, groceries, the optional fuel line, the
total and its range, each with source, period and resolution. It is shown in the same Affordability section as the
score ("how it ranks" and "what it costs"), so to a reader it is one part of the product, not a second product, while
the arithmetic stays separable for an auditor.

## Order

Ship the cost layer (phases 1 to 3) first, then the renter change (3b) as its own methodology version, so each can
be checked and, if needed, rolled back alone.
