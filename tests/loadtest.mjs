// Sky Score /v1/score load harness. No deps (Node 18+ global fetch).
// Promoted into the repo after the 2026-07-24 stress-test day (used for the
// audit load test, the 118k soak, and the post-fix verification probes).
//
// Env:
//   PHASE=single|batch
//   single: WORKERS, DURATION_S, PAUSE_MS (per-worker pacing; 0 = flat out)
//   batch:  COUNT, CONC (100-query batches)
//   KEYFILE  path to a file holding the API key (never pass keys inline)
//   CSVFILE  optional: persist EVERY request as `timestampMs,status,latencyMs`
//            — added after the 118k soak retained only aggregates and the
//            per-request question came up. With this set, "all results" is
//            a spreadsheet import away.
//
// Run against temporary keys on temporary usage plans (create + delete via
// aws apigateway; see AUDIT_REPORT.md 2026-07-24 addenda for the pattern).
// Never soak the public demo key — it shares the free-tier monthly quota.
// GOTCHA: a freshly-created key 403s for ~20s while APIGW propagates —
// probe with curl until a 200 comes back BEFORE starting a capture, or the
// CSV opens with a block of Forbidden rows.
import { appendFileSync, readFileSync } from 'node:fs';

const API = 'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod';
const KEY = readFileSync(process.env.KEYFILE, 'utf8').trim();
const PHASE = process.env.PHASE || 'single';
const CSVFILE = process.env.CSVFILE || null;
let csvBuffer = [];
if (CSVFILE) appendFileSync(CSVFILE, 'timestampMs,status,latencyMs\n');
function csvFlush(force = false) {
  if (!CSVFILE) return;
  if (csvBuffer.length >= 500 || (force && csvBuffer.length)) {
    appendFileSync(CSVFILE, csvBuffer.join('\n') + '\n');
    csvBuffer = [];
  }
}

const LONDON = ['N1 7SX', 'SW11 1AA', 'TW3 4DX', 'SE1 7PB', 'E1 6AN', 'EC1A 1BB', 'SW1A 0AA', 'E14 5AB', 'SE10 8XJ', 'NW1 6XE', 'SE23 3HN', 'W6 9YE', 'UB3 1AA', 'CR0 1PB', 'EN1 1YQ'];
const NYC = ['10001', '11201', '10453', '11375', '10301', '10025', '11215'];
const POOL = [...LONDON, ...NYC];
const PERSONAS = ['balanced', 'family', 'investor', 'quietlife', 'renter'];

const lat = [];
const codes = {};
let errSamples = [];

function record(status, ms, body) {
  codes[status] = (codes[status] || 0) + 1;
  lat.push(ms);
  if (CSVFILE) {
    csvBuffer.push(`${Date.now()},${status},${Math.round(ms)}`);
    csvFlush();
  }
  if (status >= 400 && errSamples.length < 5) errSamples.push({ status, body: String(body).slice(0, 160) });
}

function pct(sorted, p) {
  return sorted[Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length))];
}

async function one() {
  const pc = POOL[Math.floor(Math.random() * POOL.length)];
  const extra =
    Math.random() < 0.2
      ? `&weights=quiet:0.5,afford:0.2,growth:0.1,live:0.2`
      : Math.random() < 0.4
        ? `&persona=${PERSONAS[Math.floor(Math.random() * PERSONAS.length)]}`
        : '';
  const t0 = performance.now();
  try {
    const r = await fetch(`${API}/v1/score?postcode=${encodeURIComponent(pc)}${extra}`, {
      headers: { 'X-Api-Key': KEY },
    });
    const body = r.status >= 400 ? await r.text() : (await r.text(), '');
    record(r.status, performance.now() - t0, body);
  } catch (e) {
    record(0, performance.now() - t0, e.message);
  }
}

async function singlePhase() {
  const workers = Number(process.env.WORKERS || 8);
  const durationMs = Number(process.env.DURATION_S || 60) * 1000;
  const end = Date.now() + durationMs;
  const t0 = Date.now();
  await Promise.all(
    Array.from({ length: workers }, async () => {
      const pause = Number(process.env.PAUSE_MS || 0);
      while (Date.now() < end) {
        await one();
        if (pause) await new Promise((r) => setTimeout(r, pause));
      }
    })
  );
  const elapsed = (Date.now() - t0) / 1000;
  summarise(elapsed);
}

function batchPayload() {
  const queries = Array.from({ length: 100 }, () => {
    const pc = POOL[Math.floor(Math.random() * POOL.length)];
    return Math.random() < 0.3
      ? { postcode: pc, persona: PERSONAS[Math.floor(Math.random() * PERSONAS.length)] }
      : { postcode: pc };
  });
  return JSON.stringify({ queries });
}

async function oneBatch() {
  const t0 = performance.now();
  try {
    const r = await fetch(`${API}/v1/score/batch`, {
      method: 'POST',
      headers: { 'X-Api-Key': KEY, 'Content-Type': 'application/json' },
      body: batchPayload(),
    });
    let note = '';
    if (r.status === 200) {
      const j = await r.json();
      const results = j.results || [];
      const failed = results.filter((x) => x && x.error).length;
      note = `rows=${results.length} rowErrors=${failed}`;
    } else {
      note = (await r.text()).slice(0, 160);
    }
    const ms = performance.now() - t0;
    record(r.status, ms, note);
    console.log(`batch: ${r.status} ${Math.round(ms)}ms ${note}`);
  } catch (e) {
    record(0, performance.now() - t0, e.message);
    console.log(`batch: NETWORK-ERR ${e.message}`);
  }
}

async function batchPhase() {
  const count = Number(process.env.COUNT || 10);
  const conc = Number(process.env.CONC || 1);
  const t0 = Date.now();
  let done = 0;
  while (done < count) {
    const n = Math.min(conc, count - done);
    await Promise.all(Array.from({ length: n }, oneBatch));
    done += n;
  }
  summarise((Date.now() - t0) / 1000);
}

function summarise(elapsed) {
  csvFlush(true);
  const sorted = [...lat].sort((a, b) => a - b);
  const r = (x) => Math.round(x);
  console.log(
    JSON.stringify(
      {
        phase: PHASE,
        requests: lat.length,
        elapsedS: Math.round(elapsed * 10) / 10,
        achievedRps: Math.round((lat.length / elapsed) * 10) / 10,
        statusCodes: codes,
        latencyMs: sorted.length
          ? { p50: r(pct(sorted, 50)), p90: r(pct(sorted, 90)), p95: r(pct(sorted, 95)), p99: r(pct(sorted, 99)), max: r(sorted[sorted.length - 1]) }
          : null,
        errSamples,
      },
      null,
      1
    )
  );
}

if (PHASE === 'batch') await batchPhase();
else await singlePhase();
