# Cost of Living: open questions and risks

> Draft, 2026-11-03. Each item: what is open, why it matters, and a suggested way to resolve it. Ordered roughly by
> how much it can block v1. UNVERIFIED marks a claim not confirmed from a primary source.

## Licences and access

1. **Fuel Finder's data licence is not stated.** The GOV.UK guidance ("Access the latest fuel prices and forecourt
   data via API or email", 2 February 2026) carries only GOV.UK's site footer (OGL v3.0 for "content"), which may
   not cover the data feed; the developer portal (developer.fuel-finder.service.gov.uk) refused a connection from
   this session (SSL handshake failure), so its terms were not read. The guidance names VE3 Global Limited as the
   scheme's operator under the Motor Fuel Price (Open Data) Regulations 2025. **Resolve:** the founder opens the
   portal in a browser and pastes its terms; if silent on commercial reuse of derived figures (a local median
   price), ask DESNZ in writing before shipping the fuel line. Fuel is optional, so this does not block v1.
2. **The Minimum Income Standard has no stated licence.** Loughborough University's "Using MIS data" page invites
   organisations to get in touch and states no terms; MIS reports carry non-commercial reproduction notices; Trust
   for London's thresholds page shows only its copyright. **Resolve:** write to CRSP's MIS data contact (on that
   page) describing the B2B API use; until answered, use MIS only as an internal validation yardstick, never
   published. If refused, the grocery range needs another floor (open question 6).
3. **Geolytix Retail Points' terms live in the download.** The blog says "unrestricted use, no licensing
   requirements and without cost" and asks for (does not require) acknowledgement. **Resolve:** read the user guide
   in the 2026 Q1 zip, quote it in LICENSING.md, credit Geolytix anyway.
4. **OpenStreetMap as the store-location alternative carries ODbL share-alike.** A table of nearest-store distances
   per postcode would likely be a Derivative Database, and LICENSING.md records that the healthcare input chose NHS
   ODS over OSM "to keep the score clear of ODbL share-alike". **Resolve:** prefer Geolytix; use OSM only for
   display, as the `/nhs` lookups do, never in a published derived table.
5. **TfL's licence is OGL v2.0 with TfL's amendments and can change without notice.** It requires "Powered by TfL
   Open Data", caps 500 calls a minute per feed, bars implying TfL endorsement and bars using data from the Oyster
   website. **Fares are not an open data feed**; the Single Fare Finder prices one station pair per call, and caps and
   Travelcards are not in the API (TfL tech forum threads, UNVERIFIED against documentation). **Resolve:** read the
   Unified API documentation for the fare and zone fields; source caps and Travelcards from TfL's published fares
   document, held by a builder whose `--check` re-reads that document; record in LICENSING.md that TfL can revoke.
6. **No open source gives food spending by household type in the latest edition.** ONS Family Spending FYE 2025's
   workbook 4 has no one-adult vs two-adult split (its tables are by economic activity, income, number working,
   education, socio-economic class, with and without children), and ONS removed tables A9 to A11 for volatility this
   year. **Resolve, in order:** check workbook 3 (regional) and earlier editions for a composition table; check
   DEFRA's Family Food datasets (built on the same survey, per-person spending by household composition: UNVERIFIED);
   failing both, ship groceries as "not yet estimated" rather than invent a split.
7. **Ofgem's reuse terms for cap data are unconfirmed.** The regional rates page shows "(c) Ofgem 2026"; the
   consumption-values decision carries an OGL notice. **Resolve:** read Ofgem's copyright page and the cap
   workbook's notes; London's regional row must come from Ofgem's own table, never a comparison site.

## Data fit

8. **PIPR understates what a household moving in pays.** It is a stock measure ("both new and existing tenancies"),
   a geometric mean of model-predicted prices, and "official statistics in development"; local-authority indices
   carry a 3-month moving average. Relocation firms and HR teams price NEW tenancies. **Resolve:** say so beside
   every rent figure; ask ONS's Housing Market Indices team whether a new-lets series by local
   authority exists or is planned; never substitute listings-site asking rents (the brief rules out scraping
   Rightmove and Zoopla, and their terms forbid it).
