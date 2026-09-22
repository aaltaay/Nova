import { test, expect } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';

test.describe('Large Cap shared News and Earnings columns', () => {
  test('sample Large Cap shows Gainers News flame and Earnings dots', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample');
    await expect(page.getByTestId('sample-dashboard')).toBeVisible();
    await page.getByTestId('nav-rail-tab-large_cap').click();

    const table = page.locator('main.panel table');
    await expect(table).toBeVisible();
    const headers = table.locator('thead th');
    await expect(headers.filter({ hasText: /^News/ })).toHaveCount(1);
    await expect(headers.filter({ hasText: /^Earnings/ })).toHaveCount(1);
    await expect(headers.filter({ hasText: /^Days/ })).toHaveCount(1);
    await expect(table.getByText('GOOGL', { exact: true })).toBeVisible();
    await expect(table.locator('.news-flame').first()).toBeVisible();
    await expect(table.locator('.earnings-dots').first()).toBeVisible();

    await page.screenshot({
      path: '/opt/cursor/artifacts/large-cap-news-earnings.png',
      fullPage: true,
    });
    await table.screenshot({
      path: '/opt/cursor/artifacts/large-cap-news-earnings-table.png',
    });
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
