import { test, expect } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';

test.describe('Fund account', () => {
  test('opens IBKR Client Portal from beside the rail Account item', async ({ page, context }, testInfo) => {
    const { errors } = attachErrorCollector(page);
    const portalUrl = 'https://www.interactivebrokers.com/sso/Login';
    const portalRequests: string[] = [];
    // Verify the intended navigation without depending on the remote broker website or logging in.
    await context.route(portalUrl, async route => {
      portalRequests.push(route.request().url());
      await route.fulfill({ contentType: 'text/html', body: '<!doctype html><title>Fixture Client Portal</title>' });
    });
    await page.goto('/?view=sample');

    // Fund account lives in a popover beside the nav rail's Account item.
    const fund = page.getByTestId('global-bar-fund-account');
    await expect(fund).toHaveCount(0);
    const account = page.getByTestId('nav-rail-account');
    // Initial lazy-module readiness only, see architecture/frontend-live-render-contract.md.
    await expect(account).toBeVisible({ timeout: 20_000 });
    await account.hover();

    const menu = page.getByTestId('nav-rail-account-menu');
    await expect(menu).toBeVisible();
    await expect(menu.getByTestId('global-bar-fund-account')).toBeVisible();
    await expect(fund).toHaveText('Fund account');
    await expect(fund).toHaveAttribute('title', /Client Portal/);
    await expect(fund).toHaveAttribute('title', /does not deposit/i);

    const popupPromise = page.waitForEvent('popup');
    await fund.click();
    const popup = await popupPromise;
    await expect(popup).toHaveURL(portalUrl);
    expect(portalRequests).toEqual([portalUrl]);
    await popup.close();

    await page.getByTestId('nav-rail').screenshot({
      path: testInfo.outputPath('nav-rail-fund-account.png'),
    });
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
