/* global extractListing */
// cubitt33 extension — injected panel.
//
// Renders as a FLOATING CARD appended to document.body, deliberately not
// injected into Rightmove's own layout. Two reasons, and both matter:
//
//   1. Resilience. Injecting into their grid means depending on a container
//      class name, and Rightmove's class names are build-hashed — they change
//      without notice. A fixed-position card depends on nothing.
//   2. Posture. We are a guest on someone else's page. Overlaying our own
//      panel, without reflowing or hiding any of their content, is a far more
//      defensible position than restructuring it.
//
// It also does NOT fetch on page load. The user clicks the badge to ask for
// data, which means zero upstream traffic for anyone who ignores it — the
// politest possible relationship with both Rightmove and OSM's Overpass.

const PANEL_ID = 'cubitt33-panel';
const BADGE_ID = 'cubitt33-badge';

// --- Small DOM helpers ---------------------------------------------------
// Everything data-bearing is built with createElement + textContent, never
// innerHTML. This is not stylistic: /nhs proxies OpenStreetMap, which is
// CROWD-EDITED — a facility's `name` tag is arbitrary user-supplied text that
// has travelled through Overpass and our Lambda without ever being treated as
// markup. Interpolating it into innerHTML would be a stored-XSS sink with a
// public edit form at the far end of it.
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function metres(d) {
  if (d === null || d === undefined) return '';
  return d >= 1000 ? `${(d / 1000).toFixed(1)} km` : `${Math.round(d)} m`;
}

/**
 * A collapsed explanation. Added 2026-08-07 because the panel was mostly prose:
 * on a real SW5 listing it showed three measurements carrying a two-sentence
 * coverage notice, a two-sentence DEFRA vintage paragraph and a guideline
 * sub-line each, and outside London it showed ONE measurement under two
 * notices. Caveats that long stop being read, which defeats the point of
 * writing them.
 *
 * What stays visible is the FACT; what collapses is the JUSTIFICATION. "Aircraft
 * noise (estimated)" is in the row label, and DEFRA-sourced rows are tagged
 * with their vintage inline, so a reader who never opens this still cannot
 * mistake an estimate for a measurement or 2021 data for current. What moves in
 * here is why DEFRA covers so little and what the anomalous year means — real
 * and worth keeping, but not worth burying the numbers under.
 */
function disclosure(summaryText, paragraphs) {
  const box = el('details', 'c33-note');
  box.appendChild(el('summary', 'c33-note-sum', summaryText));
  for (const p of paragraphs) box.appendChild(el('p', 'c33-note-body', p));
  return box;
}

/**
 * A collapsible list, closed by default.
 *
 * WHY THE DETAIL COLLAPSES AND THE CHART DOES NOT. Each section now leads with
 * a chart that answers the question at a glance - the postcode's band spread,
 * the sold range - and follows with the rows the chart was built from. Those
 * rows are evidence, not headline: four EPC certificates and four transactions
 * is sixteen lines of small text, which pushed everything after it off-screen
 * and made two summarised sections read as one undifferentiated list.
 *
 * <details> rather than a click handler because it is the browser's own
 * disclosure widget: keyboard operable, announced as expandable, and included
 * in find-in-page in Chrome. Reimplementing it with a div and a listener loses
 * all three.
 */
function collapsible(summaryText, contentNode) {
  const box = el('details', 'c33-fold');
  box.appendChild(el('summary', 'c33-fold-sum', summaryText));
  box.appendChild(contentNode);
  return box;
}

/**
 * "4 COLLINGHAM ROAD" -> "4 Collingham Road".
 *
 * Land Registry publishes addresses in caps. Reproduced verbatim they read as
 * shouting inside a panel where nothing else is uppercase except the section
 * headings, so the loudest text on screen ends up being the least important.
 * Words already containing a digit are left alone, so "SW5" and "C14" survive.
 */
function titleCase(s) {
  return String(s || '').replace(/[^\s·]+/g, (w) =>
    /\d/.test(w) ? w : w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()
  );
}

/** "2025-03-14" -> "Mar 2025". Day precision is noise for a sold price. */
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
function shortDate(iso) {
  const m = /^(\d{4})-(\d{2})/.exec(String(iso || ''));
  if (!m) return '';
  return `${MONTHS[Number(m[2]) - 1] || ''} ${m[1]}`.trim();
}

const SVG_NS = 'http://www.w3.org/2000/svg';

function svgEl(tag, attrs) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  return node;
}

/**
 * Where a reading sits relative to its guideline, as one small bar.
 *
 * WHY THE SCALE RUNS 0 TO TWICE THE GUIDELINE. A bar needs a domain, and the
 * obvious choice - the observed range across London - is a number we would be
 * inventing at the point of drawing. METHODOLOGY §4.6 forbids exactly that
 * shape of thing for noise, and this project has twice had to undo a figure
 * that was estimated rather than sourced. The guideline is the ONLY reference
 * the endpoint hands us, so it is the only one used: it sits at the midpoint,
 * the scale ends at twice it, and every number drawn is one we were given.
 *
 * The consequence is that the bar answers "how does this compare to the WHO
 * guideline", not "how does this compare to London". That is a narrower claim
 * and it is the one the data supports.
 *
 * Over/under is carried by POSITION relative to the tick, not by colour alone,
 * so it survives WCAG 1.4.1. Colour reinforces it. The aria-label carries the
 * whole sentence, because a bar announces nothing on its own.
 */
function scaleBar({ value, guideline, unit, max }) {
  const ceiling = guideline ? guideline * 2 : max;
  const clamped = Math.min(Math.max(value / ceiling, 0), 1);
  const over = typeof guideline === 'number' && value > guideline;
  const pct = clamped * 100;

  const height = guideline ? 24 : 12;
  // Neutral when there is no guideline. Falling through to "under" would paint
  // the 0-10 quiet estimate green, i.e. assert it is good, against a threshold
  // that does not exist. Colour here reports a comparison; with nothing to
  // compare to it must report nothing.
  const verdict =
    typeof guideline === 'number' ? (over ? 'c33-bar-over' : 'c33-bar-under') : 'c33-bar-neutral';

  const svg = svgEl('svg', {
    class: `c33-bar ${verdict}`,
    width: '100%',
    height,
    role: 'img',
    'aria-label': guideline
      ? `${value} ${unit}, ${over ? 'above' : 'within'} the WHO guideline of ${guideline} ${unit}`
      : `${value} out of ${max}`,
  });

  svg.appendChild(svgEl('rect', { class: 'c33-bar-track', x: 0, y: 4, width: '100%', height: 4, rx: 2 }));
  svg.appendChild(svgEl('rect', { class: 'c33-bar-fill', x: 0, y: 4, width: `${pct}%`, height: 4, rx: 2 }));

  if (guideline) {
    // The tick is always at the midpoint, by construction of the domain.
    svg.appendChild(svgEl('line', { class: 'c33-bar-tick', x1: '50%', x2: '50%', y1: 1, y2: 11 }));
    const lab = svgEl('text', { class: 'c33-bar-lab', x: '50%', y: 21, 'text-anchor': 'middle' });
    lab.textContent = `WHO ${guideline}`;
    svg.appendChild(lab);
  }

  svg.appendChild(svgEl('circle', { class: 'c33-bar-dot', cx: `${pct}%`, cy: 6, r: 3.5 }));
  return svg;
}

