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
    if (/Failed to load resource|net::ERR_|WebSocket|Scanner API network error/i.test(text)) return;
    errors.push(`console.error: ${text}`);
  });
  return { errors };
}

test.describe('Phase 3 — Quote panels / Stock View terminal', () => {
  test('Stock View terminal shows header, charts, rail ticket — no scanner clutter', async ({
    page,
  }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample&symbol=SMPL');

    await expect(page.getByRole('main')).toBeVisible();
    await expect(page.getByTestId('stock-view-header')).toHaveCount(0);
    await expect(page.getByRole('complementary', { name: 'Trader' })).toBeVisible();

    // Compact quote card (not Quote Panel modules)
    await expect(page.getByRole('region', { name: 'Stock Quote' })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Trade order' })).toBeVisible();
    await expect(page.locator('.ticker-trade-bar--rail')).toBeVisible();

    // Symbol / price live under Stock Quote, not a second command bar
    await expect(page.getByRole('region', { name: 'Stock Quote' })).toContainText(/SMPL/i);

    // Scanner Quote Panel clutter must not appear in Stock View rail
    await expect(page.locator('[data-module="data-sources"]')).toHaveCount(0);
    await expect(page.locator('[data-module="watchlist-strip"]')).toHaveCount(0);
    await expect(page.locator('.stock-view-news-footer')).toHaveCount(0);

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
