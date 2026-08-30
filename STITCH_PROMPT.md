# Google Stitch prompt — Sky Score mobile

**Status:** the Stitch MCP server is connected in this session (`mcp__stitch__*`:
`create_project`, `generate_screen_from_text`, `generate_variants`,
`create_design_system`, `edit_screens`). Ask and I can run these directly rather
than you pasting into stitch.withgoogle.com.

**Use it for:** exploring alternative mobile layouts and visual direction.
**Do not use it for:** anything that states a number or a data source. Every
figure Sky Score prints is derived from a named public dataset, and a generated
mockup inventing plausible ones is the exact failure this repo keeps auditing
itself for. Treat all values in Stitch output as lorem ipsum.

---

## Design system prompt (run first)

> Create a design system called "Sky Score" for a UK property data app.
>
> Palette — warm neutral, not a typical SaaS blue:
> - Page background `#e4e3e0` (warm grey), card surface `#fafaf9` (off-white)
> - Primary text `#141414`, secondary text `#636363`, hairline borders `#c8c7c4`
> - Accent orange `#f27d26` — **fills, borders and swatches only, never text**
> - Orange as ink `#a85416` — the only orange allowed to carry a word
> - Data bands: green `#0a7a3e`, amber `#8e6b00`, blue `#267df2`
>
> Every colour pairing must reach WCAG AA 4.5:1 for text. The accent deliberately
> has two values because the bright one fails contrast; keep that split.
>
> Typography: one grotesque sans. Numbers are the loudest thing on screen —
> scores set large and tabular. Labels are small, uppercase, wide-tracked.
> Corners 8px. Flat — one hairline border, no drop shadows, no gradients.
>
> Tone: an instrument panel, not a marketing page. Sober, dense, legible in
> sunlight. Closer to a surveyor's report than a property portal.

## Screen prompts

**1 — Search (map-led home)**

> A mobile screen for a UK property data app. A muted map of a city fills the
> whole background, boroughs drawn as thin outlines with a translucent colour
> fill. Floating over it near the top: a compact search field reading "Enter a
> postcode or area". Above that, two tiers of small pill chips — a row of country
> tabs, then a horizontally scrolling row of city chips with one selected. Bottom
> of the screen: a fixed 3-tab bar labelled Search, Rankings, Saved, with simple
> line icons. Between the search field and the tab bar, a small card peeking up
> from the bottom edge, about a fifth of the screen tall, hinting it can be
> dragged up. The map must stay the dominant element — at least two thirds of the
> screen visible.

**2 — Score result**

> A mobile result screen. At the very top, before any explanation, a large
> headline score out of 10 with a one-word verdict beside it. Directly beneath,
> four labelled component bars — Quiet Skies, Affordability, Liveability,
> Environment — each a horizontal track with a filled portion and its own score.
> Below the fold, collapsed disclosure rows for methodology and data sources.
> No hero image, no marketing copy above the number.

**3 — Borough detail panel**

> A mobile bottom sheet expanded over a map. Header: place name, and a score
> chip. Body: a vertical stack of measurement rows. Each row has a small
> uppercase label, a value with its unit, and a thin horizontal scale bar with a
> tick mark showing a published guideline threshold. Some rows show a short
> italic caveat line instead of a value, reading "not measured here". Below,
> a collapsed section listing nearest stations with distances. A drag handle at
> the top of the sheet.

**4 — Rankings**

> A mobile ranked list. Numbered rows, each with an area name, a small grey
> secondary line beneath it, a right-aligned score, and a thin colour bar. Above
> the list, a filter row of small pill toggles. At the very top a short italic
> disclosure sentence in muted grey, styled as a caveat rather than a heading.

## Constraints to repeat in every screen prompt

1. **Missing data is shown as missing.** Where a value is absent, the mockup must
   show an explicit "not measured" state — never a zero, a dash, or a mid-range
   default. This app has shipped that defect five times; the design must make the
   honest state the easy one.
2. **Direction follows the label.** A row labelled with a good thing (Quiet
   Skies) fills right as it improves. A row labelled with a bad thing (Road
   noise) fills right as it worsens. Do not harmonise them.
