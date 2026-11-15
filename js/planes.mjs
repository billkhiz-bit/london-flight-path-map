/**
 * Planes overhead, in the front page's answer: what one postcode is told, and the block that tells it.
 *
 * WHY THIS EXISTS (2026-10-26). Bill's rulings: how often planes pass is told by the way each airport flies
 * (Kew reads ~310 on a day Heathrow flies west and ~4 on a day it flies east, and an average of the two is true
 * on no day), from static files per postcode district (scripts/build_planes_overhead.py), first in the front
 * page's answer. The design is the mock-up he chose on 25 Oct (claude.ai/artifact/RB3MHZJ8uZxmnqV9ZJtJyc).
 *
 * The files hold only airports whose tracking passed the CAA check in every month, so whatever is listed may
 * be said. What is NOT in a file is never filled in: a postcode in no list was not measured and the block stays
 * hidden; a kind of day with no figure reads "not measured", never 0; a figure on a cone's edge is a range.
 *
 * planesModel() is pure (no DOM), so Node tests it (tests/planes-model.mjs); planesNodes() writes it with
 * textContent only. Runs in the browser and in Node alike.
 */

import { AIRPORT_NAME } from './flight_geometry.mjs';
import { esc } from './street_report.mjs';

/** The rows, in the mock-up's order: the file's own order is westerly, easterly, mixed (airports.json classes). */
const KINDS = [['westerly', 'Flying west', 'west'], ['mixed', 'Both ways', null], ['easterly', 'Flying east', 'east']];
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
  'November', 'December'];
const WORDS = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve'];

export const HOW_LINK = '/how-it-works/#planes-overhead';

/** The postcode as the files key it: upper case, one space. */
export const normalPostcode = (pc) => String(pc).toUpperCase().replace(/\s+/g, ' ').trim();
/** Its district (the outward code), the file it is in. */
export const districtOf = (pc) => normalPostcode(pc).split(' ')[0];

const one = (v) => (v === '<1' ? 'under 1' : String(v));
/** A figure as the row shows it. */
export function perDay(v) {
  if (v == null) return 'not measured';
  if (v === 0) return 'none';
  if (Array.isArray(v)) return v[0] === 0 ? `up to ${one(v[1])} a day` : `${one(v[0])} to ${one(v[1])} a day`;
  return `${one(v)} a day`;
}
/** A figure inside a sentence ("about 310", "under 1", "none"); null for a range or no figure. */
function inWords(v) {
  if (v == null || Array.isArray(v)) return null;
  if (v === 0) return 'none';
  return v === '<1' ? 'under 1' : `about ${v}`;
}
/** "January to August 2026" from ['202601', '202608']. */
export function period([first, last]) {
  const [y1, m1, y2, m2] = [first.slice(0, 4), +first.slice(4), last.slice(0, 4), +last.slice(4)];
  return y1 === y2 ? `${MONTHS[m1 - 1]} to ${MONTHS[m2 - 1]} ${y2}` : `${MONTHS[m1 - 1]} ${y1} to ${MONTHS[m2 - 1]} ${y2}`;
}
const listOf = (names) => (names.length > 1 ? `${names.slice(0, -1).join(', ')} and ${names.at(-1)}` : names[0]);
/** Where a bar starts and ends, as shares of the scale: a range spans its two ends. */
function barOf(v, full) {
  if (v == null || v === 0 || v === '<1') return null;
  const f = (x) => Math.min(1, (x === '<1' ? 0 : x) / full);
  return Array.isArray(v) ? [f(v[0]), f(v[1])] : [0, f(v)];
}

/**
 * What `postcode` is told, from its district's file and airports.json; null when it is in neither list (not
 * measured: say nothing). `names` is the airport-name table (AIRPORT_NAME), passed in for tests.
 */
