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
    definition: `${info.definition} ${info.direction_rule}`,
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
    // The hero's third tile: the commonest one-way kind of day, or nothing if that day has no planes to tell.
    lead: lead && said(leadWords) ? { figure: shortFigure(lead.value), words: `planes a day, flying ${DIR[lead.kind]}` } : null,
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

/** What the block's figures rest on, for the fold under the answer: why the days differ, what overhead means, who counted. */
export function planesNotes(model, doc = document) {
  const para = (text, className = 'planes-note') => {
    const n = doc.createElement('p');
    n.className = className;
    n.textContent = text;
    return n;
  };
  const how = para('', 'planes-how');
  const link = doc.createElement('a');
  link.textContent = 'More on how it works';
  link.href = model.how;
  how.append(link);
  const out = [];
  for (const a of model.airports) out.push(para(a.wind), daysBar(a, doc));
  const cone = overheadCone(model.definition, doc);
  if (cone) out.push(cone);
  out.push(para(model.definition), para(`${model.counted} ${model.credits.join('; ')}.`), how);
  return out;
}

// How an airport's days split, as one bar: each kind of day its true share, every share also said in words.
function daysBar(airport, doc) {
  const box = doc.createElement('div');
  box.className = 'planes-days';
  const cap = doc.createElement('p');
  cap.className = 'planes-days-h';
  cap.textContent = `How ${airport.name}'s days split`;
  const bar = doc.createElement('div');
  bar.className = 'planes-days-bar';
  bar.setAttribute('role', 'img');
  bar.setAttribute('aria-label', airport.rows.map((r) => `${r.label}, ${r.share}`).join('; '));
  airport.rows.forEach((r, i) => {
    const part = doc.createElement('span');
    part.className = `planes-day-${i}`;
    part.style.width = `${r.sharePct ?? 0}%`;
    part.textContent = `${r.sharePct ?? 0}%`;
    bar.append(part);
  });
  const key = doc.createElement('p');
  key.className = 'planes-days-key';
  key.setAttribute('aria-hidden', 'true');
  airport.rows.forEach((r, i) => {
    const item = doc.createElement('span');
    const swatch = doc.createElement('i');
    swatch.className = `planes-day-${i}`;
    item.append(swatch, r.label);
    key.append(item);
  });
  box.append(cap, bar, key);
  return box;
}

// The overhead rule, drawn: a cone over a home, its angle true to the rule. The two figures are read from the definition the
// page already holds, so a change to the rule cannot leave a stale drawing: no figures found, no drawing.
function overheadCone(definition, doc) {
  const angle = /([\d.]+) degrees/.exec(definition || '')?.[1];
  const ceiling = /below ([\d,]+) ft/.exec(definition || '')?.[1];
  if (!angle || !ceiling) return null;
  const NS = 'http://www.w3.org/2000/svg';
  const draw = (tag, attrs, text) => {
    const n = doc.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (text != null) n.textContent = text;
    return n;
  };
  const baseX = 170;
  const groundY = 134;
  const topY = 22;
  const spread = (groundY - topY) / Math.tan((Number(angle) * Math.PI) / 180);
  const svg = draw('svg', { viewBox: '0 0 340 150', class: 'planes-cone', role: 'img', 'aria-label': `Overhead means inside this cone: at least ${angle} degrees up the sky from your home, and below ${ceiling} ft.` });
  svg.append(
    draw('path', { d: `M${baseX} ${groundY} L${baseX - spread} ${topY} L${baseX + spread} ${topY} Z`, class: 'cone-fill' }),
    draw('line', { x1: baseX - spread - 26, y1: topY, x2: baseX + spread + 26, y2: topY, class: 'cone-top' }),
    draw('line', { x1: 8, y1: groundY, x2: 332, y2: groundY, class: 'cone-ground' }),
    draw('path', { d: `M${baseX - 9} ${groundY} v-11 l9 -8 l9 8 v11 Z`, class: 'cone-home' }),
    draw('text', { x: baseX + spread + 4, y: topY - 6, class: 'cone-label', 'text-anchor': 'end' }, `${ceiling} ft`),
    draw('text', { x: baseX + 24, y: groundY - 6, class: 'cone-label' }, `${angle}\u00b0`),
    draw('circle', { cx: baseX - 22, cy: 58, r: 5, class: 'cone-in' }),
    draw('text', { x: baseX - 22, y: 76, class: 'cone-label', 'text-anchor': 'middle' }, 'counted'),
    draw('circle', { cx: baseX + spread + 22, cy: 58, r: 5, class: 'cone-out' }),
    draw('text', { x: baseX + spread + 22, y: 76, class: 'cone-label', 'text-anchor': 'middle' }, 'not counted'),
  );
  return svg;
}
