/**
 * The front page's sections below the map (front-page-v3 step 1, 2026-11-03).
 *
 * WHY THIS EXISTS. Bill's agreed mock-up (v8, version 12: claude.ai/artifact/8WjimVxDSZioMkdSCTVCuf; the decisions in
 * ROADMAP's START HERE of 3 Nov): a walkthrough "From a postcode to a sourced answer" in five numbered steps, each
 * SHOWING the product, and a developers band with curl / Python / JavaScript tabs. The page's policy allows no inline
 * script (script-src 'self'), so the behaviour lives here.
 *
 * NO FIGURE IS TYPED. The walkthrough's panels 02 to 04 are filled from the example answer the map above already
 * fetches (home-engine.mjs exampleAnswer(): TW9 3PZ, one shared pair of lookups), the planes only through
 * js/planes.mjs from data/planes/ (tests/test_public_wording.py's FREQUENCY rule), the air through the one pair of
 * functions every surface uses (nearestSensor / nearestMonitor, airChart). Until the answer is in, a panel says it is
 * coming; if it never comes, it says so and shows nothing in its place.
 *
 * Without this module the page still reads: the tab bars stay hidden and every step and code sample is shown in turn.
 * The pure parts (what each panel says) are exported and held without a browser by tests/home-sections.mjs.
 */

import { planesModel, planesWalk } from './planes.mjs';
import { AIR_WHO_2021, airChart, nearestMonitor, nearestSensor, stationDistance } from './street_report.mjs';

// ---- pure: what each panel says, from the example's /v1/environment answer ----

const finite = (v) => typeof v === 'number' && Number.isFinite(v);
const pct = (v, max) => Math.max(0, Math.min(100, (v / max) * 100));

/**
 * Step 02: { rows: [{ label, figure, sub, width, mark }], note } from the answer's environment and provenance, or null
 * with nothing to show. A DEFRA reading is drawn against its WHO guideline at the middle of a scale twice the
 * guideline, as the answer above draws it; the routes' estimate is a score turned round and said to be one.
 */
export function noiseRows(e, provenance = {}) {
  if (!e) return null;
  const rows = [];
  const guides = [];
  if (finite(e.aircraftNoiseLdenDb) && finite(e.aircraftNoiseWhoGuidelineDb)) {
    const who = e.aircraftNoiseWhoGuidelineDb;
    rows.push({ label: 'Aircraft', figure: `${e.aircraftNoiseLdenDb} dB`, sub: '', width: pct(e.aircraftNoiseLdenDb, who * 2), mark: 50 });
    guides.push(`${who} dB for aircraft`);
  } else if (e.aircraftQuietCoverage !== 'outside' && finite(e.aircraftQuietEstimated)) {
    const noise = 10 - e.aircraftQuietEstimated;
    rows.push({ label: 'Aircraft', figure: `${noise.toFixed(1)} / 10`, sub: 'estimate from the routes, not measured', width: pct(noise, 10), mark: null });
  }
  if (finite(e.roadNoiseLdenDb) && finite(e.roadNoiseWhoGuidelineDb)) {
    const who = e.roadNoiseWhoGuidelineDb;
    rows.push({ label: 'Road', figure: `${e.roadNoiseLdenDb} dB`, sub: '', width: pct(e.roadNoiseLdenDb, who * 2), mark: 50 });
    guides.push(`${who} dB for road`);
  } else if (finite(e.roadNoiseBelowDb)) {
    rows.push({ label: 'Road', figure: `under ${e.roadNoiseBelowDb} dB`, sub: 'surveyed, below the lowest band', width: 0, mark: null });
  }
  if (!rows.length) return null;
  const meta = provenance['environment.aircraftNoiseLdenDb'] || provenance['environment.roadNoiseLdenDb'];
  const modelled = rows.some((r) => r.mark !== null);
  const period = meta && /^\d{4}$/.test(String(meta.period)) ? `, ${meta.period}` : '';
  const note = [
    guides.length ? `The line is the WHO guideline: ${guides.join(' and ')}, Lden.` : '',
    modelled ? `DEFRA's noise maps, modelled${period}.` : '',
  ].filter(Boolean).join(' ');
  return { rows, note };
}

/**
 * Step 03: { svg, credits: [{ text, href }] } for nitrogen dioxide, or null with nothing measured or modelled. DEFRA's
 * model joins only when the answer's provenance calls it modelled on a grid (as the full map's panel reads it: never
 * called measured), beside the nearest Breathe London sensor and DEFRA monitor; one scale, the WHO guideline through it.
 */
