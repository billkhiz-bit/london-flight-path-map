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

import { shortFigure, stepColour } from './planes.mjs';

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
export function roadFinding({ db, belowDb, who, period, council, band, abovePct, area = 'council', spot = 'postcode', source } = {}) {
  if (isNum(db) && isNum(who)) {
    const side = db > who ? 'over' : db < who ? 'under' : 'at';
    return {
      key: 'road',
      head: band ? `Road noise is ${words(band)}` : `Road noise is ${side} the WHO guideline`,
      note: band && council ? `The road noise rating is for all of ${council}. The figures are for this ${spot}.` : null,
      detail: `${db.toFixed(1)} dB. The WHO guideline is ${who} dB. This is a modelled figure${period ? ` for ${period}` : ''}.`,
      gauge: { value: clamp(db), tick: clamp(who), caption: `WHO guideline ${who} dB`, text: `${db.toFixed(1)} dB` },
      tile: {
        name: 'Road noise',
        level: band ? cap(words(band)) : `${cap(side)} the WHO level`,
        sub: band ? wide(council, area) : null,
        shared: Boolean(band),
        tone: band ? toneOf(band) : null,
        stand: band ? standOf(toneOf(band)) : null,
        pill: 'Road noise',
        visual: [
          band ? strip('road', words(band), toneOf(band)) : null,
          { kind: 'bars', rows: [{ label: `This ${spot}`, text: `${db.toFixed(1)} dB`, value: db, here: true }, { label: 'The WHO recommends at most', text: `${who} dB`, value: who }] },
        ],
        say: [band
          ? `The rating is for ${placeName(council, area)} as a whole; the bars are for this ${spot}.`
          : `Road noise here is ${side} the level the World Health Organization (WHO) recommends.`],
        tip: 'Visit at rush hour to hear it for yourself.',
        source: source ? `${source}${period ? `, ${period}` : ''}` : null,
      },
    };
  }
  if (isNum(belowDb)) {
    const under = isNum(who) && belowDb <= who;
    return {
      key: 'road',
      head: under ? 'Road noise is under the WHO guideline' : "Road noise is below DEFRA's mapped levels",
      detail: `DEFRA surveyed this ${spot} and mapped none at or above ${belowDb} dB.`,
      tile: {
        name: 'Road noise',
        level: under ? 'Under the WHO level' : 'Below mapped levels',
        sub: null,
        shared: false,
        tone: under ? 'good' : null,
        stand: null,
        pill: 'Road noise',
        visual: [],
        say: [`DEFRA\u2019s map shows no road noise here at ${belowDb} dB or above${under ? `, under the ${who} dB the World Health Organization (WHO) recommends` : ''}.`],
        source: source || null,
      },
    };
  }
  if (council && band) {
    const share = isNum(abovePct) ? `: ${Math.round(abovePct)}% of its ${spot}s are over the WHO guideline` : '';
    return {
      key: 'road',
      head: `Road noise in ${council} is ${words(band)}`,
      detail: `A rating for the whole ${area}${share}. There is no figure for this ${spot}.`,
      tile: {
        name: 'Road noise',
        level: cap(words(band)),
        sub: wide(council, area),
        shared: true,
        tone: toneOf(band),
        stand: standOf(toneOf(band)),
        pill: 'Road noise',
        visual: [
          strip('road', words(band), toneOf(band)),
          isNum(abovePct) ? { kind: 'share', pct: abovePct, of: `${council} ${spot}s louder than the World Health Organization (WHO) recommends` } : null,
        ],
        say: [`We have no reading for this ${spot === 'postcode' ? 'street' : spot}, so this is for ${council} as a whole.`],
        tip: 'Visit at rush hour to hear it for yourself.',
        source: source || null,
      },
    };
  }
  return null;
}

/** Aircraft noise, out of 10. The word comes with the figure from the panel's noiseBand(), the one holder of its bands. */
export function aircraftFinding({ score, word, modelled = false, source } = {}) {
  if (!isNum(score) || !word) return null;
  const s = Math.max(0, Math.min(10, score)).toFixed(1);
  return {
    key: 'aircraft',
    head: `Aircraft noise is ${words(word)}`,
    detail: modelled ? `${s} out of 10, from DEFRA's noise map, modelled.` : `${s} out of 10, an estimate from the routes.`,
    gauge: { value: clamp(score * 10) },
    tile: {
      name: 'Aircraft noise',
      level: cap(words(word)),
      sub: `${s} out of 10`,
      shared: false,
      tone: toneOf(word),
      stand: standOf(toneOf(word)),
      pill: 'Aircraft noise',
      visual: [strip('aircraft', words(word), toneOf(word))],
      say: modelled
        ? [`Averaged over a whole year, aircraft noise here is ${words(word)}.`,
          words(word) === 'high' ? null : 'An average spreads busy days over quiet ones, so some days are much louder than this.']
        : [`Our estimate from the published flight routes puts aircraft noise here at ${words(word)}.`],
      source: source || (modelled ? null : 'Sky Score estimate from published flight routes'),
    },
  };
}

