// The San Francisco Bay Area on the live map: drawn, clicked, ranked and searched, with NO score.
//
// WHY THIS EXISTS. Release 1 (2026-10-05, Bill's ruling) puts the Bay Area on
// the map with the /bay-area/ page's FACTS and no number, because every UK
// quiet estimate is fitted against DEFRA and the Bay Area has no yardstick. It
// is the first city whose records are not scores, so every place that prints
// a score is a place it could print "undefined/10", and every search route that
// assumes New York's ZIP table could swallow a Bay Area ZIP.
//
// WHAT IT ASSERTS, at desktop and phone widths, every off-site request aborted
// and postcodes.io answering 404 (so a name search has nowhere else to go):
//   1. The Bay Area chip draws its 50 cities, three airports and the routes.
//   2. A city opens a facts card ON SCREEN with the page's own text and no
//      score anywhere in it.
//   3. The ranking is the noise-map order, with no score column.
//   4. A Bay Area ZIP typed from London lands on that city's card, with the ZIP.
//   5. A Bay Area city NAME typed from London does too.
//   6. A ZIP in no drawn city says so, on screen.
//   7. A ZIP in neither table names both places Sky Score covers.
//   8. A ?city=bayarea link ends with no inset, not England's arriving late.
//   9. No page errors.
//
//   node tests/bayarea-map.mjs

import { chromium } from '@playwright/test';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const PORT = 8955;
const TYPES = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.mjs': 'application/javascript',
  '.json': 'application/json',
  '.css': 'text/css',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
  '.png': 'image/png',
  '.webmanifest': 'application/manifest+json',
};
const server = createServer(async (req, res) => {
  let p = decodeURIComponent(req.url.split('?')[0]);
  if (p === '/') p = '/index.html';
  if (!extname(p)) p = p.replace(/\/$/, '') + '/index.html';
  try {
    const buf = await readFile(join(ROOT, p));
    res.writeHead(200, { 'Content-Type': TYPES[extname(p)] || 'application/octet-stream' });
    res.end(buf);
  } catch {
    res.writeHead(404);
    res.end('not found');
  }
});
await new Promise((r) => server.listen(PORT, '127.0.0.1', r));
const BASE = `http://127.0.0.1:${PORT}/`;

const failures = [];
let checks = 0;
const ok = (cond, label, detail = '') => {
  checks++;
  console.log(`  ${cond ? 'ok  ' : 'FAIL'} ${label}${cond || !detail ? '' : `: ${detail}`}`);
  if (!cond) failures.push(label + (detail ? `: ${detail}` : ''));
};

// The panel as a sighted visitor sees it: text only from a panel with a box on
// screen, and the first paragraph hit-tested (an element that is not rendered
// still returns its text through innerText; tests/outside-coverage.mjs records
// what assuming otherwise cost).
const panel = (page) =>
  page.evaluate(() => {
    const content = document.getElementById('sidebar-content');
    const box = content.getBoundingClientRect();
    const first = content.querySelector('p');
    const r = first?.getClientRects()[0];
    const top = r ? document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2) : null;
    return {
      title: document.getElementById('sidebar-title').textContent.trim(),
      text: box.width && box.height ? content.innerText.replace(/\s+/g, ' ') : '',
      onScreen: !!top && (top === first || first.contains(top)),
    };
  });

