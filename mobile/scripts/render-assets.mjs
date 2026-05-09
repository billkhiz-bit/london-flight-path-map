#!/usr/bin/env node
// Renders the SVG asset sources in mobile/assets/ to high-res PNGs so
// capacitor-assets can consume them. capacitor-assets only accepts
// PNG/JPEG inputs (it rasterises and resizes them into the 30+
// platform-specific variants Apple and Google require).
//
// Why Playwright: it's already a project devDependency for the PWA
// smoke test, and it produces pixel-correct SVG renderings via
// chromium's renderer. We could shell out to ImageMagick / Inkscape
// but those aren't installed by default on Codemagic's macOS instance
// either, so Playwright is the most portable option.
//
// Outputs to mobile/assets/*.png:
//   icon.png            (1024×1024, full-bleed)
//   icon-foreground.png (1024×1024, transparent background)
//   icon-background.png (1024×1024, solid dark)
//   splash.png          (2732×2732)
//   splash-dark.png     (2732×2732)

import { chromium } from 'playwright';
import { readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ASSETS = resolve(__dirname, '..', 'assets');

// Each entry: source SVG, output size, transparent background flag.
const RENDER_TASKS = [
  { src: 'icon-source.svg', out: 'icon.png', size: 1024, transparent: false },
  { src: 'icon-foreground.svg', out: 'icon-foreground.png', size: 1024, transparent: true },
  { src: 'icon-background.svg', out: 'icon-background.png', size: 1024, transparent: false },
  { src: 'splash.svg', out: 'splash.png', size: 2732, transparent: false },
  { src: 'splash-dark.svg', out: 'splash-dark.png', size: 2732, transparent: false },
];

async function renderOne(browser, task) {
  const svgPath = resolve(ASSETS, task.src);
  const svg = await readFile(svgPath, 'utf8');
  const html = `<!doctype html><html><head><meta charset="utf-8"><style>
    html,body{margin:0;padding:0;${task.transparent ? 'background:transparent;' : ''}}
    svg{display:block;width:${task.size}px;height:${task.size}px;}
  </style></head><body>${svg}</body></html>`;

  const page = await browser.newPage({
    viewport: { width: task.size, height: task.size },
    deviceScaleFactor: 1,
  });
  await page.setContent(html, { waitUntil: 'load' });
  const buf = await page.screenshot({
    type: 'png',
    omitBackground: task.transparent,
    fullPage: false,
    clip: { x: 0, y: 0, width: task.size, height: task.size },
  });
  await writeFile(resolve(ASSETS, task.out), buf);
  await page.close();
  console.log(`  ${task.src} → ${task.out} (${task.size}×${task.size})`);
}

async function main() {
  const browser = await chromium.launch();
  try {
    for (const t of RENDER_TASKS) await renderOne(browser, t);
  } finally {
    await browser.close();
  }
  console.log('done');
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
