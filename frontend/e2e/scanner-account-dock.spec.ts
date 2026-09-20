import { test, expect } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';
import { scannerOrdersDock } from './helpers/ordersDock';

test.describe('Scanner account dock', () => {
  test('sample scanner shows the Trader Positions strip', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample');

    const desk = page.getByTestId('scanner-desk');
    await expect(desk).toBeVisible();
    const dock = scannerOrdersDock(page);
    await expect(dock).toBeVisible();
    await dock.getByTestId('stock-view-dock-tab-positions').click();
    await expect(dock.getByTestId('stock-view-positions')).toBeVisible();
    await expect(dock.getByTestId('positions-table')).toContainText('SMPL');

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  // #357: the sample desk is a marketing surface and CI runs with no Nova API,
  // so both of these must hold without a backend.
  test('sample desk is badged and shows its own account figures', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample');

    const badge = page.getByTestId('sample-data-badge');
    await expect(badge).toBeVisible();
    await expect(badge).toContainText('Nova Marketing Sample Data');

    // The header must not contradict its own GATEWAY-connected chip.
    await expect(page.getByTestId('global-bar-cluster')).toBeVisible();
    await expect(page.getByTestId('global-bar-offline')).toHaveCount(0);
    await expect(page.getByTestId('global-bar-account-trigger')).toContainText('+$230.00');
    await expect(page.locator('.global-app-bar__metric--netliq')).toContainText('$100,000.00');

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
