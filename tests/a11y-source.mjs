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
    // WAIT FOR SWAGGER TO HAVE PAINTED, added 2026-08-23.
    //
    // Without this the scan raced the spec fetch and usually won in the
    // useless direction: it ran before Swagger had inserted anything, found a
    // near-empty page, and reported OK. This page was effectively unaudited,
    // and the one time it did red - a CRITICAL `select-name` on the server
    // <select> - it looked like flake because three clean re-runs followed.
    //
    // `.opblock` is an INDEPENDENT render signal, deliberately not "every
    // select has an aria-label". Waiting on the thing the fix does would be an
    // expectation read from the code under test, and this gate could then
    // never fail on it.
    renderedWhen: '#swagger-ui .opblock',
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

// TWO VIEWPORTS, not one (2026-08-12).
//
// This scanned 1440x900 only, so nothing inside `@media (max-width:900px)` had
// ever been audited. That is not a hypothetical gap: the mobile legend pill
// paints near-black and its group headings carry an INLINE
// `style="color: var(--dark)"`, giving 1.19:1 - invisible on every phone, and
// live for as long as the layer legends have existed. A desktop-only scan
// reports the page clean because those rules never apply.
//
// 390x844 is a current iPhone; 1440x900 is the desktop the audit already used.
const VIEWPORTS = [
  { label: 'desktop', width: 1440, height: 900 },
  { label: 'mobile', width: 390, height: 844 },
];

// Moderate-impact rules that MUST fail the build.
//
// The filter below keeps `critical|serious`, which is the right default - but
// axe rates these four moderate, so before today they could not fail this gate
// at any viewport no matter how badly they broke. They are structural: a
// missing <main>, a broken heading order or a role applied to the wrong element
// is what a screen-reader user navigates BY.
const FAIL_MODERATE = new Set([
  'heading-order',
  'landmark-one-main',
  'region',
  'aria-allowed-role',
]);

function failing(results) {
  return results.violations.filter(
    (v) => v.impact === 'critical' || v.impact === 'serious' || FAIL_MODERATE.has(v.id)
  );
}

const browser = await chromium.launch();

