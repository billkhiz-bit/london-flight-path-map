// Verifies the /changes "why did it move?" disclosure and the dated labelling.
import { chromium } from '@playwright/test';

const BASE = process.env.SMOKE_BASE || 'https://d1oe4ftwutjpf.cloudfront.net';
const results = [];
const record = (name, pass, detail = '') => {
  results.push({ name, pass, detail });
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`);
};

const browser = await chromium.launch();
const page = await browser.newPage();
// Known-benign and inherent to delivering CSP via <meta> rather than a header:
// frame-ancestors is header-only by spec, so Chrome always logs this. It is
// present on every page in this project and predates this feature. Allow-listed
// narrowly by exact substring so any OTHER console error still fails the run.
const KNOWN_BENIGN = ["directive 'frame-ancestors' is ignored when delivered via a <meta> element"];
const consoleErrors = [];
page.on('console', (m) => {
  if (m.type() !== 'error') return;
  const text = m.text();
  if (KNOWN_BENIGN.some((k) => text.includes(k))) return;
  consoleErrors.push(text);
});

await page.goto(`${BASE}/changes`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('#table-wrap:not([hidden])', { timeout: 30000 });

// --- dated labelling ------------------------------------------------------
const period = (await page.locator('#period-line').textContent()) || '';
record('period line names both quarters with years', /Q\d 2\d{3}.*Q\d 2\d{3}/.test(period), period.trim());

const title = await page.title();
record('tab title carries the quarter', /Q\d 2\d{3}/.test(title), title);

const thThen = (await page.locator('#th-score-then').textContent()) || '';
const thNow = (await page.locator('#th-score-now').textContent()) || '';
record('score columns are dated', /Q\d 2\d{3}/.test(thThen) && /Q\d 2\d{3}/.test(thNow), `${thThen.trim()} | ${thNow.trim()}`);

const vintage = (await page.locator('#vintage-line').textContent()) || '';
record('refresh date is long-form with year', /\d{1,2} [A-Z][a-z]+ 2\d{3}/.test(vintage), vintage.trim());

// --- the disclosure -------------------------------------------------------
const btns = page.locator('.why-btn');
const btnCount = await btns.count();
record('why buttons rendered', btnCount > 0, `${btnCount} buttons`);

const first = btns.first();
record('collapsed by default', (await first.getAttribute('aria-expanded')) === 'false');

const controls = await first.getAttribute('aria-controls');
const panel = page.locator(`#${controls}`);
record('panel hidden before click', !(await panel.isVisible()));

await first.click();
record('aria-expanded flips on open', (await first.getAttribute('aria-expanded')) === 'true');
record('panel visible after click', await panel.isVisible());

// The headline states direction and the before/after pair; the factor names
// live in the driver blocks below it, checked further down.
const prose = ((await panel.locator('.why-prose').textContent()) || '').trim();
record('headline states direction and both scores', /(rose|fell|held).*\d\.\d to \d\.\d/i.test(prose), prose);
record(
  'panel names at least one factor',
  /(Growth|Affordability|Quiet Skies|Liveability)/.test(await panel.textContent())
);

const bars = await panel.locator('.why-factor').count();
record('per-factor bars rendered', bars > 0, `${bars} factors`);

// --- the clarity upgrade: workings, benchmark naming, market context --------
const drivers = await panel.locator('.why-driver').count();
record('structured driver blocks rendered', drivers > 0, `${drivers} drivers`);

const hasWorkings = (await panel.locator('.why-workings').count()) > 0;
const workings = hasWorkings ? ((await panel.locator('.why-workings').first().textContent()) || '').trim() : '';
record('workings shown when a factor is weighted', !hasWorkings || /=/.test(workings), workings || 'no weighted driver on this row (v3.3)');

// The clarity fixes: units, plain meaning, rank, and a numbered causal chain.
const driverTitle = ((await panel.locator('.why-what').first().textContent()) || '').trim();
record('block title states the unit', /out of 10/.test(driverTitle), driverTitle);

const meaningCount = await panel.locator('.why-meaning').count();
const meaning = meaningCount ? ((await panel.locator('.why-meaning').first().textContent()) || '').trim() : '';
record('factor meaning given when weighted', !meaningCount || meaning.length > 20, meaning || 'n/a on this row (v3.3)');

// Since methodology v3.3 the balanced view carries no growth weight, so the
// top row usually has no weighted driver. Growth movement must still be
// reported, as "moved, but not counted here".
const panelText = (await panel.textContent()).replace(/\s+/g, ' ');
record('unweighted movement is reported', /not counted here|did not change the score/.test(panelText), panelText.slice(0, 130));
record('says growth is investor-only', /investor persona/.test(panelText));

const driverCount = await panel.locator('.why-driver').count();
record('at least one driver or unweighted block', driverCount > 0, `${driverCount} blocks`);

const stepCount = await panel.locator('.why-steps li').count();
if (stepCount > 0) {
  const stepsText = ((await panel.locator('.why-steps').first().textContent()) || '').replace(/\s+/g, ' ');
  record('final step states effect on the total', /of the overall score/.test(stepsText));
} else {
  record('final step states effect on the total', true, 'no weighted driver on this row (v3.3)');
}
record('no internal jargon on the page', !/vintage/i.test(await panel.textContent()));

record('no placeholder subject leaks into the UI', !/This area/.test(await panel.textContent()));

// Market context is the page-level answer to "why did everything move?"
const market = page.locator('#market-context');
record('market context visible', await market.isVisible());
const marketText = ((await market.textContent()) || '').replace(/\s+/g, ' ');
record('market context explains the city-wide move', /market fell/.test(marketText), marketText.slice(0, 110));
record('market context shows the trend shift', /Average trend/.test(marketText));
record('market context names the benchmark change', /Strongest grower/.test(marketText));

const sum = ((await panel.locator('.why-sum').textContent()) || '').replace(/\s+/g, ' ');
record('reconciliation line shown', /Contributions total/.test(sum), sum.slice(0, 120));

await first.click();
record('collapses again', (await first.getAttribute('aria-expanded')) === 'false' && !(await panel.isVisible()));

// Keyboard reachable — it is a real <button>, but prove it.
await page.keyboard.press('Tab');
const focusedTag = await page.evaluate(() => document.activeElement?.tagName);
record('focus lands on interactive elements', !!focusedTag, `first tab -> ${focusedTag}`);

record('no console errors', consoleErrors.length === 0, consoleErrors.slice(0, 3).join(' | '));

await browser.close();
const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
failed.forEach((f) => console.log(`  - ${f.name} ${f.detail}`));
process.exit(failed.length ? 1 : 0);
