import { test, expect } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';

const LIVE_KEYS = ['price', 'change_pct', 'gap_percent', 'volume'] as const;

async function columnLefts(page: import('@playwright/test').Page) {
  return page.evaluate((keys) => {
    const out: Record<string, number> = {};
    for (const key of keys) {
      const th = document.querySelector(`thead th[data-col="${key}"]`);
      if (th) out[key] = Math.round(th.getBoundingClientRect().left);
    }
    return out;
  }, [...LIVE_KEYS]);
}

test.describe('scanner column width stability', () => {
  test('Gainers CHANGE/GAP ticks do not shift sibling columns', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample');
    await expect(page.getByTestId('scanner-nav-gainers')).toBeVisible();
    await page.getByTestId('scanner-nav-gainers').click();
    await expect(page.locator('.table-wrapper--scanner table')).toBeVisible();
    await expect(page.locator('td[data-col="change_pct"]').first()).toBeVisible();
    await expect(page.locator('th[data-col="change_pct"]')).toHaveClass(/scanner-col--pct/);
    await expect(page.locator('td[data-col="gap_percent"]').first()).toHaveClass(/scanner-col--pct/);

    const layout = await page.locator('.table-wrapper--scanner table').evaluate((table) => (
      getComputedStyle(table).tableLayout
    ));
    expect(layout).toBe('fixed');

    const before = await columnLefts(page);
    expect(before.gap_percent).toBeGreaterThan(0);
    expect(before.volume).toBeGreaterThan(before.gap_percent);

    await page.evaluate(() => {
      document.querySelectorAll('td[data-col="change_pct"] .cell-stack-primary').forEach((el) => {
        el.textContent = '+9.99%';
      });
      document.querySelectorAll('td[data-col="gap_percent"] span').forEach((el) => {
        el.textContent = '+1.00%';
      });
    });
    const mid = await columnLefts(page);

    await page.evaluate(() => {
      document.querySelectorAll('td[data-col="change_pct"] .cell-stack-primary').forEach((el) => {
        el.textContent = '+215.52%';
      });
      document.querySelectorAll('td[data-col="gap_percent"] span').forEach((el) => {
        el.textContent = '+220.82%';
      });
    });
    const after = await columnLefts(page);

    expect(mid).toEqual(before);
    expect(after).toEqual(before);
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
