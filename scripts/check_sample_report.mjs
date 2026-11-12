#!/usr/bin/env node
/**
 * Is the public sample street report still TRUE? (audit I-10, 2026-11-12)
 *
 * home/reports/sample-street-report-kew.pdf is linked from /reports/ and pictured on the front page. Its picture and its
 * wording were gated; its FIGURES never were, so every data roll left them stale while preflight stayed green (the CAA
 * roll of 1 Nov; PM2.5 8.6 against 8.5 after the 10 Nov air reload). This checks the sample the way a reader's copy is
 * checked at /reports/street/: it recomputes the REFERENCE printed on it (a hash of the figures it states, the postcode,
 * the AIRAC and the day it was made: js/street_report.mjs reportReference) from today's data and the day printed on it,
 * and recomputes its HEADLINE (answerLead, with today's planes counts, which the reference does not cover).
 *
 * A mismatch: regenerate the sample, then its picture:
 *   node scripts/address_noise_report.mjs --postcode "TW9 3PZ" --place "Kew" --sample --out home/reports/sample-street-report-kew.pdf
 *   python scripts/build_report_still.py --write
 * No network: INCONCLUSIVE (exit 0, which preflight prints as incomplete, never as a pass).
 *
 *   node scripts/check_sample_report.mjs
 */
import { execFileSync } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

import { answerLead } from '../js/answer-lead.mjs';
import { districtOf, planesModel } from '../js/planes.mjs';
import { reportReference } from '../js/street_report.mjs';

const SAMPLE = resolve('home/reports/sample-street-report-kew.pdf');
const POSTCODE = 'TW9 3PZ';
const API = 'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod';
const readJson = async (p) => JSON.parse(await readFile(resolve(p), 'utf8'));
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

// The sample's own text, read with pdfium (as build_report_still.py reads it).
const text = execFileSync('python', ['-c', [
  'import sys, pypdfium2 as p',
  'd = p.PdfDocument(sys.argv[1])',
  "sys.stdout.reconfigure(encoding='utf-8')",
  "print('\\n'.join(d[i].get_textpage().get_text_range() for i in range(len(d))))",
].join('\n'), SAMPLE], { encoding: 'utf8' });
const flat = text.replace(/\s+/g, ' ');
const printedRef = (flat.match(/[Rr]eference ([A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4})/) || [])[1];
const printedDay = flat.match(/Prepared (\d{1,2}) (\w+) (\d{4})/);
if (!printedRef || !printedDay || !MONTHS.includes(printedDay[2])) {
  console.log(`FAIL: the sample states no reference or no "Prepared" day (${printedRef || 'no reference'}): regenerate it`);
  process.exit(1);
}
const made = `${printedDay[3]}-${String(MONTHS.indexOf(printedDay[2]) + 1).padStart(2, '0')}-${printedDay[1].padStart(2, '0')}`;

let env;
try {
  const geo = await (await fetch(`https://api.postcodes.io/postcodes/${encodeURIComponent(POSTCODE)}`, { signal: AbortSignal.timeout(20000) })).json();
  const { latitude, longitude } = geo.result;
  const body = await (await fetch(`${API}/v1/environment?lat=${latitude}&lon=${longitude}`, { signal: AbortSignal.timeout(20000) })).json();
  env = body.environment;
  if (!env) throw new Error('no environment in the answer');
} catch (e) {
  console.log(`INCONCLUSIVE: could not ask today's figures for ${POSTCODE} (${e.message}); the sample was not checked`);
  process.exit(0);
}

const proc = await readJson('data/flight-procedures.json');
const fresh = await reportReference(POSTCODE, made, proc.airac, env);
const planesFile = `data/planes/${districtOf(POSTCODE)}.json`;
const model = existsSync(resolve(planesFile)) ? planesModel(await readJson(planesFile), await readJson('data/planes/airports.json'), POSTCODE) : null;
const steps = (await readJson('data/planes-layer/index.json')).steps || [];
const lead = answerLead(env, POSTCODE, model, steps);

const faults = [];
if (fresh !== printedRef) {
  faults.push(`its reference ${printedRef} is not today's ${fresh} for the day it states (${made}): a figure it states, or the AIRAC (${proc.airac}), has moved`);
}
if (lead && !flat.includes(lead)) faults.push(`its headline is not today's: "${lead}"`);
if (faults.length) {
  console.log(`FAIL: the sample street report is stale: ${faults.join('; ')}. Regenerate it (see this script's header).`);
  process.exit(1);
}
console.log(`ok: the sample's reference ${printedRef} (made ${made}) and its headline match today's figures and AIRAC ${proc.airac}`);
