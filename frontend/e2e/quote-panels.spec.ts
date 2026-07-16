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

test.describe('Phase 3 — Quote panels', () => {
  test('Stock View quote panel shows symbol, price surface, and news module', async ({
    page,
  }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=stock&symbol=MSFT');

    await expect(page.locator('.stock-view-page')).toBeVisible();
    await expect(page.locator('.stock-view-quote')).toBeVisible({ timeout: 20_000 });

    // Panel modules mounted (composition)
    await expect(page.locator('[data-module="quote-header"]')).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('[data-module="news"]')).toBeVisible();
    await expect(page.locator('[data-module="fundamentals"]').first()).toBeVisible();
    await expect(page.locator('[data-module="data-sources"]')).toBeVisible();
    await expect(page.locator('[data-module="watchlist-strip"]')).toBeVisible();

    // Symbol / price (header may live on Stock View chrome + quote panel)
    await expect(page.locator('.stock-view-quote .cq-symbol')).toContainText(/MSFT/i, {
      timeout: 20_000,
    });
    // Price cell appears once quote stream/detail loads; tolerate loading then settle
    const price = page.locator('.stock-view-quote .cq-price');
    await expect(price).toBeVisible({ timeout: 30_000 });

    // News module present (populated headlines or empty attribute)
    const news = page.locator('[data-module="news"]');
    await expect(news).toHaveAttribute('data-news-empty', /true|false/);

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
