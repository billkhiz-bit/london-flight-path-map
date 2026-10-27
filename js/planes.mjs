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
      return { kind, label, share: `${a.share_pct[kind]}% of days`, text: perDay(v), bar: barOf(v, info.bar_full || 1), range: Array.isArray(v) };
    });
    const [west, east] = [inWords(figs[col.westerly]), inWords(figs[col.easterly])];
    const wind = `Planes land and take off into the wind, so the weather decides which way ${name} flies, and that decides your day`
      + (west && east ? `: here, ${west} on a day it flies west and ${east} on a day it flies east.` : '.');
    return { code, name, rows, wind, period: period(a.months) };
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

/** The block's nodes for a model, written with textContent only. */
export function planesNodes(model, doc = document) {
  const el = (tag, className, text) => {
    const n = doc.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  };
  const out = [el('h3', 'planes-h', model.heading), el('p', 'planes-sub', model.sub)];
  for (const a of model.airports) {
    if (model.airports.length > 1) out.push(el('h4', 'planes-airport', a.name));
    const rows = el('div', 'rows');
    for (const r of a.rows) {
      const row = el('div', 'row');
      const label = el('span', null, r.label);
      label.append(el('small', null, r.share));
      const bar = el('span', 'bar');
      bar.setAttribute('aria-hidden', 'true');
      if (r.bar) {
        const fill = el('i', r.range ? 'range' : null);
        fill.style.left = `${(r.bar[0] * 100).toFixed(1)}%`;
        fill.style.width = `${Math.max(1, (r.bar[1] - r.bar[0]) * 100).toFixed(1)}%`;
        bar.append(fill);
      }
      row.append(label, bar, el('span', 'val', r.text));
      rows.append(row);
    }
    out.push(rows, el('p', 'planes-wind', a.wind));
  }
  for (const [key, className] of [['none', 'planes-none'], ['edge', 'planes-note'], ['approx', 'planes-note'], ['other', 'planes-warn']]) {
    if (model[key]) out.push(el('p', className, model[key]));
  }
  out.push(el('p', 'planes-note', model.definition), el('p', 'planes-note', `${model.counted} ${model.credits.join('; ')}.`));
  const how = el('p', 'planes-how');
  const link = el('a', null, 'How the planes are counted');
  link.href = model.how;
  how.append(link);
  out.push(how);
  return out;
}
