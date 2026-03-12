import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('Accessibility', () => {
  test('WCAG 2.1 AA scan — fail only on critical violations', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('#loading')).toBeHidden({ timeout: 15_000 });

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    // Log all violations with their impact level
    if (results.violations.length > 0) {
      console.log(`\n--- Accessibility violations: ${results.violations.length} ---\n`);
      for (const violation of results.violations) {
        console.log(`[${violation.impact?.toUpperCase()}] ${violation.id}: ${violation.description}`);
        console.log(`  Help: ${violation.helpUrl}`);
        console.log(`  Affected nodes: ${violation.nodes.length}`);
        for (const node of violation.nodes.slice(0, 3)) {
          console.log(`    - ${node.target.join(' > ')}`);
        }
        if (violation.nodes.length > 3) {
          console.log(`    ... and ${violation.nodes.length - 3} more`);
        }
        console.log('');
      }
    } else {
      console.log('\nNo accessibility violations found.\n');
    }

    // Only fail the test on critical-impact violations
    const critical = results.violations.filter(v => v.impact === 'critical');
    expect(
      critical,
      `Found ${critical.length} critical accessibility violation(s):\n` +
        critical.map(v => `  [CRITICAL] ${v.id}: ${v.description}`).join('\n')
    ).toHaveLength(0);
  });
});
