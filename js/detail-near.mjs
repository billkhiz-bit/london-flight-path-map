/**
 * "All the detail", option 1 (Bill's pick, 2026-11-08 22:35): a picture of what is within 1 km of the postcode, a
 * line for each kind of place, then cards, each the nearest of something, each opening to its full list.
 *
 * Pure text in, pure text out, so Node tests every branch (tests/detail-near.mjs); index.html only places it. The
 * panel's two rules hold here too. ABSENCE: a kind that was never asked (doctors outside London, stations in New York)
 * has no line and no card, never an empty "none nearby"; a kind that was asked and found nothing within 1 km keeps its
 * line, empty, because that is a reading. A CAP IS NOT A COUNT: /transport and /nhs each send only the nearest five of
 * a kind (MAX_RESULTS_PER_TYPE in backend/lambdas/nhs/app.py, the `[:5]` in transport's; tests/detail-near.mjs reads
 * both), so five on a line can mean five or fifty. countWords() says which.
 */

/** How many of a kind each route sends at most. Held equal to both Lambdas by tests/detail-near.mjs. */
export const ROUTE_CAP = 5;
/** The picture's reach, in metres. */
export const LANE_M = 1000;

const esc = (v) => String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
const NB = ' ';

/** The lines of the picture, top to bottom. `plural` names the line; `one` names a single place in a card. */
export const KINDS = [
  { key: 'stations', plural: 'Stations', one: 'station', hollow: false },
  { key: 'gp', plural: 'Doctors and clinics', short: 'Doctors', one: 'doctor or clinic', hollow: false },
  { key: 'pharmacies', plural: 'Pharmacies', one: 'pharmacy', hollow: true },
  { key: 'hospitals', plural: 'Hospitals', one: 'hospital', hollow: false },
];

/** A station's name as the panel shows it (TfL appends "Rail Station" / "Underground Station"). */
export const stationName = (name) => String(name || '').replace(/ (Underground|Rail|DLR) Station$/, '').trim();

/** How many stations the map's NaPTAN fallback lists (index.html renderNaptanStations: nearestStations(lat, lon, 4)). */
export const NAPTAN_CAP = 4;

/**
 * Places by kind, from the answers the panel already has. `null` for a kind means it was not asked (or the route
 * failed): no line. An array means it was asked: its places within LANE_M, nearest first, each { name, m }.
 * `mayBeMore[kind]` is true when the source sent its whole cap and every one is within the reach, so more may exist
 * that it never sent: a count of them is then a floor, not a count.
 *   transport: /transport's body ({ stations: [{ name, distance }] }) or null
 *   naptan:    nearestStations()' rows ({ name, km }) when TfL is not the source, or null
 *   nhs:       /nhs's body ({ gp, pharmacies, hospitals }) or null
 */
export function placesByKind({ transport = null, naptan = null, nhs = null } = {}) {
  // `all[kind]`: every place the source sent, nearest first, at any distance (a card's list and its nearest).
  const out = { stations: null, gp: null, pharmacies: null, hospitals: null, mayBeMore: {}, all: {} };
  const take = (key, rows, cap, metres, name = (r) => r.name) => {
    const usable = (Array.isArray(rows) ? rows : []).filter((r) => r && isNum(metres(r)));
    out.all[key] = usable.map((r) => ({ name: name(r), m: Math.round(metres(r)) })).sort((a, b) => a.m - b.m);
    out[key] = out.all[key].filter((p) => p.m <= LANE_M);
    out.mayBeMore[key] = usable.length >= cap && out[key].length === usable.length;
  };
  const tflAnswered = transport && transport.available !== false && Array.isArray(transport.stations) && transport.stations.length;
  if (tflAnswered) take('stations', transport.stations, ROUTE_CAP, (r) => Number(r.distance), (r) => stationName(r.name));
  else if (Array.isArray(naptan)) take('stations', naptan, NAPTAN_CAP, (r) => r.km * 1000);
  if (nhs && nhs.available !== false) {
    for (const key of ['gp', 'pharmacies', 'hospitals']) {
      const rows = nhs[key];
      // A fallback row is a search link, sent when Overpass failed: the kind was not measured, so it gets no line.
      if (Array.isArray(rows) && !rows.some((r) => r && (r.link || r.fallback))) take(key, rows, ROUTE_CAP, (r) => Number(r.distance));
    }
  }
  return out;
}