// The official certificate scale, worst to best left-to-right is NOT how the
// certificate prints it, so A first. Fixed seven steps, never interpolated.
const EPC_BANDS = ['A', 'B', 'C', 'D', 'E', 'F', 'G'];

/**
 * The postcode's EPC bands as seven columns.
 *
 * WHY THIS IS NOT A scaleBar. `cert.rating` looks like a plottable 1-100 SAP
 * score and is not one: MHCLG's search API stopped returning the numeric
 * rating, so `backend/lambdas/epc/app.py` synthesises it from BAND_MIDPOINT.
 * Every band C in the country comes back as exactly 75. Drawing that on a
 * continuous axis would assert a precision that no longer exists anywhere in
 * the pipeline - the same invented-number failure scaleBar()'s domain comment
 * refuses, only wearing a real number's clothing. The BAND is the datum, so
 * the chart has exactly as many positions as there are bands.
 *
 * WHY THE TICK IS AT E. Same rule as the WHO guideline: cite a threshold,
 * never invent one. The Minimum Energy Efficiency Standard makes E the lowest
 * band a property may legally be let at, so F and G columns are the ones that
 * carry a consequence. It is someone else's threshold and it is named on the
 * chart, exactly as "WHO 53" is.
 *
 * Height encodes count, colour is the official band ramp, and the letters sit
 * under the columns - so the chart is readable without colour, which the ramp
 * alone would not be.
 */
function bandStrip(distribution) {
  const counts = EPC_BANDS.map((b) => Number(distribution[b]) || 0);
  const total = counts.reduce((a, b) => a + b, 0);
  if (!total) return null;

  const peak = Math.max(...counts);
  const colW = 100 / EPC_BANDS.length;
  const FLOOR = 32;
  // 20, not 26: the count now sits 3px above each column, so the tallest bar
  // must leave room for a 9px label inside the SVG box or it clips at y=0.
  const TALLEST = 20;

  const svg = svgEl('svg', {
    class: 'c33-strip',
    width: '100%',
    height: 56,
    role: 'img',
    'aria-label':
      `EPC bands lodged for this postcode: ` +
      EPC_BANDS.map((b, i) => `${b} ${counts[i]}`).join(', ') +
      `. E is the minimum band a property may legally be let at.`,
  });

  counts.forEach((n, i) => {
    // A zero column still gets a 1px stub. A band with no certificates and a
    // band that is simply short must not look identical, and an empty gap
    // reads as "no data for this band" rather than "none here".
    const h = peak ? Math.max((n / peak) * TALLEST, n ? 3 : 1) : 1;
    // An empty band keeps its stub but LOSES its colour. Painting band A green
    // when no property here is band A spends the reader's attention on the
    // scale rather than the data - seven coloured marks of which four mean
    // "none". Colour earns its place only where there is something to count.
    svg.appendChild(
      svgEl('rect', {
        class:
          `c33-strip-col ` +
          (n > 0 ? `c33-strip-${EPC_BANDS[i].toLowerCase()}` : 'c33-strip-empty'),
        x: `${i * colW + 1.2}%`,
        width: `${colW - 2.4}%`,
        y: FLOOR - h,
        height: h,
        rx: 1,
      })
    );

    const lab = svgEl('text', {
      class: 'c33-strip-lab',
      x: `${(i + 0.5) * colW}%`,
      y: 43,
      'text-anchor': 'middle',
    });
    lab.textContent = EPC_BANDS[i];
    svg.appendChild(lab);

    // The count, because height alone cannot separate 0 from 1. Both render as
    // a few pixels of stub - visible in the 2026-08-08 screenshot, where A and
    // B (zero) were indistinguishable from E, F and G (small but non-zero).
    // Omitted on zero rather than printed as "0": an empty column already says
    // none, and seven zeroes would be noise on a postcode with few lodgements.
    if (n > 0) {
      const cnt = svgEl('text', {
        class: 'c33-strip-cnt',
        x: `${(i + 0.5) * colW}%`,
        y: FLOOR - h - 3,
        'text-anchor': 'middle',
      });
      cnt.textContent = String(n);
      svg.appendChild(cnt);
    }
  });

  // The boundary between E and F, i.e. after the fifth column.
  const tickX = `${5 * colW}%`;
  svg.appendChild(
    svgEl('line', { class: 'c33-strip-tick', x1: tickX, x2: tickX, y1: 0, y2: 35 })
  );
  const tickLab = svgEl('text', {
    class: 'c33-strip-ticklab',
    x: tickX,
    y: 54,
    'text-anchor': 'middle',
  });
  tickLab.textContent = 'MEES E';
  svg.appendChild(tickLab);

  return svg;
}

/** Compact money, for axis labels where "£1,250,000" will not fit. */
function money(n) {
  if (n >= 1000000) return `£${(n / 1000000).toFixed(n >= 10000000 ? 0 : 1)}m`;
  if (n >= 1000) return `£${Math.round(n / 1000)}k`;
  return `£${n}`;
}

/**
 * Recent sold prices on this postcode, with the asking price marked.
 *
 * WHY THIS DOMAIN IS ALLOWED WHERE "THE LONDON RANGE" WAS NOT. scaleBar()
 * refuses a domain drawn from observed spread, because for a noise reading that
 * spread is a statistic we would have to source and did not. Here the observed
 * spread IS the dataset being displayed — these are the very transactions
 * listed underneath, every one of them on screen. The axis makes no claim the
 * list does not already make.
 *
 * WHAT IT DELIBERATELY DOES NOT SAY. Not "over" or "under", no verdict colour,
 * no "% above local average". Land Registry lags completion by around two
 * months, and nothing here is adjusted for size, condition, floor or lease. A
 * £34m block of flats sits legitimately far right of four one-bed sales on the
 * same postcode. Position is a fact; "overpriced" would be an inference the
 * data cannot carry, and the caption says so in words.
 */
