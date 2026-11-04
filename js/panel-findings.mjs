/**
 * The full map's panel, findings first (Bill's pick, 2026-11-04: Stitch's draft, after four rounds of charts).
 *
 * Each finding says one thing in plain words, then its number. A chart appears only where there is a real comparison:
 * the air charts, and crime against the London median. Everything here is pure text, so Node tests it
 * (tests/panel-findings.mjs); the panel only places what comes back.
 *
 * Two rules hold throughout. ABSENCE: a function with nothing true to say returns null and the panel shows nothing,
 * never a default. WHOSE FIGURE: road noise leads with the council's rating and explains it with the postcode's own
 * figure (Bill's call, 2026-11-04: Stitch's "Road noise is high" explains it better). A rating can therefore sit above
 * a figure under the guideline: Kensington and Chelsea is rated high, and SW5 9JZ reads 49.9 dB in the same ward as
 * SW5 9HP at 71.8. Bill saw that case and chose it; the group's note says whose rating it is. With no postcode figure
 * the rating names its council. A surveyed-quiet bound keeps its own words: it says the postcode is quiet, not a rating.
 */

const esc = (v) => String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
const words = (s) => String(s).trim().toLowerCase();
const clamp = (v) => Math.max(0, Math.min(100, v));
const HOME_TYPES = new Set(['flat-maisonette', 'terraced', 'semi-detached', 'detached']);
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
  'November', 'December'];

/**
 * Road noise. `db` is the postcode's reading, under the council's rating (`band`), or under the plain fact where the
 * council has none. `belowDb` is a surveyed-quiet bound, which is NOT a reading (DEFRA mapped none at or above it), so
 * it gets no bar and no figure of its own. Without either, the council's rating, named as such.
 */
export function roadFinding({ db, belowDb, who, period, council, band, abovePct, area = 'council', spot = 'postcode' } = {}) {
  if (isNum(db) && isNum(who)) {
    const side = db > who ? 'over' : db < who ? 'under' : 'at';
    return {
      key: 'road',
      head: band ? `Road noise is ${words(band)}` : `Road noise is ${side} the WHO guideline`,
      note: band && council ? `The road noise rating is for all of ${council}. The figures are for this ${spot}.` : null,
      detail: `${db.toFixed(1)} dB. The WHO guideline is ${who} dB. This is a modelled figure${period ? ` for ${period}` : ''}.`,
      gauge: { value: clamp(db), tick: clamp(who), caption: `WHO guideline ${who} dB`, text: `${db.toFixed(1)} dB` },
    };
  }
  if (isNum(belowDb)) {
    const under = isNum(who) && belowDb <= who;
    return {
      key: 'road',
      head: under ? 'Road noise is under the WHO guideline' : "Road noise is below DEFRA's mapped levels",
      detail: `DEFRA surveyed this ${spot} and mapped none at or above ${belowDb} dB.`,
    };
  }
  if (council && band) {
    const share = isNum(abovePct) ? `: ${Math.round(abovePct)}% of its ${spot}s are over the WHO guideline` : '';
    return {
      key: 'road',
      head: `Road noise in ${council} is ${words(band)}`,
      detail: `A rating for the whole ${area}${share}. There is no figure for this ${spot}.`,
    };
  }
  return null;
}

/** Aircraft noise, out of 10. The word comes with the figure from the panel's noiseBand(), the one holder of its bands. */
export function aircraftFinding({ score, word, modelled = false } = {}) {
  if (!isNum(score) || !word) return null;
  const s = Math.max(0, Math.min(10, score)).toFixed(1);
  return {
    key: 'aircraft',
    head: `Aircraft noise is ${words(word)}`,
    detail: modelled ? `${s} out of 10, from DEFRA's noise map, modelled.` : `${s} out of 10, an estimate from the routes.`,
    gauge: { value: clamp(score * 10) },
  };
}

