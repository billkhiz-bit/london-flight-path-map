// Does the borough panel's Environment caveat describe the borough in front of
// it? Camden is 3/3 (no caveat), Brooklyn has none of the three (no caveat, no
// crash), and a CONSTRUCTED 2-of-3 borough must NAME the two inputs it has.
//
// The partial case is constructed, and that is deliberate. It used to be
// Middlesbrough, which held air quality and road noise and no flood. The
// 2026-08-30 flood georeferencing fix gave Teesside flood, so Middlesbrough
// became 3/3 and this gate went red on a borough whose data had IMPROVED.
// Measured that day: of 99 borough records, 90 hold all three inputs, 4 hold
// one (Cardiff) and 5 hold none (New York) - NO borough is 2-of-3 any more.
//
// Borrowing a real borough for the partial case therefore left the caveat path
// - the exact code that shipped "undefined only here" - untestable the moment
// coverage completed. The renderer is what this file is for, so the record is
// built rather than found: one field is dropped from a real record, the panel
// is re-rendered, and the field is put back.
//
// WHY THIS FILE EXISTS. On 2026-08-29 every UK borough panel rendered
// "... - undefined only here" beside a correctly-computed Environment score,
// because envCaveat() was handed the SCORED record from matchBorough() while it
// reads the three CONTINUOUS fields, which only borough-extra.json carries. It
// shipped and deployed with all 32 gates green, and the audit found it hours
// later.
//
// NOTHING IN THE SUITE OPENS THE SIDEBAR. borough-score-parity.mjs compares the
// score out of the registry without rendering the panel, so the whole detail
// panel - every string beside every number - was unasserted. This gate renders
// it. Proven red against the pre-fix tree: Camden and Middlesbrough both came
// back with undefined=true.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join } from 'node:path';
import { chromium } from 'playwright';
import { keepPanelOpen } from './panel-fold.mjs';

// Serve the repo root regardless of where this is invoked from.
const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
const PORT = 8941;
const TYPES = {
  '.html': 'text/html', '.js': 'application/javascript', '.mjs': 'application/javascript',
  '.json': 'application/json', '.css': 'text/css', '.png': 'image/png',
  '.svg': 'image/svg+xml', '.webmanifest': 'application/manifest+json', '.woff2': 'font/woff2',
};
const server = createServer(async (req, res) => {
  const url = decodeURIComponent(req.url.split('?')[0]);
  try {
    const buf = await readFile(join(ROOT, url === '/' ? '/index.html' : url));
    res.writeHead(200, { 'content-type': TYPES[extname(url)] || 'application/octet-stream' });
    res.end(buf);
  } catch { res.writeHead(404); res.end('nf'); }
});
await new Promise((r) => server.listen(PORT, r));