/**
 * How many of a kind, in words a reader can trust. Used in the picture's description and on the cards.
 *
 * @param {number}  n          how many the source listed within the reach
 * @param {boolean} mayBeMore  true when the source sent its whole cap and all of them are within the reach, so there
 *                             may be more nearby that it never sent (placesByKind's `mayBeMore[kind]`)
 * @param {string}  one        the kind, singular ("pharmacy")
 * @param {string}  plural     the kind, plural ("pharmacies")
 * @returns {string}           e.g. "No pharmacy", "1 pharmacy", "3 pharmacies"
 *
 * The capped case (2026-11-09, Bill: "you do it"): /nhs and /transport send only their nearest 5 of a kind, and at
 * SW11 1AA all 5 pharmacies are within 650 m, so a bare "5 pharmacies" would be a floor read as a count. It says
 * "5 or more pharmacies": short, plain, and true whatever the real number is. Zero is a reading, not an absence.
 */
export function countWords(n, mayBeMore, one, plural) {
  if (n === 0) return `No ${one}`;
  if (mayBeMore) return `${n} or more ${plural}`;
  return `${n} ${n === 1 ? one : plural}`;
}

/** The picture: a line per kind on one 0-1 km scale, named at its left, so no symbol needs a key. Null with no line. */
export function lanesSvg(postcode, places) {
  const lanes = KINDS.filter((k) => Array.isArray(places[k.key]));
  if (!lanes.length) return null;
  const x = (m) => 104 + (m / LANE_M) * 184;
  const h = 18 + lanes.length * 26 + 22;
  const rows = lanes
    .map((k, i) => {
      const y = 18 + i * 26;
      const dots = places[k.key]
        .map((p) => {
          const title = `<title>${esc(p.name)}, ${p.m}${NB}m</title>`;
          return k.hollow
            ? `<circle class="near-dot near-hollow" cx="${x(p.m).toFixed(1)}" cy="${y}" r="4">${title}</circle>`
            : `<circle class="near-dot" cx="${x(p.m).toFixed(1)}" cy="${y}" r="4">${title}</circle>`;
        })
        .join('');
      return `<text x="0" y="${y + 4}" class="near-lab">${esc(k.short || k.plural)}</text>`
        + `<line class="near-line" x1="104" y1="${y}" x2="288" y2="${y}"/>${dots}`;
    })
    .join('');
  const ty = h - 20;
  const ticks = [0, 250, 500, 750, 1000]
    .map((m) => `<line class="near-tickline" x1="${x(m)}" y1="${ty}" x2="${x(m)}" y2="${ty + 4}"/>`
      + `<text x="${x(m)}" y="${ty + 15}" text-anchor="middle" class="near-tick">${m === LANE_M ? '1 km' : m}</text>`)
    .join('');
  const said = lanes.map((k) => countWords(places[k.key].length, Boolean(places.mayBeMore[k.key]), k.one, k.plural.toLowerCase())).join(', ');
  return `<svg class="near-svg" viewBox="0 0 300 ${h}" role="img" aria-label="Within 1 km of ${esc(postcode)}: ${esc(said)}">${rows}${ticks}</svg>`;
}

/** A distance as a card says it: metres under 1 km, else kilometres to one place. */
export function distanceParts(m) {
  return m < 1000 ? { v: String(m), unit: 'm' } : { v: (m / 1000).toFixed(1), unit: 'km' };
}

/**
 * A card's face for the nearest of a kind, at any distance the source reached (the picture keeps to 1 km; a card names
 * the nearest even at 1.3 km). Null when the kind was not asked or the source sent none.
 */
