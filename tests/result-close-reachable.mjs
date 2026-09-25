/**
 * The result card's close button must stay reachable however far the card
 * has been read, on the phone web layout.
 *
 * WHY THIS EXISTS (audit M-9, 2026-09-25)
 * ---------------------------------------
 * On 2026-09-24 `#tab-analysis` became its own scroller, because the sidebar
 * around it is `pointer-events: none` and a scroller that cannot be hit
 * cannot be scrolled. The close button was `position: absolute` inside that
 * card - and an absolute child of a scroller scrolls with its content.
 * Measured at 390x844 on SW11 1AA: the button sat at y=-3666 once the card
 * was read to its end, so dismissing a result meant swiping back ~3,900px.
 * It is `position: sticky` now.
 *
 * WHY NO EXISTING GATE COULD SEE IT
 * ---------------------------------
 * responsive.mjs measures each state at its initial scroll position, where
 * the button is fine (y=247). The defect exists only AFTER a scroll, and
 * nothing in tests/ scrolled the result card at all.
 *
 * HOW IT SCROLLS
 * --------------
 * Real CDP touch drags, not `Input.synthesizeScrollGesture`: headless, the
 * synthetic gesture scrolls nothing, and a gate built on it passes by never
 * moving. The gate asserts the card DID move before it asserts anything
 * about the button, so "the drag did nothing" cannot read as a pass.
 *
 * It needs api.postcodes.io to resolve the postcode, so it is a net_check.
 *
 *   node tests/result-close-reachable.mjs
 */
import { chromium } from 'playwright';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();
const PORT = 8962;
const POSTCODE = 'SW11 1AA';
const VIEWPORTS = [
  { w: 390, h: 844, label: '390x844 portrait' },
  { w: 320, h: 568, label: '320x568 portrait' },
  { w: 844, h: 390, label: '844x390 landscape' },
];
// The card must be read at least this far for the check to mean anything. A
// result that fits on screen proves nothing about a button that scrolls.
const MIN_SCROLLED_PX = 500;

const TYPES = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.mjs': 'application/javascript',
  '.json': 'application/json',
  '.css': 'text/css',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
  '.webmanifest': 'application/manifest+json',
};

const server = http.createServer((req, res) => {
  let p = decodeURIComponent(req.url.split('?')[0]);
  if (p === '/') p = '/index.html';
  const file = path.join(ROOT, p);
  if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    res.writeHead(404).end('not found');
    return;
  }
  res.writeHead(200, { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream' });
  fs.createReadStream(file).pipe(res);
});
await new Promise((r) => server.listen(PORT, r));
const browser = await chromium.launch();

/** Where the close button is, and whether a finger at its centre hits it. */
function closeState(page) {
  return page.evaluate(() => {
    const btn = document.querySelector('.result-close');
    const card = document.querySelector('#tab-analysis');
    const r = btn ? btn.getBoundingClientRect() : null;
    let hit = false;
    let at = null;
    if (r && r.width && r.height) {
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const inView = cy >= 0 && cy <= innerHeight && cx >= 0 && cx <= innerWidth;
      const el = inView ? document.elementFromPoint(cx, cy) : null;
      hit = !!el && (el === btn || btn.contains(el));
      at = el ? el.tagName.toLowerCase() + (el.className ? '.' + String(el.className).split(' ')[0] : '') : 'offscreen';
    }
    return {
      y: r ? Math.round(r.top + r.height / 2) : null,
      hit,
      at,
      scrollTop: card ? Math.round(card.scrollTop) : 0,
      scrollMax: card ? card.scrollHeight - card.clientHeight : 0,
    };
  });
}

async function drag(page, cdp, x, y0, y1) {
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y: y0 }] });
  const steps = 12;
  for (let i = 1; i <= steps; i++) {
    await cdp.send('Input.dispatchTouchEvent', {
      type: 'touchMove',
      touchPoints: [{ x, y: y0 + ((y1 - y0) * i) / steps }],
    });
    await page.waitForTimeout(16);
  }
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await page.waitForTimeout(300);
}

let fail = 0;
console.log('Result close button reachable after scrolling the card:');

for (const vp of VIEWPORTS) {
  const ctx = await browser.newContext({
    viewport: { width: vp.w, height: vp.h },
    hasTouch: true,
    isMobile: true,
  });
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  try {
    await page.goto(`http://localhost:${PORT}/index.html`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('#search-input', { state: 'visible', timeout: 15000 });
    await page.fill('#search-input', POSTCODE);
    await page.press('#search-input', 'Enter');
    // Poll for the state we want - a result with a visible close button and a
    // card long enough to scroll - never for one that is already true.
    const reached = await page
      .waitForFunction(
        (min) => {
          const card = document.querySelector('#tab-analysis');
          const btn = document.querySelector('.result-close');
          return (
            card &&
            btn &&
            !card.querySelector('.empty-state') &&
            btn.getBoundingClientRect().width > 0 &&
            card.scrollHeight - card.clientHeight > min
          );
        },
        MIN_SCROLLED_PX,
        { timeout: 20000 },
      )
      .then(() => true)
      .catch(() => false);
    if (!reached) {
      console.log(`  FAIL ${vp.label.padEnd(20)} never reached a scrollable result for ${POSTCODE}`);
      fail++;
      continue;
    }
    await page.waitForTimeout(1500);
    const before = await closeState(page);

    const box = await page.locator('#tab-analysis').boundingBox();
    const x = box.x + box.width / 2;
    const top = Math.max(box.y + 60, 10);
    const bottom = Math.min(box.y + box.height - 20, vp.h - 20);
    for (let i = 0; i < 20; i++) await drag(page, cdp, x, bottom, top);
    const after = await closeState(page);

    const moved = after.scrollTop - before.scrollTop;
    let verdict = 'ok  ';
    let why = '';
    if (moved < MIN_SCROLLED_PX) {
      // The drag did not move the card, so nothing below would be evidence.
      verdict = 'FAIL';
      why = `card scrolled only ${moved}px of ${after.scrollMax} - the gesture did not scroll it`;
    } else if (!before.hit) {
      verdict = 'FAIL';
      why = `close not hit-testable at open (y=${before.y}, finger hits ${before.at})`;
    } else if (!after.hit) {
      verdict = 'FAIL';
      why = `close unreachable after scrolling ${moved}px (y=${after.y}, finger hits ${after.at})`;
    }
    if (verdict === 'FAIL') fail++;
    console.log(
      `  ${verdict} ${vp.label.padEnd(20)} scrolled ${String(moved).padStart(5)}px, close y ${before.y} -> ${after.y}` +
        (why ? `  ${why}` : ''),
    );
  } finally {
    await ctx.close();
  }
}

await browser.close();
server.close();

if (fail) {
  console.log(`\n${fail} FAILED`);
  console.log('A reader who scrolls the result card loses the only way to close it.');
  console.log("Check `.app[data-mview='search'] .result-close` in the <=900px block.");
  process.exit(1);
}
console.log('\nall good');