3. **Map is the landing surface on mobile**, not a thumbnail under a form.
4. **Nothing may sit under the tab bar or over the top chrome** — controls need
   clear bands.

## After Stitch

Stitch output is direction, not markup. Anything adopted has to come back through
the real gates: `tests/responsive.mjs` (10 viewports, overflow + stranded +
covered + clipped-above), `tests/a11y-source.mjs` (WCAG over source), and
`tests/map-fit.mjs` (90 city/viewport combinations). The mobile tab layout is
gated on `.is-tabbed`; see `MOBILE_REDESIGN_PLAN.md` v3.

---

# Desktop prompts (brainstorm)

Today's desktop is a fixed two-column grid — `1fr 400px`, map left, a 400px
sidebar right holding search plus three tabs (Analysis, Rankings, Saved). The
prompts below deliberately include one that reproduces it and two that break it,
because the point of the exercise is to see whether the sidebar is the right
container at all. Same design system as above; same four constraints.

**D1 — The current shape, done well**

> A desktop web app for UK property noise and liveability data, 1440px wide. Left
> two thirds: a large muted map of a city region, boroughs as thin outlines with
> translucent colour fills, a compact legend card bottom-left and a small column
> of round map controls top-right. Right third, a fixed 400px panel on an
> off-white surface: a search field at the top, then three text tabs — Analysis,
> Rankings, Saved — then a scrolling result area showing a large score out of 10
> with four labelled component bars beneath it. Warm grey background, flat
> hairline borders, no shadows. Dense and instrument-like.

**D2 — Three columns: map centre, comparison rail right**

> A desktop data application, 1440px wide, three columns. Narrow left rail: a
> vertical list of city names with one selected, and beneath it a stack of small
> layer toggles with colour swatches. Wide centre column: a large map filling the
> full height. Right column ~360px: two area cards stacked vertically, each
> showing a place name, a score out of 10, and four small component bars, laid
> out so the two cards' rows line up horizontally for comparison. A thin toolbar
> across the top with a search field and a data-vintage label.

**D3 — Dashboard, map demoted to one panel among several**

> A desktop analytics dashboard, 1440px wide, on a warm grey background. A row of
> four stat cards across the top, each with a small uppercase label, a large
> number, and a thin scale bar with a guideline tick. Below, a two-column region:
> left, a map panel roughly square with boroughs shaded by value; right, a ranked
> table of areas with a score column and a thin colour bar per row. Beneath both,
> a full-width panel of small multiples — nine tiny charts in a grid, each
> labelled. Flat cards, hairline borders, no shadows.

**D4 — Split comparison, no map at rest**

> A desktop screen for comparing two places side by side. Full-width header with
> two search fields separated by the word "vs". Below, two identical columns,
> each showing a place name, a large score, and a vertical stack of measurement
> rows — small uppercase label, value with unit, thin scale bar with a guideline
> tick. Rows align across the two columns so differences read horizontally. Where
> one side lacks a measurement, that row shows an explicit "not measured here"
> caveat in muted italic rather than a blank or a zero. A small collapsed map
> thumbnail sits in each column header.

## What to look for in the output

- **Does the 400px sidebar earn its width?** It currently holds search, three
  tabs and a full result. D3 and D4 test whether the result wants the whole page.
- **Where does provenance go on a wide screen?** The legend already carries a
  383px provenance paragraph on mobile, which had to become a disclosure. Desktop
  has room to show it — see if any layout makes that a feature.
- **Comparison is the unbuilt feature.** `?compare=previous` exists in the API and
  `/changes` renders it, but nothing on the site puts two places side by side.
  D2 and D4 are the cheapest way to see whether that is worth building.

Desktop has one gate mobile does not exempt it from: `tests/map-fit.mjs` covers
90 city/viewport combinations, and the projection scale in `CITY_DATA` is fitted
to the **desktop** map box by `fit_city_projection.py`. Any layout that changes
the map container's aspect ratio means refitting all 11 cities, not just editing
CSS.
