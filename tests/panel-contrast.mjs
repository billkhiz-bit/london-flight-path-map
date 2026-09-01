#!/usr/bin/env node
/**
 * MEASURED colour contrast over the states a user actually reads.
 *
 * WHY THIS EXISTS, WHEN `a11y-source.mjs` ALREADY RUNS AXE HERE.
 *
 * Two reasons, both measured on 2026-09-01 while closing audit D5 and D7.
 *
 * 1. AXE CANNOT SEE MOST OF THIS PAGE'S CONTRAST. Opening the detail panel and
 *    asking axe for `color-contrast` returns, at 1440x900:
 *
 *        violations: 0        colour-contrast INCOMPLETE: 66
 *
 *    `incomplete` is axe declining to answer - it could not resolve an
 *    effective background - and a gate that reads `violations` alone counts
 *    every one of those as a pass. That is exactly how `.score-explain`
 *    shipped at 4.47:1 across five rows of every borough panel and the persona
 *    switch shipped at 2.71:1, under a green accessibility gate that had been
 *    scanning this very state since 2026-08-24.
 *
 * 2. THE STATE THAT GATE REACHES IS NOT THE ONE IT NAMES. It clicks
 *    `.borough-list-item, .rank-table tbody tr`; the first selector survives in
 *    CSS only (its own comment says so), and the second opens the AREA panel -
 *    `Cheam (SM3 8BD)`, not a borough. `updateSidebar()`, which renders the
 *    borough panel where D5, D7 and D8 all live, was never reached at all. A
 *    state label is not the state.
 *
 * WHAT THIS MEASURES. For every visible text node in the state, the effective
 * foreground and background - walking ancestors for the first opaque
 * background, compositing any alpha on the way - and the WCAG 2.1 AA ratio for
 * its computed font size and weight. No axe, no heuristics.
 *
 * WHAT IT DELIBERATELY DOES NOT DO. An element painted over a
 * `background-image` (this page's `.btn-primary` is a linear-gradient) has no
 * computable background colour, and the audit's own finder produced a false
 * `1:1` on exactly that before it caught itself. Those are counted and printed
 * as UNMEASURABLE rather than passed silently or failed loudly - naming what
 * the instrument cannot see is the only honest option, and a count that grows
 * is a signal to come back.
 *
 *   node tests/panel-contrast.mjs
 */
import { chromium } from 'playwright';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { join, extname } from 'node:path';

const ROOT = process.cwd();
const PORT = 8934;
const TYPES = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.mjs': 'application/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.woff2': 'font/woff2',
  '.webmanifest': 'application/manifest+json',
};

// Both viewports, because three separate mobile rules in this repo have been
// keyed on width while the failing dimension was height, and because the
// borough panel renders different chrome in the tabbed mobile layout.
const VIEWPORTS = [
  { label: 'desktop', width: 1440, height: 900 },
  { label: 'phone', width: 390, height: 844 },
];