function priceRange(transactions, asking) {
  const sold = transactions.map((t) => Number(t.price)).filter((n) => Number.isFinite(n) && n > 0);
  if (!sold.length) return null;

  const lo = Math.min(...sold);
  const hi = Math.max(...sold);
  // The asking price extends the axis when it falls outside the sold range —
  // clamping it to the edge would hide exactly the case worth seeing.
  const axisLo = Math.min(lo, asking ?? lo);
  const axisHi = Math.max(hi, asking ?? hi);
  const span = axisHi - axisLo;
  // 8% padding so an extreme value is not drawn half off the edge. A display
  // margin only: the labels state the true lo/hi, unpadded.
  //
  // Clamped at zero because the padding is proportional to the SPAN, and the
  // span is set by the asking price when that is an outlier. SW5 in the e2e:
  // sales £290k-£1.0m against a £34m asking price gives an 8% pad of £2.7m,
  // putting the axis origin at MINUS £2.4m. An axis that starts below zero
  // implies negative sale prices exist.
  const pad = span ? span * 0.08 : 1;
  const p0 = Math.max(axisLo - pad, 0);
  const p1 = axisHi + pad;
  const at = (v) => ((v - p0) / (p1 - p0)) * 100;

  const dates = transactions.map((t) => (t.date || '').slice(0, 4)).filter(Boolean).sort();
  const years = dates.length
    ? dates[0] === dates[dates.length - 1]
      ? dates[0]
      : `${dates[0]}-${dates[dates.length - 1]}`
    : '';

  // When the asking price falls outside the recorded sales entirely, say so in
  // words. The chart already shows it, but only as dot positions the reader has
  // to interpret - and in the outlier case the sales collapse into one blob, so
  // the spread they came for is unreadable. Stated as arithmetic ("above every
  // recorded sale"), never as judgement ("overpriced"): the SW5 fixture is a
  // whole block of apartments against a street of one-bed flats, where sitting
  // far above the sales is exactly correct and means nothing about value.
  const outlier = asking ? (asking > hi ? 'above' : asking < lo ? 'below' : null) : null;
  // Short enough to sit inline with the count. The long form lives in the
  // aria-label, where length costs nothing.
  const outlierNote = outlier ? `asking is ${outlier} all of them` : '';

  const svg = svgEl('svg', {
    class: 'c33-range',
    width: '100%',
    height: 62,
    role: 'img',
    'aria-label':
      `${sold.length} Land Registry ${sold.length === 1 ? 'sale' : 'sales'} on this postcode` +
      `${years ? `, ${years}` : ''}, from ${money(lo)} to ${money(hi)}` +
      (asking ? `. This listing is asking ${money(asking)}` : '') +
      (outlierNote ? `, ${outlier} every recorded sale here.` : asking ? '.' : '.') +
      ' Not adjusted for size, condition or lease.',
  });

  svg.appendChild(
    svgEl('rect', { class: 'c33-range-track', x: '0%', y: 18, width: '100%', height: 4, rx: 2 })
  );
  // The sold band: where the actual transactions sit, ignoring the asking price.
  svg.appendChild(
    svgEl('rect', {
      class: 'c33-range-band',
      x: `${at(lo)}%`,
      y: 18,
      width: `${Math.max(at(hi) - at(lo), 0.5)}%`,
      height: 4,
      rx: 2,
    })
  );

  for (const n of sold) {
    svg.appendChild(svgEl('circle', { class: 'c33-range-dot', cx: `${at(n)}%`, cy: 20, r: 3 }));
  }

  if (asking) {
    const x = `${at(asking)}%`;
    svg.appendChild(svgEl('line', { class: 'c33-range-ask', x1: x, x2: x, y1: 10, y2: 30 }));
    // Anchor the label inward at the extremes or it renders off the panel.
    const pct = at(asking);
    const lab = svgEl('text', {
      class: 'c33-range-asklab',
      x,
      y: 7,
      'text-anchor': pct < 18 ? 'start' : pct > 82 ? 'end' : 'middle',
    });
    lab.textContent = `asking ${money(asking)}`;
    svg.appendChild(lab);
  }

  // ONE label, on the sold band, naming the range it actually covers.
  //
  // This was two labels pinned to the axis ends (x=0% and x=100%) showing the
  // sold lo and hi - which is correct only while the asking price sits inside
  // the sold range. On the SW5 fixture it does not: 10 sales spanning
  // £290k-£1.0m against £34m asking put the £1.0m label at the right-hand edge,
  // where the axis actually reads £34m. The label would have named the sold
  // maximum while pointing at the asking price. Anchoring both labels to the
  // BAND instead of the axis makes the position and the number agree by
  // construction, and it stays right whatever the asking price does.
  const bandMid = (at(lo) + at(hi)) / 2;
  const bandLab = svgEl('text', {
    class: 'c33-range-lab',
    x: `${bandMid}%`,
    y: 40,
    'text-anchor': bandMid < 12 ? 'start' : bandMid > 88 ? 'end' : 'middle',
  });
  bandLab.textContent = hi === lo ? money(lo) : `${money(lo)}-${money(hi)}`;
  svg.appendChild(bandLab);

  // ONE caption line, not three. This carried the range, then a count-plus-
  // caveat, then the outlier note - three left-aligned greys stacked under a
  // chart, which is more text than the chart it explains. The caveat moves to
  // the section's disclosure, where Environment already keeps its caveats, so
  // both sections now behave the same way. The outlier note stays visible: it
  // is a fact about THIS listing, not a standing footnote.
  // One caption line. Not two text nodes on the same baseline at opposite
  // anchors: "asking price is above every recorded sale here" is ~45 characters
  // and would have overlapped the count in a 300px-wide panel.
  const cap = svgEl('text', { class: 'c33-range-cap', x: '0%', y: 56, 'text-anchor': 'start' });
  cap.textContent = [`${sold.length} sold${years ? ` ${years}` : ''}`, outlierNote]
    .filter(Boolean)
    .join(' · ');
  svg.appendChild(cap);

  return svg;
}

/**
 * The compact "we have nothing" state. Was a heading plus a sentence per
 * section, so four dead sections cost eight lines and pushed the data that DID
 * arrive off-screen. One line each now, and the reason is kept in the title
 * attribute rather than thrown away.
 */
function unavailable(label, reason) {
  const row = el('p', 'c33-none', `${label} — not available`);
  if (reason) row.title = String(reason);
  return row;
}

/**
 * Decide what the panel is allowed to show for a given extraction.
 *
 * This is the honesty gate. The Core Cities audit recorded the underlying
 * lesson the hard way: partial data presented as complete is worse than no
 * data, because a neutral-looking number reads as a measurement.
 *
 * Demo build collapses to three cases. When /v1/score, EPC and sold prices
 * arrive (all of which need lat/lon -> postcode reverse geocoding first) this
 * grows a 'partial' tier for borough-only resolution, and THAT is the tier
 * worth arguing about — a borough-average affordability score rendered against
 * a specific flat is precisely the failure above.
 *
 * TODO(bill): revisit when the reverse-geocode path lands. The open question is
 * whether a borough-level score should render greyed-out with a caveat, or not
 * render at all. I have defaulted to the conservative reading below.
 */
