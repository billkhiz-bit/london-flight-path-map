/**
 * Windows contrast themes (forced colours): legends keep their keys, a selection stays marked (audit I-5, 2026-11-23).
 *
 * Forced colours repaint every fill and border in the theme's few system colours. Measured on the live site that day:
 * the full map's DEFRA scale was an empty white bar, both flight-path lines white, the heliport mark gone and the planes
 * steps empty boxes; the front page's noise ramp vanished, and no selected tab (Check a postcode / Find areas, the
 * walkthrough's steps, curl / Python / JavaScript) nor the active city looked any different from the rest; "Check my
 * area" and "Sign me up" (border 0) read as plain text. axe cannot see any of it.
 *
 * Each element is read twice, in normal colours and with forced colours on (Chromium's emulation), and compared:
 *   - a legend KEY keeps the colour it has in normal colours (a key IS its colour);
 *   - a SELECTED tab or city differs from an unselected one of its row;
 *   - the two filled buttons have a visible edge.
 * Serves the WORKING TREE; RED-PROOF: SKY_INDEX / SKY_HOME serve another copy of the map / the front page.
 * Run: node tests/forced-colours.mjs
 */

import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join } from 'node:path';
import { chromium } from 'playwright';
import { stubLiveApi } from './stub-live-api.mjs';

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
const PORT = 8944;
const MAP = process.env.SKY_INDEX || join(ROOT, 'index.html');
const HOME = process.env.SKY_HOME || join(ROOT, 'home', 'index.html');
const TYPES = {
  '.html': 'text/html', '.js': 'application/javascript', '.mjs': 'application/javascript', '.json': 'application/json',
  '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.csv': 'text/csv',
  '.webmanifest': 'application/manifest+json',
};
const server = createServer(async (req, res) => {
  const url = decodeURIComponent(req.url.split('?')[0]);
  const file = url === '/' ? HOME : url === '/map/' || url === '/index.html' ? MAP : join(ROOT, url);
  try {
    const buf = await readFile(file);
    res.writeHead(200, { 'content-type': TYPES[extname(file)] || 'application/octet-stream' });
    res.end(buf);
  } catch { res.writeHead(404); res.end('nf'); }
});
await new Promise((r) => server.listen(PORT, '127.0.0.1', r));
const BASE = `http://127.0.0.1:${PORT}`;

