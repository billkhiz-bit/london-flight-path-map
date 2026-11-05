/**
 * /api/'s "Try a request" (Bill, 2026-11-04: the API page "animated and interactive, like the front page"): a reader sends
 * a postcode and sees the real request and its real answer, in the same band the front page shows (js/dev-demo.mjs).
 *
 * THE OPEN ROUTE, NEVER THE KEYED ONE. /v1/environment takes a point and needs no key. /v1/score would spend the public
 * demo key's quota on every visit, and that quota has run out on real prospects before (tests/stub-live-api.mjs).
 *
 * NOTHING LEAVES FOR postcodes.io UNTIL A READER SENDS. The privacy policy covers a postcode someone searches, not a lookup
 * they never asked for, so the example on arriving is a held point (EXAMPLE) and only the API is asked. A postcode a reader
 * sends is turned into a point by postcodes.io, as the front page's search does.
 *
 * ONE ROUTE, SHARED BY EVERY VISITOR. /v1/environment is throttled to 5 a second across the whole site (template.yaml), so a
 * press costs nothing it need not: a postcode on its way is not sent twice, a postcode on show replays, and a newer press
 * cancels what is on its way, even when that press needs no request of its own.
 *
 * WHAT THE ANSWER CAN BE, each read from the live route on 2026-11-05, and each said in words:
 *   - figures for the postcode asked (TW9 3PZ);
 *   - figures for a NEIGHBOUR: the route answers the nearest postcode to the point (ZE1 0AA answers as ZE1 9ZZ), and
 *     road noise can differ by 20 dB between neighbours, so a reader is told which one it is;
 *   - only some figures (EX1 1HS holds NO2 alone): the rest are said to be missing, never shown as zero;
 *   - a quiet road (NG11 8AH): a bound, "under 40 dB", which is a reading and never a missing figure;
 *   - a postcode with no point (the Isle of Man and the Channel Islands: postcodes.io answers 200 with a null latitude);
 *   - a postcode nobody knows, or no figures at all.
 *
 * THE ROUTE'S 404 IS NOT ALWAYS "NO POSTCODE HERE". The Lambda answers it too when its own call to postcodes.io fails
 * (reverse_geocode returns None for both), so the words cover both and ask the reader to send it again.
 *
 * A THROTTLED REQUEST HAS NO STATUS HERE. API Gateway's own errors carry no CORS header (checked live 2026-11-05: the 403
 * for a missing key has none, and template.yaml's GatewayResponses set none), so a browser cannot read its 429: fetch
 * just rejects. So one failure covers both, and its words say the API may be busy.
 *
 * Nothing typed is counted or stored. A way is a word from this file, once per page view.
 */

import { armDev, bindCodeTabs, bindCopy, devAnswer, finite, playDev, writeAnswer } from './dev-demo.mjs';
import { POSTCODE } from './place-box.mjs';

export const EXAMPLE = { postcode: 'TW9 3PZ', latitude: 51.476982, longitude: -0.285639 };

const squash = (pc) => String(pc ?? '').toUpperCase().replace(/[^A-Z0-9]/g, '');

/** A typed postcode in its usual form, or null when it cannot be one. No request is made for null. */
export function cleanPostcode(text) {
  const pc = squash(text);
  return POSTCODE.test(pc) ? `${pc.slice(0, -3)} ${pc.slice(-3)}` : null;
}

async function answerAt(geo, api, get, signal) {
  const res = await get(`${api}/v1/environment?lat=${geo.latitude}&lon=${geo.longitude}`, { signal });
  if (res.status === 404) return { kind: 'no-postcode' };
  if (!res.ok) return { kind: 'failed' };
  const env = await res.json();
  return devAnswer(env) ? { kind: 'answer', geo, env } : { kind: 'no-figures' };
}

// Every failure, a refused fetch included, is an outcome, so the page always has something true to say.
const outcomeOf = async (run) => {
  try { return await run(); } catch { return { kind: 'failed' }; }
};

/** The API's answer at a point: { kind: 'answer', geo, env }, or a kind with nothing to show. Never rejects. */
export const askPoint = (geo, api, { get = fetch, signal } = {}) => outcomeOf(() => answerAt(geo, api, get, signal));

/** A postcode's point, then the API's answer there, as one outcome. Never rejects. */
export const lookup = (pc, api, { get = fetch, signal } = {}) => outcomeOf(async () => {
  const place = await get(`https://api.postcodes.io/postcodes/${encodeURIComponent(squash(pc))}`, { signal });
  if (place.status === 404) return { kind: 'unknown' };
  if (!place.ok) return { kind: 'failed' };
  const geo = (await place.json())?.result;
  if (!geo) return { kind: 'unknown' };
  if (!finite(geo.latitude) || !finite(geo.longitude)) return { kind: 'no-point' };
  return answerAt(geo, api, get, signal);
});

const inWords = (list) => (list.length < 2 ? list.join('') : `${list.slice(0, -1).join(', ')} and ${list.at(-1)}`);

