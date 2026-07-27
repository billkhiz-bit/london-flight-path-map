import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

// Every public page, not just the homepage.
//
// Until 2026-07-27 this spec scanned `/` alone, which is the page that had
// already had three a11y waves run over it — so it reported a clean sweep
// while the B2B funnel, the pages actually shown to investors and pilot
// prospects, had never been scanned at all. A green a11y check covering one
// eighth of the site is worse than none: it reads as "the site is accessible".
const PAGES = [
  { path: '/', name: 'consumer app', waitFor: '#loading' },
  { path: '/pricing', name: 'pricing' },
  { path: '/privacy', name: 'privacy' },
  { path: '/api/', name: 'API landing' },
  { path: '/changes', name: 'what changed this quarter' },
  { path: '/score-demo/', name: 'score demo' },
  {
    path: '/score-demo/api-docs.html',
    name: 'API reference',
    // Swagger UI 5.17.14 renders each operation summary as a <button> that
    // CONTAINS another button (the deep-link control). That is a genuine
    // upstream a11y defect, not something we can fix without patching the
    // vendored bundle — which the next upgrade would silently overwrite.
    //
    // Scoped to this ONE rule on this ONE page rather than lowering the bar
    // globally, so every other rule here stays enforced. Re-check on the next
    // Swagger UI upgrade and delete this if they have fixed it upstream.
    //
    // Everything else Swagger got wrong WAS fixed, in the page's own <style>
    // and an onComplete hook: the critical unlabelled server <select>, the
    // method-badge contrast, the version badge, and the description links.
    disableRules: ['nested-interactive'],
  },
  { path: '/score-demo/status.html', name: 'status page' },
];

test.describe('Accessibility', () => {
  for (const { path, name, waitFor, disableRules } of PAGES) {
    test(`WCAG 2.1 AA scan: ${name} (${path})`, async ({ page }) => {
      await page.goto(path);
      if (waitFor) {
        await expect(page.locator(waitFor)).toBeHidden({ timeout: 15_000 });
      }

      let builder = new AxeBuilder({ page }).withTags([
        'wcag2a',
        'wcag2aa',
        'wcag21a',
        'wcag21aa',
      ]);
      if (disableRules) {
        builder = builder.disableRules(disableRules);
      }
      const results = await builder.analyze();

      if (results.violations.length > 0) {
        console.log(`\n--- ${path}: ${results.violations.length} violation(s) ---`);
        for (const violation of results.violations) {
          console.log(`[${violation.impact?.toUpperCase()}] ${violation.id}: ${violation.description}`);
          console.log(`  Help: ${violation.helpUrl}`);
          for (const node of violation.nodes.slice(0, 3)) {
            console.log(`  - ${node.target.join(' > ')}`);
          }
          if (violation.nodes.length > 3) {
            console.log(`  ... and ${violation.nodes.length - 3} more`);
          }
        }
        console.log('');
      }

      // Fail on critical AND serious. The original spec failed on critical
      // only, which let a "serious" contrast or name failure sit green
      // indefinitely — and serious is where most real WCAG AA breaches land.
      const blocking = results.violations.filter(
        (v) => v.impact === 'critical' || v.impact === 'serious'
      );
      expect(
        blocking,
        `${path}: ${blocking.length} critical/serious violation(s):\n` +
          blocking.map((v) => `  [${v.impact.toUpperCase()}] ${v.id}: ${v.description}`).join('\n')
      ).toHaveLength(0);
    });
  }
});