export function nearestFace(kind, places) {
  const k = KINDS.find((x) => x.key === kind);
  const first = k && places.all && places.all[kind] && places.all[kind][0];
  if (!first) return null;
  return { k: `Nearest ${k.one === 'doctor or clinic' ? 'doctor' : k.one}`, ...distanceParts(first.m), l: first.name };
}

/** The doctors-and-clinics card's face: how many within the reach, with the other kinds under it. Null if not asked. */
export function healthFace(places) {
  if (!Array.isArray(places.gp)) return null;
  const words = (key, one, plural) => countWords(places[key].length, Boolean(places.mayBeMore[key]), one, plural);
  const others = [['pharmacies', 'pharmacy', 'pharmacies'], ['hospitals', 'hospital', 'hospitals']]
    .filter(([key]) => Array.isArray(places[key]))
    .map(([key, one, plural]) => words(key, one, plural));
  const n = places.gp.length;
  return {
    k: 'Doctors and clinics',
    v: n === 0 ? 'None' : places.mayBeMore.gp ? `${n} or more` : String(n),
    unit: '',
    l: ['within 1 km'].concat(others).join(' · '),
  };
}

/** The energy card's face from /epc's body, saying which absence it is: none on the register is a reading. */
export function epcFace(data) {
  if (!data) return null;
  if (data.fullPostcodeOnly) return { k: 'Energy rating', v: 'Full postcode', unit: '', l: 'The register is searched by full postcode' };
  if (data.available === false) return { k: 'Energy rating', v: 'Not loaded', unit: '', l: 'The register could not be reached just now' };
  const s = data.count > 0 ? data.summary : null;
  if (!s || !/^[A-G]$/.test(String(s.averageBand))) return { k: 'Energy rating', v: 'None yet', unit: '', l: 'No certificates at this postcode' };
  const rating = Number(s.averageRating);
  return {
    k: 'Energy rating',
    v: `Band ${s.averageBand}`,
    unit: '',
    l: `${isNum(rating) && s.averageRating !== '' && s.averageRating != null ? `${rating} out of 100, ` : ''}from ${data.count} certificate${data.count === 1 ? '' : 's'}`,
  };
}

/** A card's face as the inside of its <summary>; every word escaped. */
export function faceHtml(f) {
  const unit = f.unit ? ` <small>${esc(f.unit)}</small>` : '';
  const tone = f.tone ? ` dc-${esc(f.tone)}` : '';
  return `<span class="t-name">${esc(f.k)}</span><span class="dc-v${tone}">${esc(f.v)}${unit}</span>`
    + (f.l ? `<span class="t-sub">${esc(f.l)}</span>` : '');
}

/** A kind's places as rows, nearest first, each with its distance: the body of a nearest-of card. */
export function placesListHtml(list) {
  const dist = (m) => { const d = distanceParts(m); return `${d.v}${NB}${d.unit}`; };
  return `<ul class="dc-list">${list.map((p) => `<li><span>${esc(p.name)}</span><b>${dist(p.m)}</b></li>`).join('')}</ul>`;
}

/**
 * The line status card's face, from /transport's body. Null when there is nothing to say: no lines listed and none
 * missed. "Not checked" when TfL's status feed did not answer, never a good service by silence.
 */
export function lineStatusFace(transport) {
  if (!transport || transport.available === false) return null;
  const rows = Array.isArray(transport.lineStatus) ? transport.lineStatus : [];
  if (transport.lineStatusAvailable === false) return { k: 'Line status today', v: 'Not checked', tone: 'watch', l: 'TfL’s status feed did not answer' };
  if (!rows.length) return null;
  const bad = rows.filter((r) => r && r.status && r.status !== 'Good Service');
  if (!bad.length) return { k: 'Line status today', v: 'Good service', tone: 'good', l: rows.map((r) => r.name).join(', ') };
  const first = bad[0];
  const rest = bad.length > 1 ? ` and ${bad.length - 1} more` : '';
  return { k: 'Line status today', v: String(first.status), tone: 'watch', l: `${first.name}${rest}` };
}
