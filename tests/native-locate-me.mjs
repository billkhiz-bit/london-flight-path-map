// "Score where I am" says how every tap ended (iOS 1.0.22, Bill's yes 2026-11-26). The native-only button used to go
// quiet when no UK postcode was found or anything failed, the reason only in the console: a reviewer outside the UK
// would tap it and see nothing happen. Each ending is reached ON PURPOSE under a Capacitor shim, with postcodes.io
// answered in the page:
//   none      GPS gives a Cupertino point; postcodes.io answers 200 with result null -> the "works in the UK" words
//   refused   GPS rejects (permission denied, timeout)                              -> the "could not be read" words
//   outage    a London point; postcodes.io answers 500 (JSON, as it does)           -> "could not be read", NOT "none"
//   found     a London point; postcodes.io names TW4 6EX                            -> the box holds it, no words
// and for each: the words in the hint under the search box AND the screen-reader status line, the button back to
// itself (no aria-disabled), the hint restored once the box is typed in. While GPS is pending the button is busy
// through aria-disabled and KEEPS keyboard focus (audit M-11: a disabled button drops focus to <body>).
// TEST_INDEX=<path> runs it against another copy of the page (how it was proven red on master's).
import { chromium, devices } from '@playwright/test';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';

const fileUrl = pathToFileURL(resolve(process.env.TEST_INDEX || 'index.html')).href;
const iPhone = devices['iPhone 13'];
const NONE = 'Score where I am works in the UK. Search a place or postcode instead.';
const FAILED = 'Your location could not be read. Search a place or postcode instead.';
const POINTS = {
  cupertino: { latitude: 37.3349, longitude: -122.009 },
  hounslow: { latitude: 51.4638, longitude: -0.4071 },
  // Audit 2026-11-27: a UK point more than 100 m from any postcode's centre. postcodes.io's reverse lookup reaches
  // 100 m unless asked for more, so the app told a walker in Richmond Park "Score where I am works in the UK".
  // Read live that day: no radius -> result null; radius=2000 -> TW10 5HR at 745 m.
  richmondPark: { latitude: 51.443, longitude: -0.275 },
};

let failures = 0;
const expect = (ok, what) => {
  console.log(`${ok ? 'ok  ' : 'FAIL'}  ${what}`);
  if (!ok) failures += 1;
};

async function run(name, { gps, postcodes, hold = false }) {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ ...iPhone });
  const page = await ctx.newPage();
  await page.addInitScript(([gpsMode, point, holdIt]) => {
    let release;
    window.__geoHeld = new Promise((r) => { release = r; });
    window.__geoRelease = () => release();
    window.Capacitor = {
      isNativePlatform: () => true,
      getPlatform: () => 'ios',
      Plugins: {
        Geolocation: {
          getCurrentPosition: async () => {
            if (holdIt) await window.__geoHeld;
            if (gpsMode === 'refuse') throw new Error('User denied location permission');
            return { coords: point };
          },
        },
      },
    };
  }, [gps === 'refuse' ? 'refuse' : 'give', POINTS[gps] || POINTS.hounslow, hold]);
  // Nothing leaves the test: postcodes.io is answered here, every other remote request is refused.
  await page.route('**/*', (route) => {
    const url = route.request().url();
    if (url.startsWith('file:')) return route.continue();
    if (url.startsWith('https://api.postcodes.io/postcodes?')) {
      const answer = typeof postcodes === 'function' ? postcodes(url) : postcodes;
      return route.fulfill({ status: answer.status, contentType: 'application/json', body: JSON.stringify(answer.body) });
    }
    return route.abort();
  });
  await page.goto(fileUrl, { waitUntil: 'load' }).catch(() => {});
  await page.waitForFunction(() => {
    const b = document.getElementById('locate-me');
    return b && !b.hidden;
  }, null, { timeout: 15000 });
  const hintBefore = await page.textContent('#search-hint');
  await page.focus('#locate-me');
  await page.keyboard.press('Enter');
  if (hold) {
    // A page that never marks the button busy fails here as a check, not as a timeout.
    await page.waitForFunction(() => document.getElementById('locate-me').getAttribute('aria-disabled') === 'true',
      null, { timeout: 5000 }).catch(() => {});
    const busy = await page.evaluate(() => {
      const b = document.getElementById('locate-me');
      return { focused: document.activeElement === b, disabled: b.disabled, text: b.textContent.trim() };
    });
    expect(busy.focused && !busy.disabled && busy.text === '…', `${name}: busy through aria-disabled, focus kept on the button`);
    await page.evaluate(() => window.__geoRelease());
  }
  await page.waitForFunction(() => document.getElementById('locate-me').getAttribute('aria-disabled') !== 'true',
    null, { timeout: 15000 });
  await page.waitForTimeout(200);
  const after = await page.evaluate(() => ({
    hint: document.getElementById('search-hint').textContent.trim(),
    status: document.getElementById('result-status').textContent.trim(),
    box: document.getElementById('search-input').value,
    button: document.getElementById('locate-me').textContent.trim(),
    hintShown: (() => {
      const h = document.getElementById('search-hint');
      const r = h.getBoundingClientRect();
      return r.width > 0 && r.height > 0 && getComputedStyle(h).display !== 'none';
    })(),
  }));
  await browser.close().catch(() => {});
  return { page, hintBefore: hintBefore.trim(), after, browser };
}

