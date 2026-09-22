import { test, expect, type Page } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';

/**
 * Switch the Trader the way the operator does: "+" opens a draft tab in the
 * strip, type the ticker, Enter -- then close the old tab. The Trader has no
 * Look Up form, and a live tab left open keeps its L2 / T&S mounted (hidden),
 * so closing it is what retires the prior symbol.
 */
async function switchTraderSymbol(page: Page, from: string, to: string) {
  await page.getByTestId('sv-tab-add').click();
  const input = page.getByTestId('sv-tab-New').getByLabel('Edit ticker');
  await input.fill(to);
  await input.press('Enter');
  await expect(page.getByTestId(`sv-tab-${to}`)).toHaveAttribute('aria-selected', 'true');
  // A pop-out's URL follows its active tab; closing the tab the URL still
  // names would close the window instead.
  await expect(page).toHaveURL(new RegExp(`[?&]symbol=${to}(&|$)`));
  await page.getByTestId(`sv-tab-${from}`).hover();
  await page.getByTestId(`sv-tab-close-${from}`).click();
  await expect(page.getByTestId(`sv-tab-${from}`)).toHaveCount(0);
}

test.describe('Phase 1 — Level 2 + Time & Sales modules', () => {
  test.skip(
    process.env.NOVA_E2E_LIVE_IBKR !== '1',
    'Requires local IBKR READY; deterministic CI has no Gateway',
  );

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

    await switchTraderSymbol(page, 'AAPL', 'MSFT');
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
