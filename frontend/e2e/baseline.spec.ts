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

    const trading = page.getByRole('button', { name: /^Trading/ });
    await trading.click();
    await expect(trading).toHaveClass(/active/);
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('Stock View opens via URL and has no page scroll', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=stock&symbol=AAPL');

    await expect(page.locator('.stock-view-page')).toBeVisible();
    await expect(page.getByText('Stock View', { exact: true })).toBeVisible();
    await expect(page).toHaveTitle(/AAPL/);

    const noPageScroll = await page.evaluate(() => {
      const el = document.documentElement;
      return el.scrollHeight === el.clientHeight;
    });
    expect(noPageScroll, 'documentElement must not page-scroll on Stock View').toBe(true);

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