export function airPanel(e, provenance, sensor, monitor) {
  const meta = provenance?.['environment.no2AnnualMeanUgm3'];
  const res = /^([0-9.]{1,8}) ?km grid$/.exec(String(meta?.resolution || ''));
  const model = e && meta?.method === 'modelled' && finite(e.no2AnnualMeanUgm3)
    ? { kind: 'model', label: "DEFRA's model", sub: [res ? `this ${res[1]} km square` : 'this grid square', /^\d{4}$/.test(String(meta.period)) ? String(meta.period) : ''].filter(Boolean).join(' · '), v: e.no2AnnualMeanUgm3 }
    : null;
  const reading = (r) => (r?.no2 && finite(r.no2.mean) ? r.no2.mean : null);
  const rows = [
    model,
    sensor && { kind: 'sensor', label: sensor.name, sub: `sensor · ${stationDistance(sensor.km)}`, v: reading(sensor) },
    monitor && { kind: 'monitor', label: monitor.name, sub: `monitor · ${stationDistance(monitor.km)}`, v: reading(monitor) },
  ].filter(Boolean);
  if (!rows.some((r) => finite(r.v))) return null;
  const who = finite(e?.no2WhoGuidelineUgm3) ? e.no2WhoGuidelineUgm3 : AIR_WHO_2021.no2;
  return { svg: airChart('no2', rows, who), credits: [sensor?.credit, monitor?.credit].filter((c) => c?.text && c?.href) };
}

// ---- the page ----

