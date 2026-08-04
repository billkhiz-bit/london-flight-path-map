// Drives the LIVE site through a list of postcodes and prints what the sidebar
// actually renders.
//
// KEEP THIS. It was written as a throwaway demo aid for Build Night (30 Jul)
// and its header said to delete it once the demo was done — but on 2026-08-03
// it was the thing that found the site and /v1/score publishing different
// headline scores for the same postcode, and it remains **the only harness
// that compares the two surfaces against each other**.
//
// Why nothing else covers this: the pytest suites only ever read the Lambda,
// and the Playwright e2e suite asserts the site against itself. Each half is
// internally consistent while disagreeing with the other — the exact shape of
// both the raster divergence and the three-month flight-path divergence.
//
// Not in /preflight deliberately: it hits the live site and reads numbers for a
// human to compare, rather than asserting a threshold. Run it by hand after any
// scoring change, and after any DATA LOAD — a load needs no deploy and can
// still change what users see, which is how the raster gap opened unnoticed.
//
//   node tests/rehearse.mjs
//   POSTCODES="E6 5QS,SE18 6NQ,TW6 1AP" node tests/rehearse.mjs
import { chromium } from '@playwright/test';

const BASE = process.env.SMOKE_BASE || 'https://d1oe4ftwutjpf.cloudfront.net';
const POSTCODES = process.env.POSTCODES
  ? process.env.POSTCODES.split(',')
  : ['E1 8BL', 'TW3 1AA', 'TW9 1AA', 'SE22 8AA', 'BR1 1AA'];

const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto(`${BASE}/index.html`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('#app', { state: 'visible', timeout: 30000 });

for (const pc of POSTCODES) {
  const input = page.locator('#search-input');
  await input.fill('');
  await input.fill(pc);
  await input.press('Enter');

  // Wait for the title to settle away from the transient SEARCHING... state.
  let title = '';
  for (let i = 0; i < 40; i++) {
    await page.waitForTimeout(250);
    title = (await page.locator('#sidebar-title').textContent()) || '';
    if (title.trim() && !/SEARCHING/i.test(title)) break;
  }

  const verdict = await page
    .locator('.summary-verdict')
    .first()
    .textContent()
    .catch(() => null);

  const rows = await page.evaluate(() => {
    const out = [];
    document.querySelectorAll('.score-row').forEach((r) => {
      const label = r.querySelector('.score-row-label')?.textContent?.trim();
      const value = r.querySelector('.score-row-value')?.textContent?.trim();
      if (label && value) out.push(`${label}: ${value}`);
    });
    return out;
  });

  console.log(`\n=== ${pc} ===`);
  console.log(`title:   ${title.trim()}`);
  console.log(`verdict: ${(verdict || '(none)').replace(/\s+/g, ' ').trim().slice(0, 160)}`);
  rows.slice(0, 10).forEach((r) => console.log(`  ${r}`));
}

await browser.close();