export function planesModel(file, info, postcode, names = AIRPORT_NAME) {
  if (!file || !info?.airports) return null;
  const pc = normalPostcode(postcode);
  const listed = file.postcodes?.[pc];
  const none = (file.none || []).includes(pc);
  if (!listed && !none) return null;
  const counted = Object.keys(info.airports).length;
  const col = Object.fromEntries((info.classes || []).map((c, i) => [c, i]));
  const airports = Object.entries(listed || {}).filter(([code]) => info.airports[code]).map(([code, figs]) => {
    const a = info.airports[code];
    const name = names[code] || code;
    const rows = KINDS.map(([kind, label]) => {
      const v = figs[col[kind]];
      return { kind, label, share: `${a.share_pct[kind]}% of days`, sharePct: a.share_pct[kind], text: perDay(v), value: v ?? null, bar: barOf(v, info.bar_full || 1), range: Array.isArray(v) };
    });
    const [west, east] = [inWords(figs[col.westerly]), inWords(figs[col.easterly])];
    const wind = `Planes land and take off into the wind, so the weather decides which way ${name} flies, and that decides your day`
      + (west && east ? `: here, ${west} on a day it flies west and ${east} on a day it flies east.` : '.');
    return { code, name, rows, wind, windShort: `The wind decides which way ${name} flies, and that decides your day.`, period: period(a.months) };
  });
  // Listed only under airports airports.json no longer publishes (a district file older than it): nothing left
  // to say, so say nothing, as for a postcode never measured. An empty block would read as a measurement.
  if (!airports.length && !none) return null;
  const periods = [...new Set(airports.map((a) => a.period))];
  return {
    postcode: pc,
    airports,
    heading: 'Planes overhead',
    sub: airports.length
      ? `From ${listOf(airports.map((a) => a.name))}, on an average day of each kind, ${periods.join('; ')}`
      : `From the ${WORDS[counted] || counted} airports we count`,
    none: none ? `Under 1 a day from each of the ${WORDS[counted] || counted} airports we count, whichever way they fly.` : null,
    edge: airports.some((a) => a.rows.some((r) => r.range))
      ? 'A range means this postcode is on the edge of a flight path, where a few metres decide whether a plane counts as overhead: it gives the fewest and the most within 100 m.'
      : null,
    approx: (file.approx || []).includes(pc)
      ? "This postcode's position is approximate (ONS gives it an estimated one), so these figures may be for a spot a few hundred metres away."
      : null,
    other: (file.other || []).includes(pc)
      ? 'Other flying passes over here too, from airfields, helicopters and airports we cannot check against official counts, so few planes from the airports we count does not mean a quiet sky.'
      : null,
    // The large-user rule (2026-11-10) only when the file carries it: a cached older airports.json mid-deploy never
    // prints "undefined" (scripts/build_planes_overhead.py POSTCODES_RULE).
    definition: [info.definition, info.direction_rule, info.postcodes_rule].filter((s) => typeof s === 'string' && s).join(' '),
    // The same three sentences apart, for the fold that sets each on its own line (2026-11-11): word for word, never
    // shortened, so every surface still says what How it works says. A sentence the file lacks is null, never "undefined".
    rules: Object.fromEntries([['overhead', info.definition], ['direction', info.direction_rule], ['postcodes', info.postcodes_rule]]
      .map(([k, s]) => [k, typeof s === 'string' && s ? s : null])),
    counted: `Counted from community flight tracking, checked against the CAA's monthly totals for ${airports.length ? listOf(airports.map((a) => a.name)) : 'each airport'}.`,
    credits: info.credits || [],
    how: HOW_LINK,
  };
}

/**
 * Where to go next from a postcode's block (2026-11-02, Bill: "make the links clear and easy to navigate"): its
 * district's page, when one is built, and while Heathrow's consultation is open, the pack, when the postcode has a
 * Heathrow figure. `index` is data/planes-districts-by-council.json (scripts/build_planes_pages.py), the one holder of
 * which pages exist: a district listed under no council has no page, so no link, never a guess at one. No index (a
 * failed fetch) means no links; the block itself still shows. `today` decides whether the consultation is open.
 */
