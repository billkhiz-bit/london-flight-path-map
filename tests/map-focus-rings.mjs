/**
 * The full map's rings, legend edges and footer landmarks (audit 2026-11-23, M-13, M-14, M-16), measured in the DOM.
 *
 *   M-13 The city buttons, the footer links (desktop and phone) and a borough card's SAVE fell back to the browser's own
 *        focus ring: amber #E59700 on Chromium's phone theme, 1.87:1 on the map's grey (WCAG 1.4.11 asks 3:1).
 *        tests/test_focus_ring_contrast.py holds the rings written in the CSS; it cannot see a control that has none.
 *        Each is focused from the keyboard here and its ring read: the site's --focus #d35a12, solid, 2 px or more.
 *   M-14 The phone's dark legend: the planes steps' darkest swatches read 1.38:1 and 2.36:1 against it, their edge
 *        rgba(0,0,0,0.2) lost on it. Every swatch's edge, laid over the panel's #252524, must stand 3:1 from it.
 *   M-16 The two footers sat inside <main> / <aside>, where a footer is no landmark and its aria-label is dropped:
 *        "Sky Score links" must be a navigation landmark by that name.
 * Serves the WORKING TREE; RED-PROOF: SKY_INDEX serves another copy as the map.
 * Run: node tests/map-focus-rings.mjs
 */

import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join } from 'node:path';
import { chromium } from 'playwright';

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
const PORT = 8945;
const MAP = process.env.SKY_INDEX || join(ROOT, 'index.html');
const TYPES = {
  '.html': 'text/html', '.js': 'application/javascript', '.mjs': 'application/javascript', '.json': 'application/json',
  '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.webmanifest': 'application/manifest+json',
};
const server = createServer(async (req, res) => {
  const url = decodeURIComponent(req.url.split('?')[0]);
  const file = url === '/' || url === '/index.html' ? MAP : join(ROOT, url);
  try {
    const buf = await readFile(file);
    res.writeHead(200, { 'content-type': TYPES[extname(file)] || 'application/octet-stream' });
    res.end(buf);
  } catch { res.writeHead(404); res.end('nf'); }
});
await new Promise((r) => server.listen(PORT, '127.0.0.1', r));
const BASE = `http://127.0.0.1:${PORT}/index.html`;
const FOCUS = 'rgb(211, 90, 18)'; // --focus #d35a12

let fail = 0;
const check = (name, ok, detail = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${name}${detail ? '  ' + detail : ''}`);
  if (!ok) fail += 1;
};
const browser = await chromium.launch();

/** Focus `selector`'s first RENDERED match as a keyboard user would reach it, then read its ring. */
async function ring(page, selector) {
  await page.keyboard.press('Shift'); // a key press first, so programmatic focus shows :focus-visible as Tab would
  const found = await page.evaluate((sel) => {
    const el = [...document.querySelectorAll(sel)].find((e) => e.getClientRects().length);
    if (!el) return false;
    el.focus();
    window.__ringed = el;
    return true;
  }, selector);
  if (!found) return null;
  // The city buttons ease `all` over 0.15 s: read at once, the ring was caught at width 0, part-way in.
  await page.waitForTimeout(400);
  return page.evaluate(() => {
    const el = window.__ringed;
    const cs = getComputedStyle(el);
    return { visible: el.matches(':focus-visible'), color: cs.outlineColor, style: cs.outlineStyle, width: parseFloat(cs.outlineWidth) };
  });
}
const isSiteRing = (r) => !!r && r.visible && r.color === FOCUS && r.style === 'solid' && r.width >= 2;

console.log('Desktop, 1366');
{
  const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
  await page.goto(`${BASE}?city=london&borough=Hounslow`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#sidebar-content .fav-btn', { timeout: 30000 }).catch(() => {});
  for (const [name, sel] of [['a city button', '.city-btn'], ['a footer link', '.site-footer a'], ["the borough card's SAVE", '#sidebar-content .fav-btn']]) {
    const r = await ring(page, sel);
    check(`${name} takes the site's focus ring`, isSiteRing(r), JSON.stringify(r));
  }
  const named = await page.getByRole('navigation', { name: 'Sky Score links' }).count();
  const footers = await page.evaluate(() => document.querySelectorAll('footer[aria-label]').length);
  check('the footer links are a navigation landmark named "Sky Score links"', named >= 1 && footers === 0, `navigation ${named}, named footers ${footers}`);
  await page.close();
}

console.log('Phone, 390');
{
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.city-btn', { timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(1500);
  for (const [name, sel] of [['a city button', '.city-btn'], ['a phone footer link', '.sheet-footer a'], ['the phone footer\'s More', '.sheet-footer summary']]) {
    const r = await ring(page, sel);
    check(`${name} takes the site's focus ring`, isSiteRing(r), JSON.stringify(r));
  }
  // Every swatch's edge laid over the dark panel (#252524, the panel's rgba(20,20,20,0.92) over the map, measured
  // 2026-08-24) must stand 3:1 from it.
  const edges = await page.evaluate(() => {
    const panel = document.querySelector('.map-legend');
    const bg = getComputedStyle(panel).backgroundColor;
    return { bg, edges: [...panel.querySelectorAll('.legend-swatch')].map((s) => getComputedStyle(s).borderTopColor) };
  });
  const lum = (rgb) => rgb.map((v) => v / 255).map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
    .reduce((s, v, i) => s + v * [0.2126, 0.7152, 0.0722][i], 0);
  const ground = [37, 37, 36];
  const worst = Math.min(...edges.edges.map((c) => {
    const v = c.match(/[\d.]+/g).map(Number);
    const a = v.length > 3 ? v[3] : 1;
    const paint = v.slice(0, 3).map((x, i) => a * x + (1 - a) * ground[i]);
    const [hi, lo] = [lum(paint), lum(ground)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
  }));
  check('on the dark phone legend every swatch has an edge standing 3:1 from the panel', edges.bg.startsWith('rgba(20, 20, 20') && edges.edges.length >= 6 && worst >= 3,
    `${edges.edges.length} swatches on ${edges.bg}; worst edge ${worst.toFixed(2)}:1`);
  await page.close();
}

await browser.close();
server.close();
console.log('');
if (fail) {
  console.error(`FAIL: ${fail} map ring/edge/landmark check(s) failed`);
  process.exit(1);
}
console.log("OK: the map's controls take the site's ring, the dark legend's swatches are edged, and its links are a landmark");
