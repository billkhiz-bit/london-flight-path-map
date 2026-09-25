/**
 * Render each talks/*.html write-up (not index.html) to the PDF beside it.
 *
 *   node scripts/render_talks_pdfs.mjs
 *
 * TAGGED, since 2026-09-25: the first renders (21 Sep) came from a scratchpad
 * script with no `tagged` flag, so both PDFs shipped with no structure tree,
 * reading order or language - the only format /talks/ offered a screen-reader
 * user. The .html sources are published beside them now too (talks-deploy).
 *
 * Writes to <name>.NEW.pdf and then renames over the old file, because a PDF
 * open in a viewer on Windows is locked and a direct overwrite fails half-way.
 */
import { chromium } from '@playwright/test';
import { readdir, rename } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const DIR = resolve('talks');
const sources = (await readdir(DIR)).filter((f) => f.endsWith('.html') && f !== 'index.html');
if (!sources.length) {
  console.error('No write-ups found in talks/ - run from the repo root.');
  process.exit(1);
}

const browser = await chromium.launch();
try {
  for (const f of sources) {
    const page = await browser.newPage();
    await page.goto(pathToFileURL(join(DIR, f)).href, { waitUntil: 'load' });
    await page.emulateMedia({ media: 'print' });
    const out = join(DIR, f.replace(/\.html$/, '.pdf'));
    const tmp = out.replace(/\.pdf$/, '.NEW.pdf');
    await page.pdf({ path: tmp, format: 'A4', printBackground: true, preferCSSPageSize: true, tagged: true, outline: true });
    await page.close();
    try {
      await rename(tmp, out);
    } catch (e) {
      console.error(`Could not replace ${out} - close it in any PDF viewer and re-run. (${e.code})`);
      process.exitCode = 1;
      continue;
    }
    console.log('wrote', out);
  }
} finally {
  await browser.close();
}
