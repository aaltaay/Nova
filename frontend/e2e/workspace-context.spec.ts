import { test, expect } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';

test.describe('Phase 2 — WorkspaceContext', () => {
  test('Trader URL still opens under WorkspaceProvider', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=stock&symbol=MSFT');

    await expect(page.locator('.stock-view-page')).toBeVisible();
    await expect(page).toHaveTitle(/MSFT.*Trader/);
    await expect(page.getByText('Trader', { exact: true })).toBeVisible();
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('quote panel Trader button opens an in-app tab, not a popup', async ({
    page,
  }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/');

    const sideInput = page.locator('.side-panel').getByLabel('Look up symbol');
    await sideInput.fill('AAPL');
    await page.locator('.side-panel').getByRole('button', { name: 'Look Up' }).click();

    const openBtn = page.locator('.side-panel').getByRole('button', { name: /Trader/i });
    await expect(openBtn).toBeVisible({ timeout: 15_000 });
    await openBtn.click();

    await expect(page.locator('[data-testid="sv-tabs-root"]')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[data-testid="sv-tab-AAPL"]')).toBeVisible();
    await expect(page.locator('.stock-view-page')).toBeVisible();
    expect(page.url()).not.toMatch(/view=stock/);

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