9. **The City of London has no PIPR rent.** No row in any month. **Resolve:** withhold the City's total and say why;
   do NOT fill it from the ONS London ad hoc median (a different, non-comparable method). If the renter
   affordability change (integration note) ships, the City takes the price basis and says so.
10. **The ONS London ad hoc release is fragile.** It is an ad hoc publication, not a scheduled statistic; ONS says it
    "should not be compared across time periods or between areas"; the borough sheet is keyed on NAMES; 98 of 329
    postcode districts have no one-bedroom median; the July 2026 window was promised but not found by search on
    2026-11-03. **Resolve:** use only its quartile SHAPE for the range; pin a name-to-ONS-code map once, generated and
    checked like `CITY_LADS`, and fail on any unmatched name; if the release stops, the range hides and the central
    stays.
11. **Council tax band per home is unknown.** The method uses the borough's middle band of one-bedroom flats (VOA
    CTSOP3.0, 31 March 2026). CTSOP's own note warns that tables built with different geography methods "should not
    be compared". **Resolve:** use CTSOP3.0 (local authority) and CTSOP3.1 (LSOA) each on its own terms; measure how
    many LSOAs hold enough one-bedroom flats before choosing a threshold for the local adjustment.
12. **Rooms in shared houses are missing.** Many single renters in London rent a room; PIPR has no room category (the
    ad hoc release does), and in a house in multiple occupation the landlord, not the tenant, may pay council tax
    (gov.uk advises contacting the council). **Resolve:** a third household type in phase 4, with its own council tax
    rule.
13. **Energy is identical across London** (one Ofgem region) and assumes gas heating. Electric-only flats, heat
    networks and bills included in rent are common and undetected. **Resolve:** phase 4 reads the EPC register (main
    fuel, floor area; already proxied by `/epc`) to weight dual-fuel against electric-only per borough or postcode,
    after checking the EPC licence covers that aggregate use.
14. **Fuel suits few London renter households.** Census 2021 TS045 gives car availability per borough (Hounslow: 33,724
    of 102,961 households with no car or van; the London-wide share was not read). Fuel is also a minority of a car's
    cost. **Resolve:** keep fuel off by default; if shown, list what is not included (insurance, parking permit,
    maintenance).

## Geography and mapping

15. **Borough to postcode.** Borough figures apply to every postcode whose NSPL local authority code is that borough's;
    the column carries a year suffix (`lad25cd` -> `lad26cd`): resolve by prefix, never by name. **Resolve:** reuse the
    postcode table's existing resolution; label each line "borough" or "this postcode".
16. **Nearest station needs codes and zones the repo does not hold.** `data/stations.json` has name, coordinates and
    type, no NaPTAN code and no zone; joining TfL zones by station name breaks "Key on ONS codes, never names" in
    spirit. **Resolve:** extend `build_city_stations.py` to keep NaPTAN ATCO codes, then join TfL StopPoint zones by
    code; boundary stations (two zones) take the lower; distance from NSPL's `east1m`/`north1m`, never a bounding box.
17. **Straight-line distance is not walking distance.** **Resolve:** state it; measure on a sample how often the
    nearest station by line differs from the nearest by route before choosing a cut-off.
18. **Westminster's parish.** Table 9 averages Queen's Park's precept across Westminster. **Resolve:** a polygon test
    on the parish boundary (ONS), a one-line adjustment once its precept is read.

## Staleness

19. **Six cadences, from twice a day to yearly.** Cap quarters, the council tax year, the fares year and PIPR months
    all expire. **Resolve:** each data file carries its period and an expiry; each builder's `--check` reds after
    expiry (as `HAVE_YOUR_SAY` `until` does), and the surface hides an expired line rather than showing old figures as
    current; a row per source in `check_data_freshness.py`.
20. **Area pages bake figures.** A monthly PIPR roll means re-running `build_area_pages.py --write` and re-dating 33
    London pages in the sitemap each month. **Resolve:** accept it (the content does change), and add the roll to
    HANDOVER's "every reader has run" step.