async function saidCase(name, opts, words) {
  const { hintBefore, after } = await run(name, opts);
  expect(after.hint === words, `${name}: the hint says "${words.slice(0, 40)}..." (got "${after.hint.slice(0, 60)}")`);
  expect(after.hintShown, `${name}: the hint is on screen`);
  expect(after.status === words, `${name}: the screen-reader status says the same`);
  expect(after.button === '◎' || after.button === '◎', `${name}: the button is itself again (got "${after.button}")`);
  return hintBefore;
}

await saidCase('none', { gps: 'cupertino', postcodes: { status: 200, body: { status: 200, result: null } } }, NONE);
await saidCase('refused', { gps: 'refuse', postcodes: { status: 200, body: { status: 200, result: null } } }, FAILED);
await saidCase('outage', { gps: 'hounslow', postcodes: { status: 500, body: { status: 500, error: 'Internal error' } } },
  FAILED);
await saidCase('busy', { gps: 'cupertino', postcodes: { status: 200, body: { status: 200, result: null } }, hold: true },
  NONE);

// found: the postcode goes into the box and no locate words appear.
{
  const { hintBefore, after } = await run('found', {
    gps: 'hounslow', postcodes: { status: 200, body: { status: 200, result: [{ postcode: 'TW4 6EX' }] } },
  });
  expect(after.box === 'TW4 6EX', `found: the box holds TW4 6EX (got "${after.box}")`);
  expect(after.hint !== NONE && after.hint !== FAILED, 'found: no locate words in the hint');
  expect(hintBefore.length > 0, 'found: the page had a hint to begin with');
}

// park: a UK point 745 m from the nearest postcode is found, never told it is outside the UK. The stub answers as
// postcodes.io does: nothing within its default 100 m, TW10 5HR when the request reaches 745 m or more.
{
  const { after } = await run('park', {
    gps: 'richmondPark',
    postcodes: (url) => {
      const radius = Number(new URL(url).searchParams.get('radius') || 100);
      return radius >= 745
        ? { status: 200, body: { status: 200, result: [{ postcode: 'TW10 5HR', distance: 745 }] } }
        : { status: 200, body: { status: 200, result: null } };
    },
  });
  expect(after.box === 'TW10 5HR', `park: a UK point 745 m from a postcode finds TW10 5HR (got "${after.box}")`);
  expect(after.hint !== NONE, 'park: never told "works in the UK" while in the UK');
}

// restore: typing in the box brings the usual hint back.
{
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ ...iPhone });
  const page = await ctx.newPage();
  await page.addInitScript(() => {
    window.Capacitor = { isNativePlatform: () => true, getPlatform: () => 'ios',
      Plugins: { Geolocation: { getCurrentPosition: async () => { throw new Error('denied'); } } } };
  });
  await page.route('**/*', (route) => (route.request().url().startsWith('file:') ? route.continue() : route.abort()));
  await page.goto(fileUrl, { waitUntil: 'load' }).catch(() => {});
  await page.waitForFunction(() => !document.getElementById('locate-me').hidden, null, { timeout: 15000 });
  const usual = (await page.textContent('#search-hint')).trim();
  await page.focus('#locate-me');
  await page.keyboard.press('Enter');
  await page.waitForFunction((w) => document.getElementById('search-hint').textContent.trim() === w, FAILED,
    { timeout: 15000 }).catch(() => {});
  await page.focus('#search-input');
  await page.keyboard.type('T');
  const back = (await page.textContent('#search-hint')).trim();
  expect(back === usual, `restore: typing brings the usual hint back (got "${back.slice(0, 60)}")`);
  await browser.close();
}

if (failures) {
  console.log(`\nFAIL: ${failures} check(s) failed`);
  process.exit(1);
}
console.log('\nPASS: every ending of Score where I am is said, and the button keeps focus while busy');
