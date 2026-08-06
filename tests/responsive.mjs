// Responsive audit of the live site across the viewports real visitors use.
//
// WHY IT CHECKS WHAT IT CHECKS. Horizontal overflow is the failure that matters
// most on a phone and the one least likely to be noticed on a desktop: the page
// still works, it just drifts sideways, and nobody testing at 1440px will ever
// see it. Everything else here is secondary to that.
//
// It runs against the DEPLOYED site rather than a local file, because the whole
// question is what visitors get. That also means a failure can be a deploy
// problem rather than a source problem — check `deployed == source` before
// hunting in index.html.
//
//   node tests/responsive.mjs
//   node tests/responsive.mjs http://localhost:8000   (override the target)

import { chromium } from '@playwright/test';

const TARGET = process.argv[2] || 'https://d1oe4ftwutjpf.cloudfront.net/';

// Breakpoints chosen from what the codebase already commits to: index.html
// switches to the desktop two-column grid at 901px, and the prototype declares
// breaks at 768 and 480. 320 is the narrowest phone still in meaningful use.
const VIEWPORTS = [
  { w: 320, h: 568, name: 'iPhone SE (smallest in use)' },
  { w: 375, h: 667, name: 'iPhone 8 / SE2' },
  { w: 390, h: 844, name: 'iPhone 14' },
  { w: 414, h: 896, name: 'iPhone 11 Pro Max' },
  { w: 480, h: 800, name: 'prototype breakpoint' },
  { w: 768, h: 1024, name: 'iPad portrait' },
  { w: 900, h: 800, name: 'just below desktop grid' },
  { w: 901, h: 800, name: 'just above desktop grid' },
  { w: 1280, h: 800, name: 'laptop' },
  { w: 1920, h: 1080, name: 'desktop' },
];

const results = [];

const browser = await chromium.launch();

for (const vp of VIEWPORTS) {
  const page = await browser.newPage({ viewport: { width: vp.w, height: vp.h } });
  const consoleErrors = [];
  page.on('pageerror', (e) => consoleErrors.push(e.message));

  try {
    await page.goto(TARGET, { waitUntil: 'networkidle', timeout: 45000 });
  } catch {
    // networkidle can never settle on a page with polling or long-lived
    // connections. Fall back rather than reporting a layout failure for what is
    // really a loading-strategy mismatch.
    await page.goto(TARGET, { waitUntil: 'domcontentloaded', timeout: 45000 });
  }
  await page.waitForTimeout(2500);

  const audit = await page.evaluate(() => {
    const doc = document.documentElement;
    const overflowBy = doc.scrollWidth - doc.clientWidth;

    // Name the specific offenders. "The page overflows" is not actionable;
    // "this element is 40px wider than the viewport" is.
    const wide = [];
    for (const node of document.querySelectorAll('body *')) {
      const r = node.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      const style = getComputedStyle(node);
      if (style.position === 'fixed' || style.visibility === 'hidden') continue;
      if (r.right > doc.clientWidth + 1 || r.left < -1) {
        wide.push({
          tag: node.tagName.toLowerCase(),
          cls: (node.className || '').toString().slice(0, 40),
          right: Math.round(r.right),
          left: Math.round(r.left),
        });
      }
    }

    // Tap targets. WCAG 2.5.8 asks for 24x24 CSS px minimum; below that a
    // control is genuinely hard to hit on a touchscreen.
    //
    // THE INLINE EXCEPTION IS APPLIED, and applying it is the difference
    // between a useful check and one nobody reads. WCAG 2.5.8 exempts a target
    // that is "in a sentence or its size is otherwise constrained by the
    // line-height of non-target text" — footer links, links inside a paragraph.
    // Without this the audit reported eleven exempt links beside one real
    // defect, and a list that is mostly noise trains you to skim past the item
    // that matters.
    const isInlineInText = (node) => {
      if (node.tagName !== 'A') return false;
      if (getComputedStyle(node).display !== 'inline') return false;
      // A link with non-link text beside it is in prose; one sitting alone in
      // its parent is a standalone control that merely looks inline.
      const parentText = (node.parentElement?.textContent || '').trim();
      const ownText = (node.textContent || '').trim();
      return parentText.length > ownText.length;
    };

    const small = [];
    for (const node of document.querySelectorAll('button, a, input, select, [role="button"]')) {
      const r = node.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      if (isInlineInText(node)) continue;
      if (r.width < 24 || r.height < 24) {
        small.push({
          tag: node.tagName.toLowerCase(),
          text: (node.textContent || '').trim().slice(0, 24),
          size: `${Math.round(r.width)}x${Math.round(r.height)}`,
        });
      }
    }

    return {
      overflowBy,
      offenders: wide.slice(0, 5),
      offenderCount: wide.length,
      smallTargets: small.slice(0, 5),
      smallCount: small.length,
      bodyFontPx: parseFloat(getComputedStyle(document.body).fontSize),
    };
  });

  results.push({ vp, audit, consoleErrors });
  await page.close();
}

await browser.close();

console.log(`\nResponsive audit: ${TARGET}\n`);

let failures = 0;
for (const { vp, audit, consoleErrors } of results) {
  const overflow = audit.overflowBy > 1;
  const flag = overflow ? 'OVERFLOW' : 'ok      ';
  if (overflow) failures += 1;

  console.log(
    `${flag} ${String(vp.w).padStart(4)}x${String(vp.h).padEnd(5)} ${vp.name}`
  );
  if (overflow) {
    console.log(`         page is ${audit.overflowBy}px wider than the viewport`);
    for (const o of audit.offenders) {
      console.log(`         <${o.tag} class="${o.cls}"> spans ${o.left}..${o.right}`);
    }
    if (audit.offenderCount > audit.offenders.length) {
      console.log(`         ...and ${audit.offenderCount - audit.offenders.length} more`);
    }
  }
  if (audit.smallCount) {
    console.log(`         ${audit.smallCount} tap target(s) under 24x24:`);
    for (const t of audit.smallTargets) {
      console.log(`           <${t.tag}> "${t.text}" ${t.size}`);
    }
  }
  if (consoleErrors.length) {
    console.log(`         ${consoleErrors.length} page error(s): ${consoleErrors[0].slice(0, 90)}`);
  }
}

console.log(
  failures === 0
    ? `\nNo horizontal overflow at any of ${VIEWPORTS.length} viewports.`
    : `\n${failures} of ${VIEWPORTS.length} viewports overflow horizontally.`
);
process.exit(failures === 0 ? 0 : 1);
