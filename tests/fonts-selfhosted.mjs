/**
 * Prove the self-hosted fonts actually load on every page whose font source
 * changed on 2026-08-05, and that no CSP rule blocks them.
 *
 * WHY THIS EXISTS. Fonts were moved off fonts.googleapis.com / fonts.gstatic.com
 * to close a UK GDPR Chapter V item: every page load was transferring the
 * visitor's IP address to Google in the US. The move touched nine pages' CSP.
 *
 * Every way that change can go wrong is SILENT:
 *   * a wrong /fonts/ path 404s and the browser falls back to a system font
 *   * a too-strict font-src blocks the woff2 and the browser falls back
 *   * a variable font declared with too narrow a font-weight range renders a
 *     clamped weight, which is the quietest failure of the three
 * In all three cases the page still renders and still looks broadly right. The
 * only way to know is to load it in a browser and ask the font system.
 *
 * Serves the repo over a local static server rather than hitting CloudFront, so
 * it validates SOURCE and can run before a deploy.
 *
 *   node tests/fonts-selfhosted.mjs
 */
import { createServer } from 'node:http';
import { createReadStream } from 'node:fs';
import { readFile, stat } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { chromium } from '@playwright/test';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PORT = 8099;

const TYPES = {
  '.html': 'text/html',
  '.css': 'text/css',
  '.js': 'application/javascript',
  '.mjs': 'application/javascript',
  '.json': 'application/json',
  '.woff2': 'font/woff2',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.webmanifest': 'application/manifest+json',
};

// family = null where the page has no sans face of its own (the prototype is
// mono-only). mono is asserted on every page.
const CASES = [
  { path: '/index.html', sans: 'Inter', mono: 'JetBrains Mono' },
  { path: '/terms.html', sans: 'Inter', mono: 'JetBrains Mono' },
  { path: '/privacy.html', sans: 'Inter', mono: 'JetBrains Mono' },
  { path: '/pricing.html', sans: 'Geist', mono: 'Geist Mono' },
  { path: '/changes.html', sans: 'Geist', mono: 'Geist Mono' },
  { path: '/api/index.html', sans: 'Geist', mono: 'Geist Mono' },
  { path: '/score-demo/index.html', sans: 'Geist', mono: 'Geist Mono' },
  { path: '/score-demo/status.html', sans: 'Geist', mono: 'Geist Mono' },
  { path: '/prototype/index.html', sans: null, mono: 'JetBrains Mono' },
];

// Weight 400 is declared by every family in fonts.css, so it is the one probe
// that is meaningful everywhere.
//
// An earlier version of this test probed 300-700 against every family and
// reported a failure on score-demo, because Geist Mono legitimately declares
// only 400-500. Probing weights a family never claimed tests the browser's
// clamping behaviour, not our configuration. The declared RANGES are asserted
// separately below, by parsing fonts.css, which is where that belongs.
const PROBE_WEIGHT = 400;

// Ranges must match scripts/vendor_fonts.py's output. Asserted against
// fonts.css so a regenerate that narrows a range cannot pass silently.
const EXPECTED_RANGES = {
  Geist: '300 700',
  'Geist Mono': '400 500',
  Inter: '300 600',
  'JetBrains Mono': '300 700',
};

