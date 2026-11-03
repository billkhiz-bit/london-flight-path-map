/**
 * The full map's planes overhead layer (Bill's pick B2, 2026-11-02): pictures drawn by
 * scripts/build_planes_layer.py from the per-postcode files, placed on the map, named by the legend.
 *
 * What is held, from the DOM and the built files, never from a flag the code under test sets:
 *   - the legend's step rows are exactly the builder's steps and colours (index.json), both directions;
 *   - off at boot; switching it on shows the city's picture for the pressed kind of day, its district lines,
 *     and switches DEFRA aircraft noise off (and back: switching aircraft noise on switches planes off);
 *   - each picture is placed by its two corners through the map's own projection, and the file the browser
 *     loads is the size index.json says (so a picture and its corners cannot drift apart);
 *   - the kind-of-day switch swaps the picture and moves aria-pressed;
 *   - a city with no picture paints nothing and says so, and coming back paints again;
 *   - the period and the credits are read from index.json (ODbL attribution travels with the pictures);
 *   - at 390 px the legend group fits and each switch button is a 24 px target or more (WCAG 2.2 AA).
 * The pixels themselves (Kew 200+ flying west, clear flying east) are held by tests/test_build_planes_layer.py.
 *
 *   node tests/planes-layer.mjs
 */
import { chromium } from '@playwright/test';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';

const ROOT = process.cwd();
const PORT = 8971; // the other harnesses hold 8099, 8921-8926, 8931-8962
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

let index;
try {
  index = JSON.parse(await readFile(join(ROOT, 'data/planes-layer/index.json'), 'utf8'));
} catch {
  // Built from gitignored files: a clone without the tracks cannot run this. Unrunnable is not failed, never a pass.
  console.log('INCONCLUSIVE: data/planes-layer/index.json is missing (python scripts/build_planes_layer.py --write)');
  process.exit(0);
}

const server = createServer(async (req, res) => {
  const raw = decodeURIComponent(req.url.split('?')[0]);
  const p = join(ROOT, normalize(raw === '/' ? '/index.html' : raw));
  if (!p.startsWith(ROOT)) return res.writeHead(403).end();
  try {
    const body = await readFile(p);
    res.writeHead(200, { 'content-type': TYPES[extname(p)] || 'application/octet-stream' });
    res.end(body);
  } catch {
    res.writeHead(404).end();
  }
});
await new Promise((r) => server.listen(PORT, r));

let failures = 0;
let passed = 0;
const ok = (cond, name, detail = '') => {
  if (cond) {
    passed += 1;
    console.log(`  ok   ${name}`);
  } else {
    failures += 1;
    console.log(`  FAIL ${name}${detail ? `: ${detail}` : ''}`);
  }
};

