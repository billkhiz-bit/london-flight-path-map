# Homepage grid: the prompt given to Google Stitch

Written 2026-10-02. Paste the block below into Stitch (stitch.withgoogle.com)
to generate another round. The copy is the same as `homepage-grid.html`, and
every figure in it is a real one from the product. Nothing here is deployed.

```
Design a desktop homepage for Sky Score, a UK website that tells people how
loud the aircraft are at any address, using official government data.

WHO VISITS AND WHAT THE PAGE MUST DO
Visitors are people about to buy or rent a home, plus the professionals who
advise them. Most arrive not knowing what the site is. Within five seconds the
page must (1) say what the site does, (2) put a postcode search box in front of
them, and (3) show the other ways to use the data. The model is a grid-style
product homepage such as Hometrack's: a clear headline, then cards by product
and by audience. It must feel like a trustworthy data instrument, not a
property portal and not a startup landing page.

LOOK AND FEEL
- Light theme. Page background warm grey #e4e3e0, cards off-white #fafaf9,
  text near-black #141414, secondary text #55554f, one accent: orange #f27d26
  (use it sparingly: the main button, the map pin, one highlighted figure).
- Typefaces: Geist for headings (bold, tight letter-spacing), Inter for body
  text, JetBrains Mono in small uppercase with wide letter-spacing for labels,
  figures and the code sample.
- Square or barely rounded corners, 1px near-black borders on cards, no drop
  shadows, no gradients, no stock photography, no illustrations of people, no
  emoji. Generous white space. Think Ordnance Survey map sheet or an
  engineering datasheet: precise, calm, confident.
- The noise scale is the one place with many colours. Use this exact ramp,
  quiet to loud, in 5 decibel steps from 40 to 80: #B8D6D1, #CEE4CC, #E2F2BF,
  #F3C683, #E87E4D, #CD463E, #A11A4D, #75085C, #430A4A. These are the UK
  government's own map colours, so do not change them.

SECTION 1: TOP BAR
Left: wordmark "SKY SCORE" in spaced uppercase mono. Right: links Map,
Reports, API, Open data, Pricing.

SECTION 2: HERO (two columns)
Left column:
- Small label: "AIRCRAFT NOISE, AIR AND FLOOD RISK, BY POSTCODE"
- Headline, very large: "How loud are the planes where you want to live?"
- One sentence: "Type a postcode. You get the official noise, air quality and
  flood figures for that street, the flight routes that pass it, and the name
  of the public body behind every number."
- A large postcode input with an orange "Check" button attached. This is the
  most prominent control on the page.
- Under it, a row of small example chips labelled "Try": TW9 3PZ, SW11 1AA,
  B33 0YS, M22 5RX.
Right column:
- A flat, abstract map of west London: pale borough outlines, two long thin
  coloured noise lobes running east from Heathrow in the ramp above, two thin
  straight approach lines along them, and one orange pin labelled
  "TW9 3PZ  57 dB". No street detail, no satellite imagery.
- Under the map, a horizontal noise ruler in the ramp colours from 40 to 80
  decibels, with a tick marked "World Health Organization guideline: 45" and
  the pin's 57 marked on it.

SECTION 3: "ONE SET OF OFFICIAL FIGURES, HOWEVER YOU NEED IT"
A grid of six cards, three across and two down. The first card is larger or
visually stronger than the rest. Each card has a small mono label, a heading,
one or two lines of text, one concrete piece of content, and a text link.
1. THE MAP: "See a whole city at once". Every borough, with flight routes,
   aircraft and road noise, air quality and flood risk. Free, nothing to sign
   up for. Content: city names as small chips (London, Greater Manchester,
   West Midlands, West Yorkshire, Merseyside, Tyne and Wear, Bristol, New
   York). Link: "Open the map".
2. THE REPORT: "One page on one postcode". Content: four figures in a list:
   "57 dB aircraft noise, against a guideline of 45", "0.1 km from Heathrow's
   northern approach", "1,800 ft height of landing aircraft there", "61% of
   TW9 postcodes are quieter". Link: "See the sample".
3. THE API: "The same figures, in your own system". Content: a small code
   block: GET /v1/score?postcode=SW11+1AA returning { "score": 5.1,
   "quiet": 6.4, "sources": [ ... ] }. Line: "10,000 lookups a month free."
   Link: "Read the docs".
4. FOR RESIDENTS' GROUPS: "A free summary for your streets". Content: a pull
   quote: "Earl's Court: nitrogen dioxide is 2.4 times the WHO guideline."
   Link: "Ask for one".
5. OPEN DATA: "Every council area in one file". Content: a tiny table with
   columns borough, score, quiet, env and rows Camden 5.4 10.0 4.9; Hounslow
   3.4 0.0 6.5; Norwich 6.0 5.0 7.5. Link: "Download the CSV".
6. HOW IT IS CHECKED: "Every number goes back to its source". Content: four
   ticked lines: prices compared with HM Land Registry; crime compared with
   the Office for National Statistics; flood compared with the Environment
   Agency's own map; routes drawn from the official aeronautical publications.
   Link: "Read the method".

SECTION 4: "WHO IT HELPS"
A row of six compact items, each a bold name and one line:
- Buying or renting: check a street before a viewing.
- Buying agents and relocation firms: a sourced one-page answer for a client.
- Residents' groups: start a bid or consultation response from the official
  baseline.
- Islamic home finance: environmental checks on an address.
- Conveyancers and surveyors: add aircraft noise to the reports you produce.
- Researchers and journalists: rank and compare areas from one open file.

SECTION 5: FOOTER
One line: "All figures from open government data. Sky Score is run by
Cubitt33 Ltd." Links: Privacy, Terms, Method.

RULES
- Use the copy above word for word. Do not invent statistics, testimonials,
  customer logos, star ratings or awards.
- EVERY word on the page must come from this brief. Add no label, tag,
  caption, scale, date, organisation name, version code or copyright line of
  your own. The first run invented "UK FLIGHT METRICS", "CAA", "LAeq 16h",
  "Scale 1:50,000", "Ordnance Survey", "2024", "address lookup" and "User case
  01": none of those is true of this product, so none may appear.
- The noise unit is written "dB Lden" and nothing else.
- The wordmark is exactly "SKY SCORE". The top bar has exactly five links.
- British English spelling.
- The postcode search must stay the first thing the eye lands on after the
  headline.
```

## What to ask Stitch for next

- "Make the hero map fill the full width behind the headline and search box."
- "Show the same page at phone width, with the search box above the map."
- "Give three layout variants of the six-card grid."
