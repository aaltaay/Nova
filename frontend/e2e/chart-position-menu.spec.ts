import { test, expect } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';

test.describe('Chart position tag menu', () => {
  test('sample SMPL Long tag opens Close Position and View Trade Details', async ({
    page,
  }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample&symbol=SMPL');
    await expect(page.getByTestId('chart-desk-toolbar')).toBeVisible();

    const tag = page.getByTestId('chart-position-tag-btn').first();
    await expect(tag).toBeVisible();
    await expect(tag).toContainText(/Long 200/);
    await page.screenshot({
      path: 'test-results/chart-position-tag.png',
      fullPage: true,
    });

    await tag.click();
    const menu = page.getByTestId('chart-position-menu');
    await expect(menu).toBeVisible();
    await expect(page.getByTestId('chart-position-menu-close')).toHaveText(
      'Close Position',
    );
    await expect(page.getByTestId('chart-position-menu-details')).toHaveText(
      'View Trade Details',
    );
    await page.screenshot({
      path: 'test-results/chart-position-menu-open.png',
      fullPage: true,
    });

    await page.keyboard.press('Escape');
    await expect(menu).toHaveCount(0);

    await tag.click();
    await page.getByTestId('chart-position-menu-details').click();
    await expect(page.getByTestId('stock-view-positions')).toBeVisible();
    await expect(page.getByTestId('positions-table')).toContainText('SMPL');
    await page.screenshot({
      path: 'test-results/chart-position-view-details.png',
      fullPage: true,
    });

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
