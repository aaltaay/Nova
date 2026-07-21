import { test, expect, type ConsoleMessage, type Page } from '@playwright/test';

/** Mirrors LAYOUT_STORAGE_KEY — avoid importing Vite-bound constants in e2e. */
const LAYOUT_STORAGE_KEY = 'nova_workspace_layout_v1';
const MODULE_VISIBILITY_STORAGE_KEY = 'nova_module_visibility_v1';

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

test.describe('Phase 5 — Layout store panel order', () => {
  test('layout localStorage persists across reload', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/');
    await page.evaluate(
      ([layoutKey, visKey]) => {
        localStorage.removeItem(visKey);
        localStorage.setItem(
          layoutKey,
          JSON.stringify({
            version: 1,
            slots: {
              side_panel: ['news', 'quote', 'charts', 'level2', 'tape'],
              stock_view: ['level2', 'tape', 'news', 'quote', 'charts'],
            },
            sizes: {},
          }),
        );
      },
      [LAYOUT_STORAGE_KEY, MODULE_VISIBILITY_STORAGE_KEY] as const,
    );
    await page.reload();
    await expect(page.locator('.tab-bar')).toBeVisible();

    const stored = await page.evaluate((key) => localStorage.getItem(key), LAYOUT_STORAGE_KEY);
    expect(stored).toBeTruthy();
    expect(JSON.parse(stored!).slots.side_panel[0]).toBe('news');
    // Modules menu retired — no UI reorder surface.
    await expect(page.getByTestId('modules-menu')).toHaveCount(0);

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('side panel quote blocks follow saved layout order', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/');
    await page.evaluate((key) => {
      localStorage.setItem(
        key,
        JSON.stringify({
          version: 1,
          slots: {
            side_panel: ['news', 'quote', 'charts', 'level2', 'tape'],
            stock_view: ['level2', 'tape', 'news', 'quote', 'charts'],
          },
          sizes: {},
        }),
      );
    }, LAYOUT_STORAGE_KEY);
    await page.reload();
    await expect(page.locator('.tab-bar')).toBeVisible();

    const search = page.locator('.side-panel .side-search-input');
    await expect(search).toBeVisible();
    await search.fill('AAPL');
    await page.locator('.side-panel .side-search-btn').click();

    const detailBody = page.locator('.side-panel .detail-body .cq-root');
    await expect(detailBody).toBeVisible({ timeout: 30_000 });

    const blocks = detailBody.locator('[data-layout-block]');
    await expect(blocks.first()).toHaveAttribute('data-layout-block', 'news', { timeout: 15_000 });

    const order = await blocks.evaluateAll((els) =>
      els.map((el) => el.getAttribute('data-layout-block')),
    );
    expect(order[0]).toBe('news');
    expect(order).toContain('quote');

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