const browser = await chromium.launch();
const page = await browser.newPage();
await keepPanelOpen(page);
await page.goto(`http://localhost:${PORT}/index.html`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(3000);

let fail = 0;
// `drop` removes one env field from the borough's borough-extra record before
// rendering, so a coverage level that no longer occurs in the data can still be
// exercised. `mustName` asserts the caveat NAMES what survived, because a
// caveat that fires with the wrong list is the defect this file was written for.
async function check(city, country, borough, expectCaveat, drop = null, mustName = null) {
  await page.evaluate((c) => switchCountry(c), country);
  await page.waitForTimeout(300);
  await page.evaluate((c) => switchCity(c), city);
  await page.waitForTimeout(1500);
  const out = await page.evaluate(([b, cityKey, dropField]) => {
    const d = matchBorough(b);
    if (!d) return { err: 'borough not found' };
    let rec = null, saved, had = false;
    if (dropField) {
      rec = cityOf(cityKey).boroughExtra()[b];
      if (!rec) return { err: 'no borough-extra record to construct from' };
      had = Object.prototype.hasOwnProperty.call(rec, dropField);
      if (!had) return { err: `record has no ${dropField} to drop` };
      saved = rec[dropField];
      delete rec[dropField];
    }
    let text, panel = '';
    try {
      updateSidebar(d);
      // THE CAVEAT SITS IN THE ANSWER CARD'S SCORE since 2026-11-20 (option A: the borough's old score breakdown, where
      // it was a `.score-explain` row, went with the rest of the old "All the detail"). It is drawn only when there is
      // one, so its absence is the right answer for a fully-measured borough.
      //
      // NOT-FOUND IS STILL A FAILURE, NOT A PASS (2026-09-07 audit, I14). An absent caveat proves nothing unless the
      // card drew the score it qualifies, so the five score rows must be there (else three of these cases go green
      // having rendered nothing, as they once did); and the constructed 2-of-3 case below fails if the caveat is not
      // found, so renaming `.ac-env-caveat` cannot switch this gate off silently.
      const card = document.getElementById('ac-score');
      if (card) card.open = true; // so the whole-panel read below sees the card's body too
      const rows = document.querySelectorAll('#ac-score .score-breakdown .score-row').length;
      if (rows !== 5) return { err: `the answer card drew ${rows} score rows, not 5: the caveat cannot be judged` };
      text = document.querySelector('#ac-score .ac-env-caveat')?.textContent.trim() || '';
      // THE WHOLE PANEL, NOT JUST THIS ROW (2026-09-11).
      //
      // updateSidebar() renders the entire sidebar and this gate then threw
      // all of it away but one .score-explain row, so the `undefined` check
      // below - the check this file exists for - only ever saw the
      // Environment sentence. Four sibling interpolations in the same
      // function (data.note, data.property, extra.crime, extra.schoolNote)
      // were unguarded, and 53 of 91 boroughs rendered the literal word
      // `undefined`, including `UNDEFINED` in the rating-high colour under
      // CRIME. It rendered here on every run and nothing looked at it.
      //
      // Rendering a surface is not asserting it. The caveat checks stay
      // scoped to the row; `undefined` is now asked of the whole panel.
      panel = (document.querySelector('#sidebar-content')?.innerText || '').trim();
    } finally {
      // Restore even if rendering threw, so one failing case cannot corrupt
      // the records every later case reads.
      if (rec && had) rec[dropField] = saved;
    }
    return { text, panel };
  }, [borough, city, drop]);
  if (out.err) { console.log(`  ! ${borough}: ${out.err}`); fail++; return; }
  // Asked of the WHOLE panel, not just the environment row - see the note in
  // the evaluate above. `out.text` is a substring of `out.panel`, so testing
  // the panel strictly widens what this catches.
  const hasUndef = /undefined/i.test(out.panel || out.text);
  const hasCaveat = /only here/.test(out.text);
  const named = mustName ? mustName.test(out.text) : true;
  const ok = !hasUndef && hasCaveat === expectCaveat && named;
  if (!ok) fail++;
  const label = borough + (drop ? ` (-${drop})` : '');
  console.log(`  ${ok ? 'ok ' : 'FAIL'} ${label.padEnd(34)} caveat=${hasCaveat} (want ${expectCaveat}) undefined=${hasUndef}${mustName ? ` named=${named}` : ''}`);
  console.log(`       "${out.text.slice(0, 165)}"`);
}

console.log('Environment caveat, rendered:');
await check('london', 'United Kingdom', 'Camden', false);
// Middlesbrough is 3/3 since the 2026-08-30 flood fix, so it must NOT caveat.
await check('teesside', 'United Kingdom', 'Middlesbrough', false);
// ...and the same borough with flood removed must caveat, naming the two it kept.
await check('teesside', 'United Kingdom', 'Middlesbrough', true,
  'floodMediumOrHighPct', /air quality and road noise/i);
await check('nyc', 'United States', 'Brooklyn', false);

console.log(fail ? `\n${fail} FAILED` : '\nall good');
await browser.close();
server.close();
process.exit(fail ? 1 : 0);
