import { test, expect } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';

test.describe('Phase 0 baseline', () => {
  test('app loads', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/');
    await expect(page.getByTestId('scanner-side-nav')).toBeVisible();
    await expect(page.getByTestId('scanner-nav-gappers')).toBeVisible();
    await expect(page.getByTestId('scanner-nav-gappers')).toHaveClass(/is-active/);
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('tabs switch', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/');
    const gainers = page.getByTestId('scanner-nav-gainers');
    await gainers.click();
    await expect(gainers).toHaveClass(/is-active/);

    const account = page.getByTestId('global-bar-account-nav');
    await account.click();
    await expect(account).toHaveClass(/active/);
    await expect(page.getByRole('region', { name: 'Account' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Reports' })).toBeVisible();
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('Trader window opens via URL and has no page scroll', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample&symbol=SMPL');

    await expect(page.getByRole('main')).toBeVisible();
    await expect(page.getByTestId('stock-view-header')).toHaveCount(0);
    await expect(page.getByTestId('header-market-clock')).toBeVisible();
    await expect(page.getByText('Trader', { exact: true })).toBeVisible();
    await expect(page).toHaveTitle(/SMPL.*Trader/);

    const noPageScroll = await page.evaluate(() => {
      const el = document.documentElement;
      return el.scrollHeight === el.clientHeight;
    });
    expect(noPageScroll, 'documentElement must not page-scroll on Trader').toBe(true);

    // Terminal composition: charts + rail (when detail loads)
    await expect(page.getByRole('complementary', { name: 'Trader' })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Multi-timeframe charts' })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Trade order' })).toBeVisible();

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});

