# Sky Score Cost of Living: methodology (DRAFT)

> Draft 0.1, written 2026-11-03. **Nothing here is built or published.** It is the proposed method for an estimated
> monthly cost of living in London's boroughs, written to sit as a new section of `METHODOLOGY.md` (after §4.8) once
> built. Every figure below carries its source; figures marked *illustrative* use inputs the build will replace.
> Unverified claims are marked UNVERIFIED.

---

## Contents

1. [What it is, and what it is not](#1-what-it-is-and-what-it-is-not)
2. [Coverage](#2-coverage)
3. [The two households](#3-the-two-households)
4. [Component formulas](#4-component-formulas)
   - 4.1 Rent
   - 4.2 Council tax
   - 4.3 Transport
   - 4.4 Energy
   - 4.5 Groceries
   - 4.6 Fuel (only with a car)
   - 4.7 The total and its range
5. [Borough-level and postcode-level parts](#5-borough-level-and-postcode-level-parts)
6. [Worked example: Hounslow](#6-worked-example-hounslow)
7. [Data sources and licences](#7-data-sources-and-licences)
8. [Update schedule and staleness](#8-update-schedule-and-staleness)
9. [Limitations](#9-limitations)
10. [What is not included](#10-what-is-not-included)
11. [Fairness](#11-fairness)
12. [Validation](#12-validation)
13. [Changelog](#13-changelog)

---

## 1. What it is, and what it is not

The Cost of Living estimate is the **monthly cost of a stated household living in a London borough**, built from
published charges and official statistics, each line traced to a named source and a stated assumption. It answers
the second half of "is it pleasant, and what will it actually cost me?", beside the five scores.

It **is**:

- an estimate in pounds a month, with a range wherever the inputs are uncertain;
- a sum of six named parts, each shown, so a reader can replace any assumption with their own;
- borough-level for rent and council tax, postcode-level for transport and the nearest discount supermarket, and
  London-wide for energy and groceries. Every part says which.

It **is not**:

- a quote, an offer, or what any particular home will cost. A landlord's asking rent, a home's actual council tax
  band and a household's own energy use can each fall outside the range;
- a score. It is never folded into the 0-10 components; see the integration note for why, and for the one narrower
  change proposed instead (rent as the renter view's affordability input);
- a measure of anyone's income or what they can afford. §11 explains why income never enters it.

## 2. Coverage

London's 33 boroughs (ONS codes E09000001 to E09000033). **The City of London has no ONS PIPR rent** (no row in any
month of the 21 October 2026 edition), so its rent is shown as not published and **its total is withheld**; every
other part is still shown. Postcodes outside London get no estimate and no zero.

## 3. The two households

| Household | Who | Home assumed | Why that home |
|---|---|---|---|
| `single` | One working-age adult renting privately | A self-contained one-bedroom home | The Local Housing Allowance size criteria allow one bedroom for a single adult or a couple (UNVERIFIED wording here; the rule is in the Housing Benefit Regulations' size criteria and must be quoted from source before publishing) |
| `couple` | Two working-age adults, no children, renting privately | The same one-bedroom home | As above |

Both are assumed to commute (§4.3), heat with mains gas (§4.4), and pay by Direct Debit. A room in a shared house
is the commonest single renter's home in much of London and is not modelled in v1 (§10).

## 4. Component formulas

### 4.1 Rent

```
rent_central = PIPR "Rental price one bed" for the borough's ONS code, latest month
rent_low     = rent_central x (LQ / median)     one-bedroom, same borough, ONS London ad hoc
rent_high    = rent_central x (UQ / median)
```

**Central.** ONS's Price Index of Private Rents publishes a £ level per local authority per month, by bedrooms. It
is the only rent source built to be compared between areas: it adjusts for the mix of homes (a hedonic model).
**Range.** ONS's ad hoc "Private rental market in London" (VOA rent officers' data, 12 months) gives each borough's
lower quartile, median and upper quartile of recorded one-bedroom rents. Its LEVELS are not used: ONS says they are
"not comparable" with PIPR and "should not be compared across time periods or between areas". Only the SHAPE of the
spread (the two ratios) is borrowed, so the range says how far ordinary one-bedroom rents in that borough sit either
side of the middle. This is a Sky Score derivation and is labelled as one. Where the ad hoc release suppresses the
borough's one-bedroom quartiles, the central figure is shown with "range not published".

**Why PIPR understates what a mover pays.** PIPR is a STOCK measure: it covers "both new and existing tenancies",
and existing tenancies lag the market. A household moving in pays a new-let rent, usually higher. v1 says so beside
every rent figure ("the average rent paid by current tenants, ONS; a new tenancy usually costs more"). Measuring the
gap needs a new-let source; none open is known (§9).

### 4.2 Council tax

```
band_central = the middle band of one-bedroom flats in the borough        (VOA CTSOP3.0)
band_low     = the band at the 25th percentile of those flats
band_high    = the band at the 75th percentile
annual(b)    = MHCLG Table 9, area council tax for band b, the borough's ONS code, the current year
monthly      = annual(b) x occupancy / 12      occupancy = 0.75 single, 1.00 couple
```

Table 9 gives the charge for every band, per billing authority, for a dwelling occupied by two adults, including
parish and adult social care precepts. **Local adjustment:** where a postcode's LSOA (from NSPL) holds enough
one-bedroom flats in CTSOP3.1, its own middle band replaces the borough's (threshold to be measured, not chosen in
advance). The 25% single person discount is statutory ("You'll get 25% off your bill if you pay Council Tax and
either: you live on your own, or everyone else in your home is disregarded", gov.uk). Divided by 12, not by the
10 default instalments, because the estimate is a monthly budget over a year. Council Tax Reduction (means-tested)
is not applied: it needs an income (§11).

**Westminster.** Table 9 is the area AVERAGE, and Westminster contains a parish (Queen's Park; believed to be
London's only one, UNVERIFIED), so a Queen's Park postcode pays slightly more than the figure shown (the precept's
size is not yet read). Its boundary is a polygon test, never a bounding box.

### 4.3 Transport

```
zone        = the fare zone of the nearest rail, Underground, Overground, DLR or Elizabeth line station to the
              postcode (straight line, NaPTAN point; a station in two zones takes the lower)
day_cost    = min(daily cap Zones 1-zone, 2 x peak single Zones 1-zone)
pattern     = days a week each adult travels to Zone 1          central 3, low 2, high 5
month_payg  = min(pattern x day_cost, weekly cap Zones 1-zone) x 52 / 12
monthly     = min(month_payg, monthly Travelcard Zones 1-zone) x adults
```

Where no station is within 1,200 m (to be measured; a choice, not a published threshold), the bus and tram cap is
used instead. **Every fare is TfL's published adult fare for the current fares year**, held in one file built from
TfL's own fares document and checked against it; no figure is typed into a page. **Why a pattern and not one
commute:** the cost depends on where and how often a household travels, which an area cannot know; three days a
week is an assumption (UNVERIFIED: no source chosen yet for hybrid working; ONS's Opinions and Lifestyle Survey is
the candidate), so the range runs from two days to five. **No fares are quoted in this draft**: the figures found
on 2026-11-03 came from secondary sites and disagreed.

### 4.4 Energy

```
annual = E_kWh x e_unit + 365 x e_standing + G_kWh x g_unit + 365 x g_standing
monthly = annual / 12
central: Ofgem low TDCV     E = 1,600 kWh, G = 6,000 kWh
high:    Ofgem medium TDCV  E = 2,500 kWh, G = 9,500 kWh
low:     = central
rates:   Ofgem price cap, London region, Direct Debit, the quarter in force
```

Ofgem's typical domestic consumption values from 1 July 2026 (decision of 27 May 2026): electricity single-rate
1,600 / 2,500 / 3,800 kWh a year and gas 6,000 / 9,500 / 14,000 kWh a year (low / medium / high). **The mapping of
a one-bedroom home to "low" is a Sky Score assumption**; Ofgem's values describe consumption levels, not
households. Annualising one quarter's cap rate is the convention Ofgem's own "typical annual bill" uses. **Check
the formula reproduces Ofgem:** at the England, Scotland and Wales average Direct Debit rates for 1 October to 31
December 2026 (electricity 26.32p/kWh, 54.83p a day; gas 7.97p/kWh, 29.68p a day), medium consumption gives
£1,723.61 a year; Ofgem's headline is £1,723. **London is one Ofgem region**, so this part is the same for every
borough.

### 4.5 Groceries

```
monthly_central = weekly food and non-alcoholic drinks spend for the household type x 52 / 12
range           = from a minimum budget (MIS, if licensed) to the average spend (ONS Family Spending)
```

**There is no official cost of a basket.** ONS Family Spending reports what households SPEND on average (a mean,
from about 5,000 households, FYE 2025); the Minimum Income Standard reports what a household NEEDS for a minimum
socially acceptable standard. A range between the two is honest; either alone is not. **Not yet settled:** FYE
2025's workbook 4 does not split food spending by household composition (its nearest table, A57, gives households
without children, £61.60 a week, UK, FYE 2023 to FYE 2025 pooled), and MIS has no stated licence. Until both are
answered (open questions), this part is shown as "not yet estimated", never filled.

**The nearest discount supermarket** (Geolytix Retail Points, "Discounters": Aldi and Lidl) is shown beside the
groceries line as a distance from the postcode. **It never changes the £ figure:** no open source prices a basket
per store, and turning a distance into pounds would publish a number nobody measured.

### 4.6 Fuel (only with a car)

Off by default for both households. With a car:

```
monthly = (annual miles / 12) x litres per mile x local E10 price
local E10 price = median price at forecourts within 3 km, averaged over the last 28 days    (Fuel Finder)
```

Mileage and fuel economy need published sources (the Department for Transport's National Travel Survey is the
candidate: UNVERIFIED). The page says that fuel is a minority of a car's cost and that insurance, parking permits
and maintenance are not included. Fuel Finder's data licence is unread (open questions), so this part ships only
after it is.

### 4.7 The total and its range

```
total_central = sum of central parts present
total_low     = sum of lows       total_high = sum of highs
```

Summing every low and every high treats the parts as moving together, which makes the range WIDER than a
statistical interval would be: the cautious side for an estimate that must never read as a quote. Displayed to the
nearest £10; computed unrounded. **The total is withheld if rent is missing** (rent is most of it); with any other
part missing, the total is shown with the missing part named ("excludes groceries: not yet estimated").

## 5. Borough-level and postcode-level parts

| Part | Resolution | From the postcode by |
|---|---|---|
| Rent | Borough (local authority) | NSPL's local authority code (resolve the column by prefix: `lad25cd` then `lad26cd`) |
| Council tax charge | Borough | The same |
| Council tax band | Borough, or the postcode's LSOA where enough flats are counted | NSPL's LSOA code |
| Transport | Postcode | The nearest station by distance from the postcode's NSPL grid reference (`east1m`/`north1m`), never a bounding box |
| Energy | Ofgem region (all of London) | None |
| Groceries | London-wide | None; the discount store distance is postcode-level |
| Fuel | Postcode (forecourts within 3 km) | Distance from the grid reference |

Every API field carries its `resolution` in its provenance, and every page line says "borough" or "this postcode".

## 6. Worked example: Hounslow

Hounslow (E09000018), a single renter. Rent and council tax use the real 2026 inputs; energy is *illustrative* (the
average Great Britain cap rate, which London's regional rate replaces in the build); transport and groceries are not
yet estimable (§4.3, §4.5), so this is a subtotal, not the total.

**Step 1, rent.** PIPR, September 2026, Hounslow one bed: **£1,589**. ONS London ad hoc, April 2025 to March 2026,
Hounslow one bedroom: lower quartile £1,350, median £1,550, upper quartile £1,739, so the ratios are 0.871 and
1.122. Range **£1,384 to £1,783**.

**Step 2, council tax.** VOA CTSOP3.0 (31 March 2026): Hounslow holds 23,670 one-bedroom flats; the 25th percentile
band is B, the median C, the 75th percentile C. MHCLG Table 9, 2026-27: band B £1,699.88, band C £1,942.72 a year.
Single: x 0.75 / 12 = **£121.42** a month (central, band C), **£106.24** (low, band B), £121.42 (high).

**Step 3, energy (illustrative).** Low: 1,600 x 26.32p + 365 x 54.83p + 6,000 x 7.97p + 365 x 29.68p = £1,207.78
a year, **£100.65** a month. Medium (high end): £1,723.61 a year, **£143.63** a month.

**Subtotal (rent, council tax, energy):** central £1,811.07, range £1,590.86 to £2,047.81; displayed **£1,810
(£1,590 to £2,050)**. The couple: council tax at x 1.00 (£161.89 central, £141.66 low), so **£1,850 (£1,630 to
£2,090)**.

A blocking gate re-derives this example from the source files on every commit, as `check_worked_example.py` does
for §6 of METHODOLOGY.

## 7. Data sources and licences

| Source | Publisher | Dataset | Geography | Cadence | Licence | Access |
|---|---|---|---|---|---|---|
| Rent, central | Office for National Statistics | Price Index of Private Rents, UK: monthly price statistics (official statistics in development) | Local authority (England, Wales); BRMA (Scotland, Northern Ireland) | Monthly | OGL v3.0 | xlsx download |
| Rent, range | Office for National Statistics, from Valuation Office Agency data | Private rental market in London (ad hoc, e.g. ref 3389, April 2025 to March 2026) | Borough (by NAME), postcode district | Quarterly, rolling 12 months, unscheduled | OGL v3.0 | xlsx download |
| Council tax charge | Ministry of Housing, Communities and Local Government | Council Tax levels set by local authorities in England 2026 to 2027, Table 9 | Billing authority (ONS code) | Annual, March | OGL v3.0 | ODS download |
| Council tax band | Valuation Office Agency (HM Revenue & Customs) | Council Tax: stock of properties, 2026 (CTSOP3.0, 3.1) | Local authority; LSOA | Annual, September | OGL v3.0 | ODS, zip |
| Single person discount | GOV.UK | Council Tax: who has to pay | England | Statute | OGL v3.0 | Page |
| Fares, zones | Transport for London | Unified API (StopPoint, Single Fare Finder); the published fares document | Station | Annual (fares year) | OGL v2.0 with TfL's amendments; "Powered by TfL Open Data" | API key; document |
| Energy rates | Ofgem | Energy price cap, unit rates and standing charges by region | Ofgem region | Quarterly | "(c) Ofgem 2026"; reuse terms to confirm | Page, workbook |
| Energy use | Ofgem | Review of typical domestic consumption values: decision (27 May 2026) | Great Britain | Occasional | OGL (the document's own notice) | PDF |
| Groceries, average | Office for National Statistics | Family spending in the UK, FYE 2025, workbooks 3 and 4 | UK; region | Annual, June | OGL v3.0 | xlsx |
| Groceries, minimum | Loughborough University CRSP, Joseph Rowntree Foundation; Trust for London (London) | Minimum Income Standard | UK; inner and outer London | Annual | **Not stated; permission needed** | Reports; data on request |
| Discount stores | Geolytix | Supermarket Retail Points | Store point | Quarterly | "unrestricted use, no licensing requirements"; user guide terms unread | zip download |
| Fuel | Department for Energy Security and Net Zero (operated by VE3 Global Limited) | Fuel Finder | Forecourt point | Prices within 30 minutes; CSV twice a day | **UNVERIFIED** | CSV by email; API (GOV.UK One Login, OAuth 2.0) |

Attribution follows each publisher's wording, word for word, held in the data file and checked by its builder (the
pattern AURN and Breathe London use).

## 8. Update schedule and staleness

| Part | Rolls when | A file is stale when | Then |
|---|---|---|---|
| Rent (PIPR) | Each monthly edition | Its month is more than 75 days old | Shown with its month; `--check` reports the newer edition |
| Rent range (ad hoc) | Each quarterly window | Its window ended more than 15 months ago | Range hidden, central kept |
| Council tax | Each April (tables published in March) | After 31 March of its year | `--check` reds; the line hides until rolled |
| Transport | Each fares change (usually March) | After a newer TfL fares document's effective date | `--check` reds |
| Energy | Each cap quarter | After the quarter's last day | `--check` reds (as `HAVE_YOUR_SAY` `until` does); the line hides |
| Groceries | Each June (Family Spending) | 18 months after its survey year ends | Shown with its year |
| Discount stores | Each Geolytix quarter | Two quarters behind | Distance hidden |
| Fuel | Weekly, from the twice-daily CSV | More than 14 days without a fetch | Line hidden |

A roll is done only when every reader has run: the JSON, the Lambda's copy, the area pages
(`build_area_pages.py --write`), then the drift check.

## 9. Limitations

- **Rent is an average paid by current tenants, not a new-let price**, and a geometric mean of model-predicted
  prices. ONS's local-authority indices are smoothed by a 3-month moving average, so a sudden change reaches the
  figure late.
- **One-bedroom only.** A single renter in a shared house pays less; a couple wanting two bedrooms more.
- **Energy assumes gas heating and Direct Debit.** Electric-only flats, heat networks, prepayment and standard credit
  all cost differently; bills included in rent are common and are not detected.
- **Energy and groceries do not vary across London**, so differences between boroughs come almost entirely from rent,
  council tax and transport. The page says so.
- **Transport assumes a Zone 1 commute** at a stated pattern; a household working locally or cycling pays less.
- **The council tax band is the borough's typical band for one-bedroom flats**, not the home's own band, which the
  VOA's public band search would give for a specific address.
- **London-only**: never compared with another city's figures until those exist on the same method.

## 10. What is not included

Water and sewerage (varies by supplier area within London: a phase 4 candidate), broadband and mobile, the TV
licence, contents insurance, childcare, clothing, leisure, savings, tenancy deposits and moving costs. The page
lists them, so the total is never read as everything.

## 11. Fairness

No income, wealth or benefit entitlement enters any part, consistent with §10 of METHODOLOGY ("Income or wealth
distributions of residents" are never inputs). That is why Council Tax Reduction, Housing Benefit and Universal
Credit are not applied, and why the estimate never says what a household "can afford": both need an income. The
estimate describes costs of a place for a stated household; who lives there is not an input.

## 12. Validation

- **Reproduce Ofgem**: the energy formula at medium consumption must equal Ofgem's headline typical bill for the
  quarter to within £1 (2026-11-03: £1,723.61 against £1,723).
- **Below the minimum budget's non-housing total**: transport, energy and groceries together must sit below the
  Minimum Income Standard for London's after-housing-costs budget for the same household (2026: single £395 a week
  inner, £408 outer; couple £662 inner, £687 outer; Trust for London, April 2025 prices), because MIS covers more
  items. A borough above it is a defect to explain.
- **Rent against the ad hoc medians**: not a test (ONS says the two are not comparable), but a borough where PIPR
  and the ad hoc median differ by more than a third is listed for reading before each roll.
- Each builder's `--check` proven red on the defect it exists for, before it is trusted green.

## 13. Changelog

- **0.1, 2026-11-03**: draft. Sources read on their own pages; PIPR, the ONS London ad hoc, MHCLG Table 9, VOA
  CTSOP3.0 and Family Spending workbook 4 opened and read; Fuel Finder's developer terms not reachable.
