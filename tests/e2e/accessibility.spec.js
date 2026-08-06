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
  { path: '/terms', name: 'terms of use' },
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

  // Every scan above is of a page that has just loaded and been left alone, so
  // this suite could only ever see the initial DOM. The result panel — where the
  // scores, the badges and the verdict live, i.e. the entire reason someone
  // visits — is rendered by a search and was therefore never scanned at all.
  // A gate that inspects one keystroke short of the product is the same shape as
  // the two gates this repo has already been burned by.
  test('WCAG 2.1 AA scan: result panel after a postcode search', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('#app', { state: 'visible', timeout: 30_000 });

    const input = page.locator('#search-input');
    await input.fill('SW11 1AA');
    await input.press('Enter');

    // Wait for the RESULT, not for the absence of the loading state. Asserting
    // "title is not SEARCHING" passes instantly, before the search has even
    // started, and then races the render — a green wait that guarantees nothing,
    // which is the failure mode this whole test exists to close.
    await expect(page.locator('#sidebar-title')).toHaveText(/SW11/i, { timeout: 30_000 });
    await expect(page.locator('.score-row').first()).toBeVisible({ timeout: 30_000 });

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    if (results.violations.length > 0) {
      console.log(`\n--- result panel: ${results.violations.length} violation(s) ---`);
      for (const violation of results.violations) {
        console.log(`[${violation.impact?.toUpperCase()}] ${violation.id}: ${violation.description}`);
        for (const node of violation.nodes.slice(0, 5)) {
          console.log(`  - ${node.target.join(' > ')}`);
        }
        if (violation.nodes.length > 5) {
          console.log(`  ... and ${violation.nodes.length - 5} more`);
        }
      }
      console.log('');
    }

    const blocking = results.violations.filter(
      (v) => v.impact === 'critical' || v.impact === 'serious'
    );
    expect(
      blocking,
      `result panel: ${blocking.length} critical/serious violation(s):\n` +
        blocking.map((v) => `  [${v.impact.toUpperCase()}] ${v.id}: ${v.description}`).join('\n')
    ).toHaveLength(0);
  });

  // WCAG 2.1.1. Until 2026-08-03 the ranking table's 128 rows and every saved
  // postcode bound `click` alone with cursor:pointer, so a keyboard, switch or
  // voice user could not activate any of them. axe does not catch this: a <tr>
  // with a click listener and no role looks inert to it, which is precisely why
  // it needs an explicit behavioural test rather than another rule scan.
  test('ranking rows are operable by keyboard alone', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('#app', { state: 'visible', timeout: 30_000 });
    await page.evaluate(() => switchTab('ranking'));
    const rows = page.locator('#borough-ranking tbody tr[data-rank-name]');
    await expect(rows.first()).toBeVisible({ timeout: 30_000 });

    // Every row must be reachable and labelled.
    const audit = await page.evaluate(() => {
      const rs = [...document.querySelectorAll('#borough-ranking tbody tr[data-rank-name]')];
      return {
        total: rs.length,
        missingTabindex: rs.filter((r) => r.getAttribute('tabindex') !== '0').length,
        missingLabel: rs.filter((r) => !r.getAttribute('aria-label')).length,
        // role=button on a <tr> would strip the cells from the a11y tree.
        withButtonRole: rs.filter((r) => r.getAttribute('role') === 'button').length,
      };
    });
    expect(audit.total).toBeGreaterThan(0);
    expect(audit.missingTabindex, `${audit.missingTabindex} rows are not focusable`).toBe(0);
    expect(audit.missingLabel, `${audit.missingLabel} rows have no accessible name`).toBe(0);
    expect(
      audit.withButtonRole,
      'role=button on a table row removes the cells from the accessibility tree'
    ).toBe(0);

    // And activation must actually work with no pointer involved.
    const before = (await page.locator('#sidebar-title').textContent())?.trim();
    await page.evaluate(() =>
      document.querySelectorAll('#borough-ranking tbody tr[data-rank-name]')[2].focus()
    );
    await page.keyboard.press('Enter');
    await expect(page.locator('#sidebar-title')).not.toHaveText(before || '', { timeout: 30_000 });
  });
});
