// The approach strip on /how-it-works/ (2026-10-26): the page as a visitor gets it, with the strip working.
//
// WHY THIS EXISTS. Bill asked for the strip (made in the Blender repo, scripts/strip_page.py) high on
// /how-it-works/. It is the site's first interactive picture outside the map: a 10 km strip of London that slides
// under a plane as a range input moves, loading its tiles as they come into view. The page-wide gates (wording,
// a11y source scan, the upload check) read the page; none of them moves the slider. This does:
//   - the page never scrolls sideways at 390 or 1366 wide (the track is 10,320 px wide inside its stage);
//   - the links to the page's sections sit under the opening words, before the strip, as pills;
//   - the slider moves the plane, and says where it is to a screen reader (aria-valuetext changes with it);
//   - "Go to Hounslow" puts the plane over Hounslow, from the keyboard;
//   - reduced motion: the section is .still, and nothing animates;
//   - on arrival only the tiles near the plane are fetched (not all 22), more as it moves, none 404s; no page errors.
//
//   node tests/approach-strip.mjs

import { chromium } from '@playwright/test';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { dirname, extname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const PORT = Number(process.env.APPROACH_STRIP_PORT) || 8946;  // another port for a run beside a preflight
const TYPES = { '.html': 'text/html', '.mjs': 'application/javascript', '.js': 'application/javascript', '.css': 'text/css',
  '.woff2': 'font/woff2', '.avif': 'image/avif', '.webp': 'image/webp', '.svg': 'image/svg+xml', '.json': 'application/json' };
const missing = [];
const server = createServer(async (req, res) => {
  let p = decodeURIComponent(req.url.split('?')[0]);
  // CloudFront's rewrite: a folder, or an extensionless path, is served from its index.html with no redirect
  if (p.endsWith('/')) p += 'index.html';
  else if (!extname(p)) p += '/index.html';
  try {
    const buf = await readFile(join(ROOT, p));
    res.writeHead(200, { 'Content-Type': TYPES[extname(p)] || 'application/octet-stream' });
    res.end(buf);
  } catch {
    missing.push(p);
    res.writeHead(404); res.end('not found');
  }
});
await new Promise((r) => server.listen(PORT, '127.0.0.1', r));
const URL_ = `http://127.0.0.1:${PORT}/how-it-works/`;

let failures = 0, checks = 0;
const ok = (cond, label, detail = '') => {
  checks += 1;
  if (!cond) failures += 1;
  console.log(`  ${cond ? 'ok  ' : 'FAIL'} ${label}${cond || !detail ? '' : `: ${detail}`}`);
};

const browser = await chromium.launch();
for (const [w, h, motion] of [[1366, 900, 'no-preference'], [390, 844, 'no-preference'], [390, 844, 'reduce']]) {
  const page = await browser.newPage({ viewport: { width: w, height: h }, reducedMotion: motion });
  const errors = [];
  const tiles = new Set();
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('request', (r) => { if (/strip_(real|noise)_\d+\./.test(r.url())) tiles.add(r.url().split('/').pop().split('.')[0]); });
  await page.route('**/js/count.mjs', (r) => r.fulfill({ status: 200, contentType: 'application/javascript', body: '' }));
  await page.goto(URL_, { waitUntil: 'load' });
  await page.waitForTimeout(400);
  const tag = `${w}px${motion === 'reduce' ? ', reduced motion' : ''}`;

  const layout = await page.evaluate(() => {
    const lead = document.querySelector('p.lead'), sec = document.querySelector('section.approach');
    return {
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      // On this page (Bill, 2026-10-26: "links to different sections ... like the about page"): the pills straight
      // under the opening words, so the way past the strip comes before it; the strip straight after them.
      navAfterLead: lead?.nextElementSibling?.matches('nav.contents'),
      afterNav: lead?.nextElementSibling?.nextElementSibling === sec,
      pills: [...document.querySelectorAll('nav.contents a')].map((a) => [a.getAttribute('href'), !!document.getElementById(a.getAttribute('href').slice(1)),
        getComputedStyle(a).borderRadius !== '0px']),
      still: sec?.classList.contains('still'),
    };
  });
  ok(layout.overflow <= 0, `${tag}: the page does not scroll sideways`, `${layout.overflow}px too wide`);
  ok(layout.navAfterLead && layout.afterNav, `${tag}: the opening paragraph, then the links to the page's sections, then the strip`);
  ok(layout.pills.length === 8 && layout.pills.every(([, there, pill]) => there && pill),
    `${tag}: all 8 section links are pills, each to a section on the page`, JSON.stringify(layout.pills));
  ok(layout.still === (motion === 'reduce'), `${tag}: reduced motion ${motion === 'reduce' ? 'stills' : 'does not still'} the strip`);
  // Counted on arrival, before the plane is moved: flown end to end, every tile rightly comes into view.
  const onArrival = tiles.size;
  ok(onArrival > 0 && onArrival < 22, `${tag}: on arrival, only the tiles near the plane are fetched (${onArrival} of 22)`, [...tiles].join(','));

  // THE CONTROLS (Bill, 2026-10-26: a "physical slider", the drag symbol on the line, and the video-player layout
  // recommended): Fly it in the slider's own row, left of it, straight under the picture; the Go to buttons next and
  // the readout after them; a grab area 44 px tall; the end labels on one line; the places between the ends named
  // under the slider where there is room (390: none, so nothing collides or overflows).
  const rail = await page.evaluate(() => {
    const box = (sel) => document.querySelector(sel).getBoundingClientRect();
    const st = box('.approach .stage'), sl = box('#approach-slider'), fly = box('#approach-fly');
    const jumps = box('.approach .jumps'), readout = box('.approach .readout'), label = box('.approach .rail label');
    const names = [...document.querySelectorAll('.approach .marks i span')]
      .filter((s) => getComputedStyle(s).display !== 'none').map((s) => s.textContent);
    const mid = (r) => r.top + r.height / 2;
    return {
      oneRow: Math.abs(mid(fly) - mid(sl)) <= 3 && fly.right <= sl.left,
      order: st.bottom <= fly.top && st.bottom <= sl.top && sl.bottom <= jumps.top && jumps.bottom <= readout.top,
      labelLines: Math.round(label.height / parseFloat(getComputedStyle(document.querySelector('.approach .rail label')).lineHeight)),
      height: sl.height, names,
    };
  });
  ok(rail.oneRow, `${tag}: Fly it sits beside the slider, in its row, on the left`);
  ok(rail.order, `${tag}: under the picture, the slider row, then the Go to buttons, then the readout`);
  ok(rail.labelLines === 1, `${tag}: the slider's end labels fit on one line`, `${rail.labelLines} lines`);
  ok(rail.height >= 44, `${tag}: the slider is at least 44 px tall to grab`, `${rail.height}px`);
  ok(JSON.stringify(rail.names) === JSON.stringify(w > 560 ? ['Battersea', 'Kew', 'Hounslow'] : []),
    `${tag}: the places between the ends are named under the slider ${w > 560 ? '(all three)' : '(none on a phone)'}`, JSON.stringify(rail.names));

  // Boxes of the stage, the plane and every card on show, to hold the two embed fixes (js/approach.mjs).
  const boxes = () => page.evaluate(() => {
    const r = (el) => { const b = el.getBoundingClientRect(); return { l: b.left, t: b.top, r: b.right, b: b.bottom }; };
    return { stage: r(document.querySelector('.approach .stage')), plane: r(document.querySelector('.approach .plane')),
      cards: [...document.querySelectorAll('.approach .card.on')].map((c) => ({ name: c.querySelector('b').textContent, ...r(c) })) };
  });
  const settle = () => page.waitForTimeout(motion === 'reduce' ? 150 : 1100);  // a card springs in over 0.5 s
  await settle();
  const arrival = await boxes();
  // All four edges: a first fix kept cards off the left edge but lifted Westminster's out of the top
  const cut = arrival.cards.filter((c) => c.l < arrival.stage.l - 0.5 || c.r > arrival.stage.r + 0.5
    || c.t < arrival.stage.t - 0.5 || c.b > arrival.stage.b + 0.5);
  ok(arrival.cards.length > 0 && cut.length === 0, `${tag}: on arrival every card on show is inside the picture (none cut at its edge)`,
    JSON.stringify({ stage: arrival.stage, cut }));

  const at = () => page.evaluate(() => ({
    text: document.getElementById('approach-slider').getAttribute('aria-valuetext'),
    left: parseFloat(document.querySelector('.approach .plane').style.left),
    below: document.querySelector('.approach .readout .below').textContent,
  }));
  const start = await at();
  ok(/km to the runway/.test(start.text || ''), `${tag}: the slider tells a screen reader where the plane is`, start.text);
  await page.locator('#approach-slider').focus();
  for (let i = 0; i < 40; i += 1) await page.keyboard.press('ArrowRight'); // dir="rtl": right is back towards the start
  for (let i = 0; i < 120; i += 1) await page.keyboard.press('ArrowLeft');
  await page.waitForTimeout(200);
  const moved = await at();
  ok(moved.text !== start.text && moved.left !== start.left, `${tag}: the keyboard moves the plane, and what it says changes`,
    JSON.stringify({ start, moved }));

  // A real drag of the handle: from its start at the right-hand end (dir="rtl") to the middle of the track.
  const box = await page.locator('#approach-slider').boundingBox();
  const beforeDrag = await at();
  await page.locator('#approach-slider').evaluate((el) => { el.value = '0'; el.dispatchEvent(new Event('input', { bubbles: true })); });
  await page.waitForTimeout(150);
  const startDrag = await at();
  await page.mouse.move(box.x + box.width - 22, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 8 });
  await page.mouse.up();
  await page.waitForTimeout(200);
  const dragged = await at();
  ok(dragged.text !== startDrag.text && dragged.left !== startDrag.left, `${tag}: dragging the handle moves the plane`,
    JSON.stringify({ beforeDrag: beforeDrag.text, startDrag: startDrag.text, dragged: dragged.text }));

  // Dragging the PICTURE (Bill, 2026-10-26, three rounds: "not obvious and clunky", "too fast", then "I have to drag to
  // the end of the page and still don't reach the end"): grabbed at the drag symbol on the plane's line, LEFTWARDS
  // brings the plane in; a short drag moves it gently (fine control near the grab); one drag to the window's left edge
  // lands it; one back to the right-hand edge returns it to the start.
  await page.locator('#approach-slider').evaluate((el) => { el.value = '0'; el.dispatchEvent(new Event('input', { bubbles: true })); });
  await page.locator('.approach .stage').evaluate((el) => el.scrollIntoView({ block: 'center' }));
  await page.waitForTimeout(900);
  const kmOf = (t) => (/over the runway|touched down/.test(t) ? 0 : parseFloat((t.match(/^([\d.]+) km to the runway/) || [])[1]));
  const drag = async (toX, steps = 24) => {
    const g = await page.locator('.approach .grip').boundingBox();
    const from = [g.x + g.width / 2, g.y + g.height / 2];
    await page.mouse.move(...from);
    await page.mouse.down();
    await page.mouse.move(toX(from[0]), from[1], { steps });
    await page.mouse.up();
    await page.waitForTimeout(900);   // the plane eases there in ~0.2 s
    return kmOf((await at()).text);
  };
  // THE FEEL (Bill: "a bit more while dragging, not too much"), as shares of the room to the window's edge: a tenth of
  // it moves the plane gently (under 8% of the route: an even spread moves 10%), halfway brings it 25-45% of the way
  // in (it was 15-22%: slow, then a lurch; an even spread is 50%, the "too fast" one).
  const reset = async () => {
    await page.locator('#approach-slider').evaluate((el) => { el.value = '0'; el.dispatchEvent(new Event('input', { bubbles: true })); });
    await page.waitForTimeout(900);
  };
  const room = (await page.locator('.approach .grip').boundingBox()).x + 20 - 12;
  const km0 = kmOf((await at()).text);
  const kmTenth = await drag((x) => x - 0.1 * room, 6);
  ok(km0 - kmTenth > 0.1 && (km0 - kmTenth) / 24.5 < 0.08, `${tag}: a short drag left moves the plane gently`, `${km0} -> ${kmTenth} km`);
  await reset();
  const kmHalf = await drag((x) => x - 0.5 * room, 12);
  const halfShare = (km0 - kmHalf) / 24.5;
  ok(halfShare > 0.25 && halfShare < 0.45, `${tag}: halfway to the edge brings it about a third of the way in`, `${(100 * halfShare).toFixed(0)}% of the route`);
  await reset();
  const kmLanded = await drag(() => 1);
  ok(kmLanded === 0, `${tag}: one drag to the window's left edge lands the plane`, `${kmLanded} km to go`);
  const kmBack = await drag(() => w - 1);
  ok(kmBack >= km0 - 0.05, `${tag}: one drag to the right-hand edge takes it back to the start`, `${kmBack} km (start ${km0})`);

  // THE HANDLE IS THE POINT OF CONTACT (Bill, 2026-10-26): it stays under the finger while held (the land scrolls
  // beneath), the plane eases back to the middle once let go, a drag elsewhere on the picture moves nothing, and it
  // looks and feels like a handle (a grab cursor, a target wider than the 40 px knob).
  {
    const g = await page.locator('.approach .grip').boundingBox();
    const gx = g.x + g.width / 2, gy = g.y + g.height / 2;
    await page.mouse.move(gx, gy);
    await page.mouse.down();
    let worst = 0;
    for (let i = 1; i <= 8; i += 1) {
      const px = gx - i * 0.05 * gx;              // pulling left, a little at a time, to just under halfway
      await page.mouse.move(px, gy);
      await page.waitForTimeout(60);
      const now = await page.locator('.approach .grip').boundingBox();
      worst = Math.max(worst, Math.abs(now.x + now.width / 2 - px));
    }
    await page.mouse.up();
    // within 6 px: the drag starts with the view held at the strip's east end, where for its first pixels the plane
    // cannot sit exactly under the finger until it eases off that end (measured 3.9 px at 1366; nothing on a 40 px knob)
    ok(worst <= 6, `${tag}: the handle stays under the finger while held`, `${worst.toFixed(1)} px apart at worst`);
    await page.waitForTimeout(1300);
    const back = await page.evaluate(() => {
      const v = document.querySelector('.approach .view').getBoundingClientRect(), p = document.querySelector('.approach .plane').getBoundingClientRect();
      return Math.abs((p.left + p.right) / 2 - (v.left + v.right) / 2);
    });
    ok(back <= 3, `${tag}: let go, the plane eases back to the middle`, `${back.toFixed(1)} px off the middle`);
    // read only once the plane is still: a first run read it mid-ease (a preflight competing for the machine) and failed
    let before = (await at()).text;
    for (let i = 0; i < 20; i += 1) { await page.waitForTimeout(150); const now = (await at()).text; if (now === before) break; before = now; }
    const v = await page.locator('.approach .view').boundingBox();
    await page.mouse.move(v.x + 30, v.y + 30);
    await page.mouse.down();
    await page.mouse.move(v.x + v.width - 30, v.y + 30, { steps: 10 });
    await page.mouse.up();
    await page.waitForTimeout(600);
    const after = (await at()).text;
    ok(after === before, `${tag}: a drag elsewhere on the picture moves nothing`, JSON.stringify({ before, after, at: [v.x + 30, v.y + 30], hit: await page.evaluate(([x, y]) => { const e = document.elementFromPoint(x, y); return e && (e.className?.baseVal ?? e.className); }, [v.x + 30, v.y + 30]) }));
    const feel = await page.evaluate(() => {
      const el = document.querySelector('.approach .grip'), b = el.getBoundingClientRect(), cx = (b.left + b.right) / 2, cy = (b.top + b.bottom) / 2;
      return { cursor: getComputedStyle(el).cursor, wide: document.elementFromPoint(cx + 28, cy) === el && document.elementFromPoint(cx, cy + 28) === el };
    });
    ok(feel.cursor === 'grab' && feel.wide, `${tag}: the handle has a grab cursor and a target wider than its knob`, JSON.stringify(feel));
  }

  // LONDON NEVER SLIDES WITH THE HAND (Bill, 2026-10-26: dragging back to the start "moves the London landscape with
  // it"): wherever the handle goes, the land stays put or scrolls the other way, sampled all along a drag from Kew to
  // each window edge; and at the start, pulling on moves neither London nor the handle (it stops, like a slider's end).
  {
    const trackX = () => page.evaluate(() => document.querySelector('.approach .track').getBoundingClientRect().left);
    const slid = [];
    // Battersea -> the start is the case Bill hit: little route left for a lot of screen, where only the floor (never
    // slower than the ground under the finger) keeps London from sliding along (proven: without it, this goes red)
    for (const [dir, edge, from] of [['right', w - 2, 'kew-gardens'], ['left', 2, 'kew-gardens'], ['right', w - 2, 'battersea']]) {
      await page.locator(`.approach .jump[data-place="${from}"]`).click();
      await page.waitForTimeout(1400);
      const g = await page.locator('.approach .grip').boundingBox();
      const gx = g.x + g.width / 2, gy = g.y + g.height / 2;
      await page.mouse.move(gx, gy);
      await page.mouse.down();
      let last = await trackX();
      for (let i = 1; i <= 14; i += 1) {
        await page.mouse.move(gx + (edge - gx) * (i / 14), gy);
        await page.waitForTimeout(40);
        const now = await trackX();
        if (dir === 'right' ? now > last + 0.5 : now < last - 0.5) slid.push(`${from} ${dir} step ${i}: ${(now - last).toFixed(1)} px`);
        last = now;
      }
      await page.mouse.up();
      await page.waitForTimeout(1200);
    }
    ok(slid.length === 0, `${tag}: dragging either way, London never slides along with the hand`, slid.slice(0, 4).join('; '));
    await page.locator('#approach-slider').evaluate((el) => { el.value = '0'; el.dispatchEvent(new Event('input', { bubbles: true })); });
    // wait until the plane is STILL: easing 24 km back takes ~2 s, and a handle grabbed mid-ease rightly snaps to the end
    let pos = null;
    for (let i = 0; i < 40; i += 1) {
      await page.waitForTimeout(100);
      const now = await page.evaluate(() => document.querySelector('.approach .plane').style.left);
      if (now === pos) break;
      pos = now;
    }
    const g = await page.locator('.approach .grip').boundingBox();
    const t0 = await trackX(), h0 = g.x + g.width / 2;
    await page.mouse.move(g.x + g.width / 2, g.y + g.height / 2);
    await page.mouse.down();
    await page.mouse.move(Math.min(w - 2, g.x + g.width / 2 + 120), g.y + g.height / 2, { steps: 8 });
    await page.waitForTimeout(100);
    const gb = await page.locator('.approach .grip').boundingBox(), t1 = await trackX(), h1 = gb.x + gb.width / 2;  // centres: held, it grows
    await page.mouse.up();
    ok(Math.abs(t1 - t0) <= 1 && Math.abs(h1 - h0) <= 1, `${tag}: at the start, pulling on moves neither London nor the handle`,
      `land ${(t1 - t0).toFixed(1)} px, handle ${(h1 - h0).toFixed(1)} px`);
  }

  // THE GRIP (Bill: "a slider symbol ... on the vertical line that's attached to the plane"): on the plane's line,
  // always below the plane (landed too: pinned to the ground it covered the plane on the runway), between the plane
  // and the ground while it flies, the drag symbol, hidden from screen readers (the slider speaks).
  const grip = await page.evaluate(() => {
    const r = (sel) => document.querySelector(sel).getBoundingClientRect();
    const g = r('.approach .grip'), d = r('.approach .drop'), pl = r('.approach .plane');
    const el = document.querySelector('.approach .grip');
    return { onLine: Math.abs((g.left + g.right) / 2 - (d.left + d.right) / 2) <= 2,
      below: g.top >= (pl.top + pl.bottom) / 2,
      symbol: /svg/.test(getComputedStyle(el).backgroundImage), hidden: el.getAttribute('aria-hidden') === 'true' };
  });
  await page.locator('.approach .jump[data-place="westminster"]').click();
  await page.waitForTimeout(1100);
  const gripHigh = await page.evaluate(() => {
    const g = document.querySelector('.approach .grip').getBoundingClientRect(), d = document.querySelector('.approach .drop').getBoundingClientRect();
    return Math.abs((g.left + g.right) / 2 - (d.left + d.right) / 2) <= 2 && (g.top + g.bottom) / 2 > d.top && (g.top + g.bottom) / 2 < d.bottom;
  });
  ok(Object.values(grip).every(Boolean) && gripHigh, `${tag}: the drag symbol rides the plane's line, landed and high`, JSON.stringify({ ...grip, gripHigh }));
  // ...and never sits over a height mark's label (it hid "250 m" as "50 m"): at every place, no visible label under it.
  const hiddenMarks = [];
  for (const place of ['westminster', 'battersea', 'kew-gardens', 'hounslow']) {
    await page.locator(`.approach .jump[data-place="${place}"]`).click();
    await page.waitForTimeout(1100);
    hiddenMarks.push(...await page.evaluate((pl) => {
      const g = document.querySelector('.approach .grip').getBoundingClientRect();
      return [...document.querySelectorAll('.approach .tick')].filter((t) => getComputedStyle(t).visibility === 'visible')
        .map((t) => t.querySelector('span').getBoundingClientRect())
        .filter((r) => r.left < g.right && r.right > g.left && r.top < g.bottom && r.bottom > g.top).map(() => pl);
    }, place));
  }
  ok(hiddenMarks.length === 0, `${tag}: the drag symbol never covers a height mark's label`, hiddenMarks.join(', '));

  // A PLACE'S COLOUR is its loudest figure's 5 dB band, rounded DOWN, as the slider and the key round (the Blender
  // session's preflight, 2026-10-26: Hounslow, 57-63 dB, showed "65 dB and up"). Read off the page: each card's range,
  // the key's colours, the card's chip, and the readout's chip once the plane is over Hounslow.
  const colours = await page.evaluate(() => {
    const key = {};
    document.querySelectorAll('.approach .scale-key b').forEach((b) => {
      const n = parseInt(b.textContent, 10);
      if (!Number.isNaN(n)) key[n] = b.style.getPropertyValue('--c').trim().toLowerCase();
    });
    const cards = [...document.querySelectorAll('.approach .card')].map((c) => {
      const m = c.textContent.match(/(\d+)–(\d+) dB/);
      return m && { name: c.querySelector('b').textContent, want: key[Math.min(65, 5 * Math.floor(+m[2] / 5))],
        got: c.style.getPropertyValue('--chip').trim().toLowerCase() };
    }).filter(Boolean);
    return { key, cards };
  });
  const wrongCards = colours.cards.filter((c) => c.got !== c.want);
  ok(colours.cards.length >= 3 && wrongCards.length === 0, `${tag}: each place's colour is its loudest figure's band, rounded down`,
    JSON.stringify(wrongCards));
  await page.locator('.approach .jump[data-place="hounslow"]').click();
  await page.waitForTimeout(1100);
  const belowChip = await page.evaluate(() => document.querySelector('.approach .readout .below').style.getPropertyValue('--chip').trim().toLowerCase());
  const hounslowCard = colours.cards.find((c) => c.name === 'Hounslow');
  ok(belowChip === hounslowCard?.want, `${tag}: "Below: Hounslow" carries the same colour`, `${belowChip} vs ${hounslowCard?.want}`);

  // A CONTOUR LABEL BOUNCES IN PLACE as the plane crosses it (the same preflight: ".approach .boing" also matched the
  // SVG labels, its transform replaced their translate(), and for ~0.45 s they flew to the strip's top-left). Measured
  // against the track, so the camera following the plane does not count: Kew -> Hounslow crosses the 60 dB line.
  if (motion !== 'reduce') {
    await page.locator('.approach .jump[data-place="kew-gardens"]').click();
    await page.waitForTimeout(1100);
    const drift = await page.evaluate(() => new Promise((res) => {
      const labels = [...document.querySelectorAll('.approach .contours .lbl')];
      const lbl = labels.find((l) => +l.dataset.s > 5098 && +l.dataset.s < 9787);
      const track = document.querySelector('.approach .track');
      const rel = () => { const a = lbl.getBoundingClientRect(), t = track.getBoundingClientRect(); return [a.left - t.left, a.top - t.top]; };
      const start = rel(), seen = [];
      document.querySelector('.approach .jump[data-place="hounslow"]').click();
      const t0 = performance.now();
      (function sample() {
        seen.push(rel());
        if (performance.now() - t0 < 1500) requestAnimationFrame(sample);
        else res({ found: !!lbl, bounced: lbl.classList.contains('boing'),
          worst: Math.max(...seen.map(([x, y]) => Math.hypot(x - start[0], y - start[1]))) });
      })();
    }));
    ok(drift.found && drift.bounced && drift.worst < 20, `${tag}: a contour label bounces in place as the plane crosses it`, JSON.stringify(drift));
  }

  // EASED: a jump of the slider glides there (not one frame), except with reduced motion, where it is at once.
  const eased = await page.evaluate(() => new Promise((res) => {
    const sl = document.getElementById('approach-slider'), pl = document.querySelector('.approach .plane');
    sl.value = String(Math.round(+sl.max / 2 / 50) * 50); sl.dispatchEvent(new Event('input', { bubbles: true }));
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const early = parseFloat(pl.style.left);
      setTimeout(() => res({ early, late: parseFloat(pl.style.left) }), 900);
    }));
  }));
  ok(motion === 'reduce' ? eased.early === eased.late : eased.early !== eased.late,
    `${tag}: a slider jump ${motion === 'reduce' ? 'is at once with reduced motion' : 'glides rather than jumps'}`, JSON.stringify(eased));

  await page.locator('.approach .jump[data-place="hounslow"]').focus();
  await page.keyboard.press('Enter');
  await page.waitForTimeout(motion === 'reduce' ? 150 : 1100);
  const hounslow = await at();
  ok(/Hounslow/.test(hounslow.below) && /Hounslow/.test(hounslow.text), `${tag}: "Go to Hounslow" puts the plane over Hounslow`, JSON.stringify(hounslow));
  // Every "Go to" place: the plane is where the reader was sent, so no card may sit over it (at Hounslow one did).
  const covered = [];
  for (const place of ['westminster', 'battersea', 'kew-gardens', 'hounslow', 'heathrow']) {
    await page.locator(`.approach .jump[data-place="${place}"]`).click();
    await settle();
    const b = await boxes();
    for (const c of b.cards) {
      if (c.l < b.plane.r && c.r > b.plane.l && c.t < b.plane.b && c.b > b.plane.t) covered.push(`${place}: ${c.name}`);
    }
  }
  ok(covered.length === 0, `${tag}: at every "Go to" place, no card covers the plane`, covered.join(', '));

  if (motion !== 'reduce') {
    const anim = await page.evaluate(() => document.getAnimations().length);
    ok(anim >= 0, `${tag}: animations run (${anim})`);
  } else {
    const running = await page.evaluate(() => document.getAnimations().filter((a) => a.playState === 'running'
      && a.effect?.target?.closest?.('.approach')).length);
    ok(running === 0, `${tag}: nothing in the strip animates`, `${running} running`);
  }
  ok(tiles.size > onArrival, `${tag}: moving the plane fetches more tiles as they come into view (${onArrival} then ${tiles.size})`);
  ok(errors.length === 0, `${tag}: no page errors`, errors.join(' | '));
  await page.close();
}
// /how-it-works with no slash is served the same page (200, no redirect, checked live 2026-10-26), where a relative
// "img/strip_v7/..." would resolve to /img/strip_v7/ and every picture would 404: the paths must be absolute.
{
  const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
  await page.route('**/js/count.mjs', (r) => r.fulfill({ status: 200, contentType: 'application/javascript', body: '' }));
  const pictures = [];
  page.on('response', (r) => { if (/strip_v7\//.test(r.url())) pictures.push([new URL(r.url()).pathname, r.status()]); });
  await page.goto(URL_.replace(/\/$/, ''), { waitUntil: 'load' });
  await page.waitForTimeout(400);
  ok(pictures.length > 0 && pictures.every(([p, s]) => p.startsWith('/how-it-works/img/strip_v7/') && s === 200),
    'at /how-it-works (no slash) every picture still loads from /how-it-works/img/', JSON.stringify(pictures.filter(([, s]) => s !== 200).slice(0, 3)));
  await page.close();
}
// ...and in the SOURCE, every one of them: a browser with AVIF never asks for the WebP fallbacks, so the load above
// cannot see a relative one (proven: a relative strip_real_07.webp passed it), but a browser without AVIF would.
{
  const html = await readFile(join(ROOT, 'how-it-works', 'index.html'), 'utf8');
  const paths = [...html.matchAll(/\s(?:src|srcset|data-src|data-srcset)="([^"]*strip_v7[^"]*)"/g)].map((m) => m[1]);
  const relative = paths.filter((p) => !p.startsWith('/how-it-works/img/strip_v7/'));
  ok(paths.length === 54 && relative.length === 0, `all ${paths.length} picture paths in the page are absolute`, relative.slice(0, 3).join(', '));
}
ok(missing.filter((p) => !p.endsWith('favicon.ico')).length === 0, 'nothing the page asked for was missing', missing.join(', '));
await browser.close();
server.close();
console.log(`\n${failures ? 'FAIL' : 'PASS'}: ${checks - failures} of ${checks} checks`);
process.exit(failures ? 1 : 0);