function decidePresentation(listing) {
  if (!listing) {
    // No coordinates means no data we can stand behind. Show nothing at all —
    // not an empty panel, not a "couldn't find anything" card. An empty panel
    // invites the reader to conclude the area has no GPs and no stations.
    return { show: 'nothing', sections: [], caveat: null };
  }

  // WHAT THE CHANNEL DECIDES.
  //
  // Land Registry Price Paid records SALES. On a letting, "Sold nearby" is not
  // neutral padding - it is a column of six-figure sums beside a property
  // nobody is selling, in a different unit from the only price on the page.
  // Dropped rather than shown empty.
  //
  // SECTION ORDER DOES NOT CHANGE. Only the CONTENT does.
  //
  // The first cut promoted EPC to the top on a letting, reasoning that MEES is
  // legally material to a tenant where the band is mere context to a buyer.
  // That reasoning still holds and it still produced the wrong design: a user
  // moving between a sale and a rental met a panel whose sections had moved,
  // and read it as the extension behaving inconsistently rather than as an
  // editorial judgement about their situation. Reported from live use, which is
  // the only place a reordering cost like that shows up.
  //
  // Environment leads throughout - it is the measurement nobody else on the
  // page is offering, and the reason to open this at all. The letting-specific
  // value arrives inside EPC (the MEES line, the tenant disclosure) rather than
  // by moving furniture around it. Stable layout, situational content.
  //
  // A null channel keeps the sale layout. That is the conservative direction:
  // an unnecessary Sold nearby on a rental is noise, where a missing one on a
  // sale removes the section most likely to be the reason someone opened this.
  const letting = listing.channel === 'letting';
  const order = letting
    ? ['environment', 'epc', 'nhs']
    : ['environment', 'epc', 'soldPrices', 'nhs'];

  if (!listing.inLondon) {
    // Outside London the environmental rasters thin out - DEFRA's aircraft
    // contours are English agglomerations and the road raster we hold is a
    // London bbox. Everything here still resolves via postcode, so the sections
    // stay; the caveat exists so a sparse answer is not read as a clean one.
    return {
      show: 'partial',
      sections: order,
      letting,
      caveat:
        'Aircraft and road noise coverage is strongest in London; figures outside it may be absent.',
    };
  }

  return { show: 'full', sections: order, letting, caveat: null };
}

// --- Section renderers ---------------------------------------------------

function renderNhs(result) {
  if (!result.ok) {
    return unavailable('Healthcare', result.error);
  }

  const section = el('section', 'c33-section');
  section.appendChild(el('h3', 'c33-h3', 'Healthcare'));

  const data = result.data;

  if (data.available === false) {
    section.appendChild(el('p', 'c33-none', data.note || 'Live data unavailable'));
  }

  const groups = [
    ['gp', 'Doctors & clinics'],
    ['pharmacies', 'Pharmacies'],
    ['hospitals', 'Hospitals'],
  ];

  let rendered = 0;
  for (const [key, label] of groups) {
    const items = data[key] || [];
    if (!items.length) continue;

    const group = el('div', 'c33-group');
    group.appendChild(el('h4', 'c33-h4', label));

    const list = el('ul', 'c33-list');
    for (const item of items.slice(0, 3)) {
      const li = el('li', 'c33-item');
      const row = el('div', 'c33-row');
      row.appendChild(el('span', 'c33-name', item.name));
      // A fallback row has distance null — it is a link to nhs.uk, not a
      // located facility, so showing "0 m" would be a lie.
      row.appendChild(el('span', 'c33-dist', item.fallback ? '' : metres(item.distance)));
      li.appendChild(row);
      list.appendChild(li);
    }
    group.appendChild(list);
    section.appendChild(group);
    rendered += 1;
  }

  if (rendered === 0) {
    section.appendChild(el('p', 'c33-none', 'None found nearby'));
  }

  return section;
}