// The two panel states, reached by DIFFERENT routes on purpose. The area panel
// comes from the neighbourhood ranking; the borough panel comes from
// updateSidebar() and is the one no gate had ever opened.
const STATES = [
  {
    name: 'borough panel',
    // FAILS rather than falls back. The first version of this state did fall
    // back to a ranking row when it could not find a borough name, and both
    // states then measured the SAME area panel while the report named two -
    // which is the defect this whole file was written to catch, reproduced
    // inside the catcher. Identical node counts across two states was the tell.
    open: async (page) =>
      page.evaluate(() => {
        // `selectBoroughByName` is the app's own entry point - the one a map
        // click calls - and `getActiveBoroughData()` is where it looks the
        // borough up, so asking the same function for a name cannot drift from
        // what it will accept. `BOROUGH_DATA` is NOT a global (measured), which
        // is what defeated the first attempt.
        if (
          typeof window.selectBoroughByName !== 'function' ||
          typeof window.getActiveBoroughData !== 'function'
        ) {
          return null;
        }
        const names = Object.keys(window.getActiveBoroughData() || {});
        if (!names.length) return null;
        window.selectBoroughByName(names[0]);
        return names[0];
      }),
    // A borough panel names a BOROUGH. The area panel names a postcode, so this
    // is what tells the two apart from the outside.
    expect: (title) => !/\(\w{1,2}\d/.test(title),
  },
  {
    name: 'area panel',
    open: async (page) =>
      page.evaluate(() => {
        const row = document.querySelector('.rank-table tbody tr');
        if (row) {
          row.click();
          return 'ranking row';
        }
        return null;
      }),
    // ... and the area panel names a postcode district, e.g. "Cheam (SM3 8BD)".
    expect: (title) => /\(\w{1,2}\d/.test(title),
  },
];

// WHICH STATES TO RUN. `--only=<prefix>` selects one; the default is all.
//
// This exists because the two states have DIFFERENT NETWORK NEEDS, and hiding
// that inside the gate would make it dishonest in one direction or the other.
// Measured with every offsite request aborted: the borough panel measures 134
// nodes at desktop and 87 at phone, and BOTH area states fail with
// `opened=ranking row, score rows=0`. The area panel is reached by a
// ranking-row click that runs triggerSearch(), which resolves the district
// through api.postcodes.io - so its readiness includes a third party's
// availability, and the borough panel's does not.
//
// The alternative was an in-gate skip: notice the resolver is unreachable and
// pass anyway. That is this repo's most-repeated defect wearing a new hat - a
// gate that reports "nothing wrong here" when what it means is "I could not
// look". preflight already owns this distinction with `check` vs `net_check`,
// which prints a skipped stage on its own line, in its own position, and
// reports the run INCOMPLETE. Running one state per stage reuses that instead
// of reinventing it, and puts the dependency in the report where it is read.
const ONLY = (process.argv.find((a) => a.startsWith('--only=')) || '').slice('--only='.length);
const ACTIVE_STATES = ONLY ? STATES.filter((s) => s.name.startsWith(ONLY)) : STATES;
if (ONLY && !ACTIVE_STATES.length) {
  console.log(
    `FAIL: --only=${ONLY} matched no state. Known: ${STATES.map((s) => s.name).join(', ')}`
  );
  process.exit(1);
}

const server = createServer(async (req, res) => {
  const clean = decodeURIComponent(req.url.split('?')[0]);
  const candidates = clean.endsWith('/')
    ? [join(clean, 'index.html')]
    : [clean, `${clean}.html`, join(clean, 'index.html')];
  for (const candidate of candidates) {
    try {
      const body = await readFile(join(ROOT, candidate));
      res.writeHead(200, { 'Content-Type': TYPES[extname(candidate)] || 'application/octet-stream' });
      res.end(body);
      return;
    } catch {
      /* next candidate */
    }
  }
  res.writeHead(404);
  res.end('not found');
});
await new Promise((resolve) => server.listen(PORT, '127.0.0.1', resolve));

// Runs in the page. Returns one record per visible text-bearing element.
const COLLECT = () => {
  const parse = (value) => {
    const m = String(value).match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(',').map((x) => parseFloat(x.trim()));
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const over = (fg, bg) => ({
    r: fg.r * fg.a + bg.r * (1 - fg.a),
    g: fg.g * fg.a + bg.g * (1 - fg.a),
    b: fg.b * fg.a + bg.b * (1 - fg.a),
    a: 1,
  });
  const lum = (c) => {
    const f = (v) => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  };
  const ratio = (a, b) => {
    const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
  };
  const label = (el) => {
    if (el.id) return `#${el.id}`;
    const cls = (el.getAttribute('class') || '').trim().split(/\s+/).filter(Boolean)[0];
    return el.tagName.toLowerCase() + (cls ? `.${cls}` : '');
  };

  const out = [];
  for (const el of document.querySelectorAll('body *')) {
    // Only elements holding their OWN text. A wrapper inherits nothing to fail
    // on, and counting it would report every defect once per ancestor.
    const own = [...el.childNodes]
      .filter((n) => n.nodeType === 3)
      .map((n) => n.textContent.trim())
      .join(' ')
      .trim();
    if (!own) continue;
    const rect = el.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) === 0) continue;
    if (el.closest('[inert]') || el.closest('[aria-hidden="true"]')) continue;

    const fg = parse(cs.color);
    if (!fg) continue;

    // Walk for the first opaque background, compositing translucent layers.
    let bg = null;
    let unmeasurable = null;
    let node = el;
    let stack = [];
    while (node) {
      const s = getComputedStyle(node);
      if (s.backgroundImage && s.backgroundImage !== 'none') {
        unmeasurable = `${label(node)} has background-image`;
        break;
      }
      const c = parse(s.backgroundColor);
      if (c && c.a > 0) {
        if (c.a >= 1) {
          bg = c;
          break;
        }
        stack.push(c);
      }
      node = node.parentElement;
    }
    if (!bg && !unmeasurable) bg = { r: 255, g: 255, b: 255, a: 1 };
    if (unmeasurable) {
      out.push({ sel: label(el), text: own.slice(0, 40), unmeasurable });
      continue;
    }
    for (let i = stack.length - 1; i >= 0; i--) bg = over(stack[i], bg);

    const size = parseFloat(cs.fontSize);
    const weight = parseInt(cs.fontWeight, 10) || 400;
    const large = size >= 24 || (size >= 18.66 && weight >= 700);
    out.push({
      sel: label(el),
      text: own.slice(0, 40),
      fg: cs.color,
      bg: `rgb(${Math.round(bg.r)}, ${Math.round(bg.g)}, ${Math.round(bg.b)})`,
      size,
      large,
      need: large ? 3.0 : 4.5,
      ratio: Math.round(ratio(fg.a >= 1 ? fg : over(fg, bg), bg) * 100) / 100,
    });
  }
  return out;
};

// WAIT FOR THE STATE, NOT FOR THE CLOCK.
//
// This was a fixed `waitForTimeout(1200)` until 2026-09-01, which made a
// BLOCKING, source-pointed gate depend on a third party's latency: opening the
// area panel clicks a ranking row, which runs triggerSearch(), which resolves
// the district through api.postcodes.io. Measured warm, the panel renders
// 113-147 ms after the click; on a cold first run the same sequence overran
// 1200 ms and the gate printed "could not open" against a tree whose panel was
// perfectly fine. A blocking gate that reds on someone else's DNS is a gate
// that gets switched off - this repo already carries a top-up retry on the
// flood gate for exactly that reason.
//
// The failure semantics are unchanged: a state that never opens still reds, it
// just takes READY_TIMEOUT_MS to say so instead of 1.2 s. The timeout is the
// budget for "this state is never going to open", not for "the network is
// slow today", so it is deliberately far above any observed render.
const READY_TIMEOUT_MS = 15000;
const POLL_MS = 100;

const countScoreRows = (page) =>
  page.evaluate(
    () => document.querySelectorAll('#sidebar-content .score-breakdown .score-row').length
  );

async function waitForPanel(page) {
  const deadline = Date.now() + READY_TIMEOUT_MS;
  for (;;) {
    const rows = await countScoreRows(page);
    if (rows > 0) return rows;
    if (Date.now() >= deadline) return 0;
    await page.waitForTimeout(POLL_MS);
  }
}

let failures = 0;
let measured = 0;
let unmeasurable = 0;
let statesReached = 0;

const browser = await chromium.launch();
for (const vp of VIEWPORTS) {
  const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
  const page = await context.newPage();
  for (const state of ACTIVE_STATES) {
    await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('#app', { state: 'visible', timeout: 30000 });
    const opened = await state.open(page);
    const rows = await waitForPanel(page);
    const header = `${state.name} @ ${vp.label}`.padEnd(30);
    // NOT REACHING THE STATE IS A FAILURE. The gate this one was written to
    // replace passed for eight days while scanning a state it had not opened.
    if (!opened || rows === 0) {
      console.log(`${header} FAIL could not open (opened=${opened}, score rows=${rows})`);
      failures++;
      continue;
    }
    // AND IT MUST BE THE STATE IT SAYS. Checked against what the panel titles
    // itself, not against the selector used to get here - a selector proves
    // only that something was clicked.
    const panelTitle = await page.evaluate(
      () => (document.getElementById('sidebar-title') || {}).textContent || ''
    );
    if (state.expect && !state.expect(panelTitle)) {
      console.log(`${header} FAIL opened the wrong panel - title is "${panelTitle.trim()}"`);
      failures++;
      continue;
    }
    statesReached++;
    const records = await page.evaluate(COLLECT);
    const bad = records.filter((r) => !r.unmeasurable && r.ratio < r.need);
    const skipped = records.filter((r) => r.unmeasurable);
    measured += records.length - skipped.length;
    unmeasurable += skipped.length;
    console.log(
      `${header} ${bad.length ? 'FAIL' : 'ok  '} ` +
        `${records.length - skipped.length} text nodes measured, ` +
        `${bad.length} below AA, ${skipped.length} unmeasurable`
    );
    for (const r of bad.slice(0, 12)) {
      console.log(
        `    ${r.ratio.toFixed(2)}:1 (needs ${r.need}) ${r.sel} ${r.fg} on ${r.bg} ` +
          `${r.size}px - "${r.text}"`
      );
    }
    failures += bad.length;
  }
  await context.close();
}
await browser.close();
server.close();

// A FLOOR, per state and in total. Every count here has been satisfied by
// nothing at least once in this repo's history: a selector that stops matching,
// a panel that renders empty, a collector that returns [] because the page
// changed shape. "0 below AA" over 0 nodes is not a pass.
const EXPECTED_STATES = VIEWPORTS.length * ACTIVE_STATES.length;
const MIN_NODES = 40;
console.log('');
console.log(
  `${statesReached} of ${EXPECTED_STATES} states opened, ${measured} text nodes measured, ` +
    `${unmeasurable} unmeasurable (background-image)`
);
if (statesReached < EXPECTED_STATES) {
  console.log(`FAIL: ${EXPECTED_STATES - statesReached} state(s) never opened.`);
  process.exit(1);
}
if (measured < MIN_NODES) {
  console.log(`FAIL: only ${measured} text nodes measured, floor is ${MIN_NODES}. The`);
  console.log('      collector is finding nothing, which reads identically to a clean page.');
  process.exit(1);
}
if (failures) {
  console.log(`FAIL: ${failures} text node(s) below WCAG 2.1 AA.`);
  process.exit(1);
}
console.log(
  `OK: every measured text node clears WCAG 2.1 AA in ` +
    `${ACTIVE_STATES.map((s) => s.name).join(' + ')}.`
);
