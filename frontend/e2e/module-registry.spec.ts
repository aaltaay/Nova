import { test, expect, type ConsoleMessage, type Page } from '@playwright/test';

/** Mirrors MODULE_VISIBILITY_STORAGE_KEY — avoid importing Vite-bound constants in e2e. */
const MODULE_VISIBILITY_STORAGE_KEY = 'nova_module_visibility_v1';

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

async function clearModuleVisibility(page: Page) {
  await page.goto('/');
  await page.evaluate((key) => {
    localStorage.removeItem(key);
  }, MODULE_VISIBILITY_STORAGE_KEY);
  await page.reload();
  await expect(page.locator('.tab-bar')).toBeVisible();
}

test.describe('Phase 4 — Module registry tabs', () => {
  test('TabNav renders registry tabs including Gainers and Losers', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await clearModuleVisibility(page);

    await expect(page.locator('[data-tab="gappers"]')).toBeVisible();
    await expect(page.locator('[data-tab="gainers"]')).toBeVisible();
    await expect(page.locator('[data-tab="losers"]')).toBeVisible();
    await expect(page.locator('[data-tab="watchlist"]')).toBeVisible();
    // Modules menu removed from the tab bar (power-user UI retired).
    await expect(page.getByTestId('modules-menu')).toHaveCount(0);

    await page.locator('[data-tab="gainers"]').click();
    await expect(page.locator('.tab-bar')).toHaveAttribute('data-active-tab', 'gainers');

    await page.locator('[data-tab="losers"]').evaluate((el: HTMLElement) => el.click());
    await expect(page.locator('.tab-bar')).toHaveAttribute('data-active-tab', 'losers');
    await expect(page.locator('[data-tab="losers"]')).toHaveClass(/active/);

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('module visibility from localStorage still hides tabs', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/');
    await page.evaluate((key) => {
      localStorage.setItem(key, JSON.stringify({ gappers: false }));
    }, MODULE_VISIBILITY_STORAGE_KEY);
    await page.reload();
    await expect(page.locator('.tab-bar')).toBeVisible();
    await expect(page.locator('[data-tab="gappers"]')).toHaveCount(0);
    await expect(page.locator('[data-tab="gainers"]')).toBeVisible();
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
