/**
 * The country tier and the city chips are independently absolute-positioned, so
 * every responsive override that moves one must move the other. It did not, and
 * between 901px and 1366px the chips rendered on top of the tabs — visible in no
 * screenshot taken at 1440px.
 *
 * Asserts they never overlap at any width, and that the tier is the topmost
 * element at its own coordinates.
 *
 *   node tests/selector-widths.mjs   (expects a server on :8920)
 */
import { chromium } from '@playwright/test';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';

const ROOT = process.cwd();
const PORT = 8922;
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.webmanifest': 'application/manifest+json' };
const server = createServer(async (req, res) => {
  const p = join(ROOT, normalize(decodeURIComponent(req.url.split('?')[0]) === '/' ? '/index.html' : decodeURIComponent(req.url.split('?')[0])));
  if (!p.startsWith(ROOT)) return res.writeHead(403).end();
  try {
    // Read before writing the header - see the note in locator-verify.mjs.
    // Same copied server, same bug: a missing file killed the harness with
    // ERR_HTTP_HEADERS_SENT instead of serving a 404.
    const body = await readFile(p);
    res.writeHead(200, { 'content-type': TYPES[extname(p)] || 'application/octet-stream' });
    res.end(body);
  } catch { res.writeHead(404).end(); }
});
await new Promise((r) => server.listen(PORT, r));

const browser = await chromium.launch();
let fail = 0;
// Widths chosen to straddle every breakpoint boundary in the file.
for (const w of [1680, 1440, 1367, 1366, 1200, 1024, 901, 900, 768]) {
  const page = await browser.newPage({ viewport: { width: w, height: 800 } });
  await page.goto(`http://localhost:${PORT}/index.html`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(700);
  const r = await page.evaluate(() => {
    const c = document.getElementById('country-selector');
    const s = document.getElementById('city-selector');
    const cb = c.getBoundingClientRect();
    const sb = s.getBoundingClientRect();
    const hit = document.elementFromPoint(cb.x + 6, cb.y + cb.height / 2);
    // EVERY CITY CHIP MUST BE INSIDE THE STRIP AT DESKTOP WIDTHS (2026-08-31,
    // audit D4).
    //
    // The strip is `overflow-x: auto`, so a chip scrolled past its edge is a
    // SCROLL case, and responsive.mjs correctly exempts it - the same
    // exemption that stops it failing on the mobile scroll strip. That is why
    // that gate could not see this: with a mouse there was no way to scroll at
    // all. Measured `offsetHeight - clientHeight = 0` at every width, so no
    // scrollbar exists; a plain vertical wheel left scrollLeft at 0; there is
    // no drag handler. Content is 1109px, so 652px of it - SIX of the ten
    // cities - was unreachable at 901px, and Greater Manchester was still off
    // the strip at 1366x768, the most common laptop resolution.
    //
    // Asserted only at >=901: below that the scroll strip is deliberate and
    // swipeable, and was itself the 2026-08-11 fix for chips the map container
    // clipped.
    const chips = [...s.querySelectorAll('.city-btn')];
    const outside = chips
      .filter((el) => {
        const q = el.getBoundingClientRect();
        return q.left < sb.left - 1 || q.right > sb.right + 1 || q.bottom > sb.bottom + 1;
      })
      .map((el) => el.textContent.trim());
    return {
      cy: Math.round(cb.y), sy: Math.round(sb.y),
      overlap: !(cb.bottom <= sb.top || sb.bottom <= cb.top),
      covered: !(hit && (hit.closest('#country-selector') !== null)),
      chips: chips.length,
      outside,
    };
  });
  const chipsEscaped = w >= 901 && r.outside.length > 0;
  const ok = !r.overlap && !r.covered && !chipsEscaped && r.chips >= 10;
  if (!ok) fail++;
  console.log(
    `${String(w).padStart(5)}px  country=${String(r.cy).padStart(3)} chips=${String(r.sy).padStart(3)} ` +
      `n=${r.chips}  ${ok ? 'OK' : 'FAIL' + (r.overlap ? ' overlap' : '') + (r.covered ? ' covered' : '') + (chipsEscaped ? ` outside-strip: ${r.outside.join(', ')}` : '') + (r.chips < 10 ? ` only ${r.chips} chips` : '')}`
  );
  await page.close();
}
await browser.close();
server.close();
console.log(`\nRESULT: ${fail === 0 ? 'PASS' : 'FAIL'}`);
process.exit(fail === 0 ? 0 : 1);