/** The postcode an answer is for: the one the route names, or the one asked when it names none. */
export const answeredFor = (asked, env) => env?.location?.postcode || asked;

/** What a reader is told about an answer on show: whose it is, and what it leaves out. */
export function sayAnswer(asked, env) {
  const answered = answeredFor(asked, env);
  const head = squash(answered) === squash(asked)
    ? `Answered for ${answered}.`
    : `Answered for ${answered}, the nearest postcode the API found to ${asked}.`;
  const { missing } = devAnswer(env);
  return missing.length ? `${head} No DEFRA figure here for ${inWords(missing)}.` : head;
}

/** What a reader is told when nothing new is on show. `shown` is the postcode still on the page, if any. */
export function sayProblem(kind, pc, shown) {
  const said = {
    invalid: 'That is not a UK postcode. Try one like SW5 9HP.',
    unknown: `We could not find ${pc}. Check it and send it again.`,
    'no-point': `${pc} has no map reference, so there is no point to ask about. The Isle of Man and the Channel Islands have none.`,
    'no-postcode': `The API could not match ${pc} to a postcode just now. Send it again in a moment, or try another.`,
    'no-figures': `No DEFRA noise or NO₂ figure for ${pc}.`,
    failed: 'The request did not finish. The API may be busy: wait a moment and send it again.',
  }[kind];
  return shown ? `${said} Still showing ${shown}.` : said;
}

// Once per page view, by name only, as js/count.mjs's own events are.
const counted = new Set();
function count(way) {
  if (counted.has(way)) return;
  counted.add(way);
  const name = `api-demo-${way}`;
  try { window.goatcounter?.count?.({ path: `event/${name}`, title: name, event: true }); } catch { /* never break the page for a count */ }
}

function init() {
  const form = document.getElementById('try-form');
  const box = document.getElementById('try-pc');
  const status = document.getElementById('try-status');
  const run = document.getElementById('dev-run');
  bindCopy(count);
  bindCodeTabs(count);
  // Without the API's host there is nothing to send to, so the form stays hidden and the page is its samples. .no-answer
  // gives back the room the page keeps for them.
  if (!form || !box || !status || !window.API_BASE) {
    for (const held of [form, run]) held?.classList.add('no-answer');
    return;
  }

  let asking = 0;
  let controller = null;
  let pending = null; // the postcode on its way
  let asked = null; // the postcode whose answer is on show, as it was asked
  let shown = null; // the postcode that answer is for
  let said = ''; // what the status line says of that answer
  let pressed = false; // a reader pressed the postcode on its way, so it plays when it lands

  // `way` is what the reader pressed; none means the example, arriving. Only the newest press may reach the page, so one
  // that needs no request still cancels what is on its way.
  async function ask(text, way) {
    if (way) count(way);
    const pc = cleanPostcode(text);
    if (!pc) {
      box.setAttribute('aria-invalid', 'true');
      status.textContent = sayProblem('invalid', null, shown);
      return;
    }
    box.removeAttribute('aria-invalid');
    if (pc === pending) {
      pressed ||= Boolean(way);
      return;
    }
    const id = ++asking;
    controller?.abort();
    pressed = false;
    if (pc === asked) {
      pending = null;
      form.removeAttribute('aria-busy');
      status.textContent = said; // a problem from an earlier press does not describe what is on show
      playDev();
      return;
    }
    controller = new AbortController();
    const { signal } = controller;
    pending = pc;
    form.setAttribute('aria-busy', 'true');
    status.textContent = `Asking about ${pc}.`;
    const outcome = way ? await lookup(pc, window.API_BASE, { signal }) : await askPoint(EXAMPLE, window.API_BASE, { signal });
    if (id !== asking) return;
    const press = Boolean(way) || pressed;
    pressed = false;
    pending = null;
    form.removeAttribute('aria-busy');
    box.removeAttribute('aria-invalid'); // the status line is about this request now, so a mark with no reason goes too
    if (outcome.kind !== 'answer' || !writeAnswer(outcome.geo, outcome.env)) {
      status.textContent = sayProblem(outcome.kind === 'answer' ? 'no-figures' : outcome.kind, pc, shown);
      run?.classList.add('no-answer'); // nothing is coming, so the room kept for it goes
      return;
    }
    asked = pc;
    shown = answeredFor(pc, outcome.env);
    said = sayAnswer(pc, outcome.env);
    status.textContent = said;
    armDev(count, { auto: !press });
    if (press) playDev(); // a press is a request, whatever the reader's motion setting
  }

  form.hidden = false;
  form.addEventListener('submit', (ev) => {
    ev.preventDefault();
    ask(box.value, 'send');
  });
  box.addEventListener('input', () => box.removeAttribute('aria-invalid'));
  for (const chip of form.querySelectorAll('[data-try]')) {
    chip.addEventListener('click', () => {
      box.value = chip.dataset.try;
      ask(chip.dataset.try, 'chip');
    });
  }
  ask(EXAMPLE.postcode);
}

if (typeof document !== 'undefined') init();
