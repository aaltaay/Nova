import { test, expect } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';

/**
 * #449: the sample desk has its own workspace -- Trader tabs, the Focus rail
 * and pop-out -- held in memory. It demos them, opens the Market page, and
 * saves none of it: the browser's localStorage for the origin stays empty.
 */
test.describe('Sample desk workspace', () => {
  test('Trader tabs, Focus rail, pop-out and the Market page work on the sample desk and save nothing', async ({ page, baseURL }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample&symbol=SMPL');
    await expect(page.getByTestId('sample-data-badge')).toBeVisible();

    // The URL's symbol is the one tab; the Focus rail lists the sample Gappers.
    await expect(page.getByTestId('sv-tab-SMPL')).toHaveAttribute('aria-selected', 'true');
    const rail = page.getByTestId('focus-rail');
    await expect(rail).toBeVisible();
    await expect(rail.getByTestId('focus-rail-list-label')).toContainText('Gappers');

    // Open from the rail, then switch back.
    await rail.getByTestId('focus-rail-row-GAPX').click();
    await expect(page.getByTestId('sv-tab-GAPX')).toHaveAttribute('aria-selected', 'true');
    await expect(page).toHaveURL(/[?&]symbol=GAPX/);
    await page.getByTestId('sv-tab-SMPL').locator('.sv-tab__label').click();
    await expect(page.getByTestId('sv-tab-SMPL')).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByTestId('sv-tab-GAPX')).toHaveAttribute('aria-selected', 'false');

    // Pop GAPX out: a sample window, never the live `?view=stock` one.
    const popupPromise = page.waitForEvent('popup');
    await page.getByTestId('sv-tab-GAPX').hover();
    await page.getByTestId('sv-tab-extract-GAPX').click();
    const popup = await popupPromise;
    await expect(popup).toHaveURL(/[?&]view=sample/);
    await expect(popup).toHaveURL(/[?&]popout=1/);
    await expect(popup).toHaveURL(/[?&]symbol=GAPX/);
    await expect(popup.getByTestId('sample-data-badge')).toBeVisible();
    await expect(popup.getByTestId('sv-tab-GAPX')).toBeVisible();
    // It cannot dock back into the sample desk, and says so.
    const dock = popup.getByTestId('float-desk-dock');
    await expect(dock).toBeDisabled();
    await expect(dock).toHaveAttribute('data-why', /sample pop-out does not dock back/);
    await popup.close();
    await expect(page.getByTestId('sv-tab-GAPX')).toHaveCount(0);

    // The Market page (ADR 053) opens on the sample desk too, never "not available".
    await page.getByTestId('nav-rail-market').click();
    const market = page.getByTestId('market-page');
    await expect(market).toBeVisible();
    await expect(market).not.toContainText('not available');

    // The Forex page (ADR 062), first on the rail, opens on the sample desk with the whole market's size.
    await page.getByTestId('nav-rail-forex').click();
    const forex = page.getByTestId('forex-page');
    await expect(forex).toBeVisible();
    await expect(forex).toContainText('$9.51T');
    await expect(page.getByTestId('forex-row-EUR')).toBeVisible();

    // The Global page (ADR 060), under Forex on the rail, opens on the sample desk too.
    await page.getByTestId('nav-rail-global').click();
    const global = page.getByTestId('global-page');
    await expect(global).toBeVisible();
    await expect(global).toContainText('Rotation, not an exit');
    await expect(page.getByTestId('global-row-us')).toBeVisible();

    // Nothing the sample desk did reached the browser's storage. storageState
    // reads it from an isolated world, past the page's storage gate.
    const state = await page.context().storageState();
    const origin = new URL(baseURL ?? page.url()).origin;
    const saved = state.origins.find((o) => o.origin === origin)?.localStorage ?? [];
    expect(saved.map((item) => item.name)).toEqual([]);

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
