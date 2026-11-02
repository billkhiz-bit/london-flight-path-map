/**
 * "Describe what you want" for Find areas: plain words read into the tab's own choices, in the browser.
 *
 * WHY THIS EXISTS (2026-11-02). Bill asked for a search "like other websites", then: "without imposing on privacy
 * concerns". So nothing typed here leaves the page: no server, no outside service, no model, nothing stored or
 * counted. Fixed rules read a sentence ("quiet, near a station, under £500k in Manchester") into the controls Find
 * areas already has (a region, a price step, six avoid/want choices); the controls stay the truth, the reading is
 * shown back in words ("Read as: ...") with anything not understood, and the visitor corrects it on the chips.
 * No figure comes from here: the areas listed are the tab's own, from the open-data file, as before.
 *
 * Pure (no DOM), so Node tests it (tests/find-words.mjs). British spelling and £ throughout.
 */

/** What each choice answers to. Order matters only for the words shown back. */
const CHOICES = [
  { key: 'planes', patterns: [/\b(?:no|less|fewer|away from|avoid|without|not under)\s+(?:the\s+)?(?:planes?|aircraft|flights?|flight\s*paths?|airports?|aeroplanes?)\b/,
    /\bquiet\s+skies\b/, /\bflight\s*paths?\b/, /\b(?:aircraft|aeroplane|airport|plane)\s+noise\b/, /\bplanes?\b/, /\baircraft\b/, /\bairports?\b/] },
  { key: 'roads', patterns: [/\b(?:no|away from|avoid|without)\s+(?:busy\s+|main\s+)?roads?\b/, /\bbusy\s+roads?\b/, /\bmain\s+roads?\b/,
    /\broad\s+noise\b/, /\btraffic\b/, /\bquiet\s+streets?\b/] },
  { key: 'flood', patterns: [/\b(?:low|no|little)\s+flood(?:ing)?(?:\s+risk)?\b/, /\bflood(?:ing|s)?(?:\s+risk)?\b/, /\bnot\s+(?:at\s+risk\s+of\s+)?flood(?:ing)?\b/] },
  { key: 'air', patterns: [/\bclean(?:er)?\s+air\b/, /\bfresh\s+air\b/, /\bair\s+quality\b/, /\bpollut(?:ion|ed)\b/, /\bpoor\s+air\b/, /\bdirty\s+air\b/] },
  { key: 'rail', patterns: [/\b(?:near|close to|by|walk to|walking distance (?:of|to|from))\s+(?:a\s+|the\s+)?(?:train\s+|tube\s+|rail(?:way)?\s+|metro\s+|tram\s+|underground\s+)?(?:stations?|stops?)\b/,
    /\b(?:train|tube|rail(?:way)?|metro|tram|underground)\s+(?:stations?|stops?|links?|lines?)\b/, /\bstations?\b/, /\btransport\s+links?\b/,
    /\bcommut(?:e|ing)\b/, /\b(?:tube|trains?|trams?|metro|underground|railway)\b/] },
  { key: 'schools', patterns: [/\b(?:good|great|best|top|decent|strong)\s+(?:secondary\s+)?schools?\b/, /\bschools?\b/, /\bprogress\s*8\b/] },
];
/** "quiet" alone is both: aircraft and road noise, said back as two choices so the visitor can drop one. */
const QUIET = /\b(?:quiet|peaceful|tranquil|calm)\b/;
/** A want said with a "not" before it is not read as the want: shown back as not understood instead. */
const NOT_WANT = /\b(?:not|no|away from|avoid|without)\s+(?:near\s+|close to\s+)?(?:a\s+|the\s+)?(?:train\s+|tube\s+)?(?:stations?|schools?)\b/;

/** Other names for the regions (cities people say), mapped to the region keys the tab offers. */
const REGION_ALIASES = {
  manchester: 'manchester', salford: 'manchester', stockport: 'manchester', bolton: 'manchester',
  birmingham: 'westmidlands', coventry: 'westmidlands', wolverhampton: 'westmidlands',
  leeds: 'westyorkshire', bradford: 'westyorkshire', wakefield: 'westyorkshire', huddersfield: 'westyorkshire',
  sheffield: 'southyorkshire', rotherham: 'southyorkshire', doncaster: 'southyorkshire', barnsley: 'southyorkshire',
  liverpool: 'merseyside', wirral: 'merseyside',
  newcastle: 'tyneandwear', sunderland: 'tyneandwear', gateshead: 'tyneandwear',
  middlesbrough: 'teesside', stockton: 'teesside',
};

