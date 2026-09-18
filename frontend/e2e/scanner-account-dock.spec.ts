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
});