export function planesLinks(index, postcode, model, today = new Date()) {
  if (!index?.councils || !model) return [];
  const d = districtOf(postcode);
  const out = [];
  if (Object.values(index.councils).some((ds) => Array.isArray(ds) && ds.includes(d))) {
    out.push({ text: `Every postcode in ${d}, sector by sector`, href: `/planes-overhead/${d.toLowerCase()}/` });
  }
  const c = index.consultation;
  const open = c?.hub && /^\d{4}-\d{2}-\d{2}$/.test(c.until || '') && today.toISOString().slice(0, 10) <= c.until;
  if (open && model.airports.some((a) => a.code === c.airport)) {
    const [, m, day] = c.until.split('-').map(Number);
    out.push({ text: `For Heathrow's consultation, open until ${day} ${MONTHS[m - 1]}: the planes over each council`, href: c.hub });
  }
  return out;
}

// ---- the front page's walkthrough, step 04 (front-page-v3, 2026-11-03: Bill's mock v8 v12) ----
// One airport's answer in a sentence, then its three kinds of day as bars, each with its share of days, coloured as the
// full map's planes layer colours that figure (scripts/build_planes_layer.py's steps, read from the layer's index.json).
// Everything comes from a planesModel(), so the walkthrough can only say what the answer above it says.

/** The most a figure can be: a range's top, '<1' as 0, no figure -1. */
const mostOf = (v) => (v == null ? -1 : v === '<1' ? 0 : Array.isArray(v) ? mostOf(v[1]) : v);
/** A figure as the walkthrough's bars print it, without "a day" (the heading says it once). */
export function shortFigure(v) {
  if (v == null) return 'not measured';
  if (v === 0) return 'none';
  if (Array.isArray(v)) return v[0] === 0 ? `up to ${one(v[1])}` : `${one(v[0])} to ${one(v[1])}`;
  return one(v);
}
/**
 * The planes layer's colour for a figure: the highest of `steps` ([{from, colour}], the layer's index.json) it
 * reaches, judged on a range's top as the layer judges an edge's busier end; null under the first step (the layer draws
 * nothing there) or without steps.
 */