## The repo's own gates

21. **`tests/test_public_wording.py` would refuse the layer as briefed.** Measured against the test's code on
    2026-11-03:
    - `PRICE_SHAPE` matches "£<amount> a month" (and per/a year), so "rent £1,589 a month" fails.
    - `test_our_prices_appear_only_on_pricing` refuses ANY £ amount equal to one of our prices read from /pricing (25,
      35, 150, 250, 499, 750, 2,500 on that date), with no allow-list. A cost of £750 or £2,500 would fail by
      coincidence after a data roll, and rounding to £10 does not avoid it.
    - `ADDRESS_SHARE` refuses "N% of households", so a Census car-ownership line worded that way fails.
    - JSON-LD `price` fields outside /pricing fail (`priced_in_json_ld`).
    - Area pages pass today only because they print "£369,881" (an amount, no "a month", not one of our prices).
    **Resolve before any page shows a figure:** a `COST_ALLOWED` list (the cost builder's exact sentence frame, matched
    by path PREFIX since `allowed_for` matches whole paths or `*` only, each with its reason) honoured by both price
    tests; the builder's `--check` holds every cost figure byte-equal to a fresh build, so a typed figure cannot shelter
    under the allowance; never put cost figures in JSON-LD; word Census shares as "of households" only with its own
    allowance and reason.
22. **Provenance has no word for a published charge.** Tariffs, fares and council tax are neither `statistic` nor
    `modelled`. **Resolve:** add one method word (for example `published-rate`) to the vocabulary that
    `backend/tests/test_provenance.py` holds, and new `PROVENANCE_SOURCES` and `PROVENANCE_PERIODS` rows.
23. **"Absence must never render as a measurement."** The tempting fills are all wrong: a 5.0 or zero for a missing
    rent, a London average for the City, the GB cap rate for London. **Resolve:** tests that assert the City's total is
    absent and named, that `EX1 1HS` returns no cost block, and that no part reads `.get(x, 0)`.

## Business and legal

24. **The Constraints.** A monthly living-cost figure is exactly what a conventional lender's affordability check
    wants; the Constraints rule out conventional mortgage lenders and insurers (riba-free) and treat estate and
    letting agents as misaligned. **Resolve:** keep them off the target list for this layer as for the rest; the
    brief's buyers that fit are relocation firms, employer HR, build-to-rent operators, buyer-side proptech, councils,
    charities and journalists. (Separately, METHODOLOGY §9 still lists "mortgage underwriting" and "insurance
    underwriting" as suitable uses, which reads against the Constraints: worth a look in its own right.)
25. **Reliance without insurance.** No professional indemnity policy is held (Constraints). An HR team may set a
    relocation allowance from this figure. **Resolve:** "estimate, not a quote" on every surface and in the API
    response; the liability cap and "no third-party reliance" terms already in legal batch 2 must cover this layer
    before it is sold.
26. **Fairness.** No income enters (§10); Council Tax Reduction and benefits are therefore not applied, and the layer
    never says what a household "can afford". **Resolve:** state it in the methodology (drafted, §11) and in the API's
    field descriptions.
27. **Comparability beyond London.** v1 figures exist for London only; a reader will compare them with other cities'
    affordability scores. **Resolve:** no cost block outside London, and the coverage sentence for the layer names
    London alone until another region is built on the same method. Rent and council tax travel to the other twelve
    regions easily; transport does not (no open fare data outside TfL).
28. **Missing components a buyer will ask for.** Water (supplier areas differ within London), broadband, the TV
    licence, contents insurance, childcare. **Resolve:** list them as not included on every surface; water first in
    phase 4 if supplier boundaries and average bills are openly licensed (UNVERIFIED).
29. **Effort risk.** Two sources (MIS, Fuel Finder) need a licence answer before code, and TfL fares need a builder
    for a document rather than a feed. **Resolve:** start phase 1 with PIPR, council tax and Ofgem (all open, all
    read), which alone give rent and council tax (two of the three parts that vary by borough) plus energy.
