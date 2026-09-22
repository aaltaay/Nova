import { test, expect } from '@playwright/test';
import {
  QUOTE_PANEL_LOOKUP_ARIA,
  QUOTE_PANEL_LOOKUP_LABEL,
} from '../src/constantGroups/scanner_board';
import { attachErrorCollector } from './helpers/errorCollector';

test.describe('Phase 2 — WorkspaceContext', () => {
  test('Trader URL still opens under WorkspaceProvider', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=stock&symbol=MSFT');

    await expect(page.locator('.stock-view-page')).toBeVisible();
    await expect(page.getByTestId('scanner-desk')).toHaveCount(0);
    await expect(page).toHaveTitle(/MSFT.*Trader/);
    // A ?view=stock URL is a pop-out float: thin float chrome, no main header.
    const chrome = page.getByTestId('float-desk-chrome');
    await expect(chrome).toBeVisible();
    await expect(chrome).toContainText('Pop-out');
    await expect(chrome).toContainText('MSFT');
    await expect(page.getByTestId('global-app-bar')).toHaveCount(0);
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('quote panel Trader button opens an in-app tab, not a popup', async ({
    page,
  }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/');

    const sideInput = page.locator('.side-panel').getByLabel(QUOTE_PANEL_LOOKUP_ARIA);
    await sideInput.fill('AAPL');
    await page.locator('.side-panel').getByRole('button', { name: QUOTE_PANEL_LOOKUP_LABEL }).click();

    const openBtn = page.locator('.side-panel').getByRole('button', { name: /Trader/i });
    await expect(openBtn).toBeVisible({ timeout: 15_000 });
    await openBtn.click();

    await expect(page.locator('[data-testid="sv-tabs-root"]')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[data-testid="sv-tab-AAPL"]')).toBeVisible();
    await expect(page.locator('.stock-view-page')).toBeVisible();
    await expect(page.getByTestId('scanner-desk')).toHaveCount(0);
    expect(page.url()).not.toMatch(/view=stock/);

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('rail Trader keeps chrome and opens an in-app tab', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/');

    await expect(page.getByTestId('global-app-bar')).toBeVisible();
    await page.getByTestId('nav-rail-trader').click();

    await expect(page.getByTestId('global-app-bar')).toBeVisible();
    await expect(page.getByTestId('sv-tabs-root')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('sv-tab-SPY')).toBeVisible();
    await expect(page.getByTestId('scanner-desk')).toHaveCount(0);
    await expect(page.getByTestId('nav-rail-trader')).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(page.url()).not.toMatch(/view=stock/);
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