function renderEnvironment(result) {
  if (!result.ok) {
    return unavailable('Environment', result.error);
  }

  const section = el('section', 'c33-section');
  section.appendChild(el('h3', 'c33-h3', 'Environment'));

  const data = result.data;
  const env = data.environment || {};

  // Every row is present only when a real measurement exists — the endpoint
  // omits the key rather than sending null or a default. So an empty list here
  // means "nothing was measured for this postcode", which the notices explain,
  // and never "measured as fine".
  // Every environmental row now carries its WHO reference. A bare "69.6 dB
  // Lden" is uninterpretable — the guideline is what turns a number into
  // something a reader can act on, and it is cited rather than invented:
  // WHO Environmental Noise Guidelines for the European Region (2018) for the
  // two noise rows, WHO global air quality guidelines (2021) for the two
  // pollutant rows.
  //
  // The estimated aircraft row is the exception and deliberately carries none.
  // It is on a 0-10 quiet scale, not decibels, because it comes from
  // flight-path geometry rather than a reading — putting a dB guideline beside
  // it would imply a measurement that does not exist.
  // Whether the DEFRA rows carry the COVID-year vintage. Kept as a per-row flag
  // so the tag sits ON the affected reading rather than as a paragraph under
  // rows it does not apply to.
  const mapsCovidYear = [env.aircraftNoiseSource, env.roadNoiseSource]
    .filter(Boolean)
    .some((s) => /maps 2021/.test(s));

  // THE AIRCRAFT CAVEAT RIDES ITS OWN ROW, ABOVE ROAD NOISE.
  //
  // It was in the disclosure at the foot of the section, which meant the one
  // reading on this panel that is NOT a measurement - a geometric estimate, on
  // a 0-10 scale, for the ~91% of London postcodes DEFRA never surveyed - had
  // its caveat sitting two rows below a measured road figure and behind a
  // click. A reader scanning down met "5/10 quiet" and then "49.5 dB Lden" with
  // nothing between them to say those are different KINDS of number.
  //
  // Same principle as the 2021 vintage tag: put the qualification on the
  // reading it qualifies, not in a paragraph under readings it does not.
  //
  // Matched on the notice's opening rather than a flag because both strings
  // live in this repo (`_COVERAGE_NOTICES['postcode']` in score/app.py). If
  // that wording ever changes the match fails OPEN - the notice stays in the
  // disclosure and nothing is lost, rather than vanishing from both places.
  const aircraftNotice = (data.notices || []).find((n) => /^Aircraft noise here is/.test(n));

  const rows = [
    ['Aircraft noise', env.aircraftNoiseLdenDb, 'dB Lden', env.aircraftNoiseWhoGuidelineDb, mapsCovidYear, ''],
    [
      'Aircraft noise (estimated)',
      env.aircraftQuietEstimated,
      '/10 quiet',
      null,
      false,
      // Prefer the endpoint's own per-row basis string, which exists for this;
      // fall back to the longer coverage notice when it is absent.
      env.aircraftQuietBasis
        ? `Estimated from ${env.aircraftQuietBasis}.`
        : aircraftNotice || '',
    ],
    ['Road noise', env.roadNoiseLdenDb, 'dB Lden', env.roadNoiseWhoGuidelineDb, mapsCovidYear, ''],
    ['Nitrogen dioxide', env.no2AnnualMeanUgm3, 'ug/m3', env.no2WhoGuidelineUgm3, false, ''],
    ['Fine particles (PM2.5)', env.pm25AnnualMeanUgm3, 'ug/m3', env.pm25WhoGuidelineUgm3, false, ''],
  ].filter((r) => typeof r[1] === 'number');

  if (rows.length) {
    const list = el('ul', 'c33-list');
    for (const [label, value, unit, guideline, vintage, note] of rows) {
      const item = el('li', 'c33-item');
      const row = el('div', 'c33-row');
      const name = el('span', 'c33-name', label);
      // The vintage rides on the reading it qualifies. This used to be a
      // two-sentence paragraph below the list, which meant it applied visually
      // to the air-quality rows it has nothing to do with.
      if (vintage) {
        // The space is a real text node, not CSS margin. Without it textContent
        // is "Aircraft noise2021", which is what a screen reader announces and
        // what any text assertion sees - the margin only moves pixels.
        name.appendChild(document.createTextNode(' '));
        const tag = el('span', 'c33-tag', '2021');
        tag.title = 'DEFRA data mapping 2021';
        name.appendChild(tag);
      }
      row.appendChild(name);

      // "/10 quiet" is a suffix, not a unit, so it takes no leading space -
      // this rendered as "5 /10 quiet".
      const readout = el(
        'span',
        'c33-dist',
        unit.startsWith('/') ? `${value}${unit}` : `${value} ${unit}`
      );
      // Colour states a fact, not a verdict: whether the measurement is above
      // the cited guideline. No "good"/"bad" wording, because the guideline is
      // WHO's judgement and the comparison is arithmetic — anything richer
      // would be us editorialising over someone else's threshold.
      if (typeof guideline === 'number') {
        readout.className += value > guideline ? ' c33-over' : ' c33-under';
      }
      row.appendChild(readout);
      item.appendChild(row);

      // The bar replaces the sub-line it used to carry ("within WHO 53 dB
      // Lden"), which was repeated verbatim on every row and read as
      // boilerplate. The same fact is now positional, and the aria-label still
      // says it in words for anyone the bar cannot reach.
      if (typeof guideline === 'number') {
        item.appendChild(scaleBar({ value, guideline, unit }));
      } else if (unit.startsWith('/')) {
        // The 0-10 quiet estimate: a scale by construction, so it gets a bar
        // with no guideline tick. There is nothing to compare it to, and
        // inventing a threshold for a geometry-derived figure would be exactly
        // the move the comment above refuses.
        item.appendChild(scaleBar({ value, guideline: null, unit, max: 10 }));
      }

      // Below the bar, so it reads as a footnote to THIS reading and the next
      // row starts clean.
      if (note) item.appendChild(el('div', 'c33-rownote', note));
      list.appendChild(item);
    }
    section.appendChild(list);
  }

  // The vintage caveat travels with the reading, not just in the footer.
  //
  // DEFRA Round 4 was published in 2022 and maps 2021 — a year its own
  // documentation calls "a highly anomalous situation" because of COVID travel
  // restrictions, with Heathrow movements substantially below 2019. Every dB
  // here therefore ERRS QUIET. Shown beside the numbers because a reader who
  // takes 50.4 dB at face value has been misled by an omission, and the footer
  // is not where anyone looks for that.
  //
  // No corrected figure is offered. METHODOLOGY §4.6 forbids applying an
  // estimated correction factor: inventing a multiplier is a failure mode this
  // project has already had to undo twice.
  // One disclosure for everything explanatory, rather than a stack of
  // paragraphs. The facts these justify are already on the rows: "(estimated)"
  // in a label, "2021" tagged on the readings it applies to. See disclosure().
  const explanations = [];
  if (mapsCovidYear) {
    explanations.push(
      'DEFRA noise data maps 2021, a COVID-affected year, so these readings ' +
        'understate current exposure. The direction is known; the amount is not, ' +
        'and no correction factor is applied.'
    );
  }
  // Everything except the aircraft coverage notice, which now sits inline on
  // the row it describes. Kept here when no estimated row rendered to carry it
  // — a caveat with nothing to attach to still has to be said somewhere.
  const inlinedAircraftNotice = rows.some((r) => r[5] && r[0].includes('estimated'));
  explanations.push(
    ...(data.notices || []).filter((n) => !(inlinedAircraftNotice && n === aircraftNotice))
  );

  if (explanations.length) {
    // The summary names the count so it is obvious something was left out,
    // rather than a decorative "more info" nobody opens.
    const label =
      explanations.length === 1
        ? 'About this reading'
        : `About these readings (${explanations.length})`;
    section.appendChild(disclosure(label, explanations));
  }

  if (!rows.length && !explanations.length) {
    section.appendChild(el('p', 'c33-none', 'No environmental measurements here'));
  }

  return section;
}

