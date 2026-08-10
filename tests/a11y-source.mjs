/**
 * WCAG 2.1 AA scan of the SOURCE tree, before a deploy.
 *
 * Why this exists
 * ---------------
 * `tests/e2e/accessibility.spec.js` scans `baseURL`, which is CloudFront. It is
 * a good gate and it stays — but it can only ever see DEPLOYED state, so an
 * accessibility regression is uncatchable until it is already in production and
 * in front of users. That is not hypothetical: the locator inset shipped on
 * 2026-08-09 carrying `role="img"` around ten focusable `role="button"` markers,
 * and the only thing that noticed was a red gate the following morning, against
 * live.
 *
 * This is the same move `tests/fonts-selfhosted.mjs` already makes — serve the
 * repo and validate the bytes we are about to ship, rather than the bytes we
 * shipped last time.
 *
 * The two are NOT redundant. This one catches a defect before it deploys; the
 * e2e one catches a bad or partial deploy, and drift between source and origin.
 * Deleting either leaves a real hole.
 *
 * Usage
 * -----
 *     node tests/a11y-source.mjs
 */
import { chromium } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';

const ROOT = process.cwd();
// NOT 8123. preflight.sh binds that to a `python -m http.server` for
// smoke-local, and this stage runs inside the same block — sharing the port
// makes this harness die with EADDRINUSE, which reads as an accessibility
// failure and is not one. 8099/8920-8922 are taken by the other harnesses.
const PORT = 8923;
const TYPES = {
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.mjs': 'text/javascript',
  '.json': 'application/json',
  '.css': 'text/css',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.woff2': 'font/woff2',
  '.webmanifest': 'application/manifest+json',
};

// Mirrors the PAGES list in tests/e2e/accessibility.spec.js. Kept in the same
// order so a diff between the two reads cleanly; if a page is added there and
// not here, this file is scanning less than it claims to.
const PAGES = [
  { path: '/', name: 'consumer app', waitFor: '#app' },
  { path: '/pricing', name: 'pricing' },
  { path: '/privacy', name: 'privacy' },
  { path: '/terms', name: 'terms of use' },
  { path: '/api/', name: 'API landing' },
  { path: '/changes', name: 'what changed this quarter' },
  { path: '/score-demo/', name: 'score demo' },
  {
    path: '/score-demo/api-docs.html',
    name: 'API reference',
    // Swagger UI 5.17.14 renders an operation summary <button> containing the
    // deep-link <button>. Upstream defect, unfixable without patching a
    // vendored bundle the next upgrade would overwrite. Scoped to this ONE rule
    // on this ONE page, exactly as the e2e spec scopes it — lowering the bar
    // globally here would silently un-gate the rule that caught the locator.
    disableRules: ['nested-interactive'],
  },
  { path: '/score-demo/status.html', name: 'status page' },
];

/**
 * Resolve a request path the way the `sky-score-rewrite-index` CloudFront
 * function does, so what is scanned locally is what the origin will serve.
 * An extensionless path tries `<path>.html` first, then `<path>/index.html`.
 */
async function resolve(urlPath) {
  const clean = normalize(decodeURIComponent(urlPath.split('?')[0]));
  const candidates = clean.endsWith('/')
    ? [join(clean, 'index.html')]
    : extname(clean)
      ? [clean]
      : [`${clean}.html`, join(clean, 'index.html')];
  for (const candidate of candidates) {
    const full = join(ROOT, candidate);
    if (!full.startsWith(ROOT)) continue;
    try {
      // Read BEFORE writing any header — see the note in locator-verify.mjs.
      // The other order turns a missing file into ERR_HTTP_HEADERS_SENT, and
      // the harness then exits non-zero for a reason that has nothing to do
      // with accessibility.
      return { body: await readFile(full), ext: extname(full) };
    } catch {
      /* try the next candidate */
    }
  }
  return null;
}

const server = createServer(async (req, res) => {
  const hit = await resolve(req.url);
  if (!hit) {
    res.writeHead(404).end();
    return;
  }
  res.writeHead(200, { 'content-type': TYPES[hit.ext] || 'application/octet-stream' });
  res.end(hit.body);
});
await new Promise((r) => server.listen(PORT, '127.0.0.1', r));

const browser = await chromium.launch();
// axe-core/playwright rejects the implicit context browser.newPage() creates.
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

let failed = 0;
for (const { path, name, waitFor, disableRules } of PAGES) {
  let violations = [];
  let note = '';
  try {
    await page.goto(`http://127.0.0.1:${PORT}${path}`, { waitUntil: 'domcontentloaded' });
    if (waitFor) {
      await page.waitForSelector(waitFor, { state: 'visible', timeout: 30000 });
      // The locator inset and both selector tiers are rendered by script after
      // #app is revealed. Scanning before they exist would report a clean sweep
      // of markup that is not the markup a user meets — the exact shape of
      // "a gate that inspects one keystroke short of the product".
      await page
        .waitForFunction(() => document.querySelectorAll('#locator-cities .cty').length > 0, null, {
          timeout: 20000,
        })
        .catch(() => {
          note = ' (locator never rendered)';
        });
    }
    let builder = new AxeBuilder({ page }).withTags([
      'wcag2a',
      'wcag2aa',
      'wcag21a',
      'wcag21aa',
    ]);
    if (disableRules) builder = builder.disableRules(disableRules);
    const results = await builder.analyze();
    violations = results.violations.filter(
      (v) => v.impact === 'critical' || v.impact === 'serious'
    );
  } catch (e) {
    // A page that cannot be loaded or scanned is a FAILURE, not a skip. A
    // swallowed error here would be a check that cannot go red.
    console.log(`${path.padEnd(28)} ERROR ${e.message.split('\n')[0]}`);
    failed++;
    continue;
  }

  if (violations.length) failed++;
  console.log(
    `${path.padEnd(28)} ${violations.length ? 'FAIL' : 'OK  '} ${name}${note}` +
      (violations.length ? ` — ${violations.length} critical/serious` : '')
  );
  for (const v of violations) {
    console.log(`    [${v.impact.toUpperCase()}] ${v.id}: ${v.help}`);
    for (const node of v.nodes.slice(0, 3)) {
      console.log(`      - ${node.target.join(' > ')}`);
    }
    if (v.nodes.length > 3) console.log(`      ... and ${v.nodes.length - 3} more`);
  }
}

await browser.close();
server.close();
console.log(`\nRESULT: ${failed === 0 ? 'PASS' : 'FAIL'} (${PAGES.length} pages scanned)`);
process.exit(failed === 0 ? 0 : 1);
