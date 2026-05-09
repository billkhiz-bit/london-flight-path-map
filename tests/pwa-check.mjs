// Quick PWA smoke test. Uses the @playwright/test browser to load the
// page, verify the manifest is reachable + parseable, the SW registers,
// and the install affordance markup is present. Run via:
//   node tests/pwa-check.mjs
import { chromium } from 'playwright';

const URL = 'http://localhost:8765/';

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', (err) => errors.push(`pageerror: ${err.message}`));
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(`console.error: ${msg.text()}`);
  });

  await page.goto(URL, { waitUntil: 'load' });
  // Give the SW a moment to register after window.load.
  await page.waitForTimeout(500);

  const checks = await page.evaluate(async () => {
    const out = {};
    out.manifestLink = document.querySelector('link[rel="manifest"]')?.href || null;
    out.appleTouch = document.querySelector('link[rel="apple-touch-icon"]')?.href || null;
    out.appleCapable = document.querySelector('meta[name="apple-mobile-web-app-capable"]')?.content || null;
    out.appleTitle = document.querySelector('meta[name="apple-mobile-web-app-title"]')?.content || null;
    out.installPrompt = !!document.getElementById('install-prompt');
    out.installChip = !!document.getElementById('install-chip');
    out.iosHint = !!document.getElementById('ios-install-hint');

    if (out.manifestLink) {
      try {
        const r = await fetch(out.manifestLink);
        const m = await r.json();
        out.manifestName = m.name;
        out.manifestScope = m.scope;
        out.manifestStartUrl = m.start_url;
        out.manifestThemeColor = m.theme_color;
        out.manifestIcons = (m.icons || []).length;
        out.manifestStatus = r.status;
        out.manifestType = r.headers.get('content-type');
      } catch (e) {
        out.manifestError = e.message;
      }
    }

    if ('serviceWorker' in navigator) {
      const reg = await navigator.serviceWorker.getRegistration();
      out.swRegistered = !!reg;
      out.swScope = reg?.scope || null;
    } else {
      out.swSupported = false;
    }
    return out;
  });

  console.log(JSON.stringify(checks, null, 2));
  if (errors.length) {
    console.log('\nErrors observed:');
    errors.forEach((e) => console.log('  -', e));
  }
  await browser.close();

  // Pass/fail summary
  const pass =
    checks.manifestLink &&
    checks.manifestName === 'Sky Score' &&
    checks.manifestScope === '/' &&
    checks.manifestIcons >= 2 &&
    checks.swRegistered &&
    checks.installPrompt &&
    checks.appleCapable === 'yes';
  console.log(pass ? '\nPASS' : '\nFAIL');
  process.exit(pass ? 0 : 1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