export function stepColour(v, steps = []) {
  const n = mostOf(v);
  let colour = null;
  for (const s of steps || []) if (typeof s?.from === 'number' && n >= s.from && /^#[0-9a-f]{6}$/i.test(s.colour || '')) colour = s.colour;
  return colour;
}
const DIR = { westerly: 'west', easterly: 'east' };
const said = (w) => w && w !== 'none' && w !== 'under 1';
/**
 * The airport to tell (the busiest, by its top figure) and its commonest one-way kind of day, in words: shared by the
 * walkthrough's sentence and option C's headline (planesLead), so the two always pick the same day and figure.
 */
function leadDay(model) {
  const a = model.airports.reduce((best, x) => (Math.max(...x.rows.map((r) => mostOf(r.value))) > Math.max(...best.rows.map((r) => mostOf(r.value))) ? x : best));
  const by = Object.fromEntries(a.rows.map((r) => [r.kind, r]));
  const lead = ['westerly', 'easterly'].map((k) => by[k]).filter(Boolean).sort((x, y) => (y.sharePct ?? 0) - (x.sharePct ?? 0))[0];
  const other = lead && by[lead.kind === 'westerly' ? 'easterly' : 'westerly'];
  return { a, lead, other, leadWords: lead && inWords(lead.value), otherWords: other && inWords(other.value) };
}
/**
 * Step 04's content from a planesModel(): { sentence: [{ text, strong }], rows, foot, how }, or null when the model has
 * no airport to tell (then the step shows no figure). With several airports it tells the busiest, by its top figure.
 * The sentence leads with the commonest kind of day only where that kind is one way and more than half of all days
 * ("On most days"); anything else takes the model's own wind sentence.
 */
export function planesWalk(model, steps = []) {
  if (!model?.airports?.length) return null;
  const { a, lead, other, leadWords, otherWords } = leadDay(model);
  const sentence = lead && (lead.sharePct ?? 0) > 50 && said(leadWords) && otherWords
    ? [{ text: 'On most days, ' }, { text: `${leadWords} planes a day`, strong: true },
      { text: ` pass over ${model.postcode}: the days ${a.name} flies ${DIR[lead.kind]}. On a day it flies ${DIR[other.kind]}, ` },
      { text: otherWords, strong: true }, { text: '.' }]
    : [{ text: a.wind }];
  return {
    airport: a.name,
    sentence,
    // The hero's third tile: the commonest one-way kind of day, or nothing if that day has no planes to tell. Its line
    // (Bill's pick A, 2026-11-13) is how often the airport flew that way over the counted period, read from the file;
    // `yardShort` is the same fact for a narrow tile.
    lead: lead && said(leadWords) ? {
      figure: shortFigure(lead.value),
      words: `planes a day, flying ${DIR[lead.kind]}`,
      yard: Number.isFinite(lead.sharePct) ? `${a.name} flew ${DIR[lead.kind]} on ${lead.sharePct}% of days` : null,
      yardShort: Number.isFinite(lead.sharePct) ? `${DIR[lead.kind].charAt(0).toUpperCase()}${DIR[lead.kind].slice(1)} on ${lead.sharePct}% of days` : null,
      over: false,
    } : null,
    rows: a.rows.map((r) => ({ kind: r.kind, label: r.label, share: r.share, figure: shortFigure(r.value), bar: r.bar, range: r.range, colour: stepColour(r.value, steps) })),
    foot: `Planes a day over ${model.postcode} from ${a.name}, ${a.period}. Never an average of the three: no day is average.`,
    how: model.how,
  };
}

/**
 * OPTION C, the answer as the headline (review prototype, 2026-11-07): the front page's h1 for this answer, when the
 * planes are what to lead with, or null. One clause, on planesWalk()'s own rule: "On most days" only where one way is over
 * half of all days and its figure is a single one (never a range); the busiest airport, NAMED, so a postcode under two
 * airports never reads as the sum of them. Only where the full map's planes layer would colour that figure (`steps`, the
 * layer's index.json, through stepColour()): under its first step the layer leaves a postcode blank, and a few planes a day
 * must not out-rank, say, a road far over its guideline; without the steps, never. Never with a caveat that changes what
 * the figure means, because a headline cannot carry one: a position ONS only estimates, or other flying the count cannot
 * see (the answer below keeps both, on their rows). Null in every such case, and the headline leads with something else.
 */
export function planesLead(model, steps = []) {
  if (!model?.airports?.length || model.approx || model.other) return null;
  const { a, lead, leadWords } = leadDay(model);
  if (!lead || (lead.sharePct ?? 0) <= 50 || !said(leadWords) || !stepColour(lead.value, steps)) return null;
  return `On most days, ${leadWords} ${a.name} planes a day pass over ${model.postcode}`;
}

/**
 * OPTION C, the quiet side (Bill, 2026-11-07: "answer the planes question before road noise"): where the postcode sits
 * in the band the full map's planes layer leaves blank, the heading says so AS THAT BAND ("Fewer than N", N the layer's
 * first step, read from `steps`, never typed), never a single figure. Only when it is true on every kind of day for every
 * airport the file lists: a kind not measured, or a range whose top reaches the step, is not "fewer than" and claims
 * nothing. The airports are only those airports.json publishes (the year rule's passers); a postcode with other flying
 * the count cannot see, or a position ONS only estimates, claims nothing. Per airport, never a sum: one airport is named,
 * several are each held to the band and said so; a postcode measured with nothing reaching 1 a day says it of each airport
 * we count. Null otherwise.
 */
export function planesBandLead(model, steps = []) {
  if (!model || model.approx || model.other) return null;
  const firsts = (steps || []).map((s) => s?.from).filter((n) => typeof n === 'number' && n > 0);
  if (!firsts.length) return null;
  const floor = Math.min(...firsts);
  if (!model.airports.length) return model.none ? `Fewer than ${floor} planes a day from each airport we count pass over ${model.postcode}` : null;
  const under = (a) => a.rows.length > 0 && a.rows.every((r) => r.value !== null && r.value !== undefined && mostOf(r.value) < floor);
  if (!model.airports.every(under)) return null;
  const names = model.airports.map((a) => a.name);
  return names.length === 1
    ? `Fewer than ${floor} ${names[0]} planes a day pass over ${model.postcode}`
    : `Fewer than ${floor} planes a day from each of ${listOf(names)} pass over ${model.postcode}`;
}

/** The block's nodes for a model, written with textContent only; `links` (planesLinks) go just above "How the planes are counted". */
export function planesNodes(model, doc = document, links = []) {
  const el = (tag, className, text) => {
    const n = doc.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  };
  const out = [el('h3', 'planes-h', model.heading), el('p', 'planes-sub', model.sub)];
  for (const a of model.airports) {
    if (model.airports.length > 1) out.push(el('h4', 'planes-airport', a.name));
    const kinds = el('div', 'planes-kinds');
    for (const r of a.rows) {
      const kind = el('div', 'planes-kind');
      kind.append(el('b', null, r.text), el('span', null, r.label), el('small', null, r.share));
      kinds.append(kind);
    }
    out.push(kinds, el('p', 'planes-wind', a.windShort));
  }
  for (const [key, className] of [['none', 'planes-none'], ['edge', 'planes-note'], ['approx', 'planes-note'], ['other', 'planes-warn']]) {
    if (model[key]) out.push(el('p', className, model[key]));
  }
  for (const l of links) {
    const p = el('p', 'planes-more');
    const a = el('a', null, l.text);
    a.href = l.href;
    p.append(a);
    out.push(p);
  }
  return out;
}

// ---- the planes chart (Bill's pick, 2026-11-10: "less text, like the air readings"; claude.ai/artifact/26UkCjWZSzhmQr28Loe2GK v2) ----
// The air chart's twin (js/street_report.mjs airChart): one row per kind of day, its share of days under its name, a dot
// at its figure, the same row height, label column and axis, so planes and air read alike. Behind the rows, the full map's
// planes layer steps (its index.json), so "100 or more a day" here is the colour it is on the map. Pure: SVG text, every
// name escaped, so the front page and the full map's tile set the same picture.

/** The scale's end: the first of these at or above the top figure plus a little room, so the busiest dot never sits on the edge. */
const CHART_ENDS = [10, 20, 50, 100, 200, 300, 400, 500, 600, 800, 1000, 1500, 2000];
/** Where a figure's dot goes: a range at its top (as the layer judges an edge), under 1 just off zero. */
const chartAt = (v) => (Array.isArray(v) ? chartAt(v[1]) : v === '<1' ? 0.5 : typeof v === 'number' ? v : null);
const NEUTRAL = '#9a9893';

/**
 * One airport's kinds of day on one scale, as SVG text, from a planesModel() airport. `steps` ([{from, colour}], the
 * layer's index.json) shade the bands and colour the dots; without them every dot is neutral and no band is drawn, never
 * a guessed colour. A kind with no figure says "not measured", never 0. A range is a bar from its fewest to its most,
 * its label above it. Every row carries data-kind and data-value for the tests.
 */
export function planesChart(airport, steps = []) {
  const rows = airport?.rows || [];
  const tops = rows.map((r) => chartAt(r.value)).filter((n) => typeof n === 'number');
  const max = CHART_ENDS.find((n) => n >= Math.max(10, ...tops) * 1.08) ?? CHART_ENDS.at(-1);
  const W = 352, L = 176, R = 18, rowH = 30, top = 16;
  const x0 = L, x1 = W - R;
  const x = (u) => +(x0 + (Math.min(Math.max(u, 0), max) / max) * (x1 - x0)).toFixed(2);
  const axisY = top + rows.length * rowH + 4;
  const H = axisY + 18;
  const bandSteps = (steps || []).filter((s) => typeof s?.from === 'number' && /^#[0-9a-f]{6}$/i.test(s.colour || '') && s.from < max)
    .sort((a, b) => a.from - b.from);
  const bands = bandSteps.map((s, i) => {
    const a = x(s.from), b = x(i + 1 < bandSteps.length ? bandSteps[i + 1].from : max);
    return `<rect data-band="${s.from}" x="${a}" y="${top - 4}" width="${(b - a).toFixed(2)}" height="${rows.length * rowH + 8}" fill="${s.colour}" fill-opacity="0.14"/>`;
  }).join('');
  const ink = 'fill:var(--air-ink, #141414)';
  const ink3 = 'fill:var(--air-ink-3, #636363)';
  const body = rows.map((r, i) => {
    const cy = top + i * rowH + rowH / 2;
    const head = `<text x="0" y="${cy - 2}" font-size="11.5" font-weight="600" style="${ink}">${esc(r.label ?? '')}</text>`
      + `<text x="0" y="${cy + 11}" font-size="10" style="${ink3}">${esc(r.share || '')}</text>`;
    const v = r.value;
    if (v == null) {
      return `<g data-kind="${esc(r.kind ?? '')}" data-value="">${head}<text x="${x1}" y="${cy + 4}" font-size="11" text-anchor="end" style="${ink3}">not measured</text></g>`;
    }
    const label = shortFigure(v);
    const cx = x(chartAt(v));
    const colour = stepColour(v, steps) || NEUTRAL;
    const range = Array.isArray(v);
    const textW = label.length * 6.5; // about 6.5 px a character at 11 px
    const left = cx > W - 52;
    // A range's label rides above its bar (on it, the two collide); one that would run into the name column starts at the bar.
    const rangeAnchor = cx - textW < x0 ? 'start' : 'end';
    const lead = !range && (left ? cx - 14 - textW : cx - 9) > x0
      ? `<line x1="${x0}" x2="${(left ? cx - 14 - textW : cx - 9).toFixed(2)}" y1="${cy}" y2="${cy}" stroke-width="2" style="stroke:var(--air-rule, #c8c7c4)"/>` : '';
    const bar = range ? `<line data-range="1" x1="${x(chartAt(v[0]))}" x2="${cx}" y1="${cy}" y2="${cy}" stroke-width="6" stroke-linecap="round" stroke="${colour}" stroke-opacity="0.45"/>` : '';
    const [tx, ty, anchor] = range ? [rangeAnchor === 'end' ? cx : x(chartAt(v[0])), cy - 9, rangeAnchor] : [left ? cx - 10 : cx + 10, cy + 4, left ? 'end' : 'start'];
    return `<g data-kind="${esc(r.kind ?? '')}" data-value="${esc(label)}"><title>${esc(`${r.label} (${r.share}): ${perDay(v)}`)}</title>${head}${lead}${bar}`
      + `<circle data-mark="planes" cx="${cx}" cy="${cy}" r="6" fill="${colour}"/>`
      + `<text x="${tx}" y="${ty}" font-size="11" font-weight="600" text-anchor="${anchor}" style="${ink};font-family:var(--font-mono, monospace)">${esc(label)}</text></g>`;
  }).join('');
  const ticks = [...new Set([0, ...bandSteps.map((s) => s.from).filter((f) => f >= max * 0.2), max])];
  const aria = `Planes overhead a day from ${airport?.name || ''}: ${rows.map((r) => `${r.label}${r.share ? ` (${r.share})` : ''}, ${perDay(r.value)}`).join('; ')}.`;
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(aria)}" data-planes-chart="${esc(airport?.code || airport?.name || '')}" data-max="${max}">`
    + bands + body
    + `<line data-axis="1" x1="${x0}" x2="${x1}" y1="${axisY}" y2="${axisY}" stroke-width="1" style="stroke:var(--air-ink-3, #636363)"/>`
    + ticks.map((t) => `<text x="${x(t)}" y="${axisY + 13}" font-size="9.5" text-anchor="${t === max ? 'end' : t === 0 ? 'start' : 'middle'}" style="${ink3};font-family:var(--font-mono, monospace)">${t}</text>`).join('')
    + '</svg>';
}

/**
 * What the block's figures rest on, for the fold under the answer (2026-11-11, Bill: "still text heavy"): each airport's
 * chart, the overhead rule beside a small drawing of it, the day rule, the CAA check and the PO-box rule as three short
 * points (each sentence word for word from airports.json, as How it works says it), then one sources line. The flight
 * tracks' credit stays in sight beside the figures (ODbL 4.3); every other source is one link away, on How it works.
 * `steps` (the layer's index.json) colour the chart; without them it is drawn in one neutral colour.
 */
export function planesNotes(model, doc = document, steps = []) {
  const el = (tag, className, text) => {
    const n = doc.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  };
  const link = (text, href) => Object.assign(el('a', null, text), { href });
  const out = [];
  for (const a of model.airports) {
    const fig = el('figure', 'walk-air planes-fig');
    fig.append(el('figcaption', null, `Planes overhead a day, from ${a.name}`));
    // planesChart() escapes every name; parsed by the HTML parser (a template), which gives an <svg> its namespace.
    const t = doc.createElement('template');
    t.innerHTML = planesChart(a, steps);
    const svg = t.content.querySelector('svg');
    if (svg) fig.append(svg);
    out.push(fig);
  }
  const rules = model.rules || {};
  if (rules.overhead) {
    const over = el('div', 'planes-over');
    const t = doc.createElement('template');
    t.innerHTML = overheadConeSvg(rules.overhead);
    const cone = t.content.querySelector('svg');
    if (cone) over.append(cone);
    over.append(el('p', null, rules.overhead));
    out.push(over);
  }
  const points = [['%', rules.direction], ['✓', model.counted], ['−', rules.postcodes]].filter(([, s]) => s);
  if (points.length) {
    const ul = el('ul', 'fold-keys');
    for (const [mark, text] of points) {
      const li = el('li');
      const b = el('b', null, mark);
      b.setAttribute('aria-hidden', 'true');
      li.append(b, el('span', null, text));
      ul.append(li);
    }
    out.push(ul);
  }
  const src = el('p', 'planes-how fold-src');
  if (model.credits?.[0]) src.append(`${model.credits[0]} · `);
  src.append(link('How it is counted', model.how), ' · ', link('All sources', '/how-it-works/#credits'));
  out.push(src);
  return out;
}

/**
 * The overhead rule, drawn small beside its sentence, as SVG text (the front page's fold and the full map's set the same
 * picture): a cone over a home, its angle true to the rule, a plane inside it counted and one outside it not. The angle is
 * read from the sentence it sits beside, so a change to the rule cannot leave a stale drawing: no angle found, ''. Hidden
 * from screen readers: the sentence beside it says all it shows. Only numbers go into it, never text.
 */
export function overheadConeSvg(sentence) {
  const angle = Number(/([\d.]+) degrees/.exec(sentence || '')?.[1]);
  if (!(angle > 0 && angle < 90)) return '';
  const baseX = 60, groundY = 62, topY = 10;
  const half = (y) => (groundY - y) / Math.tan((angle * Math.PI) / 180);
  const spread = half(topY);
  // The plane not counted sits just outside the cone's edge at its height; where the cone fills the picture, none is drawn.
  const outX = baseX + half(26) + 10;
  return '<svg viewBox="0 0 120 70" class="planes-cone" aria-hidden="true" focusable="false">'
    + `<line x1="4" y1="${topY}" x2="116" y2="${topY}" class="cone-top"/>`
    + `<path d="M${baseX} ${groundY} L${(baseX - spread).toFixed(1)} ${topY} L${(baseX + spread).toFixed(1)} ${topY} Z" class="cone-fill"/>`
    + `<circle cx="${baseX - 8}" cy="28" r="4.5" class="cone-in"/>`
    + `<path d="M${baseX - 6} ${groundY} v-6 l6 -5 l6 5 v6 Z" class="cone-home"/>`
    + `<line x1="2" y1="${groundY}" x2="118" y2="${groundY}" class="cone-ground"/>`
    + (outX <= 115 ? `<circle cx="${outX.toFixed(1)}" cy="26" r="4" class="cone-out"/>` : '')
    + '</svg>';
}