const browser = await chromium.launch();
for (const vp of [
  { width: 1440, height: 900, label: 'desktop' },
  { width: 390, height: 844, label: 'phone' },
]) {
  const ctx = await browser.newContext({ viewport: vp, isMobile: vp.width < 900, hasTouch: vp.width < 900 });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (route) =>
    /api\.postcodes\.io/.test(route.request().url())
      ? route.fulfill({ status: 404, contentType: 'application/json', body: '{"status":404,"error":"not found"}' })
      : route.abort()
  );
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof switchCity === 'function', { timeout: 20000 });
  const L = vp.label.padEnd(8);

  // 1. Drawn.
  await page.evaluate(() => switchCity('bayarea'));
  await page.waitForFunction(() => document.querySelectorAll('path.borough').length >= 50, null, { timeout: 20000 }).catch(() => {});
  const drawn = await page.evaluate(() => ({
    outlines: document.querySelectorAll('path.borough').length,
    airports: document.querySelectorAll('.layer-airports circle').length,
    routes: document.querySelectorAll('.layer-paths path').length,
  }));
  ok(drawn.outlines === 50 && drawn.airports === 3 && drawn.routes >= 40, `${L} the Bay Area draws 50 cities, 3 airports and its routes`, JSON.stringify(drawn));

  // 2. A city's facts, on screen, with no score.
  await page.evaluate(() => selectBoroughByName('San Bruno'));
  await page.waitForTimeout(300);
  const sb = await panel(page);
  ok(
    sb.title === 'SAN BRUNO' && sb.onScreen && /Not scored/.test(sb.text) && /94% of the city/.test(sb.text) && /SFO 10L/.test(sb.text),
    `${L} San Bruno opens its facts card on screen, in the page's own words`,
    `${sb.title} / on screen ${sb.onScreen} / ${sb.text.slice(0, 140)}`
  );
  ok(!/\/10|undefined|NaN|null/.test(sb.text), `${L} the facts card prints no score and no placeholder`, sb.text.slice(0, 200));

  // 3. The ranking: noise-map order, no score column.
  const rank = await page.evaluate(() => {
    renderBoroughRanking();
    const head = [...document.querySelectorAll('#borough-ranking thead th')].map((t) => t.textContent.trim());
    const first = [...document.querySelectorAll('#borough-ranking tbody tr')].map((tr) => tr.dataset.rankName);
    return { head, first: first.slice(0, 3), n: first.length, text: document.getElementById('borough-ranking').innerText };
  });
  ok(
    rank.n === 50 && rank.head.includes('On the noise map') && !rank.head.some((h) => /score/i.test(h)) && /Not scored/.test(rank.text),
    `${L} the ranking lists 50 cities by noise-map share, with no score column`,
    JSON.stringify({ head: rank.head, n: rank.n })
  );
  ok(rank.first[0] === 'Colma', `${L} the ranking starts where the Bay Area page does (Colma, 100%)`, rank.first.join(', '));

  // 4. A Bay Area ZIP from London.
  await page.evaluate(() => switchCity('london'));
  await page.waitForFunction(() => document.querySelectorAll('path.borough').length === 33, null, { timeout: 20000 });
  await page.evaluate(() => triggerSearch('94301'));
  await page.waitForFunction(() => /PALO ALTO/i.test(document.getElementById('sidebar-title').textContent), null, { timeout: 20000 }).catch(() => {});
  const zip = await panel(page);
  ok(/PALO ALTO/i.test(zip.title) && zip.onScreen && /ZIP 94301[\s\S]*In Palo Alto\./i.test(zip.text), `${L} ZIP 94301 typed on London's map opens Palo Alto with its ZIP line`, `${zip.title} / ${zip.text.slice(0, 160)}`);

  // 4a. The ZIP tier: its own AREA's facts and outline, then its city's (layer 1, 2026-10-05).
  await page.evaluate(() => switchCity('london'));
  await page.waitForFunction(() => document.querySelectorAll('path.borough').length === 33, null, { timeout: 20000 });
  await page.evaluate(() => triggerSearch('94066'));
  await page.waitForFunction(() => /ZIP 94066/i.test(document.getElementById('sidebar-title').textContent), null, { timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(300);
  const zipTier = await panel(page);
  const zipOutline = await page.evaluate(() => document.querySelectorAll('.tier-outline').length);
  ok(
    zipTier.onScreen && /89% of the ZIP area, from San Francisco International/.test(zipTier.text) && /94% of the city/.test(zipTier.text) && zipOutline === 1,
    `${L} ZIP 94066 shows its own area's facts and outline, then San Bruno's`,
    `outline ${zipOutline} / ${zipTier.text.slice(0, 220)}`
  );

  // 4b. The neighbourhood tier: a name typed on London's map.
  await page.evaluate(() => switchCity('london'));
  await page.waitForFunction(() => document.querySelectorAll('path.borough').length === 33, null, { timeout: 20000 });
  await page.evaluate(() => triggerSearch('Excelsior'));
  await page.waitForFunction(() => /EXCELSIOR/i.test(document.getElementById('sidebar-title').textContent), null, { timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(300);
  const nh = await panel(page);
  const nhOutline = await page.evaluate(() => document.querySelectorAll('.tier-outline').length);
  ok(
    /EXCELSIOR/i.test(nh.title) && nh.onScreen && /A neighbourhood of San Francisco/.test(nh.text) && /60% of the neighbourhood/.test(nh.text) && nhOutline === 1,
    `${L} "Excelsior" opens a San Francisco neighbourhood card with its own facts and outline`,
    `${nh.title} / outline ${nhOutline} / ${nh.text.slice(0, 160)}`
  );

  // 4c. San Francisco's card names its neighbourhoods; the ranking toggles to them.
  await page.evaluate(() => selectBoroughByName('San Francisco'));
  await page.waitForFunction(() => document.querySelectorAll('#sidebar-content [data-nhood]').length > 0, null, { timeout: 15000 }).catch(() => {});
  const listed = await page.evaluate(() => ({
    n: document.querySelectorAll('#sidebar-content [data-nhood]').length,
    outline: document.querySelectorAll('.tier-outline').length,
  }));
  ok(listed.n === 41 && listed.outline === 0, `${L} San Francisco's card lists its 41 neighbourhoods, and drops the last outline`, JSON.stringify(listed));
  const nhRank = await page.evaluate(async () => {
    renderBoroughRanking();
    document.getElementById('bay-ranking-toggle').click();
    for (let i = 0; i < 50 && !document.querySelector('#borough-ranking tr[data-rank-action="neighbourhood"]'); i++) await new Promise((r) => setTimeout(r, 100));
    const rows = [...document.querySelectorAll('#borough-ranking tbody tr')].map((tr) => tr.dataset.rankName);
    document.getElementById('bay-ranking-toggle').click(); // back to the cities, as the next checks expect
    return { n: rows.length, first: rows[0] };
  });
  ok(nhRank.n === 41 && nhRank.first === 'Visitacion Valley', `${L} the ranking toggles to San Francisco's 41 neighbourhoods, noise-map order`, JSON.stringify(nhRank));

  // 4d. Suggestions as you type, which the UK lookup could not give: on the Bay
  // Area's map a neighbourhood, and its cities labelled as cities.
  const suggest = async (text) => {
    await page.fill('#search-input', '');
    await page.fill('#search-input', text);
    await page.waitForFunction(() => document.querySelectorAll('#autocomplete-dropdown .autocomplete-item').length > 0, null, { timeout: 8000 }).catch(() => {});
    return page.evaluate(() => [...document.querySelectorAll('#autocomplete-dropdown .autocomplete-item')].map((i) => `${i.dataset.type}:${i.dataset.value}:${i.querySelector('.ac-area')?.textContent || ''}`));
  };
  const nhSuggest = await suggest('Exce');
  ok(nhSuggest.includes('nhood:Excelsior:San Francisco neighbourhood'), `${L} typing "Exce" on the Bay Area suggests the Excelsior neighbourhood`, nhSuggest.join(' | '));
  const citySuggest = await suggest('San B');
  ok(citySuggest.includes('borough:San Bruno:City'), `${L} the Bay Area's cities are suggested as cities, not boroughs`, citySuggest.join(' | '));

  // 4e. A ZIP suggested from London's map, chosen with a click.
  await page.evaluate(() => switchCity('london'));
  await page.waitForFunction(() => document.querySelectorAll('path.borough').length === 33, null, { timeout: 20000 });
  const zipSuggest = await suggest('9406');
  ok(zipSuggest.includes('zip:94066:ZIP · San Bruno'), `${L} typing "9406" on London's map suggests ZIP 94066`, zipSuggest.join(' | '));
  await page.locator('#autocomplete-dropdown .autocomplete-item[data-value="94066"]').click();
  await page.waitForFunction(() => /ZIP 94066/i.test(document.getElementById('sidebar-title').textContent), null, { timeout: 20000 }).catch(() => {});
  ok(/ZIP 94066/i.test((await panel(page)).title), `${L} choosing the suggested ZIP opens it`, (await panel(page)).title);
  await page.evaluate(() => triggerSearch('94128'));
  await page.waitForFunction(() => /ZIP 94128/i.test(document.getElementById('sidebar-title').textContent), null, { timeout: 20000 }).catch(() => {});
  ok(/inside the ZIP area/.test((await panel(page)).text), `${L} a ZIP holding an airport says it is inside the ZIP area, not "the city"`, (await panel(page)).text.slice(0, 260));

  // 5. A Bay Area city name from London (postcodes.io answers 404, so only the Bay Area can find it).
  await page.evaluate(() => switchCity('london'));
  await page.waitForFunction(() => document.querySelectorAll('path.borough').length === 33, null, { timeout: 20000 });
  await page.evaluate(() => triggerSearch('Livermore'));
  await page.waitForFunction(() => /LIVERMORE/i.test(document.getElementById('sidebar-title').textContent), null, { timeout: 20000 }).catch(() => {});
  const named = await panel(page);
  ok(/LIVERMORE/i.test(named.title) && named.onScreen && /36% of the city, from Livermore Municipal/.test(named.text), `${L} "Livermore" typed on London's map opens Livermore's facts`, `${named.title} / ${named.text.slice(0, 160)}`);

  // 6. A ZIP in no drawn city.
  await page.evaluate(() => triggerSearch('94305'));
  await page.waitForFunction(() => /ZIP 94305/i.test(document.getElementById('sidebar-title').textContent), null, { timeout: 20000 }).catch(() => {});
  const cdp = await panel(page);
  ok(/ZIP 94305/i.test(cdp.title) && cdp.onScreen && /Santa Clara County/.test(cdp.text) && /Stanford/.test(cdp.text), `${L} a ZIP in no drawn city says so, on screen, and names where it is`, `${cdp.title} / ${cdp.text.slice(0, 160)}`);

  // 7. A ZIP in neither table.
  await page.evaluate(() => triggerSearch('90210'));
  await page.waitForFunction(() => document.getElementById('sidebar-title').textContent.trim() === 'NOT FOUND', null, { timeout: 20000 }).catch(() => {});
  const none = await panel(page);
  ok(none.title === 'NOT FOUND' && none.onScreen && /New York City/.test(none.text) && /Bay Area/.test(none.text), `${L} a ZIP in neither table names both places covered`, none.text.slice(0, 160));

  // 8. A ?city=bayarea link must not end with England's inset on screen. London's
  // silhouette is fetched at boot and held back here, so it lands AFTER the
  // switch, which is how the live page came to show it (2026-10-05).
  await page.route('**/data/uk-locator.json', async (route) => {
    await new Promise((r) => setTimeout(r, 1500));
    await route.continue();
  });
  await page.goto(`${BASE}?city=bayarea`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.querySelectorAll('path.borough').length >= 50, null, { timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(2500);
  const inset = await page.evaluate(() => {
    const box = document.getElementById('locator');
    const shown = !!box && !box.hidden && getComputedStyle(box).display !== 'none';
    return { shown, region: document.querySelector('.locator-region')?.textContent || '', bay: !!document.querySelector('#locator-cities [data-city="bayarea"]') };
  });
  // The inset is hidden at 900px and below by design (no room beside the map). Above
  // that it must show, and be the US's with the Bay Area marked - never England's
  // arriving after the switch, and never absent, which is how it shipped on 5 Oct.
  const insetWanted = vp.width > 900;
  ok(insetWanted ? inset.shown && inset.region === 'Contiguous United States' && inset.bay : !inset.shown, `${L} a ?city=bayarea link shows ${insetWanted ? 'the US inset with the Bay Area marked' : 'no inset, as at every phone width'}`, JSON.stringify(inset));
  const hint = await page.evaluate(() => {
    const h = document.getElementById('first-hint');
    return !h || getComputedStyle(h).display === 'none' ? '' : h.textContent.replace(/\s+/g, ' ').trim();
  });
  ok(hint === '', `${L} a ?city=bayarea link shows no UK "type a postcode" hint`, hint);

  ok(errors.length === 0, `${L} no page errors`, errors.join(' | '));
  await ctx.close();
}
// 10. A search fired the instant the page's script runs, before the map is built:
// it reached switchCity() with no projection and threw "reading 'center'" (seen
// live, 2026-10-05). It must wait for the map and land.
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (route) => route.abort());
  // init() awaits London's outlines before it builds the projection; held back,
  // the window a slow connection opens is reproduced on a fast one.
  await page.route('**/data/london-boroughs.json', async (route) => {
    await new Promise((r) => setTimeout(r, 2000));
    await route.continue();
  });
  await page.goto(BASE, { waitUntil: 'commit' });
  await page.waitForFunction(() => typeof triggerSearch === 'function', null, { timeout: 20000, polling: 5 });
  await page.evaluate(() => { triggerSearch('94066').catch((e) => { window.__early = String(e); }); });
  await page.waitForFunction(() => /ZIP 94066/i.test(document.getElementById('sidebar-title')?.textContent || '') || window.__early, null, { timeout: 25000 }).catch(() => {});
  const early = await page.evaluate(() => ({ title: document.getElementById('sidebar-title').textContent.trim(), err: window.__early || '' }));
  ok(/ZIP 94066/i.test(early.title) && !early.err && errors.length === 0, 'a ZIP searched before the map is built waits for it and lands', `${early.title} / ${early.err} / ${errors.join(' | ')}`);
  await page.close();
}

await browser.close();
server.close();

const EXPECTED = 2 * 21 + 1;
if (checks < EXPECTED) {
  console.error(`\nFAIL: ran ${checks} checks, expected ${EXPECTED}.`);
  process.exit(1);
}
if (failures.length) {
  console.error(`\nFAIL: ${failures.length} problem(s):`);
  for (const f of failures) console.error('  - ' + f);
  process.exit(1);
}
console.log(`\nThe Bay Area is drawn, searched and ranked with no score: ${checks} checks.`);
