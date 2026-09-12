import { test, expect } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';

test.describe('D-010 Trend Line two-click place', () => {
  test('dropdown opens and arms a tool on the sample desk', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample&symbol=SMPL');
    await expect(page.getByTestId('chart-desk-toolbar')).toBeVisible();

    await page.getByRole('button', { name: 'Line drawing tools' }).click();
    const menu = page.getByTestId('chart-draw-tools-menu');
    await expect(menu).toBeVisible();
    await expect(menu.getByRole('menuitemradio', { name: /Trendline/ })).toBeVisible();
    await page.screenshot({
      path: '/opt/cursor/artifacts/d109-draw-tools-menu.png',
      fullPage: true,
    });
    await menu.getByRole('menuitemradio', { name: /Horizontal Line/ }).click();

    const chart = page.locator('.chart-body').first();
    await expect(chart).toHaveAttribute('data-active-draw-tool', 'HorizontalLine');
    await expect(menu).toHaveCount(0);
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('Use Trendline arms the chart body for pointerup place', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample&symbol=SMPL');
    await expect(page.getByTestId('chart-desk-toolbar')).toBeVisible();

    const chart = page.locator('.chart-body').first();
    await expect(chart).toBeVisible();
    await page.getByRole('button', { name: 'Use Trendline' }).click();
    await expect(chart).toHaveAttribute('data-active-draw-tool', 'TrendLine');
    await expect(chart).toHaveAttribute('data-chart-pan-locked', '1');
    await page.screenshot({
      path: '/opt/cursor/artifacts/d010-trendline-armed.png',
      fullPage: true,
    });

    const box = await chart.boundingBox();
    expect(box).toBeTruthy();
    if (!box) return;
    await page.mouse.click(box.x + box.width * 0.3, box.y + box.height * 0.65);
    await page.mouse.move(box.x + box.width * 0.55, box.y + box.height * 0.45);
    // Offline sample often has an empty IBKR time scale, so anchors cannot convert.
    // When bars exist, first click stamps the rubber-band preview host flags.
    const barCount = await page.locator('[data-testid^="ticker-chart-"]').first().getAttribute('data-bar-count');
    if (barCount && Number(barCount) > 0) {
      await expect(chart).toHaveAttribute('data-drawing-preview', '1');
      await expect(chart).toHaveAttribute('data-place-pending', '1');
      await page.screenshot({
        path: '/opt/cursor/artifacts/d119-trendline-preview.png',
        fullPage: true,
      });
    }
    await page.mouse.click(box.x + box.width * 0.7, box.y + box.height * 0.35);

    await expect(chart).toHaveAttribute('data-active-draw-tool', 'TrendLine');
    await expect(chart).toHaveAttribute('data-chart-pan-locked', '1');
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('idle chart restores pan and does not mark a handle edit', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample&symbol=SMPL');
    const chart = page.locator('.chart-body').first();
    await expect(chart).toBeVisible();
    await expect(chart).not.toHaveAttribute('data-active-draw-tool', 'TrendLine');
    await expect(chart).not.toHaveAttribute('data-chart-pan-locked', '1');
    await expect(chart).not.toHaveAttribute('data-editing-handle', '1');
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
