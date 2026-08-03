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
//   ../data/<allow-list> → www/data/           (see REQUIRED_DATA below:
//                                               noise tile + the three JSON
//                                               files the app cannot score
//                                               without)
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
      // Fatal, not a warning. A bundle without index.html or sw.js is not a
      // degraded app, it is a broken one, and a warning in a build log is not
      // a control.
      console.error(`  FATAL: missing required shell file ${f}`);
      process.exit(1);
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

  // data/ is an ALLOW-LIST, not an extension filter, and a missing entry is
  // fatal.
  //
  // This was `(n) => n.endsWith('.png')`, written when data/ held nothing but
  // the DEFRA noise tile and the point was to skip the 769 MB NSPL CSV. It still
  // skipped the CSV, and it also silently skipped every JSON file added later:
  // borough-extra.json (crime, schools, transport, healthcare) and both borough
  // boundary files. Capacitor declares no remote server URL, so index.html's
  // fetch of /data/borough-extra.json resolved INSIDE the bundle, 404'd, and was
  // caught into an empty object the code called "non-fatal" - leaving every
  // borough scoring liveability at a flat default in the shipped app, with a
  // console.warn nobody reads on a phone as the only signal.
  //
  // An extension filter fails open: add a file, get no error, ship without it.
  // An allow-list fails closed, and this build now exits non-zero rather than
  // producing a bundle that looks fine and scores wrong.
  const REQUIRED_DATA = [
    'borough-extra.json', // crime/schools/transport/healthcare - liveability
    'london-boroughs.json', // map geometry, precached by sw.js
    'nyc-boroughs.json', // ditto; cache.addAll() is atomic, so a miss kills install
    'aircraft-noise-london-lden.png', // DEFRA overlay
  ];
  const missingData = [];
  await mkdir(join(WWW, 'data'), { recursive: true });
  for (const f of REQUIRED_DATA) {
    const src = join(ROOT, 'data', f);
    if (existsSync(src)) {
      await copyFile(src, join(WWW, 'data', f));
      console.log(`  copy data/${f}`);
    } else {
      missingData.push(f);
    }
  }
  if (missingData.length) {
    console.error(
      `
  FATAL: data/ is missing ${missingData.length} required file(s): ${missingData.join(', ')}`
    );
    console.error('  The app would ship scoring liveability at a flat default. Refusing to build.');
    process.exit(1);
  }

  console.log(`done → ${WWW}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
