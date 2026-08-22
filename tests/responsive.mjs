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

const RAW_TARGET = process.argv[2] || 'https://d1oe4ftwutjpf.cloudfront.net/';

// EVERY PUBLIC PAGE, not just the homepage (2026-08-22, audit finding I8).
//
// This file audited ONE url for its whole life. The homepage is the hardest
// page to get right and the obvious thing to check, so the gap never showed -
// but it meant the legal and funnel pages had never been measured at any
// width. BOTH pages carrying a <table> were broken when this was widened:
// privacy.html overflowed 149px at 320, and changes.html scrolled the WINDOW
// 402px sideways at five viewports. A legal notice that drifts off-screen is
// the worst page to have left unchecked.
//
// The base may be CloudFront (which rewrites `/privacy` to `privacy/index.html`)
// or a plain local file server (where only `privacy.html` exists), so each path
// is RESOLVED against the target rather than assumed. A page that resolves to
// neither form is a FAILURE, not a skip - a silently dropped page is how this
// check came to cover one url in the first place.
const BASE = RAW_TARGET.replace(/\/(index\.html)?$/, '');

const PAGES = [
  { name: 'consumer app', slug: 'index', full: true, settle: 2500 },
  { name: 'pricing', slug: 'pricing' },
  { name: 'privacy', slug: 'privacy' },
  { name: 'terms of use', slug: 'terms' },
  { name: 'what changed', slug: 'changes', settle: 2500 },
  { name: 'API landing', slug: 'api/index' },
  { name: 'score demo', slug: 'score-demo/index' },
  { name: 'status page', slug: 'score-demo/status' },
];

async function resolvePage(slug) {
  const bare = slug.replace(/\/?index$/, '');
  const candidates = slug.endsWith('index')
    ? [`${bare}/`, `${bare}/index.html`]
    : [`/${slug}`, `/${slug}.html`];
  for (const c of candidates) {
    const url = BASE + (c.startsWith('/') ? c : `/${c}`);
    try {
      const res = await fetch(url, { redirect: 'follow' });
      if (res.ok) return url;
    } catch {
      /* try the next form */
    }
  }
  return null;
}

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

// The homepage gets all ten. The static pages get the narrow end only: they
// carry no responsive JavaScript, overflow is a pure CSS question, and the
// phone widths are where it bites. Eight more pages x ten viewports would
// roughly quadruple a blocking stage to re-measure widths that cannot differ.
const NARROW = VIEWPORTS.filter((v) => v.w <= 480);

const results = [];

const browser = await chromium.launch();

const unresolved = [];
for (const meta of PAGES) {
  const url = await resolvePage(meta.slug);
  if (!url) {
    unresolved.push(meta);
    continue;
  }
  for (const vp of meta.full ? VIEWPORTS : NARROW) {
  const page = await browser.newPage({ viewport: { width: vp.w, height: vp.h } });
  const consoleErrors = [];
  page.on('pageerror', (e) => consoleErrors.push(e.message));

  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 45000 });
  } catch {
    // networkidle can never settle on a page with polling or long-lived
    // connections. Fall back rather than reporting a layout failure for what is
    // really a loading-strategy mismatch.
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
  }
  await page.waitForTimeout(meta.settle ?? 600);

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

    // UNREACHABLE CONTROLS. Added 2026-08-11, and the reason is that this file
    // computed `wide` above and only ever PRINTED it when the page itself
    // scrolled sideways — so anything clipped by an `overflow: hidden` ancestor
    // was invisible to the audit by construction.
    //
    // That is not hypothetical. The city switcher grew from three chips to
    // eight and became a 453px row inside the map container, which hides its
    // overflow. The page never scrolled, this audit read "ok" at all ten
    // viewports, and three of eight UK cities could not be tapped at 320px.
    //
    // A control past the edge is only a DEFECT if nothing can bring it back.
    // A horizontal scroll strip legitimately parks its later items off-screen,
    // so walk up for an ancestor that actually scrolls on x. That distinction
    // is what keeps this check honest in both directions: it fails on the bug
    // it was written for, and passes the scroll strip that fixed it.
    const scrollableOnX = (node) => {
      for (let el = node.parentElement; el && el !== document.body; el = el.parentElement) {
        const s = getComputedStyle(el);
        if (
          (s.overflowX === 'auto' || s.overflowX === 'scroll') &&
          el.scrollWidth > el.clientWidth + 1
        ) {
          return true;
        }
      }
      return false;
    };

    const unreachable = [];
    for (const node of document.querySelectorAll(
      'button, a[href], input, select, [role="button"]'
    )) {
      const r = node.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      const s = getComputedStyle(node);
      if (s.visibility === 'hidden' || s.display === 'none') continue;
      if (r.right <= doc.clientWidth + 1 && r.left >= -1) continue;
      if (scrollableOnX(node)) continue;
      unreachable.push({
        tag: node.tagName.toLowerCase(),
        cls: (node.className || '').toString().slice(0, 34),
        text: (node.textContent || '').trim().slice(0, 24),
        left: Math.round(r.left),
        right: Math.round(r.right),
      });
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
      unreachable: unreachable.slice(0, 8),
      unreachableCount: unreachable.length,
      smallTargets: small.slice(0, 5),
      smallCount: small.length,
      bodyFontPx: parseFloat(getComputedStyle(document.body).fontSize),
    };
  });

  results.push({ meta, vp, audit, consoleErrors });
  await page.close();
  }
}

await browser.close();

console.log(`\nResponsive audit: ${BASE || RAW_TARGET}\n`);

let failures = 0;
// A page whose url resolved to nothing is a hard failure. Skipping it would
// quietly recreate the single-page coverage this widening removed.
for (const meta of unresolved) {
  console.log(`UNRESOLVED    ${meta.name} (${meta.slug}) - no url served at either form`);
  failures += 1;
}
let lastPage = null;
for (const { meta, vp, audit, consoleErrors } of results) {
  if (meta.name !== lastPage) {
    console.log(`${lastPage ? '\n' : ''}# ${meta.name}`);
    lastPage = meta.name;
  }
  const overflow = audit.overflowBy > 1;
  const stranded = audit.unreachableCount > 0;
  const flag = overflow ? 'OVERFLOW' : stranded ? 'STRANDED' : 'ok      ';
  if (overflow || stranded) failures += 1;

  console.log(
    `${flag} ${String(vp.w).padStart(4)}x${String(vp.h).padEnd(5)} ${vp.name}`
  );
  if (stranded) {
    console.log(
      `         ${audit.unreachableCount} control(s) past the viewport edge with no way to scroll to them:`
    );
    for (const u of audit.unreachable) {
      console.log(`           <${u.tag} class="${u.cls}"> "${u.text}" ${u.left}..${u.right}`);
    }
  }
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
    ? `\nNo horizontal overflow and no stranded controls: ${results.length} page/viewport ` +
      `combinations across ${PAGES.length} pages.`
    : `\n${failures} of ${results.length} page/viewport combinations overflow horizontally, ` +
      `strand a control, or could not be reached.`
);
process.exit(failures === 0 ? 0 : 1);