/** Planes overhead, only ever from planesModel() (js/planes.mjs): the wording rule allows no other route. */
export function planesFindings(model, { steps = [] } = {}) {
  if (!model) return [];
  // A caveat that changes what a figure means stays with the figure, never in the fold (a range, a place that is only
  // approximate, other flying over a quiet count).
  const caveats = [model.edge, model.approx, model.other].filter(Boolean);
  // THE TILE NAMES ITS MAIN SOURCE; THE FOLD NAMES THEM ALL (Bill, 2026-11-09: "quite a lot of text"). Four credits ran to
  // five lines under three bars, and planesNotes() already lists every one under "About these figures", which the panel
  // places in the LAST airport tile, so the tile said them twice. The flight tracks, with their licence, stay in sight on
  // every airport tile; "Other sources below" points at the fold. With no airport there is no fold, so all stay in sight.
  const all = model.credits || [];
  const credits = all.join('; ');
  const main = all.length ? `${all[0]}` : '';
  const more = all.length > 1 ? '. Other sources below' : '';
  if (!model.airports.length) {
    return model.none ? [{
      key: 'planes', head: model.heading, detail: model.none, caveats,
      tile: { name: 'Planes overhead', level: 'Under 1 a day', sub: null, shared: false, tone: null, stand: null, pill: null, visual: [], say: [model.none], notes: caveats, source: credits || null },
    }] : [];
  }
  // A watch item from the planes layer's third step (the busiest colour but one): read from its index.json, never typed.
  const froms = (steps || []).map((x) => x && x.from).filter(isNum).sort((x, y) => x - y);
  const watchFrom = froms.length >= 3 ? froms[2] : null;
  const most = (v) => (Array.isArray(v) ? v[1] : isNum(v) ? v : v === '<1' ? 0.5 : null);
  const found = model.airports.map((a) => {
    // The face says the commonest one-way kind of day, as the front page's tile does (planesWalk().lead).
    const lead = a.rows.filter((r) => r.kind !== 'mixed').sort((x, y) => (y.sharePct ?? 0) - (x.sharePct ?? 0))[0];
    const fig = lead && lead.value !== null && lead.value !== undefined ? shortFigure(lead.value) : null;
    const top = lead ? most(lead.value) : null;
    return {
      key: 'planes',
      head: `${a.name} planes overhead`,
      detail: `On an average day of each kind, ${a.period}.`,
      rows: a.rows.map((r) => [`${r.label}: ${r.text}`, r.share]),
      tile: {
        name: `${a.name} planes overhead`,
        level: !fig || fig === 'not measured' ? 'Not measured' : fig === 'none' ? 'None' : `${fig} a day`,
        sub: lead && fig ? lead.label.toLowerCase() : null,
        shared: false,
        tone: null,
        stand: isNum(watchFrom) && isNum(top) && top >= watchFrom ? 'watch' : null,
        pill: `${a.name} planes`,
        visual: [{ kind: 'bars', room: 1, rows: a.rows.map((r) => ({ label: r.label, sub: r.share, text: r.text, value: most(r.value), colour: stepColour(r.value, steps) || null })) }],
        say: [a.windShort],
        source: main ? `${main}${a.period ? `, ${a.period}` : ''}${more}` : null,
      },
    };
  });
  found.at(-1).caveats = caveats;
  found.at(-1).tile.notes = caveats;
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
export function pathFinding(km, { airport, name, under, record } = {}) {
  if (!isNum(km)) return null;
  const landing = /final approach|arrival/i.test(name || '');
  const leaving = /departure/i.test(name || '');
  const way = runwayHeading(name);
  const at = airport || 'the airport';
  const days = way ? ` on days it flies ${way}` : '';
  return {
    key: 'path',
    rows: [['Nearest flight path', `${km.toFixed(1)} km`]],
    tile: {
      name: 'Nearest flight path',
      level: `${km.toFixed(1)} km away`,
      // Only where the map's own planeAltitude() says a landing route is not overhead (`under === false`): it never guesses.
      sub: under === false ? 'not directly under it' : null,
      shared: false,
      tone: null,
      stand: null,
      pill: null,
      visual: [{ kind: 'ruler', km, label: landing ? 'Landing route' : leaving ? 'Take-off route' : 'Flight route' }],
      say: [
        landing ? `Planes landing at ${at}${days} use this route.` : leaving ? `Planes taking off from ${at}${days} use this route.` : 'This is the nearest published flight route.',
        under === false ? 'You are not directly under it.' : null,
      ],
      tip: 'Turn on Flight paths on the map to see where it goes.',
      source: record || null,
    },
  };
}

/** A council-wide rating in plain words: "Flood risk is low". Nothing to say without a rating. */
export function ratingFinding(key, name, rating, ctx = {}) {
  if (!rating || words(rating) === 'not recorded') return null;
  const w = words(rating);
  const tone = toneOf(w);
  const area = ctx.area || 'council';
  return {
    key,
    head: `${name} ${name.endsWith('Schools') ? 'are' : 'is'} ${words(rating)}`,
    tile: {
      name,
      level: cap(w),
      sub: wide(ctx.council, area),
      shared: true,
      tone,
      stand: standOf(tone),
      pill: name,
      visual: [strip(ctx.scale || key, w, tone)],
      say: ctx.say || [`A rating for ${placeName(ctx.council, area)} as a whole.`],
      notes: ctx.notes || [],
      tip: ctx.tip || null,
      source: ctx.source || null,
    },
  };
}

/**
 * Crime is council-wide and said so. Against the London median only where the figures compare (`comparable`: New
 * York's come from a different source). The two amounts get a bar each, from a true zero, on one scale.
 */
export function crimeFinding({ band, rate, median, comparable = true, area = 'council', estimated = false, council, note } = {}) {
  const hasRate = isNum(rate);
  if (!band && !hasRate) return null;
  const place = placeName(council, area);
  const tone = band ? toneOf(band) : null;
  const tile = (visual, say) => ({
    name: 'Crime', level: band ? cap(words(band)) : `${rate} per 1,000`, sub: wide(council, area), shared: true, tone,
    stand: standOf(tone), pill: 'Crime', visual: [band ? strip('crime', words(band), tone) : null, ...visual], say, notes: note ? [note] : [],
  });
  const per = hasRate ? `${cap(place)} has ${rate} ${estimated ? 'crimes (our estimate)' : 'recorded crimes'} a year for every 1,000 people.` : null;
  if (!hasRate) return { key: 'crime', head: `Crime is ${words(band)}`, tile: tile([], [`A rating for ${place} as a whole.`]) };
  // ONS publishes no rate for the City of London: the figure is ours, and the sentence says so.
  const rateLine = estimated
    ? `${rate} offences per 1,000 residents a year across the whole ${area}, Sky Score's estimate`
    : `${rate} recorded offences per 1,000 residents a year across the whole ${area}`;
  if (!comparable || !isNum(median) || median <= 0) {
    return { key: 'crime', head: band ? `Crime is ${words(band)}` : 'Recorded crime', detail: `${rateLine}.`, tile: tile([], [per]) };
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
    tile: tile(
      [{ kind: 'bars', unit: estimated ? 'crimes a year per 1,000 people, our estimate' : 'recorded crimes a year per 1,000 people', rows: [{ label: council || `This ${area}`, text: String(rate), value: rate, here: true }, { label: 'A typical London borough', text: m, value: median }] }],
      [per, ratio >= 1.15 ? `That is ${ratio.toFixed(1)} times a typical London borough.` : ratio <= 0.85 ? 'That is lower than a typical London borough.' : 'That is close to a typical London borough.'],
    ),
  };
}

/** A name and distance the panel already lists, under a rating. The rating alone if the list has nothing yet. */
export function nearestFinding(key, name, rating, nearest, ctx = {}) {
  const f = ratingFinding(key, name, rating, ctx);
  const row = nearest && nearest.name ? [nearest.name, String(nearest.dist || '').replace(/^(\d+)m$/, '$1 m')] : null;
  const said = row ? `${row[0]} is ${row[1]} away.` : null;
  if (!f) {
    return row ? {
      key, head: name, rows: [row],
      tile: { name, level: row[1], sub: row[0], shared: false, tone: null, stand: null, pill: null, visual: [], say: [said], source: ctx.source || null },
    } : null;
  }
  return row ? { ...f, rows: [row], tile: { ...f.tile, say: [said, ...(ctx.say || [])] } } : f;
}

/** The council's average price and its trend. `trend` is the record's own text, such as "-13.8%". */
export function priceFinding({ price, trend, area = 'council', council, afford, source } = {}) {
  if (!price) return null;
  const m = /^([+-]?)(\d+(?:\.\d+)?)%$/.exec(String(trend ?? '').trim());
  const moved = m ? (Number(m[2]) === 0 ? 'unchanged in a year.' : `${m[1] === '-' ? 'down' : 'up'} ${m[2]}% in a year.`) : null;
  const since = m ? (Number(m[2]) === 0 ? 'the same as a year ago' : `${m[2]}% ${m[1] === '-' ? 'less' : 'more'} than a year ago`) : null;
  return {
    key: 'price', label: `Average price in the ${area === 'council' ? 'council area' : area}`, big: price, detail: moved,
    tile: {
      name: 'Average price',
      level: price,
      sub: wide(council, area),
      shared: true,
      tone: null,
      // A watch item where prices this high put affordability under 3 of 10 (Bill's rule, 2026-11-08).
      stand: isNum(afford) && afford < 3 ? 'watch' : null,
      pill: 'High prices',
      visual: [isNum(afford) ? { kind: 'score', name: 'Affordability', value: afford } : null],
      say: [`The average price of a home in ${placeName(council, area)}${since ? `, ${since}` : ''}.`,
        isNum(afford) ? `That gives it an affordability score of ${afford.toFixed(1)} out of 10.` : null],
      source: source || null,
    },
  };
}

/** The latest standard sale of a home here: only a known home type in category A may carry the label; unknown is not a home. */
export function soldFinding(sold, format) {
  if (!Array.isArray(sold)) return null;
  const s = sold.find((r) => r && isNum(r.price) && HOME_TYPES.has(r.type) && r.category === 'A');
  if (!s) return null;
  const d = /^(\d{4})-(\d{2})/.exec(String(s.date || ''));
  const month = d && MONTHS[Number(d[2]) - 1];
  return {
    key: 'sold', label: 'Last home sold at this postcode', rows: [[format(s.price), month ? `${month} ${d[1]}` : '']], strong: true,
    tile: {
      name: 'Last home sold here', level: format(s.price), sub: month ? `${month} ${d[1]}` : null, shared: false, tone: null, stand: null, pill: null,
      visual: [], say: ['The most recent sale of a home at this postcode.'], source: 'HM Land Registry',
    },
  };
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
    tile: {
      name: 'Energy rating', level: `Band ${s.averageBand}`, sub: rating === null ? null : `${rating} out of 100`, shared: false, tone: null,
      stand: null, pill: null, visual: [strip('epc', String(s.averageBand), null)],
      say: [`The average of ${data.count} energy certificate${data.count === 1 ? '' : 's'} for homes at this postcode.`],
      source: 'Energy Performance of Buildings Register',
    },
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

// ---- THE ANSWER CARD'S TILES (Bill, 2026-11-08) ----
// Bill: "keep to road noise is high", then "make the text simpler... we want any user to understand it, and choose
// visuals where applicable". Every finding above also carries `tile`: its face (the thing, its level, a short line under
// it, and whether the level is the council's), its tone, and its explanation as data: pictures, one or two short
// sentences with the number inside, a tip, and the source in small type. Jargon (Lden, Progress 8) lives only in the
// source. Pictures are only of the kinds the area pages allow: a rating among its own words (`strip`), a share of
// postcodes as 100 squares (`share`), figures side by side from a true zero (`bars`), one distance on a scale from zero
// (`ruler`), and a score on its 0-10 track (`score`). A word outside its scale draws no strip: never a wrong picture.

/** Each rating's own words, low end first. */
export const SCALES = {
  road: ['low', 'moderate', 'high'],
  aircraft: ['low', 'moderate', 'high'],
  air: ['good', 'moderate', 'poor'],
  flood: ['low', 'medium', 'high'],
  crime: ['low', 'medium', 'high'],
  transport: ['poor', 'moderate', 'good', 'excellent'],
  healthcare: ['poor', 'moderate', 'good', 'excellent'],
  schools: ['well below average', 'below average', 'average', 'above average', 'well above average'],
  epc: ['G', 'F', 'E', 'D', 'C', 'B', 'A'],
};
const SHORT = { 'well below average': 'Well below', 'below average': 'Below', 'above average': 'Above', 'well above average': 'Well above' };
const cap = (s) => String(s).charAt(0).toUpperCase() + String(s).slice(1);

// A rating's tone, as index.html ratingBadgeClass() and schoolBandFromP8() class it (held equal by tests/panel-findings.mjs).
// An unknown word has no tone, never "bad": absence is not a reading.
const GOOD = new Set(['low', 'good', 'excellent', 'above average', 'well above average']);
const MID = new Set(['medium', 'moderate', 'average']);
const BAD = new Set(['high', 'poor', 'below average', 'well below average']);
export function toneOf(word) {
  const w = words(word ?? '');
  return GOOD.has(w) ? 'good' : MID.has(w) ? 'mid' : BAD.has(w) ? 'bad' : null;
}
const standOf = (tone) => (tone === 'good' ? 'good' : tone === 'bad' ? 'watch' : null);
const placeName = (council, area) => council || `the whole ${area}`;
const wide = (council, area) => (council ? `${council}-wide` : `${cap(area)}-wide`);
const strip = (scale, current, tone) => (SCALES[scale] && SCALES[scale].includes(current) ? { kind: 'strip', scale, current, tone } : null);

const COMPASS = ['north', 'north-east', 'east', 'south-east', 'south', 'south-west', 'west', 'north-west'];
/** "LHR 27L final approach" -> the way planes on it fly: runway 27 points 270 degrees, west. Null when it says no runway. */
export function runwayHeading(name) {
  const m = /\b(\d{2})[LRC]?\b/.exec(String(name || ''));
  if (!m) return null;
  const deg = (Number(m[1]) * 10) % 360;
  return Number(m[1]) >= 1 && Number(m[1]) <= 36 ? COMPASS[Math.round(deg / 45) % 8] : null;
}

/**
 * The card's pills: what stands out, watch first then good, in the panel's own order. `entries` are the placed tiles'
 * { key, stand, pill, slot }. One rule across tiles: where any planes tile is a watch item, aircraft noise is never a
 * "good" pill too, so "low" never stands beside "318 a day" as two verdicts (the DEFRA map is a yearly average).
 */
export function pillsFor(entries) {
  const list = (entries || []).filter((e) => e && e.pill && e.stand);
  const planesWatch = list.some((e) => e.key === 'planes' && e.stand === 'watch');
  const kept = list.filter((e) => !(planesWatch && e.key === 'aircraft' && e.stand === 'good'));
  return [...kept.filter((e) => e.stand === 'watch'), ...kept.filter((e) => e.stand === 'good')];
}

function stripHtml(v) {
  const label = `${cap(v.current)}, on a scale of ${SCALES[v.scale].map(cap).join(', ')}`;
  return `<div class="t-strip" role="img" aria-label="${esc(label)}">${SCALES[v.scale].map((w) => `<span class="${w === v.current ? `on t-bg-${v.tone || 'plain'}` : ''}">${esc(SHORT[w] || cap(w))}</span>`).join('')}</div>`;
}
function shareHtml(v) {
  const pct = Math.max(0, Math.min(100, Math.round(v.pct)));
  return `<figure class="t-share" role="img" aria-label="${pct} in every 100 ${esc(v.of)}"><div class="t-squares">${'<i class="on"></i>'.repeat(pct)}${'<i></i>'.repeat(100 - pct)}</div>`
    + `<figcaption><b>${pct} in every 100</b> ${esc(v.of)}</figcaption></figure>`;
}
function barsHtml(v) {
  const top = Math.max(...v.rows.map((r) => (isNum(r.value) ? r.value : 0)), 0) * (v.room ?? 1.12) || 1;
  const rows = v.rows.map((r) => {
    const width = isNum(r.value) && r.value > 0 ? Math.max(1.5, clamp((r.value / top) * 100)) : 0;
    const fill = r.colour ? `background:${esc(r.colour)}` : '';
    return `<div class="t-bar"><div class="t-cap"><span>${esc(r.label)}${r.sub ? ` <small>· ${esc(r.sub)}</small>` : ''}</span><b>${esc(r.text)}</b></div>`
      + `<div class="t-track"><i class="${r.colour ? '' : r.here ? 'here' : 'yard'}" style="width:${width}%;${fill}"></i></div></div>`;
  }).join('');
  return `<div class="t-bars" role="img" aria-label="${esc(v.rows.map((r) => `${r.label}${r.sub ? `, ${r.sub}` : ''}: ${r.text}`).join('; '))}">${rows}${v.unit ? `<p class="t-unit">${esc(v.unit)}</p>` : ''}</div>`;
}
function rulerHtml(v) {
  const step = [1, 2, 5, 10, 20, 50].find((s) => v.km / s <= 4) || 100;
  const max = Math.max(step * 2, Math.ceil((v.km * 1.25) / step) * step);
  const x = (km) => 16 + (km / max) * 268;
  const ticks = Array.from({ length: max / step + 1 }, (_, i) => i * step)
    .map((k) => `<line x1="${x(k)}" y1="54" x2="${x(k)}" y2="60" stroke="currentColor" opacity=".45"/><text x="${x(k)}" y="74" font-size="11" text-anchor="middle">${k} km</text>`).join('');
  const label = `${v.label} · ${v.km.toFixed(1)} km`;
  const anchor = x(v.km) > 190 ? 'end' : 'start';
  return `<svg class="t-ruler" viewBox="0 0 300 80" role="img" aria-label="${esc(`${v.label}, ${v.km.toFixed(1)} km away`)}">`
    + `<line x1="16" y1="56" x2="284" y2="56" stroke="currentColor" opacity=".3" stroke-width="2.5"/>${ticks}`
    + `<circle cx="16" cy="56" r="5.5" fill="currentColor"/><text x="16" y="44" font-size="12" font-weight="700" text-anchor="middle">You</text>`
    + `<line x1="${x(v.km)}" y1="10" x2="${x(v.km)}" y2="56" stroke="currentColor" stroke-width="2.4"/>`
    + `<text x="${x(v.km) + (anchor === 'end' ? -5 : 5)}" y="16" font-size="12" font-weight="700" text-anchor="${anchor}">${esc(label)}</text></svg>`;
}
function scoreHtml(v, colourOf) {
  const fill = colourOf ? `background:${esc(colourOf(v.value))}` : '';
  return `<div class="t-bar"><div class="t-cap"><span>${esc(v.name)}</span><b>${v.value.toFixed(1)} out of 10</b></div>`
    + `<div class="t-track"><i class="here" style="width:${Math.max(1.5, clamp(v.value * 10))}%;${fill}"></i></div></div>`;
}

/**
 * One finding as a tile the reader opens; '' for nothing. `opts.scoreColour` is the panel's scoreColor(), so a score's
 * bar is coloured as every score on the site is. The explanation is closed until tapped.
 */
export function tileHtml(f, opts = {}) {
  const t = f && f.tile;
  if (!t) return '';
  const ink = t.tone ? `t-ink-${t.tone}` : 't-ink-plain';
  const sub = t.sub ? `<span class="t-sub${t.shared ? ' t-wide' : ''}">${esc(t.sub)}</span>` : '';
  const pictures = (t.visual || []).filter(Boolean).map((v) => (v.kind === 'strip' ? stripHtml(v) : v.kind === 'share' ? shareHtml(v)
    : v.kind === 'bars' ? barsHtml(v) : v.kind === 'ruler' ? rulerHtml(v) : v.kind === 'score' ? scoreHtml(v, opts.scoreColour) : '')).join('');
  const say = (t.say || []).filter(Boolean).map((s) => `<p class="t-say">${esc(s)}</p>`).join('');
  const notes = (t.notes || []).filter(Boolean).map((s) => `<p class="t-note">${esc(s)}</p>`).join('');
  const tip = t.tip ? `<p class="t-tip"><b>Tip:</b> ${esc(t.tip)}</p>` : '';
  const src = t.source ? `<p class="t-src">Source: ${esc(t.source)}</p>` : '';
  const data = [`data-finding="${esc(f.key)}"`, t.stand ? `data-stand="${t.stand}"` : '', t.pill ? `data-pill="${esc(t.pill)}"` : '',
    t.shared ? 'data-shared' : ''].filter(Boolean).join(' ');
  return `<details class="tile" ${data}><summary class="t-face"><span class="t-name">${esc(t.name)}</span>`
    + `<span class="t-level ${ink}">${esc(t.level)}</span>${sub}</summary><div class="t-body">${pictures}${say}${notes}${tip}${src}</div></details>`;
}