function renderEpc(result, listing) {
  if (!result.ok) {
    return unavailable('EPC register', result.error);
  }

  const section = el('section', 'c33-section');
  section.appendChild(el('h3', 'c33-h3', 'EPC register'));

  const data = result.data;
  const certs = data.certificates || [];
  const summary = data.summary || {};

  if (!certs.length) {
    section.appendChild(el('p', 'c33-muted', 'No lodged certificates for this postcode.'));
    return section;
  }

  // The point is NOT "here is the EPC" — Rightmove already shows one, from
  // whatever the agent uploaded. The point is what the MHCLG register holds for
  // this postcode, and how this property's claim sits against its neighbours.
  // A listing claiming C on a postcode where seven of nine homes are D or E is
  // a question worth asking, and no listing page asks it for you.
  // Was two text lines - "Postcode: B×2 C×5 D×3" and "Most common band here: C"
  // - which asked the reader to hold seven counts in their head to see a shape.
  // The chart is that shape, and the tallest column IS the most common band, so
  // the second line stated something the first already contained. Same move as
  // the scale bar replacing its per-row "within WHO 53 dB" sentence: keep the
  // fact, drop the words, and put the words in the aria-label for anyone the
  // chart cannot reach.
  // No intro line above the chart. "EPC bands lodged at this postcode" restated
  // what the section heading, the A-G axis and the counts already say between
  // them - a caption is worth a line only when the chart is ambiguous without
  // it. The full sentence still reaches screen readers via the aria-label.
  const strip = bandStrip(summary.bandDistribution || {});
  if (strip) section.appendChild(strip);

  // ON A LETTING, MEES IS THE POINT OF THIS SECTION.
  //
  // For a buyer the band is context. For a tenant it is two live facts: below
  // band E a property generally may not lawfully be let, and the band is a
  // heating bill they pay on fabric they cannot change. Rightmove prints the
  // band; it does not print either consequence.
  //
  // THE CONSTRAINT THAT SHAPES THE WORDING. We deliberately never capture the
  // listing's address, so no certificate here can be matched to THIS property.
  // Every sentence below is therefore about the POSTCODE's lodged certificates
  // and says so. "This flat is band D" is the claim we are not entitled to
  // make, and it is the one a reader would most like to be given.
  if (listing?.channel === 'letting') {
    const dist = summary.bandDistribution || {};
    const belowE = (Number(dist.F) || 0) + (Number(dist.G) || 0);
    const total = EPC_BANDS.reduce((n, b) => n + (Number(dist[b]) || 0), 0);

    if (total > 0) {
      const line =
        belowE > 0
          ? `${belowE} of ${total} certificates at this postcode are below band E`
          : `All ${total} certificates at this postcode meet band E`;
      const mees = el('p', 'c33-mees', `${line} — the minimum for a new letting.`);
      if (belowE > 0) mees.className += ' c33-mees-flag';
      section.appendChild(mees);
    }

  }

  const list = el('ul', 'c33-list');
  for (const cert of certs.slice(0, 6)) {
    const item = el('li', 'c33-item');
    const row = el('div', 'c33-row');
    row.appendChild(el('span', 'c33-name', cert.address || 'Address not given'));
    // EPC bands carry a colour scale everyone already recognises from the
    // certificate itself, so reusing it costs nothing and reads instantly.
    // Class per band rather than a computed colour: A-G is a fixed, official
    // seven-step scale, not something to interpolate.
    const band = (cert.band || '').toUpperCase();
    const badge = el('span', 'c33-dist c33-band', band || '?');
    if (/^[A-G]$/.test(band)) badge.className += ` c33-band-${band.toLowerCase()}`;
    row.appendChild(badge);
    item.appendChild(row);
    // "lodged 2025-01-21" -> "Jan 2025". The day a certificate was filed is
    // never the question; roughly how recent it is always is.
    if (cert.date) item.appendChild(el('div', 'c33-sub', shortDate(cert.date)));
    list.appendChild(item);
  }

  // Folded away by default. The chart above already answers "what are the
  // bands here"; these rows are the evidence behind it, and open they cost
  // twelve lines that pushed Sold nearby off the first screen entirely.
  const shown = Math.min(certs.length, 6);
  const label =
    certs.length > shown
      ? `${shown} of ${certs.length} certificates`
      : `${shown} certificate${shown === 1 ? '' : 's'}`;
  section.appendChild(collapsible(label, list));

  // Last, after the evidence, matching Sold nearby's chart → fold → disclosure
  // order. Explanation belongs behind the thing it explains; the first cut put
  // it above the certificate list and the two sections read differently for no
  // reason a user could infer.
  if (listing?.channel === 'letting') {
    section.appendChild(
      disclosure('What the band means for a tenant', [
        'Under the Minimum Energy Efficiency Standard, a property in band F or ' +
          'G generally cannot be let on a new tenancy in England and Wales, ' +
          'with limited registered exemptions.',
        'The band is also a running cost. Heating a band D home costs ' +
          'materially more than a band B one, and it is a bill the tenant pays ' +
          'on fabric only the landlord can change.',
        'These certificates are everything lodged at this postcode. This ' +
          'extension never reads the listing address, so none of them can be ' +
          'matched to the specific property you are looking at — treat them as ' +
          'the building stock here, not as this flat.',
      ])
    );
  }
  return section;
}

function renderSoldPrices(result, listing) {
  if (!result.ok) {
    return unavailable('Sold nearby', result.error);
  }

  const section = el('section', 'c33-section');
  section.appendChild(el('h3', 'c33-h3', 'Sold nearby'));

  const tx = (result.data || {}).transactions || [];
  if (!tx.length) {
    section.appendChild(el('p', 'c33-muted', 'No Land Registry sales recorded for this postcode.'));
    return section;
  }

  // Rightmove HAS sold-price data, but as a separate search tool — not on the
  // listing you are looking at, beside the asking price. Putting the street's
  // actual transactions next to what is being asked for is the whole value.
  //
  // The chart is that sentence made literal. The asking price is absent on a
  // letting and whenever the page did not positively say it is a sale, in which
  // case this still draws the spread of completed sales, which stands alone.
  const range = priceRange(tx, listing?.askingPrice ?? null);
  if (range) section.appendChild(range);

  // Most recent first. The API's order is not guaranteed, and a 2007 sale at
  // the top of a list headed "Sold nearby" invites the reader to take it as
  // current. Sorting on the date we already display keeps what is shown and
  // what it is ranked by the same thing.
  const ordered = [...tx].sort((a, b) => String(b.date || '').localeCompare(String(a.date || '')));

  const shownTx = ordered.slice(0, 6);
  const whereOf = (t) => titleCase([t.address, t.street].filter(Boolean).join(' ').trim());
  // "flat-maisonette" is Land Registry's raw enum. Presented as written it looks
  // like a field we forgot to format; hyphen to slash is the whole fix.
  const typeOf = (t) => (t.type ? String(t.type).replace(/-/g, '/') : '');

  // ELIDE WHAT IS CONSTANT. Land Registry keys on PAON, so a block of flats
  // returns every sale at the same "4 COLLINGHAM ROAD" and often the same
  // property type - printed per row that reads as one property sold six times,
  // and it fills the line where the distinguishing detail should be. Any field
  // identical across the whole list is stated ONCE above the rows: a repeated
  // value carries no information after its first appearance.
  const constant = (fn) => {
    const vals = shownTx.map(fn);
    return vals[0] && vals.every((v) => v === vals[0]) ? vals[0] : null;
  };
  const commonWhere = constant(whereOf);
  const commonType = constant(typeOf);

  const list = el('ul', 'c33-list');
  for (const t of shownTx) {
    const item = el('li', 'c33-item');

    // Price leads, date beside it. This row used to put the address first and
    // the price right-aligned, with the date on a third line - so scanning for
    // "what did things go for, and when" meant reading three lines per sale in
    // two different alignments. Price and date are the comparison; the address
    // is which one, and drops to the secondary line with the property type.
    const row = el('div', 'c33-row');
    row.appendChild(
      el('span', 'c33-price', t.price ? '£' + Number(t.price).toLocaleString('en-GB') : '')
    );
    row.appendChild(el('span', 'c33-when', shortDate(t.date)));
    item.appendChild(row);

    const meta = [
      commonWhere ? '' : whereOf(t) || 'Address not given',
      commonType ? '' : typeOf(t),
      // Never elided: "new build" is true of individual sales, so its absence
      // on a row is information rather than repetition.
      t.newBuild ? 'new build' : '',
    ]
      .filter(Boolean)
      .join(' · ');
    if (meta) item.appendChild(el('div', 'c33-sub', meta));
    list.appendChild(item);
  }

  const wrap = el('div', null);
  // "at" before the address, or "All 4 Collingham Road" reads as "all four".
  const shared = commonWhere
    ? [`at ${commonWhere}`, commonType].filter(Boolean).join(' · ')
    : commonType;
  if (shared) wrap.appendChild(el('p', 'c33-common', `All ${shared}`));
  wrap.appendChild(list);

  const shown = shownTx.length;
  const label =
    ordered.length > shown
      ? `${shown} most recent of ${ordered.length} sales`
      : `${shown} sale${shown === 1 ? '' : 's'}`;
  section.appendChild(collapsible(label, wrap));

  // The standing caveats, in the same disclosure Environment uses for its own.
  // They were a permanent grey line under the chart, read once and ignored
  // after - and they are the difference between a position and a valuation, so
  // being ignored is the failure mode. One consistent place for "what you
  // should know about these numbers", in every section that has any.
  section.appendChild(
    disclosure('About these figures', [
      'HM Land Registry Price Paid records completed sales and publishes them ' +
        'roughly two months in arrears, so the most recent sale on a street may ' +
        'not appear here yet.',
      'Figures are not adjusted for size, condition, floor or lease length. A ' +
        'larger or freehold property sitting above its neighbours is expected, ' +
        'not a signal, which is why nothing here is coloured as good or bad.',
    ])
  );
  return section;
}

