import { test, expect } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';

test.describe('Scanner account dock', () => {
  test('sample scanner shows the Trader Positions strip', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample');

    await expect(page.getByTestId('scanner-desk')).toBeVisible();
    await expect(page.getByTestId('stock-view-open-orders-dock')).toBeVisible();
    await page.getByTestId('stock-view-dock-tab-positions').click();
    await expect(page.getByTestId('stock-view-positions')).toBeVisible();
    await expect(page.getByTestId('positions-table')).toContainText('SMPL');

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
