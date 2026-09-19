import { test, expect } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';

test.describe('Fund account', () => {
  test('opens IBKR Client Portal from under the Account icon', async ({ page }, testInfo) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample');

    // Slim header: Fund account lives in a popover under the Account icon.
    const fund = page.getByTestId('global-bar-fund-account');
    await expect(fund).toHaveCount(0);
    const account = page.getByTestId('global-bar-account-nav');
    await expect(account).toBeVisible();
    await account.hover();

    const menu = page.getByTestId('global-bar-account-menu');
    await expect(menu).toBeVisible();
    await expect(menu.getByTestId('global-bar-fund-account')).toBeVisible();
    await expect(fund).toHaveText('Fund account');
    await expect(fund).toHaveAttribute('title', /Client Portal/);
    await expect(fund).toHaveAttribute('title', /does not deposit/i);

    const popupPromise = page.waitForEvent('popup');
    await fund.click();
    const popup = await popupPromise;
    await expect(popup).toHaveURL(/interactivebrokers\.com\/sso\/Login/);
    await popup.close();

    await page.getByTestId('global-app-bar').screenshot({
      path: testInfo.outputPath('global-bar-fund-account.png'),
    });
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