const browser = await chromium.launch();
try {
  // Service workers BLOCKED: sw.js claims the page, and a request it makes never reaches page.route, so 3a's held
  // index.json would arrive at once and the "before it arrives" state would pass or fail by chance (as in
  // tests/failure-path.mjs).
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 }, serviceWorkers: 'block' })).newPage();
  // Offline: anything not on this server is refused, so the test reads only the repo's own files.
  await page.route('**/*', (route) => (route.request().url().startsWith(`http://localhost:${PORT}/`) ? route.continue() : route.abort()));
  await page.goto(`http://localhost:${PORT}/index.html`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.querySelector('.layer-planes') && typeof projection === 'function', null, { timeout: 30000 });

  // 1. The legend's steps are the builder's, both directions.
  const rows = await page.evaluate(() =>
    [...document.querySelectorAll('#legend-planes-steps [data-step]')].map((r) => {
      const c = getComputedStyle(r.querySelector('.legend-swatch')).backgroundColor.match(/\d+/g).map(Number);
      return { step: Number(r.dataset.step), colour: '#' + c.slice(0, 3).map((v) => v.toString(16).padStart(2, '0')).join('') };
    })
  );
  const want = index.steps.map((s) => ({ step: s.step, colour: s.colour.toLowerCase() }));
  const key = (xs) => JSON.stringify([...xs].sort((a, b) => a.step - b.step));
  ok(key(rows) === key(want), 'the legend names exactly the steps and colours the pictures are drawn in', `${key(rows)} vs ${key(want)}`);

  // 2. Off at boot.
  const boot = await page.evaluate(() => ({
    shown: getComputedStyle(document.querySelector('.layer-planes')).display !== 'none',
    legend: getComputedStyle(document.getElementById('legend-planes-group')).display !== 'none',
    pressed: document.querySelector('.layer-toggle[data-layer="planes"]').getAttribute('aria-pressed'),
  }));
  ok(!boot.shown && !boot.legend && boot.pressed === 'false', 'off when the map opens', JSON.stringify(boot));

  // 3. On: London's picture for flying west, its district lines, DEFRA aircraft noise switched off.
  const readState = () =>
    page.evaluate(() => {
      const img = document.getElementById('planes-img');
      const lines = document.getElementById('planes-districts-img');
      const num = (el, a) => Number(el.getAttribute(a));
      return {
        city: currentCity,
        href: img.getAttribute('href'),
        lines: lines.getAttribute('href'),
        box: ['x', 'y', 'width', 'height'].map((a) => num(img, a)),
        linesBox: ['x', 'y', 'width', 'height'].map((a) => num(lines, a)),
        shown: getComputedStyle(document.querySelector('.layer-planes')).display !== 'none',
        legend: getComputedStyle(document.getElementById('legend-planes-group')).display !== 'none',
        none: !document.getElementById('legend-planes-none').hidden,
        // What a visitor sees, not the flag: [hidden] loses to an author display rule unless the CSS says so.
        steps: getComputedStyle(document.getElementById('legend-planes-steps')).display !== 'none',
        kindSwitch: getComputedStyle(document.getElementById('legend-planes-kind')).display !== 'none',
        disclosure: getComputedStyle(document.getElementById('legend-planes-disclosure')).display !== 'none',
        aircraft: document.querySelector('.layer-toggle[data-layer="defra-aircraft"]').getAttribute('aria-pressed'),
        aircraftShown: getComputedStyle(document.querySelector('.layer-defra-aircraft')).display !== 'none',
        planesPressed: document.querySelector('.layer-toggle[data-layer="planes"]').getAttribute('aria-pressed'),
        kinds: Object.fromEntries([...document.querySelectorAll('[data-planes-kind]')].map((b) => [b.dataset.planesKind, b.getAttribute('aria-pressed')])),
        period: document.getElementById('legend-planes-period').textContent,
        credits: document.getElementById('legend-planes-credits').textContent,
      };
    });
  const waitHref = (end) =>
    page.waitForFunction((e) => (document.getElementById('planes-img').getAttribute('href') || '').endsWith(e), end, { timeout: 15000 }).then(
      () => true,
      () => false
    );
  if (await page.evaluate(() => document.querySelector('.layer-toggle[data-layer="defra-aircraft"]').getAttribute('aria-pressed')) !== 'true') {
    await page.click('.layer-toggle[data-layer="defra-aircraft"]'); // start from the default: aircraft noise on
  }
  // 3a. Before index.json arrives the legend is open but must name no step, offer no switch and explain nothing:
  // nothing is drawn yet. Reached ON PURPOSE by holding the file, never by hoping the network is slow.
  let release;
  const held = new Promise((r) => (release = r));
  await page.route('**/data/planes-layer/index.json', async (route) => {
    await held;
    await route.continue();
  });
  await page.click('.layer-toggle[data-layer="planes"]');
  await page.waitForFunction(() => getComputedStyle(document.getElementById('legend-planes-group')).display !== 'none', null, { timeout: 15000 });
  let s = await readState();
  ok(s.legend && !s.steps && !s.kindSwitch && !s.disclosure && !s.none,
    'while index.json is on its way the legend shows no steps, no switch and no "About this data"',
    JSON.stringify({ steps: s.steps, kindSwitch: s.kindSwitch, disclosure: s.disclosure, none: s.none }));
  release();
  const london = index.cities.london;
  await waitHref(london.files.westerly);
  s = await readState();
  ok(s.shown && s.legend && s.planesPressed === 'true', 'switching it on shows the layer and its legend', JSON.stringify({ shown: s.shown, legend: s.legend }));
  ok(s.href === `/data/planes-layer/${london.files.westerly}` && s.lines === `/data/planes-layer/${london.files.districts}`,
    'London shows its flying-west picture and its district lines', `${s.href} | ${s.lines}`);
  ok(s.aircraft === 'false' && !s.aircraftShown, 'switching it on switches DEFRA aircraft noise off (one orange layer at a time)',
    JSON.stringify({ pressed: s.aircraft, shown: s.aircraftShown }));
  ok(s.steps && s.kindSwitch && s.disclosure && !s.none, 'a city with a picture shows the steps, the switch and "About this data", not "not counted"',
    JSON.stringify({ steps: s.steps, kindSwitch: s.kindSwitch, disclosure: s.disclosure, none: s.none }));

  // 4. Placed by its corners through the map's own projection; the loaded file is the size index.json says.
  const placed = await page.evaluate((b) => {
    const tl = projection([b[0], b[3]]);
    const br = projection([b[2], b[1]]);
    return [tl[0], tl[1], br[0] - tl[0], br[1] - tl[1]];
  }, london.bounds);
  const near = (a, b) => a.every((v, i) => Math.abs(v - b[i]) < 0.5);
  ok(near(s.box, placed) && near(s.linesBox, placed), 'both pictures sit on their corners through the map projection',
    `${s.box.map((v) => v.toFixed(1))} vs ${placed.map((v) => v.toFixed(1))}`);
  const natural = await page.evaluate(async (href) => {
    const im = new Image();
    im.src = href;
    await im.decode();
    return [im.naturalWidth, im.naturalHeight];
  }, s.href);
  ok(natural[0] === london.size[0] && natural[1] === london.size[1], 'the picture the browser loads is the size its corners were cut for',
    `${natural} vs ${london.size}`);
  // The exact words index.months make, built here with the test's own month list (any two months used to pass).
  const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  const said = (yyyymm) => `${MONTHS[Number(String(yyyymm).slice(4, 6)) - 1]} ${String(yyyymm).slice(0, 4)}`;
  const wantPeriod = `${said(index.months[0])} to ${said(index.months[1])}`;
  ok(s.period === wantPeriod, 'the period is the months index.json counts, word for word', `"${s.period}" vs "${wantPeriod}"`);

  // 4b. Smoothed until one picture pixel covers a screen pixel, sharp from there (each pixel is a postcode's step).
  // Measured from the DOM (the picture's drawn width over its own), either side of the line, so a threshold set
  // anywhere else, or a rendering never switched, fails.
  const rendering = (k) =>
    page.evaluate(async (kk) => {
      zoom.scaleTo(svg, kk);
      await new Promise((r) => requestAnimationFrame(() => r()));
      const el = document.getElementById('planes-img');
      const im = new Image();
      im.src = el.getAttribute('href');
      await im.decode();
      return { k: kk, perPixel: el.getBoundingClientRect().width / im.naturalWidth, rendering: getComputedStyle(el).imageRendering };
    }, k);
  const k0 = await page.evaluate(() => d3.zoomTransform(svg.node()).k);
  const drawnW = await page.evaluate(() => {
    const el = document.getElementById('planes-img');
    return el.getBoundingClientRect().width;
  });
  const kStar = (k0 * london.size[0]) / drawnW; // the zoom at which one picture pixel is one screen pixel
  const below = await rendering(kStar * 0.9);
  const above = await rendering(kStar * 1.1);
  ok(below.perPixel < 1 && below.rendering !== 'pixelated', 'just below one screen pixel per picture pixel, the picture is smoothed', JSON.stringify(below));
  ok(above.perPixel >= 1 && above.rendering === 'pixelated', 'just above it, the picture is drawn sharp', JSON.stringify(above));
  await rendering(k0);
  ok(index.credits.every((c) => s.credits.includes(c)) && s.credits.includes(index.licence), 'every credit and the licence travel with the pictures', s.credits);

  // 5. The kind-of-day switch.
  await page.click('[data-planes-kind="easterly"]');
  await waitHref(london.files.easterly);
  s = await readState();
  ok(s.href.endsWith(london.files.easterly) && s.kinds.easterly === 'true' && s.kinds.westerly === 'false' && s.kinds.mixed === 'false',
    'flying east swaps the picture and moves the pressed state', JSON.stringify({ href: s.href, kinds: s.kinds }));
  await page.click('[data-planes-kind="mixed"]');
  await waitHref(london.files.mixed);
  s = await readState();
  ok(s.href.endsWith(london.files.mixed) && s.kinds.mixed === 'true', 'both ways swaps it again', s.href);

  // 6. A city with no picture paints nothing and says so; coming back paints again.
  const without = await page.evaluate((have) => Object.keys(CITY_DATA).find((c) => !have.includes(c) && CITY_DATA[c].country === 'United Kingdom'), Object.keys(index.cities));
  if (without) {
    await page.evaluate((c) => {
      switchCountry(CITY_DATA[c].country);
      return switchCity(c);
    }, without);
    await page.waitForFunction((c) => currentCity === c && !document.getElementById('legend-planes-none').hidden, without, { timeout: 30000 }).catch(() => {});
    s = await readState();
    ok(s.city === without && !s.href && !s.lines && s.none && !s.steps && !s.kindSwitch && !s.disclosure,
      `${without}: no picture, "not counted" said, and no steps, switch or "About this data"`,
      JSON.stringify({ city: s.city, href: s.href, none: s.none, steps: s.steps, kindSwitch: s.kindSwitch, disclosure: s.disclosure }));
    await page.evaluate(() => {
      switchCountry(CITY_DATA.london.country);
      return switchCity('london');
    });
    const back = await waitHref(london.files.mixed);
    s = await readState();
    ok(back && s.steps && !s.none, 'back in London the picture returns, on the kind still pressed', s.href);
  } else {
    ok(false, 'a UK city without a picture to test the empty case', 'every UK city has one: pick another empty case');
  }

  // 6b. THE DISTRICT UNDER A TAP (2026-11-03, Bill's pick "small card"): with the layer on, a tap names its postcode
  // district and links its planes page; a district without a page gets no card. Targets come from the BUILT files (the
  // district grid and the pages' holder), never typed, and each is a cell deep inside its district, so a tap cannot fall
  // on a boundary. Each picture pixel goes to the screen through the picture's own transform, then a real mouse click.
  {
    const ids = JSON.parse(await readFile(join(ROOT, 'data', 'planes-layer', london.files.district_ids), 'utf8'));
    const pages = JSON.parse(await readFile(join(ROOT, 'data', 'planes-districts-by-council.json'), 'utf8'));
    const withPage = new Set(Object.values(pages.councils).flat());
    const codeAt = (r, c) => {
      let x = 0;
      for (let i = 0; i < ids.rows[r].length; i += 2) {
        x += ids.rows[r][i + 1];
        if (c < x) return ids.rows[r][i];
      }
      return 0;
    };
    const deepCells = (want) => {
      const out = [];
      for (let r = 6; r < ids.rows.length - 6; r += 9) {
        for (let c = 6; c < ids.size[0] - 6; c += 9) {
          const code = codeAt(r, c);
          if (!code || !want(ids.names[code - 1])) continue;
          let same = true;
          for (let dr = -4; dr <= 4 && same; dr += 2) for (let dc = -4; dc <= 4 && same; dc += 2) same = codeAt(r + dr, c + dc) === code;
          if (same) out.push({ name: ids.names[code - 1], col: (c + 0.5) * ids.cell, row: (r + 0.5) * ids.cell });
        }
      }
      return out;
    };
    // The first deep cell whose screen point is a borough on the map (not under the legend, the panel or off screen).
    const onScreen = async (cells) => {
      for (const t of cells) {
        const pt = await page.evaluate(([col, row, W, H]) => {
          const img = document.getElementById('planes-img');
          const p = img.ownerSVGElement.createSVGPoint();
          p.x = +img.getAttribute('x') + (col / W) * +img.getAttribute('width');
          p.y = +img.getAttribute('y') + (row / H) * +img.getAttribute('height');
          const s2 = p.matrixTransform(img.getScreenCTM());
          const hit = document.elementFromPoint(s2.x, s2.y);
          return hit && hit.closest('path') && hit.ownerSVGElement === img.ownerSVGElement ? [s2.x, s2.y] : null;
        }, [t.col, t.row, london.size[0], london.size[1]]);
        if (pt) return { ...t, pt };
      }
      return null;
    };
    const card = () => page.evaluate(() => {
      const el = document.getElementById('planes-card');
      return { shown: !el.hidden, district: el.dataset.district || '', href: el.querySelector('a').getAttribute('href'),
               text: el.innerText.replace(/\s+/g, ' ').trim() };
    });
    const hit = await onScreen(deepCells((n) => withPage.has(n)));
    ok(Boolean(hit), 'a district with a planes page lies on screen in London, deep inside its outline', '');
    if (hit) {
      await page.mouse.click(hit.pt[0], hit.pt[1]);
      await page.waitForFunction(() => !document.getElementById('planes-card').hidden, null, { timeout: 10000 }).catch(() => {});
      let c = await card();
      ok(c.shown && c.district === hit.name && c.href === `/planes-overhead/${hit.name.toLowerCase()}/`,
        `a tap in ${hit.name} names it and links its page`, JSON.stringify(c));
      ok(!/\d/.test(c.text.split(hit.name).join('')), 'the card carries no figure, only the district and its link', c.text);
      await page.evaluate(() => switchCity('manchester'));
      c = await card();
      ok(!c.shown, 'switching city closes the card', JSON.stringify(c));
      await page.evaluate(() => switchCity('london'));
      await waitHref(london.files.mixed);
    }
    const noPage = await onScreen(deepCells((n) => !withPage.has(n)));
    if (noPage) {
      await page.mouse.click(noPage.pt[0], noPage.pt[1]);
      await page.waitForTimeout(800);
      const c = await card();
      ok(!c.shown, `a tap in ${noPage.name}, which has no planes page, shows no card (never a guessed link)`, JSON.stringify(c));
    } else {
      console.log('  (every on-screen London district has a page: the no-page case is not reachable here)');
    }
    if (hit) { // left open for step 7, which turns the layer off
      await page.mouse.click(hit.pt[0], hit.pt[1]);
      await page.waitForFunction(() => !document.getElementById('planes-card').hidden, null, { timeout: 10000 }).catch(() => {});
    }
  }

  // 7. Switching aircraft noise back on switches planes off.
  await page.click('.layer-toggle[data-layer="defra-aircraft"]');
  ok(await page.evaluate(() => document.getElementById('planes-card').hidden), 'planes off closes the district card', '');
  s = await readState();
  ok(s.aircraft === 'true' && s.planesPressed === 'false' && !s.shown && !s.legend, 'aircraft noise on switches planes overhead off',
    JSON.stringify({ aircraft: s.aircraft, planes: s.planesPressed, shown: s.shown }));

  // 8. Phone, 390 px: the legend group fits and the switch is a real target.
  const phone = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await phone.route('**/*', (route) => (route.request().url().startsWith(`http://localhost:${PORT}/`) ? route.continue() : route.abort()));
  await phone.goto(`http://localhost:${PORT}/index.html`, { waitUntil: 'domcontentloaded' });
  await phone.waitForFunction(() => document.querySelector('.layer-planes') && typeof projection === 'function', null, { timeout: 30000 });
  await phone.evaluate(() => {
    const trigger = document.getElementById('layers-trigger');
    if (trigger && trigger.getAttribute('aria-expanded') !== 'true') trigger.click();
  });
  await phone.click('.layer-toggle[data-layer="planes"]');
  await phone.evaluate(() => {
    const t = document.getElementById('legend-toggle');
    if (t && t.getAttribute('aria-expanded') !== 'true') t.click();
  });
  // The switch shows only once index.json has said London has a picture: wait for IT, not just the group.
  await phone.waitForFunction(() => getComputedStyle(document.getElementById('legend-planes-kind')).display !== 'none', null, { timeout: 15000 }).catch(() => {});
  const fit = await phone.evaluate(() => {
    const group = document.getElementById('legend-planes-group');
    const legend = document.getElementById('map-legend');
    const btns = [...document.querySelectorAll('[data-planes-kind]')].map((b) => b.getBoundingClientRect());
    const r = group.getBoundingClientRect();
    return {
      visible: getComputedStyle(group).display !== 'none',
      overflow: group.scrollWidth - group.clientWidth,
      inViewport: r.left >= 0 && r.right <= window.innerWidth,
      legendOverflow: legend.scrollWidth - legend.clientWidth,
      minH: Math.min(...btns.map((b) => b.height)),
      minW: Math.min(...btns.map((b) => b.width)),
    };
  });
  ok(fit.visible && fit.overflow <= 0 && fit.legendOverflow <= 0 && fit.inViewport, 'at 390 px the planes legend fits, nothing sideways', JSON.stringify(fit));
  ok(fit.minH >= 24 && fit.minW >= 24, 'at 390 px each kind-of-day button is a 24 px target or more', JSON.stringify(fit));
} finally {
  await browser.close();
  server.close();
}

console.log(failures ? `FAIL: ${failures} of ${passed + failures} checks` : `planes layer: ${passed} checks passed`);
process.exit(failures ? 1 : 0);
