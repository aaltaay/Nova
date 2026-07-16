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

async function clearLayoutAndVisibility(page: Page) {
  await page.goto('/');
  await page.evaluate(
    ([layoutKey, visKey]) => {
      localStorage.removeItem(layoutKey);
      localStorage.removeItem(visKey);
    },
    [LAYOUT_STORAGE_KEY, MODULE_VISIBILITY_STORAGE_KEY] as const,
  );
  await page.reload();
  await expect(page.locator('.tab-bar')).toBeVisible();
}

test.describe('Phase 5 — Layout store panel order', () => {
  test('reorder via Modules menu persists across reload', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await clearLayoutAndVisibility(page);

    await page.getByTestId('modules-menu').getByRole('button', { name: /^Modules$/ }).click();
    await expect(page.getByTestId('layout-order-section')).toBeVisible();
    await expect(page.getByTestId('layout-order-list')).toBeVisible();

    // Default side_panel order starts with Charts
    const firstBefore = page.locator('[data-layout-order-id]').first();
    await expect(firstBefore).toHaveAttribute('data-layout-order-id', 'charts');

    // Move News up until it is first (charts, level2, tape, news, quote → news first)
    // From index 3: up×3
    const newsUp = page.locator('[data-layout-move="up"][data-layout-move-id="news"]');
    await newsUp.click();
    await newsUp.click();
    await newsUp.click();

    await expect(page.locator('[data-layout-order-id]').first()).toHaveAttribute(
      'data-layout-order-id',
      'news',
    );

    const storedBefore = await page.evaluate((key) => localStorage.getItem(key), LAYOUT_STORAGE_KEY);
    expect(storedBefore).toBeTruthy();
    const parsedBefore = JSON.parse(storedBefore!);
    expect(parsedBefore.version).toBe(1);
    expect(parsedBefore.slots.side_panel[0]).toBe('news');

    await page.reload();
    await expect(page.locator('.tab-bar')).toBeVisible();

    const stored = await page.evaluate((key) => localStorage.getItem(key), LAYOUT_STORAGE_KEY);
    expect(stored).toBeTruthy();
    expect(JSON.parse(stored!).slots.side_panel[0]).toBe('news');

    await page.getByTestId('modules-menu').getByRole('button', { name: /^Modules$/ }).click();
    await expect(page.locator('[data-layout-order-id]').first()).toHaveAttribute(
      'data-layout-order-id',
      'news',
    );

    // Reset restores defaults
    await page.getByTestId('layout-reset').click();
    await expect(page.locator('[data-layout-order-id]').first()).toHaveAttribute(
      'data-layout-order-id',
      'charts',
    );

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

    // Select a symbol so the side panel mounts TickerDetailContent
    const search = page.locator('.side-panel .side-search-input');
    await expect(search).toBeVisible();
    await search.fill('AAPL');
    await page.locator('.side-panel .side-search-btn').click();

    // Wait for quote body (may be loading)
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
