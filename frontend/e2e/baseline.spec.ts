import { test, expect } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';

test.describe('Phase 0 baseline', () => {
  test('app loads', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/');
    await expect(page.getByTestId('nav-rail')).toBeVisible();
    await expect(page.getByTestId('nav-rail-tab-gappers')).toBeVisible();
    await expect(page.getByTestId('nav-rail-tab-gappers')).toHaveClass(/is-active/);
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('tabs switch', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/');
    const gainers = page.getByTestId('nav-rail-tab-gainers');
    await gainers.click();
    await expect(gainers).toHaveClass(/is-active/);

    const account = page.getByTestId('nav-rail-account');
    await account.click();
    await expect(account).toHaveClass(/active/);
    // The page is the region named exactly "Account"; "Account Details" is a panel inside it.
    await expect(page.getByRole('region', { name: 'Account', exact: true })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Reports' })).toBeVisible();
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('Trader window opens via URL and has no page scroll', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample&symbol=SMPL');

    await expect(page.getByRole('main')).toBeVisible();
    await expect(page.getByTestId('stock-view-header')).toHaveCount(0);
    // The header's ET clock leaves at 1400px and below so the search is never
    // covered (styles/global-app-bar-responsive.css, QA V8); this viewport is 1280.
    const clock = page.getByTestId('header-market-clock');
    await expect(clock).toHaveCount(1);
    await expect(clock).toBeHidden();
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

    // Wide enough for the header to keep its clock.
    await page.setViewportSize({ width: 1600, height: 900 });
    await expect(clock).toBeVisible();

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});