/** Planes overhead, only ever from planesModel() (js/planes.mjs): the wording rule allows no other route. */
export function planesFindings(model) {
  if (!model) return [];
  // A caveat that changes what a figure means stays with the figure, never in the fold (a range, a place that is only
  // approximate, other flying over a quiet count).
  const caveats = [model.edge, model.approx, model.other].filter(Boolean);
  if (!model.airports.length) return model.none ? [{ key: 'planes', head: model.heading, detail: model.none, caveats }] : [];
  const found = model.airports.map((a) => ({
    key: 'planes',
    head: `${a.name} planes overhead`,
    detail: `On an average day of each kind, ${a.period}.`,
    rows: a.rows.map((r) => [`${r.label}: ${r.text}`, r.share]),
  }));
  found.at(-1).caveats = caveats;
  return found;
}

/** What sits behind the planes figures, from the same model: the wind, the definition, the credits. */
export function planesNotes(model) {
  if (!model) return [];
  const notes = [...model.airports.map((a) => a.wind), model.definition];
  return [...notes, `${model.counted} ${(model.credits || []).join('; ')}.`].filter(Boolean);
}

/** Those notes, folded, with the way to the full method. Nothing for a postcode with no figures. */
export function planesNotesHtml(model) {
  const notes = planesNotes(model);
  if (!notes.length) return '';
  const body = notes.map((n) => `<p class="info-note">${esc(n)}</p>`).join('');
  return `<details class="legend-disclosure air-about"><summary>About these figures</summary>${body}`
    + `<p class="info-note"><a href="${esc(model.how)}">More on how it works</a></p></details>`;
}

/** The nearest published flight path, from the same analysis as the panel's key facts. */
export function pathFinding(km) {
  return isNum(km) ? { key: 'path', rows: [['Nearest flight path', `${km.toFixed(1)} km`]] } : null;
}

/** A council-wide rating in plain words: "Flood risk is low". Nothing to say without a rating. */
export function ratingFinding(key, name, rating) {
  if (!rating || words(rating) === 'not recorded') return null;
  return { key, head: `${name} ${name.endsWith('Schools') ? 'are' : 'is'} ${words(rating)}` };
}

/**
 * Crime is council-wide and said so. Against the London median only where the figures compare (`comparable`: New
 * York's come from a different source). The two amounts get a bar each, from a true zero, on one scale.
 */
export function crimeFinding({ band, rate, median, comparable = true, area = 'council', estimated = false } = {}) {
  const hasRate = isNum(rate);
  if (!band && !hasRate) return null;
  if (!hasRate) return { key: 'crime', head: `Crime is ${words(band)}` };
  // ONS publishes no rate for the City of London: the figure is ours, and the sentence says so.
  const rateLine = estimated
    ? `${rate} offences per 1,000 residents a year across the whole ${area}, Sky Score's estimate`
    : `${rate} recorded offences per 1,000 residents a year across the whole ${area}`;
  if (!comparable || !isNum(median) || median <= 0) {
    return { key: 'crime', head: band ? `Crime is ${words(band)}` : 'Recorded crime', detail: `${rateLine}.` };
  }
  const ratio = rate / median;
  const m = median.toFixed(1);
  const against = ratio >= 1.15
    ? `${ratio.toFixed(1)} times the London median of ${m}`
    : ratio <= 0.85
      ? `${(1 / ratio).toFixed(1)} times lower than the London median of ${m}`
      : `close to the London median of ${m}`;
  const top = Math.max(rate, median) * 1.12;
  return {
    key: 'crime',
    // With no council band the comparison is the finding, in the area pages' words; the figure then stands under it once.
    head: band ? `Crime is ${words(band)}` : `${estimated ? 'Estimated' : 'Recorded'} crime is ${against}`,
    detail: band ? `${rateLine}, ${against}.` : `${rateLine}.`,
    amounts: [[`This ${area}`, rate, clamp((rate / top) * 100), true], ['London median', m, clamp((median / top) * 100), false]],
  };
}

/** A name and distance the panel already lists, under a rating. The rating alone if the list has nothing yet. */
export function nearestFinding(key, name, rating, nearest) {
  const f = ratingFinding(key, name, rating);
  const row = nearest && nearest.name ? [nearest.name, String(nearest.dist || '').replace(/^(\d+)m$/, '$1 m')] : null;
  if (!f) return row ? { key, head: name, rows: [row] } : null;
  return row ? { ...f, rows: [row] } : f;
}