/** "450k" / "£1.2m" / "450,000" / "450 thousand" -> pounds; null when it is not a price. */
function pounds(num, unit) {
  const n = Number(String(num).replace(/,/g, ''));
  if (!Number.isFinite(n) || n <= 0) return null;
  const u = (unit || '').toLowerCase();
  if (u === 'k' || u === 'thousand') return n * 1e3;
  if (u === 'm' || u === 'mil' || u === 'million') return n * 1e6;
  return n >= 10000 ? n : null; // a bare "450" is not a house price; "450000" is
}
const PRICE = /(?:under|below|less than|up to|upto|max(?:imum)?|budget(?:\s+of)?|no more than|at most|<|£)\s*£?\s*(\d[\d,]*(?:\.\d+)?)\s*(k|m|mil|thousand|million)?\b/;

const WORDS_TO_SKIP = new Set(('a an the in at on of to for with and or but near nearby around within by close i we me my our '
  + 'want wants looking look find somewhere someplace area areas place places live living home homes house houses flat flats '
  + 'property buy buying rent renting family families good nice lots plenty some any that which has have having is are be '
  + 'please also as well like would love ideally maybe really very best great decent top somewhere preferably price prices '
  + 'pound pounds budget under below less than up max no not avoid away without').split(/\s+/));

/**
 * Read `text` into Find areas' choices.
 *   regions: [[key, name]] the tab offers; budgets: its price steps (ascending pounds); keys: the choice keys it has.
 * Returns { where, budget, keys, said, unread }: `said` is the reading in words for "Read as:", `unread` the words
 * nothing matched (shown back, never guessed at). An empty or unreadable sentence changes nothing (all null/empty).
 */
export function readWords(text, { regions = [], budgets = [], keys = [] } = {}) {
  let rest = ` ${String(text || '').toLowerCase().replace(/[’']/g, "'").replace(/\s+/g, ' ')} `;
  const take = (re) => {
    const m = rest.match(re);
    if (!m) return null;
    rest = rest.slice(0, m.index) + ' '.repeat(m[0].length) + rest.slice(m.index + m[0].length);
    return m;
  };
  const said = [];

  // Where: a region by its own name first (longest first, so "West Midlands" wins over a stray "midlands"), then a city.
  let where = null;
  for (const [key, name] of [...regions].sort((a, b) => b[1].length - a[1].length)) {
    const n = name.toLowerCase().replace(/^greater\s+/, '(?:greater\\s+)?');
    if (take(new RegExp(`\\b${n}\\b`))) { where = key; break; }
  }
  if (!where) {
    for (const [alias, key] of Object.entries(REGION_ALIASES)) {
      if (regions.some(([k]) => k === key) && take(new RegExp(`\\b${alias}\\b`))) { where = key; break; }
    }
  }
  if (where) said.push(regions.find(([k]) => k === where)[1]);

  // Price: the largest step not above the amount; one under every step is said, never stretched to fit.
  let budget = null;
  // Taken only when it reads as a price: "under 450" stays in the words, so it is given back as not understood
  // rather than dropped without a word.
  const seen = rest.match(PRICE);
  const amount = seen ? pounds(seen[1], seen[2]) : null;
  if (amount) {
    take(PRICE);
    const step = [...budgets].sort((a, b) => a - b).filter((b) => b <= amount).at(-1);
    if (step) {
      budget = step;
      said.push(step === amount ? `under £${step.toLocaleString('en-GB')}` : `under £${step.toLocaleString('en-GB')} (the nearest step under £${amount.toLocaleString('en-GB')})`);
    } else if (budgets.length) {
      said.push(`no price set: the lowest step is £${Math.min(...budgets).toLocaleString('en-GB')}`);
    }
  }

  // A want said with "not" is set aside first, so "not near a station" is never read as wanting one.
  const unreadNot = [];
  for (let n = take(NOT_WANT); n; n = take(NOT_WANT)) unreadNot.push(n[0].trim());

  const chosen = new Set();
  for (const c of CHOICES) {
    if (!keys.includes(c.key)) continue;
    for (const re of c.patterns) {
      if (take(re)) chosen.add(c.key);
    }
  }
  if (take(QUIET)) {
    for (const k of ['planes', 'roads']) if (keys.includes(k)) chosen.add(k);
  }

  const unread = [...unreadNot, ...rest.split(/[^a-z0-9£'-]+/).filter((w) => w.length > 1 && !WORDS_TO_SKIP.has(w))];
  return { where, budget, keys: keys.filter((k) => chosen.has(k)), said, unread: [...new Set(unread)] };
}
