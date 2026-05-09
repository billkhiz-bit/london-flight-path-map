#!/usr/bin/env node
// Assembles the Capacitor `www/` directory from the parent Sky Score
// web project. Run via `npm run build:web` before `npx cap sync`.
//
// We deliberately don't symlink — Capacitor's WebView treats `www/` as
// a self-contained bundle, and symlinks confuse Codemagic's cloud
// build environment.
//
// Files copied:
//   ../index.html       → www/index.html       (main app shell)
//   ../manifest.webmanifest → www/manifest.webmanifest
//   ../sw.js            → www/sw.js            (service worker)
//   ../icons/*          → www/icons/*
//   ../js/*             → www/js/*             (api-base.js, future shared JS)
//   ../prototype/*      → www/prototype/*      (3D radar, kept in scope)
//   ../data/*.png       → www/data/            (DEFRA noise tiles bundled
//                                               so the app launches even
//                                               without network)
//
// Files NOT copied: backend/, score-demo/, node_modules/, tests/,
// docs (README, METHODOLOGY, etc.) — none of these belong inside the
// shipped app bundle.

import { mkdir, copyFile, readdir, stat, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..', '..');
const WWW = resolve(__dirname, '..', 'www');

async function copyDir(src, dst, filter = () => true) {
  await mkdir(dst, { recursive: true });
  const entries = await readdir(src, { withFileTypes: true });
  for (const e of entries) {
    const s = join(src, e.name);
    const d = join(dst, e.name);
    if (!filter(e.name)) continue;
    if (e.isDirectory()) {
      await copyDir(s, d, filter);
    } else if (e.isFile()) {
      await copyFile(s, d);
    }
  }
}

async function main() {
  // Clean www/ each run so deletes in the source propagate (otherwise
  // a renamed/removed file would linger in the bundle forever).
  if (existsSync(WWW)) {
    await rm(WWW, { recursive: true, force: true });
  }
  await mkdir(WWW, { recursive: true });

  // Top-level shell files.
  for (const f of ['index.html', 'manifest.webmanifest', 'sw.js']) {
    const src = join(ROOT, f);
    if (existsSync(src)) {
      await copyFile(src, join(WWW, f));
      console.log(`  copy ${f}`);
    } else {
      console.warn(`  MISSING ${f}`);
    }
  }

  // Asset directories.
  if (existsSync(join(ROOT, 'icons'))) {
    await copyDir(join(ROOT, 'icons'), join(WWW, 'icons'));
    console.log('  copy icons/');
  }
  if (existsSync(join(ROOT, 'js'))) {
    await copyDir(join(ROOT, 'js'), join(WWW, 'js'));
    console.log('  copy js/');
  }
  if (existsSync(join(ROOT, 'prototype'))) {
    await copyDir(join(ROOT, 'prototype'), join(WWW, 'prototype'));
    console.log('  copy prototype/');
  }

  // DEFRA noise tile (PNGs only — skip the 782 MB raw NSPL CSV).
  if (existsSync(join(ROOT, 'data'))) {
    await copyDir(join(ROOT, 'data'), join(WWW, 'data'), (n) => n.endsWith('.png'));
    console.log('  copy data/*.png');
  }

  console.log(`done → ${WWW}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