// --- Attribution ---------------------------------------------------------
// Both upstreams carry licence obligations that follow the data into any
// surface that displays it — TfL Open Data requires credit, and OpenStreetMap
// is ODbL, which requires attribution on any Produced Work. The Lambdas already
// return the correct strings in `sources`; our only job is not to drop them.
function renderSources(payloads) {
  const seen = new Set();
  for (const p of payloads) {
    if (!p?.ok) continue;
    for (const s of p.data.sources || []) seen.add(s);
  }
  if (!seen.size) return null;

  const foot = el('footer', 'c33-foot');
  for (const s of seen) foot.appendChild(el('div', null, s));
  return foot;
}

// --- Panel lifecycle -----------------------------------------------------

function removePanel() {
  document.getElementById(PANEL_ID)?.remove();
}

function buildPanel(listing, plan) {
  removePanel();

  const panel = el('div', null);
  panel.id = PANEL_ID;
  panel.setAttribute('role', 'complementary');
  panel.setAttribute('aria-label', 'cubitt33 property data');

  const header = el('header', 'c33-header');

  // The title is a BUTTON, not a span with a listener on the header. A bare
  // click handler on a <header> is invisible to the keyboard and announces
  // nothing; a button is focusable, operable with Enter and Space, and carries
  // aria-expanded so the collapsed state is perceivable without seeing it.
  //
  // It does NOT wrap the close button. Nesting an interactive element inside
  // another is invalid HTML and Chrome resolves the click ambiguously - close
  // would sometimes collapse instead.
  const toggle = el('button', 'c33-toggle');
  toggle.type = 'button';
  toggle.setAttribute('aria-expanded', 'true');
  toggle.appendChild(badgeMark());
  toggle.appendChild(el('span', 'c33-title', 'cubitt33'));
  // Drawn, not the '⌄' character. That glyph has no consistent metrics across
  // the system-ui stack and rendered as a small lowercase "v" sitting off the
  // baseline - visible in the 2026-08-08 screenshot. A path has the shape it
  // is given, everywhere.
  const chev = svgEl('svg', {
    class: 'c33-chev',
    width: 12,
    height: 12,
    viewBox: '0 0 12 12',
    'aria-hidden': 'true',
    focusable: 'false',
  });
  chev.appendChild(
    svgEl('path', {
      d: 'M3 4.5 L6 7.5 L9 4.5',
      fill: 'none',
      stroke: 'currentColor',
      'stroke-width': 1.6,
      'stroke-linecap': 'round',
      'stroke-linejoin': 'round',
    })
  );
  toggle.appendChild(chev);
  toggle.addEventListener('click', () => {
    const collapsed = panel.getAttribute('data-collapsed') === 'true';
    panel.setAttribute('data-collapsed', String(!collapsed));
    toggle.setAttribute('aria-expanded', String(collapsed));
  });
  header.appendChild(toggle);

  const close = el('button', 'c33-close', '×');
  close.type = 'button';
  close.setAttribute('aria-label', 'Close cubitt33 panel');
  close.addEventListener('click', () => {
    removePanel();
    showBadge(listing);
  });
  header.appendChild(close);
  panel.appendChild(header);

  // Echo back what we located, so a mislocation is obvious at a glance rather
  // than silently poisoning every number below it.
  if (listing.address) {
    // Rightmove's displayAddress repeats the town when the street already names
    // it, so a real SW5 listing renders "Collingham Road, London, London, SW5".
    // Dedupe case-insensitively and keep the FIRST occurrence, which preserves
    // the address's own ordering rather than imposing one.
    const seen = new Set();
    const address = String(listing.address)
      .split(',')
      .map((part) => part.trim())
      .filter((part) => {
        if (!part) return false;
        const key = part.toLowerCase();
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .join(', ');
    panel.appendChild(el('p', 'c33-addr', address));
  }

  if (plan.caveat) {
    panel.appendChild(el('p', 'c33-caveat', plan.caveat));
  }

  const body = el('div', 'c33-body');
  body.appendChild(el('p', 'c33-muted', 'Loading…'));
  panel.appendChild(body);

  document.body.appendChild(panel);
  return body;
}

// Ordered by how much each adds that the listing page does not.
//
// Environment first: noise and air quality are the only figures here a portal
// will never print. EPC and sold prices next - both exist on Rightmove, but the
// register is the authority rather than the agent's upload, and sold prices sit
// in a separate search tool rather than beside the asking price. Healthcare
// last, as the weakest.
//
// `postcode: true` marks a section that cannot start until /v1/environment has
// reverse-geocoded a postcode from the listing's coordinates.
const SECTIONS = {
  environment: { label: 'Environment', render: renderEnvironment },
  epc: { label: 'EPC register', render: renderEpc, postcode: true },
  soldPrices: { label: 'Sold nearby', render: renderSoldPrices, postcode: true },
  nhs: { label: 'Healthcare', render: renderNhs },
};

async function requestSection(name, listing, postcode) {
  try {
    return await chrome.runtime.sendMessage({
      type: 'FETCH_ENDPOINT',
      endpoint: name,
      lat: listing.lat,
      lon: listing.lon,
      postcode,
    });
  } catch {
    // Fires when the service worker was torn down mid-flight, or the extension
    // was reloaded while this tab stayed open. Both are recoverable by the
    // user, so report rather than fail silently.
    return { ok: false, error: 'extension reloaded, refresh the page' };
  }
}

async function loadInto(body, listing, plan) {
  // Each section gets its own placeholder and fills in when ITS upstream
  // answers. Previously the panel waited for both and repainted once, which
  // meant a slow or dead Overpass held the transport data hostage — measured at
  // up to 30 seconds of "Loading…" with TfL's answer already in memory.
  const slots = {};
  const parts = [];

  body.replaceChildren();
  for (const name of plan.sections) {
    const holder = el('section', 'c33-section');
    holder.appendChild(el('h3', 'c33-h3', SECTIONS[name].label));
    holder.appendChild(el('p', 'c33-muted', 'Loading…'));
    slots[name] = holder;
    body.appendChild(holder);
  }

  const results = {};

  const paint = (name, result) => {
    results[name] = result;
    // `listing` reaches the renderers so sold prices can mark the asking price.
    // Passed to all of them rather than special-cased, so the next renderer
    // that needs page context does not have to re-plumb this.
    const rendered = SECTIONS[name].render(result, listing);
    slots[name].replaceWith(rendered);
    slots[name] = rendered;
  };

  // Coordinate-keyed sections start immediately. Postcode-keyed ones cannot:
  // a listing page yields a point, and /epc and /sold-prices want a postcode,
  // so they wait for /v1/environment to reverse-geocode one. Chained rather
  // than blocked — the coordinate sections still paint as they land, and a
  // failed environment call costs only the two that depend on it.
  const byKey = (wantsPostcode) =>
    plan.sections.filter((n) => Boolean(SECTIONS[n].postcode) === wantsPostcode);

  const coordWork = byKey(false).map(async (name) => {
    const result = await requestSection(name, listing);
    paint(name, result);
    return [name, result];
  });

  const postcodeWork = (async () => {
    const dependants = byKey(true);
    if (!dependants.length) return;

    const env = await requestSection('environment', listing);
    const postcode = env.ok ? (env.data || {}).location?.postcode : null;

    if (!postcode) {
      // No postcode means these genuinely cannot be answered, which is a
      // different thing from "we looked and found nothing". Say which.
      for (const name of dependants) {
        paint(name, { ok: false, error: 'no postcode resolved for this location' });
      }
      return;
    }

    await Promise.all(
      dependants.map(async (name) => {
        paint(name, await requestSection(name, listing, postcode));
      })
    );
  })();

  await Promise.all([...coordWork, postcodeWork]);

  // Attribution and the debug line go in once everything has settled: both are
  // summaries over the whole response set, so painting them early would mean
  // rewriting them.
  const sources = renderSources(Object.values(results));
  if (sources) parts.push(sources);

  const fromCache = Object.values(results).some((r) => r?.fromCache);

  // Debug line. Which extraction strategy won, the outcode we parsed, the
  // coordinates, and whether this came from cache. When Rightmove ships a
  // redesign this is the first thing to read: a silent fall-through to a weaker
  // strategy looks identical to success without it.
  //
  // The outcode is not used by either demo endpoint (both take lat/lon) but is
  // shown here because it IS the input the postcode-keyed endpoints will need
  // — /v1/score, /epc and /sold-prices. Surfacing it now means its accuracy is
  // being observed before anything depends on it.
  const debug = el(
    'div',
    'c33-debug',
    [
      listing.source,
      listing.outcode || 'no-outcode',
      `${listing.lat.toFixed(4)}, ${listing.lon.toFixed(4)}`,
      fromCache ? 'cached' : null,
    ]
      .filter(Boolean)
      .join(' · ')
  );
  parts.push(debug);

  // append, NOT replaceChildren. The sections are already in the DOM — they
  // painted as each upstream answered. Replacing here would wipe them and
  // undo the whole point of the incremental render.
  body.append(...parts);
}

// --- Badge (the click target) --------------------------------------------
// Nothing is fetched until this is pressed. See the file header.

function removeBadge() {
  document.getElementById(BADGE_ID)?.remove();
}

/**
 * The badge mark: a miniature of the scale bar the panel is built from.
 *
 * A track, a threshold tick, and a dot sitting past it. It is the same shape as
 * every reading inside — the WHO bars, the MEES tick, the asking-price marker —
 * so the button previews what clicking it gives you rather than just spelling
 * the name. Drawn rather than an image file so it inherits currentColor and
 * needs no web-accessible resource declaration in the manifest.
 */
function badgeMark() {
  const svg = svgEl('svg', {
    class: 'c33-badge-mark',
    width: 18,
    height: 12,
    viewBox: '0 0 18 12',
    'aria-hidden': 'true',
    focusable: 'false',
  });
  // r=2.6 on a 2px track, not r=3: the first cut read as a lollipop rather than
  // a marker on a scale. The dot has to sit ON the track, not swallow it.
  svg.appendChild(svgEl('rect', { x: 0, y: 5, width: 18, height: 2, rx: 1, opacity: 0.35 }));
  svg.appendChild(svgEl('rect', { x: 0, y: 5, width: 10, height: 2, rx: 1 }));
  svg.appendChild(svgEl('rect', { x: 13.2, y: 1.5, width: 1.2, height: 9, rx: 0.6 }));
  svg.appendChild(svgEl('circle', { cx: 10, cy: 6, r: 2.6 }));
  return svg;
}

function showBadge(listing) {
  removeBadge();

  const badge = el('button', null);
  badge.id = BADGE_ID;
  badge.type = 'button';
  badge.appendChild(badgeMark());
  badge.appendChild(el('span', 'c33-badge-word', 'cubitt33'));
  badge.setAttribute('aria-label', 'Show cubitt33 property data for this listing');

  badge.addEventListener('click', () => {
    const plan = decidePresentation(listing);
    if (plan.show === 'nothing') return;
    removeBadge();
    const body = buildPanel(listing, plan);
    loadInto(body, listing, plan);
  });

  document.body.appendChild(badge);
}

function run() {
  removePanel();
  removeBadge();

  const listing = extractListing();
  const plan = decidePresentation(listing);

  // show === 'nothing' means we could not locate the property. Render no UI at
  // all — an inert badge on a page we cannot serve is a promise we then break.
  if (plan.show === 'nothing') return;

  showBadge(listing);
}

// Rightmove routes between listings client-side, so a full page load is not
// guaranteed between one property and the next. Poll the URL rather than
// installing a MutationObserver over a page this size — the observer would fire
// on every lazy-loaded image for a signal we can read in one string compare.
let lastHref = location.href;
setInterval(() => {
  if (location.href !== lastHref) {
    lastHref = location.href;
    // Let the new page's scripts populate the DOM before extracting; the
    // coordinates are written by their router, not present at navigation time.
    setTimeout(run, 800);
  }
}, 1000);

run();
