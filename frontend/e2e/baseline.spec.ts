import { test, expect, type ConsoleMessage, type Page } from '@playwright/test';

/** Collect page errors + console.error; ignore benign network noise. */
function attachErrorCollector(page: Page): { errors: string[] } {
  const errors: string[] = [];
  page.on('pageerror', (err) => {
    errors.push(`pageerror: ${err.message}`);
  });
  page.on('console', (msg: ConsoleMessage) => {
    if (msg.type() !== 'error') return;
    const text = msg.text();
    // Vite HMR / failed optional API polls should not fail the happy-path suite.
    if (/Failed to load resource|net::ERR_|WebSocket/i.test(text)) return;
    errors.push(`console.error: ${text}`);
  });
  return { errors };
}

test.describe('Phase 0 baseline', () => {
  test('app loads', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/');
    await expect(page.locator('.tab-bar')).toBeVisible();
    await expect(page.getByRole('button', { name: /^Dashboard/ })).toBeVisible();
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('tabs switch', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/');
    const gappers = page.getByRole('button', { name: /^Gappers/ });
    await gappers.click();
    await expect(gappers).toHaveClass(/active/);
    await expect(page.locator('.tab.active')).toContainText('Gappers');

    const account = page.getByTestId('header-account-btn');
    await account.click();
    await expect(account).toHaveClass(/active/);
    await expect(page.getByTestId('account-view')).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Reports' })).toBeVisible();
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('Trader window opens via URL and has no page scroll', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=stock&symbol=AAPL');

    await expect(page.locator('.stock-view-page')).toBeVisible();
    await expect(page.getByTestId('stock-view-header')).toBeVisible();
    await expect(page.getByText('Trader', { exact: true })).toBeVisible();
    await expect(page).toHaveTitle(/AAPL.*Trader/);

    const noPageScroll = await page.evaluate(() => {
      const el = document.documentElement;
      return el.scrollHeight === el.clientHeight;
    });
    expect(noPageScroll, 'documentElement must not page-scroll on Trader').toBe(true);

    // Terminal composition: charts + rail (when detail loads)
    await expect(page.getByTestId('stock-view-rail')).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('.stock-view-charts .chart-grid')).toBeVisible();
    await expect(page.locator('.manual-order-ticket')).toBeVisible();

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});