/** The council's average price and its trend. `trend` is the record's own text, such as "-13.8%". */
export function priceFinding({ price, trend, area = 'council' } = {}) {
  if (!price) return null;
  const m = /^([+-]?)(\d+(?:\.\d+)?)%$/.exec(String(trend ?? '').trim());
  const moved = m ? (Number(m[2]) === 0 ? 'unchanged in a year.' : `${m[1] === '-' ? 'down' : 'up'} ${m[2]}% in a year.`) : null;
  return { key: 'price', label: `Average price in the ${area === 'council' ? 'council area' : area}`, big: price, detail: moved };
}

/** The latest standard sale of a home here: only a known home type in category A may carry the label; unknown is not a home. */
export function soldFinding(sold, format) {
  if (!Array.isArray(sold)) return null;
  const s = sold.find((r) => r && isNum(r.price) && HOME_TYPES.has(r.type) && r.category === 'A');
  if (!s) return null;
  const d = /^(\d{4})-(\d{2})/.exec(String(s.date || ''));
  const month = d && MONTHS[Number(d[2]) - 1];
  return { key: 'sold', label: 'Last home sold at this postcode', rows: [[format(s.price), month ? `${month} ${d[1]}` : '']], strong: true };
}

/** The energy ratings the register holds here. Nothing while it is unavailable, or with no certificates. */
export function epcFinding(data) {
  const s = data && data.available && data.count > 0 ? data.summary : null;
  if (!s || !/^[A-G]$/.test(String(s.averageBand))) return null;
  const rating = isNum(Number(s.averageRating)) && s.averageRating !== '' && s.averageRating != null ? Number(s.averageRating) : null;
  const scale = rating === null ? '' : `${rating} out of 100, `;
  return {
    key: 'epc',
    head: `Energy rating ${s.averageBand}`,
    detail: `${scale}from ${data.count} certificate${data.count === 1 ? '' : 's'}.`,
    gauge: rating === null ? null : { value: clamp(rating) },
  };
}

function gaugeHtml(g) {
  const cap = g.caption ? `<div class="find-cap"><span>${esc(g.caption)}</span><b>${esc(g.text)}</b></div>` : '';
  const tick = isNum(g.tick) ? `<u style="left:${g.tick}%"></u>` : '';
  return `${cap}<div class="find-track" aria-hidden="true"><i style="width:${g.value}%"></i>${tick}</div>`;
}

/** One finding as the panel shows it; '' for nothing, so an absent finding leaves no trace. */
export function findingHtml(f) {
  if (!f) return '';
  const note = f.note ? `<p class="find-note">${esc(f.note)}</p>` : '';
  const label = f.label ? `<p class="find-d">${esc(f.label)}</p>` : '';
  const head = f.head ? `<p class="find-h">${esc(f.head)}</p>` : '';
  const big = f.big ? `<p class="find-h find-big">${esc(f.big)}</p>` : '';
  const detail = f.detail ? `<p class="find-d">${esc(f.detail)}</p>` : '';
  const gauge = f.gauge ? gaugeHtml(f.gauge) : '';
  const amounts = (f.amounts || []).map(([name, text, width, here]) => `<div class="find-cap"><span>${esc(name)}</span><b>${esc(text)}</b></div>`
    + `<div class="find-track" aria-hidden="true"><i class="${here ? '' : 'find-yardstick'}" style="width:${width}%"></i></div>`).join('');
  const rows = (f.rows || []).map(([a, b]) => `<div class="find-row${f.strong ? ' find-strong' : ''}"><span>${esc(a)}</span><b>${esc(b)}</b></div>`).join('');
  const caveats = (f.caveats || []).map((c) => `<p class="find-d find-caveat">${esc(c)}</p>`).join('');
  return `<div class="find" data-finding="${esc(f.key)}">${note}${label}${head}${big}${detail}${gauge}${amounts}${rows}${caveats}</div>`;
}