let failed = 0;
for (const viewport of VIEWPORTS) {
  // axe-core/playwright rejects the implicit context browser.newPage() creates.
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
  });
  const page = await context.newPage();
  console.log(`\n--- ${viewport.label} (${viewport.width}x${viewport.height}) ---`);
  for (const { path, name, waitFor, renderedWhen, disableRules } of PAGES) {
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
    if (renderedWhen) {
      // NOT REACHING THE STATE IS A FAILURE, never a quiet pass. A scan of a
      // page that never rendered is a scan of nothing, and reporting it as OK
      // is exactly how this page went unaudited.
      try {
        await page.waitForSelector(renderedWhen, { state: 'visible', timeout: 30000 });
      } catch {
        console.log(
          `${path.padEnd(28)} FAIL ${name} — never rendered (${renderedWhen}), ` +
            'so nothing was scanned'
        );
        failed++;
        continue;
      }
    }
    let builder = new AxeBuilder({ page }).withTags([
      'wcag2a',
      'wcag2aa',
      'wcag21a',
      'wcag21aa',
    ]);
    if (disableRules) builder = builder.disableRules(disableRules);
    const results = await builder.analyze();
    violations = failing(results);
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

  // THE POST-INTERACTION STATE, which had never been scanned at all.
  //
  // Every scan above runs on the landing state. But `updateSidebar()` injects
  // roughly 400 lines - score bars, the tooltip, metric cards, rating badges,
  // the EPC/crime/sold blocks - and that is the bulk of what a user actually
  // reads. A gate that only ever sees the empty shell is inspecting one
  // keystroke short of the product, which is the same criticism this file
  // already makes of scanning before the locator renders.
  try {
    await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('#app', { state: 'visible', timeout: 30000 });
    await page.evaluate(() => {
      const el = document.querySelector('.borough-list-item, .rank-table tbody tr');
      if (el) el.click();
    });
    await page.waitForTimeout(1200);
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    const v = failing(results);
    if (v.length) failed++;
    console.log(
      `${'/ (borough selected)'.padEnd(28)} ${v.length ? 'FAIL' : 'OK  '} rendered detail panel` +
        (v.length ? ` — ${v.length} blocking` : '')
    );
    for (const item of v) {
      console.log(`    [${item.impact.toUpperCase()}] ${item.id}: ${item.help}`);
      for (const node of item.nodes.slice(0, 3)) {
        console.log(`      - ${node.target.join(' > ')}`);
      }
    }
  } catch (e) {
    console.log(`${'/ (borough selected)'.padEnd(28)} ERROR ${e.message.split('\n')[0]}`);
    failed++;
  }

  // THE COLLAPSED LEGEND, which axe had never been able to see.
  //
  // Audit finding I7. The comment by VIEWPORTS above already described this
  // defect - and the mobile viewport it added still could not catch it,
  // because on a phone the legend ships `aria-expanded="false"` and
  // `.legend-toggle[aria-expanded='false'] ~ *` hides every row. axe does not
  // evaluate hidden elements, so the scan came back clean over markup no
  // check had ever looked at.
  //
  // Measured the day this was added: three group headings rendered
  // var(--dark) #141414 on the near-black pill at 1.00:1 - the SAME COLOUR as
  // their background, invisible on every phone since the layer legends
  // shipped. Adding a viewport is not the same as reaching the state.
  //
  // The layer groups are display:none until their layer paints, so they are
  // revealed here too; a legend section only reachable with live data is
  // still a legend section a user reads.
  try {
    await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('#app', { state: 'visible', timeout: 30000 });
    const opened = await page.evaluate(() => {
      const toggle = document.getElementById('legend-toggle');
      if (toggle && toggle.getAttribute('aria-expanded') === 'false') toggle.click();
      let shown = 0;
      let rows = 0;
      for (const id of ['legend-road-group', 'legend-flood-group', 'legend-aq-group']) {
        const group = document.getElementById(id);
        if (group) {
          group.style.display = 'block';
          shown++;
          // AND THE BAND ROWS INSIDE THEM, added 2026-08-23 alongside the
          // change that started hiding a row whose band painted nothing.
          //
          // Without this the scan silently narrows the day that ships. The
          // EXCELLENT air-quality swatch is hidden in all eleven cities we
          // cover - every one is urban and none clears the WHO PM2.5
          // guideline - so axe would never evaluate it, and it would first
          // reach a user on the day coverage takes in a rural borough, never
          // having had its contrast measured. That is how three legend
          // headings shipped at 1.00:1, literally the same colour as their own
          // background, until this file learned to open the collapsed legend.
          //
          // Same principle as the note above: adding a viewport is not the
          // same as reaching a state, and an element only reachable with data
          // we do not hold yet is still an element a user will read.
          for (const row of group.querySelectorAll('[data-band]')) {
            row.style.display = 'flex';
            rows++;
          }
        }
      }
      const title = document.getElementById('legend-noise-title');
      // Report what the harness actually REACHED. A scan of a legend that
      // never opened must not be able to pass as a scan of an open one -
      // that is precisely the failure being fixed here.
      return { shown, rows, titleVisible: !!(title && title.offsetParent !== null) };
    });
    await page.waitForTimeout(300);
    // The row floor is 10 because that is what the markup declares: 3 road, 3
    // flood, 4 air quality. Any count in an assertion is scheduled staleness,
    // so this one fails LOW only - adding a band raises the count and needs no
    // edit here, while a selector that stops matching drops it and does.
    if (!opened.titleVisible || opened.shown < 3 || opened.rows < 10) {
      console.log(
        `${'/ (legend expanded)'.padEnd(28)} FAIL could not reach the legend ` +
          `(groups shown ${opened.shown}/3, band rows revealed ${opened.rows}, ` +
          `heading visible ${opened.titleVisible})`
      );
      failed++;
    } else {
      const results = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze();
      const v = failing(results);
      if (v.length) failed++;
      console.log(
        `${'/ (legend expanded)'.padEnd(28)} ${v.length ? 'FAIL' : 'OK  '} all four layer legends` +
          (v.length ? ` — ${v.length} blocking` : '')
      );
      for (const item of v) {
        console.log(`    [${item.impact.toUpperCase()}] ${item.id}: ${item.help}`);
        for (const node of item.nodes.slice(0, 3)) {
          console.log(`      - ${node.target.join(' > ')}`);
        }
      }
    }
  } catch (e) {
    console.log(`${'/ (legend expanded)'.padEnd(28)} ERROR ${e.message.split('\n')[0]}`);
    failed++;
  }

  await context.close();
}

await browser.close();
server.close();
console.log(
  `\nRESULT: ${failed === 0 ? 'PASS' : 'FAIL'} ` +
    `(${PAGES.length} pages x ${VIEWPORTS.length} viewports, plus the post-selection and expanded-legend states)`
);
process.exit(failed === 0 ? 0 : 1);