const server = createServer(async (req, res) => {
  const rel = decodeURIComponent(req.url.split('?')[0]);
  const file = path.join(ROOT, rel === '/' ? '/index.html' : rel);
  try {
    const info = await stat(file);
    if (!info.isFile()) throw new Error('not a file');
    res.writeHead(200, { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream' });
    createReadStream(file).pipe(res);
  } catch {
    res.writeHead(404).end('not found');
  }
});

await new Promise((r) => server.listen(PORT, '127.0.0.1', r));

let failures = 0;

// Assert the declared weight ranges before opening a browser. This is the
// failure mode a rendering check cannot see: a variable font declared 400-600
// renders a 300-weight request clamped at 400, which looks like a slightly
// bolder page and nothing else.
const cssText = await readFile(path.join(ROOT, 'fonts', 'fonts.css'), 'utf8');
for (const [family, range] of Object.entries(EXPECTED_RANGES)) {
  const block = new RegExp(
    `font-family:\\s*'${family}';[\\s\\S]*?font-weight:\\s*([0-9 ]+);`,
    'm',
  ).exec(cssText);
  if (!block) {
    console.log(`FAIL  fonts.css declares no @font-face for '${family}'`);
    failures++;
  } else if (block[1].trim() !== range) {
    console.log(`FAIL  fonts.css '${family}' weight is "${block[1].trim()}", expected "${range}"`);
    failures++;
  }
}
console.log(`${failures === 0 ? 'PASS' : 'FAIL'}  fonts.css declared weight ranges\n`);

const browser = await chromium.launch();

for (const { path: page_path, sans, mono } of CASES) {
  const page = await browser.newPage();
  const violations = [];
  const failed = [];

  // Only font-related CSP violations matter here. Every page also logs
  // "frame-ancestors is ignored when delivered via a <meta> element" (true and
  // pre-existing, it needs a real header), and over local http the GoatCounter
  // script trips its own https-scheme allow-list. Neither has anything to do
  // with fonts, and failing on them would make this gate permanently red.
  page.on('console', (m) => {
    const t = m.text();
    if (/Content Security Policy|Refused to/i.test(t) && /font/i.test(t)) violations.push(t);
  });
  page.on('requestfailed', (r) => {
    if (r.url().includes('/fonts/')) failed.push(`${r.url()} ${r.failure()?.errorText}`);
  });
  page.on('response', (r) => {
    if (r.url().includes('/fonts/') && r.status() >= 400) failed.push(`${r.status()} ${r.url()}`);
  });

  await page.goto(`http://127.0.0.1:${PORT}${page_path}`, { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);

  const result = await page.evaluate(
    async ([sansName, monoName, weight]) => {
      // document.fonts.load() rather than a bare check(). Fonts are fetched
      // lazily, only when something actually paints with them, so check() alone
      // answers "did this page render that font above the fold" and not "is
      // this font available". score-demo/index.html declares Geist Mono on four
      // selectors that all live in the results panel, which is empty until a
      // query runs, so a bare check() reported it missing on a page where it
      // was fine. load() asks the real question: fetch it and tell me if it
      // resolves. It rejects, or resolves to an empty list, if it cannot.
      const probe = async (family) => {
        if (family === null) return null;
        try {
          const faces = await document.fonts.load(`${weight} 16px "${family}"`);
          return faces.length > 0;
        } catch {
          return false;
        }
      };
      return {
        sans: await probe(sansName),
        mono: await probe(monoName),
        // Any face still "unloaded" after fonts.ready means nothing on the page
        // requested it, which is fine; "error" means it was requested and failed.
        errored: [...document.fonts].filter((f) => f.status === 'error').map((f) => f.family),
      };
    },
    [sans, mono, PROBE_WEIGHT],
  );

  const ok =
    (sans === null || result.sans === true) &&
    result.mono === true &&
    result.errored.length === 0 &&
    violations.length === 0 &&
    failed.length === 0;

  if (!ok) failures++;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${page_path}  sans=${result.sans} mono=${result.mono}`);
  if (violations.length) console.log(`      CSP: ${violations.join(' | ')}`);
  if (failed.length) console.log(`      FONT REQ FAILED: ${failed.join(' | ')}`);
  if (result.errored.length) console.log(`      FACE ERROR: ${result.errored.join(', ')}`);

  await page.close();
}

await browser.close();
server.close();

console.log(`\n${failures === 0 ? 'ALL PASS' : failures + ' PAGE(S) FAILED'}`);
process.exit(failures === 0 ? 0 : 1);
