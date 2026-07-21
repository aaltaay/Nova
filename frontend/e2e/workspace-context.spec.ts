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
    if (/Failed to load resource|net::ERR_|WebSocket/i.test(text)) return;
    errors.push(`console.error: ${text}`);
  });
  return { errors };
}

test.describe('Phase 2 — WorkspaceContext', () => {
  test('Trader URL still opens under WorkspaceProvider', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=stock&symbol=MSFT');

    await expect(page.locator('.stock-view-page')).toBeVisible();
    await expect(page).toHaveTitle(/MSFT.*Trader/);
    await expect(page.getByText('Trader', { exact: true })).toBeVisible();
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('quote panel Trader button opens detached window via openStockView', async ({
    page,
    context,
  }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/');

    const sideInput = page.locator('.side-panel').getByLabel('Look up symbol');
    await sideInput.fill('AAPL');
    await page.locator('.side-panel').getByRole('button', { name: 'Look Up' }).click();

    const openBtn = page.locator('.side-panel').getByRole('button', { name: /Trader/i });
    await expect(openBtn).toBeVisible({ timeout: 15_000 });

    const popupPromise = context.waitForEvent('page', { timeout: 10_000 });
    await openBtn.click();
    const popup = await popupPromise;

    await popup.waitForLoadState('domcontentloaded');
    await expect(popup.locator('.stock-view-page')).toBeVisible({ timeout: 15_000 });
    expect(popup.url()).toMatch(/view=stock/);
    expect(popup.url()).toMatch(/symbol=AAPL/i);
    await popup.close();

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
