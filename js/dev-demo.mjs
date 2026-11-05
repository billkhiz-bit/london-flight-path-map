/**
 * The developers band: a request typed, its real answer arriving, each figure landing on a card. The front page shows it
 * for the example; /api/ shows it for any postcode a reader sends (js/api-demo.mjs). One copy of the behaviour, moved here
 * from js/home-sections.mjs on 2026-11-05 (Bill: the API page "animated and interactive, like the front page"), and both
 * pages carry the same ids, so neither can drift from the other. tests/test_dev_band_parity.py holds their styles equal.
 *
 * WHAT IT SHOWS (Bill's pick C of the API mock-up, 2026-11-04): only what was answered. devAnswer() builds the JSON and
 * the tiles from the response itself, and writeAnswer() rewrites the samples to that answer's point, so the request on
 * show is the one answered. Nothing here touches the document at import: the pure part runs under node in
 * tests/home-sections.mjs and tests/api-demo.mjs.
 *
 * Reads no postcode and counts none: the page passes count(way), and a way is a word from this file.
 */

export const finite = (v) => typeof v === 'number' && Number.isFinite(v);
export const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = text;
  return n;
};

export const still = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** A tab list (the walkthrough's steps, the code samples): click or Enter selects; arrows, Home and End move. */
export function bindTabs(list, onChange) {
  if (!list) return;
  const tabs = [...list.querySelectorAll('[role="tab"]')];
  const panels = tabs.map((t) => document.getElementById(t.getAttribute('aria-controls')));
  if (!tabs.length || panels.some((p) => !p)) return; // the stacked page stays as it is
  const select = (i, focus) => {
    tabs.forEach((t, j) => {
      t.setAttribute('aria-selected', String(i === j));
      t.tabIndex = i === j ? 0 : -1;
      panels[j].hidden = i !== j;
    });
    if (focus) tabs[i].focus();
    onChange?.(tabs[i], panels[i]);
  };
  tabs.forEach((t, i) => t.addEventListener('click', () => select(i, false)));
  list.addEventListener('keydown', (ev) => {
    const i = tabs.indexOf(document.activeElement);
    if (i < 0) return;
    const to = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[ev.key];
    if (to === undefined) return;
    ev.preventDefault();
    select((to + tabs.length) % tabs.length, true);
  });
  list.hidden = false;
  list.parentElement?.classList.add('is-tabbed');
  select(Math.max(0, tabs.findIndex((t) => t.getAttribute('aria-selected') === 'true')), false);
}

// The figures the band shows, in the order the response's own lines put them.
const DEV_FIELDS = [
  ['aircraftNoiseLdenDb', (v) => `${v} dB`, 'aircraft noise'],
  ['roadNoiseLdenDb', (v) => `${v} dB`, 'road noise'],
  // DEFRA surveyed the postcode and mapped no road noise this loud: a quiet reading, so a figure, never a missing one.
  ['roadNoiseBelowDb', (v) => `under ${v} dB`, 'road noise'],
  ['no2AnnualMeanUgm3', (v) => `${v} µg/m³`, 'NO₂ in the air'],
];
const devCredit = (answer, key) => {
  const p = answer.provenance?.[`environment.${key}`];
  return [answer.sourceIndex?.[p?.sources?.[0]]?.publisher, p?.method, p?.period].filter(Boolean).join(', ');
};

/**
 * The band's answer: { lines, figures, missing } from a /v1/environment response, shortened to what fits. The lines are
 * the response's own values as JSON; each figure says who made it and how, from the response's provenance. A value the
 * answer lacks is no line and no tile, never a zero, and its words are in `missing`, so a page can say so; with none of
 * them, null, and the band stays the request alone.
 */
export function devAnswer(answer) {
  const e = answer?.environment;
  if (!e) return null;
  const figures = DEV_FIELDS.filter(([key]) => finite(e[key])).map(([key, figure, words]) => ({
    key, value: e[key], figure: figure(e[key]), words, credit: devCredit(answer, key),
  }));
  if (!figures.length) return null;
  const postcode = answer.location?.postcode;
  return {
    figures,
    missing: [...new Set(DEV_FIELDS.map(([, , words]) => words))].filter((words) => !figures.some((f) => f.words === words)),
    lines: [
      '{',
      ...(postcode ? [`  "location": { "postcode": ${JSON.stringify(postcode)} },`] : []),
      '  "environment": {',
      ...figures.map((f, i) => `    "${f.key}": ${f.value}${i < figures.length - 1 ? ',' : ''}`),
      '  }',
      '}',
    ],
  };
}

/**
 * A sample's text at a new point. Through placeholders, because the two swaps must not see each other's work: one after
 * the other, a new latitude holding the old longitude's digits had its middle rewritten. On the front page this ran
 * once, for one point; /api/ runs it for every postcode sent.
 */
export function atPoint(text, was, lat, lon) {
  return text.replaceAll(was.lat, '\u0000').replaceAll(was.lon, '\u0001')
    .replaceAll('\u0000', String(lat)).replaceAll('\u0001', String(lon));
}

// The run. It plays once on arriving, in about four seconds (under the five of WCAG 2.2.2), and again for a reader who
// changes language or presses Replay; at rest, and for a reader who asks for less motion, everything is simply there.
// Typing never shortens a sample's text (the rest stays in the node, unseen), so Copy is whole at every moment, and the
// caret stands outside the text's flow: an inline box in the text was a place to break, so a long unbroken URL re-wrapped
// and its box jumped.
const STALE = Symbol('stale');
let devRun = 0;
let typing = null;
let devReady = false;
let armed = false;
const devBox = () => document.getElementById('dev-run');
const devWait = (ms, id) => new Promise((resolve, reject) => { setTimeout(() => (id === devRun ? resolve() : reject(STALE)), ms); });

/** The end of a run, however it ended: every figure on show, and nothing still moving. */
export function finishDev() {
  devRun++;
  if (typing) { typing.pre.textContent = typing.text; typing = null; }
  const box = devBox();
  if (!box) return;
  box.classList.remove('is-waiting', 'is-answered');
  box.querySelectorAll('.is-on, .is-empty, .is-lit').forEach((n) => n.classList.remove('is-on', 'is-empty', 'is-lit'));
}

function typeDev(pre, id) {
  const text = pre.textContent;
  const shown = document.createTextNode('');
  const rest = el('span', 'dev-rest', text);
  typing = { pre, text };
  pre.replaceChildren(shown, el('span', 'dev-caret'), rest);
  const start = performance.now();
  return new Promise((resolve, reject) => {
    const step = (now) => {
      if (id !== devRun) { reject(STALE); return; }
      const n = Math.min(text.length, Math.ceil(((now - start) / 700) * text.length));
      shown.data = text.slice(0, n);
      rest.textContent = text.slice(n);
      if (n < text.length) { requestAnimationFrame(step); return; }
      pre.textContent = text;
      typing = null;
      resolve();
    };
    requestAnimationFrame(step);
  });
}

// One figure at a time, all of it at once: the number lights in the answer, its card lights, and the card's figure
// appears, in one frame, then the number and the card go out together (Bill, 2026-11-04: a card lighting on landing, and
// a figure arriving after its number, both read as a mismatch). Nothing here has a transition: a fade on one side is a lag.
async function lightDev(n, i, id) {
  const out = devBox()?.querySelectorAll('.ans-tile b')[i];
  const tile = out?.closest('.ans-tile');
  if (!tile) return;
  n.classList.add('is-lit');
  tile.classList.add('is-lit');
  out.classList.remove('is-empty');
  await devWait(520, id);
  n.classList.remove('is-lit');
  tile.classList.remove('is-lit');
  await devWait(80, id);
}

export async function playDev() {
  // Any run ends the wait for the run on arriving, or scrolling down later would restart what a reader is reading.
  arriving?.disconnect();
  arriving = null;
  finishDev();
  const id = devRun;
  const box = devBox();
  const pre = document.querySelector('section.dev [role="tabpanel"]:not([hidden]) pre');
  if (!box || !pre) return;
  try {
    box.classList.add('is-waiting');
    box.querySelectorAll('.ans-tile b').forEach((b) => b.classList.add('is-empty'));
    await typeDev(pre, id);
    await devWait(260, id);
    box.classList.add('is-answered');
    await devWait(240, id);
    for (const line of box.querySelectorAll('.dev-ln')) {
      line.classList.add('is-on');
      await devWait(50, id);
    }
    await devWait(160, id);
    for (const [i, n] of [...box.querySelectorAll('.dev-n')].entries()) await lightDev(n, i, id);
    await devWait(200, id);
    finishDev();
  } catch (err) {
    if (err !== STALE) throw err;
  }
}

function jsonLine(line) {
  const row = el('span', 'dev-ln');
  const m = /^(\s*"\w+": )(-?[\d.]+)(,?)$/.exec(line);
  if (m) row.append(m[1], el('span', 'dev-n', m[2]), m[3]);
  else row.textContent = line;
  return row;
}

function devTile(f) {
  const tile = el('span', 'ans-tile');
  tile.append(el('b', '', f.figure), f.words);
  if (f.credit) tile.append(el('small', '', f.credit));
  return tile;
}

// The samples as the page wrote them, and the point they name. Every answer starts from these, never from what the last
// answer left: a point read back could be a whole degree, and `-2` is also in the API's host.
const written = new Map();
let startedAt = null;

/**
 * Puts one answer on the page: the samples at its point, its lines and its cards. False, with the page as it was, when
 * the answer holds nothing to show, so a page can say so. Safe to run again: /api/ runs it for every postcode sent.
 */
export function writeAnswer(geo, env) {
  const box = devBox();
  const res = document.getElementById('dev-res');
  const tiles = document.getElementById('dev-tiles');
  const dev = devAnswer(env);
  if (!box || !res || !tiles || !dev) return false;
  finishDev(); // a run still typing would otherwise put its old text back over the new
  // The samples name a point; the answer below them is for this one, so they say this one.
  if (!startedAt) {
    const was = /lat=(-?[\d.]+)&lon=(-?[\d.]+)/.exec(document.getElementById('dev-env')?.textContent || '');
    if (!was) return false;
    startedAt = { lat: was[1], lon: was[2] };
  }
  for (const pre of document.querySelectorAll('section.dev pre[id^="dev-env"]')) {
    if (!written.has(pre)) written.set(pre, pre.textContent);
    pre.textContent = atPoint(written.get(pre), startedAt, geo.latitude, geo.longitude);
  }
  // "Copied" was true of the request that was on show.
  const copied = document.getElementById('copy-status');
  if (copied) copied.textContent = '';
  res.replaceChildren(...dev.lines.map(jsonLine));
  tiles.replaceChildren(...dev.figures.map(devTile));
  box.hidden = false;
  return true;
}

/**
 * Replay, and the run on arriving: bound once, whatever writeAnswer() does after. A reader who asks for less motion is
 * never sent this animation, but may ask for it: what they press is theirs to see. auto: false skips the run on arriving,
 * for a reader who has already pressed something of their own; one who presses later ends the wait through playDev().
 */
let arriving = null;
export function armDev(count, { auto = true } = {}) {
  const box = devBox();
  if (armed || !box) return;
  armed = true;
  const replay = document.getElementById('dev-replay');
  if (replay) {
    replay.hidden = false;
    replay.addEventListener('click', () => {
      playDev();
      count('play');
    });
    if (still()) {
      replay.textContent = 'Play';
      replay.setAttribute('aria-label', 'Play the request and its answer');
    }
  }
  if (still() || !('IntersectionObserver' in window)) return;
  devReady = true;
  if (!auto) return;
  arriving = new IntersectionObserver((entries) => {
    if (entries.some((x) => x.isIntersecting)) playDev();
  }, { threshold: 0.35 });
  arriving.observe(box.closest('.code'));
}

/** The language tabs: Copy copies the sample on show, and a reader who changes language sees that language answered. */
export function bindCodeTabs(count) {
  bindTabs(document.querySelector('.code-tabs'), (tab, panel) => {
    finishDev();
    // Never at load: this also runs when the tabs bind.
    if (devReady) {
      playDev();
      count('lang');
    }
    const copy = document.querySelector('section.dev button.copy[data-copy]');
    const pre = panel.querySelector('pre[id]');
    if (copy && pre) {
      copy.dataset.copy = pre.id;
      copy.setAttribute('aria-label', `Copy the ${tab.textContent.trim()} request`);
    }
    const status = document.getElementById('copy-status');
    if (status) status.textContent = '';
  });
}

// Where the clipboard is refused (no permission, an old browser), the request is selected instead and the visitor is told
// how to copy on THEIR device: Ctrl+C, Cmd+C on a Mac, the menu on a phone or tablet ("Ctrl+C" showed on an iPhone: audit
// 2026-10-22, M-14).
const copyHow = () => (/iPhone|iPad|iPod|Android/.test(navigator.userAgent)
  ? 'Selected. Copy it from the menu.'
  : `Selected. Press ${/Mac/.test(navigator.userAgent) ? 'Cmd+C' : 'Ctrl+C'} to copy.`);

/** Copy puts the request EXACTLY as shown on the clipboard, and says so in a polite live region. */
export function bindCopy(count) {
  document.querySelectorAll('section.dev button.copy[data-copy]').forEach((button) => {
    button.addEventListener('click', async () => {
      const pre = document.getElementById(button.dataset.copy);
      const status = document.getElementById('copy-status');
      if (!pre) return;
      count('copy');
      try {
        await navigator.clipboard.writeText(pre.textContent);
        if (status) status.textContent = 'Copied. Paste it into a terminal.';
      } catch {
        const range = document.createRange();
        range.selectNodeContents(pre);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        if (status) status.textContent = copyHow();
      }
    });
  });
}
