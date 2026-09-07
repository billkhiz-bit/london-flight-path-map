/**
 * The legal pages must be reachable from the homepage on a phone.
 *
 * WHY THIS EXISTS
 * ---------------
 * From 2026-08-28 to 2026-09-07 the mobile web homepage rendered exactly ONE
 * visible link - the skip link. No /privacy, no /terms, no /pricing, at any
 * phone width, in any state. Measured at the time:
 *
 *   390x844 default    1 visible link,  legal/funnel: NONE
 *   390x844 ?tabbed=0  10 visible links, legal/funnel: /pricing /privacy /terms
 *   1440x900 desktop   13 visible links, legal/funnel: /pricing /privacy /terms
 *
 * The cause was a rule whose justification expired underneath it.
 * `.is-tabbed .sheet-footer { display: none }` was correct when written: the
 * class was set on the NATIVE app alone, which has its own bottom nav. Two days
 * later `.is-tabbed` became the WEB default at <=900px and nothing re-read the
 * rule - so it hid the `.sheet-footer` that had been added specifically to
 * replace the desktop footer on mobile.
 *
 * WHY NO EXISTING GATE COULD SEE IT
 * ---------------------------------
 * `responsive.mjs` asks four questions - overflow, stranded, covered, clipped
 * above - and every one of them is about a control that IS rendered. axe has no
 * rule for "a link that used to be here is gone". Nothing in tests/ asserted
 * that a given href is reachable at all. A missing control is invisible to a
 * suite that only ever measures present ones.
 *
 * WHAT THIS ASSERTS, AND IN BOTH DIRECTIONS
 * -----------------------------------------
 * On the WEB at phone widths the links must be present and visible. In the
 * NATIVE simulation they must be ABSENT - the app carries its own navigation,
 * and asserting only presence would pass a tree that had simply deleted the
 * native rule. A one-directional check here would have been satisfied by the
 * very state that caused the defect, in reverse.
 *
 *   node tests/mobile-legal-links.mjs
 */
import { chromium } from 'playwright';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();
const PORT = 8934;
const REQUIRED = ['/privacy', '/terms'];
const VIEWPORTS = [
  { w: 320, h: 568, label: '320x568 portrait' },
  { w: 390, h: 844, label: '390x844 portrait' },
  { w: 844, h: 390, label: '844x390 landscape' },
  { w: 900, h: 800, label: '900x800 (top of the mobile range)' },
];

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

/** Hrefs that a finger could actually reach: non-zero box, nothing hidden above. */
async function visibleHrefs(page) {
  return page.evaluate(() => {
    const out = [];
    for (const a of document.querySelectorAll('a[href]')) {
      const r = a.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      let el = a;
      let hidden = false;
      while (el) {
        const s = getComputedStyle(el);
        if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') {
          hidden = true;
          break;
        }
        el = el.parentElement;
      }
      if (hidden) continue;
      // HIT-TESTED, not merely visible (2026-09-07). The first version of this
      // gate asked only whether the link had a box and no hidden ancestor - and
      // it passed while every footer link sat UNDERNEATH the sticky search
      // card, which is `z-index: 3` and pinned 38px below its own flow slot.
      // `elementFromPoint` on "Pricing" returned `div.search-box`: visible,
      // unclickable, and green. `responsive.mjs` caught it and this file did
      // not, in the one gate written for exactly this surface.
      //
      // This is the question a finger asks, and it is the same detector
      // responsive.mjs uses for `covered`.
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const at = document.elementFromPoint(cx, cy);
      if (!at || !(at === a || a.contains(at) || at.contains(a))) continue;
      out.push(a.getAttribute('href'));
    }
    return out;
  });
}

async function open({ w, h }, native) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  const page = await ctx.newPage();
  if (native) {
    // Same shim tests/native-sim-render.mjs uses, so the two agree on what
    // "native" means rather than each inventing it.
    await page.addInitScript(() => {
      window.Capacitor = { isNativePlatform: () => true, getPlatform: () => 'ios', Plugins: {} };
    });
  }
  await page.goto(`http://localhost:${PORT}/index.html`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);
  return { ctx, page };
}

let fail = 0;
console.log('Legal links reachable on a phone:');

for (const vp of VIEWPORTS) {
  const { ctx, page } = await open(vp, false);
  const hrefs = await visibleHrefs(page);
  const missing = REQUIRED.filter((r) => !hrefs.some((h) => (h || '').startsWith(r)));
  const ok = missing.length === 0;
  if (!ok) fail++;
  console.log(
    `  ${ok ? 'ok  ' : 'FAIL'} ${vp.label.padEnd(34)} ${hrefs.length} visible link(s)` +
      (ok ? '' : `  MISSING: ${missing.join(', ')}`),
  );
  await ctx.close();
}

// The other direction. Without this, deleting the native rule outright would
// pass every check above - and that is the mirror image of the defect.
{
  const { ctx, page } = await open(VIEWPORTS[1], true);
  const isNative = await page.evaluate(() =>
    document.documentElement.classList.contains('is-native'),
  );
  const hrefs = await visibleHrefs(page);
  const stillThere = REQUIRED.filter((r) => hrefs.some((h) => (h || '').startsWith(r)));
  if (!isNative) {
    console.log('  FAIL native sim did not set is-native, so this check proves nothing');
    fail++;
  } else if (stillThere.length) {
    console.log(
      `  FAIL native sim still shows the web footer (${stillThere.join(', ')}). The app` +
        ' has its own nav; showing both is the state the rule exists to prevent.',
    );
    fail++;
  } else {
    console.log(`  ok   native sim hides the web footer            is-native=${isNative}`);
  }
  await ctx.close();
}

await browser.close();
server.close();

if (fail) {
  console.log(`\n${fail} FAILED`);
  console.log('A phone visitor cannot reach the privacy notice or the terms from');
  console.log('the homepage. Check the .sheet-footer rules in the <=900px block.');
  process.exit(1);
}
console.log('\nall good');