const el = (tag, className, text) => {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text != null) n.textContent = text;
  return n;
};
const still = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** A tab list (the walkthrough's steps, the code samples): click or Enter selects; arrows, Home and End move. */
function bindTabs(list, onChange) {
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

/** Step 01: each example types into the little box and says where it opens. */
function bindTry() {
  const typed = document.getElementById('walk-typed');
  const buttons = [...document.querySelectorAll('[data-walk-try]')];
  if (!typed || !buttons.length) return;
  let timer = null;
  for (const b of buttons) {
    b.addEventListener('click', () => {
      const key = b.dataset.walkTry;
      const word = b.querySelector('b')?.textContent || '';
      for (const x of buttons) x.setAttribute('aria-pressed', String(x === b));
      for (const o of document.querySelectorAll('[data-walk-opens]')) o.hidden = o.dataset.walkOpens !== key;
      clearInterval(timer);
      if (still()) { typed.textContent = word; return; }
      let n = 0;
      typed.textContent = '';
      timer = setInterval(() => {
        n += 1;
        typed.textContent = word.slice(0, n);
        if (n >= word.length) clearInterval(timer);
      }, 55);
    });
  }
}

/** The developers band: Copy copies the sample on show (home-engine.mjs reads data-copy when it is clicked). */
function onCodeTab(tab, panel) {
  const copy = document.querySelector('section.dev button.copy[data-copy]');
  const pre = panel.querySelector('pre[id]');
  if (copy && pre) {
    copy.dataset.copy = pre.id;
    copy.setAttribute('aria-label', `Copy the ${tab.textContent.trim()} request`);
  }
  const status = document.getElementById('copy-status');
  if (status) status.textContent = '';
}

// The full map's planes layer colours (scripts/build_planes_layer.py writes its steps into the layer's index.json).
// Optional: without them the bars are drawn in one neutral colour, never a guess at the layer's.
let stepsLoad = null;
const layerSteps = () => (stepsLoad ??= fetch('/data/planes-layer/index.json')
  .then((r) => (r.ok ? r.json() : null)).then((d) => (Array.isArray(d?.steps) ? d.steps : []))
  .catch(() => { stepsLoad = null; return []; }));

const FAILED = "The example's figures could not load just now. Search a postcode above to see them for any street.";

function settle(box, nodes) {
  if (!box) return;
  box.replaceChildren(...nodes);
  box.removeAttribute('aria-busy');
}

function writeNoise(box, n) {
  if (!n) return settle(box, [el('p', 'walk-wait', 'No noise figures for this example.')]);
  const rows = el('div', 'walk-rows');
  for (const r of n.rows) {
    const row = el('div', 'walk-row');
    const label = el('span', 'walk-label', r.label);
    if (r.sub) label.append(el('small', null, r.sub));
    const bar = el('span', 'walk-bar');
    bar.setAttribute('aria-hidden', 'true');
    const fill = el('i');
    fill.style.width = `${r.width.toFixed(1)}%`;
    bar.append(fill);
    if (r.mark !== null) {
      const mark = el('b');
      mark.style.left = `${r.mark}%`;
      bar.append(mark);
    }
    row.append(label, bar, el('span', 'walk-fig', r.figure));
    rows.append(row);
  }
  settle(box, [rows, el('p', 'walk-note', n.note)]);
}

function writeAir(box, a) {
  if (!a) return settle(box, [el('p', 'walk-wait', 'No air figures near this example.')]);
  const fig = el('figure', 'walk-air');
  fig.append(el('figcaption', null, 'Nitrogen dioxide, µg/m³'));
  // airChart() returns SVG text with every name escaped (js/street_report.mjs), as the full map's panel sets it; parsed
  // by the HTML parser (a template), which gives an <svg> without xmlns its SVG namespace.
  const t = document.createElement('template');
  t.innerHTML = a.svg;
  const svg = t.content.querySelector('svg');
  if (svg) fig.append(svg);
  const credit = el('p', 'walk-note');
  a.credits.forEach((c, i) => {
    if (i) credit.append(' · ');
    credit.append(Object.assign(el('a', null, c.text), { href: c.href }));
  });
  settle(box, a.credits.length ? [fig, credit] : [fig]);
}

function writePlanes(box, w) {
  if (!w) return settle(box, [el('p', 'walk-wait', 'No planes figures for this example.')]);
  const head = el('p', 'walk-planes-head');
  for (const part of w.sentence) head.append(part.strong ? el('b', null, part.text) : part.text);
  const bars = el('div', 'walk-pbars');
  for (const r of w.rows) {
    const row = el('div', 'walk-pb');
    const label = el('span', 'walk-pb-l', r.label);
    label.append(el('small', null, r.share));
    const track = el('span', 'walk-pb-t');
    track.setAttribute('aria-hidden', 'true');
    if (r.bar) {
      const fill = el('i', r.range ? 'range' : null);
      fill.style.left = `${(r.bar[0] * 100).toFixed(1)}%`;
      fill.style.width = `${Math.max(1, (r.bar[1] - r.bar[0]) * 100).toFixed(1)}%`;
      if (r.colour) fill.style.background = r.colour;
      track.append(fill);
    }
    row.append(label, track, el('b', 'walk-pb-v', r.figure));
    bars.append(row);
  }
  const how = el('p', 'walk-note', `${w.foot} `);
  how.append(Object.assign(el('a', null, 'How the planes are counted'), { href: w.how }));
  settle(box, [head, bars, how]);
}

async function fillWalk() {
  const boxes = Object.fromEntries([...document.querySelectorAll('[data-walk-fill]')].map((b) => [b.dataset.walkFill, b]));
  let engine;
  let ex = null;
  try {
    engine = await import('./home-engine.mjs');
    ex = await engine.exampleAnswer();
  } catch {
    ex = null;
  }
  if (!ex) {
    for (const box of Object.values(boxes)) settle(box, [el('p', 'walk-wait', FAILED)]);
    return;
  }
  const { geo, env } = ex;
  const e = env.environment;
  const prov = env.provenance || {};
  try { writeNoise(boxes.noise, noiseRows(e, prov)); } catch { settle(boxes.noise, [el('p', 'walk-wait', FAILED)]); }
  engine.airFiles().then(([sensors, monitors]) => {
    const sensor = sensors ? nearestSensor(sensors, geo.latitude, geo.longitude) : null;
    const monitor = monitors ? nearestMonitor(monitors, geo.latitude, geo.longitude) : null;
    writeAir(boxes.air, airPanel(e, prov, sensor, monitor));
  }).catch(() => settle(boxes.air, [el('p', 'walk-wait', FAILED)]));
  Promise.all([engine.planesFilesFor(geo.postcode), layerSteps()]).then(([[file, info], steps]) => {
    writePlanes(boxes.planes, planesWalk(planesModel(file, info, geo.postcode), steps));
  }).catch((err) => {
    // As the answer above: a file the model cannot read is said in the console, so the page tests still see it.
    console.error('The walkthrough\'s planes step is empty: its files could not be read.', err);
    settle(boxes.planes, [el('p', 'walk-wait', FAILED)]);
  });
}

function init() {
  bindTabs(document.querySelector('.walk-steps'));
  bindTabs(document.querySelector('.code-tabs'), onCodeTab);
  bindTry();
  const walk = document.getElementById('walkthrough');
  if (!walk || !document.querySelector('[data-walk-fill]')) return;
  // A plain visit has asked for the example already (the map's answer opens on it), so this costs nothing new; a deep
  // link has not, so the walkthrough asks only when it comes near the screen.
  let started = false;
  const start = () => { if (!started) { started = true; fillWalk(); } };
  if (!('IntersectionObserver' in window)) { start(); return; }
  const io = new IntersectionObserver((entries) => {
    if (entries.some((x) => x.isIntersecting)) { io.disconnect(); start(); }
  }, { rootMargin: '600px 0px' });
  io.observe(walk);
}

if (typeof document !== 'undefined') init();
