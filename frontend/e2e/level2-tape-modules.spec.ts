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

async function lookUpSymbol(page: Page, symbol: string) {
  const input = page.getByLabel('Look up symbol');
  await input.fill(symbol);
  await page.getByRole('button', { name: 'Look Up' }).click();
}

test.describe('Phase 1 — Level 2 + Time & Sales modules', () => {
  test('Stock View renders independent L2 and T&S modules', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=stock&symbol=AAPL');

    await expect(page.locator('.stock-view-page')).toBeVisible();

    const l2 = page.locator('[data-module="level2"]');
    const tape = page.locator('[data-module="time-sales"]');

    // Requires IBKR connected + ticker detail match (same gate as production quote path).
    await expect(l2).toBeVisible({ timeout: 30_000 });
    await expect(tape).toBeVisible();
    await expect(l2).toHaveAttribute('data-symbol', 'AAPL');
    await expect(tape).toHaveAttribute('data-symbol', 'AAPL');
    // Matched pane headers — no stacked "Level 2 · Time & Sales" + "Time & Sales".
    const stack = page.locator('[data-testid="stock-view-depth-stack"]');
    await expect(stack.locator('.sv-module-card__title')).toHaveCount(0);
    await expect(page.locator('.sv-md-pane__title').filter({ hasText: 'Level 2' })).toBeVisible();
    await expect(page.locator('.sv-md-pane__title').filter({ hasText: 'Time & Sales' })).toBeVisible();

    const titleColor = await page.locator('.sv-md-pane__title').filter({ hasText: 'Time & Sales' }).evaluate((el) => {
      const style = getComputedStyle(el);
      return { color: style.color, bgImage: style.backgroundImage };
    });
    // Must not be ~4% white (token collision) or hero-bg on module chrome.
    expect(titleColor.color).not.toMatch(/rgba?\(\s*255,\s*255,\s*255,\s*0\.0[0-4]/);
    expect(titleColor.bgImage).toBe('none');

    const tapeCol = page.locator('[data-testid="stock-view-tape-col"]');
    const overflow = await tapeCol.evaluate((el) => {
      const panel = el.querySelector('.ts-panel, .sv-md-pane') as HTMLElement | null;
      if (!panel) return { scrollWidth: 0, clientWidth: 0 };
      return { scrollWidth: panel.scrollWidth, clientWidth: panel.clientWidth };
    });
    expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth + 2);

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('symbol switch clears L2 and T&S independently', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=stock&symbol=AAPL');

    const l2 = page.locator('[data-module="level2"]');
    const tape = page.locator('[data-module="time-sales"]');
    await expect(l2).toBeVisible({ timeout: 30_000 });
    await expect(tape).toHaveAttribute('data-symbol', 'AAPL');

    await lookUpSymbol(page, 'MSFT');
    await expect(page).toHaveTitle(/MSFT/, { timeout: 15_000 });

    // Modules remount with the new symbol key — prior symbol must not linger.
    await expect(l2).toHaveAttribute('data-symbol', 'MSFT', { timeout: 30_000 });
    await expect(tape).toHaveAttribute('data-symbol', 'MSFT');
    await expect(page.locator('[data-module="level2"][data-symbol="AAPL"]')).toHaveCount(0);
    await expect(page.locator('[data-module="time-sales"][data-symbol="AAPL"]')).toHaveCount(0);
    // Both modules still present for the new symbol (independent remount, not shared glue state).
    await expect(l2).toBeVisible();
    await expect(tape).toBeVisible();

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
