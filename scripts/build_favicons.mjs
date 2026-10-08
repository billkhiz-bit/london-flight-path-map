// Renders the two raster icons a browser asks for, from the two SVGs that are
// the source of truth:
//
//   favicon.ico                  <- icons/favicon.svg at 16, 32 and 48 px
//   icons/apple-touch-icon.png   <- icons/icon.svg at 180 px on solid ground
//
// favicon.ico is what every browser requests from the site root whatever a
// page declares, so without it each page view logs a 404. The apple-touch
// icon must be a PNG: iOS ignores an SVG there, which is what the map page
// used to point at. It is drawn on the icon's own edge colour because iOS
// fills transparency with black, and it rounds the corners itself.
//
// There is no --check. Chromium's rasteriser is not byte-stable across
// versions, so comparing a re-render with the committed file would go red on
// a browser update with nothing changed. tests/test_favicons.py checks what
// can be checked: the files exist at the right sizes and every page links them.
//
// Usage: node scripts/build_favicons.mjs [repoRoot]
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { join, resolve } from 'node:path';

const root = resolve(process.argv[2] || '.');
const require = createRequire(join(process.cwd(), 'package.json')); // run from the repo root
const { chromium } = require('playwright');

const ICO_SIZES = [16, 32, 48];
const TOUCH_SIZE = 180;
const TOUCH_GROUND = '#070b16'; // the outer stop of icons/icon.svg's background gradient

const dataUri = (path) => 'data:image/svg+xml;base64,' + readFileSync(path).toString('base64');

async function render(page, src, size, ground) {
  await page.setViewportSize({ width: size, height: size });
  await page.setContent(
    `<body style="margin:0;background:${ground || 'transparent'}">` +
      `<img src="${src}" width="${size}" height="${size}" style="display:block"></body>`,
  );
  await page.waitForFunction(() => document.images[0].complete);
  return page.screenshot({ omitBackground: !ground, clip: { x: 0, y: 0, width: size, height: size } });
}

// An ICO whose entries are PNGs (supported by every browser since IE 9):
// a 6-byte header, a 16-byte directory entry per image, then the PNGs.
function packIco(pngs) {
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0); // reserved
  header.writeUInt16LE(1, 2); // type: icon
  header.writeUInt16LE(pngs.length, 4);
  let offset = 6 + 16 * pngs.length;
  const entries = pngs.map(({ size, data }) => {
    const e = Buffer.alloc(16);
    e.writeUInt8(size >= 256 ? 0 : size, 0); // width (0 means 256)
    e.writeUInt8(size >= 256 ? 0 : size, 1); // height
    e.writeUInt8(0, 2); // palette colours
    e.writeUInt8(0, 3); // reserved
    e.writeUInt16LE(1, 4); // colour planes
    e.writeUInt16LE(32, 6); // bits per pixel
    e.writeUInt32LE(data.length, 8);
    e.writeUInt32LE(offset, 12);
    offset += data.length;
    return e;
  });
  return Buffer.concat([header, ...entries, ...pngs.map((p) => p.data)]);
}

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ deviceScaleFactor: 1 });

  const favicon = dataUri(join(root, 'icons/favicon.svg'));
  const pngs = [];
  for (const size of ICO_SIZES) pngs.push({ size, data: await render(page, favicon, size) });
  writeFileSync(join(root, 'favicon.ico'), packIco(pngs));

  const icon = dataUri(join(root, 'icons/icon.svg'));
  writeFileSync(join(root, 'icons/apple-touch-icon.png'), await render(page, icon, TOUCH_SIZE, TOUCH_GROUND));

  console.log(`favicon.ico (${ICO_SIZES.join(', ')} px) and icons/apple-touch-icon.png (${TOUCH_SIZE} px) written`);
} finally {
  await browser.close();
}