let fail = 0;
/** WCAG contrast between two painted colours ("r,g,b"): a selection must stand 3:1 apart (1.4.11), not merely differ. */
const contrast = (a, b) => {
  const lum = (s) => s.split(',').map(Number).map((v) => v / 255).map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
    .reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
  if (!a || !b) return 0;
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};
const apart = (on, off) => contrast(on, off) >= 3;
const check = (name, ok, detail = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${name}${detail ? '  ' + detail : ''}`);
  if (!ok) fail += 1;
};

const browser = await chromium.launch();

/**
 * A colour as PAINTED: blended over the theme's own background (Canvas), so a transparent unselected tab and a white
 * selected one on a white theme read as the same white. Comparing raw values passed on master: forced colours keep
 * alpha, so rgb(255,255,255) "differed" from rgba(255,255,255,0) though the two looked identical.
 * Runs in the page (passed as a string, so the probes can call it).
 */
const PAINTED = `window.__painted = (c) => {
  const probe = document.createElement('div');
  probe.style.backgroundColor = 'Canvas';
  document.body.append(probe);
  const canvas = getComputedStyle(probe).backgroundColor.match(/[\\d.]+/g).map(Number);
  probe.remove();
  const v = (c || '').match(/[\\d.]+/g)?.map(Number);
  if (!v) return null;
  const a = v.length > 3 ? v[3] : 1;
  return v.slice(0, 3).map((x, i) => Math.round(a * x + (1 - a) * canvas[i])).join(',');
};`;

/** Each probe's computed styles in one page, read once with forced colours off and once on. */
async function readBoth(path, ready, probe) {
  const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
  await page.addInitScript(() => { try { localStorage.setItem('skipgc', 't'); } catch { /* none */ } });
  await stubLiveApi(page); // js/count.mjs counts nothing from localhost, so it is served as it is
  await page.goto(`${BASE}${path}`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(ready, null, { timeout: 30000 }).catch(() => {});
  await page.evaluate(PAINTED);
  // Each read waits out the controls' own transitions (the city buttons ease 0.15 s): read at once, the active city
  // was caught part-way from its dark fill to the highlight.
  await page.emulateMedia({ forcedColors: 'none' });
  await page.waitForTimeout(600);
  const normal = await page.evaluate(probe);
  // A LIGHT and a DARK contrast theme: most contrast users run a dark one, where a selection drawn in the page's own
  // dark fill is a black box on black. On the light theme alone, the active city's misplaced rule read as "different".
  const themes = {};
  for (const scheme of ['light', 'dark']) {
    await page.emulateMedia({ forcedColors: 'active', colorScheme: scheme });
    await page.waitForTimeout(600);
    themes[scheme] = await page.evaluate(probe);
  }
  await page.close();
  return { normal, themes };
}

console.log('The full map');
{
  const { normal, themes } = await readBoth('/map/', () => document.querySelectorAll('.noise-scale-bar > span').length > 0
    && document.querySelector('.city-btn.active'), () => {
    const cs = (el, p) => (el ? getComputedStyle(el)[p] : null);
    const active = document.querySelector('.city-btn.active');
    const other = [...document.querySelectorAll('.city-btn')].find((b) => b !== active && b.offsetParent);
    return {
      line: cs(document.querySelector('.legend-line'), 'borderTopColor'),
      heli: cs(document.querySelector('#legend-heli-row .legend-dot'), 'backgroundColor'),
      scale: [...document.querySelectorAll('.noise-scale-bar > span')].map((s) => cs(s, 'backgroundColor')),
      steps: [...document.querySelectorAll('#legend-planes-group .legend-swatch[style*="background"]')].map((s) => cs(s, 'backgroundColor')),
      activeBg: window.__painted(cs(active, 'backgroundColor')), otherBg: window.__painted(cs(other, 'backgroundColor')),
    };
  });
  for (const [theme, forced] of Object.entries(themes)) {
    const t = `(${theme} theme)`;
    check(`${t} a flight-path line keeps its colour`, !!normal.line && forced.line === normal.line, `${normal.line} -> ${forced.line}`);
    check(`${t} the heliport mark keeps its colour`, !!normal.heli && forced.heli === normal.heli, `${normal.heli} -> ${forced.heli}`);
    check(`${t} the DEFRA scale keeps every colour`, normal.scale.length > 5 && JSON.stringify(forced.scale) === JSON.stringify(normal.scale),
      `${normal.scale.length} blocks; first ${normal.scale[0]} -> ${forced.scale[0]}`);
    check(`${t} the planes steps keep their colours`, normal.steps.length === 4 && JSON.stringify(forced.steps) === JSON.stringify(normal.steps),
      JSON.stringify(forced.steps));
    check(`${t} the active city stands 3:1 apart from the others`, apart(forced.activeBg, forced.otherBg),
      `active ${forced.activeBg}, other ${forced.otherBg}, ${contrast(forced.activeBg, forced.otherBg).toFixed(2)}:1`);
  }
}

console.log('The front page');
{
  const { normal, themes } = await readBoth('/', () => document.querySelectorAll('.legend .ramp b').length > 0
    && document.querySelector('.walk-steps button[aria-selected="true"]'), () => {
    const cs = (el, p) => (el ? getComputedStyle(el)[p] : null);
    const pair = (sel) => {
      const all = [...document.querySelectorAll(sel)];
      const on = all.find((b) => b.getAttribute('aria-selected') === 'true');
      const off = all.find((b) => b.getAttribute('aria-selected') !== 'true');
      return { on: window.__painted(cs(on, 'backgroundColor')), off: window.__painted(cs(off, 'backgroundColor')), found: !!on && !!off };
    };
    const edge = (el) => (el ? { w: getComputedStyle(el).borderTopWidth, s: getComputedStyle(el).borderTopStyle } : null);
    return {
      ramp: [...document.querySelectorAll('.legend .ramp b')].map((b) => cs(b, 'backgroundColor')),
      tabs: pair('.tabs [role="tab"]'), walk: pair('.walk-steps button'), code: pair('.code-tabs button'),
      check: edge(document.querySelector('form.check button')), news: edge(document.querySelector('.news-row button')),
    };
  });
  for (const [theme, forced] of Object.entries(themes)) {
    const t = `(${theme} theme)`;
    check(`${t} the map's noise ramp keeps every colour`, normal.ramp.length > 3 && JSON.stringify(forced.ramp) === JSON.stringify(normal.ramp),
      `${normal.ramp.length} steps; first ${normal.ramp[0]} -> ${forced.ramp[0]}`);
    for (const [name, p] of [['Check a postcode / Find areas', forced.tabs], ["the walkthrough's steps", forced.walk], ['curl / Python / JavaScript', forced.code]]) {
      check(`${t} the selected tab of ${name} stands 3:1 apart from the others`, p.found && apart(p.on, p.off), `${JSON.stringify(p)} ${contrast(p.on, p.off).toFixed(2)}:1`);
    }
    for (const [name, e] of [['"Check my area"', forced.check], ['"Sign me up"', forced.news]]) {
      check(`${t} ${name} has a visible edge`, !!e && e.s !== 'none' && parseFloat(e.w) >= 1, JSON.stringify(e));
    }
  }
}

await browser.close();
server.close();
console.log('');
if (fail) {
  console.error(`FAIL: ${fail} forced-colours check(s) failed`);
  process.exit(1);
}
console.log('OK: legends keep their keys and selections stay marked in a Windows contrast theme');
